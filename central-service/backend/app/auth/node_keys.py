"""Проверка API-ключа узла по хешу из edge_nodes."""

from sqlalchemy import select
from sqlalchemy.orm import Session
from werkzeug.exceptions import Unauthorized
from werkzeug.security import check_password_hash

from ..catalog.models import EdgeNode


def authenticate_node(session: Session, raw_id: str, api_key: str) -> EdgeNode:
    invalid = Unauthorized("Неверные учётные данные узла.")
    if not raw_id.isascii() or not raw_id.isdecimal() or len(raw_id) > 10 or not api_key:
        raise invalid
    node_id = int(raw_id)
    if not 1 <= node_id <= 2**31 - 1:
        raise invalid
    node = session.scalar(
        select(EdgeNode).where(EdgeNode.id == node_id, EdgeNode.is_active).with_for_update(read=True)
    )
    if node is None or not check_password_hash(node.api_key_hash, api_key):
        raise invalid
    return node
