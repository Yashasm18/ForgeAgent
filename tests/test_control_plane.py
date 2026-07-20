import tempfile
import unittest
from pathlib import Path

from forgeagent.control_plane import AuthorizationError, ControlPlane


class ControlPlaneTests(unittest.TestCase):
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
