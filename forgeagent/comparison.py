"""Measured comparison of a stateless agent and ForgeAgent's trusted memory."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from forgeagent.agent import ForgeAgent, PlanStep
from forgeagent.registry import ToolRegistry


RECURRING_ENGINEERING_STEPS = (
    PlanStep("normalize_dates_01", "Normalize inconsistent date formats in this import log", {"text": "batch=ledger 03/07/2026"}),
    PlanStep("redact_incident_02", "Redact PII before sharing this support ticket", {"text": "Mina mina@example.com cannot access billing; call +1 415 555 0142."}),
    PlanStep("triage_incident_02", "Triage support risk for this customer incident", {"text": "The production dashboard is down and the customer may cancel today."}),
    PlanStep("extract_trace_02", "Extract structured error codes and line numbers from this stack trace", {"text": "ERROR E_RATE_LIMIT at api.py:line 61"}),
    PlanStep("normalize_dates_02", "Normalize inconsistent date formats in this import log", {"text": "batch=payout 2026/7/4"}),
    PlanStep("redact_incident_03", "Redact PII before sharing this support ticket", {"text": "Jae jae@example.com reported a secret code 89789 in an urgent account lock."}),
    PlanStep("triage_incident_03", "Triage support risk for this customer incident", {"text": "Unauthorized access was reported; reports are broken and renewal is at risk."}),
    PlanStep("extract_trace_03", "Extract structured error codes and line numbers from this stack trace", {"text": "ERROR E_SCHEMA_INVALID at parser.py:line 17"}),
    PlanStep("normalize_dates_03", "Normalize inconsistent date formats in this import log", {"text": "batch=archive Jul 5, 2026"}),
    PlanStep("redact_incident_04", "Redact PII before sharing this support ticket", {"text": "Omar omar@example.com says the portal is broken; phone +1 415 555 0173."}),
    PlanStep("triage_incident_04", "Triage support risk for this customer incident", {"text": "Customers cannot access exports and a competitor review is scheduled."}),
    PlanStep("extract_trace_04", "Extract structured error codes and line numbers from this stack trace", {"text": "ERROR E_GATEWAY_TIMEOUT at gateway.py:line 73"}),
    PlanStep("normalize_dates_04", "Normalize inconsistent date formats in this import log", {"text": "batch=retry 06-07-2026"}),
    PlanStep("redact_incident_05", "Redact PII before sharing this support ticket", {"text": "Nora nora@example.com says the account is locked; API key: demo-key-12345."}),
    PlanStep("triage_incident_05", "Triage support risk for this customer incident", {"text": "Service outage blocks invoices and the customer requested a refund."}),
)


def _run(plan: tuple[PlanStep, ...], shared_memory: bool) -> dict[str, object]:
    started = time.perf_counter()
    creations = reuses = 0
    with tempfile.TemporaryDirectory(prefix="forge-comparison-") as directory:
        root = Path(directory)
        if not shared_memory:
            # A stateless agent receives no verified capability memory between
            # steps, so every recurring task must prove a fresh tool again.
            for run in range(2):
                for index, step in enumerate(plan):
                    registry = ToolRegistry(root / f"stateless-{run}-{index}.json")
                    ForgeAgent(registry, emit=lambda _: None).complete(step.task, step.payload)
                    creations += len(registry.list())
        else:
            for _ in range(2):
                registry = ToolRegistry(root / "shared.json")
                ForgeAgent(registry, emit=lambda _: None).execute_plan("Securely analyze recurring engineering incidents", plan)
        if shared_memory:
            tools = ToolRegistry(root / "shared.json").list()
            creations = len(tools)
            reuses = sum(tool.reuse_count for tool in tools)
    return {"new_skills": creations, "reuses": reuses, "elapsed_ms": round((time.perf_counter() - started) * 1000, 1)}


def compare(plan: tuple[PlanStep, ...]) -> dict[str, object]:
    workload = plan + RECURRING_ENGINEERING_STEPS
    stateless = _run(workload, shared_memory=False)
    forge = _run(workload, shared_memory=True)
    return {
        "scenario": "Two identical 18-step recurring engineering incident workflows",
        "stateless_agent": stateless,
        "forgeagent": forge,
        "claim": "ForgeAgent learns once, verifies once, and reuses trusted capabilities on subsequent tasks.",
    }
