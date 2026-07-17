import os
import tempfile
import unittest
from pathlib import Path

from governance import assess
from foundry import CapabilityFoundry
from platform_store import PlatformStore
from registry import Tool, ToolRegistry
from sandbox import SandboxError, SandboxProfile, container_command, execute


SOURCE = "def run(payload):\n    return {'ok': payload['value']}\n"


class ProductionControlTests(unittest.TestCase):
    def test_container_command_has_no_egress_or_host_mount(self):
        command = container_command(SandboxProfile("container", image="forgeagent-sandbox:test"))
        self.assertEqual(command[:5], ["docker", "run", "--rm", "-i", "--network"])
        self.assertIn("none", command)
        self.assertIn("--read-only", command)
        self.assertIn("--cap-drop", command)
        self.assertIn("ALL", command)
        self.assertIn("no-new-privileges", command)
        self.assertNotIn("-v", command)
        self.assertNotIn("--volume", command)

    def test_strict_mode_refuses_local_execution(self):
        previous = os.environ.get("FORGEAGENT_REQUIRE_CONTAINER")
        os.environ["FORGEAGENT_REQUIRE_CONTAINER"] = "1"
        try:
            with self.assertRaises(SandboxError):
                execute(SOURCE, {"value": "safe"}, profile=SandboxProfile("local"))
        finally:
            if previous is None:
                os.environ.pop("FORGEAGENT_REQUIRE_CONTAINER", None)
            else:
                os.environ["FORGEAGENT_REQUIRE_CONTAINER"] = previous

    def test_production_policy_holds_even_safe_candidate_for_human(self):
        decision = assess("production", "normalizer", "curated proposal", {"passed": True, "trust_score": 100})
        self.assertEqual(decision.decision, "pending")
        self.assertTrue(decision.requires_human)

    def test_policy_findings_are_rejected(self):
        decision = assess("production", "normalizer", "curated proposal", {"passed": False, "policy_findings": ["disallowed import: os"]})
        self.assertEqual(decision.decision, "rejected")

    def test_receipt_has_integrity_hash_and_human_reason_is_required(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PlatformStore(Path(directory) / "foundry.sqlite3")
            record = store.promote("production/a", "normalizer", SOURCE, "curated", {"passed": True, "trust_score": 100}, policy="production")
            self.assertEqual(record.state, "pending")
            receipt = store.receipt("production/a")
            self.assertEqual(len(str(receipt["integrity_sha256"])), 64)
            with self.assertRaises(ValueError):
                store.decide(record.id, "approved", "A", "ok")
            self.assertEqual(store.decide(record.id, "approved", "alice", "validated proof evidence").state, "trusted")

    def test_production_policy_does_not_silently_reuse_legacy_skill(self):
        with tempfile.TemporaryDirectory() as directory:
            registry_path = Path(directory) / "skills.json"
            registry = ToolRegistry(registry_path)
            registry.register(Tool("date_format_normalizer", "test", SOURCE, {"value": "safe"}, {"ok": "safe"}, ToolRegistry.timestamp()))
            foundry = CapabilityFoundry(registry_path, root=Path(directory))
            outcome = foundry.run("Normalize inconsistent date formats in this import log", {"value": "safe"}, approval_policy="production")
            self.assertEqual(outcome["status"], "pending")
            self.assertIsNone(outcome["result"])
