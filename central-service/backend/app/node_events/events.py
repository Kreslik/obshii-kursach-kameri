"""Запись события и результата его обработки в одной транзакции PostgreSQL."""

from dataclasses import asdict
from hashlib import sha256
import json
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..audit.models import AuditLog
from ..alerts.service import decide_alert
from ..catalog.models import Camera, RoiZone
from ..detections.models import Detection
from .schemas import CameraDetection, CameraStatus, InvalidEvent


def store_event(session: Session, event: CameraStatus | CameraDetection) -> dict | None:
    status = isinstance(event, CameraStatus)
    action = "camera.status" if status else "camera.detection"
    details = asdict(event)
    del details["event_uuid"]
    details["occurred_at"] = event.occurred_at.isoformat()
    original = details.copy()
    if isinstance(event, CameraDetection):
        # Сверяем полное сообщение при повторе, сохраняя в журнале только
        # отпечаток и видимые поля детекции без входного флага.
        digest = sha256(json.dumps(details, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        del details["is_alert"]
        details["payload_sha256"] = digest
    # Один UUID занимает одну строку журнала даже при параллельной повторной доставке.
    audit_id = session.scalar(
        insert(AuditLog)
        .values(event_uuid=event.event_uuid, action=action, entity_type="camera", details=details)
        .on_conflict_do_nothing(index_elements=[AuditLog.event_uuid])
        .returning(AuditLog.id)
    )
    if audit_id is None:
        existing = session.execute(
            select(AuditLog.action, AuditLog.details).where(AuditLog.event_uuid == event.event_uuid)
        ).one()
        if existing.action != action or existing.details not in (details, original):
            raise InvalidEvent("UUID уже зарегистрирован с другими данными")
        return

    camera = session.get(
        Camera, (event.substation_id, event.camera_id), with_for_update={"read": not status},
    )
    if camera is None:
        raise InvalidEvent(f"Неизвестная камера {event.substation_id}:{event.camera_id}")
    if isinstance(event, CameraStatus):
        if camera.status_at is None or event.occurred_at > camera.status_at:
            camera.status = "online" if event.viable else "offline"
            camera.status_at = event.occurred_at
            return {"type": "update", "substation_id": event.substation_id}
        return

    if event.zone_id is not None:
        zone = session.scalar(
            select(RoiZone.id).where(
                RoiZone.id == event.zone_id, RoiZone.substation_id == event.substation_id,
                RoiZone.camera_id == event.camera_id,
            ).with_for_update(read=True)
        )
        if zone is None:
            raise InvalidEvent("Зона не принадлежит указанной камере")
    detection = session.scalar(
        insert(Detection).values(
            event_uuid=event.event_uuid, substation_id=event.substation_id, camera_id=event.camera_id,
            roi_id=event.zone_id, detected_at=event.occurred_at, person_count=event.person_count,
            confidence=event.confidence, file=event.file,
        ).on_conflict_do_nothing(index_elements=[Detection.event_uuid]).returning(Detection)
    )
    if detection is None:
        raise InvalidEvent("UUID уже занят детекцией, принятой до перехода на Kafka")
    alert = decide_alert(session, detection, event.is_alert, camera.node_id)
    if alert is not None:
        return {"type": "alert", "id": str(alert.id), "substation_id": event.substation_id}
    return {"type": "update", "substation_id": event.substation_id}


def record_rejection(session: Session, topic: str, partition: int, offset: int, reason: str) -> None:
    # Координаты записи стабильны при повторном чтении после сбоя подтверждения Kafka.
    rejection_id = uuid5(NAMESPACE_URL, f"kafka:central/rejected/{topic}/{partition}/{offset}")
    session.execute(insert(AuditLog).values(
        event_uuid=rejection_id, action="kafka.rejected",
        details={"topic": topic, "partition": partition, "offset": offset, "reason": reason},
    ).on_conflict_do_nothing(index_elements=[AuditLog.event_uuid]))
