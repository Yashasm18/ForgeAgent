"""Deterministic, privacy-first incident analysis used by ForgeAgent demos."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass


STOP_WORDS = frozenset(
    "the a an and or is are was were to of in on for with after unless they this that "
    "their customer cannot today redacted secret message email phone code".split()
)
RISK_SIGNALS = {
    "security": ("unauthorized", "breach", "leak", "stolen", "compromised"),
    "access": ("cannot access", "locked", "lockout", "login failed"),
    "retention": ("cancel", "churn", "competitor", "refund"),
    "urgency": ("urgent", "immediately", "today", "asap"),
}


@dataclass(frozen=True)
class IncidentResult:
    redacted_text: str
    redaction_categories: tuple[str, ...]
    risk: str
    risk_signals: tuple[str, ...]
    recurring_terms: tuple[tuple[str, int], ...]

    def audit_payload(self) -> dict[str, object]:
        """Safe-to-store result: intentionally excludes the original payload."""
        return asdict(self)


def analyze_incident(text: str) -> IncidentResult:
    """Return a stable structured analysis for arbitrary support text.

    Only explicitly labelled secret values are removed; arbitrary prose and
    unlabelled numeric identifiers are retained to avoid destructive overreach.
    """
    if not isinstance(text, str):
        raise TypeError("incident text must be a string")
    categories: list[str] = []

    def replace(pattern: str, replacement: str, category: str) -> None:
        nonlocal text
        text, count = re.subn(pattern, replacement, text, flags=re.IGNORECASE)
        if count:
            categories.append(category)
        return None

    replace(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", "[REDACTED_EMAIL]", "email")
    # Card-like sequences are longer than most phones, so classify them first.
    replace(r"\b(?:\d[ -]?){13,19}\b", "[REDACTED_CARD]", "card")
    replace(r"(?<!\w)(?:\+?\d[\d\s-]{8,}\d)(?!\w)", "[REDACTED_PHONE]", "phone")
    replace(
        r"\b(secret\s*(?:code|key)|pass(?:word|code)|otp|pin|api[ _-]?key|access[ _-]?token)\s*(?:is|:|=)?\s*[A-Za-z0-9_-]{4,}\b",
        r"\1 [REDACTED_SECRET]",
        "labelled_secret",
    )
    replace(
        r"\b(secret\s*message|confidential\s*message)\s*(?:is|:|=)\s*[^.\n]+",
        r"\1: [REDACTED_SECRET_MESSAGE]",
        "secret_message",
    )
    lowered = text.lower()
    signals = tuple(name for name, phrases in RISK_SIGNALS.items() if any(phrase in lowered for phrase in phrases))
    risk = "critical" if "security" in signals else "high" if len(signals) >= 2 else "medium" if signals else "low"
    words = [word for word in re.findall(r"[a-z]{4,}", lowered) if word not in STOP_WORDS]
    recurring = tuple(sorted(Counter(words).items(), key=lambda row: (-row[1], row[0]))[:5])
    return IncidentResult(text, tuple(dict.fromkeys(categories)), risk, signals, recurring)
