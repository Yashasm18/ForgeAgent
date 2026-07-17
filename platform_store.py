"""SQLite control plane for Foundry capability evidence and approvals."""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS capabilities (
  id TEXT PRIMARY KEY, project_id TEXT NOT NULL, name TEXT NOT NULL, version INTEGER NOT NULL,
  source TEXT NOT NULL, provenance TEXT NOT NULL, trust_score INTEGER NOT NULL,
  state TEXT NOT NULL, created_at REAL NOT NULL, UNIQUE(project_id, name, version)
);
CREATE TABLE IF NOT EXISTS proofs (
  id INTEGER PRIMARY KEY, capability_id TEXT NOT NULL, result_json TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
  id INTEGER PRIMARY KEY, capability_id TEXT NOT NULL, policy TEXT NOT NULL, decision TEXT NOT NULL,
  reviewer TEXT NOT NULL, reason TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY, project_id TEXT NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL, created_at REAL NOT NULL
);
"""

SENSITIVE_MARKERS = frozenset({"secret", "payment", "finance", "security", "network", "filesystem", "external"})


@dataclass(frozen=True)
class CapabilityRecord:
    id: str
    project_id: str
    name: str
    version: int
    source: str
    provenance: str
    trust_score: int
    state: str


class PlatformStore:
    """Local-first memory with project isolation and an append-only decision trail."""

    def __init__(self, path: str | Path = "data/platform.sqlite3") -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(target)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()

    def promote(self, project_id: str, name: str, source: str, provenance: str, proof: dict[str, object], policy: str = "auto") -> CapabilityRecord:
        if policy not in {"auto", "review", "never"}:
            raise ValueError("policy must be auto, review, or never")
        if not project_id.strip() or not name.strip():
            raise ValueError("project_id and capability name are required")
        now = time.time()
        self.db.execute("INSERT OR IGNORE INTO projects VALUES (?, ?)", (project_id, now))
        version = self.db.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM capabilities WHERE project_id = ? AND name = ?", (project_id, name)).fetchone()[0]
        capability_id = hashlib.sha256(f"{project_id}:{name}:{version}:{source}".encode()).hexdigest()[:20]
        sensitive = any(marker in f"{name} {provenance}".lower() for marker in SENSITIVE_MARKERS)
        proof_passed = bool(proof.get("passed"))
        if policy == "never" and sensitive:
            decision, state, reason = "rejected", "rejected", "policy forbids sensitive or external capability"
        elif policy == "review" or sensitive:
            decision, state, reason = "pending", "pending", "human approval required"
        elif proof_passed:
            decision, state, reason = "approved", "trusted", "policy and proof passed"
        else:
            decision, state, reason = "rejected", "rejected", "proof did not pass"
        score = int(proof.get("trust_score", 0)) if state != "rejected" else 0
        self.db.execute("INSERT INTO capabilities VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (capability_id, project_id, name, version, source, provenance, score, state, now))
        self.db.execute("INSERT INTO proofs(capability_id,result_json,created_at) VALUES (?, ?, ?)", (capability_id, json.dumps(proof, sort_keys=True), now))
        self.db.execute("INSERT INTO approvals(capability_id,policy,decision,reviewer,reason,created_at) VALUES (?, ?, ?, ?, ?, ?)", (capability_id, policy, decision, "system", reason, now))
        self._event(project_id, "capability_proposed", f"{name}@v{version}:{state}")
        self.db.commit()
        return self.get(capability_id)

    def decide(self, capability_id: str, decision: str, reviewer: str, reason: str) -> CapabilityRecord:
        if decision not in {"approved", "rejected"}:
            raise ValueError("decision must be approved or rejected")
        record = self.get(capability_id)
        state = "trusted" if decision == "approved" else "rejected"
        score = max(record.trust_score, 80) if state == "trusted" else 0
        self.db.execute("UPDATE capabilities SET state = ?, trust_score = ? WHERE id = ?", (state, score, capability_id))
        self.db.execute("INSERT INTO approvals(capability_id,policy,decision,reviewer,reason,created_at) VALUES (?, ?, ?, ?, ?, ?)", (capability_id, "human", decision, reviewer, reason, time.time()))
        self._event(record.project_id, "human_decision", f"{record.name}@v{record.version}:{decision}")
        self.db.commit()
        return self.get(capability_id)

    def rollback(self, capability_id: str, reviewer: str, reason: str) -> CapabilityRecord:
        record = self.get(capability_id)
        self.db.execute("UPDATE capabilities SET state = ?, trust_score = 0 WHERE id = ?", ("rolled_back", capability_id))
        self.db.execute("INSERT INTO approvals(capability_id,policy,decision,reviewer,reason,created_at) VALUES (?, ?, ?, ?, ?, ?)", (capability_id, "human", "rolled_back", reviewer, reason, time.time()))
        self._event(record.project_id, "rollback", f"{record.name}@v{record.version}:{reason}")
        self.db.commit()
        return self.get(capability_id)

    def get(self, capability_id: str) -> CapabilityRecord:
        row = self.db.execute("SELECT id,project_id,name,version,source,provenance,trust_score,state FROM capabilities WHERE id = ?", (capability_id,)).fetchone()
        if row is None:
            raise KeyError(capability_id)
        return CapabilityRecord(**dict(row))

    def list(self, project_id: str, trusted_only: bool = False) -> list[CapabilityRecord]:
        sql = "SELECT id,project_id,name,version,source,provenance,trust_score,state FROM capabilities WHERE project_id = ?"
        if trusted_only:
            sql += " AND state = 'trusted'"
        sql += " ORDER BY created_at DESC"
        return [CapabilityRecord(**dict(row)) for row in self.db.execute(sql, (project_id,))]

    def receipt(self, project_id: str) -> dict[str, object]:
        return {"project": project_id, "capabilities": [asdict(record) for record in self.list(project_id)], "events": [dict(row) for row in self.db.execute("SELECT kind,detail,created_at FROM events WHERE project_id = ? ORDER BY id", (project_id,))]}

    def export_package(self, capability_id: str, signing_key: str) -> dict[str, object]:
        record = self.get(capability_id)
        proof = self.db.execute("SELECT result_json FROM proofs WHERE capability_id = ? ORDER BY id DESC LIMIT 1", (capability_id,)).fetchone()
        payload = {"format": "forgeagent.capability.v1", "capability": asdict(record), "proof": json.loads(proof["result_json"]) if proof else {}, "exported_at": int(time.time())}
        signature = hmac.new(signing_key.encode(), self._canonical(payload), hashlib.sha256).hexdigest()
        return {"algorithm": "HMAC-SHA256", "payload": payload, "signature": signature}

    def import_package(self, package: dict[str, object], signing_key: str, target_project: str) -> CapabilityRecord:
        payload = package.get("payload")
        if not isinstance(payload, dict) or package.get("algorithm") != "HMAC-SHA256":
            raise ValueError("unsupported capability package")
        expected = hmac.new(signing_key.encode(), self._canonical(payload), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(str(package.get("signature", "")), expected):
            raise ValueError("invalid package signature")
        source = payload["capability"]
        return self.promote(target_project, str(source["name"]), str(source["source"]), f"marketplace import; {source['provenance']}", dict(payload.get("proof", {})), policy="review")

    def _event(self, project_id: str, kind: str, detail: str) -> None:
        self.db.execute("INSERT INTO events(project_id,kind,detail,created_at) VALUES (?, ?, ?, ?)", (project_id, kind, detail, time.time()))

    @staticmethod
    def _canonical(value: object) -> bytes:
        return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
