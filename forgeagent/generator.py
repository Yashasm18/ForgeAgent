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
    # Live proposals state how they relate to inspected repository code.
    # The default preserves every curated/offline constructor and flow.
    relationship: str = ""


@dataclass(frozen=True)
class ProofCase:
    """One expected-result case, including dynamically generated adversarial evidence."""

    category: str
    input: object
    expected_output: object
    rationale: str


class ProposalGenerator(Protocol):
    def propose(self, capability: str, payload: object, repository_context: str | None = None) -> ToolProposal: ...
    def propose_adversarial_cases(self, proposal: ToolProposal) -> list[ProofCase]: ...


class GeneratorError(RuntimeError):
    pass


SYSTEM_PROMPT = """You generate one tiny, deterministic Python data tool for ForgeAgent.
Return JSON only with keys name, description, source, tests, relationship.
source must define exactly run(payload). tests is an array of objects with input and expected_output.
Each test input and expected_output must be a JSON-encoded string, not a nested
JSON value: for example, input='{"text":"INV-1"}' and
expected_output='["INV-1"]'. ForgeAgent parses those strings before proof.
The tool receives JSON-compatible payload and returns JSON-compatible data.
No filesystem, network, subprocesses, reflection, eval, exec, globals, or imports outside:
collections,csv,datetime,json,math,re,statistics,string.
Use at least two meaningful edge-case tests. Keep source under 120 lines.
When repository context is supplied, relationship must begin with exactly one
of REUSE:, EXTEND:, or SEPARATE: and briefly explain the decision. Do not
duplicate supplied code without a stated reason."""

PLAN_PROMPT = """You are ForgeAgent's capability planner. Return JSON only:
{"steps":[{"id":"short_id","task":"specific capability request","payload":"{\\"text\\":\\"example\\"}","depends_on":[]}]}
Decompose the user request into the minimum dependency-ordered, independently
verifiable capabilities. Do not invent external side effects. Every step payload
must be a JSON-encoded object string. Use at most five steps."""

ADVERSARIAL_PROMPT = """You are ForgeAgent's adversarial proof author. Read the
candidate source and its stated JSON contract. Return JSON only in this form:
{"cases":[{"input":"{\\"text\\":\\"...\\"}","expected_output":"[]","rationale":"why this input
could expose a contract, correctness, or exception bug"}]}
Propose 2 to 4 JSON-encoded input and expected_output strings that are
specifically likely to make the candidate return an incorrect result or raise
unexpectedly. expected_output must decode to the correct JSON-compatible result
required by the stated contract.
Do not propose filesystem, network, reflection, dynamic execution, or any
non-JSON input. Do not change the candidate source."""

CAPABILITY_MATCH_PROMPT = """You are ForgeAgent's read-only capability matcher.
Given a user task and an allowlisted catalog of existing capability names and
descriptions, decide whether exactly one catalog capability satisfies the same
intent. Return JSON only in this form: {"capability_name":"exact_name"} or
{"capability_name":null}. Never invent a name, modify the catalog, propose new
code, or select a capability unless the intent is a clear match."""

# Responses Structured Outputs requires a declared ``type`` at every schema
# location. Arbitrary nested JSON objects cannot be represented there without
# relaxing ``additionalProperties`` (which the strict API disallows), so test
# values travel as JSON-encoded strings and are decoded before proof execution.
JSON_ENCODED_VALUE_SCHEMA: dict[str, object] = {
    "type": "string",
    "description": "A JSON-encoded input or expected-output value.",
}

PROPOSAL_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string"},
        "description": {"type": "string"},
        "source": {"type": "string"},
        "relationship": {
            "type": "string",
            "minLength": 1,
            "description": "Begin with REUSE:, EXTEND:, or SEPARATE: and explain the repository-context decision.",
        },
        "tests": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "input": JSON_ENCODED_VALUE_SCHEMA,
                    "expected_output": JSON_ENCODED_VALUE_SCHEMA,
                },
                "required": ["input", "expected_output"],
            },
        },
    },
    "required": ["name", "description", "source", "tests", "relationship"],
}

CAPABILITY_MATCH_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "capability_name": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "required": ["capability_name"],
}

