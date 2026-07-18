import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path

from forgeagent.platform_store import PlatformStore


class PlatformStoreTests(unittest.TestCase):
    def test_namespace_import_approval_and_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PlatformStore(Path(directory) / "foundry.sqlite3")
            proof = {"passed": True, "trust_score": 95}
            record = store.promote("team/a", "normalizer", "def run(payload): return payload", "test", proof)
            self.assertEqual(record.state, "trusted")
            self.assertEqual(store.rollback(record.id, "reviewer", "regression").state, "rolled_back")


@unittest.skipUnless(importlib.util.find_spec("cryptography"), "optional cryptography dependency is not installed")
class CapabilityPackageSigningTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = PlatformStore(Path(self.directory.name) / "foundry.sqlite3")
        self.record = self.store.promote(
            "team/a", "normalizer", "def run(payload): return payload", "test",
            {"passed": True, "trust_score": 95},
        )
        self.keys = PlatformStore.generate_signing_keypair()

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def package(self, compatibility=None):
        return self.store.export_package(
            self.record.id, self.keys["private_key_pem"],
            compatibility=compatibility,
        )

    def test_tampered_payload_is_rejected(self):
        package = copy.deepcopy(self.package())
        package["payload"]["capability"]["source"] = "def run(payload): return 'tampered'"

        with self.assertRaisesRegex(ValueError, "invalid package signature"):
            self.store.import_package(package, self.keys["public_key_pem"], "team/b")

    def test_revoked_signer_key_is_rejected_even_with_valid_signature(self):
        package = self.package()
        key_id = package["payload"]["signer"]["key_id"]

        with self.assertRaisesRegex(ValueError, "revoked signer key"):
            self.store.import_package(package, self.keys["public_key_pem"], "team/b", revoked_key_ids={key_id})

    def test_incompatible_schema_is_rejected_with_clear_reason(self):
        package = self.package({"min_schema_version": 3, "max_schema_version": 3})

        with self.assertRaisesRegex(ValueError, "incompatible package schema"):
            self.store.import_package(package, self.keys["public_key_pem"], "team/b")

    def test_valid_package_imports_into_review_state(self):
        package = self.package()

        imported = self.store.import_package(package, self.keys["public_key_pem"], "team/b")

        self.assertEqual(imported.state, "pending")
