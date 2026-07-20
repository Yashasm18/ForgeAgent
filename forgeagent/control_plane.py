"""Tenant-aware control-plane primitives for ForgeAgent's local API and MCP v2.

The implementation is dependency-free for hackathon portability.  Its public
contracts deliberately separate identity, authorization, and Foundry state so
the SQLite backend can later be replaced by Postgres without changing clients.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from forgeagent.foundry import CapabilityFoundry
from forgeagent.offline_intelligence import OfflineTemplateGenerator
from forgeagent.platform_store import PlatformStore


SCHEMA = """
CREATE TABLE IF NOT EXISTS control_projects (
  project_id TEXT PRIMARY KEY, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS memberships (
  project_id TEXT NOT NULL, subject TEXT NOT NULL, role TEXT NOT NULL,
  created_at REAL NOT NULL, PRIMARY KEY(project_id, subject)
);
CREATE TABLE IF NOT EXISTS api_tokens (
  token_hash TEXT PRIMARY KEY, subject TEXT NOT NULL, label TEXT NOT NULL,
  expires_at REAL, created_at REAL NOT NULL, revoked_at REAL
);
CREATE TABLE IF NOT EXISTS control_events (
  id INTEGER PRIMARY KEY, project_id TEXT NOT NULL, actor TEXT NOT NULL,
  kind TEXT NOT NULL, detail_json TEXT NOT NULL, created_at REAL NOT NULL
);
"""

ROLE_RANK = {"viewer": 0, "developer": 1, "reviewer": 2, "admin": 3, "owner": 4}


@dataclass(frozen=True)
class Principal:
    subject: str
    role: str


class AuthorizationError(PermissionError):
    pass


class ControlPlane:
    """Local-first tenant and approval boundary for Foundry operations."""

    def __init__(self, root: str | Path = "data") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.root / "control_plane.sqlite3")
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()
        self.store = PlatformStore(self.root / "foundry.sqlite3")

    def close(self) -> None:
        self.store.close()
        self.db.close()

    def create_project(self, project_id: str, owner: str) -> Principal:
        self._require_text(project_id, "project_id")
        self._require_text(owner, "owner")
        now = time.time()
        self.db.execute("INSERT OR IGNORE INTO control_projects(project_id,created_at) VALUES (?,?)", (project_id, now))
        self.db.execute("INSERT OR IGNORE INTO memberships(project_id,subject,role,created_at) VALUES (?,?,?,?)", (project_id, owner, "owner", now))
        self._event(project_id, owner, "project_created", {"owner": owner})
        self.db.commit()
        return Principal(owner, "owner")

    def grant_role(self, project_id: str, actor: str, subject: str, role: str) -> Principal:
        self.require(project_id, actor, "admin")
        if role not in ROLE_RANK:
            raise ValueError("role must be viewer, developer, reviewer, admin, or owner")
        self._require_text(subject, "subject")
        self.db.execute("INSERT INTO memberships(project_id,subject,role,created_at) VALUES (?,?,?,?) ON CONFLICT(project_id,subject) DO UPDATE SET role=excluded.role", (project_id, subject, role, time.time()))
        self._event(project_id, actor, "role_granted", {"subject": subject, "role": role})
        self.db.commit()
        return Principal(subject, role)

    def issue_token(self, subject: str, label: str, ttl_seconds: int | None = 86_400) -> str:
        self._require_text(subject, "subject")
        self._require_text(label, "label")
        token = "fga_" + secrets.token_urlsafe(32)
        expiry = time.time() + ttl_seconds if ttl_seconds else None
        self.db.execute("INSERT INTO api_tokens(token_hash,subject,label,expires_at,created_at,revoked_at) VALUES (?,?,?,?,?,NULL)", (self._hash(token), subject, label, expiry, time.time()))
        self.db.commit()
        return token

    def authenticate(self, token: str) -> str:
        row = self.db.execute("SELECT subject,expires_at,revoked_at FROM api_tokens WHERE token_hash=?", (self._hash(token),)).fetchone()
        if not row or row["revoked_at"] is not None or (row["expires_at"] and row["expires_at"] <= time.time()):
            raise AuthorizationError("invalid, expired, or revoked API token")
        return str(row["subject"])

    def require(self, project_id: str, subject: str, minimum_role: str) -> Principal:
        if minimum_role not in ROLE_RANK:
            raise ValueError("unknown required role")
        row = self.db.execute("SELECT role FROM memberships WHERE project_id=? AND subject=?", (project_id, subject)).fetchone()
        if row is None or ROLE_RANK[row["role"]] < ROLE_RANK[minimum_role]:
            raise AuthorizationError(f"{minimum_role} role required for project {project_id}")
        return Principal(subject, str(row["role"]))

    def request_capability(self, project_id: str, actor: str, task: str, payload: dict[str, object], production: bool = True) -> dict[str, object]:
        self.require(project_id, actor, "developer")
        self._require_text(task, "task")
        # The local control plane remains useful without API credits: known
        # blueprints and explicitly reviewed templates can still be proved,
        # governed, and held for human approval.
        foundry = CapabilityFoundry(
            self.root / "tool_registry.json",
            project_id=project_id,
            root=".",
            generator=OfflineTemplateGenerator(),
        )
        try:
            outcome = foundry.run(task, payload, approval_policy="production" if production else "review")
        finally:
            # CapabilityFoundry opens an independent SQLite connection for a
            # request. The control plane owns this short-lived instance, so
            # close it before returning to a long-running MCP/API process.
            foundry.store.close()
        self._event(project_id, actor, "capability_requested", {"task": task, "status": outcome["status"], "production": production})
        self.db.commit()
        return outcome

    def decide_capability(self, project_id: str, actor: str, capability_id: str, decision: str, reason: str) -> dict[str, object]:
        self.require(project_id, actor, "reviewer")
        record = self.store.get(capability_id)
        if record.project_id != project_id:
            raise AuthorizationError("capability is outside this project namespace")
        updated = self.store.decide(capability_id, decision, actor, reason)
        self._event(project_id, actor, "capability_decided", {"capability_id": capability_id, "decision": decision})
        self.db.commit()
        return asdict(updated)

    def project_snapshot(self, project_id: str, actor: str) -> dict[str, object]:
        self.require(project_id, actor, "viewer")
        receipt = self.store.receipt(project_id)
        membership = [dict(row) for row in self.db.execute("SELECT subject,role,created_at FROM memberships WHERE project_id=? ORDER BY subject", (project_id,))]
        return {"project_id": project_id, "members": membership, "receipt": receipt, "metrics": self.metrics(project_id, actor)}

    def metrics(self, project_id: str, actor: str) -> dict[str, object]:
        self.require(project_id, actor, "viewer")
        records = self.store.list(project_id)
        states: dict[str, int] = {}
        for record in records:
            states[record.state] = states.get(record.state, 0) + 1
        events = [dict(row) for row in self.db.execute("SELECT kind,created_at FROM control_events WHERE project_id=? ORDER BY id", (project_id,))]
        return {
            "capability_count": len(records),
            "states": states,
            "trusted_reuse_count": sum(record.trust_score > 0 and record.state == "trusted" for record in records),
            "control_event_count": len(events),
            "last_event_at": events[-1]["created_at"] if events else None,
        }

    def _event(self, project_id: str, actor: str, kind: str, detail: dict[str, object]) -> None:
        self.db.execute("INSERT INTO control_events(project_id,actor,kind,detail_json,created_at) VALUES (?,?,?,?,?)", (project_id, actor, kind, json.dumps(detail, sort_keys=True), time.time()))

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    @staticmethod
    def _require_text(value: str, label: str) -> None:
        if not value or not value.strip():
            raise ValueError(f"{label} is required")
