"""A real click-through demonstration of ForgeAgent's trust-maintenance loop."""

from __future__ import annotations

import shutil
import threading
from dataclasses import asdict
from pathlib import Path

from forgeagent.foundry import CapabilityFoundry
from forgeagent.generator import ToolProposal
from forgeagent.mcp_server import _run_project_trusted_capability
from forgeagent.offline_intelligence import OfflineTemplateGenerator
from forgeagent.platform_store import CapabilityRecord, PlatformStore
from forgeagent.proof_engine import ProofEngine


JUDGE_PROJECT = "judge/demo"
JUDGE_TASK = "Extract invoice IDs from billing logs"
JUDGE_PAYLOAD = {"text": "Invoices INV-2048 and INV-9 are awaiting review."}
FEEDBACK_PAYLOAD = {"text": "Duplicate billing record INV-2048, INV-2048."}
FEEDBACK_EXPECTED = ["INV-2048"]


class JudgeMode:
    """Runs an isolated, deterministic judge scenario against real local state.

    It intentionally uses a dedicated sibling directory so clicking Reset in a
    recording never touches a developer's normal ForgeAgent project memory.
    """

    def __init__(self, root: str | Path, repository_root: str | Path = ".") -> None:
        self.root = Path(root)
        self.repository_root = Path(repository_root)
        self._lock = threading.RLock()

    @property
    def registry_path(self) -> Path:
        return self.root / "tool_registry.json"

    @property
    def database_path(self) -> Path:
        return self.root / "foundry.sqlite3"

    def reset(self) -> dict[str, object]:
        with self._lock:
            if self.root.exists():
                shutil.rmtree(self.root)
            return self.state()

    def state(self) -> dict[str, object]:
        with self._lock:
            if not self.database_path.exists():
                return self._empty_state()
            store = PlatformStore(self.database_path)
            try:
                records = store.list(JUDGE_PROJECT)
                if not records:
                    return self._empty_state()
                record = records[0]
                evidence = store.capability_evidence(record.id)
                return {
                    "project_id": JUDGE_PROJECT,
                    "phase": self._phase(record, evidence),
                    "record": asdict(record),
                    "evidence": evidence,
                    "available_actions": self._actions(record, evidence),
                }
            finally:
                store.close()

    def forge(self) -> dict[str, object]:
        with self._lock:
            if self.database_path.exists():
                existing = PlatformStore(self.database_path)
                try:
                    if existing.list(JUDGE_PROJECT):
                        raise ValueError("Judge Mode already has a capability. Reset the isolated demo first.")
                finally:
                    existing.close()
            foundry = CapabilityFoundry(
                self.registry_path,
                project_id=JUDGE_PROJECT,
                root=self.repository_root,
                generator=OfflineTemplateGenerator(),
            )
            try:
                return foundry.run(
                    JUDGE_TASK,
                    JUDGE_PAYLOAD,
                    approval_policy="production",
                    adversarial_proof=True,
                )
            finally:
                foundry.store.close()

    def approve(self) -> dict[str, object]:
        with self._lock:
            store = self._store()
            try:
                record = self._current(store)
                if record.state != "pending":
                    raise ValueError("Only a pending Judge Mode capability can be approved.")
                return asdict(store.decide(record.id, "approved", "Judge", "Reviewed isolated proof, policy, and contract evidence."))
            finally:
                store.close()

    def reuse(self) -> dict[str, object]:
        with self._lock:
            store = self._store()
            try:
                outcome = _run_project_trusted_capability(store, JUDGE_PROJECT, JUDGE_TASK, JUDGE_PAYLOAD)
                if outcome is None:
                    raise ValueError("No approved trusted capability is available for Judge Mode reuse.")
                return outcome
            finally:
                store.close()

    def report_failure(self) -> dict[str, object]:
        with self._lock:
            store = self._store()
            try:
                record = self._current(store)
                if record.state != "trusted":
                    raise ValueError("Judge Mode can report a failure only after the capability is trusted.")
                return store.record_feedback(
                    record.id,
                    reporter="Judge",
                    verdict="incorrect",
                    summary="Contract requires duplicate invoice identifiers to collapse to one value.",
                    payload=FEEDBACK_PAYLOAD,
                    expected_output=FEEDBACK_EXPECTED,
                )
            finally:
                store.close()

    def repair(self) -> dict[str, object]:
        with self._lock:
            store = self._store()
            try:
                previous = self._current(store)
                if previous.state != "quarantined":
                    raise ValueError("Judge Mode can repair only a quarantined capability.")
                proposal = ToolProposal(
                    "invoice_id_extractor",
                    "Extract unique invoice IDs in first-seen order from billing text.",
                    "import re\n"
                    "def run(payload):\n"
                    "    matches = re.findall(r'\\bINV-\\d+\\b', payload['text'])\n"
                    "    unique = []\n"
                    "    for item in matches:\n"
                    "        if item not in unique:\n"
                    "            unique.append(item)\n"
                    "    return unique\n",
                    (
                        ({"text": "billing INV-2048 is delayed"}, ["INV-2048"]),
                        ({"text": ""}, []),
                        ({"text": "no invoice identifier present"}, []),
                    ),
                    "deterministic Judge Mode repair after reproduced duplicate-ID regression",
                    "EXTEND: Preserves the verified extractor contract while repairing duplicate identifier handling.",
                )
                proof_engine = ProofEngine()
                proof = proof_engine.evaluate(
                    proposal,
                    adversarial_cases=OfflineTemplateGenerator().propose_adversarial_cases(proposal),
                )
                threat = proof_engine.threat_model(proposal)
                record = store.promote(
                    JUDGE_PROJECT,
                    proposal.name,
                    proposal.source,
                    proposal.provenance,
                    proof,
                    policy="auto",
                    threat_model=threat,
                    requested_task=JUDGE_TASK,
                )
                return asdict(record)
            finally:
                store.close()

    def _store(self) -> PlatformStore:
        self.root.mkdir(parents=True, exist_ok=True)
        return PlatformStore(self.database_path)

    @staticmethod
    def _phase(record: CapabilityRecord, evidence: dict[str, object]) -> str:
        if record.state == "pending":
            return "pending_review"
        if record.state == "quarantined":
            return "quarantined"
        if record.state == "trusted" and record.version > 1 and int(evidence["feedback_regression_count"]) > 0:
            return "repaired_trusted"
        return record.state

    @staticmethod
    def _actions(record: CapabilityRecord, evidence: dict[str, object]) -> list[str]:
        if record.state == "pending":
            return ["approve"]
        if record.state == "trusted":
            return ["reuse", "report-failure"]
        if record.state == "quarantined":
            return ["repair"]
        return []

    @staticmethod
    def _empty_state() -> dict[str, object]:
        return {
            "project_id": JUDGE_PROJECT,
            "phase": "ready",
            "record": None,
            "evidence": None,
            "available_actions": ["forge"],
        }

    @staticmethod
    def _current(store: PlatformStore) -> CapabilityRecord:
        records = store.list(JUDGE_PROJECT)
        if not records:
            raise ValueError("Judge Mode has no capability yet. Forge one first.")
        return records[0]
