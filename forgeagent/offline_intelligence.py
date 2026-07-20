"""Deterministic, zero-cost intelligence for ForgeAgent's offline mode.

This module intentionally does not imitate a general-purpose language model.
It ranks the existing capability catalog, selects explicitly reviewed contract
templates, creates bounded adversarial cases, and decomposes known workflows.
Anything outside those supported contracts is refused instead of fabricated.
"""

from __future__ import annotations

import re
from typing import Iterable

from forgeagent.generator import GeneratorError, ProofCase, ToolProposal


STOP_WORDS = frozenset({"a", "an", "and", "are", "at", "be", "by", "for", "from", "i", "in", "into", "is", "it", "my", "of", "on", "please", "the", "this", "to", "with", "you", "your"})
NORMALIZED_TOKENS = {
    "dates": "date", "errors": "error", "identifiers": "identifier", "ids": "id",
    "logs": "log", "messages": "message", "secrets": "secret", "tickets": "ticket",
}


def _tokens(value: str) -> set[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9_]*", value.lower())
    return {NORMALIZED_TOKENS.get(word, word) for word in words if word not in STOP_WORDS and len(word) > 1}


def _rank(task: str, catalog: Iterable[dict[str, str]]) -> str | None:
    """Return a conservative, explainable catalog match or ``None``.

    Two shared meaningful terms and a minimum Sørensen-Dice score are required,
    avoiding a false match from a single generic word such as ``support``.
    """
    task_terms = _tokens(task)
    candidates: list[tuple[float, int, str]] = []
    for item in catalog:
        name, description = item.get("name"), item.get("description")
        if not isinstance(name, str) or not isinstance(description, str):
            continue
        capability_terms = _tokens(f"{name} {description}")
        shared = task_terms & capability_terms
        score = (2 * len(shared) / (len(task_terms) + len(capability_terms))) if task_terms and capability_terms else 0.0
        if len(shared) >= 2 and score >= 0.25:
            candidates.append((score, len(shared), name))
    return max(candidates, default=(0.0, 0, ""), key=lambda item: (item[0], item[1], item[2]))[2] or None


class OfflineTemplateGenerator:
    """Reviewed local templates and proofs, with no model or network calls."""

    offline_semantic_matching_available = True
    # Foundry must retain the curated blueprint path for known capabilities;
    # this generator only owns explicitly reviewed templates for new work.
    offline_template_only = True

    @staticmethod
    def template_capability_name(task: str) -> str | None:
        """Return the reviewed template name that owns a task, if any."""
        return "invoice_id_extractor" if "invoice" in _tokens(task) else None

    def match_existing_capability(self, task: str, capabilities: list[dict[str, str]]) -> str | None:
        return _rank(task, capabilities)

    def propose(self, capability: str, payload: object, repository_context: str | None = None) -> ToolProposal:
        if self.template_capability_name(capability) is None:
            raise GeneratorError(
                "Offline templates support invoice-ID extraction and known trusted capabilities only. "
                "Use a local model or GPT-5.6 for genuinely new capability design."
            )
        relationship = (
            "EXTEND: Deterministic invoice-ID template selected after repository inspection; no existing executable code is copied."
            if repository_context
            else "SEPARATE: Deterministic invoice-ID template selected because no reusable capability matched."
        )
        return ToolProposal(
            "invoice_id_extractor",
            "Extract invoice IDs in the INV-<digits> format from billing text.",
            "import re\n"
            "def run(payload):\n"
            "    return re.findall(r'\\bINV-\\d+\\b', payload['text'])\n",
            (
                ({"text": "billing INV-2048 is delayed"}, ["INV-2048"]),
                ({"text": ""}, []),
                ({"text": "no invoice identifier present"}, []),
            ),
            "deterministic offline template: invoice_id_extractor@v1",
            relationship,
        )

    def propose_adversarial_cases(self, proposal: ToolProposal) -> list[ProofCase]:
        if proposal.name != "invoice_id_extractor":
            raise GeneratorError(f"No deterministic adversarial contract is registered for {proposal.name}.")
        return [
            ProofCase(
                "adversarial",
                {"text": "first INV-000 then INV-9"},
                ["INV-000", "INV-9"],
                "Multiple IDs, including a leading-zero identifier, must be preserved in source order.",
            ),
            ProofCase(
                "adversarial",
                {"text": "Invoice INV-1\nnoise\nInvoice INV-2"},
                ["INV-1", "INV-2"],
                "Newlines must not truncate extraction after the first matching ID.",
            ),
        ]

    def plan(self, user_task: str, payload: object) -> list[dict[str, object]]:
        """Plan supported work with a fixed, inspectable dependency order."""
        task_terms = _tokens(user_task)
        planned: list[tuple[str, str]] = []
        if task_terms & {"redact", "pii", "secret", "personal", "email", "phone"}:
            planned.append(("redact", "Redact PII before sharing this support ticket"))
        if task_terms & {"triage", "risk", "incident", "support", "customer", "outage"}:
            planned.append(("triage", "Triage support risk for this customer incident"))
        if task_terms & {"stack", "trace", "error", "code", "line"}:
            planned.append(("extract_errors", "Extract structured error codes and line numbers from this stack trace"))
        if task_terms & {"date", "format", "calendar"}:
            planned.append(("normalize_dates", "Normalize inconsistent date formats in this import log"))
        if "invoice" in task_terms:
            planned.append(("extract_invoices", "Extract invoice IDs from billing logs"))
        if not planned:
            raise GeneratorError(
                "Offline planner found no supported capability or reviewed template for this task. "
                "It will not invent a capability without a configured model."
            )
        steps: list[dict[str, object]] = []
        prior: str | None = None
        for step_id, task in planned:
            steps.append({"id": step_id, "task": task, "payload": payload, "depends_on": [prior] if prior else []})
            prior = step_id
        return steps
