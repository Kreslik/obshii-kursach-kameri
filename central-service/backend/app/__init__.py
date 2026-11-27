"""Точка сборки центрального приложения."""

from flask import Flask

from .access_requests.routes import bp as requests_bp
from .alerts.routes import bp as alerts_bp
from .audit.routes import bp as audit_bp
from .auth.routes import bp as auth_bp
from .auth.permissions import init_permissions
from .realtime.alerts_socket import init_alert_socket
from .catalog.routes import bp as catalog_bp
from .cli import register_commands
from .config import load_settings
from .db import init_db
from .detections.routes import bp as detections_bp
from .reports.routes import bp as reports_bp
from .users.routes import bp as users_bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(load_settings())
    init_db(app)
    init_permissions(app)
    init_alert_socket(app)
    register_commands(app)

    for blueprint in (
        auth_bp, users_bp, catalog_bp, requests_bp, alerts_bp, detections_bp, audit_bp, reports_bp
    ):
        app.register_blueprint(blueprint)

    @app.get("/api/v1/health")
    def health():
        """Проверка доступности процесса Flask."""
        return {"status": "ok"}

    return app
