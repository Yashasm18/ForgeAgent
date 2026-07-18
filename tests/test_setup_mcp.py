import json
import tempfile
import unittest
from pathlib import Path

from scripts.setup_mcp import SetupTarget, configure_targets


class SetupMcpTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.server = self.root / "ForgeAgent" / "forgeagent" / "mcp_server.py"
        self.server.parent.mkdir(parents=True)
        self.server.write_text("# fixture server\n", encoding="utf-8")

    def tearDown(self):
        self.directory.cleanup()

    def test_dry_run_never_creates_or_modifies_client_config(self):
        config = self.root / "cursor" / "mcp.json"
        target = SetupTarget("cursor", config, "json", True)

        result = configure_targets([target], self.server, apply=False)

        self.assertFalse(config.exists())
        self.assertEqual(result[0]["state"], "would_configure")
        self.assertIn(str(self.server.resolve()), result[0]["detail"])

    def test_apply_backs_up_and_merges_existing_json_config(self):
        config = self.root / "cursor" / "mcp.json"
        config.parent.mkdir(parents=True)
        original = {"mcpServers": {"unrelated": {"command": "node", "args": ["server.js"]}}, "otherSetting": True}
        config.write_text(json.dumps(original), encoding="utf-8")
        target = SetupTarget("cursor", config, "json", True)

        result = configure_targets([target], self.server, apply=True)

        self.assertEqual(result[0]["state"], "configured")
        backups = list(config.parent.glob("mcp.json.bak.*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(json.loads(backups[0].read_text(encoding="utf-8")), original)
        merged = json.loads(config.read_text(encoding="utf-8"))
        self.assertEqual(merged["mcpServers"]["unrelated"], original["mcpServers"]["unrelated"])
        self.assertTrue(merged["otherSetting"])
        self.assertEqual(merged["mcpServers"]["forgeagent-foundry"]["args"], [str(self.server.resolve())])

    def test_apply_is_idempotent_and_does_not_duplicate_forgeagent_entry(self):
        config = self.root / "cursor" / "mcp.json"
        target = SetupTarget("cursor", config, "json", True)

        configure_targets([target], self.server, apply=True)
        result = configure_targets([target], self.server, apply=True)

        self.assertEqual(result[0]["state"], "already_configured")
        merged = json.loads(config.read_text(encoding="utf-8"))
        self.assertEqual(list(merged["mcpServers"]), ["forgeagent-foundry"])

    def test_claude_apply_backs_up_project_config_then_uses_documented_cli(self):
        config = self.root / ".mcp.json"
        config.write_text(json.dumps({"mcpServers": {"unrelated": {"command": "node"}}}), encoding="utf-8")
        target = SetupTarget("claude-code", config, "claude", True)
        calls = []

        def fake_runner(command, cwd):
            calls.append((command, cwd))
            data = json.loads(config.read_text(encoding="utf-8"))
            data["mcpServers"]["forgeagent-foundry"] = json.loads(command[4])
            config.write_text(json.dumps(data), encoding="utf-8")

        result = configure_targets([target], self.server, apply=True, runner=fake_runner)

        self.assertEqual(result[0]["state"], "configured")
        self.assertEqual(len(list(self.root.glob(".mcp.json.bak.*"))), 1)
        self.assertEqual(calls[0][0][:4], ["claude", "mcp", "add-json", "forgeagent-foundry"])
        self.assertIn("--scope", calls[0][0])
        self.assertIn("project", calls[0][0])

    def test_codex_toml_preserves_existing_config_when_adding_server(self):
        config = self.root / "codex" / "config.toml"
        config.parent.mkdir(parents=True)
        config.write_text('model = "gpt-5.6"\n\n[mcp_servers.docs]\ncommand = "docs"\n', encoding="utf-8")
        target = SetupTarget("codex", config, "toml", True)

        configure_targets([target], self.server, apply=True)

        text = config.read_text(encoding="utf-8")
        self.assertIn('model = "gpt-5.6"', text)
        self.assertIn("[mcp_servers.docs]", text)
        self.assertIn("[mcp_servers.forgeagent-foundry]", text)
        self.assertEqual(len(list(config.parent.glob("config.toml.bak.*"))), 1)


if __name__ == "__main__":
    unittest.main()
