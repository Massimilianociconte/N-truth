"""Tests for the current-to-target map checker (scripts/check_current_target_map.py)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPOSITORY_ROOT / "scripts" / "check_current_target_map.py"

_SPEC = importlib.util.spec_from_file_location("check_current_target_map", SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
checker = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("check_current_target_map", checker)
_SPEC.loader.exec_module(checker)

VALID_MAP = """\
schema_version: 9.0.0
map_id: TEST-MAP
map_version: 0.2.0
target_contract: N-Truth PRD v9.0 unified tree
status_semantics: Engineering implementation status only.
historical_predecessor: docs/architecture/prd-v8-current-to-target.yaml
historical_note_file: docs/architecture/prd-v8-current-to-target.HISTORICAL.md
components:
  kernel:
    current_paths:
      - packages/ntruth/schemas/kernel.py
    state: IMPLEMENTED
    owner_role: semantic-lead
    adr_paths:
      - docs/adr/0013-prd-v8-scientific-contract-migration.md
    migration_issue: none open
    clean_checkout_evidence: uv run pytest tests/unit -q -p no:cacheprovider
"""


def _make_repo(tmp_path: Path) -> None:
    docs = tmp_path / "docs" / "architecture"
    docs.mkdir(parents=True)
    (tmp_path / "packages" / "ntruth" / "schemas").mkdir(parents=True)
    (tmp_path / "packages" / "ntruth" / "schemas" / "kernel.py").write_text(
        "x = 1\n", encoding="utf-8"
    )
    adr = tmp_path / "docs" / "adr"
    adr.mkdir()
    (adr / "0013-prd-v8-scientific-contract-migration.md").write_text("# ADR\n", encoding="utf-8")
    (docs / "prd-v8-current-to-target.yaml").write_text("{}", encoding="utf-8")
    (docs / "prd-v8-current-to-target.HISTORICAL.md").write_text("# HISTORICAL\n", encoding="utf-8")


def _write_map(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "docs" / "architecture" / "prd-current-to-target.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def _run(root: Path) -> tuple[dict[str, Any], int]:
    checks, diagnostics = checker.check_current_target_map(root)
    return {"checks": checks, "diagnostics": list(diagnostics)}, 1 if diagnostics else 0


def test_repository_map_passes() -> None:
    checks, diagnostics = checker.check_current_target_map(REPOSITORY_ROOT)

    assert diagnostics == ()
    assert checks["map_parseable"] == "PASS"
    assert checks["root_fields"] == "PASS"
    assert checks["component_fields"] == "PASS"
    assert checks["states_valid"] == "PASS"
    assert checks["paths_resolve"] == "PASS"
    summary = json.loads(checks["summary"])
    assert summary["component_count"] >= 15
    assert set(summary["state_counts"]) == {"IMPLEMENTED", "PARTIAL", "MISSING"}
    assert summary["state_counts"]["IMPLEMENTED"] >= 5


def test_valid_fixture_passes(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    _write_map(tmp_path, VALID_MAP)
    payload, code = _run(tmp_path)

    assert code == 0
    assert payload["diagnostics"] == []


def test_unparseable_map_fails_closed(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    _write_map(tmp_path, "components:\n  - broken: [unbalanced\n")
    payload, code = _run(tmp_path)

    assert code == 1
    assert payload["checks"]["map_parseable"] == "FAIL"


def test_nonexistent_path_with_implemented_state_is_rejected(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    _write_map(
        tmp_path,
        VALID_MAP.replace(
            "- packages/ntruth/schemas/kernel.py",
            "- packages/ntruth/schemas/does_not_exist.py",
        ),
    )
    payload, code = _run(tmp_path)

    assert code == 1
    assert any("does not exist" in diagnostic for diagnostic in payload["diagnostics"])


def test_missing_state_requires_only_placeholder(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    missing_component = """\
  scope-claims:
    current_paths:
      - MISSING_EXPLICIT
    state: MISSING
    owner_role: semantic-lead
    adr_paths: []
    migration_issue: ObservedEvidenceScope and TargetPopulationClaim absent
    clean_checkout_evidence: no command available yet
"""
    _write_map(tmp_path, VALID_MAP + missing_component)
    payload, code = _run(tmp_path)

    assert code == 0
    assert payload["diagnostics"] == []

    bad_missing = missing_component.replace("- MISSING_EXPLICIT", "- packages/nowhere/x.py")
    _write_map(tmp_path, VALID_MAP + bad_missing)
    payload, code = _run(tmp_path)
    assert code == 1


def test_invalid_state_owner_and_fields_are_rejected(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    _write_map(tmp_path, VALID_MAP.replace("state: IMPLEMENTED", "state: DONE"))
    payload, code = _run(tmp_path)

    assert code == 1
    assert any("invalid state" in diagnostic for diagnostic in payload["diagnostics"])

    _write_map(tmp_path, VALID_MAP.replace("owner_role: semantic-lead", "owner_role: Alice"))
    payload, code = _run(tmp_path)
    assert code == 1
    assert any(
        "owner_role must be a role id" in diagnostic for diagnostic in payload["diagnostics"]
    )

    stripped = "\n".join(
        line for line in VALID_MAP.splitlines() if not line.startswith("    migration_issue")
    )
    _write_map(tmp_path, stripped + "\n")
    payload, code = _run(tmp_path)
    assert code == 1
    assert any("missing required field migration_issue" in d for d in payload["diagnostics"])


def test_nonexistent_adr_or_predecessor_paths_are_rejected(tmp_path: Path) -> None:
    _make_repo(tmp_path)
    _write_map(
        tmp_path,
        VALID_MAP.replace(
            "- docs/adr/0013-prd-v8-scientific-contract-migration.md",
            "- docs/adr/9999-missing.md",
        ),
    )
    payload, code = _run(tmp_path)

    assert code == 1
    assert any("ADR path does not exist" in diagnostic for diagnostic in payload["diagnostics"])

    _write_map(
        tmp_path,
        VALID_MAP.replace(
            "historical_predecessor: docs/architecture/prd-v8-current-to-target.yaml",
            "historical_predecessor: docs/architecture/nope.yaml",
        ),
    )
    payload, code = _run(tmp_path)
    assert code == 1
    assert any(
        "historical_predecessor does not exist" in diagnostic
        for diagnostic in payload["diagnostics"]
    )
