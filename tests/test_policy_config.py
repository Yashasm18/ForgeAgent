import contextlib
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

from forgeagent.generator import ToolProposal
from forgeagent.governance import assess
from forgeagent.policy_config import load_policy
from forgeagent.proof_engine import ProofEngine
from forgeagent.sandbox import SandboxError, execute, policy_violations


@contextlib.contextmanager
def policy_workspace(contents: str | None):
    previous = Path.cwd()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        if contents is not None:
            (root / "forgeagent-policy.yml").write_text(contents)
        os.chdir(root)
        try:
            yield root
        finally:
            os.chdir(previous)


@unittest.skipUnless(importlib.util.find_spec("yaml"), "optional PyYAML dependency is not installed")
class PolicyConfigTests(unittest.TestCase):
    def test_adversarial_allowed_import_cannot_add_to_hardcoded_floor(self):
        with policy_workspace("allowed_imports:\n  - re\n  - subprocess\n"):
            policy = load_policy()
            findings = policy_violations("import subprocess\ndef run(payload): return {}\n")

        self.assertEqual(policy.allowed_imports, frozenset({"re"}))
        self.assertIn("disallowed import: subprocess", findings)

    def test_adversarial_required_categories_cannot_remove_hardcoded_minimum(self):
        with policy_workspace("required_proof_categories:\n  - normal\n"):
            policy = load_policy()

        self.assertTrue({"normal", "edge", "contract"}.issubset(policy.required_proof_categories))

    def test_policy_can_narrow_allowed_imports(self):
        source = "import re\ndef run(payload): return re.findall(r'\\d+', payload['text'])\n"
        with policy_workspace("allowed_imports:\n  - json\n"):
            findings = policy_violations(source)
            with self.assertRaises(SandboxError):
                execute(source, {"text": "a12"})

        self.assertIn("disallowed import: re", findings)

    def test_malformed_policy_falls_back_to_exact_baseline(self):
        source = "import re\ndef run(payload): return re.findall(r'\\d+', payload['text'])\n"
        with policy_workspace(None):
            baseline_findings = policy_violations(source)
            baseline = ProofEngine().evaluate(
                ToolProposal("digits", "digits", source, (({"text": "a12"}, ["12"]),), "test")
            )
        with policy_workspace("allowed_imports: [re\n"):
            malformed_findings = policy_violations(source)
            malformed = ProofEngine().evaluate(
                ToolProposal("digits", "digits", source, (({"text": "a12"}, ["12"]),), "test")
            )

        self.assertEqual(malformed_findings, baseline_findings)
        self.assertEqual(json.dumps(malformed, sort_keys=True), json.dumps(baseline, sort_keys=True))

    def test_no_policy_file_preserves_baseline_behavior(self):
        source = "import re\ndef run(payload): return re.findall(r'\\d+', payload['text'])\n"
        with policy_workspace(None):
            policy = load_policy()
            self.assertEqual(execute(source, {"text": "a12 b34"}), ["12", "34"])

        self.assertEqual(policy.allowed_imports, frozenset({"collections", "csv", "datetime", "json", "math", "re", "statistics", "string"}))
        self.assertEqual(policy.required_proof_categories, frozenset({"normal", "edge", "contract"}))

    def test_review_rules_can_only_add_a_human_approval_hold(self):
        with policy_workspace("auto_promotion_rules:\n  require_human_review: true\n"):
            decision = assess("auto", "normalizer", "test", {"passed": True, "trust_score": 100})

        self.assertEqual(decision.decision, "pending")
        self.assertTrue(decision.requires_human)
