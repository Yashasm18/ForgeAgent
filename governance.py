"""Explicit approval policy used before a Foundry capability becomes trusted."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping

from policy_config import load_policy


SENSITIVE_TERMS = frozenset({"secret", "credential", "payment", "finance", "security", "network", "filesystem", "external", "production"})


@dataclass(frozen=True)
class GovernanceDecision:
    policy: str
    decision: str
    reason: str
    requires_human: bool

    def export(self) -> dict[str, object]:
        return asdict(self)


def assess(policy: str, name: str, provenance: str, proof: Mapping[str, object], threat_model: Mapping[str, object] | None = None) -> GovernanceDecision:
    """Return an auditable promotion decision without executing external actions."""
    if policy not in {"auto", "review", "never", "production"}:
        raise ValueError("policy must be auto, review, never, or production")
    findings = list(proof.get("policy_findings", []))
    surfaces = list((threat_model or {}).get("detected_risk_surfaces", []))
    text = f"{name} {provenance}".lower()
    sensitive = bool(set(surfaces)) or any(term in text for term in SENSITIVE_TERMS)
    if findings:
        return GovernanceDecision(policy, "rejected", "Static policy findings block promotion.", False)
    if not proof.get("passed"):
        return GovernanceDecision(policy, "rejected", "Evidence proof did not pass.", False)
    if policy == "never" and sensitive:
        return GovernanceDecision(policy, "rejected", "Policy forbids sensitive or external capabilities.", False)
    if load_policy().require_human_review:
        return GovernanceDecision(policy, "pending", "Project policy requires a named human approver before promotion.", True)
    if policy in {"review", "production"} or sensitive:
        scope = "Production policy" if policy == "production" else "Risk policy"
        return GovernanceDecision(policy, "pending", f"{scope} requires a named human approver before promotion.", True)
    return GovernanceDecision(policy, "approved", "Low-risk capability passed policy and proof.", False)


def validate_human_decision(reviewer: str, reason: str) -> None:
    if len(reviewer.strip()) < 2:
        raise ValueError("a named reviewer is required")
    if len(reason.strip()) < 8:
        raise ValueError("an approval reason of at least 8 characters is required")
