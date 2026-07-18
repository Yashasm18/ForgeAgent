"""Temporary PR-review fixture: intentionally unsafe and never for production."""

import subprocess


def run(payload):
    return {"value": subprocess.check_output(["echo", payload["value"]], text=True).strip()}


PROOF_CASES = [
    {"category": "normal", "input": {"value": "unsafe"}, "expected_output": {"value": "unsafe"}, "rationale": "fixture"},
    {"category": "edge", "input": {"value": ""}, "expected_output": {"value": ""}, "rationale": "fixture"},
    {"category": "contract", "input": {"value": "x"}, "expected_output": {"value": "x"}, "rationale": "fixture"},
]
