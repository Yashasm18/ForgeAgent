import io
import json
import unittest
from unittest.mock import patch

from forgeagent.generator import (
    ADVERSARIAL_CASES_SCHEMA,
    CAPABILITY_MATCH_SCHEMA,
    GPT56Generator,
    PROPOSAL_SCHEMA,
)


class StructuredOutputGeneratorTests(unittest.TestCase):
    def test_live_calls_send_responses_api_schemas_and_parse_clean_json(self):
        """Mock the three live calls without requiring an API key or network."""
        responses = iter((
            {
                "name": "invoice_id_extractor",
                "description": "Extract invoice IDs from support logs.",
                "source": "def run(payload):\n    return []\n",
                "tests": [{"input": {"text": "INV-1"}, "expected_output": ["INV-1"]}],
                "relationship": "EXTEND: Reuse the matched invoice parser's identifier pattern while adding log extraction.",
            },
            {"capability_name": "invoice_id_extractor"},
            {
                "cases": [
                    {"input": {"text": ""}, "expected_output": [], "rationale": "Empty logs must not raise."},
                    {"input": {"text": "INV-000"}, "expected_output": ["INV-000"], "rationale": "Leading zeroes must be preserved."},
                ],
            },
        ))
        request_bodies = []

        def fake_urlopen(request, timeout):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            return io.BytesIO(json.dumps({"output_text": json.dumps(next(responses))}).encode("utf-8"))

        with patch("forgeagent.generator.urllib.request.urlopen", side_effect=fake_urlopen):
            generator = GPT56Generator(api_key="test-key")
            proposal = generator.propose(
                "Extract invoice IDs",
                {"text": "INV-1"},
                repository_context="File: parser.py\nSymbol: parse_invoice\nDocstring: Parse invoice identifiers.\nExcerpt:\ndef parse_invoice(payload):\n    return payload",
            )
            match = generator.match_existing_capability(
                "Find the invoice identifier",
                [{"name": "invoice_id_extractor", "description": "Extract invoice IDs from support logs."}],
            )
            cases = generator.propose_adversarial_cases(proposal)

        # Each mocked response is plain JSON, with no Markdown fence to strip.
        self.assertEqual(proposal.name, "invoice_id_extractor")
        self.assertTrue(proposal.relationship.startswith("EXTEND:"))
        self.assertEqual(match, "invoice_id_extractor")
        self.assertEqual(len(cases), 2)

        expected = (
            ("forgeagent_tool_proposal", PROPOSAL_SCHEMA),
            ("forgeagent_capability_match", CAPABILITY_MATCH_SCHEMA),
            ("forgeagent_adversarial_cases", ADVERSARIAL_CASES_SCHEMA),
        )
        self.assertEqual(len(request_bodies), len(expected))
        for body, (name, schema) in zip(request_bodies, expected):
            self.assertIn("input", body)
            self.assertEqual(body["text"], {
                "format": {
                    "type": "json_schema",
                    "name": name,
                    "strict": True,
                    "schema": schema,
                },
            })
        proposal_prompt = request_bodies[0]["input"][1]["content"][0]["text"]
        self.assertIn("parser.py", proposal_prompt)
        self.assertIn("parse_invoice", proposal_prompt)
        self.assertIn("Relevant existing repository context", proposal_prompt)


if __name__ == "__main__":
    unittest.main()
