import tempfile
import unittest
from pathlib import Path

from control_plane import AuthorizationError, ControlPlane


class ControlPlaneTests(unittest.TestCase):
    def test_tenant_roles_tokens_and_production_request(self):
        with tempfile.TemporaryDirectory() as directory:
            plane = ControlPlane(directory)
            try:
                plane.create_project("team/invoices", "owner")
                token = plane.issue_token("owner", "test", ttl_seconds=60)
                self.assertEqual(plane.authenticate(token), "owner")
                plane.grant_role("team/invoices", "owner", "developer", "developer")
                outcome = plane.request_capability("team/invoices", "developer", "Find word frequency", {"text": "tools tools"})
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
