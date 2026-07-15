"""Append-only evidence trail for every ForgeAgent trust decision."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class AuditEvent:
    event: str
    capability: str
    detail: str
    outcome: str
    created_at: str


class AuditLog:
    def __init__(self, path: str | Path = "data/audit_log.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, event: str, capability: str, detail: str, outcome: str) -> AuditEvent:
        item = AuditEvent(event, capability, detail, outcome, datetime.now(timezone.utc).isoformat(timespec="seconds"))
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(item), sort_keys=True) + "\n")
        return item

    def recent(self, limit: int = 12) -> list[dict[str, str]]:
        if not self.path.exists():
            return []
        rows = [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return list(reversed(rows[-limit:]))
