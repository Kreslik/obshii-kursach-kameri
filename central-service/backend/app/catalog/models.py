"""Справочники подстанций, оборудования, зон наблюдения и видов работ."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, ForeignKeyConstraint, SmallInteger, UniqueConstraint, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class Substation(Base):
    __tablename__ = "substations"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    address: Mapped[str | None]
    is_active: Mapped[bool] = mapped_column(server_default=true())

    cameras: Mapped[list[Camera]] = relationship(back_populates="substation")
    edge_nodes: Mapped[list[EdgeNode]] = relationship(back_populates="substation")


class EdgeNode(Base):
    __tablename__ = "edge_nodes"
    __table_args__ = (
        UniqueConstraint("substation_id", "name", name="uq_edge_nodes_station_name"),
        UniqueConstraint("id", "substation_id", name="uq_edge_nodes_id_station"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    substation_id: Mapped[int] = mapped_column(ForeignKey("substations.id"))
    name: Mapped[str]
    api_key_hash: Mapped[str]
    status: Mapped[str] = mapped_column(
        Enum("online", "offline", name="node_status"), server_default="offline"
    )
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    model_version: Mapped[str | None]
    software_version: Mapped[str | None]
    is_active: Mapped[bool] = mapped_column(server_default=true())

    substation: Mapped[Substation] = relationship(back_populates="edge_nodes")


class Camera(Base):
    __tablename__ = "cameras"
    __table_args__ = (
        CheckConstraint("camera_id > 0", name="ck_cameras_local_id_positive"),
        ForeignKeyConstraint(
            ["node_id", "substation_id"],
            ["edge_nodes.id", "edge_nodes.substation_id"],
            name="fk_cameras_node_station",
        ),
    )

    substation_id: Mapped[int] = mapped_column(ForeignKey("substations.id"), primary_key=True)
    camera_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    node_id: Mapped[int | None] = mapped_column()
    name: Mapped[str]
    rtsp_url: Mapped[str]
    is_active: Mapped[bool] = mapped_column(server_default=true())
    status: Mapped[str] = mapped_column(
        Enum("online", "offline", name="camera_status"), server_default="offline"
    )
    last_frame_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    substation: Mapped[Substation] = relationship(back_populates="cameras")
    # При назначении узла ORM меняет только node_id. Подстанцию проверяет составной FK.
    node: Mapped[EdgeNode | None] = relationship(foreign_keys=[node_id])
    roi_zones: Mapped[list[RoiZone]] = relationship(back_populates="camera")


class RoiZone(Base):
    __tablename__ = "roi_zones"
    __table_args__ = (
        ForeignKeyConstraint(
            ["substation_id", "camera_id"], ["cameras.substation_id", "cameras.camera_id"], name="fk_roi_zones_camera",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    substation_id: Mapped[int]
    camera_id: Mapped[int]
    name: Mapped[str]
    polygon: Mapped[list] = mapped_column(JSONB)

    camera: Mapped[Camera] = relationship(back_populates="roi_zones")


class RequestType(Base):
    __tablename__ = "request_types"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
