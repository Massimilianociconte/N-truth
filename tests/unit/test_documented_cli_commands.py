"""Every `uv run ntruth ...` command shown in user-facing docs must exist.

Audit 2026-09-12 A12: the README quickstart advertised `ntruth reality-gate`,
which exits 2. A quickstart is only useful if it is executable, so the command
paths (not their arguments) are checked against the real Typer application.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ntruth.cli.main import app

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DOCUMENTS = ("README.md", "docs/troubleshooting.md", "docs/status-snapshot.md")
_COMMAND = re.compile(r"^\s*uv run ntruth (?P<args>[^#\\]+)")


def _documented_commands() -> list[tuple[str, tuple[str, ...]]]:
    commands: list[tuple[str, tuple[str, ...]]] = []
    for relative in DOCUMENTS:
        text = (REPOSITORY_ROOT / relative).read_text(encoding="utf-8")
        for line in text.splitlines():
            match = _COMMAND.match(line)
            if match is None:
                continue
            path: list[str] = []
            for token in shlex.split(match.group("args")):
                if token.startswith("-") or "/" in token or "." in token or token.isupper():
                    break
                path.append(token)
            if path:
                commands.append((relative, tuple(path)))
    return commands


DOCUMENTED = _documented_commands()


def test_documented_commands_were_found() -> None:
    assert any(path[:1] == ("quick-design",) for _source, path in DOCUMENTED)


@pytest.mark.parametrize(("source", "path"), DOCUMENTED, ids=lambda value: " ".join(value))
def test_documented_command_path_exists(source: str, path: tuple[str, ...]) -> None:
    result = CliRunner().invoke(app, [*path, "--help"])
    assert result.exit_code == 0, f"{source}: `ntruth {' '.join(path)}` -> {result.output}"
