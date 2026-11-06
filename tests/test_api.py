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

    def test_work_groups_real_tasks_and_exposes_evidence_without_raw_errors(self):
        from watchdog.native import NativeObserver

        observer = NativeObserver(self.store.native)
        for child, title in (("ci", "Release readiness · Tests"), ("review", "Release readiness · Recovery audit")):
            observer.observe(
                "subagent_start",
                {
                    "parent_session_id": "release",
                    "child_session_id": child,
                    "child_goal": title + "\nUse the repository evidence; token=DO_NOT_PERSIST",
                },
                surface="desktop",
                bound_id="release",
                bound_key="private-route",
            )
        for child, call in (("ci", "1"), ("ci", "2"), ("review", "3")):
            observer.observe(
                "post_tool_call",
                {
                    "session_id": child,
                    "turn_id": "t",
                    "tool_call_id": call,
                    "tool_name": "read_file",
                    "status": "error",
                    "error_message": "PRIVATE_ERROR",
                },
            )
        observer.observe(
            "post_tool_call",
            {"session_id": "ci", "turn_id": "t", "tool_call_id": "4", "tool_name": "terminal", "status": "ok"},
        )
        observer.observe(
            "subagent_stop", {"child_session_id": "ci", "parent_session_id": "release", "child_status": "completed"}
        )
        response = self.client.get("/work")
        self.assertEqual(response.status_code, 200)
        page = response.json()
        mission = page["missions"][0]
        self.assertEqual(mission["counts"], {"workers": 2, "active": 1, "waiting": 0, "returned": 1, "attention": 1})
        worker = next(w for w in mission["workers"] if w["session_id"] == "ci")
        self.assertEqual(worker["label"], "Release readiness · Tests")
        self.assertTrue(worker["label_excerpt"])
        self.assertEqual(worker["state"], "returned")
        self.assertEqual(worker["observed_errors"], 2)
        # A later successful tool must not be blamed for the earlier matching errors.
        self.assertEqual(mission["incidents"][0]["tools"], ["read_file"])
        for secret in ("DO_NOT_PERSIST", "PRIVATE_ERROR", "private-route"):
            self.assertNotIn(secret, response.text)
        self.assertNotIn("evidence", worker)
        detail = self.client.get("/work/runs/ci").json()
        self.assertEqual(len(detail["evidence"]), 4)
        self.assertEqual(detail["worker"]["session_id"], "ci")
        # The generated frontend schema must stay in lockstep with Python.
        import json

        schema_path = Path(__file__).resolve().parents[1] / "desktop/generated/WorkPage.schema.json"
        expected = self.module._views.WorkPage.model_json_schema()
        expected["$id"] = "WorkPage"
        self.assertEqual(json.loads(schema_path.read_text()), expected)

    def test_work_pagination_has_exact_totals_and_no_silent_loss(self):
        for i in range(11):
            self.store.native.start(f"root-{i}", f"child-{i}", f"route-{i}")
        first = self.client.get("/work").json()
        second = self.client.get("/work?cursor=10").json()
        self.assertEqual((first["total_missions"], len(first["missions"]), first["next_cursor"]), (11, 10, 10))
        self.assertEqual((len(second["missions"]), second["next_cursor"]), (1, None))
        ids = {m["root_id"] for m in first["missions"] + second["missions"]}
        self.assertEqual(len(ids), 11)
        self.assertEqual(self.client.get("/work?cursor=-1").status_code, 422)
        self.assertEqual(self.client.get("/work?cursor=257").status_code, 422)
        self.assertEqual(self.client.get("/work/runs/not-in-profile").status_code, 409)

    def test_typed_history_preserves_cancellation_and_optional_results(self):
        response = self.client.get("/history")
        self.assertEqual(response.status_code, 200)
        task = response.json()["tasks"][0]
        self.assertEqual(task["goal"], "test task")
        self.assertTrue(task["can_cancel"])
        self.assertNotIn("PRIVATE_CAPABILITY", response.text)

    def test_notice_outbox_is_valid_in_work_contract(self):
        from watchdog.native import NativeObserver

        self.store.native.start("root", "waiting", "route")
        observer = NativeObserver(self.store.native, notices=True)
        observer.observe(
            "on_human_input_request", {"session_id": "waiting", "request_id": "approval", "kind": "approval"}
        )
        response = self.client.get("/work")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["missions"][0]["incidents"][0]["delivery"][0]["kind"], "opening")

    def test_reloading_updated_install_does_not_reuse_old_backend_modules(self):
        import shutil

        root = Path(__file__).resolve().parents[1]
        install = Path(self.tmp.name) / "install"
        shutil.copytree(root / "watchdog", install / "watchdog", ignore=shutil.ignore_patterns("__pycache__"))
        (install / "dashboard").mkdir()
        shutil.copyfile(root / "dashboard/plugin_api.py", install / "dashboard/plugin_api.py")

        def load_backend():
            spec = importlib.util.spec_from_file_location("reload_test", install / "dashboard/plugin_api.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module

        first = load_backend()
        # Keep a first-generation class alive just like an in-flight API request.
        old = first._storage.Store.local(Path(self.tmp.name) / "old.db")
        goal = "Review the actual release evidence " * 10
        old.native.start("root", "old", "route", goal=goal)
        source = install / "watchdog/presentation.py"
        source.write_text(source.read_text().replace("LABEL_CHARS_MAX = 160", "LABEL_CHARS_MAX = 40"))
        second = load_backend()
        new = second._storage.Store.local(Path(self.tmp.name) / "new.db")
        try:
            new.native.start("root", "new", "route", goal=goal)
            self.assertEqual(len(old.native.run("old")["label"]), 160)
            self.assertEqual(len(new.native.run("new")["label"]), 40)
            self.assertIsNot(first._storage.Store, second._storage.Store)
        finally:
            old.close()
            new.close()
