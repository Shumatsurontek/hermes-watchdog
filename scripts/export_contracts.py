"""Export the backend's response contracts without a running Hermes profile."""

import argparse
import json
import sys
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--hermes-source")
a = p.parse_args()
if a.hermes_source:
    sys.path.insert(0, a.hermes_source)
    import hermes_bootstrap  # noqa: F401
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from watchdog.views import ActionResult, CancelResult, HistoryPage, WorkerDetail, WorkPage

folder = Path(__file__).resolve().parents[1] / "desktop/generated"
for model in (WorkPage, WorkerDetail, HistoryPage, ActionResult, CancelResult):
    schema = model.model_json_schema()
    schema["$id"] = model.__name__
    (folder / (model.__name__ + ".schema.json")).write_text(json.dumps(schema, indent=2) + "\n")
