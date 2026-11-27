"""Сессия диспетчера. В Redis хранится только отпечаток случайного ключа."""

from hashlib import sha256

from flask import current_app, g, request
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import select

from ..db import get_session
from ..users.models import User


COOKIE = "__Host-center_session"
LIFETIME = 8 * 60 * 60
ROLES = ("dispatcher", "admin")


def session_key(token):
    return "central:session:" + sha256(token.encode()).hexdigest()


def current_operator():
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    user_id = current_app.extensions["redis"].get(session_key(token))
    if user_id is None:
        return None
    return get_session().scalar(select(User).where(
        User.id == int(user_id), User.is_blocked.is_(False), User.role.in_(ROLES),
    ))


def init_permissions(app):
    app.extensions["redis"] = Redis.from_url(
        app.config.get("REDIS_URL", "redis://localhost:6379/0"),
        decode_responses=True, socket_connect_timeout=3, socket_timeout=5,
    )

    @app.before_request
    def protect_dispatcher():
        if request.path == "/ws/alerts":
            if request.headers.get("Origin") != "https://" + request.host:
                return {"error": "Недопустимый источник подключения"}, 403
        elif request.blueprint not in ("access_requests", "alerts", "catalog", "detections") and request.endpoint != "auth.session_info":
            return None
        g.operator = current_operator()
        if g.operator is None:
            return {"error": "Требуется вход"}, 401

    @app.after_request
    def no_cached_data(response):
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(RedisError)
    def redis_unavailable(error):
        return {"error": "Сервис временно недоступен"}, 503
