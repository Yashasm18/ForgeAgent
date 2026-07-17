"""ForgeAgent Capability Foundry: graph -> council -> proof -> governed memory."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agent import BLUEPRINTS, ForgeAgent
from audit import AuditLog
from generator import ProofCase, ProposalGenerator, ToolProposal
from platform_store import PlatformStore
from proof_engine import ProofEngine
from repository_graph import RepositoryGraph
from registry import ToolRegistry


@dataclass(frozen=True)
class CouncilDecision:
    role: str
    status: str
    detail: str


class CapabilityFoundry:
    """Coordinates the five accountable roles behind autonomous capability work."""

    def __init__(self, registry_path: str | Path = "data/tool_registry.json", project_id: str = "local/default", root: str | Path = ".", generator: ProposalGenerator | None = None) -> None:
        self.registry_path = Path(registry_path)
        self.registry = ToolRegistry(self.registry_path)
        self.project_id = project_id
        self.root = Path(root)
        self.generator = generator
        self.proofs = ProofEngine()
        self.store = PlatformStore(self.registry_path.parent / "foundry.sqlite3")
        # The Council output was previously returned only after a run finished.
        # This append-only mirror makes those same decisions observable live.
        self.audit = AuditLog(self.registry_path.parent / "audit_log.jsonl")

    def _record_decision(
        self,
        decisions: list[CouncilDecision],
        capability: str,
        role: str,
        status: str,
        detail: str,
    ) -> None:
        decision = CouncilDecision(role, status, detail)
        decisions.append(decision)
        self.audit.record(f"council_{role}", capability, detail, status)

    def inspect(self, capability: str) -> dict[str, object]:
        graph = RepositoryGraph(self.root)
        graph.build()
        existing = self.registry.get(capability)
        return {"capability": capability, "existing_trusted_tool": asdict(existing) if existing else None, "repository_matches": graph.query(capability), "impact": graph.impact(capability), "graph": graph.export()}

    def run(self, task: str, payload: dict[str, object], approval_policy: str = "auto", max_repairs: int = 2, adversarial_proof: bool = False) -> dict[str, object]:
        blueprint = next((item for item in BLUEPRINTS if item.matches(task)), None)
        capability = blueprint.name if blueprint else self._slug(task)
        inspection = self.inspect(capability)
        decisions: list[CouncilDecision] = []
        self._record_decision(decisions, capability, "planner", "complete", f"Task maps to capability '{capability}'.")
        if adversarial_proof and self.generator is None:
            raise RuntimeError("Live adversarial proof requires OPENAI_API_KEY and a GPT-5.6 generator; offline mode remains unchanged without --adversarial-proof.")
        if inspection["existing_trusted_tool"]:
            if approval_policy == "production":
                self._record_decision(decisions, capability, "builder", "skipped", "An existing capability was found; production reuse is still subject to review.")
                self._record_decision(decisions, capability, "governor", "pending", "Production policy requires a named human approval before reuse.")
                return self._outcome(task, capability, "pending", None, inspection, decisions)
            agent = ForgeAgent(self.registry, emit=lambda _: None)
            result = agent.complete(task, payload)
            self._record_decision(decisions, capability, "builder", "skipped", "A trusted capability already exists.")
            self._record_decision(decisions, capability, "governor", "reused", f"Reused {capability} without creating new code.")
            return self._outcome(task, capability, "reused", result, inspection, decisions)
        proposal = self._proposal(task, payload, blueprint)
        threat: dict[str, object] | None = None
        report: dict[str, object] | None = None
        for attempt in range(max_repairs + 1):
            self._record_decision(decisions, capability, "builder", "complete" if attempt == 0 else "repaired", f"Produced constrained candidate '{proposal.name}' (attempt {attempt + 1}).")
            threat = self.proofs.threat_model(proposal)
            self._record_decision(decisions, capability, "security", "complete", f"Threat model found {len(threat['policy_findings'])} policy findings.")
            adversarial_cases = self._adversarial_cases(proposal) if adversarial_proof else []
            if adversarial_cases:
                self._record_decision(decisions, capability, "security", "complete", f"GPT-5.6 supplied {len(adversarial_cases)} adversarial proof cases.")
            report = self.proofs.evaluate(proposal, adversarial_cases=adversarial_cases)
            self._record_decision(decisions, capability, "evaluator", "passed" if report["passed"] else "rejected", f"Trust score {report['trust_score']}; {report['failure_count']} proof failures.")
            if report["passed"] or not self.generator or attempt == max_repairs:
                break
            failure = "; ".join(result["detail"] for result in report["results"] if not result["passed"])
            self._record_decision(decisions, capability, "planner", "repair_requested", f"Candidate failed proof: {failure}")
            proposal = self.generator.propose(f"{task}\nRepair the prior candidate. Failure evidence: {failure}", payload)
        assert threat is not None and report is not None
        record = self.store.promote(self.project_id, proposal.name, proposal.source, proposal.provenance, report, approval_policy, threat)
        if record.state != "trusted":
            self._record_decision(decisions, capability, "governor", record.state, "Capability was retained as evidence but not executed.")
            return self._outcome(task, capability, record.state, None, inspection, decisions, threat, report, record)
        agent = ForgeAgent(self.registry, emit=lambda _: None)
        # A newly promoted proposal must still replace an existing registry
        # version through the full verification path; never treat a version
        # update as a cache hit.
        result = agent._verify_and_run(proposal, payload, force_candidate=self.registry.get(proposal.name) is not None)
        self._record_decision(decisions, capability, "governor", "trusted", f"Promoted {record.name}@v{record.version} after policy and proof.")
        return self._outcome(task, capability, "trusted", result, inspection, decisions, threat, report, record)

    def _proposal(self, task: str, payload: dict[str, object], blueprint: object | None) -> ToolProposal:
        if self.generator:
            return self.generator.propose(task, payload)
        if blueprint is None:
            raise RuntimeError("A live gpt-5.6-terra generator is required for an unknown capability. Set OPENAI_API_KEY or choose a supported curated capability.")
        return ToolProposal(blueprint.name, blueprint.description, blueprint.source, ((blueprint.test_input, blueprint.expected_output),), "curated offline Foundry proposal")

    def _adversarial_cases(self, proposal: ToolProposal) -> list[ProofCase]:
        generator = self.generator
        if generator is None or not hasattr(generator, "propose_adversarial_cases"):
            raise RuntimeError("Configured live generator does not support adversarial proof generation.")
        cases = generator.propose_adversarial_cases(proposal)
        if not cases:
            raise RuntimeError("Live adversarial proof generation returned no cases; refusing promotion.")
        return cases

    @staticmethod
    def _slug(task: str) -> str:
        import re
        return "_".join(re.findall(r"[a-z0-9]+", task.lower())[:5]) or "unnamed_capability"

    @staticmethod
    def _outcome(task: str, capability: str, status: str, result: object, inspection: dict[str, object], decisions: list[CouncilDecision], threat: dict[str, object] | None = None, proof: dict[str, object] | None = None, record: object | None = None) -> dict[str, object]:
        return {"task": task, "capability": capability, "status": status, "result": result, "council": [asdict(decision) for decision in decisions], "inspection": {"impact": inspection["impact"], "existing_trusted_tool": inspection["existing_trusted_tool"], "match_count": len(inspection["repository_matches"])}, "threat_model": threat, "proof": proof, "memory_record": asdict(record) if record else None}
