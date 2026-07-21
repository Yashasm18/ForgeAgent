import tempfile
import unittest
from pathlib import Path

from forgeagent.foundry import CapabilityFoundry
from forgeagent.generator import ProofCase, ToolProposal
from forgeagent.demo_tasks import RECORDED_ADVERSARIAL_EXAMPLE


class SequenceGenerator:
    def __init__(self, proposals):
        self.proposals = iter(proposals)
        self.tasks = []

    def propose(self, task, payload, repository_context=None):
        self.tasks.append(task)
        return next(self.proposals)


class AdversarialGenerator:
    def __init__(self, proposal, cases):
        self.proposal = proposal
        self.cases = cases

    def propose(self, task, payload, repository_context=None):
        return self.proposal

    def propose_adversarial_cases(self, proposal):
        return self.cases


class FoundryTests(unittest.TestCase):
    def test_live_generator_receives_matched_repository_context_and_relationship(self):
        """The Foundry gives a live proposal only the code graph says is relevant."""

        class CapturingGenerator:
            def __init__(self):
                self.contexts = []

            def propose(self, task, payload, repository_context=None):
                self.contexts.append(repository_context)
                return ToolProposal(
                    "date_format_normalizer",
                    "Normalize dates.",
                    "def run(payload):\n    return payload['text']\n",
                    (({"text": "2026/7/4"}, "2026/7/4"),),
                    "fake live proposal",
                    "EXTEND: Reuse the repository helper's ISO-date pattern while adding import-log handling.",
                )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "calendar_helpers.py").write_text(
                'def canonicalize_value(payload):\n'
                '    """Normalize date values into ISO calendar format."""\n'
                '    return payload\n'
            )
            generator = CapturingGenerator()
            foundry = CapabilityFoundry(root / "registry.json", root=root, generator=generator)
            outcome = foundry.run("Normalize inconsistent date formats in this import log", {"text": "2026/7/4"})
            audit_text = (root / "audit_log.jsonl").read_text(encoding="utf-8")

        self.assertEqual(outcome["status"], "trusted")
        self.assertEqual(len(generator.contexts), 1)
        context = generator.contexts[0]
        self.assertIn("calendar_helpers.py", context)
        self.assertIn("canonicalize_value", context)
        self.assertIn("Normalize date values into ISO calendar format.", context)
        self.assertEqual(outcome["relationship"], "EXTEND: Reuse the repository helper's ISO-date pattern while adding import-log handling.")
        builder = next(item for item in outcome["council"] if item["role"] == "builder")
        self.assertIn("EXTEND:", builder["detail"])
        self.assertIn("EXTEND:", audit_text)

    def test_curated_capability_is_proven_then_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = root / "registry.json"
            foundry = CapabilityFoundry(registry, root=root)
            first = foundry.run("Normalize inconsistent date formats in this import log", {"text": "batch=A 03/07/2026"})
            self.assertEqual(first["status"], "trusted")
            second = foundry.run("Normalize inconsistent date formats in this import log", {"text": "batch=B 2026/7/4"})
            self.assertEqual(second["status"], "reused")

    def test_newly_forged_record_persists_actual_proof_engine_case_count(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            foundry = CapabilityFoundry(root / "registry.json", root=root)
            outcome = foundry.run("Normalize inconsistent date formats in this import log", {"text": "batch=A 03/07/2026"})
            actual_cases = sum(
                result["passed"] and result["category"] not in {"policy", "coverage"}
                for result in outcome["proof"]["results"]
            )
            recorded = foundry.registry.get("date_format_normalizer")
        self.assertEqual(outcome["status"], "trusted")
        self.assertEqual(actual_cases, 3)
        self.assertEqual(recorded.proof_case_count, actual_cases)

    def test_unknown_capability_needs_live_generator(self):
        with tempfile.TemporaryDirectory() as directory:
            foundry = CapabilityFoundry(Path(directory) / "registry.json", root=directory)
            with self.assertRaises(RuntimeError):
                foundry.run("Extract invoice IDs", {"text": "INV-1"})

    def test_live_generator_candidate_is_repaired_before_promotion(self):
        broken = ToolProposal("invoice_ids", "broken", "def run(payload):\n    return []\n", (({"text": "INV-1"}, ["INV-1"]),), "fixture")
        repaired = ToolProposal("invoice_ids", "repaired", "import re\ndef run(payload):\n    return re.findall(r'INV-\\d+', payload['text'])\n", (({"text": "INV-1"}, ["INV-1"]),), "fixture")
        with tempfile.TemporaryDirectory() as directory:
            generator = SequenceGenerator([broken, repaired])
            foundry = CapabilityFoundry(Path(directory) / "registry.json", root=directory, generator=generator)
            outcome = foundry.run("Extract invoice IDs", {"text": "INV-1"})
            self.assertEqual(outcome["status"], "trusted")
            self.assertIn("repair_requested", [entry["status"] for entry in outcome["council"]])
            self.assertEqual(len(generator.tasks), 2)
            repair_task = generator.tasks[1]
            self.assertIn("Prior candidate source:", repair_task)
            self.assertIn("def run(payload):\n    return []", repair_task)
            self.assertIn('"input": {"text": "INV-1"}', repair_task)
            self.assertIn("Exact failed proof cases", repair_task)

    def test_live_named_capability_reuses_exact_request_without_a_second_generation(self):
        """Live names need not match task slugs; request lineage still reuses safely."""
        proposal = ToolProposal(
            "extract_invoice_ids", "Extract unique invoice IDs.",
            "import re\ndef run(payload):\n    return list(dict.fromkeys(re.findall(r'(?<![A-Za-z0-9_-])INV-[0-9]+(?![A-Za-z0-9_-])', payload['text'])))\n",
            (({"text": "INV-2048, INV-2048, INV-9910"}, ["INV-2048", "INV-9910"]),),
            "fake live proposal",
        )
        task = "Build a pure Python invoice ID extractor for exact ASCII INV-number tokens"
        with tempfile.TemporaryDirectory() as directory:
            generator = SequenceGenerator([proposal])
            foundry = CapabilityFoundry(Path(directory) / "registry.json", root=directory, generator=generator)
            forged = foundry.run(task, {"text": "INV-2048, INV-9910"})
            reused = foundry.run(task, {"text": "INV-77, INV-77, INV-88"})

        self.assertEqual(forged["status"], "trusted")
        self.assertEqual(reused["status"], "reused")
        self.assertEqual(reused["result"], ["INV-77", "INV-88"])
        self.assertEqual(reused["inspection"]["existing_trusted_tool"]["name"], "extract_invoice_ids")
        self.assertEqual(len(generator.tasks), 1)

    def test_adversarial_generator_case_blocks_promotion(self):
        proposal = ToolProposal(
            "slug_normalizer", "Normalize a release name into a slug.",
            "def run(payload):\n    return {'slug': payload['name'].strip().lower().replace(' ', '-')}\n",
            (({"name": "Release Candidate"}, {"slug": "release-candidate"}),),
            "fake live proposal",
        )
        adversarial = ProofCase(
            "adversarial", {"name": "release  candidate"}, {"slug": "release-candidate"},
            "Repeated whitespace must collapse to one slug separator.",
        )
        with tempfile.TemporaryDirectory() as directory:
            foundry = CapabilityFoundry(
                Path(directory) / "registry.json", root=directory,
                generator=AdversarialGenerator(proposal, [adversarial]),
            )
            outcome = foundry.run("Normalize a release name", {"name": "release  candidate"}, max_repairs=0, adversarial_proof=True)
            self.assertEqual(outcome["status"], "rejected")
            self.assertFalse(outcome["proof"]["passed"])
            self.assertIn("adversarial", outcome["proof"]["coverage"])
            self.assertIn("Expected {'slug': 'release-candidate'}, got {'slug': 'release--candidate'}", str(outcome["proof"]["results"]))
            self.assertEqual(foundry.registry.list(), [])

    def test_offline_curated_flow_is_unchanged_without_adversarial_flag(self):
        with tempfile.TemporaryDirectory() as directory:
            foundry = CapabilityFoundry(Path(directory) / "registry.json", root=directory)
            outcome = foundry.run("Normalize inconsistent date formats in this import log", {"text": "batch=A 03/07/2026"})
            self.assertEqual(outcome["status"], "trusted")
            self.assertNotIn("relationship", outcome)
            with self.assertRaisesRegex(RuntimeError, "Live adversarial proof requires OPENAI_API_KEY"):
                foundry.run("Normalize inconsistent date formats in this import log", {"text": "batch=A 03/07/2026"}, adversarial_proof=True)
            self.assertEqual(RECORDED_ADVERSARIAL_EXAMPLE["label"], "curated offline adversarial proof recording")
