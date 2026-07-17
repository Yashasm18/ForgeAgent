import tempfile
import unittest
from pathlib import Path

from platform_store import PlatformStore


class PlatformStoreTests(unittest.TestCase):
    def test_namespace_import_approval_and_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PlatformStore(Path(directory) / "foundry.sqlite3")
            proof = {"passed": True, "trust_score": 95}
            record = store.promote("team/a", "normalizer", "def run(payload): return payload", "test", proof)
            self.assertEqual(record.state, "trusted")
            package = store.export_package(record.id, "shared-key")
            imported = store.import_package(package, "shared-key", "team/b")
            self.assertEqual(imported.state, "pending")
            approved = store.decide(imported.id, "approved", "reviewer", "verified")
            self.assertEqual(approved.state, "trusted")
            self.assertEqual(store.rollback(approved.id, "reviewer", "regression").state, "rolled_back")
