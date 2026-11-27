"""Адресация камеры по подстанции и номеру; данные событий Kafka."""

from alembic import op
import sqlalchemy as sa


revision = "0005_kafka_camera_events"
down_revision = "0004_camera_station_key"
branch_labels = None
depends_on = None

CAMERA_REFERENCES = ("detections", "roi_zones")
CAMERA_KEY = ["substation_id", "camera_id"]


def upgrade() -> None:
    # До конца транзакции старые писатели не могут добавить ссылку между UPDATE и сменой FK.
    op.execute("LOCK TABLE cameras, detections, roi_zones IN ACCESS EXCLUSIVE MODE")
    for table in CAMERA_REFERENCES:
        op.add_column(table, sa.Column("substation_id", sa.Integer()))
        op.drop_constraint(f"{table}_camera_id_fkey", table, type_="foreignkey")
        op.execute(f"""
            UPDATE {table} AS child
               SET substation_id = c.substation_id, camera_id = c.local_camera_id
              FROM cameras AS c
             WHERE child.camera_id = c.id
        """)
        op.alter_column(table, "substation_id", nullable=False)

    op.drop_constraint("cameras_pkey", "cameras", type_="primary")
    op.drop_constraint("uq_cameras_station_local_id", "cameras", type_="unique")
    op.alter_column("cameras", "local_camera_id", new_column_name="camera_id")
    op.create_primary_key("cameras_pkey", "cameras", CAMERA_KEY)
    for table in CAMERA_REFERENCES:
        op.create_foreign_key(f"fk_{table}_camera", table, "cameras", CAMERA_KEY, CAMERA_KEY)
    op.drop_column("cameras", "id")
    op.add_column("cameras", sa.Column("status_at", sa.DateTime(timezone=True)))
    op.alter_column("detections", "frame_key", new_column_name="file")
    # В HTTP-событиях до этой ревизии узел не передавал is_alert.
    op.add_column("detections", sa.Column("is_alert", sa.Boolean()))


def downgrade() -> None:
    op.execute("LOCK TABLE cameras, detections, roi_zones IN ACCESS EXCLUSIVE MODE")
    # Старые сквозные ID удалены. Создаём новые и переносим обе группы ссылок на них.
    op.execute("ALTER TABLE cameras ADD COLUMN id SERIAL")
    for table in CAMERA_REFERENCES:
        op.drop_constraint(f"fk_{table}_camera", table, type_="foreignkey")
        op.execute(f"""
            UPDATE {table} AS child
               SET camera_id = c.id
              FROM cameras AS c
             WHERE child.substation_id = c.substation_id AND child.camera_id = c.camera_id
        """)
        op.drop_column(table, "substation_id")
    op.drop_constraint("cameras_pkey", "cameras", type_="primary")
    op.alter_column("cameras", "camera_id", new_column_name="local_camera_id")
    op.create_primary_key("cameras_pkey", "cameras", ["id"])
    op.create_unique_constraint("uq_cameras_station_local_id", "cameras", ["substation_id", "local_camera_id"])
    for table in CAMERA_REFERENCES:
        op.create_foreign_key(f"{table}_camera_id_fkey", table, "cameras", ["camera_id"], ["id"])
    op.drop_column("cameras", "status_at")
    op.drop_column("detections", "is_alert")
    op.alter_column("detections", "file", new_column_name="frame_key")
