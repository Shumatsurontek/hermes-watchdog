"""Metadata-only native evidence. Matching failures are not a root-cause diagnosis."""

import hashlib
import json
import re

from .policy import Rejected, bounded_text

NATIVE_ACTIVE_MAX = 64
ROOTS_MAX = 256
ROWS_MAX = 1000
OPEN_MAX = 32
EVIDENCE_MAX = 64
IDENTITIES_MAX = 4096
INPUT_BYTES_MAX = 65_536
EVENT_BYTES_MAX = 1024
WINDOW_SECONDS = 120
MATCH_COUNT = 3
WORKER_COUNT = 2
BRIEF_BYTES_MAX = 4096
OUTBOX_MAX = 32
DELIVERY_ATTEMPTS_MAX = 3
PAGE_MAX = 50
SETTLED = frozenset({"returned", "failed", "interrupted"})
ATTENTION = frozenset({"open", "acknowledged", "follow_up_requested"})


def digest(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=True).encode()).hexdigest()


def identity(value):
    return bounded_text(value, "event identity", 256)


def normalize(kind, data):
    """Read only bounded scalar fields; never serialize arbitrary hook payloads."""
    event = {"kind": kind}
    if kind == "post_tool_call":
        turn, call = identity(data.get("turn_id")), identity(data.get("tool_call_id"))
        tool = bounded_text(data.get("tool_name"), "tool name", 128)
        if not re.fullmatch(r"[A-Za-z0-9_.:-]+", tool):
            raise Rejected("Unsupported tool name; no grouping attempted")
        status = data.get("status")
        if status not in {"ok", "error", "blocked", "cancelled"}:
            raise Rejected("Missing or unsupported tool outcome")
        event.update(tool=tool, status=status)
        if status == "error":
            error = data.get("error_message")
            if not error:
                result = data.get("result")
                if isinstance(result, str):
                    bounded_text(result, "tool result", INPUT_BYTES_MAX)
                    try:
                        result = json.loads(result)
                    except (ValueError, RecursionError):
                        result = None
                if isinstance(result, dict):
                    error = result.get("error")
            if isinstance(error, str) and error.strip():
                bounded_text(error, "error fingerprint input", INPUT_BYTES_MAX)
                event.update(fingerprint=digest(tool, " ".join(error.split())), classification="unclassified")
            else:
                event["gap"] = "No bounded error text available for matching"
        key = digest(kind, turn, call)
    elif kind in {"on_human_input_request", "on_human_input_resolved"}:
        request = identity(data.get("request_id"))
        event["request"] = digest(request)
        if kind.endswith("request"):
            event["resolved_key"] = digest("on_human_input_resolved", request)
        event["input_kind"] = data.get("kind") if data.get("kind") in {"approval", "clarify", "sudo"} else "human_input"
        if kind.endswith("resolved"):
            # Outcome is display metadata, never permission for the plugin to act.
            event["outcome"] = (
                data.get("outcome")
                if data.get("outcome")
                in {"approved", "denied", "answered", "cancelled", "timeout", "error", "submitted"}
                else "resolved"
            )
        key = digest(kind, request)
    elif kind == "subagent_stop":
        status = data.get("child_status")
        event["state"] = {
            "completed": "returned",
            "failed": "failed",
            "error": "failed",
            "interrupted": "interrupted",
        }.get(status, "unknown")
        if event["state"] == "unknown":
            event["gap"] = "Unrecognized native completion status"
        key = digest(kind)
    else:
        raise Rejected("Unsupported native event")
    assert len(json.dumps(event).encode()) <= EVENT_BYTES_MAX
    return key, event


def related(rows):
    """Caller supplies the exact fingerprint, root, and bounded time window."""
    return sum(row["calls"] for row in rows) >= MATCH_COUNT and len(rows) >= WORKER_COUNT


def recovery_brief(incident, runs):
    # IDs are encoded as data. No goal, result, command, or error text enters an
    # instruction channel. The parent must inspect its original conversation.
    heading = (
        "The user requested a Watchdog recovery review in this conversation. "
        "Inspect the native worker transcripts and current external state before continuing. "
        "Preserve returned work. Check for partial effects before repeating operations. "
        "Propose follow-up or perform only work already authorized; keep Hermes approvals. "
        "Matching failures are unclassified evidence, not a proven shared cause. "
        "A returned worker result is not verified correctness.\n"
    )
    brief = heading + "Incident: " + incident["id"] + " (" + incident["kind"] + ").\n"
    selected = 0
    for run in runs:  # SQL caps this at ROWS_MAX; output selection is explicit.
        line = (
            json.dumps(
                {"worker_session": run["session_id"], "reported_state": run["state"], "evidence_gap": bool(run["gap"])}
            )
            + "\n"
        )
        if len((brief + line).encode()) > BRIEF_BYTES_MAX - 160:
            break
        brief += line
        selected += 1
    brief += f"Selected {selected} of {len(runs)} observed workers. Full metadata is in the local Watchdog inbox.\n"
    assert len(brief.encode()) <= BRIEF_BYTES_MAX
    return brief
