"""ForgeAgent's native, queryable graph of tasks, skills, evidence, and lineage.

This is intentionally a capability graph, not a codebase knowledge graph: every
edge explains how an agent earned, used, repaired, or rolled back a skill.
"""

from __future__ import annotations

import json
import hashlib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class Node:
    id: str
    kind: str
    label: str
    metadata: dict[str, object]


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    relation: str


class CapabilityGraph:
    def __init__(self, path: str | Path = "data/capability_graph.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({"nodes": [], "edges": []})

    def _read(self) -> dict[str, list[dict[str, object]]]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError("Capability graph is invalid JSON") from exc

    def _write(self, data: dict[str, object]) -> None:
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp.replace(self.path)

    @staticmethod
    def task_id(task: str) -> str:
        digest = hashlib.sha256(task.encode("utf-8")).hexdigest()[:16]
        return "task:" + digest

    @staticmethod
    def skill_id(name: str, version: int) -> str:
        return f"skill:{name}@v{version}"

    def add_node(self, node: Node) -> None:
        data = self._read()
        if not any(item["id"] == node.id for item in data["nodes"]):
            data["nodes"].append(asdict(node))
            self._write(data)

    def add_edge(self, edge: Edge) -> None:
        data = self._read()
        record = asdict(edge)
        if record not in data["edges"]:
            data["edges"].append(record)
            self._write(data)

    def record_task_need(self, task: str, skill: str) -> str:
        task_id = self.task_id(task)
        self.add_node(Node(task_id, "task", task, {"created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}))
        self.add_node(Node(f"capability:{skill}", "capability", skill, {}))
        self.add_edge(Edge(task_id, f"capability:{skill}", "needs"))
        return task_id

    def record_skill(self, name: str, version: int, dependencies: list[str], trusted_by: str) -> None:
        skill_id = self.skill_id(name, version)
        self.add_node(Node(skill_id, "skill", f"{name} v{version}", {"trusted_by": trusted_by, "version": version}))
        for dependency in dependencies:
            self.add_node(Node(f"capability:{dependency}", "capability", dependency, {}))
            self.add_edge(Edge(skill_id, f"capability:{dependency}", "depends_on"))
        self.add_node(Node(f"evidence:{name}@v{version}", "evidence", f"Proof for {name} v{version}", {}))
        self.add_edge(Edge(skill_id, f"evidence:{name}@v{version}", "verified_by"))

    def link_task_to_skill(self, task: str, name: str, version: int, relation: str = "resolved_by") -> None:
        self.add_edge(Edge(self.task_id(task), self.skill_id(name, version), relation))

    def link_replacement(self, name: str, old_version: int, new_version: int) -> None:
        self.add_edge(Edge(self.skill_id(name, new_version), self.skill_id(name, old_version), "supersedes"))

    def link_rollback(self, name: str, version: int) -> None:
        self.add_edge(Edge(f"rollback:{name}@v{version}", self.skill_id(name, version), "reactivates"))
        self.add_node(Node(f"rollback:{name}@v{version}", "rollback", f"Rollback to {name} v{version}", {}))

    def export(self) -> dict[str, object]:
        return self._read()
