"""Одна детекция может породить не более одной тревоги."""

from alembic import op


revision = "0002_alert_detection_unique"
down_revision = "0001_central_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_alerts_detection_id", "alerts", ["detection_id"])


def downgrade() -> None:
    op.drop_constraint("uq_alerts_detection_id", "alerts", type_="unique")
