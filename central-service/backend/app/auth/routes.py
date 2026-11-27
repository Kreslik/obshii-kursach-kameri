"""Вход и завершение серверной сессии диспетчера."""

import secrets
from datetime import datetime, timezone

from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy import select
from werkzeug.security import check_password_hash

from ..db import get_session
from ..users.models import User
from .permissions import COOKIE, LIFETIME, ROLES, session_key

bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")


def profile(user):
    return {"login": user.login, "name": user.full_name, "role": user.role}


@bp.post("/login")
def login():
    data = request.get_json()
    if not isinstance(data, dict) or not all(isinstance(data.get(k), str) and data[k] for k in ("login", "password")):
        return {"error": "Введите логин и пароль"}, 400
    db = get_session()
    user = db.scalar(select(User).where(User.login == data["login"]))
    if not user or not check_password_hash(user.password_hash, data["password"]) or user.is_blocked or user.role not in ROLES:
        return {"error": "Не удалось войти с этими данными"}, 401
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    token = secrets.token_urlsafe(32)
    cache = current_app.extensions["redis"]
    previous = request.cookies.get(COOKIE)
    with cache.pipeline() as transaction:
        if previous:
            transaction.delete(session_key(previous))
        transaction.setex(session_key(token), LIFETIME, user.id)
        transaction.execute()
    response = jsonify(profile(user))
    response.set_cookie(COOKIE, token, max_age=LIFETIME, secure=True, httponly=True, samesite="Strict", path="/")
    return response


@bp.get("/session")
def session_info():
    return profile(g.operator)


@bp.post("/logout")
def logout():
    request.get_json()
    token = request.cookies.get(COOKIE)
    if token:
        current_app.extensions["redis"].delete(session_key(token))
    response = jsonify({"ok": True})
    response.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="Strict")
    return response
