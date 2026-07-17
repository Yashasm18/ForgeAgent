import tempfile
import unittest
from pathlib import Path

from repository_graph import RepositoryGraph


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
