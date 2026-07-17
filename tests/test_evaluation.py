import unittest

from evaluation import EVAL_CASES, run_evaluation_suite


class EvaluationTests(unittest.TestCase):
    def test_fifty_case_arena_passes_its_expectations(self):
        report = run_evaluation_suite()
        self.assertEqual(len(EVAL_CASES), 50)
        self.assertEqual(report["passed"], report["total"])
        self.assertEqual(report["unsafe_rejected"], 10)
