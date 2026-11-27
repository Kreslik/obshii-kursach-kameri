"""Учётные записи пользователей центра."""

from datetime import datetime

from sqlalchemy import DateTime, Enum, false, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[str] = mapped_column(unique=True)
    password_hash: Mapped[str]
    full_name: Mapped[str]
    role: Mapped[str] = mapped_column(
        Enum("dispatcher", "admin", "auditor", name="user_role")
    )
    is_blocked: Mapped[bool] = mapped_column(server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
