"""Small subprocess sandbox for generated single-function tools.

This is defense-in-depth for a demo, not a security boundary for hostile code.
The child process has a timeout, a minimal environment, a temporary working
directory, and an import allowlist enforced before execution.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ALLOWED_IMPORTS = {"collections", "csv", "datetime", "json", "math", "re", "statistics", "string"}

RUNNER = r'''
import ast, json, sys
ALLOWED = __ALLOWED__
source = json.loads(sys.stdin.readline())
payload = json.loads(sys.stdin.readline())
tree = ast.parse(source, mode="exec")
for node in ast.walk(tree):
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        modules = [item.name.split(".")[0] for item in node.names] if isinstance(node, ast.Import) else [(node.module or "").split(".")[0]]
        if any(module not in ALLOWED for module in modules):
            raise RuntimeError("disallowed import")
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"open", "exec", "eval", "compile", "__import__"}:
        raise RuntimeError("disallowed operation")
namespace = {"__builtins__": {"__import__": __import__, "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict, "enumerate": enumerate, "float": float, "int": int, "isinstance": isinstance, "len": len, "list": list, "max": max, "min": min, "range": range, "round": round, "set": set, "sorted": sorted, "str": str, "sum": sum, "tuple": tuple, "zip": zip}}
exec(compile(tree, "generated_tool.py", "exec"), namespace, namespace)
print(json.dumps({"ok": True, "output": namespace["run"](payload)}, sort_keys=True, default=str))
'''.replace("__ALLOWED__", repr(ALLOWED_IMPORTS))


class SandboxError(RuntimeError):
    pass


def execute(source: str, payload: object, timeout: float = 2.0) -> object:
    with tempfile.TemporaryDirectory(prefix="forgeagent-") as workdir:
        try:
            result = subprocess.run(
                [sys.executable, "-I", "-c", RUNNER],
                input=json.dumps(source) + "\n" + json.dumps(payload) + "\n",
                text=True,
                capture_output=True,
                timeout=timeout,
                cwd=workdir,
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
