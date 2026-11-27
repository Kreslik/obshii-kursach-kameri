"""Публикация контрольных событий для панели на локальном Compose-стенде."""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from confluent_kafka import Producer
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.access_requests.models import AccessRequest
from app.catalog.models import Camera, EdgeNode, RequestType, Substation
from app.db import get_database_url, load_models
from app.users.models import User


def prepare(session, login, at):
    run = uuid4().hex[:8]
    with session.begin():
        author = session.scalars(select(User).where(User.login == login)).one()
        stations = []
        for name in ("Северная", "Южная"):
            station = Substation(code=f"{name}-{run}", name=f"{name} · {run}")
            session.add(station)
            session.flush()
            node = EdgeNode(substation_id=station.id, name=f"Узел · {name}", api_key_hash="disabled")
            session.add(node)
            session.flush()
            session.add(Camera(substation_id=station.id, camera_id=1, node_id=node.id,
                               name=f"Въезд · {name}", rtsp_url="rtsp://camera.invalid/demo"))
            stations.append((station.id, node.id))
        kind = session.scalar(select(RequestType).where(RequestType.name == "Контрольный обход"))
        if kind is None:
            kind = RequestType(name="Контрольный обход")
            session.add(kind)
            session.flush()
        request = AccessRequest(substation_id=stations[0][0], created_by=author.id, type_id=kind.id,
                                responsible="Учебная бригада", people_count=1, status="active",
                                valid_from=at - timedelta(minutes=2), valid_to=at - timedelta(minutes=1))
        session.add(request)
        session.flush()
        request_id = request.id
    return run, stations, request_id


def main(login):
    at = datetime.now(timezone.utc).replace(microsecond=0)
    load_models()
    with Session(create_engine(get_database_url())) as session:
        run, ((station, node), (other, _)), request = prepare(session, login, at)
    producer = Producer({"bootstrap.servers": os.environ["KAFKA_BOOTSTRAP_SERVERS"],
                         "acks": "all", "message.timeout.ms": 15000})
    errors = []

    def delivered(error, message):
        if error:
            errors.append(str(error))

    def publish(topic, key, payload):
        producer.produce(os.environ[topic], key=key, value=json.dumps(payload), on_delivery=delivered)

    key = f"{station}:1"
    first = dict(id=str(uuid4()), camera_id=1, zone_id=None, person_count=1, confidence=0.97,
                 detected_time=(at - timedelta(seconds=90)).isoformat(), is_alert=True,
                 file="demo/entry.jpg", Sender=station)
    second = first | {"id": str(uuid4()), "detected_time": at.isoformat()}
    for event in (first, second, second):
        publish("KAFKA_DETECTIONS_TOPIC", key, event)
    publish("KAFKA_STATUS_TOPIC", key, dict(id=str(uuid4()), Camera_id=1, Time=at.isoformat(),
                                           Viable=True, Sender=station))
    publish("KAFKA_HEARTBEAT_TOPIC", str(node), dict(node_id=node, Time=at.isoformat()))
    if producer.flush(20) or errors:
        raise RuntimeError(f"Брокер не подтвердил все события: {errors}")
    print(f"Серия {run}. Северная: {station}:1, узел {node}. Южная: {other}:1.")
    print(f"Первая детекция {first['id']} → заявка №{request}.")
    print(f"Вторая детекция {second['id']} опубликована дважды → одна тревога.")
    print(f"Время последнего heartbeat: {at.isoformat()}.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Передайте логин созданного диспетчера.")
    main(sys.argv[1])
