"""Task titles must survive upgrades without copying complete task prompts."""

import tempfile
import unittest
from pathlib import Path

from watchdog.presentation import task_label
from watchdog.store import Store


class PresentationTests(unittest.TestCase):
    def test_title_uses_first_line_and_discloses_excerpt(self):
        label, excerpt = task_label("Release readiness · CI\nPrivate detailed instructions")
        self.assertEqual(label, "Release readiness · CI")
        self.assertTrue(excerpt)
        self.assertEqual(task_label(None), ("", False))
        self.assertEqual(task_label("x" * 65537), ("", False))
        label, excerpt = task_label("a sentence " * 30)
        self.assertEqual(len(label), 160)
        self.assertTrue(excerpt)

    def test_title_redacts_common_credential_shapes_and_invisible_controls(self):
        label, _ = task_label("Check https://user:pass@example.com auth token=secret user@example.com \u202ehidden")
        self.assertNotIn("example.com", label)
        self.assertNotIn("secret", label)
        self.assertNotIn("\u202e", label)
        self.assertIn("[redacted]", label)

    def test_v2_migration_preserves_observation_and_outbox(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "data.db"
            store = Store.local(path)
            store.native.start("root", "worker", "route")
            store.db.execute("ALTER TABLE native_runs DROP COLUMN label")
            store.db.execute("ALTER TABLE native_runs DROP COLUMN label_excerpt")
            store.db.execute("PRAGMA user_version=2")
            store.db.commit()
            before = dict(store.db.execute("SELECT * FROM native_runs").fetchone())
            store.close()
            migrated = Store.local(path)
            self.assertEqual(migrated.db.execute("PRAGMA user_version").fetchone()[0], 3)
            run = migrated.native.run("worker")
            self.assertEqual({k: run[k] for k in before}, before)
            self.assertEqual(run["label"], "")
            migrated.native.start("root", "new", "route", goal="Release readiness · Checks")
            self.assertEqual(migrated.native.run("new")["label"], "Release readiness · Checks")
            migrated.close()
