import unittest

from evaluation import EVAL_CASES, run_evaluation_suite


class EvaluationTests(unittest.TestCase):
    def test_suite_has_real_cases_and_all_expectations_hold(self):
        report = run_evaluation_suite()
        self.assertGreaterEqual(len(EVAL_CASES), 20)
        self.assertEqual(report["passed"], report["total"])
        self.assertGreaterEqual(report["candidate_policy_blocks"], 5)
