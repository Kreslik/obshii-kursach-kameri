"""Отдельный процесс: Kafka → транзакция PostgreSQL → подтверждение offset."""

import logging
import json
import os
import signal
from threading import Event

from confluent_kafka import Consumer, KafkaError, KafkaException
from confluent_kafka.admin import AdminClient, NewTopic
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from redis import Redis
from redis.exceptions import RedisError

from ..db import get_database_url, load_models
from ..monitoring.heartbeat import record_heartbeat
from ..realtime import ALERT_CHANNEL
from .events import record_rejection, store_event
from .schemas import InvalidEvent, decode_event, decode_heartbeat


log = logging.getLogger(__name__)


def ensure_topics(bootstrap: str, topics: list[str]) -> None:
    if not all(topics) or len(set(topics)) != len(topics):
        raise ValueError("Имена топиков Kafka должны быть непустыми и разными")
    admin = AdminClient({"bootstrap.servers": bootstrap})
    pending = admin.create_topics(
        [NewTopic(name, num_partitions=1, replication_factor=1) for name in topics], request_timeout=30,
    )
    for future in pending.values():
        try:
            future.result()
        except KafkaException as exc:
            if exc.args[0].code() != KafkaError.TOPIC_ALREADY_EXISTS:
                raise


def run(stopping: Event) -> None:
    bootstrap = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
    status = os.environ.get("KAFKA_STATUS_TOPIC", "camera.status")
    detections = os.environ.get("KAFKA_DETECTIONS_TOPIC", "camera.detections")
    group = os.environ.get("KAFKA_GROUP_ID", "central-camera-events")
    heartbeat = os.environ.get("KAFKA_HEARTBEAT_TOPIC", "node.heartbeat")
    topics = [status, detections, heartbeat]
    ensure_topics(bootstrap, topics)
    load_models()
    engine = create_engine(get_database_url(), pool_pre_ping=True, hide_parameters=True)
    sessions = sessionmaker(engine)
    cache = Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
                           socket_connect_timeout=2, socket_timeout=2)
    consumer = Consumer({
        "bootstrap.servers": bootstrap, "group.id": group,
        "auto.offset.reset": "earliest", "enable.auto.commit": False, "enable.auto.offset.store": False,
    })
    try:
        consumer.subscribe(topics)
        log.info("Группа %s читает %s", group, ", ".join(topics))
        while not stopping.is_set():
            message = consumer.poll(1)
            if message is None:
                continue
            if message.error():
                raise KafkaException(message.error())
            notification = None
            try:
                with sessions.begin() as session:
                    if message.topic() == heartbeat:
                        try:
                            station = record_heartbeat(session, *decode_heartbeat(message.key(), message.value()))
                            if station is not None:
                                notification = {"type": "update", "substation_id": station}
                        except InvalidEvent as exc:
                            log.warning("Отклонено %s[%s]@%s: %s", heartbeat, message.partition(), message.offset(), exc)
                    else:
                        event = decode_event(message.key(), message.value(), status=message.topic() == status)
                        notification = store_event(session, event)
            except InvalidEvent as exc:
                with sessions.begin() as session:
                    record_rejection(session, message.topic(), message.partition(), message.offset(), str(exc))
                log.warning("Отклонено %s[%s]@%s: %s", message.topic(), message.partition(), message.offset(), exc)
            # Обе ветви дошли сюда только после успешного COMMIT в PostgreSQL.
            if notification is not None:
                try:
                    cache.publish(ALERT_CHANNEL, json.dumps(notification))
                except RedisError:
                    # Клиент также сверяет снимок по таймеру и после переподключения.
                    log.warning("Не удалось отправить уведомление панели через Redis", exc_info=True)
            for partition in consumer.commit(message=message, asynchronous=False):
                if partition.error:
                    raise KafkaException(partition.error)
    finally:
        consumer.close()
        cache.close()
        engine.dispose()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    stopping = Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stopping.set())
    run(stopping)


if __name__ == "__main__":
    main()
