import tempfile
import unittest
from pathlib import Path

from scripts.review_capabilities import review_paths


SAFE_CAPABILITY = '''\
def run(payload):
    return {"value": payload["value"].strip()}

PROOF_CASES = [
    {"category": "normal", "input": {"value": " ok "}, "expected_output": {"value": "ok"}, "rationale": "normal input"},
    {"category": "edge", "input": {"value": ""}, "expected_output": {"value": ""}, "rationale": "empty string"},
    {"category": "contract", "input": {"value": "x"}, "expected_output": {"value": "x"}, "rationale": "JSON contract"},
]
'''


class CapabilityPrReviewTests(unittest.TestCase):
    def test_unsafe_capability_is_detected_and_rejected_by_real_policy_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unsafe_tool.py"
            path.write_text("import subprocess\n\n" + SAFE_CAPABILITY)

            report = review_paths([path])

        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["capability_files"], [str(path)])
        self.assertTrue(any("disallowed import: subprocess" in finding for finding in report["findings"]))

    def test_safe_capability_with_proof_cases_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "safe_tool.py"
            path.write_text(SAFE_CAPABILITY)

            report = review_paths([path])

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["capability_files"], [str(path)])

    def test_unrelated_change_passes_without_capability_review(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "notes.py"
            path.write_text("def helper(value):\n    return value\n")

            report = review_paths([path])

        self.assertEqual(report, {"status": "passed", "capability_files": [], "findings": [], "message": "No capability-shaped files changed."})
