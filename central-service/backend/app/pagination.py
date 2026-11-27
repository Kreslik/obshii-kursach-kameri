"""Постраничное чтение событий панели по выбранной подстанции."""

from datetime import datetime

from flask import request

from .db import get_session


def positive_int(name, default=None, maximum=2_147_483_647):
    value = request.args.get(name)
    if value is None:
        return default
    if not value.isascii() or not value.isdecimal() or len(value) > 10:
        raise ValueError(f"Некорректный параметр {name}")
    number = int(value)
    if not 1 <= number <= maximum:
        raise ValueError(f"{name} должен быть от 1 до {maximum}")
    return number


def event_page(query, station_column):
    try:
        station = positive_int("substation_id")
        page = positive_int("page", default=1)
        per_page = positive_int("per_page", default=20, maximum=100)
    except ValueError as error:
        return {"error": str(error)}, 400
    if station is not None:
        query = query.where(station_column == station)
    rows = get_session().execute(
        query.offset((page - 1) * per_page).limit(per_page + 1)
    ).mappings().all()
    items = [
        {key: value.isoformat() if isinstance(value, datetime) else value
         for key, value in row.items()}
        for row in rows[:per_page]
    ]
    return {"items": items, "page": page, "per_page": per_page, "has_more": len(rows) > per_page}
