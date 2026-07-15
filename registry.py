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
        return next((tool for tool in self.list() if tool.name == name), None)

    def register(self, tool: Tool) -> None:
        if self.get(tool.name):
            raise ValueError(f"Tool already registered: {tool.name}")
        records = [asdict(item) for item in self.list()]
        records.append(asdict(tool))
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp.replace(self.path)

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
