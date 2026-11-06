"""Single profile-owned delivery pump. A host acceptance is not observed delivery."""

import logging
import threading

from .incidents import DELIVERY_ATTEMPTS_MAX

log = logging.getLogger(__name__)
TICK_SECONDS = 5


class RecoveryOutbox:
    def __init__(self, store, ctx):
        self.store, self.ctx = store, ctx
        self.stopping = threading.Event()
        self.thread = None
        self.delivery_lock = threading.Lock()

    def start(self):
        assert self.thread is None, "One delivery pump per runtime"
        self.thread = threading.Thread(target=self._run, name="watchdog-recovery", daemon=True)
        self.thread.start()

    def _run(self):
        # Host-lifetime server loop: one thread, no queued executor jobs, one
        # synchronous host call in flight. A hung call cannot spawn another.
        while not self.stopping.wait(TICK_SECONDS):
            try:
                self.tick()
            except Exception:
                log.exception("Watchdog recovery pump failed; no ambiguous send is retried")
                try:
                    self.store.native.degrade("Recovery delivery failed; inspect host logs")
                except Exception:
                    log.exception("Watchdog could not persist recovery degradation")

    def tick(self):
        # The public host contract reports 'cli' whenever the classic REPL is
        # attached. That transport ignores explicit session keys; never dispatch
        # a persisted Desktop request into it after a profile is reopened there.
        if self.ctx.session_surface() not in {"", "desktop"}:
            return
        if self.stopping.is_set() or not self.delivery_lock.acquire(blocking=False):
            return
        try:
            # One row per tick is stricter than the 32-row / five-second budget.
            with self.store.transaction():
                row = self.store.db.execute(
                    "SELECT o.* FROM recovery_outbox o JOIN native_roots r ON o.root_id=r.root_id WHERE o.state='pending' AND r.deleted=0 AND r.route_active=1 AND o.route=r.route AND o.attempts<? ORDER BY o.updated,o.id LIMIT 1",
                    (DELIVERY_ATTEMPTS_MAX,),
                ).fetchone()
                if not row:
                    return
                self.store.db.execute(
                    "UPDATE recovery_outbox SET state='sending',attempts=attempts+1,updated=? WHERE id=?",
                    (self.store.clock(), row["id"]),
                )
            # Once claimed, delivery has begun. Delete/reset can withdraw queued
            # messages, but cannot recall a host call which already entered.
            try:
                accepted = self.ctx.inject_message(row["content"], role="user", session_key=row["route"])
                if accepted is not True and accepted is not False:
                    accepted = None
            except Exception:
                accepted = None
                log.exception("Watchdog recovery acceptance is unknown")
            with self.store.transaction():
                state = (
                    "accepted"
                    if accepted is True
                    else "unknown"
                    if accepted is None
                    else "failed"
                    if row["attempts"] + 1 >= DELIVERY_ATTEMPTS_MAX
                    else "pending"
                )
                owner = self.store.db.execute(
                    "SELECT route_active,deleted FROM native_roots WHERE root_id=?", (row["root_id"],)
                ).fetchone()
                if state == "pending" and (not owner or owner["deleted"] or not owner["route_active"]):
                    state = "withdrawn"
                self.store.db.execute(
                    "UPDATE recovery_outbox SET state=?,updated=? WHERE id=? AND state='sending'",
                    (state, self.store.clock(), row["id"]),
                )
        finally:
            self.delivery_lock.release()

    def close(self, timeout=2):
        self.stopping.set()
        if self.thread:
            self.thread.join(timeout=max(0, timeout))
        return not self.thread or not self.thread.is_alive()
