import tempfile
import unittest
from pathlib import Path

from forgeagent.platform_store import PlatformStore


def proof_with_cases(payload: object, expected: object) -> dict[str, object]:
    return {
        "passed": True,
        "trust_score": 100,
        "coverage": ["contract", "edge", "normal"],
        "results": [
            {"category": "policy", "passed": True, "rationale": "policy", "detail": "clean"},
            {"category": "normal", "passed": True, "rationale": "normal", "detail": "ok"},
            {"category": "edge", "passed": True, "rationale": "edge", "detail": "ok"},
            {"category": "contract", "passed": True, "rationale": "contract", "detail": "ok"},
            {"category": "coverage", "passed": True, "rationale": "coverage", "detail": "complete"},
        ],
        "cases": [
            {"category": "normal", "input": payload, "expected_output": expected, "rationale": "stored contract"},
            {"category": "edge", "input": payload, "expected_output": expected, "rationale": "stored boundary"},
            {"category": "contract", "input": payload, "expected_output": expected, "rationale": "stored JSON contract"},
        ],
    }


class CapabilityMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = PlatformStore(Path(self.directory.name) / "foundry.sqlite3")
        self.record = self.store.promote(
            "team/billing",
            "invoice_echo",
            "def run(payload):\n    return payload['invoice_id']\n",
            "test fixture",
            proof_with_cases({"invoice_id": "INV-9"}, "INV-9"),
        )

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def test_reproduced_incorrect_feedback_becomes_regression_evidence_and_quarantines(self):
        feedback = self.store.record_feedback(
            self.record.id,
            reporter="Ada",
            verdict="incorrect",
            summary="The parser omitted the second invoice identifier.",
            payload={"invoice_id": "INV-9 INV-10"},
            expected_output=["INV-9", "INV-10"],
        )

        self.assertEqual(feedback["status"], "reproduced_mismatch")
        self.assertEqual(self.store.get(self.record.id).state, "quarantined")
        regressions = self.store.regression_cases(self.record.id)
        self.assertEqual(len(regressions), 1)
        self.assertEqual(regressions[0]["expected_output"], ["INV-9", "INV-10"])
        self.assertIn("feedback_regression_quarantined", [event["kind"] for event in self.store.events("team/billing")])

    def test_contract_drift_replays_stored_evidence_and_quarantines_only_on_failure(self):
        first = self.store.check_contract_drift("team/billing")
        self.assertEqual(first["passed"], 1)
        self.assertEqual(first["quarantined"], 0)
        self.assertEqual(self.store.get(self.record.id).state, "trusted")

        self.store.db.execute(
            "UPDATE capabilities SET source = ? WHERE id = ?",
            ("def run(payload):\n    return 'contract drift'\n", self.record.id),
        )
        self.store.db.commit()

        second = self.store.check_contract_drift("team/billing")
        self.assertEqual(second["passed"], 0)
        self.assertEqual(second["quarantined"], 1)
        self.assertEqual(second["checks"][0]["state"], "quarantined")
        self.assertEqual(self.store.get(self.record.id).state, "quarantined")
        self.assertIn("contract_drift_quarantined", [event["kind"] for event in self.store.events("team/billing")])

    def test_legacy_proof_without_replayable_cases_reports_evidence_unavailable(self):
        legacy = self.store.promote(
            "team/billing",
            "legacy",
            "def run(payload):\n    return payload\n",
            "legacy fixture",
            {"passed": True, "trust_score": 90},
        )

        report = self.store.check_contract_drift("team/billing", capability_id=legacy.id)

        self.assertEqual(report["unavailable"], 1)
        self.assertEqual(report["checks"][0]["status"], "evidence_unavailable")
        self.assertEqual(self.store.get(legacy.id).state, "trusted")

    def test_repaired_successor_must_pass_inherited_feedback_regression_before_trust(self):
        self.store.record_feedback(
            self.record.id,
            reporter="Ada",
            verdict="incorrect",
            summary="The parser omitted the second invoice identifier.",
            payload={"invoice_id": "INV-9 INV-10"},
            expected_output=["INV-9", "INV-10"],
        )

        rejected = self.store.promote(
            "team/billing",
            "invoice_echo",
            "def run(payload):\n    return payload['invoice_id']\n",
            "unrepaired successor",
            proof_with_cases({"invoice_id": "INV-9"}, "INV-9"),
        )
        self.assertEqual(rejected.state, "rejected")

        repaired = self.store.promote(
            "team/billing",
            "invoice_echo",
            "def run(payload):\n    return payload['invoice_id'].split()\n",
            "repaired successor",
            proof_with_cases({"invoice_id": "INV-9"}, ["INV-9"]),
        )
        self.assertEqual(repaired.state, "trusted")

    def test_feedback_rejects_sensitive_reproduction_before_any_raw_payload_is_persisted(self):
        with self.assertRaisesRegex(ValueError, "submit a redacted reproduction"):
            self.store.record_feedback(
                self.record.id,
                reporter="Ada",
                verdict="incorrect",
                summary="The support incident payload includes an email address.",
                payload={"invoice_id": "customer@example.com"},
                expected_output="redacted",
            )
        count = self.store.db.execute("SELECT COUNT(*) FROM capability_feedback").fetchone()[0]
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
