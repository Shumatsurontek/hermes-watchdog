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

    def native_incident(self):
        from watchdog.native import NativeObserver

        observer = NativeObserver(self.store.native)
        for child in ("native-a", "native-b"):
            self.store.native.start("parent-a", child, "session-a")
        for child, call in (("native-a", "1"), ("native-a", "2"), ("native-b", "3")):
            observer.observe(
                "post_tool_call",
                {
                    "session_id": child,
                    "turn_id": "turn",
                    "tool_call_id": call,
                    "tool_name": "connector",
                    "status": "error",
                    "error_message": "SECRET_ERROR",
                },
            )
        return self.client.get("/incidents?view=related").json()["incidents"][0]

    def test_native_reads_hide_route_raw_errors_and_capabilities(self):
        item = self.native_incident()
        response = self.client.get("/incidents/" + item["id"])
        self.assertEqual(response.status_code, 200)
        for secret in ("SECRET_ERROR", "session-a", "PRIVATE_CAPABILITY"):
            self.assertNotIn(secret, response.text)
        self.assertEqual(response.json()["parent_session_id"], "parent-a")
        self.assertEqual(self.client.get("/native-runs?view=returned").json()["runs"], [])
        self.assertEqual(len(self.client.get("/native-runs/native-a").json()["evidence"]), 2)

    def test_native_action_is_idempotent_and_never_injects_from_http(self):
        item = self.native_incident()
        body = {
            "action": "request_recovery_review",
            "parent_session_id": "parent-a",
            "revision": item["revision"],
            "idempotency_key": "native-action-key",
        }
        url = "/incidents/" + item["id"] + "/actions"
        first = self.client.post(url, json=body)
        self.assertEqual(first.status_code, 202)
        self.assertEqual(first.json(), self.client.post(url, json=body).json())
        state = self.client.get("/incidents/" + item["id"]).json()["delivery"][0]["state"]
        self.assertEqual(state, "pending")

    def test_native_scope_revision_and_schema_cannot_be_bypassed(self):
        item = self.native_incident()
        url = "/incidents/" + item["id"] + "/actions"
        body = {
            "action": "request_recovery_review",
            "parent_session_id": "wrong",
            "revision": item["revision"],
            "idempotency_key": "native-action-key",
        }
        self.assertEqual(self.client.post(url, json=body).status_code, 409)
        body.update(parent_session_id="parent-a", revision=item["revision"] + 1)
        self.assertEqual(self.client.post(url, json=body).status_code, 409)
        body.update(revision=item["revision"], profile="another-profile")
        self.assertEqual(self.client.post(url, json=body).status_code, 422)
        self.assertEqual(self.client.get("/incidents?limit=51").status_code, 422)
        self.assertEqual(self.client.get("/native-runs?view=needs").status_code, 422)
        self.assertEqual(self.client.get("/incidents/unknown").status_code, 409)
