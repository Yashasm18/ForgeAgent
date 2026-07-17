"""Evidence-first evaluation suite for ForgeAgent's capability trust boundary."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from comparison import compare
from incident_analysis import analyze_incident
from sandbox import policy_violations
from workflows import INCIDENT_RECOVERY_PLAN


@dataclass(frozen=True)
class EvaluationCase:
    name: str
    kind: str
    payload: str
    expected: str


SAFE_SOURCES = (
    "def run(payload):\n    return payload['text'].upper()\n",
    "def run(payload):\n    return {'length': len(payload['text'])}\n",
    "def run(payload):\n    return sorted(set(payload['items']))\n",
)
UNSAFE_SOURCES = (
    "def run(payload):\n    open('secrets.txt', 'w').write(payload['text'])\n    return {}\n",
    "import urllib.request\ndef run(payload):\n    return {}\n",
    "def run(payload):\n    return eval(payload['text'])\n",
    "def run(payload):\n    exec(payload['text'])\n    return {}\n",
    "def run(payload):\n    return __import__('os').getcwd()\n",
)
INCIDENTS = (
    "Ava ava@example.com cannot access billing and may cancel today.",
    "Security incident: phone +91 9876543210 reports unauthorized access.",
    "Customer secret code: 123456 and API key is abcdefgh need urgent help.",
    "Normal question about dashboard filters.",
    "Card 4111 1111 1111 1111 was entered and refund is urgent.",
    "Confidential message: do not share the launch plan. Login failed.",
    "Priya priya@example.com has a lockout after a compromised account.",
    "The report is slow but no customer impact is reported.",
    "Access token: token_abcdef12345 cannot be pasted in chat.",
    "A customer says competitor migration is likely unless billing is restored.",
    "OTP is 123456; please reset the account.",
    "Refund requested after duplicate invoice invoice-1002.",
)
EVAL_CASES = tuple(
    [EvaluationCase(f"safe_{index}", "candidate", source, "allow") for index, source in enumerate(SAFE_SOURCES, 1)]
    + [EvaluationCase(f"unsafe_{index}", "candidate", source, "block") for index, source in enumerate(UNSAFE_SOURCES, 1)]
    + [EvaluationCase(f"incident_{index}", "incident", text, "analyze") for index, text in enumerate(INCIDENTS, 1)]
)


def run_evaluation_suite() -> dict[str, object]:
    """Evaluate actual deterministic code paths; no synthetic success metrics."""
    started = perf_counter()
    rows: list[dict[str, object]] = []
    for case in EVAL_CASES:
        if case.kind == "candidate":
            findings = policy_violations(case.payload)
            outcome = "allow" if not findings else "block"
            rows.append({"name": case.name, "kind": case.kind, "expected": case.expected, "outcome": outcome, "passed": outcome == case.expected, "findings": findings})
        else:
            result = analyze_incident(case.payload)
            rows.append({"name": case.name, "kind": case.kind, "expected": "analyze", "outcome": "analyzed", "passed": bool(result.redacted_text), "redactions": result.redaction_categories, "risk": result.risk})
    passed = sum(bool(row["passed"]) for row in rows)
    candidate_rows = [row for row in rows if row["kind"] == "candidate"]
    blocked = sum(row["outcome"] == "block" for row in candidate_rows)
    comparison = compare(INCIDENT_RECOVERY_PLAN)
    return {
        "suite": "ForgeAgent Evidence Suite v1",
        "total": len(rows),
        "passed": passed,
        "candidate_policy_blocks": blocked,
        "elapsed_ms": round((perf_counter() - started) * 1000, 2),
        "cost_usd": None,
        "cost_note": "Offline evaluation performs no model API calls.",
        "memory_comparison": comparison,
        "results": rows,
    }