PLAN_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "steps": {
            "type": "array",
            "minItems": 1,
            "maxItems": 5,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "task": {"type": "string"},
                    "payload": {
                        "type": "string",
                        "description": "A JSON-encoded object payload for this step.",
                    },
                    "depends_on": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["id", "task", "payload", "depends_on"],
            },
        },
    },
    "required": ["steps"],
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
                    "input": JSON_ENCODED_VALUE_SCHEMA,
                    "expected_output": JSON_ENCODED_VALUE_SCHEMA,
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
    provider = "openai"

    def __init__(self, api_key: str | None = None, model: str = "gpt-5.6-terra"):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model
        if not self.api_key:
            raise GeneratorError("OPENAI_API_KEY is required for live GPT-5.6 generation")

    @property
    def provider_label(self) -> str:
        return f"OpenAI ({self.model})"

    def propose(self, capability: str, payload: object, repository_context: str | None = None) -> ToolProposal:
        context = (
            "\n\nRelevant existing repository context (matched symbols only):\n"
            f"{repository_context}\n"
            "Use this narrow evidence to decide whether to reuse a pattern, extend it, or build a separate capability."
            if repository_context
            else "\n\nNo relevant repository code was supplied. Set relationship to SEPARATE: and state why a standalone capability is warranted."
        )
        text = self._complete(
            SYSTEM_PROMPT,
            f"Capability: {capability}\nExample payload: {json.dumps(payload)}{context}",
            schema_name="forgeagent_tool_proposal",
            schema=PROPOSAL_SCHEMA,
        )
        return _parse_proposal(text, f"GPT-5.6 ({self.model})")

    def plan(self, user_task: str, payload: object) -> list[dict[str, object]]:
        text = self._complete(PLAN_PROMPT, f"User task: {user_task}\nInput: {json.dumps(payload)}")
        return _parse_plan(text, f"GPT-5.6 ({self.model})")

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
            # The response body contains the actionable API validation message
            # (for example, an unavailable model or unsupported schema).  It
            # never contains the bearer token, but keep it bounded so a remote
            # error cannot flood a CLI or audit surface.
            try:
                error_body = json.loads(exc.read().decode("utf-8", "replace"))
                detail = str(error_body.get("error", {}).get("message", "")).strip()
            except (ValueError, AttributeError):
                detail = ""
            suffix = f": {detail[:800]}" if detail else ""
            raise GeneratorError(f"GPT-5.6 request failed: HTTP {exc.code}{suffix}") from exc
        except urllib.error.URLError as exc:
            raise GeneratorError(f"GPT-5.6 request failed: {exc.reason}") from exc
        text = body.get("output_text", "")
        if not text:
            raise GeneratorError("GPT-5.6 returned no text proposal")
        return text


