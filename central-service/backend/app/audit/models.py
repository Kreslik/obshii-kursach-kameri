"""Журнал действий пользователей и системных событий."""

from __future__ import annotations

from datetime import datetime
from ipaddress import IPv4Address, IPv6Address
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base

if TYPE_CHECKING:
    from ..catalog.models import EdgeNode
    from ..users.models import User


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_uuid: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), unique=True, default=uuid4)
    node_id: Mapped[int | None] = mapped_column(ForeignKey("edge_nodes.id"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    ip_address: Mapped[IPv4Address | IPv6Address | None] = mapped_column(INET)
    action: Mapped[str]
    entity_type: Mapped[str | None]
    entity_id: Mapped[int | None] = mapped_column(BigInteger)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    node: Mapped[EdgeNode | None] = relationship()
    user: Mapped[User | None] = relationship()
