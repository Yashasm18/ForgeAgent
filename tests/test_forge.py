import tempfile
import unittest
from pathlib import Path

from agent import ForgeAgent
from generator import ToolProposal
from registry import ToolRegistry


class StaticGenerator:
    def __init__(self, proposal):
        self.proposal = proposal

    def propose(self, capability, payload):
        return self.proposal


GOOD = ToolProposal(
    "uppercase_tokens",
    "Return uppercase words from text.",
    'import re\ndef run(payload):\n    return re.findall(r"\\b[A-Z]{2,}\\b", payload["text"])\n',
    (({"text": "Ship API with JSON"}, ["API", "JSON"]), ({"text": "nothing"}, [])),
    "test fixture",
)


class ForgeTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
