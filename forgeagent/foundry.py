"""ForgeAgent Capability Foundry: graph -> council -> proof -> governed memory."""

from __future__ import annotations

import ast
from dataclasses import asdict, dataclass
from pathlib import Path

from forgeagent.agent import BLUEPRINTS, ForgeAgent
from forgeagent.audit import AuditLog
from forgeagent.generator import ProofCase, ProposalGenerator, ToolProposal
from forgeagent.platform_store import PlatformStore
from forgeagent.proof_engine import ProofEngine
from forgeagent.repository_graph import RepositoryGraph
from forgeagent.registry import ToolRegistry


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
        repository_context = self._repository_context(inspection) if self.generator else None
        proposal = self._proposal(task, payload, blueprint, repository_context)
        threat: dict[str, object] | None = None
        report: dict[str, object] | None = None
        for attempt in range(max_repairs + 1):
            relationship = f" Relationship: {proposal.relationship}" if proposal.relationship else ""
            self._record_decision(
                decisions,
                capability,
                "builder",
                "complete" if attempt == 0 else "repaired",
                f"Produced constrained candidate '{proposal.name}' (attempt {attempt + 1}).{relationship}",
            )
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
            proposal = self.generator.propose(
                f"{task}\nRepair the prior candidate. Failure evidence: {failure}",
                payload,
                repository_context=repository_context,
            )
        assert threat is not None and report is not None
        record = self.store.promote(
            self.project_id, proposal.name, proposal.source, proposal.provenance,
            report, approval_policy, threat, requested_task=task,
        )
        if record.state != "trusted":
            self._record_decision(decisions, capability, "governor", record.state, "Capability was retained as evidence but not executed.")
            return self._outcome(task, capability, record.state, None, inspection, decisions, threat, report, record, proposal.relationship if self.generator else None)
        agent = ForgeAgent(self.registry, emit=lambda _: None)
        # A newly promoted proposal must still replace an existing registry
        # version through the full verification path; never treat a version
        # update as a cache hit.
        executed_proof_cases = sum(
            result["passed"] and result["category"] not in {"policy", "coverage"}
            for result in report["results"]
        )
        result = agent._verify_and_run(
            proposal,
            payload,
            force_candidate=self.registry.get(proposal.name) is not None,
            proof_case_count=executed_proof_cases,
        )
        self._record_decision(decisions, capability, "governor", "trusted", f"Promoted {record.name}@v{record.version} after policy and proof.")
        return self._outcome(task, capability, "trusted", result, inspection, decisions, threat, report, record, proposal.relationship if self.generator else None)

    def _proposal(self, task: str, payload: dict[str, object], blueprint: object | None, repository_context: str | None = None) -> ToolProposal:
        # A deterministic offline generator deliberately covers only a small,
        # reviewed template catalog.  Known blueprints still use their curated
        # offline proposals rather than asking that generator to invent them.
        if self.generator and not (getattr(self.generator, "offline_template_only", False) and blueprint is not None):
            return self.generator.propose(task, payload, repository_context=repository_context)
        if blueprint is None:
            raise RuntimeError("A live gpt-5.6-terra generator is required for an unknown capability. Set OPENAI_API_KEY or choose a supported curated capability.")
        return ToolProposal(blueprint.name, blueprint.description, blueprint.source, ((blueprint.test_input, blueprint.expected_output),), "curated offline Foundry proposal")

    def _repository_context(self, inspection: dict[str, object]) -> str | None:
        """Format only graph-matched definitions for a live proposal prompt.

        The graph supplies file paths and symbol names; this method re-parses
        only those definitions to avoid sending an entire repository (or an
        unrelated neighbouring function) to the generator.
        """
        impact = inspection.get("impact")
        graph = inspection.get("graph")
        if not isinstance(impact, dict) or not isinstance(graph, dict):
            return None
        paths = {value for value in impact.get("impact_candidates", []) if isinstance(value, str)}
        symbols = {value for value in impact.get("related_symbols", []) if isinstance(value, str)}
        nodes = graph.get("nodes", [])
        if not paths or not symbols or not isinstance(nodes, list):
            return None

        excerpts: list[str] = []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            path, label, kind = node.get("path"), node.get("label"), node.get("kind")
            if not isinstance(path, str) or not isinstance(label, str) or not isinstance(kind, str):
                continue
            if path not in paths or label not in symbols or kind not in {"function", "class", "capability"}:
                continue
            excerpt = self._symbol_excerpt(path, label, kind)
            if excerpt:
                excerpts.append(excerpt)
            if len(excerpts) == 2:
                break
        return "\n\n".join(excerpts) or None

    def _symbol_excerpt(self, relative_path: str, symbol: str, kind: str) -> str | None:
        """Return a bounded definition excerpt for one graph-matched symbol."""
        path = (self.root / relative_path).resolve()
        try:
            path.relative_to(self.root.resolve())
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text)
        except (OSError, SyntaxError, UnicodeDecodeError, ValueError):
            return None
        if kind in {"function", "class"}:
            definitions = (
                node for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == symbol
            )
            node = next(definitions, None)
            if node is None:
                return None
            docstring = ast.get_docstring(node) or "(no docstring)"
            source = ast.get_source_segment(text, node) or ""
            excerpt = "\n".join(source.splitlines()[:14])
            return f"File: {relative_path}\nSymbol: {symbol}\nDocstring: {docstring}\nExcerpt:\n{excerpt}"
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != "ToolBlueprint":
                continue
            if len(node.args) < 3 or not all(isinstance(arg, ast.Constant) and isinstance(arg.value, str) for arg in node.args[:3]):
                continue
            if node.args[0].value != symbol:
                continue
            description, source = node.args[1].value, node.args[2].value
            excerpt = "\n".join(source.splitlines()[:14])
            return f"File: {relative_path}\nCapability: {symbol}\nDescription: {description}\nExcerpt:\n{excerpt}"
        return None

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
    def _outcome(task: str, capability: str, status: str, result: object, inspection: dict[str, object], decisions: list[CouncilDecision], threat: dict[str, object] | None = None, proof: dict[str, object] | None = None, record: object | None = None, relationship: str | None = None) -> dict[str, object]:
        outcome = {"task": task, "capability": capability, "status": status, "result": result, "council": [asdict(decision) for decision in decisions], "inspection": {"impact": inspection["impact"], "existing_trusted_tool": inspection["existing_trusted_tool"], "match_count": len(inspection["repository_matches"])}, "threat_model": threat, "proof": proof, "memory_record": asdict(record) if record else None}
        if relationship:
            outcome["relationship"] = relationship
        return outcome
