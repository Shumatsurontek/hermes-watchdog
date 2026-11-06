"""Fault tests for passive observation, durable attention and at-most-once intent."""

import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from watchdog.incidents import EVIDENCE_MAX, normalize
from watchdog.native import NativeObserver
from watchdog.policy import Rejected
from watchdog.recovery import RecoveryOutbox
from watchdog.store import Store


class NativeFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "ledger.db"
        self.now = 1000.0
        self.store = Store.local(self.path, clock=lambda: self.now)
        self.ledger = self.store.native
        self.observer = NativeObserver(self.ledger)
        self.messages = []
        self.acceptance = True
        self.pump = RecoveryOutbox(self.store, self)

    def tearDown(self):
        self.pump.close()
        self.store.close()
        self.tmp.cleanup()

    def inject_message(self, content, *, role, session_key):
        self.messages.append((content, role, session_key))
        if isinstance(self.acceptance, Exception):
            raise self.acceptance
        return self.acceptance

    def session_surface(self):
        return ""

    def start(self, child="a", parent="root", route="route", **kw):
        self.observer.observe(
            "subagent_start",
            {"parent_session_id": parent, "child_session_id": child, **kw},
            surface="desktop",
            bound_id=parent,
            bound_key=route,
        )

    def event(
        self, session="a", call="1", status="error", error="UPSTREAM_SECRET", tool="connector_fetch", turn="turn"
    ):
        self.observer.observe(
            "post_tool_call",
            {
                "session_id": session,
                "tool_call_id": call,
                "turn_id": turn,
                "status": status,
                "error_message": error,
                "tool_name": tool,
                "args": {"password": "PRIVATE"},
            },
        )

    def incident(self):
        return self.ledger.page()["incidents"][0]

    def failures(self):
        self.start("a")
        self.start("b")
        self.event("a", "1")
        self.event("a", "2")
        self.event("b", "3")
        return self.incident()

    def request(self, item=None, nonce="unique-action"):
        item = item or self.incident()
        return self.ledger.action(item["id"], "request_recovery_review", "root", item["revision"], nonce)

    def wait_event(self, kind, request="r1", session="a"):
        self.observer.observe(
            kind,
            {
                "session_id": session,
                "request_id": request,
                "kind": "approval",
                "outcome": "denied",
                "prompt": "PRIVATE",
            },
        )


