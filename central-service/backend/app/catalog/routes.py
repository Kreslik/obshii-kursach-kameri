"""Управление подстанциями, узлами, камерами, зонами ROI и типами заявок."""

from flask import Blueprint
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..db import get_session
from .models import Camera, EdgeNode, Substation

bp = Blueprint("catalog", __name__, url_prefix="/api/v1/catalog")


@bp.get("/equipment")
def equipment():
    query = select(Substation).order_by(Substation.id).options(
        selectinload(Substation.edge_nodes).load_only(
            EdgeNode.id, EdgeNode.name, EdgeNode.status, EdgeNode.last_heartbeat_at
        ),
        selectinload(Substation.cameras).load_only(
            Camera.camera_id, Camera.node_id, Camera.name, Camera.status
        ),
    )
    items = []
    for station in get_session().scalars(query):
        nodes = [
            {
                "id": node.id, "name": node.name, "status": node.status,
                "last_heartbeat_at": node.last_heartbeat_at.isoformat() if node.last_heartbeat_at else None,
            }
            for node in sorted(station.edge_nodes, key=lambda node: node.id)
        ]
        cameras = [
            {"camera_id": cam.camera_id, "name": cam.name, "status": cam.status, "node_id": cam.node_id}
            for cam in sorted(station.cameras, key=lambda cam: cam.camera_id)
        ]
        items.append({"id": station.id, "name": station.name, "nodes": nodes, "cameras": cameras})
    return {"items": items}
