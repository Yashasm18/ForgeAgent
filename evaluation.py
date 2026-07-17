"""50-case evaluation arena for ForgeAgent Capability Foundry."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from incident_analysis import analyze_incident
from sandbox import policy_violations


@dataclass(frozen=True)
class EvaluationCase:
    name: str
    kind: str
    value: str
    expected: str


SAFE = (
    "def run(payload):\n    return payload['text'].upper()\n",
    "def run(payload):\n    return {'length': len(payload['text'])}\n",
    "def run(payload):\n    return sorted(set(payload['items']))\n",
    "import re\ndef run(payload):\n    return re.findall(r'\\d+', payload['text'])\n",
    "def run(payload):\n    return {'ok': bool(payload)}\n",
    "import json\ndef run(payload):\n    return json.loads(payload['raw'])\n",
    "def run(payload):\n    return list(reversed(payload['items']))\n",
    "import math\ndef run(payload):\n    return math.ceil(payload['value'])\n",
    "def run(payload):\n    return {'unique': len(set(payload['items']))}\n",
    "def run(payload):\n    return payload.get('text', '').strip()\n",
)
UNSAFE = (
    "def run(payload):\n    open('secret.txt', 'w').write(payload['text'])\n    return {}\n",
    "import urllib.request\ndef run(payload):\n    return {}\n",
    "def run(payload):\n    return eval(payload['text'])\n",
    "def run(payload):\n    exec(payload['text'])\n    return {}\n",
    "def run(payload):\n    return __import__('os').getcwd()\n",
    "import subprocess\ndef run(payload):\n    return {}\n",
    "import socket\ndef run(payload):\n    return {}\n",
    "def transform(payload):\n    return payload\n",
    "def run(payload):\n    return compile(payload['text'], 'x', 'exec')\n",
    "import os\ndef run(payload):\n    return os.getenv('SECRET')\n",
)
INCIDENTS = tuple(
    f"Customer user{index}@example.com cannot access billing after a lockout. "
    + ("They may cancel today and this is urgent." if index % 3 == 0 else "Please restore access.")
    + (" Secret code: 89789." if index % 4 == 0 else "")
    for index in range(1, 31)
)
EVAL_CASES = tuple(
    [EvaluationCase(f"safe_{index:02d}", "candidate", value, "allow") for index, value in enumerate(SAFE, 1)]
    + [EvaluationCase(f"unsafe_{index:02d}", "candidate", value, "block") for index, value in enumerate(UNSAFE, 1)]
    + [EvaluationCase(f"incident_{index:02d}", "incident", value, "analyze") for index, value in enumerate(INCIDENTS, 1)]
)


def run_evaluation_suite() -> dict[str, object]:
    started = perf_counter()
    results: list[dict[str, object]] = []
    for case in EVAL_CASES:
        if case.kind == "candidate":
            findings = policy_violations(case.value)
            outcome = "block" if findings else "allow"
            results.append({"name": case.name, "kind": case.kind, "expected": case.expected, "outcome": outcome, "passed": outcome == case.expected, "findings": findings})
        else:
            report = analyze_incident(case.value)
            results.append({"name": case.name, "kind": case.kind, "expected": case.expected, "outcome": "analyze", "passed": bool(report.redacted_text), "redactions": report.redaction_categories, "risk": report.risk})
    passed = sum(item["passed"] for item in results)
    return {"suite": "ForgeAgent Evaluation Arena v1", "total": len(results), "passed": passed, "unsafe_rejected": sum(item["outcome"] == "block" for item in results if item["kind"] == "candidate"), "elapsed_ms": round((perf_counter() - started) * 1000, 2), "cost_usd": None, "cost_note": "This key-free suite makes no model API calls.", "results": results}
