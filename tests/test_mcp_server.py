import ast
import inspect
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from forgeagent.control_plane import ControlPlane
import forgeagent.mcp_server as mcp_server
from forgeagent.mcp_server import PROJECT_SCOPED_TOOLS, call, handle
from forgeagent.platform_store import PlatformStore


class McpTests(unittest.TestCase):
    @staticmethod
    def _spawn_stdio_server(root: Path) -> subprocess.Popen[str]:
        server = Path(__file__).resolve().parents[1] / "forgeagent" / "mcp_server.py"
        return subprocess.Popen(
            [sys.executable, str(server)], cwd=root, text=True, bufsize=1,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

    def _rpc(self, process: subprocess.Popen[str], request_id: int, name: str, arguments: dict[str, object]) -> dict[str, object]:
        assert process.stdin is not None and process.stdout is not None
        process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": request_id, "method": "tools/call", "params": {"name": name, "arguments": arguments}}) + "\n")
        process.stdin.flush()
        response = json.loads(process.stdout.readline())
        self.assertNotIn("error", response)
        return json.loads(response["result"]["content"][0]["text"])

    def _close_server(self, process: subprocess.Popen[str]) -> None:
        if process.stdin and not process.stdin.closed:
            process.stdin.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        if process.stdout and not process.stdout.closed:
            process.stdout.close()
        if process.stderr and not process.stderr.closed:
            process.stderr.close()

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

    def test_offline_template_is_requestable_then_reusable_over_mcp(self):
        """No-key template creation must preserve the same approval boundary."""
        with tempfile.TemporaryDirectory() as directory:
            plane = ControlPlane(Path(directory) / "control")
            try:
                request = call("forge_request_capability", {
                    "project_id": "billing", "task": "Extract invoice IDs from billing logs",
                    "payload": {"text": "invoice INV-2048 is delayed"}, "production": True,
                }, plane.store, plane)
                self.assertEqual(request["status"], "pending")
                self.assertEqual(request["memory_record"]["name"], "invoice_id_extractor")
                capability_id = request["memory_record"]["id"]
                call("forge_decide_capability", {
                    "capability_id": capability_id, "decision": "approved", "reviewer": "Ada",
                    "reason": "Reviewed deterministic template and proof evidence.",
                }, plane.store, plane)

                reused = call("forge_run_trusted_capability", {
                    "project_id": "billing", "task": "Extract invoice identifiers from new billing logs",
                    "payload": {"text": "INV-2048 and INV-9"},
                }, plane.store, plane)
                self.assertEqual(reused["status"], "reused")
                self.assertEqual(reused["result"], ["INV-2048", "INV-9"])
                self.assertEqual(reused["memory_source"], "platform_store")
            finally:
                plane.close()

    def test_separate_mcp_processes_reuse_approved_project_capability(self):
        """Judge-path regression: approval in process A is reusable in process B."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            process_a = self._spawn_stdio_server(root)
            try:
                request = self._rpc(process_a, 1, "forge_request_capability", {
                    "project_id": "judge-subprocess", "task": "Normalize inconsistent date formats in this import log",
                    "payload": {"text": "batch=A 03/07/2026"}, "production": True,
                })
                capability_id = request["memory_record"]["id"]
                approved = self._rpc(process_a, 2, "forge_decide_capability", {
                    "capability_id": capability_id, "decision": "approved", "reviewer": "Ada",
                    "reason": "Reviewed proof evidence and constrained source.",
                })
                self.assertEqual(approved["state"], "trusted")
            finally:
                self._close_server(process_a)

            process_b = self._spawn_stdio_server(root)
            try:
                reused = self._rpc(process_b, 3, "forge_run_trusted_capability", {
                    "project_id": "judge-subprocess", "task": "Normalize inconsistent date formats in this import log",
                    "payload": {"text": "batch=B 2026/7/4"},
                })
                self.assertEqual(reused["status"], "reused")
                self.assertEqual(reused["memory_source"], "platform_store")
                self.assertEqual(reused["memory_record"]["id"], capability_id)
                self.assertEqual(reused["inspection"]["existing_trusted_tool"]["id"], capability_id)
            finally:
                self._close_server(process_b)

    def test_project_scoped_dispatch_cannot_use_flat_registry_memory(self):
        """Future project MCP tools must stay behind the SQLite control-plane boundary."""
        expected = {
            "forge_list_capabilities", "forge_get_audit_receipt", "forge_request_capability",
            "forge_run_trusted_capability", "forge_get_approval_status", "forge_get_metrics",
        }
        self.assertEqual(PROJECT_SCOPED_TOOLS, expected)
        dispatch = inspect.getsource(mcp_server.call)
        self.assertNotIn("CapabilityFoundry", dispatch)
        self.assertNotIn("ToolRegistry", dispatch)
        self.assertNotIn("tool_registry.json", dispatch)
        names = {node.id for node in ast.walk(ast.parse(dispatch)) if isinstance(node, ast.Name)}
        self.assertIn("project_store", names)
        self.assertIn("ControlPlane", names)
