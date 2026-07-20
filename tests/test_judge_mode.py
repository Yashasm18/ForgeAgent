import tempfile
import unittest
from pathlib import Path

from forgeagent.judge_mode import JudgeMode


class JudgeModeTests(unittest.TestCase):
    """The click-through recording path must use real Foundry state."""

    def test_full_judge_story_forges_reuses_quarantines_repairs_and_reuses_again(self):
        with tempfile.TemporaryDirectory() as directory:
            mode = JudgeMode(Path(directory) / "judge_mode", repository_root=Path(__file__).resolve().parents[1])

            self.assertEqual(mode.state()["phase"], "ready")
            forged = mode.forge()
            self.assertEqual(forged["status"], "pending")
            self.assertEqual(mode.state()["phase"], "pending_review")

            approved = mode.approve()
            self.assertEqual(approved["state"], "trusted")
            reused = mode.reuse()
            self.assertEqual(reused["status"], "reused")
            self.assertEqual(reused["drift_check"]["status"], "passed")

            feedback = mode.report_failure()
            self.assertTrue(feedback["quarantined"])
            self.assertEqual(mode.state()["phase"], "quarantined")
            with self.assertRaisesRegex(ValueError, "No approved trusted capability"):
                mode.reuse()

            repaired = mode.repair()
            self.assertEqual(repaired["state"], "trusted")
            state = mode.state()
            self.assertEqual(state["phase"], "repaired_trusted")
            self.assertEqual(state["evidence"]["feedback_regression_count"], 1)
            self.assertIn("feedback", state["evidence"]["proof"]["coverage"])
            self.assertEqual(mode.reuse()["status"], "reused")


if __name__ == "__main__":
    unittest.main()