class ObservationTests(NativeFixture):
    def test_nested_origin_and_no_legacy_reservations(self):
        self.start()
        self.start("nested", parent="a", parent_subagent_id="sa-a")
        self.assertEqual(self.ledger.run("nested")["root_id"], "root")
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM attempts").fetchone()[0], 0)

    def test_missing_nested_ancestor_disables_delivery(self):
        self.start("a", parent_subagent_id="missing")
        self.wait_event("on_human_input_request")
        self.assertFalse(self.incident()["recovery_available"])
        self.assertIn("ancestor", self.ledger.run("a")["gap"])

    def test_related_failures_are_scoped_and_do_not_claim_cause(self):
        item = self.failures()
        self.assertEqual(item["kind"], "related_failures")
        self.assertEqual(item["worker_count"], 2)
        self.start("other", parent="another-root", route="another-route")
        self.event("other", "4")
        self.assertEqual(len(self.ledger.page()["incidents"]), 1)
        encoded = json.dumps(self.ledger.run("a", evidence=True))
        self.assertNotIn("UPSTREAM_SECRET", encoded)
        self.assertNotIn("PRIVATE", encoded)
        self.assertIn("unclassified", encoded)

    def test_duplicates_and_missing_call_identity_cannot_cross_threshold(self):
        self.start("a")
        self.start("b")
        for _ in range(5):
            self.event("a", "1")
        self.event("b", "2")
        self.event("b", "")
        self.assertEqual(self.ledger.page()["incidents"], [])
        self.assertEqual(self.ledger.run("a")["seq"], 1)
        self.assertTrue(self.ledger.run("b")["gap"])

    def test_window_and_exact_tool_matching(self):
        self.start("a")
        self.start("b")
        self.event("a", "1")
        self.event("a", "2")
        self.now += 121
        self.event("b", "3")
        self.event("b", "4", tool="different_connector")
        self.assertFalse(self.ledger.page()["incidents"])

    def test_no_incident_for_healthy_or_transient_failure(self):
        self.start()
        self.event()
        self.now += 10000
        self.event(call="2", status="ok")
        self.assertFalse(self.ledger.page()["incidents"])
        self.assertEqual(self.ledger.run("a")["state"], "active")

    def test_unrelated_success_does_not_resolve_related_failure(self):
        item = self.failures()
        self.event(call="ok", status="ok", tool="different_tool")
        self.assertEqual(self.ledger.detail(item["id"])["status"], "open")

    def test_waits_resolve_only_by_matching_identity_or_terminal(self):
        self.start()
        self.wait_event("on_human_input_request")
        self.event(call="unrelated", status="ok")
        self.wait_event("on_human_input_resolved", "wrong")
        self.assertTrue(self.ledger.run("a")["waiting"])
        self.wait_event("on_human_input_resolved")
        self.assertFalse(self.ledger.run("a")["waiting"])
        self.assertEqual(self.incident()["status"], "resolved")
        self.wait_event("on_human_input_request")  # Duplicate remains resolved.
        self.assertEqual(self.incident()["status"], "resolved")

    def test_resolution_before_request_never_reopens_a_wait(self):
        self.start()
        self.wait_event("on_human_input_resolved")
        self.wait_event("on_human_input_request")
        self.assertFalse(self.ledger.run("a")["waiting"])
        self.assertFalse(self.ledger.page()["incidents"])

    def test_completion_is_reported_not_verified_and_clears_wait(self):
        self.start()
        self.wait_event("on_human_input_request")
        self.observer.observe(
            "subagent_stop",
            {
                "child_session_id": "a",
                "parent_session_id": "root",
                "child_status": "completed",
                "child_summary": "PRIVATE",
            },
        )
        item = self.ledger.run("a", evidence=True)
        self.assertEqual(item["state"], "returned")
        self.assertFalse(item["waiting"])
        self.assertNotIn("PRIVATE", json.dumps(item))
        self.assertEqual(self.incident()["status"], "ended")

    def test_metadata_window_retains_dedupe_tombstones(self):
        self.start()
        for n in range(80):
            self.event(call=str(n), status="ok")
        self.event(call="0", status="ok")
        item = self.ledger.run("a", evidence=True)
        self.assertEqual(item["seq"], 80)
        self.assertEqual(len(item["evidence"]), EVIDENCE_MAX)
        self.assertEqual(item["retained_from"], 17)

    def test_oversize_payload_and_capacity_are_visible_gaps(self):
        self.start()
        self.event(error="x" * 65_537)
        self.assertTrue(self.ledger.run("a")["gap"])
        for n in range(64):
            self.start("worker-" + str(n))
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM native_runs").fetchone()[0], 64)
        self.assertIn("capacity", self.ledger.page()["health"]["degraded"])

    def test_native_restart_preserves_wait_and_marks_execution_unknown(self):
        self.start()
        self.wait_event("on_human_input_request")
        self.ledger.recover()
        self.assertEqual(self.ledger.run("a")["state"], "unknown")
        self.assertEqual(self.incident()["status"], "open")
        self.assertTrue(self.incident()["execution_unknown"])

    def test_reset_uses_old_identity_and_late_events_do_not_reopen_attention(self):
        item = self.failures()
        self.request(item)
        self.observer.observe(
            "on_session_reset", {"session_id": "new", "old_session_id": "root", "new_session_id": "new"}
        )
        self.wait_event("on_human_input_request")
        self.pump.tick()
        self.assertFalse(self.messages)
        self.assertEqual(self.incident()["status"], "withdrawn")
        self.assertEqual(len(self.ledger.page()["incidents"]), 1)

    def test_terminal_failure_does_not_duplicate_related_attention(self):
        self.failures()
        for child in ("a", "b"):
            self.observer.observe(
                "subagent_stop", {"child_session_id": child, "parent_session_id": "root", "child_status": "failed"}
            )
        self.assertEqual(len(self.ledger.page()["incidents"]), 1)

    def test_identity_capacity_prevents_counting_old_events_again(self):
        from unittest.mock import patch

        self.start()
        with patch("watchdog.native_store.IDENTITIES_MAX", 2):
            self.event(call="1")
            self.event(call="2")
            self.event(call="3")
        self.assertEqual(self.ledger.run("a")["seq"], 2)
        self.assertIn("identities", self.ledger.run("a")["gap"])

    def test_pruning_preserves_unresolved_work_and_legacy_slots(self):
        tid = self.store.reserve("legacy", "legacy-parent", "goal", "", 900)
        self.start()
        self.start("returned", parent="settled-root")
        self.observer.observe(
            "subagent_stop",
            {"child_session_id": "returned", "parent_session_id": "settled-root", "child_status": "completed"},
        )
        self.now += 8 * 86400
        self.ledger.prune()
        self.assertTrue(self.ledger.has_run("a"))
        self.assertFalse(self.ledger.has_run("returned"))
        self.assertTrue(self.store.public(tid)["reserved"])

    def test_other_surfaces_and_legacy_children_are_not_double_observed(self):
        data = {"parent_session_id": "root", "child_session_id": "a"}
        self.observer.observe("subagent_start", data, surface="cli")
        self.observer.observe("subagent_start", data, surface="desktop", legacy=True)
        self.assertFalse(self.ledger.has_run("a"))


