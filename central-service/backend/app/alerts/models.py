"""Тревоги центрального сервиса и решения диспетчеров."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base

if TYPE_CHECKING:
    from ..access_requests.models import AccessRequest
    from ..catalog.models import EdgeNode, Substation
    from ..detections.models import Detection
    from ..users.models import User


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint("detection_id", name="uq_alerts_detection_id"),
        Index("ix_alerts_station_status_created", "substation_id", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    detection_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("detections.id"))
    substation_id: Mapped[int] = mapped_column(ForeignKey("substations.id"))
    node_id: Mapped[int] = mapped_column(ForeignKey("edge_nodes.id"))
    request_id: Mapped[int | None] = mapped_column(ForeignKey("access_requests.id"))
    processed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(
        Enum("new", "confirmed", "false_positive", "linked", name="alert_status"),
        server_default="new",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    detection: Mapped[Detection] = relationship()
    substation: Mapped[Substation] = relationship()
    node: Mapped[EdgeNode] = relationship()
    linked_request: Mapped[AccessRequest | None] = relationship()
    processor: Mapped[User | None] = relationship()
