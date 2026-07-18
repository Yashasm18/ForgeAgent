"""Flagship ForgeAgent workflows expressed as capability dependency plans."""

from forgeagent.agent import PlanStep


INCIDENT_RECOVERY_PLAN = (
    PlanStep(
        "redact",
        "Redact PII before sharing this support ticket",
        {"text": "Ava (ava@example.com) says the dashboard is down. Call +1 415 555 0112."},
    ),
    PlanStep(
        "triage",
        "Triage support risk for this customer incident",
        {"text": "A customer says the dashboard is down and they cannot access reports; they may cancel."},
        ("redact",),
    ),
    PlanStep(
        "extract_errors",
        "Extract structured error codes and line numbers from this stack trace",
        {"text": "ERROR E_GATEWAY_TIMEOUT at gateway.py:line 73"},
        ("triage",),
    ),
)
