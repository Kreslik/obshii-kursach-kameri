"""Параметры отчётов, просмотр агрегатов и запрос выгрузки."""

from flask import Blueprint

bp = Blueprint("reports", __name__, url_prefix="/api/v1/reports")
