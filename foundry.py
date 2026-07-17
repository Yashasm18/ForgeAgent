"""ForgeAgent Capability Foundry: graph -> council -> proof -> governed memory."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agent import BLUEPRINTS, ForgeAgent
from generator import ProposalGenerator, ToolProposal
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

    def inspect(self, capability: str) -> dict[str, object]:
        graph = RepositoryGraph(self.root)
        graph.build()
        existing = self.registry.get(capability)
        return {"capability": capability, "existing_trusted_tool": asdict(existing) if existing else None, "repository_matches": graph.query(capability), "impact": graph.impact(capability), "graph": graph.export()}

    def run(self, task: str, payload: dict[str, object], approval_policy: str = "auto", max_repairs: int = 2) -> dict[str, object]:
        blueprint = next((item for item in BLUEPRINTS if item.matches(task)), None)
        capability = blueprint.name if blueprint else self._slug(task)
        inspection = self.inspect(capability)
        decisions = [CouncilDecision("planner", "complete", f"Task maps to capability '{capability}'.")]
        if inspection["existing_trusted_tool"]:
            if approval_policy == "production":
                decisions.extend([
                    CouncilDecision("builder", "skipped", "An existing capability was found; production reuse is still subject to review."),
                    CouncilDecision("governor", "pending", "Production policy requires a named human approval before reuse."),
                ])
                return self._outcome(task, capability, "pending", None, inspection, decisions)
            agent = ForgeAgent(self.registry, emit=lambda _: None)
            result = agent.complete(task, payload)
            decisions.extend([CouncilDecision("builder", "skipped", "A trusted capability already exists."), CouncilDecision("governor", "reused", f"Reused {capability} without creating new code.")])
            return self._outcome(task, capability, "reused", result, inspection, decisions)
        proposal = self._proposal(task, payload, blueprint)
        threat: dict[str, object] | None = None
        report: dict[str, object] | None = None
        for attempt in range(max_repairs + 1):
            decisions.append(CouncilDecision("builder", "complete" if attempt == 0 else "repaired", f"Produced constrained candidate '{proposal.name}' (attempt {attempt + 1})."))
            threat = self.proofs.threat_model(proposal)
            decisions.append(CouncilDecision("security", "complete", f"Threat model found {len(threat['policy_findings'])} policy findings."))
            report = self.proofs.evaluate(proposal)
            decisions.append(CouncilDecision("evaluator", "passed" if report["passed"] else "rejected", f"Trust score {report['trust_score']}; {report['failure_count']} proof failures."))
            if report["passed"] or not self.generator or attempt == max_repairs:
                break
            failure = "; ".join(result["detail"] for result in report["results"] if not result["passed"])
            decisions.append(CouncilDecision("planner", "repair_requested", f"Candidate failed proof: {failure}"))
            proposal = self.generator.propose(f"{task}\nRepair the prior candidate. Failure evidence: {failure}", payload)
        assert threat is not None and report is not None
        record = self.store.promote(self.project_id, proposal.name, proposal.source, proposal.provenance, report, approval_policy, threat)
        if record.state != "trusted":
            decisions.append(CouncilDecision("governor", record.state, "Capability was retained as evidence but not executed."))
            return self._outcome(task, capability, record.state, None, inspection, decisions, threat, report, record)
        agent = ForgeAgent(self.registry, emit=lambda _: None)
        result = agent._verify_and_run(proposal, payload)
        decisions.append(CouncilDecision("governor", "trusted", f"Promoted {record.name}@v{record.version} after policy and proof."))
        return self._outcome(task, capability, "trusted", result, inspection, decisions, threat, report, record)

    def _proposal(self, task: str, payload: dict[str, object], blueprint: object | None) -> ToolProposal:
        if self.generator:
            return self.generator.propose(task, payload)
        if blueprint is None:
            raise RuntimeError("A live gpt-5.6-terra generator is required for an unknown capability. Set OPENAI_API_KEY or choose a supported curated capability.")
        return ToolProposal(blueprint.name, blueprint.description, blueprint.source, ((blueprint.test_input, blueprint.expected_output),), "curated offline Foundry proposal")

    @staticmethod
    def _slug(task: str) -> str:
        import re
        return "_".join(re.findall(r"[a-z0-9]+", task.lower())[:5]) or "unnamed_capability"

    @staticmethod
    def _outcome(task: str, capability: str, status: str, result: object, inspection: dict[str, object], decisions: list[CouncilDecision], threat: dict[str, object] | None = None, proof: dict[str, object] | None = None, record: object | None = None) -> dict[str, object]:
        return {"task": task, "capability": capability, "status": status, "result": result, "council": [asdict(decision) for decision in decisions], "inspection": {"impact": inspection["impact"], "existing_trusted_tool": inspection["existing_trusted_tool"], "match_count": len(inspection["repository_matches"])}, "threat_model": threat, "proof": proof, "memory_record": asdict(record) if record else None}
