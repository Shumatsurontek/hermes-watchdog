"""Pure policy: suspicion is evidence for attention, never proof of termination."""

from dataclasses import dataclass

PLUGIN_ID = "hermes-watchdog"
ACTIVE_MAX = 3
TASKS_PER_SESSION_MAX = 10
TASK_ROWS_MAX = 1000
SESSION_ROWS_MAX = 256
GOAL_BYTES_MAX = 4096
CONTEXT_BYTES_MAX = 8192
RESULT_BYTES_MAX = 128_000
EVENT_BYTES_MAX = 1024
OBSERVATIONS_MAX = 64
EVENTS_MAX = 128
ACTIONS_PENDING_MAX = 32
PAGE_MAX = 50
TICK_SECONDS = 5
TICKS_MAX = 370
QUIET_SECONDS = 120
CANCEL_CONFIRM_SECONDS = 30
NOTICE_ATTEMPTS_MAX = 3
JUDGE_CALLS_MAX = 2
TERMINAL = frozenset({"succeeded", "failed", "interrupted", "cancelled"})


class Rejected(ValueError):
    """Expected policy refusal, safe to show to the operator."""


def bounded_text(value, name, limit, *, empty=False):
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise Rejected(f"{name} must be a {'possibly empty ' if empty else 'nonempty '}string")
    if len(value.encode("utf-8")) > limit:
        raise Rejected(f"{name} exceeds {limit} UTF-8 bytes")
    return value


def excerpt(text, limit):
    raw = str(text or "").encode("utf-8")
    return raw[:limit].decode("utf-8", errors="ignore"), len(raw) > limit


def deadline(value):
    if type(value) is not int or not 10 <= value <= 1800:
        raise Rejected("deadline_seconds must be an integer from 10 to 1800")
    return value


@dataclass(frozen=True)
class Settings:
    enabled: bool = True
    deadline_seconds: int = 900
    judge_enabled: bool = False

    @classmethod
    def read(cls, ctx):
        enabled = ctx.get_config("enabled", True)
        judge = ctx.get_config("judge_enabled", False)
        if type(enabled) is not bool or type(judge) is not bool:
            raise Rejected("enabled and judge_enabled must be booleans")
        if ctx.get_config("preset", "search") != "search":
            raise Rejected("Only the search preset is supported")
        if ctx.get_config("retry_mode", "manual") != "manual":
            raise Rejected("Automatic retries are not supported")
        return cls(enabled, deadline(ctx.get_config("deadline_seconds", 900)), judge)


def assess(attempt, now):
    if attempt["execution"] in TERMINAL:
        return "none", attempt["supervision"]
    if attempt["cancel_at"] is not None:
        if now - attempt["cancel_at"] >= CANCEL_CONFIRM_SECONDS:
            return "stop", "execution_unresolved"
        return "none", attempt["supervision"]
    if attempt["supervision"] in {"evidence_gap", "control_unavailable"}:
        return "none", attempt["supervision"]
    if now >= attempt["deadline_at"]:
        return "cancel", "deadline_exceeded"
    if attempt["waiting"]:
        return "none", "waiting_unknown"
    if attempt["failure_streak"] >= 3 or now - attempt["last_progress_at"] >= QUIET_SECONDS:
        return "judge", "suspected_stall"
    return "none", "healthy"


def retry_reason():
    # This host does not expose an attested effective child tool surface. A label
    # such as "search" cannot rule out inherited MCP tools or side effects.
    return "Retry disabled: Hermes does not attest the effective worker tools or repeat-safe termination."
