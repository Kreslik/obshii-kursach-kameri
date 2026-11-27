"""Список действующих и архивных заявок для диспетчера."""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from flask import Blueprint, request
from sqlalchemy import or_, select

from ..catalog.models import Substation
from ..pagination import event_page
from .models import AccessRequest

bp = Blueprint("access_requests", __name__, url_prefix="/api/v1/requests")
MOSCOW = ZoneInfo("Europe/Moscow")


def date_filter(name):
    raw = request.args.get(name)
    if raw is None:
        return None
    try:
        day = date.fromisoformat(raw)
        if day.isoformat() != raw:
            raise ValueError
    except ValueError:
        raise ValueError(f"{name}: ожидается дата ГГГГ-ММ-ДД") from None
    return day


@bp.get("")
def list_requests():
    query = (
        select(
            AccessRequest.id, AccessRequest.substation_id, Substation.name.label("substation_name"),
            AccessRequest.responsible, AccessRequest.valid_from, AccessRequest.valid_to, AccessRequest.status,
        )
        .join(AccessRequest.substation)
        .where(AccessRequest.deleted_at.is_(None))
        .order_by(AccessRequest.valid_from.desc(), AccessRequest.id.desc())
    )
    status = request.args.get("status")
    if status is not None:
        if status not in ("pending", "active", "closed", "rejected"):
            return {"error": "Неизвестный статус заявки"}, 400
        query = query.where(AccessRequest.status == status)

    try:
        start = date_filter("date_from")
        end = date_filter("date_to")
    except ValueError as error:
        return {"error": str(error)}, 400
    if start and end and start > end:
        return {"error": "Дата окончания фильтра раньше даты начала"}, 400
    if start:
        query = query.where(AccessRequest.valid_to >= datetime.combine(start, time.min, MOSCOW))
    if end:
        query = query.where(AccessRequest.valid_from <= datetime.combine(end, time.max, MOSCOW))

    search = request.args.get("q", "").strip()
    if search:
        if "\x00" in search:
            return {"error": "Некорректный текст поиска"}, 400
        matches = [
            AccessRequest.responsible.icontains(search, autoescape=True),
            Substation.name.icontains(search, autoescape=True),
        ]
        if search.isascii() and search.isdecimal() and len(search) <= 10:
            request_id = int(search)
            if request_id <= 2_147_483_647:
                matches.append(AccessRequest.id == request_id)
        query = query.where(or_(*matches))
    return event_page(query, AccessRequest.substation_id)
