"""Лента, фильтры, карточка и действия диспетчера по тревоге."""

from flask import Blueprint
from sqlalchemy import String, cast, select

from ..catalog.models import Camera, Substation
from ..detections.models import Detection
from ..pagination import event_page
from .models import Alert

bp = Blueprint("alerts", __name__, url_prefix="/api/v1/alerts")


@bp.get("")
def list_alerts():
    query = (
        select(
            cast(Alert.id, String).label("id"), Alert.status, Alert.created_at,
            cast(Alert.detection_id, String).label("detection_id"),
            Alert.substation_id, Substation.name.label("substation_name"),
            Detection.event_uuid, Detection.detected_at, Detection.camera_id,
            Camera.name.label("camera_name"),
        )
        .select_from(Alert)
        .join(Alert.substation)
        .join(Alert.detection)
        .join(Detection.camera)
        .order_by(Alert.created_at.desc(), Alert.id.desc())
    )
    return event_page(query, Alert.substation_id)
