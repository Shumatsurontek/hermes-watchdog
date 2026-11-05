"""One bounded context-preserving monitor per active attempt, maximum three."""

import contextvars
import hashlib
import json
import logging
import threading
import time
import uuid

from . import judge as adviser
from .policy import (
    CONTEXT_BYTES_MAX,
    GOAL_BYTES_MAX,
    JUDGE_CALLS_MAX,
    NOTICE_ATTEMPTS_MAX,
    TERMINAL,
    TICK_SECONDS,
    TICKS_MAX,
    Rejected,
    Settings,
    assess,
    bounded_text,
    deadline,
    excerpt,
    retry_reason,
)

log = logging.getLogger(__name__)


class Runtime:
    def __init__(self, ctx, store, *, clock=time.time, tick=TICK_SECONDS, acquire_lock=True):
        self.ctx, self.store, self.clock, self.tick = ctx, store, clock, tick
        self.stop = threading.Event()
        self.lock = threading.RLock()
        self.judge_lock = threading.Lock()
        self.workers = {}
        self.children = {}
        self.launching = contextvars.ContextVar("watchdog_launch", default=None)
        self.degraded = None
        self.owner_file = None
        if acquire_lock:
            # Prevent a second host process from declaring this process's workers
            # lost. The file and lock belong only to this plugin's profile data.
            import fcntl

            from plugins.plugin_storage import plugin_data_dir

            from .policy import PLUGIN_ID

            self.owner_file = (plugin_data_dir(PLUGIN_ID) / "owner.lock").open("a")
            try:
                fcntl.flock(self.owner_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                self.owner_file.close()
                raise Rejected("Watchdog is already active in another host process") from None
        self.store.recover()

    def identity(self):
        from gateway.session_context import get_session_env

        if self.ctx.session_surface() != "desktop":
            raise Rejected("Watchdog currently requires a local Hermes Desktop conversation")
        session = get_session_env("HERMES_SESSION_KEY", "")
        parent = get_session_env("HERMES_SESSION_ID", "")
        if not session or not parent:
            raise Rejected("No durable conversation identity is bound to this call")
        bounded_text(session, "session_key", 256)
        bounded_text(parent, "parent_session_id", 256)
        return session, parent

    def start(self, goal, context="", deadline_seconds=None, preset="search"):
        settings = Settings.read(self.ctx)
        if not settings.enabled or self.stop.is_set():
            raise Rejected("Watchdog is disabled or unloading")
        if self.degraded:
            raise Rejected("Watchdog storage or observation failure; inspect host logs before launching")
        if preset != "search":
            raise Rejected("Only the search preset is supported")
        bounded_text(goal, "goal", GOAL_BYTES_MAX)
        bounded_text(context, "context", CONTEXT_BYTES_MAX, empty=True)
        seconds = deadline(settings.deadline_seconds if deadline_seconds is None else deadline_seconds)
        session, parent = self.identity()
        from agent.subagent_lifecycle import SubagentLaunchRequest, SubagentLifecycleService

        if not isinstance(self.ctx.subagent_lifecycle, SubagentLifecycleService):
            raise Rejected("Watchdog requires the in-process lifecycle service; isolated/remote hosts are unsupported")
        task_id = self.store.reserve(session, parent, goal, context, seconds)
        token = self.launching.set(task_id)
        try:
            handle = self.ctx.subagent_lifecycle.launch(
                SubagentLaunchRequest(
                    goal=goal,
                    context=context or None,
                    role="leaf",
                    model=None,
                    provider=None,
                    allowed_toolsets=("search",),
                    parent_session_id=parent,
                    correlation_id=task_id,
                    metadata={"plugin": "hermes-watchdog", "task_id": task_id},
                )
            )
            if handle.parent_session_id != parent:
                raise Rejected("Host returned an unexpected parent identity")
            _, attempt = self.store.read(task_id)
            self.store.attach(task_id, handle.to_dict(), attempt["child_session"])
            owned = contextvars.copy_context()
            thread = threading.Thread(
                target=owned.run,
                args=(self._monitor, task_id, handle, settings),
                name="watchdog-" + task_id,
                daemon=True,
            )
            with self.lock:
                self.workers[task_id] = thread
            thread.start()
        except Exception as exc:
            # A raised launch can follow child construction: do not assume no work
            # started and do not reclaim its reservation automatically.
            self.store.degrade(task_id, "launch_or_monitor_start_unknown")
            self.store.update(task_id, error_classification=type(exc).__name__)
            log.error("Watchdog launch failed for %s (%s)", task_id, type(exc).__name__)
        finally:
            self.launching.reset(token)
        return self.store.public(task_id)

    def _monitor(self, task_id, handle, settings):
        try:
            for _ in range(TICKS_MAX):
                if not self.step(task_id, handle, settings):
                    break
                self.flush_notices(self.store.read(task_id)[0]["session_key"])
                self.stop.wait(self.tick)
            else:
                self.store.degrade(task_id, "monitor_tick_budget_exhausted")
            # One tick coalesces nearby completions without keeping any model turn
            # open; false acceptance can retry, ambiguous acceptance cannot.
            for _ in range(NOTICE_ATTEMPTS_MAX):
                self.stop.wait(self.tick)
                self.flush_notices(self.store.read(task_id)[0]["session_key"])
                if self.stop.is_set():
                    break
        except Exception as exc:
            self.degraded = type(exc).__name__
            log.exception("Watchdog supervision failed for %s", task_id)
            try:
                self.store.degrade(task_id, "supervisor_or_storage_error", "evidence_gap")
            except Exception:
                log.exception("Watchdog could not persist its degraded state for %s", task_id)
        finally:
            with self.lock:
                self.workers.pop(task_id, None)
                self.children = {child: ident for child, ident in self.children.items() if ident != task_id}

    def step(self, task_id, handle, settings):
        service = self.ctx.subagent_lifecycle
        state = service.status(handle).state.value.lower()
        if state in TERMINAL:
            result = service.result(handle)
            if not result.ready:
                self.store.degrade(task_id, "terminal_without_result", "evidence_gap")
            else:
                self.store.settle(task_id, state, result.summary or result.error_message, result.error_classification)
            return False
        if state == "unknown":
            self.store.degrade(task_id, "parent_context_or_handle_unavailable")
            return False
        if self.degraded:
            self.store.degrade(task_id, "supervisor_degraded", "evidence_gap")
            return False
        task, a = self.store.read(task_id)
        action, supervision = assess(a, self.clock())
        if action == "stop":
            self.store.degrade(task_id, "cancellation_not_confirmed", supervision)
            return False
        requested = self.store.has_cancel(task_id) or task["deleted"] or self.stop.is_set()
        if requested or action == "cancel":
            reason = (
                "parent_deleted"
                if task["deleted"]
                else (
                    "plugin_unloaded"
                    if self.stop.is_set()
                    else ("explicit_cancel" if requested else "deadline_exceeded")
                )
            )
            if self.store.cancel_intent(task_id, reason, supervision):
                reply = service.cancel(handle, reason=reason)
                if not reply.accepted and not reply.already_terminal:
                    self.store.degrade(task_id, "host_did_not_accept_cancellation")
                    return False
            if self.stop.is_set():
                self.store.degrade(task_id, "plugin_unloaded_with_execution_unresolved")
                return False
        elif supervision != a["supervision"]:
            fields = {"supervision": supervision, "reason": supervision}
            if supervision == "suspected_stall":
                fields["notification"] = "pending"
            self.store.update(task_id, **fields)
        if action == "judge" and settings.judge_enabled and a["judge_calls"] < JUDGE_CALLS_MAX:
            self.advise(task_id, handle)
        return True

    def advise(self, task_id, handle):
        if not self.judge_lock.acquire(blocking=False):
            return
        try:
            _, a = self.store.read(task_id)
            if a["judge_calls"] >= JUDGE_CALLS_MAX or a["waiting"] or a["supervision"] == "evidence_gap":
                return
            self.store.update(task_id, judge_calls=a["judge_calls"] + 1)
            try:
                verdict = adviser.judge(self.ctx.llm, a["observations"])
            except Exception as exc:
                self.store.update(task_id, reason="judge_unavailable_" + type(exc).__name__)
                return
            with self.store.transaction():
                self.store._event(task_id, "judge", verdict)
            if verdict["verdict"] == "steer" and a["steers"] == 0:
                # Reserve the steer before calling Hermes; unknown acceptance is
                # never replayed as another intervention after a crash.
                self.store.update(task_id, steers=1)
                accepted = self.ctx.subagent_lifecycle.steer(handle, verdict["message"])
                self.store.update(task_id, reason="steer_accepted" if accepted else "steer_refused")
            elif verdict["verdict"] == "attention":
                self.store.update(task_id, reason="judge_requests_attention", notification="pending")
        finally:
            self.judge_lock.release()

    def flush_notices(self, session):
        if self.stop.is_set():
            return
        items = self.store.claim_notices(session)
        if not items:
            return
        # No worker-supplied text enters this notification. Read results explicitly
        # through watchdog_status, where they remain labelled untrusted data.
        lines = [
            "Watchdog update. Use watchdog_status to inspect results; success means the worker returned, not verified correctness."
        ]
        lines.extend(f"{i['id']}: {i['execution']} ({i['reason']})." for i in items)
        text = "\n".join(lines)
        assert len(text.encode()) <= 2048
        try:
            accepted = self.ctx.inject_message(text, role="user", session_key=session)
            if type(accepted) is not bool:
                accepted = None
        except Exception:
            accepted = None
            log.exception("Watchdog notification acceptance is unknown")
        self.store.finish_notices([i["id"] for i in items], accepted)

    def observe(self, kind, data):
        try:
            if kind == "subagent_start":
                task_id = self.launching.get()
                if task_id is None:
                    return
                task, _ = self.store.read(task_id)
                child = data.get("child_session_id")
                if task["parent_id"] != data.get("parent_session_id") or not child:
                    self.store.degrade(task_id, "subagent_identity_missing", "evidence_gap")
                    return
                self.store.update(task_id, child_session=child)
                with self.lock:
                    self.children[child] = task_id
                return
            if kind == "on_session_finalize":
                # Desktop finalization also fires on disconnect or eviction. It
                # does not prove the durable conversation was deleted.
                return
            if kind in {"on_session_delete", "on_session_reset"}:
                parent = data.get("session_id")
                if parent:
                    self.store.delete_parent(parent)
                return
            with self.lock:
                task_id = self.children.get(data.get("session_id") or data.get("child_session_id"))
            if task_id is None:
                return
            names = {
                "pre_tool_call": "tool_start",
                "post_tool_call": "tool_end",
                "pre_api_request": "api_start",
                "post_api_request": "api_end",
                "api_request_error": "api_error",
                "on_human_input_request": "human_input",
                "subagent_stop": "child_stop",
            }
            item = {"kind": names[kind]}
            if kind in {"pre_tool_call", "post_tool_call"}:
                name = str(data.get("tool_name", ""))
                raw = json.dumps(data.get("args") or {}, sort_keys=True, default=str)
                # Argument contents are deliberately absent from the ledger.
                if len(raw.encode()) > 65_536:
                    self.store.degrade(task_id, "tool_fingerprint_input_exceeds_bound", "evidence_gap")
                    return
                item.update(
                    tool=name[:80],
                    call_id=str(data.get("tool_call_id") or "")[:128],
                    fingerprint=hashlib.sha256((name + raw).encode()).hexdigest(),
                    status=str(data.get("status") or "")[:32],
                )
            self.store.observe(task_id, item)
        except Exception as exc:
            self.degraded = type(exc).__name__
            log.exception("Watchdog observer failed; automatic interventions disabled")
            with self.lock:
                tasks = list(self.workers)
            for task_id in tasks:
                try:
                    self.store.degrade(task_id, "observer_or_storage_error", "evidence_gap")
                except Exception:
                    log.exception("Watchdog could not persist observer failure")

    def status(self, task_id=None):
        session, parent = self.identity()
        if task_id:
            task, _ = self.store.read(task_id)
            if task["session_key"] != session or task["parent_id"] != parent:
                raise Rejected("Task does not belong to the calling conversation")
            result = self.store.public(task_id, detail=True)
            if result["result"]:
                result["result"], clipped = excerpt(result["result"], 16_000)
                result["result_excerpt"] = result["result_excerpt"] or clipped
            result["result_trust"] = "untrusted_worker_output"
            return result
        return self.store.page(session_key=session, limit=10)

    def control(self, task_id, action):
        if action == "request_retry":
            raise Rejected(retry_reason())
        if action != "request_cancel":
            raise Rejected("Unknown action")
        snapshot = self.status(task_id)
        self.store.request_cancel(task_id, snapshot["session_key"], snapshot["revision"], uuid.uuid4().hex)
        return {"task_id": task_id, "action": "cancel_queued"}

    def close(self):
        self.stop.set()
        with self.lock:
            workers = list(self.workers.values())
        end = time.monotonic() + 2
        for worker in workers:
            worker.join(timeout=max(0, end - time.monotonic()))
        if any(t.is_alive() for t in workers):
            # Retain the lock/connection until process exit; a blocked host call
            # must not let a newly loaded plugin double-supervise its children.
            log.error("Watchdog unload could not join all monitors; owner lease retained")
            return
        self.store.close()
        if self.owner_file:
            self.owner_file.close()
