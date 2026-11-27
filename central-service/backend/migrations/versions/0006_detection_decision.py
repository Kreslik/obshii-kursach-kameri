"""Флаг пересечения зоны передаётся только во входном событии."""

from alembic import op
import sqlalchemy as sa

revision = "0006_detection_decision"
down_revision = "0005_kafka_camera_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("detections", "is_alert")


def downgrade() -> None:
    op.add_column("detections", sa.Column("is_alert", sa.Boolean(), nullable=True))
