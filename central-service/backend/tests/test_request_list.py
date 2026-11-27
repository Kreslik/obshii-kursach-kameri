"""Чтение заявок из изолированной схемы PostgreSQL."""

import os
import unittest
from datetime import datetime

from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from app import create_app
from app.access_requests.models import AccessRequest
from app.auth.permissions import COOKIE, session_key
from app.catalog.models import RequestType, Substation
from app.users.models import User
from db_fixture import isolated_schema


MAX_REQUEST_ID = 2_147_483_647


@unittest.skipUnless(os.getenv("TEST_POSTGRES") == "1", "Требуется тестовый доступ к PostgreSQL")
class RequestListTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        engine = cls.enterClassContext(isolated_schema())
        command.upgrade(Config("alembic.ini"), "head")
        cls.app = create_app()
        cls.addClassCleanup(cls.app.extensions["db_engine"].dispose)
        with Session(engine) as session, session.begin():
            session.add_all([
                User(id=1, login="tester", full_name="Тест", role="dispatcher", password_hash="unused"),
                RequestType(id=1, name="Осмотр"),
                Substation(id=10, code="N", name="Северная"),
                Substation(id=20, code="S", name="Южная"),
            ])
            session.flush()
            for number, station, responsible, status, start, end in [
                (5, 10, "Петров", "pending", "2026-11-24T18:00Z", "2026-11-24T21:00Z"),
                (6, 10, "Иванов 9999999999", "active", "2026-11-25T19:00Z", "2026-11-25T22:00Z"),
                (7, 20, "Иванова", "closed", "2026-11-25T19:00Z", "2026-11-25T20:00Z"),
                (MAX_REQUEST_ID, 20, "Бригада 50%", "rejected", "2026-11-25T21:00Z", "2026-11-26T01:00Z"),
                (9, 10, "Удалена", "active", "2026-11-24T18:00Z", "2026-11-26T01:00Z"),
            ]:
                session.add(AccessRequest(
                    id=number, substation_id=station, type_id=1, created_by=1, responsible=responsible,
                    people_count=1, valid_from=datetime.fromisoformat(start), valid_to=datetime.fromisoformat(end),
                    status=status, deleted_at=datetime.fromisoformat(end) if number == 9 else None,
                ))
        # Тест списка использует реальный фильтр роли и блокировки в PostgreSQL.
        cls.app.extensions["redis"] = {session_key("operator-test-key"): "1"}

    def setUp(self):
        self.client = self.app.test_client()
        self.client.set_cookie(COOKIE, "operator-test-key")

    def page(self, **query):
        response = self.client.get("/api/v1/requests", query_string=query)
        self.assertEqual(response.status_code, 200, response.data)
        return response.get_json()

    def ids(self, **query):
        return [r["id"] for r in self.page(**query)["items"]]

    def test_authorization_fields_and_pagination(self):
        self.assertEqual(self.app.test_client().get("/api/v1/requests").status_code, 401)
        page = self.page(per_page=2)
        self.assertEqual([r["id"] for r in page["items"]], [MAX_REQUEST_ID, 7])
        self.assertTrue(page["has_more"])
        self.assertEqual(self.ids(page=2, per_page=2), [6, 5])
        self.assertFalse(self.page(page=2, per_page=2)["has_more"])
        row = page["items"][1]
        self.assertEqual(set(row), {"id", "substation_id", "substation_name", "responsible", "valid_from", "valid_to", "status"})
        self.assertEqual(row["substation_name"], "Южная")
        self.assertIsNotNone(datetime.fromisoformat(row["valid_to"]).tzinfo)

    def test_combined_filters_and_literal_search(self):
        self.assertEqual(self.ids(q="иван", substation_id=10, status="active"), [6])
        self.assertEqual(self.ids(q="Южная"), [MAX_REQUEST_ID, 7])
        self.assertEqual(self.ids(q="5"), [MAX_REQUEST_ID, 5])  # 50% в имени бригады и точный номер 5.
        self.assertEqual(self.ids(q="%"), [MAX_REQUEST_ID])
        self.assertEqual(self.ids(q="Удалена"), [])
        self.assertEqual(self.ids(q="нет такой записи"), [])

    def test_numeric_search_at_integer_limit(self):
        self.assertEqual(self.ids(q=str(MAX_REQUEST_ID)), [MAX_REQUEST_ID])
        self.assertEqual(self.ids(q=str(MAX_REQUEST_ID + 1)), [])
        self.assertEqual(self.ids(q="9999999999"), [6])

    def test_moscow_calendar_overlap(self):
        self.assertEqual(self.ids(date_from="2026-11-25", date_to="2026-11-25"), [7, 6, 5])
        self.assertEqual(self.ids(date_from="2026-11-26"), [MAX_REQUEST_ID, 6])
        self.assertEqual(self.ids(date_to="2026-11-24"), [5])

    def test_invalid_filters(self):
        for query in [
            {"status": "unknown"}, {"page": 0}, {"substation_id": -1}, {"per_page": 101},
            {"date_from": "2026-02-31"}, {"date_to": "20261125"},
            {"date_from": "2026-11-26", "date_to": "2026-11-25"},
        ]:
            with self.subTest(query=query):
                response = self.client.get("/api/v1/requests", query_string=query)
                self.assertEqual(response.status_code, 400)
