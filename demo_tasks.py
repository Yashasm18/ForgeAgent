"""Fixed demo sequence: build, reuse on a distinct task, then a second gap."""

DEMO_TASKS = [
    ("Find word frequency in this project note", {"text": "Forge tools. Forge trust. Build tools that build better tools."}),
    ("Find word frequency in this customer feedback", {"text": "Reliable tools make teams reliable; teams build reliable work."}),
    ("Create an email domain summary from these leads", {"text": "sam@OpenAI.com, lee@openai.com, priya@forage.dev, max@forage.dev, no-email"}),
]

SHOWCASE_TASKS = [
    ("Redact PII before sharing this support ticket", {"text": "Ava (ava@example.com) says the dashboard is down. Call +1 415 555 0112."}),
    ("Triage support risk for this customer incident", {"text": "A customer says the dashboard is down and they cannot access reports; they may cancel."}),
    ("Find word frequency in this customer feedback", {"text": "Reliable tools make teams reliable; teams build reliable work."}),
]
