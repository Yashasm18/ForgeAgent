"""ForgeAgent's explicit gap -> generate -> verify -> persist -> reuse loop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from audit import AuditLog
from capability_graph import CapabilityGraph, Edge
from generator import ProposalGenerator, ToolProposal
from registry import Tool, ToolRegistry
from sandbox import SandboxError, execute, policy_violations


@dataclass(frozen=True)
class ToolBlueprint:
    name: str
    description: str
    source: str
    test_input: object
    expected_output: object
    matches: Callable[[str], bool]


@dataclass(frozen=True)
class PlanStep:
    """One capability needed to finish a user task, with explicit dependencies."""

    id: str
    task: str
    payload: dict[str, object]
    depends_on: tuple[str, ...] = ()


BLUEPRINTS = (
    ToolBlueprint(
        "word_frequency",
        "Count normalized words in text and return descending frequency rows.",
        '''import re
def run(payload):
    words = re.findall(r"[a-z0-9']+", payload["text"].lower())
    counts = {}
    for word in words:
        counts[word] = counts.get(word, 0) + 1
    return [{"word": word, "count": count} for word, count in sorted(counts.items(), key=lambda row: (-row[1], row[0]))]
''',
        {"text": "Build, build better tools."},
        [{"word": "build", "count": 2}, {"word": "better", "count": 1}, {"word": "tools", "count": 1}],
        lambda task: any(word in task.lower() for word in ("word frequency", "word count", "frequent words")),
    ),
    ToolBlueprint(
        "email_domain_summary",
        "Extract email domains and count them case-insensitively.",
        '''import re
def run(payload):
    emails = re.findall(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\\.[A-Za-z]{2,})", payload["text"])
    counts = {}
    for domain in emails:
        domain = domain.lower()
        counts[domain] = counts.get(domain, 0) + 1
    return [{"domain": domain, "count": count} for domain, count in sorted(counts.items(), key=lambda row: (-row[1], row[0]))]
''',
        {"text": "a@OpenAI.com; b@openai.com; c@example.org"},
        [{"domain": "openai.com", "count": 2}, {"domain": "example.org", "count": 1}],
        lambda task: any(word in task.lower() for word in ("email domain", "email domains", "domain summary")),
    ),
    ToolBlueprint(
        "pii_redactor",
        "Redact email addresses, phone numbers, and card-like number sequences from text.",
        '''import re
def run(payload):
    text = payload["text"]
    text = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}", "[EMAIL]", text)
    text = re.sub(r"(?<!\\w)(?:\\+?\\d[ -]?){8,15}(?!\\w)", "[PHONE]", text)
    text = re.sub(r"\\b(?:\\d[ -]?){13,19}\\b", "[CARD]", text)
    return text
''',
        {"text": "Email ava@example.com or call +1 415 555 0112."},
        "Email [EMAIL] or call [PHONE].",
        lambda task: any(phrase in task.lower() for phrase in ("redact pii", "redact personal", "remove personal")),
    ),
    ToolBlueprint(
        "support_risk_triage",
        "Classify a support ticket's operational risk with explainable keyword signals.",
        '''def run(payload):
    text = payload["text"].lower()
    signals = []
    if any(word in text for word in ("breach", "security", "leak", "unauthorized")):
        signals.append("security")
    if any(word in text for word in ("outage", "down", "cannot access", "broken")):
        signals.append("service")
    if any(word in text for word in ("cancel", "churn", "competitor", "refund")):
        signals.append("retention")
    priority = "critical" if "security" in signals else "high" if "service" in signals else "medium" if "retention" in signals else "low"
    return {"priority": priority, "signals": signals}
''',
        {"text": "Our dashboard is down and customers cannot access their reports."},
        {"priority": "high", "signals": ["service"]},
        lambda task: any(phrase in task.lower() for phrase in ("triage support", "support risk", "churn risk")),
    ),
)


class ForgeAgent:
    def __init__(self, registry: ToolRegistry, emit: Callable[[str], None] = print, generator: ProposalGenerator | None = None, audit: AuditLog | None = None, graph: CapabilityGraph | None = None):
        self.registry, self.emit, self.generator = registry, emit, generator
        self.audit = audit or AuditLog(registry.path.parent / "audit_log.jsonl")
        self.graph = graph or CapabilityGraph(registry.path.parent / "capability_graph.json")

    def forge(self, capability: str, payload: object, max_repairs: int = 2) -> object:
        """Create, verify, persist, and run a model-proposed capability."""
        if not self.generator:
            raise RuntimeError("No GPT-5.6 generator configured. Set OPENAI_API_KEY and use live mode.")
        self.emit(f"\nREQUEST  {capability}")
        self.audit.record("capability_requested", capability, "Agent identified a capability gap", "pending")
        self.emit("PLAN     Asking GPT-5.6 for a constrained tool and edge-case tests...")
        failure = ""
        for attempt in range(max_repairs + 1):
            prompt = capability if not failure else f"{capability}. Repair the previous proposal; failure: {failure}"
            proposal = self.generator.propose(prompt, payload)
            try:
                return self._verify_and_run(proposal, payload, force_candidate=attempt > 0)
            except (SandboxError, RuntimeError) as exc:
                failure = str(exc)
                self.audit.record("repair_requested", capability, f"attempt {attempt + 1}: {failure}", "retrying")
                self.emit(f"REPAIR   Candidate failed; preparing repair {attempt + 1}/{max_repairs}...")
        raise RuntimeError(f"ForgeAgent exhausted {max_repairs + 1} verified attempts: {failure}")

    def _verify_and_run(self, proposal: ToolProposal, payload: object, force_candidate: bool = False) -> object:
        existing = self.registry.get(proposal.name)
        if existing and not force_candidate:
            tool = existing
            self.emit(f"REUSE ✓  Verified tool already exists: {tool.name}")
            tool = self.registry.mark_reused(tool.name)
            self.audit.record("tool_reused", tool.name, f"Reuse count is now {tool.reuse_count}", "trusted")
        else:
            self.emit(f"FORGE    Candidate skill: {proposal.name}")
            findings = policy_violations(proposal.source)
            if findings:
                detail = "; ".join(findings)
                self.audit.record("policy_rejected", proposal.name, detail, "rejected")
                self.emit(f"REJECT ✗  Policy gate blocked candidate: {detail}")
                raise SandboxError(detail)
            self.emit(f"VERIFY   Running {len(proposal.tests)} deterministic tests in isolated sandbox...")
            try:
                for test_input, expected_output in proposal.tests:
                    actual = execute(proposal.source, test_input)
                    if actual != expected_output:
                        raise RuntimeError("test output did not match the expected output")
            except (SandboxError, RuntimeError) as exc:
                self.audit.record("verification_rejected", proposal.name, str(exc), "rejected")
                self.emit(f"REJECT ✗  {proposal.name} never entered memory: {exc}")
                raise
            test_input, expected_output = proposal.tests[0]
            candidate = Tool(
                proposal.name, proposal.description, proposal.source, test_input, expected_output,
                self.registry.timestamp(),
                tests=[{"input": item, "expected_output": expected} for item, expected in proposal.tests],
                provenance=proposal.provenance,
            )
            if existing and force_candidate:
                tool = self.registry.replace(existing, candidate)
                self.graph.link_replacement(tool.name, tool.replaces_version or 1, tool.version)
                self.audit.record("tool_repaired", tool.name, f"v{tool.version} supersedes v{tool.replaces_version}", "trusted")
            else:
                tool = candidate
                self.registry.register(tool)
            self.graph.record_skill(tool.name, tool.version, tool.dependencies, tool.provenance)
            self.audit.record("tool_trusted", tool.name, f"{len(proposal.tests)} deterministic proof cases passed; {proposal.provenance}", "trusted")
            self.emit(f"TRUST ✓  Tests passed. REGISTER ✓  {tool.name} is now reusable memory.")
        self.emit(f"RUN      Executing trusted skill: {tool.name}")
        answer = execute(tool.source, payload)
        self.audit.record("tool_executed", tool.name, "Trusted tool executed on task payload", "completed")
        self.emit("DONE     Result produced by a verified capability.")
        return answer

    def rollback(self, capability: str, version: int) -> Tool:
        tool = self.registry.rollback(capability, version)
        self.graph.link_rollback(capability, version)
        self.audit.record("tool_rolled_back", capability, f"Reactivated v{version}", "trusted")
        self.emit(f"ROLLBACK ✓  {capability} v{version} is active again.")
        return tool

    def execute_plan(self, user_task: str, steps: Iterable[PlanStep]) -> dict[str, object]:
        """Resolve a multi-skill task in dependency order, learning on a gap."""
        steps_by_id = {step.id: step for step in steps}
        pending = dict(steps_by_id)
        outputs: dict[str, object] = {}
        while pending:
            ready = [step for step in pending.values() if all(dep in outputs for dep in step.depends_on)]
            if not ready:
                raise ValueError("Capability plan has an unresolved or cyclic dependency")
            for step in ready:
                self.emit(f"\nPLAN STEP  {step.id}  ← {', '.join(step.depends_on) or 'root'}")
                payload = dict(step.payload)
                payload["upstream"] = {dep: outputs[dep] for dep in step.depends_on}
                blueprint = next((item for item in BLUEPRINTS if item.matches(step.task)), None)
                capability = blueprint.name if blueprint else step.task
                self.graph.record_task_need(user_task, capability)
                try:
                    outputs[step.id] = self.complete(step.task, payload) if blueprint else self.forge(step.task, payload)
                except (SandboxError, RuntimeError, KeyError) as exc:
                    self.audit.record("task_step_failed", step.id, str(exc), "failed")
                    if not self.generator:
                        raise RuntimeError(f"Plan step '{step.id}' needs a new skill but no live generator is configured") from exc
                    outputs[step.id] = self.forge(step.task, payload)
                tool = self.registry.get(capability)
                if tool:
                    self.graph.link_task_to_skill(user_task, tool.name, tool.version)
                    for dependency in step.depends_on:
                        upstream_step = steps_by_id[dependency]
                        upstream_tool = self._tool_for_task(upstream_step.task)
                        if upstream_tool:
                            self.graph.add_edge(Edge(self.graph.skill_id(tool.name, tool.version), self.graph.skill_id(upstream_tool.name, upstream_tool.version), "depends_on"))
                del pending[step.id]
        return outputs

    def execute_user_task(self, user_task: str, payload: dict[str, object]) -> dict[str, object]:
        """Plan a user task, then learn/repair every missing capability needed to finish it."""
        if not self.generator or not hasattr(self.generator, "plan"):
            raise RuntimeError("A GPT-5.6 planner is required to autonomously decompose an unknown user task")
        raw_steps = self.generator.plan(user_task, payload)
        steps = tuple(
            PlanStep(
                str(item["id"]), str(item["task"]), dict(item.get("payload", payload)),
                tuple(str(dep) for dep in item.get("depends_on", [])),
            )
            for item in raw_steps
        )
        self.audit.record("task_planned", user_task, f"GPT-5.6 proposed {len(steps)} dependent capability steps", "pending")
        return self.execute_plan(user_task, steps)

    def _tool_for_task(self, task: str) -> Tool | None:
        blueprint = next((item for item in BLUEPRINTS if item.matches(task)), None)
        return self.registry.get(blueprint.name) if blueprint else None

    def complete(self, task: str, payload: object) -> object:
        self.emit(f"\nTASK  {task}")
        blueprint = next((item for item in BLUEPRINTS if item.matches(task)), None)
        if not blueprint:
            raise ValueError("No safe generator blueprint for this task. Try a word-frequency or email-domain task.")
        self.graph.record_task_need(task, blueprint.name)
        tool = self.registry.get(blueprint.name)
        if tool:
            self.emit(f"REUSE ✓  Found verified tool: {tool.name}")
            tool = self.registry.mark_reused(tool.name)
            self.audit.record("tool_reused", tool.name, f"Reuse count is now {tool.reuse_count}", "trusted")
        else:
            self.emit(f"GAP    I need '{blueprint.name}', and I do not have it. I will build it.")
            self.emit(f"BUILD  Generated executable tool: {blueprint.name}")
            self.emit("TEST   Running mandatory sample test in isolated sandbox...")
            try:
                result = execute(blueprint.source, blueprint.test_input)
            except SandboxError as exc:
                self.emit(f"REJECT ✗  Test could not run: {exc}")
                raise
            if result != blueprint.expected_output:
                self.emit("REJECT ✗  Test output did not match expected result; tool was not registered.")
                raise RuntimeError("Generated tool failed verification")
            tool = Tool(blueprint.name, blueprint.description, blueprint.source, blueprint.test_input, blueprint.expected_output, self.registry.timestamp())
            self.registry.register(tool)
            self.graph.record_skill(tool.name, tool.version, tool.dependencies, "curated offline demonstration")
            self.audit.record("tool_trusted", tool.name, "Curated offline demonstration proof passed", "trusted")
            self.emit(f"VERIFY ✓  Sample test passed. REGISTER ✓  Toolkit now has {len(self.registry.list())} verified tool(s).")
        self.emit(f"RUN    Executing {tool.name} on task input...")
        answer = execute(tool.source, payload)
        self.graph.link_task_to_skill(task, tool.name, tool.version)
        self.audit.record("tool_executed", tool.name, "Trusted tool executed on task payload", "completed")
        self.emit("DONE   Result produced by verified tool.")
        return answer
