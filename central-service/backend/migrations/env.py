"""Настройка Alembic для PostgreSQL центрального сервиса."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from app.db import Base, get_database_url, load_models


if context.config.config_file_name:
    fileConfig(context.config.config_file_name, disable_existing_loggers=False)

load_models()
settings = {
    "target_metadata": Base.metadata,
    "compare_type": True,
    "compare_server_default": True,
}


def run_migrations_offline() -> None:
    context.configure(url=get_database_url(), literal_binds=True, **settings)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(get_database_url(), poolclass=NullPool)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, **settings)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
