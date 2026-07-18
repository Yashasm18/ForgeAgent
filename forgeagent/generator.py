"""Proposal generators for ForgeAgent.

The live generator uses GPT-5.6 through the Responses API.  The curated
generator is deliberately labelled as an offline recording fallback so a demo
never pretends to be a live model call when credentials are unavailable.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ToolProposal:
    name: str
    description: str
    source: str
    tests: tuple[tuple[object, object], ...]
    provenance: str


@dataclass(frozen=True)
class ProofCase:
    """One expected-result case, including dynamically generated adversarial evidence."""

    category: str
    input: object
    expected_output: object
    rationale: str


class ProposalGenerator(Protocol):
    def propose(self, capability: str, payload: object) -> ToolProposal: ...
    def propose_adversarial_cases(self, proposal: ToolProposal) -> list[ProofCase]: ...


class GeneratorError(RuntimeError):
    pass


SYSTEM_PROMPT = """You generate one tiny, deterministic Python data tool for ForgeAgent.
Return JSON only with keys name, description, source, tests.
source must define exactly run(payload). tests is an array of objects with input and expected_output.
The tool receives JSON-compatible payload and returns JSON-compatible data.
No filesystem, network, subprocesses, reflection, eval, exec, globals, or imports outside:
collections,csv,datetime,json,math,re,statistics,string.
Use at least two meaningful edge-case tests. Keep source under 120 lines."""

PLAN_PROMPT = """You are ForgeAgent's capability planner. Return JSON only:
{"steps":[{"id":"short_id","task":"specific capability request","payload":{},"depends_on":[]}]}
Decompose the user request into the minimum dependency-ordered, independently
verifiable capabilities. Do not invent external side effects. Every step payload
must be JSON-compatible. Use at most five steps."""

ADVERSARIAL_PROMPT = """You are ForgeAgent's adversarial proof author. Read the
candidate source and its stated JSON contract. Return JSON only in this form:
{"cases":[{"input":{},"expected_output":{},"rationale":"why this input
could expose a contract, correctness, or exception bug"}]}
Propose 2 to 4 JSON-compatible inputs that are specifically likely to make the
candidate return an incorrect result or raise unexpectedly. expected_output
must be the correct JSON-compatible result required by the stated contract.
Do not propose filesystem, network, reflection, dynamic execution, or any
non-JSON input. Do not change the candidate source."""

CAPABILITY_MATCH_PROMPT = """You are ForgeAgent's read-only capability matcher.
Given a user task and an allowlisted catalog of existing capability names and
descriptions, decide whether exactly one catalog capability satisfies the same
intent. Return JSON only in this form: {"capability_name":"exact_name"} or
{"capability_name":null}. Never invent a name, modify the catalog, propose new
code, or select a capability unless the intent is a clear match."""

# `input` and `expected_output` intentionally accept any JSON-compatible
# value; the surrounding object shape is what Structured Outputs enforces.
JSON_VALUE_SCHEMA: dict[str, object] = {}

PROPOSAL_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string"},
        "description": {"type": "string"},
        "source": {"type": "string"},
        "tests": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "input": JSON_VALUE_SCHEMA,
                    "expected_output": JSON_VALUE_SCHEMA,
                },
                "required": ["input", "expected_output"],
            },
        },
    },
    "required": ["name", "description", "source", "tests"],
}

CAPABILITY_MATCH_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "capability_name": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "required": ["capability_name"],
}

ADVERSARIAL_CASES_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "cases": {
            "type": "array",
            "minItems": 2,
            "maxItems": 4,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "input": JSON_VALUE_SCHEMA,
                    "expected_output": JSON_VALUE_SCHEMA,
                    "rationale": {"type": "string"},
                },
                "required": ["input", "expected_output", "rationale"],
            },
        },
    },
    "required": ["cases"],
}


class GPT56Generator:
    """Minimal stdlib client so the project has no framework dependency."""

    # ForgeAgent checks this explicit capability rather than treating arbitrary
    # proposal generators as live classifiers. Offline fixtures stay offline.
    semantic_matching_available = True

    def __init__(self, api_key: str | None = None, model: str = "gpt-5.6-terra"):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model
        if not self.api_key:
            raise GeneratorError("OPENAI_API_KEY is required for live GPT-5.6 generation")

    def propose(self, capability: str, payload: object) -> ToolProposal:
        text = self._complete(
            SYSTEM_PROMPT,
            f"Capability: {capability}\nExample payload: {json.dumps(payload)}",
            schema_name="forgeagent_tool_proposal",
            schema=PROPOSAL_SCHEMA,
        )
        return _parse_proposal(text, f"GPT-5.6 ({self.model})")

    def plan(self, user_task: str, payload: object) -> list[dict[str, object]]:
        text = self._complete(PLAN_PROMPT, f"User task: {user_task}\nInput: {json.dumps(payload)}")
        try:
            data = json.loads(text)
            steps = data["steps"]
            if not isinstance(steps, list) or not steps:
                raise ValueError("empty plan")
            return steps
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise GeneratorError("GPT-5.6 plan was not valid ForgeAgent JSON") from exc

    def propose_adversarial_cases(self, proposal: ToolProposal) -> list[ProofCase]:
        """Ask GPT-5.6 to attack a candidate before it can earn trust."""
        if not self.api_key:
            raise GeneratorError("OPENAI_API_KEY is required for live adversarial proof generation")
        candidate = {
            "name": proposal.name,
            "description": proposal.description,
            "source": proposal.source,
            "existing_tests": [{"input": input_value, "expected_output": expected} for input_value, expected in proposal.tests],
        }
        text = self._complete(
            ADVERSARIAL_PROMPT,
            f"Candidate to attack:\n{json.dumps(candidate)}",
            schema_name="forgeagent_adversarial_cases",
            schema=ADVERSARIAL_CASES_SCHEMA,
        )
        return _parse_adversarial_cases(text)

    def match_existing_capability(self, task: str, capabilities: list[dict[str, str]]) -> str | None:
        """Return one allowlisted capability name, or ``None`` for no match."""
        if not self.api_key:
            raise GeneratorError("OPENAI_API_KEY is required for semantic capability matching")
        catalog = [{"name": item["name"], "description": item["description"]} for item in capabilities]
        text = self._complete(
            CAPABILITY_MATCH_PROMPT,
            f"Task: {task}\nExisting capability catalog: {json.dumps(catalog)}",
            schema_name="forgeagent_capability_match",
            schema=CAPABILITY_MATCH_SCHEMA,
        )
        return _parse_capability_match(text, {item["name"] for item in catalog})

    def _complete(
        self,
        system_prompt: str,
        user_text: str,
        *,
        schema_name: str | None = None,
        schema: dict[str, object] | None = None,
    ) -> str:
        request_body = {
            "model": self.model,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
                {"role": "user", "content": [{"type": "input_text", "text": user_text}]},
            ],
        }
        if schema_name and schema:
            request_body["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            }
        request = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(request_body).encode(),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                body = json.load(response)
        except urllib.error.HTTPError as exc:
            raise GeneratorError(f"GPT-5.6 request failed: HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise GeneratorError(f"GPT-5.6 request failed: {exc.reason}") from exc
        text = body.get("output_text", "")
        if not text:
            raise GeneratorError("GPT-5.6 returned no text proposal")
        return text


def _parse_proposal(text: str, provenance: str) -> ToolProposal:
    try:
        data = json.loads(text)
        tests = tuple((item["input"], item["expected_output"]) for item in data["tests"])
        if not tests:
            raise ValueError("no tests")
        return ToolProposal(data["name"], data["description"], data["source"], tests, provenance)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise GeneratorError("GPT-5.6 proposal was not valid ForgeAgent JSON") from exc


def _parse_adversarial_cases(text: str) -> list[ProofCase]:
    try:
        data = json.loads(text)
        raw_cases = data["cases"]
        if not isinstance(raw_cases, list) or not 2 <= len(raw_cases) <= 4:
            raise ValueError("expected 2-4 adversarial cases")
        cases = [ProofCase("adversarial", item["input"], item["expected_output"], item["rationale"]) for item in raw_cases]
        for case in cases:
            json.dumps(case.input)
            json.dumps(case.expected_output)
            if not isinstance(case.rationale, str) or not case.rationale.strip():
                raise ValueError("missing adversarial rationale")
        return cases
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise GeneratorError("GPT-5.6 adversarial proof cases were not valid ForgeAgent JSON") from exc


def _parse_capability_match(text: str, allowed_names: set[str]) -> str | None:
    """Parse and validate a semantic match against the caller's allowlist."""
    try:
        data = json.loads(text)
        name = data["capability_name"]
        if name is None:
            return None
        if not isinstance(name, str) or name not in allowed_names:
            raise ValueError("response selected a capability outside the supplied catalog")
        return name
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise GeneratorError("GPT-5.6 semantic match was not valid ForgeAgent JSON") from exc
