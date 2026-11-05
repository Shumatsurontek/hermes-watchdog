"""Run deterministic tests and optionally write the BB Tests JSON report."""

import argparse
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class Report(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rows = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.rows.append({"name": test.id(), "status": "passed"})

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.rows.append({"name": test.id(), "status": "failed", "message": self._exc_info_to_string(err, test)})

    def addError(self, test, err):
        super().addError(test, err)
        self.rows.append({"name": test.id(), "status": "failed", "message": self._exc_info_to_string(err, test)})

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.rows.append({"name": test.id(), "status": "skipped", "message": reason})


p = argparse.ArgumentParser()
p.add_argument("--report")
a = p.parse_args()
suite = unittest.defaultTestLoader.discover(str(Path(__file__).resolve().parents[1] / "tests"))
result = unittest.TextTestRunner(verbosity=2, resultclass=Report).run(suite)
if a.report:
    Path(a.report).write_text(json.dumps(result.rows, indent=2) + "\n")
raise SystemExit(not result.wasSuccessful())
