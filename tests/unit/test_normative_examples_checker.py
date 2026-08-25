"""Tests for the normative example checker (scripts/check_normative_examples.py)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPOSITORY_ROOT / "scripts" / "check_normative_examples.py"

_SPEC = importlib.util.spec_from_file_location("check_normative_examples", SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
checker = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("check_normative_examples", checker)
_SPEC.loader.exec_module(checker)

GOOD_JSON = json.dumps({"factor_role": "ASSIGNED_INTERVENTION", "knowledge_state": "PRESENT"})
BAD_ENUM_JSON = json.dumps({"factor_role": "TELEPORTATION"})
BAD_JSON = '{"factor_role": '


def _write_doc(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _run(root: Path) -> dict[str, object]:
    return checker.run_checks(root)


def test_repository_scan_is_green_with_zero_blocks() -> None:
    summary = _run(REPOSITORY_ROOT)

    assert summary["status"] == "PASS"
    assert summary["errors"] == []
    assert isinstance(summary["files_scanned"], int)
    assert summary["files_scanned"] > 0


def test_zero_normative_blocks_exit_pass_with_note(tmp_path: Path) -> None:
    _write_doc(tmp_path, "docs/plain.md", "# Plain\n\nNo fenced blocks at all.\n")
    summary = _run(tmp_path)

    assert summary["status"] == "PASS"
    assert summary["normative_blocks"] == 0
    assert "no normative examples found" in str(summary["note"])


def test_marker_before_fence_is_normative_and_valid(tmp_path: Path) -> None:
    _write_doc(
        tmp_path,
        "docs/spec.md",
        f"NORMATIVE\n```json\n{GOOD_JSON}\n```\n",
    )
    summary = _run(tmp_path)

    assert summary["status"] == "PASS"
    assert summary["normative_blocks"] == 1
    assert summary["errors"] == []


def test_marker_after_fence_is_normative(tmp_path: Path) -> None:
    _write_doc(
        tmp_path,
        "docs/spec.md",
        f"```json\n{GOOD_JSON}\n```\nNORMATIVE\n",
    )
    summary = _run(tmp_path)

    assert summary["status"] == "PASS"
    assert summary["normative_blocks"] == 1


def test_normative_heading_captures_yaml_block(tmp_path: Path) -> None:
    _write_doc(
        tmp_path,
        "docs/appendix.md",
        "## Normative registry record\n\n```yaml\n" + GOOD_JSON + "\n```\n",
    )
    summary = _run(tmp_path)

    assert summary["status"] == "PASS"
    assert summary["normative_blocks"] == 1


def test_unmarked_block_is_ignored(tmp_path: Path) -> None:
    _write_doc(tmp_path, "docs/spec.md", f"```json\n{BAD_ENUM_JSON}\n```\n")
    summary = _run(tmp_path)

    assert summary["status"] == "PASS"
    assert summary["normative_blocks"] == 0


def test_historical_marker_excludes_block(tmp_path: Path) -> None:
    _write_doc(
        tmp_path,
        "docs/history.md",
        f"HISTORICAL appendix\n```json\n{BAD_ENUM_JSON}\n```\n",
    )
    summary = _run(tmp_path)

    assert summary["status"] == "PASS"
    assert summary["normative_blocks"] == 0


def test_unknown_enum_token_fails(tmp_path: Path) -> None:
    _write_doc(
        tmp_path,
        "docs/spec.md",
        f"NORMATIVE\n```json\n{BAD_ENUM_JSON}\n```\n",
    )
    summary = _run(tmp_path)

    assert summary["status"] == "FAIL"
    assert any("unknown factor_role token" in error for error in summary["errors"])  # type: ignore[operator]


def test_malformed_json_fails(tmp_path: Path) -> None:
    _write_doc(tmp_path, "docs/spec.md", f"NORMATIVE\n```json\n{BAD_JSON}\n```\n")
    summary = _run(tmp_path)

    assert summary["status"] == "FAIL"
    assert any("invalid JSON" in error for error in summary["errors"])  # type: ignore[operator]


def test_normative_block_with_prose_language_fails(tmp_path: Path) -> None:
    _write_doc(
        tmp_path,
        "docs/spec.md",
        "NORMATIVE\n```text\nfactor_role: ASSIGNED_INTERVENTION\n```\n",
    )
    summary = _run(tmp_path)

    assert summary["status"] == "FAIL"
    assert any("must be yaml or json" in error for error in summary["errors"])  # type: ignore[operator]


def test_yaml_without_parser_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _no_yaml(text: str) -> object:
        return checker._YAML_NOT_AVAILABLE

    monkeypatch.setattr(checker, "_yaml_safe_load", _no_yaml)
    _write_doc(
        tmp_path,
        "docs/spec.md",
        "## Normative example\n\n```yaml\nkey:\n  - unparseable_as_json: [\n```\n",
    )
    summary = _run(tmp_path)

    assert summary["status"] == "FAIL"
    assert any("without PyYAML" in error for error in summary["errors"])  # type: ignore[operator]


def test_yaml_payload_enum_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(checker, "_yaml_safe_load", lambda text: json.loads(text))
    payload = json.dumps({"contrast_type": "OBSERVATIONAL_ASSOCIATION"})
    _write_doc(
        tmp_path,
        "docs/spec.md",
        f"NORMATIVE\n```yaml\n{payload}\n```\n",
    )

    good = _run(tmp_path)
    assert good["status"] == "PASS"

    bad_payload = json.dumps({"contrast_type": "NOT_A_CONTRAST"})
    _write_doc(
        tmp_path,
        "docs/spec-bad.md",
        f"NORMATIVE\n```yaml\n{bad_payload}\n```\n",
    )
    bad = _run(tmp_path)
    assert bad["status"] == "FAIL"


def test_nested_canonical_fields_are_validated(tmp_path: Path) -> None:
    payload = json.dumps({"record": {"material_lineage_event_kind": "SUBSAMPLE", "nested": []}})
    _write_doc(tmp_path, "docs/spec.md", f"NORMATIVE\n```json\n{payload}\n```\n")

    good = _run(tmp_path)
    assert good["status"] == "PASS"

    bad = json.dumps({"record": {"event_kind": "VANISH"}})
    _write_doc(tmp_path, "docs/spec-bad.md", f"NORMATIVE\n```json\n{bad}\n```\n")
    summary = _run(tmp_path)
    assert summary["status"] == "FAIL"
