"""Additive native ledger; execution ownership stays with Hermes.

All writes run under Store.transaction. Limits are checked before insertion;
neither native observation nor retention touches legacy execution reservations.
"""

import json
import uuid

from .incidents import (
    ATTENTION,
    EVIDENCE_MAX,
    IDENTITIES_MAX,
    NATIVE_ACTIVE_MAX,
    OPEN_MAX,
    OUTBOX_MAX,
    PAGE_MAX,
    ROOTS_MAX,
    ROWS_MAX,
    SETTLED,
    WINDOW_SECONDS,
    digest,
    identity,
    recovery_brief,
    related,
)
from .policy import Rejected, bounded_text

SCHEMA = """
CREATE TABLE IF NOT EXISTS native_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS native_roots (
    root_id TEXT PRIMARY KEY, route TEXT NOT NULL, route_active INTEGER NOT NULL,
    deleted INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS native_runs (
    session_id TEXT PRIMARY KEY, parent_id TEXT NOT NULL, root_id TEXT NOT NULL,
    state TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
    seq INTEGER NOT NULL DEFAULT 0, gap TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS native_runs_root ON native_runs(root_id, session_id);
CREATE TABLE IF NOT EXISTS native_seen (
    session_id TEXT NOT NULL, key TEXT NOT NULL, PRIMARY KEY(session_id, key));
CREATE TABLE IF NOT EXISTS native_evidence (
    session_id TEXT NOT NULL, seq INTEGER NOT NULL, created REAL NOT NULL,
    fingerprint TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY(session_id, seq));
CREATE INDEX IF NOT EXISTS native_fingerprints ON native_evidence(fingerprint, created);
CREATE TABLE IF NOT EXISTS incidents (
    id TEXT PRIMARY KEY, root_id TEXT NOT NULL, kind TEXT NOT NULL, signature TEXT NOT NULL,
    status TEXT NOT NULL, revision INTEGER NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
    UNIQUE(root_id, kind, signature));
CREATE TABLE IF NOT EXISTS incident_members (
    incident_id TEXT NOT NULL, session_id TEXT NOT NULL, PRIMARY KEY(incident_id, session_id));
CREATE TABLE IF NOT EXISTS recovery_outbox (
    id TEXT PRIMARY KEY, incident_id TEXT NOT NULL, root_id TEXT NOT NULL, route TEXT NOT NULL,
    kind TEXT NOT NULL, content TEXT NOT NULL, state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
    created REAL NOT NULL, updated REAL NOT NULL, UNIQUE(incident_id, kind));
CREATE TABLE IF NOT EXISTS native_actions (
    nonce TEXT PRIMARY KEY, request TEXT NOT NULL, response TEXT NOT NULL, incident_id TEXT NOT NULL);
"""


