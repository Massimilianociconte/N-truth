"""Public CLI rules list uses Unicode em dash (packaged smoke contract)."""

from __future__ import annotations

import re

from typer.testing import CliRunner

from ntruth.cli.main import app

RULESET_PATTERN = re.compile(r"^ntruth-core@\S+ — (\d+) regole \(checksum [0-9a-f]+\)$")


def test_rules_list_emdash_contract() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["rules", "list"])
    assert result.exit_code == 0, result.output
    lines = [line.strip() for line in result.output.splitlines() if line.strip()]
    assert lines, result.output
    assert RULESET_PATTERN.match(lines[0]), lines[0]
