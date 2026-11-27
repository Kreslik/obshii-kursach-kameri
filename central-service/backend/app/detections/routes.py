"""Детекции и фактически сохранённые связи с заявками и тревогами."""

from flask import Blueprint
from sqlalchemy import String, cast, select

from ..alerts.models import Alert
from ..catalog.models import Camera, RoiZone, Substation
from ..pagination import event_page
from .models import Detection

bp = Blueprint("detections", __name__, url_prefix="/api/v1/detections")


@bp.get("")
def list_detections():
    query = (
        select(
            cast(Detection.id, String).label("id"), Detection.event_uuid, Detection.detected_at,
            Detection.substation_id, Substation.name.label("substation_name"),
            Detection.camera_id, Camera.name.label("camera_name"),
            Detection.roi_id, RoiZone.name.label("roi_name"),
            Detection.matched_request_id, cast(Alert.id, String).label("alert_id"),
        )
        .select_from(Detection)
        .join(Detection.camera)
        .join(Camera.substation)
        .outerjoin(Detection.roi)
        .outerjoin(Alert, Alert.detection_id == Detection.id)
        .order_by(Detection.detected_at.desc(), Detection.id.desc())
    )
    return event_page(query, Detection.substation_id)
