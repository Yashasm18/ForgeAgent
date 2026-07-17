import unittest

from sandbox import SandboxError, execute, policy_violations


class SandboxSecurityTests(unittest.TestCase):
    def test_import_alias_bypass_is_rejected_before_execution(self):
        source = "def run(payload):\n    imp = __import__\n    return imp('os').system('id')\n"
        self.assertIn("disallowed name reference: __import__", policy_violations(source))
        with self.assertRaises(SandboxError):
            execute(source, {})

    def test_class_subclasses_escape_is_rejected_before_execution(self):
        source = "def run(payload):\n    return ().__class__.__bases__[0].__subclasses__()\n"
        findings = policy_violations(source)
        self.assertTrue(any("disallowed dunder attribute" in finding for finding in findings))
        with self.assertRaises(SandboxError):
            execute(source, {})

    def test_dynamic_getattr_escape_is_rejected_before_execution(self):
        source = "def run(payload):\n    return getattr(payload, '__' + 'class__')\n"
        self.assertIn("disallowed name reference: getattr", policy_violations(source))
        with self.assertRaises(SandboxError):
            execute(source, {})

    def test_allowed_imports_continue_to_work_through_restricted_importer(self):
        source = "import re\ndef run(payload):\n    return re.findall(r'\\d+', payload['text'])\n"
        self.assertEqual(execute(source, {"text": "a12 b34"}), ["12", "34"])
