#!/usr/bin/env python3
"""Review changed capability-shaped Python files with ForgeAgent's real gates.

A capability-shaped file has a top-level ``run(payload)`` function and must
declare literal ``PROOF_CASES`` entries using this format:
``{"category", "input", "expected_output", "rationale"}``.
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path
from typing import Iterable

# GitHub Actions invokes this file by path, which otherwise makes ``scripts/``
# rather than the repository root the first import location.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from generator import ProofCase, ToolProposal
from proof_engine import ProofEngine
from sandbox import policy_violations


def is_capability_source(source: str) -> bool:
    """Return true only for the project's explicit top-level run(payload) contract."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "run"
        and len(node.args.args) == 1
        and node.args.args[0].arg == "payload"
        for node in tree.body
    )


def proof_cases(source: str) -> list[ProofCase]:
    """Read literal review cases without importing or executing changed code."""
    tree = ast.parse(source)
    value = next(
        (
            node.value
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "PROOF_CASES" for target in node.targets)
        ),
        None,
    )
    if value is None:
        raise ValueError("missing literal PROOF_CASES evidence")
    try:
        raw_cases = ast.literal_eval(value)
    except (ValueError, TypeError) as exc:
        raise ValueError("PROOF_CASES must be a literal list") from exc
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("PROOF_CASES must be a non-empty literal list")
    cases: list[ProofCase] = []
    for index, item in enumerate(raw_cases, 1):
        if not isinstance(item, dict):
            raise ValueError(f"PROOF_CASES[{index}] must be a mapping")
        try:
            category = item["category"]
            rationale = item["rationale"]
            input_value = item["input"]
            expected = item["expected_output"]
        except KeyError as exc:
            raise ValueError(f"PROOF_CASES[{index}] is missing {exc.args[0]}") from exc
        if not isinstance(category, str) or not isinstance(rationale, str):
            raise ValueError(f"PROOF_CASES[{index}] category and rationale must be strings")
        json.dumps(input_value)
        json.dumps(expected)
        cases.append(ProofCase(category, input_value, expected, rationale))
    return cases


def review_paths(paths: Iterable[str | Path]) -> dict[str, object]:
    """Return a JSON-ready review result for added or modified files."""
    capability_files: list[str] = []
    findings: list[str] = []
    for raw_path in paths:
        path = Path(raw_path)
        if path.suffix != ".py" or not path.is_file():
            continue
        source = path.read_text(encoding="utf-8")
        if not is_capability_source(source):
            continue
        capability_files.append(str(path))
        violations = policy_violations(source)
        if violations:
            findings.extend(f"{path}: {violation}" for violation in violations)
            continue
        try:
            cases = proof_cases(source)
            proposal = ToolProposal(path.stem, f"PR capability from {path}", source, (), "PR capability review")
            report = ProofEngine().evaluate(proposal, cases=cases)
        except (ValueError, TypeError) as exc:
            findings.append(f"{path}: {exc}")
            continue
        if not report["passed"]:
            failures = [f"{result['category']}: {result['detail']}" for result in report["results"] if not result["passed"]]
            findings.extend(f"{path}: {failure}" for failure in failures)
    if not capability_files:
        return {"status": "passed", "capability_files": [], "findings": [], "message": "No capability-shaped files changed."}
    return {
        "status": "passed" if not findings else "failed",
        "capability_files": capability_files,
        "findings": findings,
        "message": "Capability review passed." if not findings else "Capability review found blocking evidence.",
    }


def changed_paths(base: str) -> list[Path]:
    """Return added/modified paths in the PR-style range from base to HEAD."""
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=AM", f"{base}...HEAD"],
        text=True,
        capture_output=True,
        check=True,
    )
    return [Path(line) for line in result.stdout.splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Review changed ForgeAgent capability files.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--base", help="Git base SHA/ref for a PR-style diff")
    group.add_argument("--files", nargs="+", help="Explicit paths for local review")
    args = parser.parse_args()
    paths = changed_paths(args.base) if args.base else [Path(item) for item in args.files]
    report = review_paths(paths)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
