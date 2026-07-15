"""Proposal generators for ForgeAgent.

The live generator uses GPT-5.6 through the Responses API.  The curated
generator is deliberately labelled as an offline recording fallback so a demo
never pretends to be a live model call when credentials are unavailable.
"""

from __future__ import annotations

import json
import os
import re
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


class ProposalGenerator(Protocol):
    def propose(self, capability: str, payload: object) -> ToolProposal: ...


class GeneratorError(RuntimeError):
    pass


SYSTEM_PROMPT = """You generate one tiny, deterministic Python data tool for ForgeAgent.
Return JSON only with keys name, description, source, tests.
source must define exactly run(payload). tests is an array of objects with input and expected_output.
The tool receives JSON-compatible payload and returns JSON-compatible data.
No filesystem, network, subprocesses, reflection, eval, exec, globals, or imports outside:
collections,csv,datetime,json,math,re,statistics,string.
Use at least two meaningful edge-case tests. Keep source under 120 lines."""


class GPT56Generator:
    """Minimal stdlib client so the project has no framework dependency."""

    def __init__(self, api_key: str | None = None, model: str = "gpt-5.6"):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model
        if not self.api_key:
            raise GeneratorError("OPENAI_API_KEY is required for live GPT-5.6 generation")

    def propose(self, capability: str, payload: object) -> ToolProposal:
        request_body = {
            "model": self.model,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": SYSTEM_PROMPT}]},
                {"role": "user", "content": [{"type": "input_text", "text": f"Capability: {capability}\nExample payload: {json.dumps(payload)}"}]},
            ],
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
        return _parse_proposal(text, f"GPT-5.6 ({self.model})")


def _parse_proposal(text: str, provenance: str) -> ToolProposal:
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    try:
        data = json.loads(fenced.group(1) if fenced else text)
        tests = tuple((item["input"], item["expected_output"]) for item in data["tests"])
        if not tests:
            raise ValueError("no tests")
        return ToolProposal(data["name"], data["description"], data["source"], tests, provenance)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise GeneratorError("GPT-5.6 proposal was not valid ForgeAgent JSON") from exc
