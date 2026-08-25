"""Task 8 fix-round-2 regressions for component descriptor anchoring."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from ntruth.governance.repository_truth import (
    CurrentTargetMapValidation,
    validate_current_target_map,
)

ROOT = Path(__file__).resolve().parents[2]
MAP_PATH = ROOT / "docs" / "architecture" / "prd-v8-current-to-target.yaml"

EXPECTED_COMPONENT_IDS = frozenset(
    {
        "canonical-count-registry",
        "core-semantic-kernel",
        "corrections-rederivation",
        "coverage-contracts",
        "derivation-theory",
        "desktop-v8",
        "evaluation-residual-cluster",
        "event-causal-context",
        "experiment-block-boundary",
        "external-challenge-custody",
        "graph-equality",
        "guided-quick-design-v8",
        "ingest-safety",
        "orthogonal-evidence-support",
        "parser-candidate-boundary",
        "planned-executed-reporting",
        "prd-examples-and-schema",
        "protected-training-boundary",
        "query-scoped-claims",
        "reality-gate-v8",
        "repository-contract-truth",
        "rulebook-conformance",
        "statistical-handoff",
        "v7-compatibility",
        "v7-to-v8-migrations",
    }
)

LOAD_BEARING_DESCRIPTOR_FIELDS = (
    "current_paths",
    "public_api",
    "adr_paths",
    "test_paths",
    "evidence_paths",
    "target",
    "status",
    "owner",
    "blocker_ids",
)

EXPECTED_ROOT_FIELDS = frozenset(
    {
        "base_sha",
        "components",
        "map_id",
        "schema_version",
        "status_semantics",
        "target_contract",
    }
)

ROOT_LITERAL_MUTATIONS = (
    ("schema_version", "8.0.1"),
    ("map_id", "NTRUTH-PRD-V8-CURRENT-TARGET-FORGED"),
    ("base_sha", "0" * 40),
    ("target_contract", "N-Truth PRD v8.1"),
    ("status_semantics", "Engineering implementation status; HOLD."),
)


def _map_payload() -> dict[str, Any]:
    return json.loads(MAP_PATH.read_text(encoding="utf-8"))


def _descriptor_swap_cases() -> tuple[tuple[str, str, str], ...]:
    components = _map_payload()["components"]
    by_id = {component["component_id"]: component for component in components}
    cases: list[tuple[str, str, str]] = []
    for component_id in sorted(EXPECTED_COMPONENT_IDS):
        component = by_id[component_id]
        for field in LOAD_BEARING_DESCRIPTOR_FIELDS:
            donor = next(
                (
                    candidate
                    for candidate in components
                    if candidate["component_id"] != component_id
                    and candidate[field] != component[field]
                ),
                None,
            )
            if donor is not None:
                cases.append((component_id, field, donor["component_id"]))
    return tuple(cases)


DESCRIPTOR_SWAP_CASES = _descriptor_swap_cases()
assert len(EXPECTED_COMPONENT_IDS) == 25
assert len(DESCRIPTOR_SWAP_CASES) == 200


def _compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _write_raw_map(tmp_path: Path, raw: str) -> Path:
    forged_map = tmp_path / "current-to-target.yaml"
    forged_map.write_text(raw, encoding="utf-8")
    return forged_map


def _assert_duplicate_key_failure(
    result: CurrentTargetMapValidation,
    *,
    key: str,
) -> None:
    assert isinstance(result, CurrentTargetMapValidation)
    assert result.valid is False
    assert result.component_ids == ()
    assert result.diagnostics == (f"architecture map contains duplicate object key: {key}",)


@pytest.mark.parametrize("field", sorted(EXPECTED_ROOT_FIELDS))
def test_root_contract_rejects_each_missing_top_level_field(
    tmp_path: Path,
    field: str,
) -> None:
    payload = _map_payload()
    payload.pop(field)

    result = validate_current_target_map(
        _write_raw_map(tmp_path, _compact_json(payload)), repository_root=ROOT
    )

    assert not result.valid
    assert any(field in diagnostic for diagnostic in result.diagnostics)


def test_root_contract_rejects_unexpected_top_level_field(tmp_path: Path) -> None:
    payload = _map_payload()
    payload["descriptor_checksum"] = "self-readdressable"

    result = validate_current_target_map(
        _write_raw_map(tmp_path, _compact_json(payload)), repository_root=ROOT
    )

    assert not result.valid
    assert any("descriptor_checksum" in diagnostic for diagnostic in result.diagnostics)


@pytest.mark.parametrize(("field", "forged_value"), ROOT_LITERAL_MUTATIONS)
def test_root_contract_rejects_each_forged_literal(
    tmp_path: Path,
    field: str,
    forged_value: str,
) -> None:
    payload = _map_payload()
    payload[field] = forged_value

    result = validate_current_target_map(
        _write_raw_map(tmp_path, _compact_json(payload)), repository_root=ROOT
    )

    assert not result.valid
    assert any(field in diagnostic for diagnostic in result.diagnostics)


def test_anchor_rejects_pairwise_component_id_exchange(tmp_path: Path) -> None:
    payload = _map_payload()
    by_id = {component["component_id"]: component for component in payload["components"]}
    first = by_id["canonical-count-registry"]
    second = by_id["core-semantic-kernel"]
    first["component_id"], second["component_id"] = (
        second["component_id"],
        first["component_id"],
    )

    result = validate_current_target_map(
        _write_raw_map(tmp_path, _compact_json(payload)), repository_root=ROOT
    )

    assert not result.valid
    assert sum("reviewed content anchor" in item for item in result.diagnostics) == 2


def test_anchor_rejects_existing_same_role_adr_readdress(tmp_path: Path) -> None:
    alternate_adr = "docs/adr/0001-inference-target-compiler-first.md"
    assert (ROOT / alternate_adr).is_file()
    payload = _map_payload()
    component = next(
        item for item in payload["components"] if item["component_id"] == "canonical-count-registry"
    )
    component["adr_paths"] = [alternate_adr]

    result = validate_current_target_map(
        _write_raw_map(tmp_path, _compact_json(payload)), repository_root=ROOT
    )

    assert not result.valid
    assert (
        "canonical-count-registry descriptor does not match its reviewed content anchor"
        in result.diagnostics
    )


def test_anchor_rejects_required_list_reordering(tmp_path: Path) -> None:
    payload = _map_payload()
    component = next(
        item for item in payload["components"] if item["component_id"] == "canonical-count-registry"
    )
    component["current_paths"] = list(reversed(component["current_paths"]))

    result = validate_current_target_map(
        _write_raw_map(tmp_path, _compact_json(payload)), repository_root=ROOT
    )

    assert not result.valid
    assert any("reviewed content anchor" in item for item in result.diagnostics)


def test_anchor_rejects_required_field_type_substitution(tmp_path: Path) -> None:
    payload = _map_payload()
    component = next(
        item for item in payload["components"] if item["component_id"] == "canonical-count-registry"
    )
    component["owner"] = 7

    result = validate_current_target_map(
        _write_raw_map(tmp_path, _compact_json(payload)), repository_root=ROOT
    )

    assert not result.valid
    assert any("reviewed content anchor" in item for item in result.diagnostics)


def test_map_rejects_duplicate_top_level_object_key_before_anchor(tmp_path: Path) -> None:
    canonical = _compact_json(_map_payload())
    raw = '{"schema_version":"FORGED",' + canonical.removeprefix("{")

    result = validate_current_target_map(_write_raw_map(tmp_path, raw), repository_root=ROOT)

    _assert_duplicate_key_failure(result, key="schema_version")


@pytest.mark.parametrize("field", ("target", "current_paths", "public_api"))
def test_map_rejects_duplicate_component_row_key_before_anchor(
    tmp_path: Path,
    field: str,
) -> None:
    payload = _map_payload()
    by_id = {component["component_id"]: component for component in payload["components"]}
    component = by_id["canonical-count-registry"]
    donor = by_id["core-semantic-kernel"]
    component_blob = _compact_json(component)
    canonical_member = f"{json.dumps(field)}:{_compact_json(component[field])}"
    duplicate_member = f"{json.dumps(field)}:{_compact_json(donor[field])}"
    forged_component_blob = component_blob.replace(
        canonical_member,
        f"{duplicate_member},{canonical_member}",
        1,
    )
    raw = _compact_json(payload).replace(component_blob, forged_component_blob, 1)

    result = validate_current_target_map(_write_raw_map(tmp_path, raw), repository_root=ROOT)

    _assert_duplicate_key_failure(result, key=field)


def test_map_rejects_escaped_duplicate_component_row_key_before_anchor(
    tmp_path: Path,
) -> None:
    payload = _map_payload()
    component = next(
        item for item in payload["components"] if item["component_id"] == "canonical-count-registry"
    )
    component_blob = _compact_json(component)
    canonical_member = f'"target":{_compact_json(component["target"])}'
    escaped_duplicate_member = '"\\u0074arget":"FORGED"'
    forged_component_blob = component_blob.replace(
        canonical_member,
        f"{escaped_duplicate_member},{canonical_member}",
        1,
    )
    raw = _compact_json(payload).replace(component_blob, forged_component_blob, 1)

    result = validate_current_target_map(_write_raw_map(tmp_path, raw), repository_root=ROOT)

    _assert_duplicate_key_failure(result, key="target")


@pytest.mark.parametrize(
    ("component_id", "field", "donor_id"),
    DESCRIPTOR_SWAP_CASES,
    ids=[
        f"{component_id}-{field}-from-{donor_id}"
        for component_id, field, donor_id in DESCRIPTOR_SWAP_CASES
    ],
)
def test_map_rejects_same_role_descriptor_readdress_for_every_component(
    tmp_path: Path,
    component_id: str,
    field: str,
    donor_id: str,
) -> None:
    payload = _map_payload()
    components = payload["components"]
    by_id = {component["component_id"]: component for component in components}
    by_id[component_id][field] = copy.deepcopy(by_id[donor_id][field])
    forged_map = tmp_path / "current-to-target.yaml"
    forged_map.write_text(json.dumps(payload), encoding="utf-8")

    result = validate_current_target_map(forged_map, repository_root=ROOT)

    assert not result.valid
    assert (
        f"{component_id} descriptor does not match its reviewed content anchor"
        in result.diagnostics
    )
