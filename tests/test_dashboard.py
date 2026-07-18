import json
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from audit import AuditLog
from dashboard import PAGE, create_server
from platform_store import PlatformStore
from registry import Tool, ToolRegistry


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

    def test_tools_endpoint_uses_one_persisted_proof_summary_for_cards_and_total(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry_path = root / "tool_registry.json"
            registry = ToolRegistry(registry_path)
            registry.register(Tool("dates", "dates", "def run(payload): return payload", {}, {}, registry.timestamp(), proof_case_count=3))
            registry.register(Tool("traces", "traces", "def run(payload): return payload", {}, {}, registry.timestamp(), proof_case_count=2))
            server = create_server(registry_path, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                url = f"http://127.0.0.1:{server.server_port}/api/tools"
                with urllib.request.urlopen(url, timeout=2) as response:
                    payload = json.load(response)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

        counts = [tool["proof_case_count"] for tool in payload["tools"]]
        self.assertEqual(counts, [3, 2])
        self.assertTrue(payload["proof_summary"]["evidence_available"])
        self.assertEqual(payload["proof_summary"]["total_case_count"], sum(counts))
        self.assertIn("d.proof_summary", PAGE)
        self.assertNotIn("x.tests?.length||1", PAGE)

    def test_pending_endpoint_returns_full_read_only_evidence_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry_path = root / "tool_registry.json"
            store = PlatformStore(root / "foundry.sqlite3")
            proof = {
                "passed": True,
                "trust_score": 91,
                "policy_findings": [],
                "results": [
                    {"category": "normal", "passed": True, "rationale": "known input", "detail": "matched"},
                    {"category": "edge", "passed": True, "rationale": "empty input", "detail": "matched"},
                    {"category": "contract", "passed": True, "rationale": "JSON output", "detail": "matched"},
                ],
            }
            threat = {"detected_risk_surfaces": ["finance"], "allowed_boundary": "JSON payload in, JSON-compatible output out"}
            store.promote(
                "review/demo", "invoice_id_extractor", "def run(payload): return {'ids': []}", "test fixture",
                proof, policy="production", threat_model=threat,
                requested_task="Extract invoice IDs from an incident.",
            )
            store.close()
            payload = self._get_json(create_server(registry_path, port=0), "/api/pending")

        self.assertEqual(len(payload["pending"]), 1)
        pending = payload["pending"][0]
        self.assertEqual(pending["name"], "invoice_id_extractor")
        self.assertEqual(pending["requested_task"], "Extract invoice IDs from an incident.")
        self.assertEqual(pending["source"], "def run(payload): return {'ids': []}")
        self.assertEqual(pending["trust_score"], 91)
        self.assertEqual(pending["threat_model"]["detected_risk_surfaces"], ["finance"])
        self.assertEqual([item["category"] for item in pending["proof"]["results"]], ["normal", "edge", "contract"])
        self.assertIn("pending-review", PAGE)

    def test_pending_endpoint_is_empty_when_no_pending_capability_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = self._get_json(create_server(Path(directory) / "tool_registry.json", port=0), "/api/pending")

        self.assertEqual(payload, {"pending": []})

    @staticmethod
    def _get_json(server, route):
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}{route}", timeout=2) as response:
                return json.load(response)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
