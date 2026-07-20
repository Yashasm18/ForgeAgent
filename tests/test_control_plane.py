import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from forgeagent.control_plane import AuthorizationError, ControlPlane
from forgeagent.generator import OllamaGenerator


class ControlPlaneTests(unittest.TestCase):
    def test_mcp_api_provider_selection_can_use_local_ollama(self):
        with patch.dict(
            "os.environ",
            {
                "FORGEAGENT_PROVIDER": "ollama",
                "FORGEAGENT_OLLAMA_MODEL": "local-test-model",
                "FORGEAGENT_OLLAMA_HOST": "http://127.0.0.1:11434",
            },
            clear=False,
        ):
            generator = ControlPlane._request_generator()

        self.assertIsInstance(generator, OllamaGenerator)
        self.assertEqual(generator.model, "local-test-model")

    def test_tenant_roles_tokens_and_production_request(self):
        with tempfile.TemporaryDirectory() as directory:
            plane = ControlPlane(directory)
            try:
                plane.create_project("team/invoices", "owner")
                token = plane.issue_token("owner", "test", ttl_seconds=60)
                self.assertEqual(plane.authenticate(token), "owner")
                plane.grant_role("team/invoices", "owner", "developer", "developer")
                outcome = plane.request_capability("team/invoices", "developer", "Normalize inconsistent date formats in this import log", {"text": "batch=A 03/07/2026"})
                self.assertEqual(outcome["status"], "pending")
                metrics = plane.metrics("team/invoices", "developer")
                self.assertGreaterEqual(metrics["control_event_count"], 3)
            finally:
                plane.close()

    def test_cross_tenant_access_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            plane = ControlPlane(directory)
            try:
                plane.create_project("team/a", "alice")
                plane.create_project("team/b", "bob")
                with self.assertRaises(AuthorizationError):
                    plane.metrics("team/b", "alice")
            finally:
                plane.close()

    def test_offline_template_request_enters_review_without_an_api_key(self):
        """The control plane can propose a reviewed local template, not just GPT work."""
        with tempfile.TemporaryDirectory() as directory:
            plane = ControlPlane(directory)
            try:
                plane.create_project("team/billing", "owner")
                plane.grant_role("team/billing", "owner", "developer", "developer")

                outcome = plane.request_capability(
                    "team/billing",
                    "developer",
                    "Extract invoice IDs from these billing logs",
                    {"text": "invoice INV-2048 is delayed"},
                )

                self.assertEqual(outcome["status"], "pending")
                self.assertEqual(outcome["memory_record"]["name"], "invoice_id_extractor")
                self.assertTrue(outcome["proof"]["passed"])
            finally:
                plane.close()

    def test_developer_feedback_quarantines_a_reproduced_failure_and_reviewer_can_run_drift_check(self):
        with tempfile.TemporaryDirectory() as directory:
            plane = ControlPlane(directory)
            try:
                plane.create_project("team/maintenance", "owner")
                plane.grant_role("team/maintenance", "owner", "developer", "developer")
                plane.grant_role("team/maintenance", "owner", "reviewer", "reviewer")
                record = plane.store.promote(
                    "team/maintenance", "echo", "def run(payload):\n    return payload['value']\n", "fixture",
                    {
                        "passed": True, "trust_score": 100,
                        "cases": [
                            {"category": "normal", "input": {"value": "ok"}, "expected_output": "ok", "rationale": "normal"},
                            {"category": "edge", "input": {"value": "ok"}, "expected_output": "ok", "rationale": "edge"},
                            {"category": "contract", "input": {"value": "ok"}, "expected_output": "ok", "rationale": "contract"},
                        ],
                    },
                )

                feedback = plane.report_capability_feedback(
                    "team/maintenance", "developer", record.id, "incorrect",
                    "The echo tool must return a list for batch input.",
                    {"value": "ok"}, ["ok"],
                )
                drift = plane.check_contract_drift("team/maintenance", "reviewer")

                self.assertTrue(feedback["quarantined"])
                self.assertEqual(plane.store.get(record.id).state, "quarantined")
                self.assertEqual(drift["checked"], 0)
            finally:
                plane.close()