class RecoveryTests(NativeFixture):
    def test_recovery_brief_preserves_reference_to_returned_partial_work(self):
        item = self.failures()
        self.start("useful-docs")
        self.observer.observe(
            "subagent_stop",
            {
                "child_session_id": "useful-docs",
                "parent_session_id": "root",
                "child_status": "completed",
                "child_summary": "PRIVATE_OUTPUT",
            },
        )
        self.request(item)
        self.pump.tick()
        brief = self.messages[0][0]
        self.assertIn('"worker_session": "useful-docs", "reported_state": "returned"', brief)
        self.assertIn("Selected 3 of 3 observed workers", brief)
        self.assertNotIn("PRIVATE_OUTPUT", brief)
        self.assertEqual(self.ledger.detail(item["id"])["status"], "follow_up_requested")

    def test_disabling_observation_does_not_disable_scope_withdrawal(self):
        self.failures()
        self.request()
        self.observer.enabled = False
        self.observer.observe("on_session_delete", {"session_id": "root"})
        self.pump.tick()
        self.assertFalse(self.messages)
        self.assertEqual(self.incident()["delivery"][0]["state"], "withdrawn")

    def test_reopening_profile_in_classic_cli_cannot_receive_desktop_brief(self):
        self.failures()
        self.request()
        self.session_surface = lambda: "cli"
        self.pump.tick()
        self.assertFalse(self.messages)
        self.assertEqual(self.incident()["delivery"][0]["state"], "pending")

    def test_action_is_scoped_revision_checked_and_idempotent(self):
        item = self.failures()
        with self.assertRaises(Rejected):
            self.ledger.action(item["id"], "request_recovery_review", "other-root", item["revision"], "wrong-root")
        first = self.request(item)
        self.assertEqual(self.request(item), first)
        with self.assertRaises(Rejected):
            self.request(item, nonce="other-action")
        self.pump.tick()
        self.pump.tick()
        self.assertEqual(len(self.messages), 1)
        self.assertEqual(self.messages[0][2], "route")
        self.assertIn("partial effects", self.messages[0][0])
        self.assertNotIn("UPSTREAM_SECRET", self.messages[0][0])
        self.assertEqual(self.incident()["delivery"][0]["state"], "accepted")

    def test_new_click_after_refresh_does_not_queue_second_recovery(self):
        self.failures()
        first = self.request()
        second = self.request(nonce="another-request")
        self.assertEqual(first["outbox_id"], second["outbox_id"])
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM recovery_outbox").fetchone()[0], 1)

    def test_explicit_nonacceptance_has_three_attempts(self):
        self.failures()
        self.request()
        self.acceptance = False
        for _ in range(5):
            self.pump.tick()
        self.assertEqual(len(self.messages), 3)
        self.assertEqual(self.incident()["delivery"][0]["state"], "failed")

    def test_unknown_acceptance_and_restart_are_never_replayed(self):
        self.failures()
        self.request()
        self.acceptance = RuntimeError("fixture")
        self.pump.tick()
        self.ledger.recover()
        self.pump.tick()
        self.assertEqual(len(self.messages), 1)
        self.assertEqual(self.incident()["delivery"][0]["state"], "unknown")

    def test_interrupted_sending_is_unknown_on_restart(self):
        self.failures()
        self.request()
        with self.store.transaction():
            self.store.db.execute("UPDATE recovery_outbox SET state='sending'")
        self.ledger.recover()
        self.pump.tick()
        self.assertFalse(self.messages)
        self.assertEqual(self.incident()["delivery"][0]["state"], "unknown")

    def test_stop_delete_and_reset_withdraw_pending_not_tab_close(self):
        for kind in ("on_session_end", "on_session_delete", "on_session_reset", "on_session_finalize"):
            with self.subTest(kind=kind):
                # Each variant gets its own root and incident, in one profile.
                root, child = kind, "child-" + kind
                self.start(child, parent=root)
                self.wait_event("on_human_input_request", session=child)
                item = self.ledger.page(root=root)["incidents"][0]
                self.ledger.action(item["id"], "request_recovery_review", root, item["revision"], "action-" + kind)
                self.observer.observe(kind, {"session_id": root, "interrupted": True})
                self.pump.tick()
                state = self.ledger.detail(item["id"])["delivery"][0]["state"]
                self.assertEqual(state, "accepted" if kind == "on_session_finalize" else "withdrawn")

    def test_single_delivery_in_flight_under_concurrent_ticks(self):
        self.failures()
        self.request()
        entered, release = threading.Event(), threading.Event()

        class SlowHost:
            def session_surface(host):
                return ""

            def inject_message(host, *args, **kwargs):
                entered.set()
                self.assertTrue(release.wait(2))
                self.messages.append(args)
                return True

        self.pump.ctx = SlowHost()
        thread = threading.Thread(target=self.pump.tick)
        thread.start()
        try:
            self.assertTrue(entered.wait(2))
            self.pump.tick()
            self.assertFalse(self.messages)
        finally:
            release.set()
            thread.join(timeout=2)
        self.assertEqual(len(self.messages), 1)

    def test_quick_wait_does_not_send_obsolete_notice(self):
        self.observer.notices = True
        self.start()
        self.wait_event("on_human_input_request")
        self.wait_event("on_human_input_resolved")
        self.pump.tick()
        self.assertFalse(self.messages)
        self.assertEqual(self.incident()["delivery"][0]["state"], "withdrawn")

    def test_acknowledged_is_not_recovered_and_human_wait_cannot_be_acknowledged(self):
        item = self.failures()
        self.ledger.action(item["id"], "acknowledge", "root", item["revision"], "ack-action")
        self.assertEqual(self.ledger.detail(item["id"])["status"], "acknowledged")
        self.wait_event("on_human_input_request")
        wait = next(i for i in self.ledger.page()["incidents"] if i["kind"] == "human_input")
        with self.assertRaises(Rejected):
            self.ledger.action(wait["id"], "acknowledge", "root", wait["revision"], "ack-wait-action")


