"""Монотонное обновление времени связи конкретного узла."""

from datetime import datetime

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from ..catalog.models import EdgeNode
from ..node_events.schemas import InvalidEvent


def record_heartbeat(session: Session, node_id: int, sent_at: datetime) -> int | None:
    updated = session.scalar(
        update(EdgeNode)
        .where(EdgeNode.id == node_id,
               or_(EdgeNode.last_heartbeat_at.is_(None), EdgeNode.last_heartbeat_at < sent_at))
        .values(last_heartbeat_at=sent_at, status="online")
        .returning(EdgeNode.substation_id)
    )
    if updated is None and session.scalar(select(EdgeNode.id).where(EdgeNode.id == node_id)) is None:
        raise InvalidEvent(f"Неизвестный node_id: {node_id}")
    return updated
