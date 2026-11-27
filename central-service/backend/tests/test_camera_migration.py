"""Проверка заполненной БД: сквозные номера камер отличаются от номеров на узле."""

import os
import unittest
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from db_fixture import isolated_schema


@unittest.skipUnless(os.getenv("TEST_POSTGRES") == "1", "Требуется PostgreSQL")
class CameraMigrationTest(unittest.TestCase):
    def test_existing_camera_references(self):
        engine = self.enterContext(isolated_schema())
        config = Config("alembic.ini")
        command.upgrade(config, "0004_camera_station_key")
        uuids = [uuid4(), uuid4()]
        with engine.begin() as db:
            for station, old_id, zone_id, event_id in [(10, 101, 5, uuids[0]), (20, 202, 6, uuids[1])]:
                args = {"station": station, "old": old_id, "zone": zone_id, "uuid": event_id, "name": str(station)}
                db.execute(text("INSERT INTO substations(id, code, name) VALUES (:station, :name, :name)"), args)
                db.execute(text("""
                    INSERT INTO cameras(id, substation_id, local_camera_id, name, rtsp_url)
                    VALUES (:old, :station, 1, :name, 'rtsp://example/camera')
                """), args)
                db.execute(text("""
                    INSERT INTO roi_zones(id, camera_id, name, polygon) VALUES (:zone, :old, :name, '[]')
                """), args)
                db.execute(text("""
                    INSERT INTO detections(event_uuid, camera_id, roi_id, detected_at, person_count, confidence, frame_key)
                    VALUES (:uuid, :old, :zone, '2026-11-25 12:00:00+00', 1, 0.9, 'old/frame.jpg')
                """), args)

        command.upgrade(config, "head")
        command.check(config)
        inspector = inspect(engine)
        self.assertNotIn("is_alert", {col["name"] for col in inspector.get_columns("detections")})
        self.assertEqual(inspector.get_pk_constraint("cameras")["constrained_columns"], ["substation_id", "camera_id"])
        self.assertTrue({"id", "local_camera_id"}.isdisjoint(c["name"] for c in inspector.get_columns("cameras")))
        for table in ["detections", "roi_zones"]:
            fk, = [fk for fk in inspector.get_foreign_keys(table) if fk["referred_table"] == "cameras"]
            self.assertEqual(fk["constrained_columns"], ["substation_id", "camera_id"])
            self.assertEqual(fk["referred_columns"], ["substation_id", "camera_id"])
        with engine.connect() as db:
            rows = db.execute(text("""
                SELECT d.event_uuid, d.substation_id, d.camera_id, z.substation_id, z.camera_id,
                       z.id, d.file, c.name
                  FROM detections d JOIN roi_zones z ON z.id = d.roi_id
                  JOIN cameras c ON (c.substation_id, c.camera_id) = (d.substation_id, d.camera_id)
                 ORDER BY d.substation_id
            """)).all()
            self.assertEqual(rows, [
                (uuids[0], 10, 1, 10, 1, 5, "old/frame.jpg", "10"),
                (uuids[1], 20, 1, 20, 1, 6, "old/frame.jpg", "20"),
            ])
        with self.assertRaises(IntegrityError), engine.begin() as db:
            db.execute(text("UPDATE roi_zones SET substation_id = 30 WHERE id = 5"))

        command.downgrade(config, "0004_camera_station_key")
        with engine.connect() as db:
            rows = db.execute(text("""
                SELECT c.substation_id, c.local_camera_id, d.event_uuid, z.id
                  FROM cameras c JOIN detections d ON d.camera_id = c.id
                  JOIN roi_zones z ON z.id = d.roi_id AND z.camera_id = c.id
                 ORDER BY c.substation_id
            """)).all()
            self.assertEqual(rows, [(10, 1, uuids[0], 5), (20, 1, uuids[1], 6)])