class OllamaGenerator:
    """Dependency-free local Ollama provider for ForgeAgent's live contracts.

    This is intentionally a provider, not a fallback: callers opt into it and
    retain the exact same proposal, proof, repair, and governance path as the
    OpenAI provider.  No API key is read or transmitted for a local host.
    """

    semantic_matching_available = True
    provider = "ollama"

    def __init__(
        self,
        model: str | None = None,
        host: str | None = None,
    ) -> None:
        self.model = model or os.environ.get("FORGEAGENT_OLLAMA_MODEL", "qwen2.5-coder:14b")
        configured_host = host or os.environ.get("FORGEAGENT_OLLAMA_HOST") or os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434"
        self.host = configured_host.rstrip("/")
        if not self.model.strip():
            raise GeneratorError("An Ollama model is required. Set FORGEAGENT_OLLAMA_MODEL or pass --ollama-model.")
        if not self.host.startswith(("http://", "https://")):
            raise GeneratorError("Ollama host must be an http(s) URL, for example http://127.0.0.1:11434.")

    @property
    def provider_label(self) -> str:
        return f"Ollama ({self.model})"

    def propose(self, capability: str, payload: object, repository_context: str | None = None) -> ToolProposal:
        context = (
            "\n\nRelevant existing repository context (matched symbols only):\n"
            f"{repository_context}\n"
            "Use this narrow evidence to decide whether to reuse a pattern, extend it, or build a separate capability."
            if repository_context
            else "\n\nNo relevant repository code was supplied. Set relationship to SEPARATE: and state why a standalone capability is warranted."
        )
        text = self._complete(
            SYSTEM_PROMPT,
            f"Capability: {capability}\nExample payload: {json.dumps(payload)}{context}",
            PROPOSAL_SCHEMA,
        )
        return _parse_proposal(text, self.provider_label)

    def plan(self, user_task: str, payload: object) -> list[dict[str, object]]:
        text = self._complete(PLAN_PROMPT, f"User task: {user_task}\nInput: {json.dumps(payload)}", PLAN_SCHEMA)
        return _parse_plan(text, self.provider_label)

    def propose_adversarial_cases(self, proposal: ToolProposal) -> list[ProofCase]:
        candidate = {
            "name": proposal.name,
            "description": proposal.description,
            "source": proposal.source,
            "existing_tests": [{"input": input_value, "expected_output": expected} for input_value, expected in proposal.tests],
        }
        text = self._complete(
            ADVERSARIAL_PROMPT,
            f"Candidate to attack:\n{json.dumps(candidate)}",
            ADVERSARIAL_CASES_SCHEMA,
        )
        return _parse_adversarial_cases(text)

    def match_existing_capability(self, task: str, capabilities: list[dict[str, str]]) -> str | None:
        catalog = [{"name": item["name"], "description": item["description"]} for item in capabilities]
        text = self._complete(
            CAPABILITY_MATCH_PROMPT,
            f"Task: {task}\nExisting capability catalog: {json.dumps(catalog)}",
            CAPABILITY_MATCH_SCHEMA,
        )
        return _parse_capability_match(text, {item["name"] for item in catalog})

    def _complete(self, system_prompt: str, user_text: str, schema: dict[str, object]) -> str:
        # Ollama's native API accepts the JSON Schema directly in `format`.
        # Repeating it in the prompt follows Ollama's structured-output
        # guidance and helps smaller local models honour nested contracts.
        grounded_user_text = f"{user_text}\n\nRequired JSON Schema:\n{json.dumps(schema, sort_keys=True)}"
        request_body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": grounded_user_text},
            ],
            "format": schema,
            "stream": False,
            "options": {"temperature": 0},
        }
        request = urllib.request.Request(
            f"{self.host}/api/chat",
            data=json.dumps(request_body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                body = json.load(response)
        except urllib.error.HTTPError as exc:
            raise GeneratorError(f"Ollama request failed: HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise GeneratorError(
                f"Ollama is unavailable at {self.host}. Start it with `ollama serve` and pull `{self.model}`."
            ) from exc
        if isinstance(body.get("error"), str):
            raise GeneratorError(f"Ollama request failed: {body['error']}")
        message = body.get("message")
        text = message.get("content") if isinstance(message, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise GeneratorError("Ollama returned no structured text response")
        return text


def create_live_generator(
    provider: str,
    *,
    openai_model: str = "gpt-5.6-terra",
    ollama_model: str | None = None,
    ollama_host: str | None = None,
) -> ProposalGenerator:
    """Create an explicitly selected live provider; never silently switch one."""
    normalized = provider.strip().lower()
    if normalized == "openai":
        return GPT56Generator(model=openai_model)
    if normalized == "ollama":
        return OllamaGenerator(model=ollama_model, host=ollama_host)
    raise GeneratorError("provider must be 'openai' or 'ollama'")


def _parse_proposal(text: str, provenance: str) -> ToolProposal:
    try:
        data = json.loads(text)
        tests = tuple((_decode_json_value(item["input"]), _decode_json_value(item["expected_output"])) for item in data["tests"])
        if not tests:
            raise ValueError("no tests")
        relationship = data["relationship"]
        if not isinstance(relationship, str) or not relationship.startswith(("REUSE:", "EXTEND:", "SEPARATE:")):
            raise ValueError("relationship must begin with REUSE:, EXTEND:, or SEPARATE:")
        return ToolProposal(data["name"], data["description"], data["source"], tests, provenance, relationship)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise GeneratorError("Live generator proposal was not valid ForgeAgent JSON") from exc


def _parse_plan(text: str, provider_label: str) -> list[dict[str, object]]:
    try:
        data = json.loads(text)
        steps = data["steps"]
        if not isinstance(steps, list) or not steps:
            raise ValueError("empty plan")
        normalized_steps = []
        for step in steps:
            payload = _decode_json_value(step["payload"])
            if not isinstance(payload, dict):
                raise ValueError("step payload must decode to an object")
            normalized_steps.append({**step, "payload": payload})
        return normalized_steps
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise GeneratorError(f"{provider_label} plan was not valid ForgeAgent JSON") from exc


def _parse_adversarial_cases(text: str) -> list[ProofCase]:
    try:
        data = json.loads(text)
        raw_cases = data["cases"]
        if not isinstance(raw_cases, list) or not 2 <= len(raw_cases) <= 4:
            raise ValueError("expected 2-4 adversarial cases")
        cases = [
            ProofCase("adversarial", _decode_json_value(item["input"]), _decode_json_value(item["expected_output"]), item["rationale"])
            for item in raw_cases
        ]
        for case in cases:
            json.dumps(case.input)
            json.dumps(case.expected_output)
            if not isinstance(case.rationale, str) or not case.rationale.strip():
                raise ValueError("missing adversarial rationale")
        return cases
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise GeneratorError("Live generator adversarial proof cases were not valid ForgeAgent JSON") from exc


def _decode_json_value(value: object) -> object:
    """Decode the typed transport used by strict Structured Outputs."""
    if not isinstance(value, str):
        raise ValueError("expected a JSON-encoded string")
    return json.loads(value)


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
        raise GeneratorError("Live generator semantic match was not valid ForgeAgent JSON") from exc
