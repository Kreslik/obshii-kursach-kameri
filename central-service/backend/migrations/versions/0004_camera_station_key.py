"""Локальный номер камеры уникален в пределах подстанции."""

from alembic import op
import sqlalchemy as sa


revision = "0004_camera_station_key"
down_revision = "0003_drop_alert_received_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cameras", sa.Column("local_camera_id", sa.Integer()))
    # Ранее узлы передавали cameras.id. Сохраняем адресацию существующих камер.
    op.execute("UPDATE cameras SET local_camera_id = id")
    op.alter_column("cameras", "local_camera_id", nullable=False)
    op.create_check_constraint("ck_cameras_local_id_positive", "cameras", "local_camera_id > 0")
    op.create_unique_constraint("uq_cameras_station_local_id", "cameras", ["substation_id", "local_camera_id"])


def downgrade() -> None:
    op.drop_column("cameras", "local_camera_id")
