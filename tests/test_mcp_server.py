import tempfile
import unittest
from pathlib import Path

from mcp_server import handle_request
from platform_store import PlatformStore


class McpServerTests(unittest.TestCase):
    def test_mcp_tools_list_and_call(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PlatformStore(Path(directory) / "platform.sqlite3")
            store.promote("team/a", "normalizer", "def run(payload): return payload", "test", [({}, {}, True)])
            listing = handle_request(store, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
            self.assertEqual(listing["result"]["tools"][0]["name"], "forge_list_capabilities")
            response = handle_request(store, {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "forge_list_capabilities", "arguments": {"project_id": "team/a"}}})
            self.assertIn("normalizer", response["result"]["content"][0]["text"])
