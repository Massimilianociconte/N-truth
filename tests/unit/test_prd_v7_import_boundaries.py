"""Import boundary: graph/rules must not import parser_ai."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "packages" / "ntruth"
FORBIDDEN_IMPORTERS = ("graph", "rules")
FORBIDDEN_TARGET = "parser_ai"


def _imports_parser_ai(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if FORBIDDEN_TARGET in alias.name:
                    hits.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module and FORBIDDEN_TARGET in node.module:
            hits.append(node.module)
    return hits


def test_graph_and_rules_do_not_import_parser_ai() -> None:
    violations: list[str] = []
    for package in FORBIDDEN_IMPORTERS:
        directory = ROOT / package
        for path in directory.rglob("*.py"):
            for hit in _imports_parser_ai(path):
                violations.append(f"{path.relative_to(ROOT)} -> {hit}")
    assert violations == []
