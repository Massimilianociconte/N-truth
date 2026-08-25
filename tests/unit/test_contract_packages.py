"""Tests for the PRD v9 Contract Package checker (scripts/check_contract_packages.py)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPOSITORY_ROOT / "scripts" / "check_contract_packages.py"

_SPEC = importlib.util.spec_from_file_location("check_contract_packages", SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
checker = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("check_contract_packages", checker)
_SPEC.loader.exec_module(checker)

VALID_MANIFEST = """\
id: CP-SCI
title: Test Package
version: 0.1.0-alpha
status: DRAFT
owner: product-owner
gate: prima di derivare claim
reviewers_minimi:
  - wet-lab-reviewer
modules:
  - core_kernel
dependencies: []
current_evidence:
  core_kernel:
    - evidence/kernel.py
known_gaps:
  - "nessuno"
"""


def _write_fixture(tmp_path: Path, text: str) -> None:
    (tmp_path / "contracts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)
    (tmp_path / "evidence" / "kernel.py").write_text("# evidence\n", encoding="utf-8")


def _write(tmp_path: Path, name: str, text: str) -> None:
    _write_fixture(tmp_path, VALID_MANIFEST)
    (tmp_path / "contracts" / name).write_text(text, encoding="utf-8")


def _run(root: Path, *, require_canonical_set: bool = False) -> tuple[dict[str, Any], int]:
    checks, diagnostics = checker.check_contract_packages(
        root, require_canonical_set=require_canonical_set
    )
    return {"checks": checks, "diagnostics": list(diagnostics)}, 1 if diagnostics else 0


def test_repository_contracts_pass() -> None:
    checks, diagnostics = checker.check_contract_packages(REPOSITORY_ROOT)

    assert diagnostics == ()
    assert checks["canonical_set"] == "PASS"
    assert checks["fields_and_evidence"] == "PASS"
    assert checks["dependencies_acyclic"] == "PASS"
    summary = json.loads(checks["summary"])
    assert set(summary) == {"missing_explicit_count"}
    assert summary["missing_explicit_count"] >= 1


def test_valid_fixture_passes(tmp_path: Path) -> None:
    _write_fixture(tmp_path, VALID_MANIFEST)
    (tmp_path / "contracts" / "cp-sci.yaml").write_text(VALID_MANIFEST, encoding="utf-8")
    payload, code = _run(tmp_path)

    assert code == 0
    assert payload["diagnostics"] == []


def test_missing_required_field_fails(tmp_path: Path) -> None:
    broken = "\n".join(
        line for line in VALID_MANIFEST.splitlines() if not line.startswith("status:")
    )
    _write(tmp_path, "cp-tst.yaml", broken + "\n")
    payload, code = _run(tmp_path)

    assert code == 1
    assert any("missing required field status" in item for item in payload["diagnostics"])


def test_unparseable_yaml_fails_closed(tmp_path: Path) -> None:
    _write(tmp_path, "cp-tst.yaml", "id: CP-SCI\n  bad_indent: [unclosed\n")
    payload, code = _run(tmp_path)

    assert code == 1
    assert any("unparseable" in item for item in payload["diagnostics"])


def test_nonexistent_evidence_path_fails(tmp_path: Path) -> None:
    broken = VALID_MANIFEST.replace("- evidence/kernel.py", "- docs/does-not-exist.md")
    _write(tmp_path, "cp-tst.yaml", broken)
    payload, code = _run(tmp_path)

    assert code == 1
    assert any("path does not exist" in item for item in payload["diagnostics"])


def test_missing_explicit_without_known_gaps_fails(tmp_path: Path) -> None:
    broken = VALID_MANIFEST.replace(
        "current_evidence:\n  core_kernel:\n    - evidence/kernel.py\n",
        "current_evidence:\n  core_kernel:\n    - MISSING_EXPLICIT\n",
    ).replace('known_gaps:\n  - "nessuno"\n', "")
    _write(tmp_path, "cp-tst.yaml", broken)
    payload, code = _run(tmp_path)

    assert code == 1
    assert any(
        "MISSING_EXPLICIT evidence without known_gaps" in item for item in payload["diagnostics"]
    )


def test_dependency_cycle_is_detected(tmp_path: Path) -> None:
    first = VALID_MANIFEST.replace("id: CP-SCI", "id: CP-AAA").replace(
        "dependencies: []", "dependencies:\n  - CP-BBB"
    )
    second = VALID_MANIFEST.replace("id: CP-SCI", "id: CP-BBB").replace(
        "dependencies: []", "dependencies:\n  - CP-AAA"
    )
    _write(tmp_path, "cp-aaa.yaml", first)
    _write(tmp_path, "cp-bbb.yaml", second)
    payload, code = _run(tmp_path)

    assert code == 1
    assert any("dependency cycle" in item for item in payload["diagnostics"])


def test_unknown_dependency_is_reported(tmp_path: Path) -> None:
    broken = VALID_MANIFEST.replace("dependencies: []", "dependencies:\n  - CP-ZZZ")
    _write(tmp_path, "cp-tst.yaml", broken)
    payload, code = _run(tmp_path)

    assert code == 1
    assert any("unknown contract packages" in item for item in payload["diagnostics"])


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "BROKEN"),
        ("version", "0.1"),
        ("owner", ""),
        ("modules", []),
    ],
)
def test_invalid_field_values_fail(field: str, value: str, tmp_path: Path) -> None:
    lines = []
    for line in VALID_MANIFEST.splitlines():
        if line.startswith(f"{field}:"):
            if field == "modules":
                continue
            lines.append(f"{field}: {value}")
        else:
            lines.append(line)
    if field == "modules":
        lines.append(f"{field}:[]")
    _write(tmp_path, "cp-tst.yaml", "\n".join(lines) + "\n")
    payload, code = _run(tmp_path)

    assert code == 1
    assert any(field in item for item in payload["diagnostics"])


def test_module_without_evidence_entry_fails(tmp_path: Path) -> None:
    broken = VALID_MANIFEST.replace(
        "modules:\n  - core_kernel\n",
        "modules:\n  - core_kernel\n  - extra_module\n",
    )
    _write(tmp_path, "cp-tst.yaml", broken)
    payload, code = _run(tmp_path)

    assert code == 1
    assert any("without current_evidence entries" in item for item in payload["diagnostics"])
