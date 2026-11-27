"""Передаёт в WebSocket уведомления Redis о завершённых транзакциях."""

from time import monotonic

from flask import current_app
from flask_sock import Sock
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from ..auth.permissions import current_operator
from ..db import get_session
from . import ALERT_CHANNEL


def init_alert_socket(app):
    app.config["SOCK_SERVER_OPTIONS"] = {"ping_interval": 20, "max_message_size": 1024}
    sock = Sock(app)

    @sock.route("/ws/alerts")
    def alert_stream(ws):
        # Не удерживаем соединение с PostgreSQL на время открытого WebSocket.
        get_session().close()
        next_check = monotonic() + 15
        next_sync = monotonic() + 60
        try:
            with current_app.extensions["redis"].pubsub() as subscription:
                subscription.subscribe(ALERT_CHANNEL)
                while ws.connected:
                    event = subscription.get_message(timeout=1)
                    now = monotonic()
                    if event or now >= next_check or now >= next_sync:
                        # Проверяем исходящие данные, даже если срок фоновой проверки ещё не наступил.
                        allowed = current_operator() is not None
                        get_session().close()
                        if not allowed:
                            ws.close(reason=1008)
                            return
                        next_check = monotonic() + 15
                    if event and event["type"] == "subscribe":
                        ws.send('{"type":"ready"}')
                    elif event and event["type"] == "message":
                        ws.send(event["data"])
                    if now >= next_sync:
                        ws.send('{"type":"sync"}')
                        next_sync = monotonic() + 60
        except (RedisError, SQLAlchemyError):
            ws.close(reason=1013)
