"""Repository intelligence graph used by the Capability Foundry.

It intentionally uses only the Python standard library: a judge can build and
query a graph of source, tests, docs, imports, symbols and headings offline.
"""

from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


SKIP_PARTS = frozenset({".git", "__pycache__", "data", ".venv", "venv", "node_modules"})
TEXT_SUFFIXES = frozenset({".py", ".md", ".txt", ".json", ".yml", ".yaml"})


@dataclass(frozen=True)
class RepoNode:
    id: str
    kind: str
    label: str
    path: str
    metadata: dict[str, object]


@dataclass(frozen=True)
class RepoEdge:
    source: str
    target: str
    relation: str


class RepositoryGraph:
    """Build a compact graph from a repository without executing its code."""

    def __init__(self, root: str | Path = ".") -> None:
        self.root = Path(root).resolve()
        self.nodes: dict[str, RepoNode] = {}
        self.edges: set[RepoEdge] = set()

    def build(self) -> dict[str, object]:
        for path in self._files():
            self._add_file(path)
        return self.export()

    def query(self, term: str, limit: int = 20) -> list[dict[str, object]]:
        normalized = term.lower().strip()
        matches = [node for node in self.nodes.values() if normalized in f"{node.label} {node.path} {node.metadata}".lower()]
        return [asdict(node) for node in sorted(matches, key=lambda item: (item.kind, item.path, item.label))[:limit]]

    def impact(self, capability: str) -> dict[str, object]:
        """Return conservative impact candidates; it never claims certainty."""
        terms = {part for part in re.split(r"[^a-z0-9]+", capability.lower()) if len(part) >= 3}
        relevant = [node for node in self.nodes.values() if any(term in f"{node.label} {node.path}".lower() for term in terms)]
        files = sorted({node.path for node in relevant if node.kind in {"file", "test", "document"}})
        symbols = sorted(node.label for node in relevant if node.kind in {"function", "class", "heading"})
        return {"capability": capability, "impact_candidates": files, "related_symbols": symbols, "confidence": "heuristic; inspect before modifying"}

    def export(self) -> dict[str, object]:
        return {"root": str(self.root), "nodes": [asdict(node) for node in sorted(self.nodes.values(), key=lambda item: item.id)], "edges": [asdict(edge) for edge in sorted(self.edges, key=lambda item: (item.source, item.target, item.relation))]}

    def _files(self) -> Iterable[Path]:
        for path in self.root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            if any(part in SKIP_PARTS for part in path.relative_to(self.root).parts):
                continue
            yield path

    def _add_file(self, path: Path) -> None:
        relative = path.relative_to(self.root).as_posix()
        file_id = self._id("file", relative)
        kind = "test" if relative.startswith("tests/") else "document" if path.suffix == ".md" else "file"
        self.nodes[file_id] = RepoNode(file_id, kind, path.name, relative, {"suffix": path.suffix})
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return
        if path.suffix == ".py":
            self._add_python(file_id, relative, text)
        elif path.suffix == ".md":
            self._add_markdown(file_id, relative, text)

    def _add_python(self, file_id: str, relative: str, text: str) -> None:
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                kind = "class" if isinstance(node, ast.ClassDef) else "function"
                symbol_id = self._id(kind, f"{relative}:{node.name}")
                self.nodes[symbol_id] = RepoNode(symbol_id, kind, node.name, relative, {"line": node.lineno})
                self.edges.add(RepoEdge(file_id, symbol_id, "defines"))
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                modules = [alias.name.split(".")[0] for alias in node.names] if isinstance(node, ast.Import) else [(node.module or "").split(".")[0]]
                for module in modules:
                    if not module:
                        continue
                    import_id = self._id("module", module)
                    self.nodes.setdefault(import_id, RepoNode(import_id, "module", module, "", {}))
                    self.edges.add(RepoEdge(file_id, import_id, "imports"))

    def _add_markdown(self, file_id: str, relative: str, text: str) -> None:
        for line_number, line in enumerate(text.splitlines(), 1):
            match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
            if not match:
                continue
            label = match.group(2)
            heading_id = self._id("heading", f"{relative}:{label}")
            self.nodes[heading_id] = RepoNode(heading_id, "heading", label, relative, {"level": len(match.group(1)), "line": line_number})
            self.edges.add(RepoEdge(file_id, heading_id, "documents"))

    @staticmethod
    def _id(kind: str, value: str) -> str:
        return f"{kind}:{hashlib.sha256(value.encode()).hexdigest()[:16]}"
