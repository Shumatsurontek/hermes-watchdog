"""Bounded local SQLite observer timing; not a provider/usefulness benchmark."""

import argparse
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from watchdog.native import NativeObserver
from watchdog.store import Store

p = argparse.ArgumentParser()
p.add_argument("--output", required=True)
a = p.parse_args()
rows = []
with tempfile.TemporaryDirectory() as tmp:
    store = Store.local(Path(tmp) / "timing.db")
    store.db.execute("PRAGMA journal_mode=WAL")
    observer = NativeObserver(store.native)
    for child in ("a", "b"):
        store.native.start("root", child, "route")
    for mode in ("ok", "error"):
        elapsed = []
        for n in range(300):
            before = time.perf_counter()
            observer.observe(
                "post_tool_call",
                {
                    "session_id": "a" if n % 2 else "b",
                    "turn_id": mode,
                    "tool_call_id": str(n),
                    "tool_name": "fixture_read",
                    "status": mode,
                    "error_message": "Controlled fixture failure" if mode == "error" else "",
                },
            )
            elapsed.append((time.perf_counter() - before) * 1000)
        assert not observer.failure, observer.failure
        rows.append(
            {
                "name": mode,
                "samples": len(elapsed),
                "median_ms": statistics.median(elapsed),
                "p95_ms": sorted(elapsed)[284],
                "max_ms": max(elapsed),
            }
        )
    report = {
        "scope": "Local WAL SQLite, two workers, 600 synchronous hook calls; no provider",
        "results": rows,
        "model_calls": 0,
        "target_p95_ms": 5,
        "target_met": all(row["p95_ms"] < 5 for row in rows),
    }
    Path(a.output).write_text(json.dumps(report, indent=2) + "\n")
    store.close()
    print(json.dumps(report))
