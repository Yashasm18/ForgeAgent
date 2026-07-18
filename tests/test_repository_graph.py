import tempfile
import unittest
from pathlib import Path

from forgeagent.repository_graph import RepositoryGraph


class RepositoryGraphTests(unittest.TestCase):
    def test_build_query_and_impact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "parser.py").write_text("import json\n\ndef invoice_parser(payload):\n    return payload\n")
            (root / "README.md").write_text("# Invoice parser\n")
            graph = RepositoryGraph(root)
            report = graph.build()
            self.assertGreaterEqual(len(report["nodes"]), 4)
            self.assertTrue(graph.query("invoice"))
            self.assertIn("parser.py", graph.impact("invoice parser")["impact_candidates"])

    def test_impact_uses_function_docstring_tokens_for_related_capability(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "calendar_helpers.py").write_text(
                'def canonicalize_value(payload):\n'
                '    """Normalize date values into ISO calendar format."""\n'
                '    return payload\n'
            )
            graph = RepositoryGraph(root)
            graph.build()

            impact = graph.impact("date_format_normalizer")

            self.assertIn("calendar_helpers.py", impact["impact_candidates"])
            self.assertIn("canonicalize_value", impact["related_symbols"])

    def test_impact_does_not_return_unrelated_symbols_from_substring_overlap(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "validation.py").write_text(
                'def validate_payload(payload):\n'
                '    """Validate a generic payload contract."""\n'
                '    return payload\n'
            )
            graph = RepositoryGraph(root)
            graph.build()

            impact = graph.impact("date_format_normalizer")

            self.assertEqual([], impact["impact_candidates"])
            self.assertEqual([], impact["related_symbols"])
