import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from forgeagent.capability_graph import CapabilityGraph
from forgeagent.registry import Tool, ToolRegistry


class CapabilityGraphTests(unittest.TestCase):
    def test_separate_processes_preserve_concurrent_graph_updates(self):
        """Concurrent CLI runs must not collide on a shared graph temp file."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            graph_path = root / "capability_graph.json"
            ready_path = root / "start"
            CapabilityGraph(graph_path)

            worker = (
                "import sys, time\n"
                "from pathlib import Path\n"
                "from forgeagent.capability_graph import CapabilityGraph, Node\n"
                "graph_path = Path(sys.argv[1])\n"
                "ready_path = Path(sys.argv[2])\n"
                "prefix = sys.argv[3]\n"
                "while not ready_path.exists(): time.sleep(0.001)\n"
                "graph = CapabilityGraph(graph_path)\n"
                "for index in range(20):\n"
                "    graph.add_node(Node(f'{prefix}:{index}', 'task', f'{prefix}:{index}', {}))\n"
            )
            commands = [
                [sys.executable, "-c", worker, str(graph_path), str(ready_path), prefix]
                for prefix in ("first", "second")
            ]
            processes = [subprocess.Popen(command, cwd=Path(__file__).resolve().parents[1]) for command in commands]
            ready_path.touch()
            for process in processes:
                self.assertEqual(0, process.wait(timeout=15))

            graph = CapabilityGraph(graph_path)
            self.assertEqual(40, len(graph.export()["nodes"]))

    def test_separate_processes_preserve_concurrent_registry_reuse_counts(self):
        """Concurrent runs must not lose reuse evidence or collide on a temp file."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry_path = root / "tool_registry.json"
            ready_path = root / "start"
            registry = ToolRegistry(registry_path)
            registry.register(
                Tool(
                    name="counter",
                    description="test counter",
                    source="def run(payload): return payload",
                    test_input={},
                    expected_output={},
                    created_at=ToolRegistry.timestamp(),
                )
            )

            worker = (
                "import sys, time\n"
                "from pathlib import Path\n"
                "from forgeagent.registry import ToolRegistry\n"
                "registry_path = Path(sys.argv[1])\n"
                "ready_path = Path(sys.argv[2])\n"
                "while not ready_path.exists(): time.sleep(0.001)\n"
                "registry = ToolRegistry(registry_path)\n"
                "for _ in range(20): registry.mark_reused('counter')\n"
            )
            command = [sys.executable, "-c", worker, str(registry_path), str(ready_path)]
            processes = [subprocess.Popen(command, cwd=Path(__file__).resolve().parents[1]) for _ in range(2)]
            ready_path.touch()
            for process in processes:
                self.assertEqual(0, process.wait(timeout=15))

            self.assertEqual(40, ToolRegistry(registry_path).get("counter").reuse_count)


if __name__ == "__main__":
    unittest.main()
