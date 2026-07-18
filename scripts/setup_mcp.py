#!/usr/bin/env python3
"""Safely register ForgeAgent's local MCP server with installed coding agents.

Dry-run is the default. ``--apply`` is required before this script writes a
client configuration or invokes Claude Code's documented registration command.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


SERVER_NAME = "forgeagent-foundry"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class SetupError(RuntimeError):
    """A configuration cannot be safely read or changed."""


@dataclass(frozen=True)
class SetupTarget:
    """One documented client setup route.

    ``toml`` is Codex's user config, ``json`` is Cursor's global config, and
    ``claude`` is Claude Code's documented project-scope ``.mcp.json`` route.
    """

    client: str
    config_path: Path
    kind: str
    detected: bool


def server_entry(server_path: str | Path) -> dict[str, object]:
    """Build a portable local-stdio entry using absolute executable paths."""
    return {"command": str(Path(sys.executable).resolve()), "args": [str(Path(server_path).resolve())]}


def discover_clients(
    root: str | Path = REPOSITORY_ROOT,
    home: str | Path | None = None,
    command_exists: Callable[[str], str | None] = shutil.which,
) -> list[SetupTarget]:
    """Find plausible client installations without writing to any path.

    The documented config locations are home-relative and therefore work on
    macOS, Linux, and Windows. Claude Code is deliberately configured through
    its documented project-scope ``.mcp.json`` plus the ``claude`` CLI rather
    than a guessed private global-settings file.
    """
    repository = Path(root).resolve()
    user_home = Path(home).expanduser().resolve() if home is not None else Path.home()
    codex_home = Path(os.environ.get("CODEX_HOME", user_home / ".codex")).expanduser()
    codex_config = codex_home / "config.toml"
    cursor_config = user_home / ".cursor" / "mcp.json"
    claude_config = repository / ".mcp.json"
    return [
        SetupTarget("codex", codex_config, "toml", bool(command_exists("codex") or codex_config.parent.exists())),
        SetupTarget(
            "cursor",
            cursor_config,
            "json",
            bool(command_exists("cursor") or command_exists("cursor-agent") or cursor_config.parent.exists()),
        ),
        SetupTarget("claude-code", claude_config, "claude", bool(command_exists("claude") or (repository / ".claude").exists())),
    ]


def configure_targets(
    targets: list[SetupTarget],
    server_path: str | Path,
    *,
    apply: bool,
    runner: Callable[[list[str], Path], None] | None = None,
) -> list[dict[str, str]]:
    """Describe or apply one idempotent ForgeAgent entry for each target."""
    entry = server_entry(server_path)
    results: list[dict[str, str]] = []
    for target in targets:
        if not target.detected:
            results.append({"client": target.client, "state": "not_detected", "detail": "No known executable or config directory was found."})
            continue
        if _already_configured(target):
            results.append({"client": target.client, "state": "already_configured", "detail": f"{SERVER_NAME} is already present in {target.config_path}."})
            continue
        detail = _planned_detail(target, entry)
        if not apply:
            results.append({"client": target.client, "state": "would_configure", "detail": detail})
            continue
        _backup_existing(target.config_path)
        if target.kind == "json":
            _merge_json(target.config_path, entry)
        elif target.kind == "toml":
            _merge_toml(target.config_path, entry)
        elif target.kind == "claude":
            command = ["claude", "mcp", "add-json", SERVER_NAME, json.dumps({"type": "stdio", **entry}), "--scope", "project"]
            (runner or _run_claude)(command, target.config_path.parent)
        else:
            raise SetupError(f"Unsupported setup target kind: {target.kind}")
        results.append({"client": target.client, "state": "configured", "detail": detail})
    return results


def _planned_detail(target: SetupTarget, entry: dict[str, object]) -> str:
    if target.kind == "claude":
        return f"Would back up {target.config_path} if present, then run Claude Code project setup for {entry['args'][0]}."
    return f"Would add {SERVER_NAME} to {target.config_path} with server {entry['args'][0]}."


def _already_configured(target: SetupTarget) -> bool:
    if not target.config_path.exists():
        return False
    if target.kind in {"json", "claude"}:
        return SERVER_NAME in _read_json(target.config_path).get("mcpServers", {})
    if target.kind == "toml":
        text = target.config_path.read_text(encoding="utf-8")
        return f"[mcp_servers.{SERVER_NAME}]" in text
    raise SetupError(f"Unsupported setup target kind: {target.kind}")


def _read_json(path: Path) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SetupError(f"Refusing to change invalid JSON config {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SetupError(f"Refusing to change {path}: top-level JSON must be an object.")
    servers = data.get("mcpServers")
    if servers is not None and not isinstance(servers, dict):
        raise SetupError(f"Refusing to change {path}: mcpServers must be an object.")
    return data


def _backup_existing(path: Path) -> Path | None:
    if not path.exists():
        return None
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_name(f"{path.name}.bak.{timestamp}")
    if backup.exists():
        raise SetupError(f"Refusing to overwrite an existing backup: {backup}")
    shutil.copy2(path, backup)
    return backup


def _merge_json(path: Path, entry: dict[str, object]) -> None:
    data = _read_json(path) if path.exists() else {}
    servers = data.setdefault("mcpServers", {})
    assert isinstance(servers, dict)
    servers[SERVER_NAME] = entry
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _merge_toml(path: Path, entry: dict[str, object]) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if f"[mcp_servers.{SERVER_NAME}]" in existing:
        return
    if any(line.strip().startswith("mcp_servers =") for line in existing.splitlines()):
        raise SetupError(f"Refusing to edit {path}: inline mcp_servers cannot be safely merged by this dependency-free helper.")
    section = (
        f"\n[mcp_servers.{SERVER_NAME}]\n"
        f"command = {json.dumps(entry['command'])}\n"
        f"args = {json.dumps(entry['args'])}\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(existing.rstrip() + section, encoding="utf-8")


def _run_claude(command: list[str], cwd: Path) -> None:
    try:
        completed = subprocess.run(command, cwd=str(cwd), text=True, capture_output=True, check=False)
    except OSError as exc:
        raise SetupError(f"Claude Code could not be started: {exc}") from exc
    if completed.returncode:
        message = completed.stderr.strip() or completed.stdout.strip() or f"exit code {completed.returncode}"
        raise SetupError(f"Claude Code MCP registration failed: {message}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Safely register ForgeAgent with installed MCP clients.")
    parser.add_argument("--apply", action="store_true", help="Apply changes. Without this flag the script only prints a dry-run plan.")
    args = parser.parse_args()
    try:
        results = configure_targets(discover_clients(), REPOSITORY_ROOT / "forgeagent" / "mcp_server.py", apply=args.apply)
    except SetupError as exc:
        parser.error(str(exc))
    for result in results:
        print(f"{result['client']}: {result['state']} — {result['detail']}")
    if not args.apply:
        print("Dry run only: no client configuration was written. Re-run with --apply to make these changes.")


if __name__ == "__main__":
    main()
