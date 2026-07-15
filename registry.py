"""Persistent registry for verified ForgeAgent tools."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class Tool:
    name: str
    description: str
    source: str
    test_input: object
    expected_output: object
    created_at: str
    tests: list[dict[str, object]] = field(default_factory=list)
    provenance: str = "unknown"
    reuse_count: int = 0
    version: int = 1
    state: str = "active"
    replaces_version: int | None = None
    dependencies: list[str] = field(default_factory=list)


class ToolRegistry:
    def __init__(self, path: str | Path = "data/tool_registry.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]\n", encoding="utf-8")

    def list(self) -> list[Tool]:
        try:
            records = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Registry is not valid JSON: {self.path}") from exc
        return [Tool(**record) for record in records]

    def get(self, name: str) -> Tool | None:
        matches = [tool for tool in self.list() if tool.name == name and tool.state == "active"]
        return max(matches, key=lambda tool: tool.version, default=None)

    def get_version(self, name: str, version: int) -> Tool | None:
        return next((tool for tool in self.list() if tool.name == name and tool.version == version), None)

    def register(self, tool: Tool) -> None:
        if self.get_version(tool.name, tool.version):
            raise ValueError(f"Tool version already registered: {tool.name}@v{tool.version}")
        records = [asdict(item) for item in self.list()]
        records.append(asdict(tool))
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp.replace(self.path)

    def replace(self, previous: Tool, candidate: Tool) -> Tool:
        """Atomically promote a verified replacement and retain rollback history."""
        if previous.state != "active":
            raise ValueError("Only the active version can be replaced")
        records = [asdict(item) for item in self.list()]
        for record in records:
            if record["name"] == previous.name and record.get("version", 1) == previous.version:
                record["state"] = "superseded"
        promoted = asdict(candidate)
        promoted.update({"version": previous.version + 1, "state": "active", "replaces_version": previous.version})
        records.append(promoted)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp.replace(self.path)
        return Tool(**promoted)

    def rollback(self, name: str, version: int) -> Tool:
        """Reactivate an earlier trusted version without deleting later evidence."""
        records = [asdict(item) for item in self.list()]
        target = next((record for record in records if record["name"] == name and record.get("version", 1) == version), None)
        if not target:
            raise KeyError(f"No version {version} for {name}")
        for record in records:
            if record["name"] == name and record.get("state", "active") == "active":
                record["state"] = "superseded"
        target["state"] = "active"
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp.replace(self.path)
        return Tool(**target)

    def mark_reused(self, name: str) -> Tool:
        records = [asdict(item) for item in self.list()]
        for record in records:
            if record["name"] == name:
                record["reuse_count"] = int(record.get("reuse_count", 0)) + 1
                temp = self.path.with_suffix(".tmp")
                temp.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                temp.replace(self.path)
                return Tool(**record)
        raise KeyError(name)

    @staticmethod
    def timestamp() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
