"""Движок SQLAlchemy и сессия PostgreSQL для текущего контекста Flask."""

from collections.abc import Mapping

from flask import Flask, current_app, g
from sqlalchemy import URL, create_engine
from sqlalchemy.orm import DeclarativeBase, Session

from .config import load_settings


class Base(DeclarativeBase):
    pass


def get_database_url(settings: Mapping[str, str] | None = None) -> URL:
    if settings is None:
        settings = load_settings()
    return URL.create(
        "postgresql+psycopg",
        username=settings.get("POSTGRES_USER", "central"),
        password=settings.get("POSTGRES_PASSWORD"),
        host=settings.get("POSTGRES_HOST", "localhost"),
        port=int(settings.get("POSTGRES_PORT", "5432")),
        database=settings.get("POSTGRES_DB", "central"),
    )


def load_models() -> None:
    # Импорт регистрирует все таблицы в общей Base.metadata для ORM и Alembic.
    from .access_requests import models as access_requests
    from .alerts import models as alerts
    from .audit import models as audit
    from .catalog import models as catalog
    from .detections import models as detections
    from .users import models as users


def get_session() -> Session:
    if "db_session" not in g:
        g.db_session = Session(current_app.extensions["db_engine"])
    return g.db_session


def init_db(app: Flask) -> None:
    load_models()
    app.extensions["db_engine"] = create_engine(
        get_database_url(app.config), pool_pre_ping=True
    )

    @app.teardown_appcontext
    def close_session(error: BaseException | None) -> None:
        session = g.pop("db_session", None)
        if session is not None:
            session.close()
