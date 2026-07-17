import os
import tempfile
import unittest
from pathlib import Path

from control_plane import ControlPlane
from mcp_server import call, handle
from platform_store import PlatformStore


class McpTests(unittest.TestCase):
    def test_tools_list_exposes_repository_and_governance_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PlatformStore(Path(directory) / "foundry.sqlite3")
            response = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, store)
            self.assertIn("forge_inspect_repository", str(response))
            self.assertIn("forge_request_capability", str(response))
            self.assertIn("forge_get_approval_status", str(response))

    def test_approved_project_capability_is_reused_by_mcp_runner(self):
        """A trusted MCP capability must be reused from project SQLite memory."""
        previous_directory = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            os.chdir(root)
            plane = ControlPlane(root / "control")
            try:
                request = call("forge_request_capability", {
                    "project_id": "payments-api",
                    "task": "Normalize inconsistent date formats in this import log",
                    "payload": {"text": "batch=A 03/07/2026"},
                    "production": True,
                }, plane.store, plane)
                capability_id = request["memory_record"]["id"]
                call("forge_decide_capability", {
                    "capability_id": capability_id,
                    "decision": "approved",
                    "reviewer": "Ada",
                    "reason": "Reviewed proof evidence and constrained source.",
                }, plane.store, plane)

                result = call("forge_run_trusted_capability", {
                    "project_id": "payments-api",
                    "task": "Normalize inconsistent date formats in this import log",
                    "payload": {"text": "batch=A 03/07/2026"},
                }, plane.store, plane)

                self.assertEqual(result["status"], "reused")
                self.assertEqual(result["memory_record"]["id"], capability_id)
                self.assertEqual(result["memory_record"]["version"], 1)
                self.assertEqual(result["inspection"]["existing_trusted_tool"]["id"], capability_id)
                self.assertEqual(result["memory_source"], "platform_store")

                listed = call("forge_list_capabilities", {"project_id": "payments-api"}, plane.store, plane)
                status = call("forge_get_approval_status", {"project_id": "payments-api"}, plane.store, plane)
                metrics = call("forge_get_metrics", {"project_id": "payments-api"}, plane.store, plane)
                self.assertEqual(listed["capabilities"][0]["id"], capability_id)
                self.assertEqual(status["capabilities"][0]["state"], "trusted")
                self.assertEqual(metrics["capability_count"], 1)
                self.assertEqual(metrics["states"], {"trusted": 1})
            finally:
                plane.close()
                os.chdir(previous_directory)
