import tempfile
import unittest
from pathlib import Path

from agent import ForgeAgent
from agent import BLUEPRINTS
from generator import ToolProposal
from registry import ToolRegistry
from sandbox import execute


class StaticGenerator:
    def __init__(self, proposal):
        self.proposal = proposal

    def propose(self, capability, payload):
        return self.proposal


class SequenceGenerator:
    def __init__(self, proposals):
        self.proposals = iter(proposals)

    def propose(self, capability, payload):
        return next(self.proposals)


class PlannerGenerator(StaticGenerator):
    def plan(self, task, payload):
        return [
            {"id": "redact", "task": "Redact PII before sharing this support ticket", "payload": payload, "depends_on": []},
            {"id": "triage", "task": "Triage support risk for this customer incident", "payload": payload, "depends_on": ["redact"]},
        ]


class SemanticMatcherGenerator(StaticGenerator):
    """A live-capable matcher fixture; it never makes a network call."""

    semantic_matching_available = True

    def __init__(self, proposal, selected_name=None, error=None):
        super().__init__(proposal)
        self.selected_name = selected_name
        self.error = error
        self.calls = []

    def match_existing_capability(self, task, capabilities):
        self.calls.append((task, capabilities))
        if self.error:
            raise self.error
        return self.selected_name


GOOD = ToolProposal(
    "uppercase_tokens",
    "Return uppercase words from text.",
    'import re\ndef run(payload):\n    return re.findall(r"\\b[A-Z]{2,}\\b", payload["text"])\n',
    (({"text": "Ship API with JSON"}, ["API", "JSON"]), ({"text": "nothing"}, [])),
    "test fixture",
)


class ForgeTests(unittest.TestCase):
    def test_pii_redactor_removes_explicitly_labelled_secrets(self):
        blueprint = next(item for item in BLUEPRINTS if item.name == "pii_redactor")
        output = execute(
            blueprint.source,
            {"text": "Email yashas@example.com; secret code 89789. Secret message is: launch at dawn. API key: sk-demo-secret."},
        )
        self.assertNotIn("89789", output)
        self.assertNotIn("launch at dawn", output)
        self.assertNotIn("sk-demo-secret", output)
        self.assertIn("[SECRET]", output)
        self.assertIn("[SECRET_MESSAGE]", output)

    def test_verified_skill_is_persisted_and_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = ToolRegistry(Path(directory) / "skills.json")
            agent = ForgeAgent(registry, emit=lambda _: None, generator=StaticGenerator(GOOD))
            self.assertEqual(agent.forge("extract uppercase tokens", {"text": "Use API"}), ["API"])
            self.assertEqual(len(registry.list()), 1)
            self.assertEqual(agent.forge("extract uppercase tokens", {"text": "Use JSON"}), ["JSON"])
            self.assertEqual(registry.get("uppercase_tokens").reuse_count, 1)

    def test_unsafe_proposal_never_enters_memory(self):
        unsafe = ToolProposal("bad", "bad", 'import os\ndef run(payload):\n return []', (({}, []),), "test fixture")
        with tempfile.TemporaryDirectory() as directory:
            registry = ToolRegistry(Path(directory) / "skills.json")
            agent = ForgeAgent(registry, emit=lambda _: None, generator=StaticGenerator(unsafe))
            with self.assertRaises(RuntimeError):
                agent.forge("unsafe", {})
            self.assertEqual(registry.list(), [])

    def test_failed_proposal_is_repaired_before_it_enters_memory(self):
        broken = ToolProposal("uppercase_tokens", "bad", 'def run(payload):\n    return ["wrong"]\n', GOOD.tests, "test fixture")
        with tempfile.TemporaryDirectory() as directory:
            registry = ToolRegistry(Path(directory) / "skills.json")
            agent = ForgeAgent(registry, emit=lambda _: None, generator=SequenceGenerator([broken, GOOD]))
            self.assertEqual(agent.forge("extract uppercase tokens", {"text": "Use API"}, max_repairs=1), ["API"])
            self.assertEqual(registry.get("uppercase_tokens").version, 1)

    def test_verified_replacement_can_be_rolled_back(self):
        improved = ToolProposal(
            "uppercase_tokens", "Return uppercase words, unique.",
            'import re\ndef run(payload):\n    return sorted(set(re.findall(r"\\b[A-Z]{2,}\\b", payload["text"])))\n',
            (({"text": "API API JSON"}, ["API", "JSON"]),), "repair fixture",
        )
        with tempfile.TemporaryDirectory() as directory:
            registry = ToolRegistry(Path(directory) / "skills.json")
            agent = ForgeAgent(registry, emit=lambda _: None, generator=StaticGenerator(GOOD))
            agent.forge("extract uppercase tokens", {"text": "API"})
            agent._verify_and_run(improved, {"text": "API API JSON"}, force_candidate=True)
            self.assertEqual(registry.get("uppercase_tokens").version, 2)
            agent.rollback("uppercase_tokens", 1)
            self.assertEqual(registry.get("uppercase_tokens").version, 1)

    def test_user_task_is_planned_then_completed_in_dependency_order(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = ToolRegistry(Path(directory) / "skills.json")
            agent = ForgeAgent(registry, emit=lambda _: None, generator=PlannerGenerator(GOOD))
            result = agent.execute_user_task("Protect and triage incident", {"text": "ava@example.com says dashboard is down"})
            self.assertIn("redact", result)
            self.assertEqual(result["triage"]["priority"], "high")

    def test_live_semantic_matching_recovers_natural_capability_phrasing(self):
        task = "please fix the inconsistent dates in this log file"
        self.assertIsNone(ForgeAgent._keyword_blueprint(task))
        generator = SemanticMatcherGenerator(GOOD, selected_name="date_format_normalizer")
        with tempfile.TemporaryDirectory() as directory:
            agent = ForgeAgent(ToolRegistry(Path(directory) / "skills.json"), emit=lambda _: None, generator=generator)
            blueprint = agent._blueprint_for_task(task)
        self.assertEqual(blueprint.name, "date_format_normalizer")
        self.assertEqual(generator.calls[0][0], task)
        self.assertIn(
            {"name": "date_format_normalizer", "description": blueprint.description},
            generator.calls[0][1],
        )

    def test_offline_matching_is_identical_to_original_keyword_behavior(self):
        tasks = (
            "normalize date format in this import log",
            "please fix the inconsistent dates in this log file",
            "extract error code and line number from this stack trace",
        )
        with tempfile.TemporaryDirectory() as directory:
            agent = ForgeAgent(ToolRegistry(Path(directory) / "skills.json"), emit=lambda _: None)
            for task in tasks:
                # Object identity proves no wrapping or reinterpretation changed
                # the original first-match keyword result in offline mode.
                self.assertIs(agent._blueprint_for_task(task), ForgeAgent._keyword_blueprint(task))

    def test_semantic_matching_rejects_unknown_or_failed_model_selection(self):
        task = "please fix the inconsistent dates in this log file"
        with tempfile.TemporaryDirectory() as directory:
            registry = ToolRegistry(Path(directory) / "skills.json")
            fabricated = ForgeAgent(
                registry, emit=lambda _: None,
                generator=SemanticMatcherGenerator(GOOD, selected_name="invented_capability"),
            )
            unavailable = ForgeAgent(
                registry, emit=lambda _: None,
                generator=SemanticMatcherGenerator(GOOD, error=RuntimeError("network unavailable")),
            )
            self.assertIsNone(fabricated._blueprint_for_task(task))
            self.assertIsNone(unavailable._blueprint_for_task(task))


if __name__ == "__main__":
    unittest.main()
