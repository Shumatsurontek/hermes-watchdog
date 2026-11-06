"""A profile-bound ledger. No Hermes call is made while a write transaction is held."""

import json
import re
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .policy import (
    ACTIONS_PENDING_MAX,
    ACTIVE_MAX,
    EVENT_BYTES_MAX,
    EVENTS_MAX,
    OBSERVATIONS_MAX,
    PAGE_MAX,
    RESULT_BYTES_MAX,
    SESSION_ROWS_MAX,
    TASK_ROWS_MAX,
    TASKS_PER_SESSION_MAX,
    TERMINAL,
    Rejected,
    excerpt,
    retry_reason,
)

SCHEMA_VERSION = 2


class EvidenceFull(Rejected):
    def __init__(self, task_id):
        super().__init__("Action evidence capacity reached")
        self.task_id = task_id


def notice_state(attempt, deleted=False):
    if deleted:
        return "not_needed"
    if attempt["notification"] in {"sending", "unknown"}:
        return attempt["notification"]
    return "pending" if attempt["notice_attempts"] < 3 else "failed"


class Store:
    def __init__(self, connection, *, clock=time.time):
        self.db = connection
        self.db.row_factory = sqlite3.Row
        self.clock = clock
        self.lock = threading.RLock()
        self.db.execute("PRAGMA busy_timeout=50")
        from .native_store import SCHEMA, NativeLedger

        with self.lock, self.db:
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, SCHEMA_VERSION):
                raise Rejected(f"Unsupported Watchdog database schema {version}")
            if version < SCHEMA_VERSION:
                # executescript otherwise commits implicitly before its first
                # statement. An explicit transaction makes migration atomic.
                self.db.executescript(
                    """
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS sessions (session_key TEXT PRIMARY KEY, count INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, session_key TEXT NOT NULL, parent_id TEXT NOT NULL,
                    created REAL NOT NULL, revision INTEGER NOT NULL, goal TEXT NOT NULL,
                    context TEXT NOT NULL, deadline INTEGER NOT NULL, deleted INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS attempts (
                    task_id TEXT PRIMARY KEY REFERENCES tasks(id), data TEXT NOT NULL, reserved INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id),
                    kind TEXT NOT NULL, data TEXT NOT NULL, status TEXT NOT NULL,
                    nonce TEXT UNIQUE, created REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS events_task ON events(task_id, id);
                CREATE INDEX IF NOT EXISTS tasks_session ON tasks(session_key, created);
            """
                    + SCHEMA
                    + "\nPRAGMA user_version=2;\nCOMMIT;"
                )
        self.native = NativeLedger(self)

    @classmethod
    def local(cls, path, **kwargs):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        connection = sqlite3.connect(path, check_same_thread=False)
        path.chmod(0o600)
        return cls(connection, **kwargs)

    @contextmanager
    def transaction(self):
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                yield
                self.db.commit()
            except EvidenceFull as exc:
                self.db.rollback()
                # The refused transaction must still leave visible evidence that
                # automated intervention no longer has a complete action history.
                self.db.execute("BEGIN IMMEDIATE")
                try:
                    _, attempt = self._read(exc.task_id)
                    attempt.update(supervision="evidence_gap", reason="action_evidence_capacity_reached")
                    self._write(exc.task_id, attempt)
                    self.db.commit()
                except BaseException:
                    self.db.rollback()
                    raise
                raise
            except BaseException:
                self.db.rollback()
                raise

    def close(self):
        with self.lock:
            self.db.close()

    def _read(self, task_id):
        if not isinstance(task_id, str) or not re.fullmatch(r"wd_[0-9a-f]{16}", task_id):
            raise Rejected("Invalid Watchdog task id")
        row = self.db.execute(
            "SELECT t.*, a.data, a.reserved FROM tasks t JOIN attempts a ON a.task_id=t.id WHERE t.id=?", (task_id,)
        ).fetchone()
        if row is None:
            raise Rejected("Task not found in this profile")
        task = dict(row)
        attempt = json.loads(task.pop("data"))
        return task, attempt

    def read(self, task_id):
        with self.lock:
            return self._read(task_id)

    def _write(self, task_id, attempt, *, reserved=None):
        if reserved is None:
            self.db.execute("UPDATE attempts SET data=? WHERE task_id=?", (json.dumps(attempt), task_id))
        else:
            self.db.execute(
                "UPDATE attempts SET data=?, reserved=? WHERE task_id=?", (json.dumps(attempt), int(reserved), task_id)
            )
        self.db.execute("UPDATE tasks SET revision=revision+1 WHERE id=?", (task_id,))

    def _event(self, task_id, kind, data, status="recorded", nonce=None):
        encoded = json.dumps(data, sort_keys=True)
        if len(encoded.encode()) > EVENT_BYTES_MAX:
            raise Rejected(f"Event exceeds {EVENT_BYTES_MAX} bytes")
        count = self.db.execute("SELECT count(*) FROM events WHERE task_id=?", (task_id,)).fetchone()[0]
        if count >= EVENTS_MAX:
            raise EvidenceFull(task_id)
        self.db.execute(
            "INSERT INTO events(task_id,kind,data,status,nonce,created) VALUES(?,?,?,?,?,?)",
            (task_id, kind, encoded, status, nonce, self.clock()),
        )

    def reserve(self, session_key, parent_id, goal, context, deadline_seconds):
        now = self.clock()
        task_id = "wd_" + uuid.uuid4().hex[:16]
        attempt = dict(
            execution="starting",
            supervision="healthy",
            notification="not_needed",
            reason="reserved_before_launch",
            handle=None,
            child_session=None,
            deadline_at=now + deadline_seconds,
            last_progress_at=now,
            cancel_at=None,
            observation_count=0,
            observations=[],
            retained_from=1,
            failure_streak=0,
            last_failure=None,
            seen_calls=[],
            waiting=False,
            result=None,
            result_excerpt=False,
            error_classification=None,
            judge_calls=0,
            steers=0,
            notice_attempts=0,
            launch_owner=None,
        )
        with self.transaction():
            if self.db.execute("SELECT count(*) FROM attempts WHERE reserved=1").fetchone()[0] >= ACTIVE_MAX:
                raise Rejected("All 3 execution slots are reserved; unresolved workers also consume a slot")
            if self.db.execute("SELECT count(*) FROM tasks").fetchone()[0] >= TASK_ROWS_MAX:
                raise Rejected("Task retention limit reached; prune settled history")
            session = self.db.execute("SELECT count FROM sessions WHERE session_key=?", (session_key,)).fetchone()
            if session is None:
                if self.db.execute("SELECT count(*) FROM sessions").fetchone()[0] >= SESSION_ROWS_MAX:
                    raise Rejected("Session retention limit reached")
                self.db.execute("INSERT INTO sessions VALUES(?,0)", (session_key,))
            elif session[0] >= TASKS_PER_SESSION_MAX:
                raise Rejected("This conversation reached its 10-task limit")
            self.db.execute("UPDATE sessions SET count=count+1 WHERE session_key=?", (session_key,))
            self.db.execute(
                "INSERT INTO tasks(id,session_key,parent_id,created,revision,goal,context,deadline) VALUES(?,?,?,?,1,?,?,?)",
                (task_id, session_key, parent_id, now, goal, context, deadline_seconds),
            )
            self.db.execute("INSERT INTO attempts VALUES(?,?,1)", (task_id, json.dumps(attempt)))
            self._event(task_id, "reserved", {"reason": "capacity_reserved_before_launch"})
        return task_id

    def attach(self, task_id, handle, child_session=None):
        with self.transaction():
            _, a = self._read(task_id)
            assert a["handle"] is None and a["execution"] == "starting"
            a.update(handle=handle, child_session=child_session, execution="running", reason="launched")
            self._write(task_id, a)
            self._event(task_id, "launched", {"reason": "host_returned_handle"})

    def degrade(self, task_id, reason, supervision="control_unavailable"):
        with self.transaction():
            task, a = self._read(task_id)
            a.update(supervision=supervision, reason=reason)
            if a["execution"] not in TERMINAL:
                a["execution"] = "unknown"
            a["notification"] = notice_state(a, task["deleted"])
            self._write(task_id, a)  # Retain capacity: unavailable control is not termination.

    def recover(self):
        with self.transaction():
            rows = self.db.execute("SELECT task_id,data,reserved FROM attempts").fetchall()
            assert len(rows) <= TASK_ROWS_MAX
            for row in rows:
                a = json.loads(row["data"])
                if row["reserved"]:
                    a.update(execution="unknown", supervision="control_unavailable", reason="process_or_plugin_restart")
                if a["notification"] == "sending":
                    a.update(notification="unknown", reason="notice_acceptance_unknown_after_restart")
                self._write(row["task_id"], a)
            self.db.execute("UPDATE events SET status='unknown' WHERE status='pending'")

    def settle(self, task_id, state, summary, classification):
        assert state in TERMINAL
        with self.transaction():
            task, a = self._read(task_id)
            if a["execution"] in TERMINAL:
                return
            text, clipped = excerpt(summary, RESULT_BYTES_MAX)
            # Timeout and unknown error classifications can hide a still-running
            # tool thread; interrupted agent loops can also leave tool calls unwinding.
            # Release slots only for known normally returned outcomes.
            settled = state == "succeeded" or (state == "failed" and classification == "ERROR")
            a.update(
                execution=state,
                result=text,
                result_excerpt=clipped,
                error_classification=classification,
                supervision="healthy" if settled else "execution_unresolved",
                reason="host_terminal_result" if settled else "host_result_does_not_prove_execution_stopped",
                waiting=False,
                notification=notice_state(a, task["deleted"]),
            )
            self._write(task_id, a, reserved=not settled)
            self.db.execute("UPDATE events SET status='obsolete' WHERE task_id=? AND status='pending'", (task_id,))
            self._event(task_id, "terminal", {"execution": state, "classification": classification})

    def observe(self, task_id, observation):
        encoded = json.dumps(observation, sort_keys=True)
        if len(encoded.encode()) > EVENT_BYTES_MAX:
            self.degrade(task_id, "observation_exceeds_bound", "evidence_gap")
            return
        with self.transaction():
            _, a = self._read(task_id)
            if a["execution"] in TERMINAL:
                return
            a["observation_count"] += 1
            item = dict(observation, seq=a["observation_count"], at=self.clock())
            a["observations"] = (a["observations"] + [item])[-OBSERVATIONS_MAX:]
            a["retained_from"] = a["observations"][0]["seq"]
            a["last_progress_at"] = self.clock()
            a["waiting"] = item["kind"] == "human_input"
            if item["kind"] == "tool_end":
                call = item.get("call_id")
                fingerprint = item.get("fingerprint")
                if not call:
                    a.update(supervision="evidence_gap", reason="tool_call_missing_identity")
                elif call not in a["seen_calls"]:
                    a["seen_calls"] = (a["seen_calls"] + [call])[-OBSERVATIONS_MAX:]
                    failed = item.get("status") == "error"
                    a["failure_streak"] = (
                        (a["failure_streak"] + 1 if a["last_failure"] == fingerprint else 1) if failed else 0
                    )
                    a["last_failure"] = fingerprint if failed else None
            self._write(task_id, a)

    def request_cancel(self, task_id, session_key, revision, nonce):
        if not isinstance(nonce, str) or not 8 <= len(nonce) <= 80:
            raise Rejected("Action idempotency key must be 8–80 characters")
        with self.transaction():
            task, a = self._read(task_id)
            if task["session_key"] != session_key or task["deleted"]:
                raise Rejected("Task does not belong to the selected conversation")
            existing = self.db.execute("SELECT task_id,kind FROM events WHERE nonce=?", (nonce,)).fetchone()
            if existing:
                if existing["task_id"] != task_id or existing["kind"] != "cancel":
                    raise Rejected("Idempotency key already used for a different action")
                return
            if type(revision) is not int or task["revision"] != revision:
                raise Rejected("Task changed; refresh before acting")
            if not task["reserved"] or a["execution"] in TERMINAL or a["supervision"] == "control_unavailable":
                raise Rejected("Task is no longer controllable")
            if a["cancel_at"] is not None or self.has_cancel(task_id):
                raise Rejected("Cancellation already requested or queued")
            if (
                self.db.execute("SELECT count(*) FROM events WHERE status='pending'").fetchone()[0]
                >= ACTIONS_PENDING_MAX
            ):
                raise Rejected("Control queue is full")
            self._event(task_id, "cancel", {"reason": "explicit_user_or_parent_request"}, "pending", nonce)
            self.db.execute("UPDATE tasks SET revision=revision+1 WHERE id=?", (task_id,))

    def cancel_intent(self, task_id, reason, supervision):
        with self.transaction():
            _, a = self._read(task_id)
            if a["execution"] in TERMINAL or a["cancel_at"] is not None:
                return False
            self._event(task_id, "cancel_intent", {"reason": reason})
            a.update(cancel_at=self.clock(), execution="cancel_requested", supervision=supervision, reason=reason)
            self._write(task_id, a)
            self.db.execute(
                "UPDATE events SET status='consumed' WHERE task_id=? AND kind='cancel' AND status='pending'", (task_id,)
            )
            return True

    def has_cancel(self, task_id):
        with self.lock:
            return (
                self.db.execute(
                    "SELECT 1 FROM events WHERE task_id=? AND kind='cancel' AND status='pending' LIMIT 1", (task_id,)
                ).fetchone()
                is not None
            )

    def update(self, task_id, **fields):
        with self.transaction():
            _, a = self._read(task_id)
            assert fields.keys() <= a.keys()
            if fields.get("notification") == "pending":
                fields["notification"] = notice_state(a)
            a.update(fields)
            self._write(task_id, a)

    def delete_parent(self, parent_id):
        with self.transaction():
            self.db.execute("UPDATE tasks SET deleted=1,revision=revision+1 WHERE parent_id=?", (parent_id,))

    def public(self, task_id, *, detail=False):
        with self.lock:
            task, a = self._read(task_id)
            result = {k: task[k] for k in ("id", "session_key", "parent_id", "created", "revision", "goal", "deleted")}
            result.update(
                {
                    k: a[k]
                    for k in (
                        "execution",
                        "supervision",
                        "notification",
                        "reason",
                        "deadline_at",
                        "cancel_at",
                        "waiting",
                        "observation_count",
                        "retained_from",
                        "judge_calls",
                        "steers",
                        "error_classification",
                    )
                }
            )
            result.update(
                cancel_pending=self.has_cancel(task_id),
                reserved=bool(task["reserved"]),
                attempt_number=1,
                retry_allowed=False,
                retry_reason=retry_reason(),
            )
            if detail:
                result.update(result=a["result"], result_excerpt=a["result_excerpt"], observations=a["observations"])
                rows = self.db.execute(
                    "SELECT id,kind,data,status,created FROM events WHERE task_id=? ORDER BY id LIMIT ?",
                    (task_id, EVENTS_MAX),
                ).fetchall()
                result["events"] = [dict(r, data=json.loads(r["data"])) for r in rows]
            return result

    def page(self, *, session_key=None, cursor="", limit=PAGE_MAX):
        if type(limit) is not int or not 1 <= limit <= PAGE_MAX:
            raise Rejected(f"Page size must be from 1 to {PAGE_MAX}")
        with self.lock:
            rows = self.db.execute(
                "SELECT id FROM tasks WHERE id>? AND (? IS NULL OR session_key=?) ORDER BY id LIMIT ?",
                (cursor, session_key, session_key, limit + 1),
            ).fetchall()
            return {
                "tasks": [self.public(r["id"]) for r in rows[:limit]],
                "next_cursor": rows[limit - 1]["id"] if len(rows) > limit else None,
            }

    def prune(self):
        cutoff = self.clock() - 7 * 86400
        with self.transaction():
            rows = self.db.execute(
                "SELECT t.id FROM tasks t JOIN attempts a ON t.id=a.task_id WHERE a.reserved=0 AND t.created<?",
                (cutoff,),
            ).fetchall()
            for row in rows:
                _, a = self._read(row["id"])
                if a["notification"] in {"pending", "sending"}:
                    continue
                self.db.execute("DELETE FROM events WHERE task_id=?", (row["id"],))
                self.db.execute("DELETE FROM attempts WHERE task_id=?", (row["id"],))
                self.db.execute("DELETE FROM tasks WHERE id=?", (row["id"],))
            # Counters survive while any task in that conversation is retained.
            self.db.execute("DELETE FROM sessions WHERE session_key NOT IN (SELECT session_key FROM tasks)")

    def claim_notices(self, session_key):
        claimed = []
        with self.transaction():
            rows = self.db.execute(
                "SELECT id FROM tasks WHERE session_key=? AND deleted=0 ORDER BY created LIMIT ?",
                (session_key, TASKS_PER_SESSION_MAX),
            ).fetchall()
            for row in rows:
                _, a = self._read(row["id"])
                if a["notification"] != "pending" or a["notice_attempts"] >= 3:
                    continue
                a.update(notification="sending", notice_attempts=a["notice_attempts"] + 1)
                self._write(row["id"], a)
                claimed.append({"id": row["id"], "execution": a["execution"], "reason": a["reason"]})
        return claimed

    def finish_notices(self, ids, accepted):
        with self.transaction():
            for task_id in ids:
                _, a = self._read(task_id)
                if a["notification"] != "sending":
                    continue
                state = (
                    "accepted"
                    if accepted is True
                    else ("unknown" if accepted is None else ("failed" if a["notice_attempts"] >= 3 else "pending"))
                )
                a["notification"] = state
                self._write(task_id, a)
                self._event(task_id, "notification", {"state": state, "attempt": a["notice_attempts"]})
