import tempfile
import unittest
from pathlib import Path

from foundry import CapabilityFoundry
from generator import ToolProposal


class SequenceGenerator:
    def __init__(self, proposals):
        self.proposals = iter(proposals)

    def propose(self, task, payload):
        return next(self.proposals)


class FoundryTests(unittest.TestCase):
    def test_curated_capability_is_proven_then_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = root / "registry.json"
            foundry = CapabilityFoundry(registry, root=root)
            first = foundry.run("Find word frequency in this customer feedback", {"text": "tools tools reliable"})
            self.assertEqual(first["status"], "trusted")
            second = foundry.run("Find word frequency in this customer feedback", {"text": "tools"})
            self.assertEqual(second["status"], "reused")

    def test_unknown_capability_needs_live_generator(self):
        with tempfile.TemporaryDirectory() as directory:
            foundry = CapabilityFoundry(Path(directory) / "registry.json", root=directory)
            with self.assertRaises(RuntimeError):
                foundry.run("Extract invoice IDs", {"text": "INV-1"})

    def test_live_generator_candidate_is_repaired_before_promotion(self):
        broken = ToolProposal("invoice_ids", "broken", "def run(payload):\n    return []\n", (({"text": "INV-1"}, ["INV-1"]),), "fixture")
        repaired = ToolProposal("invoice_ids", "repaired", "import re\ndef run(payload):\n    return re.findall(r'INV-\\d+', payload['text'])\n", (({"text": "INV-1"}, ["INV-1"]),), "fixture")
        with tempfile.TemporaryDirectory() as directory:
            foundry = CapabilityFoundry(Path(directory) / "registry.json", root=directory, generator=SequenceGenerator([broken, repaired]))
            outcome = foundry.run("Extract invoice IDs", {"text": "INV-1"})
            self.assertEqual(outcome["status"], "trusted")
            self.assertIn("repair_requested", [entry["status"] for entry in outcome["council"]])
