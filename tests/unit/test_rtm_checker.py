"""Tests for the Requirements Traceability Matrix checker (scripts/check_rtm.py)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPOSITORY_ROOT / "scripts" / "check_rtm.py"

_SPEC = importlib.util.spec_from_file_location("check_rtm", SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
checker = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("check_rtm", checker)
_SPEC.loader.exec_module(checker)

HEADER = (
    "requirement_id,source_prd_section,schema_or_api,component,test,"
    "metric_gate,owner_role,status,evidence_note\n"
)


def _row(
    requirement_id: str = "FR-001",
    section: str = "21.1",
    schema: str = "src/schema.py",
    component: str = "semantic-kernel",
    test: str = "tests/test_it.py",
    metric_gate: str = "some gate holds",
    owner_role: str = "semantic-lead",
    status: str = "IMPLEMENTED",
    note: str = '"a note, possibly with commas"',
) -> str:
    return f"{requirement_id},{section},{schema},{component},{test},{metric_gate},{owner_role},{status},{note}\n"


def _write_rtm(root: Path, *rows: str) -> Path:
    (root / "data").mkdir(parents=True, exist_ok=True)
    csv_path = root / "data" / "rtm-v0.1.csv"
    csv_path.write_text(HEADER + "".join(rows), encoding="utf-8")
    return csv_path


def _make_repo(tmp_path: Path) -> None:
    if not (tmp_path / "src").exists():
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "schema.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_it.py").write_text(
            "def test_x():\n    pass\n", encoding="utf-8"
        )


def _run(root: Path) -> tuple[dict[str, Any], int]:
    checks, diagnostics = checker.check_rtm(root)
    payload = {"checks": checks, "diagnostics": list(diagnostics)}
    return payload, 1 if diagnostics else 0


def test_repository_rtm_passes() -> None:
    checks, diagnostics = checker.check_rtm(REPOSITORY_ROOT)

    assert diagnostics == ()
    assert checks["columns_exact"] == "PASS"
    assert checks["rows_valid"] == "PASS"
    assert checks["paths_resolve"] == "PASS"
    assert checks["statuses_coherent"] == "PASS"
    summary = json.loads(checks["summary"])
    assert summary["requirement_count"] >= 25
    assert set(summary["status_counts"]) == {"IMPLEMENTED", "PARTIAL", "PLANNED"}
    assert summary["status_counts"]["PLANNED"] >= 1


def test_missing_csv_fails_closed(tmp_path: Path) -> None:
    payload, code = _run(tmp_path)

    assert code == 1
    assert payload["checks"] == {"rtm_present": "FAIL"}
    assert len(payload["diagnostics"]) == 1


def test_valid_fixture_passes(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    _write_rtm(tmp_path, _row())
    payload, code = _run(tmp_path)

    assert code == 0
    assert payload["diagnostics"] == []


def test_markers_allow_planned_rows_without_paths(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    _write_rtm(
        tmp_path,
        _row(
            requirement_id="NFR-08",
            section="22",
            schema="MISSING_EXPLICIT",
            test="NONE_WITH_RATIONALE",
            status="PLANNED",
        ),
    )
    payload, code = _run(tmp_path)

    assert code == 0
    assert payload["diagnostics"] == []


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("schema", "src/does_not_exist.py"),
        ("test", "tests/does_not_exist.py"),
    ],
)
def test_nonexistent_paths_are_rejected(tmp_path: Path, column: str, value: str) -> None:
    _make_repo(tmp_path)
    row = _row(**{column: value})
    _write_rtm(tmp_path, row)
    payload, code = _run(tmp_path)

    assert code == 1
    assert any("does not exist" in diagnostic for diagnostic in payload["diagnostics"])


def test_implemented_requires_a_real_test(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    _write_rtm(tmp_path, _row(test="NONE_WITH_RATIONALE"))
    payload, code = _run(tmp_path)

    assert code == 1
    assert any("IMPLEMENTED requires" in diagnostic for diagnostic in payload["diagnostics"])


def test_duplicate_and_malformed_requirements_are_rejected(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    _write_rtm(tmp_path, _row(), _row())
    payload, code = _run(tmp_path)

    assert code == 1
    assert any("duplicate" in diagnostic for diagnostic in payload["diagnostics"])

    bad_id = _row(requirement_id="FR-1")
    _write_rtm(tmp_path, bad_id)
    payload, code = _run(tmp_path)
    assert code == 1
    assert any("invalid requirement id" in diagnostic for diagnostic in payload["diagnostics"])


def test_invalid_status_and_owner_role_are_rejected(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    _write_rtm(tmp_path, _row(status="DONE"))
    payload, code = _run(tmp_path)

    assert code == 1
    assert any("status must be one of" in diagnostic for diagnostic in payload["diagnostics"])

    _write_rtm(tmp_path, _row(owner_role="Alice Smith"))
    payload, code = _run(tmp_path)
    assert code == 1
    assert any(
        "owner_role must be a role id" in diagnostic for diagnostic in payload["diagnostics"]
    )


def test_wrong_header_is_rejected(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    csv_path = _write_rtm(tmp_path, _row())
    csv_path.write_text(HEADER.replace("metric_gate,", "metric,") + _row(), encoding="utf-8")
    payload, code = _run(tmp_path)

    assert code == 1
    assert any("header must be exactly" in diagnostic for diagnostic in payload["diagnostics"])


def test_empty_field_is_rejected(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    _write_rtm(tmp_path, _row(note='""'))
    payload, code = _run(tmp_path)

    assert code == 1
    assert any("empty field evidence_note" in diagnostic for diagnostic in payload["diagnostics"])
