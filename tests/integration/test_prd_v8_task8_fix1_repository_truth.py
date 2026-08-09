"""Task 8 fix-round regressions for fail-closed repository truth."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from ntruth.governance.repository_truth import validate_current_target_map
from ntruth.schemas.kernel import kernel_json_schemas
from ntruth.schemas.schema_snapshot import load_installed_kernel_schema_snapshot

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

EXPECTED_KERNEL_SCHEMA_KEYS = frozenset(
    {
        "application_event",
        "assignment_event",
        "block_boundary_predicate",
        "boundary_change_reference",
        "canonical_count_record",
        "canonical_count_registry",
        "confirmation_event",
        "confirmation_target",
        "conflict_record_v8",
        "count_interval",
        "count_scope",
        "count_scope_identity",
        "derived_claim",
        "derived_claim_set",
        "design_adequacy_evaluation",
        "design_adequacy_finding",
        "evidence_record",
        "executed_design_record",
        "executed_input_ledger",
        "event_registry",
        "experiment_block_boundary_change_ledger",
        "experiment_block_boundary_change_record",
        "experiment_block_boundary_record",
        "exposure_event",
        "handoff_item",
        "inferential_query",
        "kernel_identity",
        "knowledge_value",
        "observation_event",
        "plan_execution_reconciliation",
        "planned_design_record",
        "pool_event",
        "profile_coverage_statement",
        "prospective_artifact",
        "prospective_input_ledger",
        "query_causal_context",
        "query_causal_event_aggregate",
        "query_report_section",
        "relative_timing",
        "report_bundle",
        "report_resolution_outcome",
        "rule_challenge",
        "scenario_coverage",
        "sensitivity_record",
        "source_record",
        "split_event",
        "support_evidence_binding",
        "v8_execution_manifest",
        "v8_experiment_graph",
        "v8_graph_node",
        "v8_graph_relation",
        "verified_pipeline_context",
    }
)

EXPECTED_ADDED_SCHEMA_TITLES = {
    "application_event": "ApplicationEvent",
    "assignment_event": "AssignmentEvent",
    "canonical_count_record": "CanonicalCountRecord",
    "canonical_count_registry": "CanonicalCountRegistry",
    "count_interval": "CountInterval",
    "count_scope": "CountScope",
    "count_scope_identity": "CountScopeIdentity",
    "exposure_event": "ExposureEvent",
    "event_registry": "EventRegistry",
    "inferential_query": "InferentialQuery",
    "observation_event": "ObservationEvent",
    "pool_event": "PoolEvent",
    "query_causal_context": "QueryCausalContext",
    "query_causal_event_aggregate": "QueryCausalEventAggregate",
    "relative_timing": "RelativeTiming",
    "split_event": "SplitEvent",
    "v8_experiment_graph": "V8ExperimentGraph",
    "v8_graph_node": "V8GraphNode",
    "v8_graph_relation": "V8GraphRelation",
}

ROLE_READDRESS_CASES = (
    ("current_paths", "README.md"),
    ("current_paths", "docs/adr/0013-prd-v8-scientific-contract-migration.md"),
    ("adr_paths", "README.md"),
    ("adr_paths", "packages/ntruth/schemas/kernel.py"),
    ("test_paths", "README.md"),
    (
        "test_paths",
        "docs/audits/prd-v8-full-migration/FINAL_IMPLEMENTATION_MATRIX.md",
    ),
    ("evidence_paths", "README.md"),
    ("evidence_paths", "tests/integration/test_prd_v8_task8_repository_truth.py"),
)


def _map_payload() -> dict[str, object]:
    return json.loads(MAP_PATH.read_text(encoding="utf-8"))


def _write_map(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "current-to-target.yaml"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.mark.parametrize("component_id", sorted(EXPECTED_COMPONENT_IDS))
def test_map_rejects_each_missing_canonical_component(
    tmp_path: Path,
    component_id: str,
) -> None:
    payload = _map_payload()
    components = payload["components"]
    assert isinstance(components, list)
    payload["components"] = [
        component for component in components if component["component_id"] != component_id
    ]

    result = validate_current_target_map(_write_map(tmp_path, payload), repository_root=ROOT)

    assert not result.valid
    assert any(
        "missing" in diagnostic and component_id in diagnostic for diagnostic in result.diagnostics
    )


def test_map_rejects_unexpected_component(tmp_path: Path) -> None:
    payload = _map_payload()
    components = payload["components"]
    assert isinstance(components, list)
    unexpected = copy.deepcopy(components[0])
    unexpected["component_id"] = "unexpected-component"
    components.append(unexpected)

    result = validate_current_target_map(_write_map(tmp_path, payload), repository_root=ROOT)

    assert not result.valid
    assert any(
        "unexpected" in diagnostic and "unexpected-component" in diagnostic
        for diagnostic in result.diagnostics
    )


def test_map_rejects_duplicate_canonical_component(tmp_path: Path) -> None:
    payload = _map_payload()
    components = payload["components"]
    assert isinstance(components, list)
    components.append(copy.deepcopy(components[0]))

    result = validate_current_target_map(_write_map(tmp_path, payload), repository_root=ROOT)

    assert not result.valid
    assert any("unique" in diagnostic for diagnostic in result.diagnostics)


@pytest.mark.parametrize(
    ("field", "replacement"),
    ROLE_READDRESS_CASES,
    ids=[f"{field}-{Path(replacement).name}" for field, replacement in ROLE_READDRESS_CASES],
)
def test_map_rejects_every_component_readdressed_to_the_wrong_path_role(
    tmp_path: Path,
    field: str,
    replacement: str,
) -> None:
    accepted_component_ids: list[str] = []
    for component_id in sorted(EXPECTED_COMPONENT_IDS):
        payload = _map_payload()
        components = payload["components"]
        assert isinstance(components, list)
        component = next(item for item in components if item["component_id"] == component_id)
        component[field] = [replacement]
        result = validate_current_target_map(_write_map(tmp_path, payload), repository_root=ROOT)
        if result.valid:
            accepted_component_ids.append(component_id)

    assert not accepted_component_ids, accepted_component_ids


def test_runtime_kernel_schema_registry_matches_the_normative_v8_taxonomy() -> None:
    schemas = kernel_json_schemas()

    assert len(EXPECTED_KERNEL_SCHEMA_KEYS) == 52
    assert set(schemas) == EXPECTED_KERNEL_SCHEMA_KEYS
    assert {
        key: schemas[key]["title"] for key in EXPECTED_ADDED_SCHEMA_TITLES
    } == EXPECTED_ADDED_SCHEMA_TITLES
    graph_node_schema = json.dumps(schemas["v8_graph_node"], sort_keys=True)
    assert {"UnitType", "UnitInstance"} <= {
        value for value in ("UnitType", "UnitInstance") if value in graph_node_schema
    }


def test_packaged_kernel_schema_snapshot_matches_the_exact_v8_taxonomy() -> None:
    snapshot = load_installed_kernel_schema_snapshot()

    assert set(snapshot.schemas) == EXPECTED_KERNEL_SCHEMA_KEYS
    assert snapshot.schemas == kernel_json_schemas()
