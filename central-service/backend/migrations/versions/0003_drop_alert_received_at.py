"""Убрать время приёма из тревог, создаваемых центром."""

from alembic import op
import sqlalchemy as sa


revision = "0003_drop_alert_received_at"
down_revision = "0002_alert_detection_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("alerts", "received_at")


def downgrade() -> None:
    op.add_column("alerts", sa.Column("received_at", sa.DateTime(timezone=True)))
    op.execute("UPDATE alerts SET received_at = created_at")
    op.alter_column("alerts", "received_at", nullable=False, server_default=sa.func.now())
