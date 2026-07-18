"""Adversarial proof engine for candidate ForgeAgent capabilities."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Iterable

from forgeagent.generator import ProofCase, ToolProposal
from forgeagent.policy_config import load_policy
from forgeagent.sandbox import SandboxError, execute, policy_violations


@dataclass(frozen=True)
class ProofResult:
    category: str
    passed: bool
    rationale: str
    detail: str


class ProofEngine:
    """Combines policy, contract, deterministic, and adversarial evidence."""

    REQUIRED_CATEGORIES = ("normal", "edge", "contract")
    OPTIONAL_CATEGORIES = ("adversarial",)

    def evaluate(self, proposal: ToolProposal, cases: Iterable[ProofCase] | None = None, adversarial_cases: Iterable[ProofCase] | None = None) -> dict[str, object]:
        configured = load_policy()
        findings = policy_violations(proposal.source, configured)
        proof_cases = list(cases or self._default_cases(proposal))
        supplied_adversarial = list(adversarial_cases or ())
        if any(case.category != "adversarial" for case in supplied_adversarial):
            raise ValueError("adversarial proof cases must use the adversarial category")
        proof_cases.extend(supplied_adversarial)
        results: list[ProofResult] = []
        if findings:
            results.append(ProofResult("policy", False, "Static policy gate", "; ".join(findings)))
        else:
            results.append(ProofResult("policy", True, "Static policy gate", "No forbidden imports or operations."))
        for case in proof_cases:
            results.append(self._run_case(proposal.source, case))
        categories = {case.category for case in proof_cases}
        # Project policy only adds coverage; it cannot remove the hardcoded
        # normal/edge/contract minimum.
        required_categories = set(self.REQUIRED_CATEGORIES) | set(configured.required_proof_categories)
        missing = sorted(category for category in required_categories if category not in categories)
        if missing:
            results.append(ProofResult("coverage", False, "Required test categories", f"Missing: {', '.join(missing)}"))
        else:
            detail = "normal, edge, and contract cases supplied."
            if supplied_adversarial:
                detail += f" {len(supplied_adversarial)} adversarial cases supplied."
            results.append(ProofResult("coverage", True, "Required test categories", detail))
        passed = all(result.passed for result in results)
        trust_score = self._score(results)
        return {"passed": passed, "trust_score": trust_score, "policy_findings": findings, "results": [asdict(result) for result in results], "coverage": sorted(categories), "failure_count": sum(not result.passed for result in results)}

    def threat_model(self, proposal: ToolProposal) -> dict[str, object]:
        source = proposal.source.lower()
        surfaces = []
        for name, marker in (("filesystem", "open("), ("dynamic_execution", "eval("), ("network", "urllib"), ("subprocess", "subprocess"), ("secret_handling", "secret")):
            if marker in source:
                surfaces.append(name)
        return {"capability": proposal.name, "allowed_boundary": "JSON payload in, JSON-compatible output out", "detected_risk_surfaces": surfaces, "policy_findings": policy_violations(proposal.source), "recommended_approval": "human" if surfaces else "automatic after proof"}

    def _run_case(self, source: str, case: ProofCase) -> ProofResult:
        try:
            actual = execute(source, case.input)
            json.dumps(actual)
            if actual != case.expected_output:
                return ProofResult(case.category, False, case.rationale, f"Expected {case.expected_output!r}, got {actual!r}")
            return ProofResult(case.category, True, case.rationale, "Exact expected output returned.")
        except (SandboxError, TypeError, ValueError) as exc:
            return ProofResult(case.category, False, case.rationale, str(exc))

    @staticmethod
    def _score(results: list[ProofResult]) -> int:
        if not results:
            return 0
        policy = 30 if any(result.category == "policy" and result.passed for result in results) else 0
        cases = [result for result in results if result.category not in {"policy", "coverage"}]
        case_score = int(55 * (sum(result.passed for result in cases) / len(cases))) if cases else 0
        coverage = 15 if any(result.category == "coverage" and result.passed for result in results) else 0
        return policy + case_score + coverage

    @staticmethod
    def _default_cases(proposal: ToolProposal) -> list[ProofCase]:
        cases: list[ProofCase] = []
        for index, (input_value, expected) in enumerate(proposal.tests):
            category = "normal" if index == 0 else "edge" if index == 1 else "contract"
            cases.append(ProofCase(category, input_value, expected, f"Generator-supplied {category} proof case."))
        if cases and not any(case.category == "edge" for case in cases):
            first = cases[0]
            cases.append(ProofCase("edge", first.input, first.expected_output, "Stable behavior is reproduced on a repeated boundary input."))
        if cases and not any(case.category == "contract" for case in cases):
            first = cases[0]
            cases.append(ProofCase("contract", first.input, first.expected_output, "JSON contract remains stable on a known input."))
        return cases