class NativeLedger:
    def __init__(self, store):
        self.store, self.db = store, store.db

    def _count(self, sql, args=()):
        return self.db.execute(sql, args).fetchone()[0]

    def _capacity(self, sql, limit, label, args=()):
        if self._count(sql, args) >= limit:
            raise Rejected(f"Native {label} capacity reached ({limit}); observation is incomplete")

    def degrade(self, reason, session=None):
        # Reason is plugin-authored metadata, never a caught exception's payload.
        with self.store.transaction():
            self.db.execute("INSERT OR REPLACE INTO native_meta VALUES('degraded', ?)", (reason,))
            if session:
                self.db.execute("UPDATE native_runs SET gap=? WHERE session_id=?", (reason, session))

    def start(self, parent, child, route, *, nested=False, goal: object = None):
        from .presentation import task_label

        label, label_excerpt = task_label(goal)
        identity(parent)
        identity(child)
        bounded_text(route, "origin route", 256, empty=True)
        if parent == child:
            raise Rejected("Native ancestry is cyclic")
        with self.store.transaction():
            existing = self.db.execute("SELECT parent_id FROM native_runs WHERE session_id=?", (child,)).fetchone()
            if existing:
                if existing[0] != parent:
                    raise Rejected("Conflicting native parent identity")
                return
            ancestor = self.db.execute("SELECT root_id FROM native_runs WHERE session_id=?", (parent,)).fetchone()
            root = ancestor[0] if ancestor else parent
            if root == child:
                raise Rejected("Native ancestry is cyclic")
            if nested and not ancestor:
                route = ""  # Missing ancestry is not authority to route to a guessed root.
            owner = self.db.execute("SELECT * FROM native_roots WHERE root_id=?", (root,)).fetchone()
            if owner and owner["deleted"]:
                raise Rejected("Native origin was deleted or reset")
            self._capacity("SELECT count(*) FROM native_runs", ROWS_MAX, "run history")
            self._capacity(
                "SELECT count(*) FROM native_runs WHERE state NOT IN ('returned','failed','interrupted')",
                NATIVE_ACTIVE_MAX,
                "tracked work",
            )
            now = self.store.clock()
            if not owner:
                self._capacity("SELECT count(*) FROM native_roots", ROOTS_MAX, "root history")
                self.db.execute(
                    "INSERT INTO native_roots(root_id,route,route_active,created) VALUES(?,?,?,?)",
                    (root, route, bool(route), now),
                )
            elif not ancestor and route:
                if owner["route"] and owner["route"] != route:
                    raise Rejected("Conflicting native origin route")
                self.db.execute("UPDATE native_roots SET route=?,route_active=1 WHERE root_id=?", (route, root))
            self.db.execute(
                "INSERT INTO native_runs(session_id,parent_id,root_id,state,created,updated,gap,label,label_excerpt) "
                "VALUES(?,?,?,'active',?,?,?,?,?)",
                (
                    child,
                    parent,
                    root,
                    now,
                    now,
                    "Missing ancestor identity" if nested and not ancestor else "",
                    label,
                    label_excerpt,
                ),
            )

    def has_run(self, session):
        with self.store.lock:
            return bool(self.db.execute("SELECT 1 FROM native_runs WHERE session_id=?", (session,)).fetchone())

    def _incident(self, root, kind, signature, sessions, *, notices=False):
        row = self.db.execute(
            "SELECT * FROM incidents WHERE root_id=? AND kind=? AND signature=?", (root, kind, signature)
        ).fetchone()
        now = self.store.clock()
        if row:
            incident = dict(row)
            self.db.execute("UPDATE incidents SET updated=?,revision=revision+1 WHERE id=?", (now, incident["id"]))
        else:
            self._capacity("SELECT count(*) FROM incidents", ROWS_MAX, "incident history")
            self._capacity("SELECT count(*) FROM incidents WHERE status='open'", OPEN_MAX, "open attention")
            incident = {
                "id": "wi_" + uuid.uuid4().hex[:16],
                "root_id": root,
                "kind": kind,
                "signature": signature,
                "status": "open",
            }
            self.db.execute(
                "INSERT INTO incidents VALUES(?,?,?,?, 'open',1,?,?)", (incident["id"], root, kind, signature, now, now)
            )
        for session in sessions:  # At most ROWS_MAX candidate workers.
            self.db.execute("INSERT OR IGNORE INTO incident_members VALUES(?,?)", (incident["id"], session))
            if kind == "related_failures":
                self.db.execute(
                    "UPDATE incidents SET status='grouped',revision=revision+1 WHERE root_id=? AND kind='worker_failed' AND status='open' AND id IN (SELECT incident_id FROM incident_members WHERE session_id=?)",
                    (root, session),
                )
        if not row and notices:
            self._enqueue(
                incident,
                "opening",
                f"Watchdog: {kind.replace('_', ' ')} in this conversation. Open the Watchdog inbox to inspect incident {incident['id']}. No automatic retry was requested.",
                required=False,
            )
        return incident

    def record(self, session, key, event, *, parent=None, notices=False):
        with self.store.transaction():
            run = self.db.execute("SELECT * FROM native_runs WHERE session_id=?", (session,)).fetchone()
            if not run:
                return
            if parent is not None and parent != run["parent_id"]:
                raise Rejected("Completion parent does not match observed ancestry")
            if self.db.execute("SELECT 1 FROM native_seen WHERE session_id=? AND key=?", (session, key)).fetchone():
                return
            self._capacity(
                "SELECT count(*) FROM native_seen WHERE session_id=?", IDENTITIES_MAX, "event identities", (session,)
            )
            self.db.execute("INSERT INTO native_seen VALUES(?,?)", (session, key))
            now, seq = self.store.clock(), run["seq"] + 1
            self.db.execute(
                "INSERT INTO native_evidence VALUES(?,?,?,?,?)",
                (session, seq, now, event.get("fingerprint", ""), json.dumps(event)),
            )
            self.db.execute("DELETE FROM native_evidence WHERE session_id=? AND seq<=?", (session, seq - EVIDENCE_MAX))
            self.db.execute(
                "UPDATE native_runs SET seq=?,updated=?,gap=CASE WHEN ?!='' THEN ? ELSE gap END WHERE session_id=?",
                (seq, now, event.get("gap", ""), event.get("gap", ""), session),
            )
            kind, root = event["kind"], run["root_id"]
            deleted = self.db.execute("SELECT deleted FROM native_roots WHERE root_id=?", (root,)).fetchone()[0]
            if deleted:
                if kind == "subagent_stop":
                    self.db.execute("UPDATE native_runs SET state=? WHERE session_id=?", (event["state"], session))
                return
            if kind == "post_tool_call" and event.get("fingerprint"):
                rows = self.db.execute(
                    "SELECT e.session_id,count(*) AS calls FROM native_evidence e JOIN native_runs r USING(session_id) WHERE r.root_id=? AND e.fingerprint=? AND e.created>=? GROUP BY e.session_id LIMIT ?",
                    (root, event["fingerprint"], now - WINDOW_SECONDS, ROWS_MAX),
                ).fetchall()
                if related(rows):
                    self._incident(
                        root, "related_failures", event["fingerprint"], {r[0] for r in rows}, notices=notices
                    )
            elif kind == "on_human_input_request":
                # A resolution can arrive first on concurrent host dispatch. Its
                # tombstone must keep a late request from recreating a wait.
                resolved_key = event.get("resolved_key")
                resolved = (
                    resolved_key
                    and self.db.execute(
                        "SELECT 1 FROM native_seen WHERE session_id=? AND key=?", (session, resolved_key)
                    ).fetchone()
                )
                if not resolved and run["state"] not in SETTLED:
                    self._incident(root, "human_input", digest(session, event["request"]), [session], notices=notices)
            elif kind == "on_human_input_resolved":
                rows = self.db.execute(
                    "SELECT * FROM incidents WHERE root_id=? AND kind='human_input' AND signature=?",
                    (root, digest(session, event["request"])),
                ).fetchall()
                self._resolve(rows, "resolved", notices)
            elif kind == "subagent_stop":
                self.db.execute("UPDATE native_runs SET state=? WHERE session_id=?", (event["state"], session))
                rows = self.db.execute(
                    "SELECT i.* FROM incidents i JOIN incident_members m ON i.id=m.incident_id WHERE m.session_id=? AND i.kind='human_input' AND i.status IN ('open','acknowledged','follow_up_requested')",
                    (session,),
                ).fetchall()
                self._resolve(rows, "ended", notices)
                grouped = self.db.execute(
                    "SELECT 1 FROM incidents i JOIN incident_members m ON i.id=m.incident_id WHERE m.session_id=? AND i.kind='related_failures' LIMIT 1",
                    (session,),
                ).fetchone()
                if event["state"] in {"failed", "interrupted"} and not grouped:
                    self._incident(root, "worker_" + event["state"], digest(session), [session])

    def _resolve(self, rows, state, notices):
        for row in rows:  # Bounded by OPEN_MAX unresolved waits.
            if row["status"] not in ATTENTION:
                continue
            self.db.execute(
                "UPDATE incidents SET status=?,revision=revision+1,updated=? WHERE id=?",
                (state, self.store.clock(), row["id"]),
            )
            self.db.execute(
                "UPDATE recovery_outbox SET state='withdrawn' WHERE incident_id=? AND kind='opening' AND state='pending'",
                (row["id"],),
            )
            # Resolution notices are useful only if an opening was accepted.
            opening = self.db.execute(
                "SELECT 1 FROM recovery_outbox WHERE incident_id=? AND kind='opening' AND state='accepted'",
                (row["id"],),
            ).fetchone()
            if notices and opening:
                self._enqueue(
                    row,
                    "resolution",
                    f"Watchdog: the human wait for {row['id']} {state}. This does not establish that the task succeeded.",
                    required=False,
                )

    def _enqueue(self, incident, kind, content, *, required=True):
        existing = self.db.execute(
            "SELECT id FROM recovery_outbox WHERE incident_id=? AND kind=?", (incident["id"], kind)
        ).fetchone()
        if existing:
            return existing[0]
        owner = self.db.execute("SELECT * FROM native_roots WHERE root_id=?", (incident["root_id"],)).fetchone()
        available = owner and owner["route"] and owner["route_active"] and not owner["deleted"]
        capacity = (
            self._count("SELECT count(*) FROM recovery_outbox WHERE state IN ('pending','sending','unknown')")
            < OUTBOX_MAX
        )
        if not available or not capacity:
            if required:
                raise Rejected("Recovery route is unavailable or delivery capacity is full")
            self.db.execute(
                "INSERT OR REPLACE INTO native_meta VALUES('notice_gap', 'A native notice could not be queued; inspect the inbox')"
            )
            return None
        bounded_text(content, "recovery brief", 4096)
        oid = "wo_" + uuid.uuid4().hex[:16]
        now = self.store.clock()
        self.db.execute(
            "INSERT INTO recovery_outbox(id,incident_id,root_id,route,kind,content,state,created,updated) VALUES(?,?,?,?,?,?,'pending',?,?)",
            (oid, incident["id"], incident["root_id"], owner["route"], kind, content, now, now),
        )
        return oid

    def withdraw(self, root, *, deleted=False):
        with self.store.transaction():
            self.db.execute(
                "UPDATE native_roots SET route_active=0,deleted=max(deleted,?) WHERE root_id=?", (deleted, root)
            )
            # A host call already entered is not recallable. Never claim it was.
            self.db.execute(
                "UPDATE recovery_outbox SET state='withdrawn',updated=? WHERE root_id=? AND state='pending'",
                (self.store.clock(), root),
            )
            if deleted:
                self.db.execute(
                    "UPDATE incidents SET status='withdrawn',revision=revision+1 WHERE root_id=? AND status IN ('open','acknowledged','follow_up_requested')",
                    (root,),
                )

    def recover(self):
        with self.store.transaction():
            self.db.execute(
                "UPDATE native_runs SET state='unknown',gap='Host restarted; live execution ownership is unknown' WHERE state='active'"
            )
            self.db.execute("UPDATE recovery_outbox SET state='unknown' WHERE state='sending'")

    def detail(self, incident_id):
        with self.store.lock:
            row = self.db.execute(
                "SELECT i.*, r.route_active,r.deleted,r.route!='' AS route_known FROM incidents i JOIN native_roots r ON i.root_id=r.root_id WHERE i.id=?",
                (incident_id,),
            ).fetchone()
            if row is None:
                raise Rejected("Incident not found in this profile")
            item = dict(row)
            item.pop("signature")
            item["parent_session_id"] = item["root_id"]
            item["members"] = [
                self.run(r[0])
                for r in self.db.execute(
                    "SELECT session_id FROM incident_members WHERE incident_id=? ORDER BY session_id LIMIT ?",
                    (incident_id, ROWS_MAX),
                ).fetchall()
            ]
            item["execution_unknown"] = any(member["state"] == "unknown" for member in item["members"])
            item["delivery"] = [
                dict(r)
                for r in self.db.execute(
                    "SELECT id,kind,state,attempts,created,updated FROM recovery_outbox WHERE incident_id=? ORDER BY created LIMIT 3",
                    (incident_id,),
                ).fetchall()
            ]
            item["recovery_available"] = bool(
                item["route_known"]
                and item["route_active"]
                and not item["deleted"]
                and item["status"] in ATTENTION
                and not any(r["kind"] == "recovery" for r in item["delivery"])
            )
            return item

    def run(self, session, *, evidence=False):
        with self.store.lock:
            row = self.db.execute("SELECT * FROM native_runs WHERE session_id=?", (session,)).fetchone()
            if row is None:
                raise Rejected("Native worker not found in this profile")
            item = dict(row)
            item["waiting"] = (
                bool(
                    self._count(
                        "SELECT count(*) FROM incidents i JOIN incident_members m ON i.id=m.incident_id WHERE m.session_id=? AND i.kind='human_input' AND i.status IN ('open','acknowledged','follow_up_requested')",
                        (session,),
                    )
                )
                and item["state"] == "active"
            )
            item["retained_from"] = max(1, item["seq"] - EVIDENCE_MAX + 1)
            if evidence:
                item["evidence"] = [
                    dict(seq=r["seq"], at=r["created"], **json.loads(r["data"]))
                    for r in self.db.execute(
                        "SELECT * FROM native_evidence WHERE session_id=? ORDER BY seq LIMIT ?", (session, EVIDENCE_MAX)
                    ).fetchall()
                ]
            return item

    def page(self, *, cursor="", limit=PAGE_MAX, root=None, runs=False, view="all"):
        if type(limit) is not int or not 1 <= limit <= PAGE_MAX:
            raise Rejected("Native page size must be between 1 and 50")
        bounded_text(cursor, "cursor", 256, empty=True)
        filters = {
            "all": "1",
            "returned": "state='returned'",
            "related": "kind='related_failures'",
            "needs": "(kind='human_input' AND status IN ('open','acknowledged','follow_up_requested') OR kind IN ('worker_failed','worker_interrupted') AND status='open')",
        }
        if view not in ({"all", "returned"} if runs else {"all", "related", "needs"}):
            raise Rejected("Unsupported inbox view")
        with self.store.lock:
            table, key = ("native_runs", "session_id") if runs else ("incidents", "id")
            rows = self.db.execute(
                f"SELECT {key} FROM {table} WHERE {key}>? AND (? IS NULL OR root_id=?) AND ({filters[view]}) ORDER BY {key} LIMIT ?",
                (cursor, root, root, limit + 1),
            ).fetchall()
            items = [self.run(r[0]) if runs else self.detail(r[0]) for r in rows[:limit]]
            # List responses omit member detail; each worker is available separately.
            if not runs:
                for item in items:
                    item["worker_count"] = len(item.pop("members"))
            return {
                "runs" if runs else "incidents": items,
                "next_cursor": rows[limit - 1][0] if len(rows) > limit else None,
                "health": dict(self.db.execute("SELECT key,value FROM native_meta LIMIT 4").fetchall()),
            }

    def action(self, iid, action, parent, revision, nonce):
        if action not in {"acknowledge", "request_recovery_review"}:
            raise Rejected("Unsupported incident action")
        bounded_text(nonce, "idempotency key", 80)
        if len(nonce) < 8 or type(revision) is not int or revision < 1:
            raise Rejected("Invalid action identity or revision")
        with self.store.transaction():
            item = self.detail(iid)
            if parent != item["root_id"]:
                raise Rejected("Incident does not belong to this conversation")
            request = digest(iid, action, parent, revision)
            prior = self.db.execute("SELECT request,response FROM native_actions WHERE nonce=?", (nonce,)).fetchone()
            if prior:
                if prior["request"] != request:
                    raise Rejected("Idempotency key was used for a different action")
                return json.loads(prior["response"])
            if revision != item["revision"]:
                raise Rejected("Incident changed; refresh before acting")
            if item["deleted"] or item["status"] not in ATTENTION:
                raise Rejected("Incident no longer needs this action")
            self._capacity("SELECT count(*) FROM native_actions", ROWS_MAX * 2, "action history")
            response = {"incident_id": iid, "action": action}
            if action == "request_recovery_review":
                runs = self.db.execute(
                    "SELECT * FROM native_runs WHERE root_id=? ORDER BY session_id LIMIT ?", (parent, ROWS_MAX)
                ).fetchall()
                response["outbox_id"] = self._enqueue(item, "recovery", recovery_brief(item, runs))
                status = "follow_up_requested"
            else:
                if item["kind"] == "human_input":
                    raise Rejected("Answer human-input requests in the original conversation")
                status = "acknowledged"
            self.db.execute(
                "UPDATE incidents SET status=?,revision=revision+1,updated=? WHERE id=?",
                (status, self.store.clock(), iid),
            )
            self.db.execute("INSERT INTO native_actions VALUES(?,?,?,?)", (nonce, request, json.dumps(response), iid))
            return response

    def prune(self):
        # Delete whole settled roots, preserving ancestry, idempotency tombstones,
        # ambiguous sends, and unresolved attention until explicitly handled.
        cutoff = self.store.clock() - 7 * 86400
        with self.store.transaction():
            roots = self.db.execute(
                "SELECT root_id FROM native_roots WHERE created<? LIMIT ?", (cutoff, ROOTS_MAX)
            ).fetchall()
            for (root,) in roots:
                if self._count(
                    "SELECT count(*) FROM native_runs WHERE root_id=? AND (state NOT IN ('returned','failed','interrupted') OR updated>=?)",
                    (root, cutoff),
                ):
                    continue
                if self._count(
                    "SELECT count(*) FROM incidents WHERE root_id=? AND (status IN ('open','follow_up_requested') OR updated>=?)",
                    (root, cutoff),
                ):
                    continue
                if self._count(
                    "SELECT count(*) FROM recovery_outbox WHERE root_id=? AND state IN ('pending','sending','unknown')",
                    (root,),
                ):
                    continue
                for table in ("native_evidence", "native_seen"):
                    self.db.execute(
                        f"DELETE FROM {table} WHERE session_id IN (SELECT session_id FROM native_runs WHERE root_id=?)",
                        (root,),
                    )
                for table in ("native_actions", "incident_members"):
                    self.db.execute(
                        f"DELETE FROM {table} WHERE incident_id IN (SELECT id FROM incidents WHERE root_id=?)", (root,)
                    )
                for table in ("recovery_outbox", "incidents", "native_runs", "native_roots"):
                    self.db.execute(f"DELETE FROM {table} WHERE {'root_id'}=?", (root,))
