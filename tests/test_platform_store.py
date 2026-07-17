import tempfile
import unittest
from pathlib import Path
from platform_store import PlatformStore

class PlatformStoreTests(unittest.TestCase):
    def test_namespace_approval_receipt_and_signed_marketplace_package(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PlatformStore(Path(directory) / "p.sqlite3")
            cap = store.promote("team/a", "text_normalizer", "def run(p): return p", "curated", [({}, {}, True), ({}, {}, True)])
            self.assertEqual(cap.state, "trusted")
            package = store.export_package(cap.id, "shared-key")
            imported = PlatformStore(Path(directory) / "q.sqlite3").import_package(package, "shared-key", target_project="team/b")
            self.assertEqual(imported.state, "pending")
            self.assertEqual(imported.project_id, "team/b")
            self.assertEqual(store.receipt("team/a")["capabilities"][0]["name"], "text_normalizer")

    def test_sensitive_capability_requires_review_and_can_be_rolled_back(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PlatformStore(Path(directory) / "p.sqlite3")
            cap = store.promote("team/a", "security_redactor", "def run(p): return p", "test", [({}, {}, True)])
            self.assertEqual(cap.state, "pending")
            approved = store.decide(cap.id, "approved", "reviewer@example.com", "reviewed test evidence")
            self.assertEqual(approved.state, "trusted")
            rolled_back = store.rollback(approved.id, "reviewer@example.com", "regression report")
            self.assertEqual(rolled_back.state, "rolled_back")
