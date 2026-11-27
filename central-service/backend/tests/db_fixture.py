"""Временная схема PostgreSQL для миграций и дочернего процесса consumer."""

import os
from contextlib import contextmanager
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.schema import CreateSchema, DropSchema

from app.db import get_database_url


@contextmanager
def isolated_schema():
    schema = "test_central_" + uuid4().hex
    admin = create_engine(get_database_url())
    try:
        with admin.begin() as connection:
            connection.execute(CreateSchema(schema))
        try:
            with patch.dict(os.environ, {"PGOPTIONS": f"-csearch_path={schema}"}):
                engine = create_engine(get_database_url())
                try:
                    with engine.connect() as connection:
                        if connection.scalar(text("SELECT current_schema()")) != schema:
                            raise RuntimeError("Тестовая схема не выбрана")
                    yield engine
                finally:
                    engine.dispose()
        finally:
            with admin.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
    finally:
        admin.dispose()
