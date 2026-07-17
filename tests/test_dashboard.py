import json
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from audit import AuditLog
from dashboard import create_server


class DashboardAuditEndpointTests(unittest.TestCase):
    def test_audit_log_endpoint_returns_cursor_and_only_new_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = root / "tool_registry.json"
            audit = AuditLog(root / "audit_log.jsonl")
            audit.record("council_planner", "invoice_ids", "Mapped the request.", "complete")
            audit.record("council_security", "invoice_ids", "Policy scan passed.", "complete")
            audit.record("council_evaluator", "invoice_ids", "Proof passed.", "passed")
            server = create_server(registry, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}/api/audit-log"
                with urllib.request.urlopen(f"{base}?since=0", timeout=2) as response:
                    initial = json.load(response)
                with urllib.request.urlopen(f"{base}?since=1", timeout=2) as response:
                    incremental = json.load(response)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

        self.assertEqual(initial["cursor"], 3)
        self.assertEqual([event["event"] for event in initial["events"]], [
            "council_planner", "council_security", "council_evaluator",
        ])
        self.assertEqual(incremental["cursor"], 3)
        self.assertEqual([event["event"] for event in incremental["events"]], [
            "council_security", "council_evaluator",
        ])
        self.assertEqual(
            set(incremental["events"][0]),
            {"event", "capability", "detail", "outcome", "created_at"},
        )


if __name__ == "__main__":
    unittest.main()
