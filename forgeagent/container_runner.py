"""Minimal JSON runner used inside the ForgeAgent sandbox image.

This file deliberately has no project imports.  The container receives source and
payload over stdin and returns one JSON object on stdout.  It is not a complete
defence against a compromised kernel; it is one layer in the production profile.
"""

from __future__ import annotations

import ast
import builtins
import json
import sys


ALLOWED_IMPORTS = {"collections", "csv", "datetime", "json", "math", "re", "statistics", "string"}
FORBIDDEN_NAME_REFERENCES = {
    "__import__", "eval", "exec", "compile", "open", "globals", "locals", "vars",
    "getattr", "setattr", "delattr", "__builtins__", "__loader__", "__subclasses__",
}
SAFE_BUILTINS = {
    "abs": abs, "all": all, "any": any, "bool": bool,
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
        if isinstance(node, ast.Name) and (node.id in FORBIDDEN_NAME_REFERENCES or (node.id.startswith("__") and node.id.endswith("__"))):
            raise RuntimeError("disallowed name reference")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__") and node.attr.endswith("__"):
            raise RuntimeError("disallowed dunder attribute")
    return tree


def main() -> None:
    source = json.loads(sys.stdin.readline())
    payload = json.loads(sys.stdin.readline())
    tree = validate(source)
    def safe_import(name: str, globals: object = None, locals: object = None, fromlist: object = (), level: int = 0) -> object:
        if level or name.split(".")[0] not in ALLOWED_IMPORTS:
            raise ImportError("disallowed import")
        return builtins.__import__(name, globals, locals, fromlist, level)

    namespace = {"__builtins__": {**SAFE_BUILTINS, "__import__": safe_import}}
    exec(compile(tree, "generated_tool.py", "exec"), namespace, namespace)
    print(json.dumps({"ok": True, "output": namespace["run"](payload)}, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
