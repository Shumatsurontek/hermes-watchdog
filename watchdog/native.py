"""Passive adapter for public Hermes hooks; no executor or native handle claims."""

import logging

from .incidents import normalize
from .policy import Rejected

log = logging.getLogger(__name__)
EVENTS = frozenset({"post_tool_call", "subagent_stop", "on_human_input_request", "on_human_input_resolved"})


class NativeObserver:
    def __init__(self, ledger, *, enabled=True, notices=False):
        self.ledger, self.enabled, self.notices = ledger, enabled, notices
        self.failure = ""

    def observe(self, kind, data, *, surface="", bound_id="", bound_key="", legacy=False):
        if legacy or (not self.enabled and kind not in {"on_session_delete", "on_session_reset", "on_session_end"}):
            return
        session = (
            data.get("child_session_id") if kind in {"subagent_start", "subagent_stop"} else data.get("session_id")
        )
        if kind == "on_session_reset":
            session = data.get("old_session_id") or session
        try:
            if kind in {"on_session_delete", "on_session_reset"}:
                if session:
                    self.ledger.withdraw(session, deleted=True)
            elif kind == "on_session_end" and data.get("interrupted") is True:
                if session:
                    self.ledger.withdraw(session)
            elif kind == "subagent_start":
                parent = data.get("parent_session_id")
                # Gate first-level discovery on Desktop. Nested identity comes
                # from the stored ancestry, never from a guessed route prefix.
                if surface != "desktop" and not self.ledger.has_run(parent):
                    return
                route = bound_key if surface == "desktop" and bound_id == parent else ""
                self.ledger.start(parent, session, route, nested=bool(data.get("parent_subagent_id")))
            elif kind in EVENTS and session and self.ledger.has_run(session):
                key, event = normalize(kind, data)
                self.ledger.record(
                    session,
                    key,
                    event,
                    parent=data.get("parent_session_id") if kind == "subagent_stop" else None,
                    notices=self.notices,
                )
        except Exception as exc:
            self.failure = (
                str(exc) if isinstance(exc, Rejected) else "Native observer storage failure; inspect host logs"
            )
            log.warning("Watchdog native observation degraded (%s)", type(exc).__name__)
            try:
                self.ledger.degrade(self.failure, session)
            except Exception:
                log.exception("Watchdog could not persist native observation failure")
