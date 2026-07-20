import tempfile
import unittest
from pathlib import Path

from forgeagent.agent import ForgeAgent
from forgeagent.offline_intelligence import OfflineTemplateGenerator
from forgeagent.proof_engine import ProofEngine
from forgeagent.registry import ToolRegistry


class OfflineIntelligenceTests(unittest.TestCase):
    def test_offline_semantic_match_recovers_natural_date_request_without_api(self):
        with tempfile.TemporaryDirectory() as directory:
            agent = ForgeAgent(
                ToolRegistry(Path(directory) / "registry.json"),
                emit=lambda _: None,
                generator=OfflineTemplateGenerator(),
            )
            blueprint = agent._blueprint_for_task("Please fix the inconsistent dates in this log file")

        self.assertIsNotNone(blueprint)
        self.assertEqual(blueprint.name, "date_format_normalizer")

    def test_template_generator_forges_and_proves_invoice_extractor_offline(self):
        generator = OfflineTemplateGenerator()
        proposal = generator.propose("Extract invoice identifiers from these billing logs", {"text": "INV-2048"})

        report = ProofEngine().evaluate(proposal, adversarial_cases=generator.propose_adversarial_cases(proposal))

        self.assertEqual(proposal.name, "invoice_id_extractor")
        self.assertTrue(proposal.provenance.startswith("deterministic offline template"))
        self.assertTrue(report["passed"])
        self.assertIn("adversarial", report["coverage"])

    def test_offline_adversarial_cases_block_a_broken_invoice_template(self):
        generator = OfflineTemplateGenerator()
        proposal = generator.propose("Extract invoice IDs", {"text": "INV-1"})
        broken = proposal.__class__(
            proposal.name,
            proposal.description,
            "import re\ndef run(payload):\n    return re.findall(r'\\bINV-\\d+\\b', payload['text'])[:1]\n",
            proposal.tests,
            proposal.provenance,
            proposal.relationship,
        )

        report = ProofEngine().evaluate(broken, adversarial_cases=generator.propose_adversarial_cases(proposal))

        self.assertFalse(report["passed"])
        self.assertTrue(any(item["category"] == "adversarial" and not item["passed"] for item in report["results"]))

    def test_offline_planner_decomposes_known_incident_without_live_model(self):
        steps = OfflineTemplateGenerator().plan(
            "Redact PII, triage the support incident, and extract stack-trace error codes",
            {"text": "customer@example.com cannot access service; ERROR E_TIMEOUT at api.py:7"},
        )

        self.assertEqual([step["id"] for step in steps], ["redact", "triage", "extract_errors"])
        self.assertEqual(steps[1]["depends_on"], ["redact"])
        self.assertEqual(steps[2]["depends_on"], ["triage"])


if __name__ == "__main__":
    unittest.main()
