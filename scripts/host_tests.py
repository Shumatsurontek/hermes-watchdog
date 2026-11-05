"""Run API and upstream injection contracts with Hermes's managed dependencies."""

import argparse
import sys
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--hermes-source", required=True)
p.add_argument("--test-deps", required=True)
p.add_argument("--report", required=True)
a = p.parse_args()
sys.path.insert(0, a.hermes_source)
import hermes_bootstrap  # noqa: F401 -- activate host dependencies

sys.path.insert(0, a.test_deps)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest

raise SystemExit(
    pytest.main(
        [
            "-q",
            str(Path(__file__).resolve().parents[1] / "tests"),
            str(Path(a.hermes_source) / "tests/tui_gateway/test_plugin_inject_host.py"),
            "--junitxml=" + a.report,
            "-o",
            "addopts=",
        ]
    )
)
