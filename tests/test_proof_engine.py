import unittest

from forgeagent.generator import ToolProposal
from forgeagent.proof_engine import ProofEngine


class ProofEngineTests(unittest.TestCase):
    def test_proven_candidate_receives_trust_score(self):
        proposal = ToolProposal("upper", "upper", "def run(payload):\n    return payload['text'].upper()\n", (({"text": "hi"}, "HI"), ({"text": ""}, "")), "test")
        report = ProofEngine().evaluate(proposal)
        self.assertTrue(report["passed"])
        self.assertGreaterEqual(report["trust_score"], 90)

    def test_unsafe_source_is_rejected_before_execution(self):
        proposal = ToolProposal("bad", "bad", "def run(payload):\n    return eval(payload['text'])\n", (({"text": "1"}, 1),), "test")
        report = ProofEngine().evaluate(proposal)
        self.assertFalse(report["passed"])
        self.assertIn("disallowed name reference: eval", report["policy_findings"])
