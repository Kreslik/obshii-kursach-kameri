"""Приёмочная проверка на PostgreSQL, изолированная в отдельной схеме."""

import os
import secrets
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.schema import CreateSchema, DropSchema

from app import create_app
from app.access_requests.models import AccessRequest
from app.alerts.models import Alert
from app.catalog.models import Camera
from app.db import Base, get_database_url, get_session
from app.detections.models import Detection


@unittest.skipUnless(os.getenv("TEST_POSTGRES") == "1", "Требуется тестовый доступ к PostgreSQL")
class DatabaseTest(unittest.TestCase):
    def test_migrate_seed_read_downgrade(self):
        schema = "test_central_" + uuid4().hex
        admin = create_engine(get_database_url())
        self.addCleanup(admin.dispose)
        with admin.begin() as connection:
            connection.execute(CreateSchema(schema))

        def drop_test_schema():
            with admin.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))

        self.addCleanup(drop_test_schema)
        settings = {"PGOPTIONS": f"-csearch_path={schema}", "DEMO_NODE_API_KEY": secrets.token_urlsafe()}
        with patch.dict(os.environ, settings):
            app = create_app()
            engine = app.extensions["db_engine"]
            self.addCleanup(engine.dispose)
            with engine.connect() as connection:
                self.assertEqual(connection.scalar(text("SELECT current_schema()")), schema)
            self.assertEqual(inspect(engine).get_table_names(), [])
            config = Config("alembic.ini")
            command.upgrade(config, "head")
            command.check(config)
            inspector = inspect(engine)
            self.assertEqual(set(inspector.get_table_names()), set(Base.metadata.tables) | {"alembic_version"})
            self.assertEqual(inspector.get_pk_constraint("alerts")["constrained_columns"], ["id"])
            unique_keys = [key["column_names"] for key in inspector.get_unique_constraints("alerts")]
            self.assertIn(["detection_id"], unique_keys)
            self.assertEqual(inspector.get_pk_constraint("cameras")["constrained_columns"], ["substation_id", "camera_id"])
            alert_columns = {column["name"] for column in inspector.get_columns("alerts")}
            self.assertNotIn("received_at", alert_columns)
            self.assertIn("created_at", alert_columns)
            self.assertIn("substation_id", alert_columns)
            self.assertIn("received_at", {column["name"] for column in inspector.get_columns("detections")})

            runner = app.test_cli_runner()
            for _ in range(2):
                result = runner.invoke(args=["seed-demo"])
                self.assertEqual(result.exit_code, 0, (result.output, result.exception))
            with app.app_context():
                session = get_session()
                camera = session.scalars(select(Camera)).one()
                self.assertEqual(camera.substation.code, "DEMO-PS-01")
                self.assertEqual(camera.node.substation_id, camera.substation_id)
                request = session.scalars(select(AccessRequest)).one()
                self.assertEqual(request.substation_id, camera.substation_id)
                self.assertEqual(request.status, "active")
                self.assertEqual(request.valid_from, datetime(2026, 11, 23, 9, tzinfo=timezone.utc))
                self.assertEqual(request.valid_to, datetime(2026, 11, 23, 12, tzinfo=timezone.utc))
                station_id, camera_id = camera.substation_id, camera.camera_id
                for table in ("substations", "edge_nodes", "users", "request_types"):
                    self.assertEqual(session.scalar(select(func.count()).select_from(Base.metadata.tables[table])), 1)

                detection_time = datetime(2026, 11, 23, 8, tzinfo=timezone.utc)
                detection = Detection(
                    event_uuid=uuid4(), substation_id=station_id, camera_id=camera_id, detected_at=detection_time,
                    received_at=detection_time, person_count=1, confidence=0.9, file="test/frame.jpg",
                )
                session.add(detection)
                session.flush()
                alert_created_at = datetime(2026, 11, 23, 8, 0, 1, tzinfo=timezone.utc)
                session.add(Alert(
                    detection_id=detection.id, substation_id=camera.substation_id,
                    node_id=camera.node_id, created_at=alert_created_at,
                ))
                session.commit()

            result = runner.invoke(args=["show-camera", str(station_id), str(camera_id)])
            self.assertEqual(result.exit_code, 0, (result.output, result.exception))
            self.assertIn("demo-camera-01", result.output)
            self.assertIn("DEMO-PS-01", result.output)

            with engine.begin() as connection:
                updated = connection.scalar(text("UPDATE access_requests SET updated_at = '2000-01-01' RETURNING updated_at"))
                self.assertGreater(updated.year, 2000)
            with self.assertRaises(DBAPIError) as caught, engine.begin() as connection:
                connection.execute(text("DELETE FROM audit_log"))
            self.assertEqual(caught.exception.orig.sqlstate, "55000")

            with engine.connect() as connection:
                original_alert = dict(connection.execute(text("SELECT * FROM alerts")).mappings().one())
            command.downgrade(config, "0002_alert_detection_unique")
            with engine.connect() as connection:
                received_at = connection.execute(text("SELECT received_at FROM alerts")).scalar_one()
                self.assertEqual(received_at, alert_created_at)
            command.upgrade(config, "head")
            with engine.connect() as connection:
                restored_alert = dict(connection.execute(text("SELECT * FROM alerts")).mappings().one())
                self.assertEqual(restored_alert, original_alert)
                self.assertEqual(connection.execute(text("SELECT camera_id FROM cameras")).scalar_one(), camera_id)
                self.assertEqual(connection.execute(text("SELECT received_at FROM detections")).scalar_one(), detection_time)

            command.downgrade(config, "base")
            self.assertEqual(inspect(engine).get_table_names(), ["alembic_version"])
            command.upgrade(config, "head")


if __name__ == "__main__":
    unittest.main()
