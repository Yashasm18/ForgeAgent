import unittest

from incident_analysis import analyze_incident


class IncidentAnalysisTests(unittest.TestCase):
    def test_safe_audit_payload_redacts_sensitive_values(self):
        result = analyze_incident(
            "Ava at ava@example.com is locked out. Secret code 89789. "
            "Secret message is: do not share this. She will cancel today."
        )
        self.assertNotIn("ava@example.com", result.redacted_text)
        self.assertNotIn("89789", result.redacted_text)
        self.assertNotIn("do not share this", result.redacted_text)
        self.assertEqual(result.risk, "high")
        self.assertIn("labelled_secret", result.redaction_categories)
        self.assertNotIn("89789", str(result.audit_payload()))

    def test_ordinary_text_is_supported(self):
        result = analyze_incident("The export button is slow, but the team can continue working.")
        self.assertEqual(result.risk, "low")
        self.assertEqual(result.redaction_categories, ())

    def test_noisy_embedded_secret_code_is_redacted(self):
        result = analyze_incident("sahajsecretcodeis9878787mnxc kcxcds")
        self.assertNotIn("9878787mnxc", result.redacted_text)
        self.assertIn("secretcode [REDACTED_SECRET]", result.redacted_text)
        self.assertIn("labelled_secret", result.redaction_categories)
