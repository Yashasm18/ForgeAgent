"""ForgeAgent's explicit gap -> generate -> verify -> persist -> reuse loop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from audit import AuditLog
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
)


class ForgeAgent:
    def __init__(self, registry: ToolRegistry, emit: Callable[[str], None] = print, generator: ProposalGenerator | None = None, audit: AuditLog | None = None):
        self.registry, self.emit, self.generator = registry, emit, generator
        self.audit = audit or AuditLog(registry.path.parent / "audit_log.jsonl")

    def forge(self, capability: str, payload: object) -> object:
        """Create, verify, persist, and run a model-proposed capability."""
        if not self.generator:
            raise RuntimeError("No GPT-5.6 generator configured. Set OPENAI_API_KEY and use live mode.")
        self.emit(f"\nREQUEST  {capability}")
        self.audit.record("capability_requested", capability, "Agent identified a capability gap", "pending")
        self.emit("PLAN     Asking GPT-5.6 for a constrained tool and edge-case tests...")
        proposal = self.generator.propose(capability, payload)
        return self._verify_and_run(proposal, payload)

    def _verify_and_run(self, proposal: ToolProposal, payload: object) -> object:
        tool = self.registry.get(proposal.name)
        if tool:
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
            tool = Tool(
                proposal.name, proposal.description, proposal.source, test_input, expected_output,
                self.registry.timestamp(),
                tests=[{"input": item, "expected_output": expected} for item, expected in proposal.tests],
                provenance=proposal.provenance,
            )
            self.registry.register(tool)
            self.audit.record("tool_trusted", tool.name, f"{len(proposal.tests)} deterministic proof cases passed; {proposal.provenance}", "trusted")
            self.emit(f"TRUST ✓  Tests passed. REGISTER ✓  {tool.name} is now reusable memory.")
        self.emit(f"RUN      Executing trusted skill: {tool.name}")
        answer = execute(tool.source, payload)
        self.audit.record("tool_executed", tool.name, "Trusted tool executed on task payload", "completed")
        self.emit("DONE     Result produced by a verified capability.")
        return answer

    def complete(self, task: str, payload: object) -> object:
        self.emit(f"\nTASK  {task}")
        blueprint = next((item for item in BLUEPRINTS if item.matches(task)), None)
        if not blueprint:
            raise ValueError("No safe generator blueprint for this task. Try a word-frequency or email-domain task.")
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
            self.audit.record("tool_trusted", tool.name, "Curated offline demonstration proof passed", "trusted")
            self.emit(f"VERIFY ✓  Sample test passed. REGISTER ✓  Toolkit now has {len(self.registry.list())} verified tool(s).")
        self.emit(f"RUN    Executing {tool.name} on task input...")
        answer = execute(tool.source, payload)
        self.audit.record("tool_executed", tool.name, "Trusted tool executed on task payload", "completed")
        self.emit("DONE   Result produced by verified tool.")
        return answer
