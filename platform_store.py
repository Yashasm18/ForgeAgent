"""SQLite control plane for Foundry capability evidence and approvals."""

from __future__ import annotations

import hashlib
import base64
import json
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from governance import assess, validate_human_decision
from policy_config import load_policy


PACKAGE_SCHEMA_VERSION = 2


def _signing_backend():
    """Load the optional, maintained Ed25519 implementation only on demand."""
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
    except ImportError as exc:
        raise RuntimeError(
            "Capability package signing requires the optional 'cryptography' dependency. "
            "Install it with: python3 -m pip install 'cryptography>=42,<49'"
        ) from exc
    return InvalidSignature, serialization, Ed25519PrivateKey, Ed25519PublicKey


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
CREATE TABLE IF NOT EXISTS capability_requests (
  capability_id TEXT PRIMARY KEY, task TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS threat_models (
  capability_id TEXT PRIMARY KEY, threat_json TEXT NOT NULL, created_at REAL NOT NULL
);
"""

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

    def close(self) -> None:
        self.db.close()

    def promote(self, project_id: str, name: str, source: str, provenance: str, proof: dict[str, object], policy: str = "auto", threat_model: dict[str, object] | None = None, requested_task: str | None = None) -> CapabilityRecord:
        if not project_id.strip() or not name.strip():
            raise ValueError("project_id and capability name are required")
        now = time.time()
        self.db.execute("INSERT OR IGNORE INTO projects VALUES (?, ?)", (project_id, now))
        version = self.db.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM capabilities WHERE project_id = ? AND name = ?", (project_id, name)).fetchone()[0]
        capability_id = hashlib.sha256(f"{project_id}:{name}:{version}:{source}".encode()).hexdigest()[:20]
        governance = assess(policy, name, provenance, proof, threat_model)
        decision = governance.decision
        state = {"approved": "trusted", "pending": "pending", "rejected": "rejected"}[decision]
        reason = governance.reason
        score = int(proof.get("trust_score", 0)) if state != "rejected" else 0
        self.db.execute("INSERT INTO capabilities VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (capability_id, project_id, name, version, source, provenance, score, state, now))
        self.db.execute("INSERT INTO proofs(capability_id,result_json,created_at) VALUES (?, ?, ?)", (capability_id, json.dumps(proof, sort_keys=True), now))
        if requested_task is not None:
            self.db.execute("INSERT INTO capability_requests(capability_id,task,created_at) VALUES (?, ?, ?)", (capability_id, requested_task, now))
        if threat_model is not None:
            self.db.execute("INSERT INTO threat_models(capability_id,threat_json,created_at) VALUES (?, ?, ?)", (capability_id, json.dumps(threat_model, sort_keys=True), now))
        self.db.execute("INSERT INTO approvals(capability_id,policy,decision,reviewer,reason,created_at) VALUES (?, ?, ?, ?, ?, ?)", (capability_id, policy, decision, "system", reason, now))
        self._event(project_id, "capability_proposed", f"{name}@v{version}:{state}")
        self.db.commit()
        return self.get(capability_id)

    def decide(self, capability_id: str, decision: str, reviewer: str, reason: str) -> CapabilityRecord:
        if decision not in {"approved", "rejected"}:
            raise ValueError("decision must be approved or rejected")
        validate_human_decision(reviewer, reason)
        record = self.get(capability_id)
        state = "trusted" if decision == "approved" else "rejected"
        score = max(record.trust_score, 80) if state == "trusted" else 0
        self.db.execute("UPDATE capabilities SET state = ?, trust_score = ? WHERE id = ?", (state, score, capability_id))
        self.db.execute("INSERT INTO approvals(capability_id,policy,decision,reviewer,reason,created_at) VALUES (?, ?, ?, ?, ?, ?)", (capability_id, "human", decision, reviewer, reason, time.time()))
        self._event(record.project_id, "human_decision", f"{record.name}@v{record.version}:{decision}")
        self.db.commit()
        return self.get(capability_id)

    def rollback(self, capability_id: str, reviewer: str, reason: str) -> CapabilityRecord:
        validate_human_decision(reviewer, reason)
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
        payload = {"project": project_id, "capabilities": [asdict(record) for record in self.list(project_id)], "events": [dict(row) for row in self.db.execute("SELECT kind,detail,created_at FROM events WHERE project_id = ? ORDER BY id", (project_id,))]}
        # The digest is tamper-evident evidence for export/review; raw incident
        # payloads are never stored in this control-plane receipt.
        return {**payload, "integrity_sha256": hashlib.sha256(self._canonical(payload)).hexdigest()}

    def pending_evidence(self) -> list[dict[str, object]]:
        """Return complete evidence for pending capabilities without changing state."""
        rows = self.db.execute(
            "SELECT id,project_id,name,version,source,provenance,trust_score,state "
            "FROM capabilities WHERE state = 'pending' ORDER BY created_at DESC"
        ).fetchall()
        pending: list[dict[str, object]] = []
        for row in rows:
            record = CapabilityRecord(**dict(row))
            proof = self.db.execute("SELECT result_json FROM proofs WHERE capability_id = ? ORDER BY id DESC LIMIT 1", (record.id,)).fetchone()
            threat = self.db.execute("SELECT threat_json FROM threat_models WHERE capability_id = ?", (record.id,)).fetchone()
            request = self.db.execute("SELECT task FROM capability_requests WHERE capability_id = ?", (record.id,)).fetchone()
            pending.append({
                **asdict(record),
                "requested_task": str(request["task"]) if request else None,
                "threat_model": json.loads(threat["threat_json"]) if threat else {},
                "proof": json.loads(proof["result_json"]) if proof else {},
            })
        return pending

    @staticmethod
    def generate_signing_keypair() -> dict[str, str]:
        """Generate a demo Ed25519 keypair; production keys belong in a KMS/HSM."""
        _, serialization, Ed25519PrivateKey, _ = _signing_backend()
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        return {
            "algorithm": "Ed25519",
            "private_key_pem": private_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ).decode(),
            "public_key_pem": public_key.public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            ).decode(),
        }

    def export_package(
        self,
        capability_id: str,
        private_key_pem: str | bytes,
        compatibility: dict[str, int] | None = None,
    ) -> dict[str, object]:
        """Export a capability as an Ed25519-signed, schema-constrained package."""
        record = self.get(capability_id)
        proof = self.db.execute("SELECT result_json FROM proofs WHERE capability_id = ? ORDER BY id DESC LIMIT 1", (capability_id,)).fetchone()
        _, serialization, Ed25519PrivateKey, _ = _signing_backend()
        private_key = serialization.load_pem_private_key(self._pem_bytes(private_key_pem), password=None)
        if not isinstance(private_key, Ed25519PrivateKey):
            raise ValueError("signing key must be an Ed25519 private key")
        public_key = private_key.public_key()
        package_compatibility = self._compatibility(compatibility, default_current=True)
        proof_payload = json.loads(proof["result_json"]) if proof else {}
        public_key_pem = public_key.public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()
        signer_key_id = self._key_id(public_key)
        payload = {
            "format": "forgeagent.capability.v2",
            "schema_version": PACKAGE_SCHEMA_VERSION,
            "compatibility": package_compatibility,
            "package_id": hashlib.sha256(f"{record.id}:".encode() + self._canonical(proof_payload)).hexdigest(),
            "signer": {"algorithm": "Ed25519", "key_id": signer_key_id, "public_key_pem": public_key_pem},
            "capability": asdict(record),
            "proof": proof_payload,
            "exported_at": int(time.time()),
        }
        signature = base64.b64encode(private_key.sign(self._canonical(payload))).decode()
        return {"algorithm": "Ed25519", "payload": payload, "signature": signature}

    def import_package(
        self,
        package: dict[str, object],
        public_key_pem: str | bytes,
        target_project: str,
        revoked_key_ids: Iterable[str] = (),
        revoked_package_ids: Iterable[str] = (),
        supported_schema_version: int = PACKAGE_SCHEMA_VERSION,
    ) -> CapabilityRecord:
        """Verify a trusted public key, revocation, and compatibility before review import."""
        payload = package.get("payload")
        if not isinstance(payload, dict) or package.get("algorithm") != "Ed25519":
            raise ValueError("unsupported capability package")
        if payload.get("format") != "forgeagent.capability.v2" or payload.get("schema_version") != PACKAGE_SCHEMA_VERSION:
            raise ValueError("unsupported capability package schema")
        compatibility = self._compatibility(payload.get("compatibility"))
        if not compatibility["min_schema_version"] <= supported_schema_version <= compatibility["max_schema_version"]:
            raise ValueError(
                f"incompatible package schema: supports {compatibility['min_schema_version']}"
                f"–{compatibility['max_schema_version']}, local supports {supported_schema_version}"
            )
        signer = payload.get("signer")
        package_id = payload.get("package_id")
        if not isinstance(signer, dict) or signer.get("algorithm") != "Ed25519" or not isinstance(package_id, str):
            raise ValueError("invalid package signer metadata")
        _, serialization, _, Ed25519PublicKey = _signing_backend()
        public_key = serialization.load_pem_public_key(self._pem_bytes(public_key_pem))
        if not isinstance(public_key, Ed25519PublicKey):
            raise ValueError("verification key must be an Ed25519 public key")
        signer_key_id = self._key_id(public_key)
        if signer.get("key_id") != signer_key_id or signer.get("public_key_pem") != public_key.public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode():
            raise ValueError("package signer key does not match supplied public key")
        if signer_key_id in set(revoked_key_ids):
            raise ValueError("revoked signer key")
        if package_id in set(revoked_package_ids):
            raise ValueError("revoked capability package")
        trusted_signers = load_policy().trusted_signer_keys
        if trusted_signers is not None and signer_key_id not in trusted_signers:
            raise ValueError("signer key is not trusted by project policy")
        try:
            signature = base64.b64decode(str(package.get("signature", "")), validate=True)
            public_key.verify(signature, self._canonical(payload))
        except (ValueError, _signing_backend()[0]):
            raise ValueError("invalid package signature")
        source = payload["capability"]
        return self.promote(target_project, str(source["name"]), str(source["source"]), f"marketplace import; {source['provenance']}", dict(payload.get("proof", {})), policy="review")

    def _event(self, project_id: str, kind: str, detail: str) -> None:
        self.db.execute("INSERT INTO events(project_id,kind,detail,created_at) VALUES (?, ?, ?, ?)", (project_id, kind, detail, time.time()))

    @staticmethod
    def _canonical(value: object) -> bytes:
        return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()

    @staticmethod
    def _pem_bytes(value: str | bytes) -> bytes:
        return value.encode() if isinstance(value, str) else value

    @staticmethod
    def _compatibility(value: object | None, default_current: bool = False) -> dict[str, int]:
        candidate = value
        if candidate is None and default_current:
            candidate = {
                "min_schema_version": PACKAGE_SCHEMA_VERSION,
                "max_schema_version": PACKAGE_SCHEMA_VERSION,
            }
        if not isinstance(candidate, dict):
            raise ValueError("invalid package compatibility metadata")
        minimum, maximum = candidate.get("min_schema_version"), candidate.get("max_schema_version")
        if any(not isinstance(item, int) or isinstance(item, bool) for item in (minimum, maximum)) or minimum > maximum:
            raise ValueError("invalid package compatibility metadata")
        return {"min_schema_version": minimum, "max_schema_version": maximum}

    @staticmethod
    def _key_id(public_key: object) -> str:
        _, serialization, _, _ = _signing_backend()
        raw = public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        return hashlib.sha256(raw).hexdigest()
