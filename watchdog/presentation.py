"""Bounded display metadata. Task excerpts are local UI text, never instructions."""

import re
import unicodedata

LABEL_CHARS_MAX = 160
GOAL_CHARS_MAX = 65_536
# Defense in depth, not a promise that arbitrary task prose contains no secrets.
# Omit URLs, addresses, opaque tokens and common credential assignments entirely.
PRIVATE = re.compile(
    r"https?://\S+|\S+@\S+|\b(?:sk-|ghp_|github_pat_|xox[baprs]-)\S+|"
    r"\b[\w/+\-=]{32,}\b|\b(?:password|token|secret|api[_ -]?key|authorization)\s*[:=]\s*\S+",
    re.IGNORECASE,
)


def task_label(goal: object) -> tuple[str, bool]:
    if not isinstance(goal, str) or not goal.strip() or len(goal) > GOAL_CHARS_MAX:
        return "", False
    first = goal.strip().splitlines()[0]
    clean = " ".join("".join(c for c in first if not unicodedata.category(c).startswith("C")).split())
    clean = PRIVATE.sub("[redacted]", clean)
    excerpt = len(clean) > LABEL_CHARS_MAX or first != goal.strip()
    return clean[:LABEL_CHARS_MAX], excerpt
