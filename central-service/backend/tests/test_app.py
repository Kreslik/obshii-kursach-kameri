import unittest

from app import create_app


class CentralServiceTest(unittest.TestCase):
    def test_health_endpoint(self):
        client = create_app().test_client()
        response = client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_node_http_event_route_removed(self):
        response = create_app().test_client().post("/api/v1/node/events")
        self.assertEqual(response.status_code, 404)
