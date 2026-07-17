"""Fixed demo sequence: build, reuse on a distinct task, then a second gap."""

DEMO_TASKS = [
    ("Normalize inconsistent date formats in this import log", {"text": "job=ledger 03/07/2026; job=payout 2026/7/4; job=archive Jul 5, 2026"}),
    ("Normalize inconsistent date formats in this import log", {"text": "job=retry 06-07-2026; job=sync 2026-07-08"}),
    ("Extract structured error codes and line numbers from this stack trace", {"text": "ERROR E_CONN_TIMEOUT at ingest.py:line 42\nValidation failed E_SCHEMA_INVALID in parser.py:17"}),
]

SHOWCASE_TASKS = [
    ("Redact PII before sharing this support ticket", {"text": "Ava (ava@example.com) says the dashboard is down. Call +1 415 555 0112."}),
    ("Triage support risk for this customer incident", {"text": "A customer says the dashboard is down and they cannot access reports; they may cancel."}),
    ("Extract structured error codes and line numbers from this stack trace", {"text": "ERROR E_AUTH_EXPIRED at auth.py:line 88"}),
]
