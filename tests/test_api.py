"""Exercise real FastAPI routes with an isolated ledger; host authentication stays host-owned."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

from watchdog.store import Store

AVAILABLE = importlib.util.find_spec("fastapi") is not None and importlib.util.find_spec("httpx") is not None


@unittest.skipUnless(AVAILABLE, "Run scripts/host_tests.py with Hermes dependencies for API checks")
class ApiTests(unittest.TestCase):
    def setUp(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "data.db"
        self.store = Store.local(self.path)
        self.tid = self.store.reserve("session-a", "parent-a", "test task", "", 900)
        self.store.attach(self.tid, {"capability": "PRIVATE_CAPABILITY"}, "child")
        path = Path(__file__).resolve().parents[1] / "dashboard/plugin_api.py"
        spec = importlib.util.spec_from_file_location("watchdog_api_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.module = module
        self.previous = module._storage.open_store
        module._storage.open_store = lambda: module._storage.Store.local(self.path)
        app = FastAPI()
        app.include_router(module.router)
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.module._storage.open_store = self.previous
        self.store.close()
        self.tmp.cleanup()

    def test_snapshot_redacts_handle(self):
        response = self.client.get("/tasks/" + self.tid)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("PRIVATE_CAPABILITY", response.text)
        self.assertFalse(response.json()["retry_allowed"])

    def test_cross_session_action_is_refused(self):
        body = {"action": "cancel", "session_key": "wrong", "revision": 2, "idempotency_key": "api-test-123"}
        self.assertEqual(self.client.post("/tasks/" + self.tid + "/actions", json=body).status_code, 409)
        self.assertFalse(self.store.has_cancel(self.tid))

    def test_action_is_idempotent_and_does_not_call_lifecycle(self):
        body = {"action": "cancel", "session_key": "session-a", "revision": 2, "idempotency_key": "api-test-123"}
        for _ in range(2):
            self.assertEqual(self.client.post("/tasks/" + self.tid + "/actions", json=body).status_code, 202)
        self.assertTrue(self.store.has_cancel(self.tid))
        self.assertEqual(self.store.public(self.tid)["execution"], "running")
        self.assertTrue(self.store.public(self.tid)["cancel_pending"])

    def test_retry_and_extra_fields_cannot_authorize_execution(self):
        body = {"action": "retry", "session_key": "session-a", "revision": 2, "idempotency_key": "api-test-123"}
        self.assertEqual(self.client.post("/tasks/" + self.tid + "/actions", json=body).status_code, 422)
        body.update(action="cancel", capability="forged")
        self.assertEqual(self.client.post("/tasks/" + self.tid + "/actions", json=body).status_code, 422)

    def test_stale_revision_and_page_bounds(self):
        body = {"action": "cancel", "session_key": "session-a", "revision": 1, "idempotency_key": "api-test-123"}
        self.assertEqual(self.client.post("/tasks/" + self.tid + "/actions", json=body).status_code, 409)
        self.assertEqual(self.client.get("/tasks?limit=51").status_code, 422)
