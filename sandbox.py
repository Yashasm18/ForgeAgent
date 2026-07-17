"""Small subprocess sandbox for generated single-function tools.

This is defense-in-depth for a demo, not a security boundary for hostile code.
The child process has a timeout, a minimal environment, a temporary working
directory, and an import allowlist enforced before execution.
"""

from __future__ import annotations

import json
import os
import subprocess
import shutil
import sys
import tempfile
import ast
from dataclasses import dataclass

ALLOWED_IMPORTS = {"collections", "csv", "datetime", "json", "math", "re", "statistics", "string"}
FORBIDDEN_NAME_REFERENCES = {
    "__import__", "eval", "exec", "compile", "open", "globals", "locals", "vars",
    "getattr", "setattr", "delattr", "__builtins__", "__loader__", "__subclasses__",
}

RUNNER = r'''
import ast, builtins, json, sys
ALLOWED = __ALLOWED__
FORBIDDEN = __FORBIDDEN__
source = json.loads(sys.stdin.readline())
payload = json.loads(sys.stdin.readline())
tree = ast.parse(source, mode="exec")
for node in ast.walk(tree):
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        modules = [item.name.split(".")[0] for item in node.names] if isinstance(node, ast.Import) else [(node.module or "").split(".")[0]]
        if any(module not in ALLOWED for module in modules):
            raise RuntimeError("disallowed import")
    if isinstance(node, ast.Name) and (node.id in FORBIDDEN or (node.id.startswith("__") and node.id.endswith("__"))):
        raise RuntimeError("disallowed name reference")
    if isinstance(node, ast.Attribute) and node.attr.startswith("__") and node.attr.endswith("__"):
        raise RuntimeError("disallowed dunder attribute")
def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level or name.split(".")[0] not in ALLOWED:
        raise ImportError("disallowed import")
    return builtins.__import__(name, globals, locals, fromlist, level)
namespace = {"__builtins__": {"__import__": safe_import, "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict, "enumerate": enumerate, "float": float, "int": int, "isinstance": isinstance, "len": len, "list": list, "max": max, "min": min, "range": range, "round": round, "set": set, "sorted": sorted, "str": str, "sum": sum, "tuple": tuple, "zip": zip}}
exec(compile(tree, "generated_tool.py", "exec"), namespace, namespace)
print(json.dumps({"ok": True, "output": namespace["run"](payload)}, sort_keys=True, default=str))
'''.replace("__ALLOWED__", repr(ALLOWED_IMPORTS)).replace("__FORBIDDEN__", repr(FORBIDDEN_NAME_REFERENCES))


class SandboxError(RuntimeError):
    pass


@dataclass(frozen=True)
class SandboxProfile:
    """Runtime limits for a generated capability execution."""

    backend: str
    image: str = "forgeagent-sandbox:local"
    memory: str = "256m"
    cpus: str = "0.50"
    pids: int = 64


def container_command(profile: SandboxProfile = SandboxProfile("container")) -> list[str]:
    """Return the hardened command; kept pure so it can be audited and tested."""
    if profile.backend != "container":
        raise ValueError("container_command requires a container profile")
    return [
        "docker", "run", "--rm", "-i", "--network", "none", "--read-only",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--pids-limit",
        str(profile.pids), "--memory", profile.memory, "--cpus", profile.cpus,
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m", profile.image,
    ]


def policy_violations(source: str) -> list[str]:
    """Return static policy violations before a candidate reaches execution."""
    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError as exc:
        return [f"invalid syntax: {exc.msg}"]
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = [item.name.split(".")[0] for item in node.names] if isinstance(node, ast.Import) else [(node.module or "").split(".")[0]]
            for module in modules:
                if module not in ALLOWED_IMPORTS:
                    violations.append(f"disallowed import: {module}")
        if isinstance(node, ast.Name) and (node.id in FORBIDDEN_NAME_REFERENCES or (node.id.startswith("__") and node.id.endswith("__"))):
            violations.append(f"disallowed name reference: {node.id}")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__") and node.attr.endswith("__"):
            violations.append(f"disallowed dunder attribute: {node.attr}")
    if not any(isinstance(item, ast.FunctionDef) and item.name == "run" for item in tree.body):
        violations.append("missing run(payload) function")
    return sorted(set(violations))


def execute(source: str, payload: object, timeout: float = 2.0, profile: SandboxProfile | None = None) -> object:
    """Run a proven candidate locally or in the hardened container profile.

    `FORGEAGENT_SANDBOX=container` enables the production runner. Set
    `FORGEAGENT_REQUIRE_CONTAINER=1` to reject any accidental local fallback.
    """
    violations = policy_violations(source)
    if violations:
        raise SandboxError("; ".join(violations))
    selected = profile or SandboxProfile(os.environ.get("FORGEAGENT_SANDBOX", "local"))
    if selected.backend not in {"local", "container"}:
        raise SandboxError("Sandbox backend must be local or container")
    if os.environ.get("FORGEAGENT_REQUIRE_CONTAINER") == "1" and selected.backend != "container":
        raise SandboxError("Production policy requires the container sandbox")
    request = json.dumps(source) + "\n" + json.dumps(payload) + "\n"
    if selected.backend == "container":
        if not shutil.which("docker"):
            raise SandboxError("Docker is required for container isolation. Build the sandbox image first.")
        command, workdir, env = container_command(selected), None, {"PATH": os.environ.get("PATH", ""), "PYTHONIOENCODING": "utf-8"}
        try:
            result = subprocess.run(command, input=request, text=True, capture_output=True, timeout=timeout, cwd=workdir, env=env)
        except subprocess.TimeoutExpired as exc:
            raise SandboxError(f"Timed out after {timeout}s") from exc
    else:
        with tempfile.TemporaryDirectory(prefix="forgeagent-") as workdir:
            try:
                result = subprocess.run(
                    [sys.executable, "-I", "-c", RUNNER], input=request, text=True,
                    capture_output=True, timeout=timeout, cwd=workdir,
                    env={"PATH": os.environ.get("PATH", ""), "PYTHONIOENCODING": "utf-8"},
                )
            except subprocess.TimeoutExpired as exc:
                raise SandboxError(f"Timed out after {timeout}s") from exc
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip().splitlines()[-1:]
        raise SandboxError(message[0] if message else "Sandbox execution failed")
    try:
        response = json.loads(result.stdout)
        return response["output"]
    except (json.JSONDecodeError, KeyError) as exc:
        raise SandboxError("Sandbox returned an invalid response") from exc
