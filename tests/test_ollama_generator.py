import io
import json
import unittest
from unittest.mock import patch

from forgeagent.generator import (
    ADVERSARIAL_CASES_SCHEMA,
    CAPABILITY_MATCH_SCHEMA,
    PLAN_SCHEMA,
    PROPOSAL_SCHEMA,
    OllamaGenerator,
    create_live_generator,
)


class OllamaGeneratorTests(unittest.TestCase):
    def test_provider_factory_selects_ollama_without_reading_an_api_key(self):
        generator = create_live_generator(
            "ollama",
            ollama_model="local-test-model",
            ollama_host="http://127.0.0.1:11434",
        )

        self.assertIsInstance(generator, OllamaGenerator)
        self.assertEqual(generator.model, "local-test-model")
        self.assertEqual(generator.provider_label, "Ollama (local-test-model)")

    def test_ollama_uses_local_structured_outputs_for_every_live_operation(self):
        """Ollama must use the same typed contracts as the OpenAI provider."""
        responses = iter((
            {
                "name": "order_id_extractor",
                "description": "Extract ORD-<digits> order IDs.",
                "source": "import re\ndef run(payload):\n    return re.findall(r'\\bORD-\\d+\\b', payload['text'])\n",
                "tests": [{"input": "{\"text\": \"ORD-1\"}", "expected_output": "[\"ORD-1\"]"}],
                "relationship": "SEPARATE: No relevant order-ID parser was supplied.",
            },
            {"capability_name": "date_format_normalizer"},
            {
                "cases": [
                    {"input": "{\"text\": \"\"}", "expected_output": "[]", "rationale": "Empty input must be safe."},
                    {"input": "{\"text\": \"ORD-001\"}", "expected_output": "[\"ORD-001\"]", "rationale": "Leading zeroes must be preserved."},
                ],
            },
            {"steps": [{"id": "extract", "task": "Extract order IDs", "payload": "{\"text\": \"ORD-1\"}", "depends_on": []}]},
        ))
        request_bodies = []

        def fake_urlopen(request, timeout):
            request_bodies.append(json.loads(request.data.decode("utf-8")))
            return io.BytesIO(json.dumps({"message": {"content": json.dumps(next(responses))}}).encode("utf-8"))

        with patch("forgeagent.generator.urllib.request.urlopen", side_effect=fake_urlopen):
            generator = OllamaGenerator(model="test-coder", host="http://ollama.test")
            proposal = generator.propose("Extract order IDs", {"text": "ORD-1"})
            match = generator.match_existing_capability(
                "Fix inconsistent dates in this log",
                [{"name": "date_format_normalizer", "description": "Normalize date formats."}],
            )
            cases = generator.propose_adversarial_cases(proposal)
            plan = generator.plan("Extract order IDs", {"text": "ORD-1"})

        self.assertEqual(proposal.name, "order_id_extractor")
        self.assertEqual(match, "date_format_normalizer")
        self.assertEqual(len(cases), 2)
        self.assertEqual(plan[0]["id"], "extract")
        self.assertEqual(len(request_bodies), 4)
        for body in request_bodies:
            self.assertEqual(body["model"], "test-coder")
            self.assertFalse(body["stream"])
            self.assertEqual(body["options"]["temperature"], 0)
            self.assertEqual(body["messages"][0]["role"], "system")
        self.assertEqual(
            [body["format"] for body in request_bodies],
            [PROPOSAL_SCHEMA, CAPABILITY_MATCH_SCHEMA, ADVERSARIAL_CASES_SCHEMA, PLAN_SCHEMA],
        )


if __name__ == "__main__":
    unittest.main()
