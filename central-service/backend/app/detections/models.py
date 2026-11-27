"""Детекции людей и результат сопоставления с заявкой в центре."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, REAL, SmallInteger, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base

if TYPE_CHECKING:
    from ..access_requests.models import AccessRequest
    from ..catalog.models import Camera, RoiZone


class Detection(Base):
    __tablename__ = "detections"
    __table_args__ = (
        ForeignKeyConstraint(
            ["substation_id", "camera_id"], ["cameras.substation_id", "cameras.camera_id"], name="fk_detections_camera",
        ),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_detections_confidence"),
        CheckConstraint("person_count > 0", name="ck_detections_person_count"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_uuid: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), unique=True)
    substation_id: Mapped[int]
    camera_id: Mapped[int]
    roi_id: Mapped[int | None] = mapped_column(ForeignKey("roi_zones.id"))
    matched_request_id: Mapped[int | None] = mapped_column(ForeignKey("access_requests.id"))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    person_count: Mapped[int] = mapped_column(SmallInteger)
    confidence: Mapped[float] = mapped_column(REAL)
    file: Mapped[str]

    camera: Mapped[Camera] = relationship()
    roi: Mapped[RoiZone | None] = relationship()
    matched_request: Mapped[AccessRequest | None] = relationship()