class MigrationTests(NativeFixture):
    def downgrade_fixture(self):
        # v1's exact table shape is unchanged; remove only additive v2 tables.
        names = self.store.db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        with self.store.transaction():
            for (name,) in names:
                if name.startswith("native_") or name in {"incidents", "incident_members", "recovery_outbox"}:
                    self.store.db.execute(f"DROP TABLE {name}")
            self.store.db.execute("PRAGMA user_version=1")

    def test_v1_backup_migration_and_restore_preserve_legacy_reservations(self):
        task = self.store.reserve("route", "root", "legacy goal", "context", 900)
        before = self.store.public(task, detail=True)
        self.downgrade_fixture()
        backup = sqlite3.connect(Path(self.tmp.name) / "backup.db")
        self.store.db.backup(backup)
        migrated = Store.local(self.path)
        try:
            self.assertEqual(migrated.public(task, detail=True), before)
            migrated.native.start("root", "a", "route")
            self.assertEqual(migrated.public(task)["reserved"], before["reserved"])
        finally:
            migrated.close()
        restored = sqlite3.connect(Path(self.tmp.name) / "restored.db")
        backup.backup(restored)
        self.assertEqual(restored.execute("PRAGMA user_version").fetchone()[0], 1)
        self.assertEqual(restored.execute("SELECT goal FROM tasks").fetchone()[0], "legacy goal")
        backup.close()
        restored.close()

    def test_failed_migration_rolls_back_schema_version_and_ddl(self):
        self.downgrade_fixture()
        with self.store.transaction():
            self.store.db.execute("CREATE TABLE native_runs (invalid TEXT)")
        db = sqlite3.connect(self.path)
        with self.assertRaises(sqlite3.OperationalError):
            Store(db)
        self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 1)
        self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='native_meta'").fetchone())
        db.close()


class NormalizationTests(unittest.TestCase):
    def test_error_json_is_hashed_and_giant_results_rejected(self):
        data = {
            "turn_id": "t",
            "tool_call_id": "c",
            "tool_name": "mcp_test",
            "status": "error",
            "result": '{"error":"PRIVATE"}',
        }
        _, event = normalize("post_tool_call", data)
        self.assertNotIn("PRIVATE", json.dumps(event))
        data["result"] = "x" * 65_537
        with self.assertRaises(Rejected):
            normalize("post_tool_call", data)
