"""Заявки на доступ к объектам наблюдения."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, SmallInteger, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base

if TYPE_CHECKING:
    from ..catalog.models import RequestType, Substation
    from ..users.models import User


class AccessRequest(Base):
    __tablename__ = "access_requests"
    __table_args__ = (
        CheckConstraint("valid_to > valid_from", name="ck_access_requests_period"),
        CheckConstraint("people_count > 0", name="ck_access_requests_people_count"),
        Index("ix_access_requests_station_status_from", "substation_id", "status", "valid_from"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    substation_id: Mapped[int] = mapped_column(ForeignKey("substations.id"))
    type_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("request_types.id"))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    responsible: Mapped[str]
    people_count: Mapped[int] = mapped_column(SmallInteger)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        Enum("pending", "active", "closed", "rejected", name="request_status"),
        server_default="pending",
    )
    admin_comment: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    substation: Mapped[Substation] = relationship()
    request_type: Mapped[RequestType] = relationship()
    creator: Mapped[User] = relationship()
