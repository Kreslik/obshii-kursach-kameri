"""Решение по впервые принятой детекции в транзакции consumer."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..access_requests.models import AccessRequest
from ..detections.models import Detection
from ..node_events.schemas import InvalidEvent
from .models import Alert


def decide_alert(session: Session, detection: Detection, zone_crossed: bool, node_id: int | None) -> Alert | None:
    if not zone_crossed:
        return
    request_id = session.scalar(
        select(AccessRequest.id)
        .where(
            AccessRequest.substation_id == detection.substation_id,
            AccessRequest.status == "active",
            AccessRequest.deleted_at.is_(None),
            AccessRequest.valid_from <= detection.detected_at,
            AccessRequest.valid_to >= detection.detected_at,
        )
        .order_by(AccessRequest.valid_from.desc(), AccessRequest.id)
        .limit(1)
        .with_for_update(read=True)
    )
    if request_id is not None:
        detection.matched_request_id = request_id
        return
    if node_id is None:
        raise InvalidEvent(f"Камера {detection.substation_id}:{detection.camera_id} не назначена узлу для тревоги")
    alert = Alert(detection_id=detection.id, substation_id=detection.substation_id,
                  node_id=node_id, status="new")
    session.add(alert)
    session.flush()
    return alert
