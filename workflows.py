"""Flagship ForgeAgent workflows expressed as capability dependency plans."""

from agent import PlanStep


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
        "summarize",
        "Find word frequency in this customer feedback",
        {"text": "Reliable tools make teams reliable; teams build reliable work."},
        ("triage",),
    ),
)
