"""Minimal JSON runner used inside the ForgeAgent sandbox image.

This file deliberately has no project imports.  The container receives source and
payload over stdin and returns one JSON object on stdout.  It is not a complete
defence against a compromised kernel; it is one layer in the production profile.
"""

from __future__ import annotations

import ast
import json
import sys


ALLOWED_IMPORTS = {"collections", "csv", "datetime", "json", "math", "re", "statistics", "string"}
BLOCKED_CALLS = {"open", "exec", "eval", "compile", "__import__"}
SAFE_BUILTINS = {
    "__import__": __import__, "abs": abs, "all": all, "any": any, "bool": bool,
    "dict": dict, "enumerate": enumerate, "float": float, "int": int,
    "isinstance": isinstance, "len": len, "list": list, "max": max, "min": min,
    "range": range, "round": round, "set": set, "sorted": sorted, "str": str,
    "sum": sum, "tuple": tuple, "zip": zip,
}


def validate(source: str) -> ast.Module:
    tree = ast.parse(source, mode="exec")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = [item.name.split(".")[0] for item in node.names] if isinstance(node, ast.Import) else [(node.module or "").split(".")[0]]
            if any(module not in ALLOWED_IMPORTS for module in modules):
                raise RuntimeError("disallowed import")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in BLOCKED_CALLS:
            raise RuntimeError("disallowed operation")
    return tree


def main() -> None:
    source = json.loads(sys.stdin.readline())
    payload = json.loads(sys.stdin.readline())
    tree = validate(source)
    namespace = {"__builtins__": SAFE_BUILTINS}
    exec(compile(tree, "generated_tool.py", "exec"), namespace, namespace)
    print(json.dumps({"ok": True, "output": namespace["run"](payload)}, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
