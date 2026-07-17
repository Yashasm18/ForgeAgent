import tempfile
import unittest
from pathlib import Path

from mcp_server import handle
from platform_store import PlatformStore


class McpTests(unittest.TestCase):
    def test_tools_list_exposes_repository_and_governance_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PlatformStore(Path(directory) / "foundry.sqlite3")
            response = handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, store)
            self.assertIn("forge_inspect_repository", str(response))
            self.assertIn("forge_request_capability", str(response))
            self.assertIn("forge_get_approval_status", str(response))
