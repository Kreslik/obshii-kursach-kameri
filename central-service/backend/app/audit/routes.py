"""Просмотр записей журнала с проверкой прав доступа."""

from flask import Blueprint

bp = Blueprint("audit", __name__, url_prefix="/api/v1/audit")
