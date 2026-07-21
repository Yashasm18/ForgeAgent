"""Persistent registry for verified ForgeAgent tools."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

try:  # POSIX covers the supported local and container execution environments.
    import fcntl
except ImportError:  # pragma: no cover - Windows is not part of the demo profile.
    fcntl = None


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
    # None means this legacy record predates persisted proof evidence counts.
    proof_case_count: int | None = None


class ToolRegistry:
    def __init__(self, path: str | Path = "data/tool_registry.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        with self._exclusive_lock():
            if not self.path.exists():
                self._write_records([])

    def list(self) -> list[Tool]:
        return [Tool(**record) for record in self._read_records()]

    def _read_records(self) -> list[dict[str, object]]:
        try:
            records = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Registry is not valid JSON: {self.path}") from exc
        return records

    def _write_records(self, records: list[dict[str, object]]) -> None:
        """Atomically replace the registry after the caller holds the registry lock."""
        descriptor, temp_name = tempfile.mkstemp(
            dir=self.path.parent,
            prefix=f".{self.path.name}.",
            suffix=".tmp",
        )
        temp = Path(temp_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(records, indent=2, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            temp.replace(self.path)
        finally:
            temp.unlink(missing_ok=True)

    @contextmanager
    def _exclusive_lock(self):
        """Serialize read-modify-write operations across concurrent agent runs."""
        with self.lock_path.open("a+", encoding="utf-8") as handle:
            if fcntl is None:  # pragma: no cover - see import note above.
                yield
                return
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def get(self, name: str) -> Tool | None:
        matches = [tool for tool in self.list() if tool.name == name and tool.state == "active"]
        return max(matches, key=lambda tool: tool.version, default=None)

    def get_version(self, name: str, version: int) -> Tool | None:
        return next((tool for tool in self.list() if tool.name == name and tool.version == version), None)

    def register(self, tool: Tool) -> None:
        with self._exclusive_lock():
            records = self._read_records()
            if any(record["name"] == tool.name and record.get("version", 1) == tool.version for record in records):
                raise ValueError(f"Tool version already registered: {tool.name}@v{tool.version}")
            records.append(asdict(tool))
            self._write_records(records)

    def replace(self, previous: Tool, candidate: Tool) -> Tool:
        """Atomically promote a verified replacement and retain rollback history."""
        if previous.state != "active":
            raise ValueError("Only the active version can be replaced")
        with self._exclusive_lock():
            records = self._read_records()
            for record in records:
                if record["name"] == previous.name and record.get("version", 1) == previous.version:
                    record["state"] = "superseded"
            promoted = asdict(candidate)
            promoted.update({"version": previous.version + 1, "state": "active", "replaces_version": previous.version})
            records.append(promoted)
            self._write_records(records)
            return Tool(**promoted)

    def rollback(self, name: str, version: int) -> Tool:
        """Reactivate an earlier trusted version without deleting later evidence."""
        with self._exclusive_lock():
            records = self._read_records()
            target = next((record for record in records if record["name"] == name and record.get("version", 1) == version), None)
            if not target:
                raise KeyError(f"No version {version} for {name}")
            for record in records:
                if record["name"] == name and record.get("state", "active") == "active":
                    record["state"] = "superseded"
            target["state"] = "active"
            self._write_records(records)
            return Tool(**target)

    def mark_reused(self, name: str) -> Tool:
        with self._exclusive_lock():
            records = self._read_records()
            for record in records:
                if record["name"] == name:
                    record["reuse_count"] = int(record.get("reuse_count", 0)) + 1
                    self._write_records(records)
                    return Tool(**record)
            raise KeyError(name)

    @staticmethod
    def timestamp() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
