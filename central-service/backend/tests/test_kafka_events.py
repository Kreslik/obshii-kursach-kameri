"""Producer → настоящий брокер → отдельный процесс центра → PostgreSQL и offset группы."""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import datetime, timedelta
from dataclasses import asdict
from unittest.mock import patch
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from confluent_kafka import Consumer, ConsumerGroupTopicPartitions, Producer, TopicPartition
from confluent_kafka.admin import AdminClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.alerts.models import Alert
from app.audit.models import AuditLog
from app.access_requests.models import AccessRequest
from app.catalog.models import Camera, EdgeNode, RequestType, RoiZone, Substation
from app.users.models import User
from app.node_events.schemas import decode_event
from app.monitoring.heartbeat import record_heartbeat
from app.detections.models import Detection
from app.node_events.consumer import ensure_topics
from db_fixture import isolated_schema


@unittest.skipUnless(os.getenv("TEST_POSTGRES") == "1" and os.getenv("TEST_KAFKA") == "1",
                     "Требуются тестовые подключения к PostgreSQL и Kafka")
class KafkaEventsTest(unittest.TestCase):
    def setUp(self):
        self.engine = self.enterContext(isolated_schema())
        command.upgrade(Config("alembic.ini"), "head")
        with Session(self.engine) as session, session.begin():
            for station, zone in [(10, 101), (20, 102)]:
                session.add(Substation(id=station, code=str(station), name=str(station)))
                session.flush()
                session.add(EdgeNode(id=station+100, substation_id=station, name="узел", api_key_hash="test"))
                session.flush()
                session.add(Camera(substation_id=station, camera_id=1, node_id=station+100, name="камера", rtsp_url="rtsp://example"))
                session.flush()
                session.add(RoiZone(id=zone, substation_id=station, camera_id=1, name="зона", polygon=[]))

        self.group = "test-" + uuid4().hex
        self.status = self.group + ".status"
        self.detections = self.group + ".detections"
        self.heartbeat = self.group + ".heartbeat"
        self.topics = [self.status, self.detections, self.heartbeat]
        bootstrap = os.environ["KAFKA_BOOTSTRAP_SERVERS"]
        self.enterContext(patch.dict(os.environ, {
            "KAFKA_GROUP_ID": self.group, "KAFKA_STATUS_TOPIC": self.status,
            "KAFKA_DETECTIONS_TOPIC": self.detections, "KAFKA_HEARTBEAT_TOPIC": self.heartbeat,
        }))
        ensure_topics(bootstrap, self.topics)
        self.admin = AdminClient({"bootstrap.servers": bootstrap})
        self.addCleanup(self.remove_topics)
        self.producer = Producer({"bootstrap.servers": bootstrap, "acks": "all", "message.timeout.ms": 10000})
        self.observer = Consumer({"bootstrap.servers": bootstrap, "group.id": self.group, "enable.auto.commit": False})
        self.addCleanup(self.observer.close)
        self.targets = {}

    def remove_topics(self):
        for future in self.admin.delete_topics(self.topics, request_timeout=10).values():
            future.result()

    def start_consumer(self):
        self.output = self.enterContext(tempfile.TemporaryFile(mode="w+"))
        self.worker = subprocess.Popen([sys.executable, "-m", "app.node_events.consumer"],
                                       stdout=self.output, stderr=subprocess.STDOUT)
        self.addCleanup(self.stop_consumer)

    def stop_consumer(self):
        if self.worker.poll() is None:
            self.worker.terminate()
            self.worker.wait(timeout=30)

    def publish(self, topic, key, body):
        delivered = []
        self.producer.produce(topic, key=key.encode(), value=json.dumps(body).encode(),
                              on_delivery=lambda error, msg: delivered.append((error, msg)))
        self.assertEqual(self.producer.flush(15), 0)
        error, msg = delivered[0]
        self.assertIsNone(error)
        self.targets[(topic, msg.partition())] = msg.offset() + 1

    def await_commits(self):
        deadline = time.monotonic() + 45
        partitions = [TopicPartition(topic, p) for topic, p in self.targets]
        while time.monotonic() < deadline:
            if self.worker.poll() is not None:
                self.output.seek(0)
                self.fail(self.output.read())
            positions = self.observer.committed(partitions, timeout=10)
            if all(p.offset == self.targets[(p.topic, p.partition)] for p in positions):
                return
            time.sleep(0.2)
        self.fail(f"Не достигнуты позиции {self.targets}, получены {positions}")

    def detection(self):
        return {
            "id": str(uuid4()), "camera_id": 1, "zone_id": 101, "detected_time": "2026-11-25T12:00:00+03:00",
            "person_count": 2, "confidence": 0.97, "is_alert": True, "file": r"D:\frames\камера 1.jpg", "Sender": 10,
        }

    def test_events_and_replay(self):
        self.start_consumer()
        online = {"id": str(uuid4()), "Camera_id": 1, "Time": "2026-11-25T10:02:00Z", "Viable": True, "Sender": 10}
        late = online | {"id": str(uuid4()), "Time": "2026-11-25T10:01:00Z", "Viable": False}
        offline = online | {"id": str(uuid4()), "Viable": False, "Sender": 20}
        for body in (online, late, late, offline):
            self.publish(self.status, f"{body['Sender']}:1", body)

        first = self.detection()
        second = first | {"id": str(uuid4()), "Sender": 20, "zone_id": 102, "is_alert": False}
        self.publish(self.detections, "10:1", first)
        self.publish(self.detections, "10:1", first)
        self.publish(self.detections, "20:1", second)
        self.publish(self.detections, "20:1", second | {"id": str(uuid4()), "zone_id": 101})
        self.publish(self.status, "20:1", online)
        self.publish(self.detections, "10:1", first | {"file": "other.jpg"})
        self.publish(self.detections, "10:1", first | {"is_alert": False})
        self.await_commits()

        # Имитируем повторное чтение тех же offset после уже совершённой записи в PostgreSQL.
        self.stop_consumer()
        rewind = ConsumerGroupTopicPartitions(self.group, [TopicPartition(t, 0, 0) for t in self.topics])
        self.admin.alter_consumer_group_offsets([rewind])[self.group].result(timeout=15)
        self.start_consumer()
        self.await_commits()
        with Session(self.engine) as session:
            for event, expected in [(online, "online"), (offline, "offline")]:
                cam = session.get(Camera, (event["Sender"], 1))
                self.assertEqual((cam.status, cam.status_at), (expected, datetime.fromisoformat(event["Time"])))
            audit = session.scalars(select(AuditLog).where(AuditLog.action == "camera.status")).all()
            self.assertEqual({r.event_uuid for r in audit}, {UUID(e["id"]) for e in [online, late, offline]})
            counts = dict(session.execute(select(AuditLog.action, func.count()).group_by(AuditLog.action)).all())
            self.assertEqual(counts, {"camera.status": 3, "camera.detection": 2, "kafka.rejected": 4})
            rows = session.scalars(select(Detection).order_by(Detection.substation_id)).all()
            self.assertEqual(len(rows), 2)
            for row, body in zip(rows, [first, second], strict=True):
                self.assertEqual((row.substation_id, row.camera_id, row.roi_id), (body["Sender"], 1, body["zone_id"]))
                self.assertEqual((row.event_uuid, row.detected_at), (UUID(body["id"]), datetime.fromisoformat(body["detected_time"])))
                self.assertEqual((row.file, row.person_count), (body["file"], 2))
                self.assertAlmostEqual(row.confidence, body["confidence"])
            alert = session.scalars(select(Alert)).one()
            self.assertEqual((alert.detection_id, alert.substation_id, alert.node_id, alert.status),
                             (rows[0].id, 10, 110, "new"))
            self.assertIsNotNone(alert.created_at)
            for details in session.scalars(select(AuditLog.details)):
                self.assertNotIn("is_alert", details)

    def test_failed_database_commit_is_retried_at_same_offset(self):
        with self.engine.begin() as db:
            db.execute(text("""
                CREATE FUNCTION fail_test_commit() RETURNS trigger LANGUAGE plpgsql AS
                $$ BEGIN RAISE EXCEPTION 'deliberate test commit failure'; END $$
            """))
            db.execute(text("""
                CREATE CONSTRAINT TRIGGER fail_commit AFTER INSERT ON alerts
                DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION fail_test_commit()
            """))
        self.publish(self.detections, "10:1", self.detection() | {"zone_id": None})
        self.start_consumer()
        self.assertNotEqual(self.worker.wait(timeout=45), 0)
        self.output.seek(0)
        self.assertIn("deliberate test commit failure", self.output.read())
        position, = self.observer.committed([TopicPartition(self.detections, 0)], timeout=10)
        self.assertLessEqual(position.offset, 0)
        with self.engine.begin() as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Detection)), 0)
            self.assertEqual(db.scalar(select(func.count()).select_from(AuditLog)), 0)
            self.assertEqual(db.scalar(select(func.count()).select_from(Alert)), 0)
            db.execute(text("DROP TRIGGER fail_commit ON alerts"))
        self.start_consumer()
        self.await_commits()
        with Session(self.engine) as session:
            self.assertIsNone(session.scalars(select(Detection)).one().roi_id)
            self.assertEqual(session.scalar(select(func.count()).select_from(AuditLog)), 1)

    def test_decisions_at_detection_time_and_retries_after_request_changes(self):
        self.start_consumer()
        first = self.detection() | {"detected_time": "2001-01-02T12:00:00+03:00"}
        at = datetime.fromisoformat(first["detected_time"])
        hour = timedelta(hours=1)
        def request(number, start, end, **changes):
            values = dict(id=number, substation_id=10, created_by=1, type_id=1, status="active",
                          responsible="бригада", people_count=1, valid_from=start, valid_to=end)
            return AccessRequest(**(values | changes))

        with Session(self.engine) as session, session.begin():
            session.add(User(id=1, login="operator", full_name="test", password_hash="test", role="dispatcher"))
            session.add(RequestType(id=1, name="обход"))
            session.flush()
            session.add_all([
                request(1, at-hour, at+hour, substation_id=20),
                request(2, at-2*hour, at-hour),
                request(3, at-hour, at+hour, deleted_at=at),
                request(4, at-hour, at+hour, status="pending"),
                request(5, at+hour, at+2*hour),
            ])
        self.publish(self.detections, "10:1", first)
        self.await_commits()

        with Session(self.engine) as session, session.begin():
            self.assertIsNone(session.scalars(select(Detection)).one().matched_request_id)
            self.assertEqual(session.scalar(select(func.count()).select_from(Alert)), 1)
            session.add_all([request(6, at-hour, at+hour), request(8, at, at+hour), request(7, at, at+hour)])
        self.publish(self.detections, "10:1", first)
        matched = first | {"id": str(uuid4())}
        plain = first | {"id": str(uuid4()), "is_alert": False}
        self.publish(self.detections, "10:1", matched)
        self.publish(self.detections, "10:1", plain)
        end = first | {"id": str(uuid4()), "detected_time": (at+hour).isoformat()}
        # Заявка №5 начинается в конце проверяемого интервала. Исключим её,
        # чтобы проверить включительность valid_to у №7.
        with Session(self.engine) as session, session.begin():
            session.get(AccessRequest, 5).status = "closed"
        self.publish(self.detections, "10:1", end)
        self.await_commits()
        with Session(self.engine) as session, session.begin():
            for number in (6, 7, 8):
                session.get(AccessRequest, number).status = "closed"
        self.publish(self.detections, "10:1", matched)
        self.await_commits()
        with Session(self.engine) as session:
            results = dict(session.execute(select(Detection.event_uuid, Detection.matched_request_id)).all())
            self.assertEqual(results, {UUID(first["id"]): None, UUID(plain["id"]): None,
                                       UUID(matched["id"]): 7, UUID(end["id"]): 7})
            self.assertEqual(session.scalars(select(Alert)).one().detection.event_uuid, UUID(first["id"]))

    def test_historical_audit_and_unassigned_camera(self):
        body = self.detection()
        parsed = decode_event(b"10:1", json.dumps(body).encode(), status=False)
        legacy = asdict(parsed)
        del legacy["event_uuid"]
        legacy["occurred_at"] = parsed.occurred_at.isoformat()
        with Session(self.engine) as session, session.begin():
            session.add(AuditLog(event_uuid=parsed.event_uuid, action="camera.detection", details=legacy))
            session.add(Detection(event_uuid=parsed.event_uuid, substation_id=10, camera_id=1,
                                  detected_at=parsed.occurred_at, person_count=2, confidence=0.97, file=body["file"],
                                  roi_id=101))
            session.get(Camera, (10, 1)).node_id = None
        self.start_consumer()
        self.publish(self.detections, "10:1", body)
        self.publish(self.detections, "10:1", body | {"id": str(uuid4())})
        self.await_commits()
        with Session(self.engine) as session:
            self.assertEqual(session.scalars(select(Detection)).one().event_uuid, parsed.event_uuid)
            self.assertEqual(session.scalar(select(func.count()).select_from(Alert)), 0)
            rejected = session.scalars(select(AuditLog).where(AuditLog.action == "kafka.rejected")).one()
            self.assertIn("не назначена узлу", rejected.details["reason"])

    def test_heartbeat(self):
        with Session(self.engine) as session, session.begin():
            session.add(EdgeNode(id=7, substation_id=10, name="второй", api_key_hash="test"))
        self.start_consumer()
        # Предлагаемый формат heartbeat: ключ "7", JSON содержит только node_id и Time.
        sent = {"node_id": 7, "Time": "2026-11-25T12:00:00+03:00"}
        self.publish(self.heartbeat, "7", sent)
        self.publish(self.heartbeat, "110", sent | {"node_id": 110})
        self.await_commits()
        with Session(self.engine) as session, session.begin():
            for node_id in (7, 110):
                node = session.get(EdgeNode, node_id)
                self.assertEqual((node.status, node.last_heartbeat_at), ("online", datetime.fromisoformat(sent["Time"])))
            session.get(EdgeNode, 7).status = "offline"
        for item in [sent, sent | {"Time":"2026-11-25T11:59:59+03:00"}]:
            self.publish(self.heartbeat, "7", item)
        for key, item in [("7", sent | {"node_id":110}), ("77", sent | {"node_id":77}),
                          ("7", sent | {"node_id":"7"}), ("7", sent | {"Time":"2026-11-25T13:00:00"})]:
            self.publish(self.heartbeat, key, item)
        self.await_commits()
        with Session(self.engine) as session:
            node = session.get(EdgeNode, 7)
            self.assertEqual((node.status, node.last_heartbeat_at), ("offline", datetime.fromisoformat(sent["Time"])))
        newer = "2026-11-25T12:01:00+03:00"
        self.publish(self.heartbeat, "7", sent | {"Time":newer})
        self.await_commits()
        self.stop_consumer()
        self.output.seek(0)
        reasons = self.output.read()
        for reason in ("Неизвестный node_id", "Ключ Kafka не соответствует node_id", "целое число", "ISO 8601"):
            self.assertIn(reason, reasons)
        with Session(self.engine) as session:
            node = session.get(EdgeNode, 7)
            self.assertEqual((node.status, node.last_heartbeat_at), ("online", datetime.fromisoformat(newer)))
            self.assertEqual(session.get(EdgeNode, 110).last_heartbeat_at, datetime.fromisoformat(sent["Time"]))
            self.assertIsNone(session.get(Camera, (10, 1)).status_at)
            for model in (Alert, Detection, AuditLog):
                self.assertEqual(session.scalar(select(func.count()).select_from(model)), 0)

    def test_concurrent_heartbeats_keep_max_time(self):
        barrier = Barrier(2)
        def write(instant):
            with Session(self.engine) as session, session.begin():
                session.execute(text("SELECT 1"))
                barrier.wait(timeout=10)
                record_heartbeat(session, 110, instant)
        times = [datetime.fromisoformat(f"2026-11-25T10:00:0{i}Z") for i in (2, 1)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(write, times))
        with Session(self.engine) as session:
            node = session.get(EdgeNode, 110)
            self.assertEqual((node.status, node.last_heartbeat_at), ("online", max(times)))
