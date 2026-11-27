"""Начальная схема PostgreSQL центрального сервиса."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg


revision = "0001_central_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("login", sa.String(), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("role", sa.Enum("dispatcher", "admin", "auditor", name="user_role"), nullable=False),
        sa.Column("is_blocked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "substations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(), nullable=False, unique=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("address", sa.String()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "request_types",
        sa.Column("id", sa.SmallInteger(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False, unique=True),
    )
    op.create_table(
        "edge_nodes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("substation_id", sa.Integer(), sa.ForeignKey("substations.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("api_key_hash", sa.String(), nullable=False),
        sa.Column("status", sa.Enum("online", "offline", name="node_status"), nullable=False, server_default="offline"),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("model_version", sa.String()),
        sa.Column("software_version", sa.String()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("substation_id", "name", name="uq_edge_nodes_station_name"),
        sa.UniqueConstraint("id", "substation_id", name="uq_edge_nodes_id_station"),
    )
    op.create_table(
        "cameras",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("substation_id", sa.Integer(), sa.ForeignKey("substations.id"), nullable=False),
        sa.Column("node_id", sa.Integer()),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("rtsp_url", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("status", sa.Enum("online", "offline", name="camera_status"), nullable=False, server_default="offline"),
        sa.Column("last_frame_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["node_id", "substation_id"], ["edge_nodes.id", "edge_nodes.substation_id"],
            name="fk_cameras_node_station",
        ),
    )
    op.create_table(
        "roi_zones",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("camera_id", sa.Integer(), sa.ForeignKey("cameras.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("polygon", pg.JSONB(), nullable=False),
    )
    op.create_table(
        "access_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("substation_id", sa.Integer(), sa.ForeignKey("substations.id"), nullable=False),
        sa.Column("type_id", sa.SmallInteger(), sa.ForeignKey("request_types.id"), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("responsible", sa.String(), nullable=False),
        sa.Column("people_count", sa.SmallInteger(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status", sa.Enum("pending", "active", "closed", "rejected", name="request_status"),
            nullable=False, server_default="pending",
        ),
        sa.Column("admin_comment", sa.Text()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("valid_to > valid_from", name="ck_access_requests_period"),
        sa.CheckConstraint("people_count > 0", name="ck_access_requests_people_count"),
    )
    op.create_index(
        "ix_access_requests_station_status_from", "access_requests", ["substation_id", "status", "valid_from"]
    )
    op.execute("""
        CREATE FUNCTION touch_access_request() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            NEW.updated_at := statement_timestamp();
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER tr_access_requests_updated_at
        BEFORE UPDATE ON access_requests
        FOR EACH ROW EXECUTE FUNCTION touch_access_request()
    """)
    op.create_table(
        "detections",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("event_uuid", pg.UUID(), nullable=False, unique=True),
        sa.Column("camera_id", sa.Integer(), sa.ForeignKey("cameras.id"), nullable=False),
        sa.Column("roi_id", sa.Integer(), sa.ForeignKey("roi_zones.id")),
        sa.Column("matched_request_id", sa.Integer(), sa.ForeignKey("access_requests.id")),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("person_count", sa.SmallInteger(), nullable=False),
        sa.Column("confidence", sa.REAL(), nullable=False),
        sa.Column("frame_key", sa.String(), nullable=False),
        sa.CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_detections_confidence"),
        sa.CheckConstraint("person_count > 0", name="ck_detections_person_count"),
    )
    op.create_table(
        "alerts",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("detection_id", sa.BigInteger(), sa.ForeignKey("detections.id"), nullable=False),
        sa.Column("substation_id", sa.Integer(), sa.ForeignKey("substations.id"), nullable=False),
        sa.Column("node_id", sa.Integer(), sa.ForeignKey("edge_nodes.id"), nullable=False),
        sa.Column("request_id", sa.Integer(), sa.ForeignKey("access_requests.id")),
        sa.Column("processed_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column(
            "status", sa.Enum("new", "confirmed", "false_positive", "linked", name="alert_status"),
            nullable=False, server_default="new",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_alerts_station_status_created", "alerts", ["substation_id", "status", "created_at"])
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("event_uuid", pg.UUID(), nullable=False, unique=True),
        sa.Column("node_id", sa.Integer(), sa.ForeignKey("edge_nodes.id")),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("ip_address", pg.INET()),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String()),
        sa.Column("entity_id", sa.BigInteger()),
        sa.Column("details", pg.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.execute("""
        CREATE FUNCTION reject_audit_log_change() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only' USING ERRCODE = '55000';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER tr_audit_log_append_only
        BEFORE UPDATE OR DELETE OR TRUNCATE ON audit_log
        FOR EACH STATEMENT EXECUTE FUNCTION reject_audit_log_change()
    """)


def downgrade() -> None:
    op.drop_table("audit_log")
    op.execute("DROP FUNCTION reject_audit_log_change()")
    op.drop_table("alerts")
    op.drop_table("detections")
    op.drop_table("access_requests")
    op.execute("DROP FUNCTION touch_access_request()")
    op.drop_table("roi_zones")
    op.drop_table("cameras")
    op.drop_table("edge_nodes")
    op.drop_table("request_types")
    op.drop_table("substations")
    op.drop_table("users")
    for name in ("alert_status", "request_status", "camera_status", "node_status", "user_role"):
        pg.ENUM(name=name).drop(op.get_bind(), checkfirst=False)
