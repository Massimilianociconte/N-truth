"""Final PRD v8 repository-truth refresh after the Task 9 hardening audit."""

from __future__ import annotations

import json
from pathlib import Path

from ntruth.schemas.schema_snapshot import (
    build_kernel_schema_snapshot,
    load_installed_kernel_schema_snapshot,
)

REPOSITORY_ROOT = Path(__file__).parents[2]


REQUIRED_TASK9_PATHS = {
    "core-semantic-kernel": {
        "test_paths": {
            "tests/unit/test_prd_v8_task9_knowledge_provenance_uniqueness.py",
            "tests/unit/test_prd_v8_task9_knowledge_provenance_uniqueness_fix1.py",
            "tests/unit/test_prd_v8_task9_knowledge_provenance_uniqueness_fix2.py",
            "tests/unit/test_prd_v8_task9_knowledge_provenance_uniqueness_fix3.py",
            "tests/unit/test_prd_v8_task9_knowledge_provenance_uniqueness_fix4.py",
            "tests/unit/test_prd_v8_task9_knowledge_provenance_uniqueness_fix5.py",
            "tests/unit/test_prd_v8_task9_knowledge_nested_boundary_fix6.py",
        },
    },
    "rulebook-conformance": {
        "current_paths": {
            "packages/ntruth/derivation_theory/runtime.py",
            "theories/reviewed-evaluator-registry-0.1.0.json",
        },
        "test_paths": {
            "tests/unit/test_prd_v8_task9_evaluator_transitive_digest.py",
            "tests/unit/test_prd_v8_task9_evaluator_transitive_digest_fix1.py",
            "tests/unit/test_prd_v8_task9_evaluator_transitive_digest_fix2.py",
            "tests/unit/test_prd_v8_task9_evaluator_transitive_digest_fix3.py",
        },
    },
    "query-scoped-claims": {
        "current_paths": {
            "packages/ntruth/runtime_tree.py",
            "packages/ntruth/verifier/v8.py",
        },
        "test_paths": {
            "tests/unit/test_prd_v8_task9_scientific_runtime_fix1.py",
            "tests/unit/test_prd_v8_task9_scientific_runtime_fix2.py",
            "tests/unit/test_prd_v8_task9_scientific_runtime_fix3.py",
            "tests/unit/test_prd_v8_task9_scientific_runtime_fix4.py",
        },
    },
    "event-causal-context": {
        "test_paths": {
            "tests/unit/test_prd_v8_task9_scientific_runtime_fix1.py",
        },
    },
    "graph-equality": {
        "test_paths": {
            "tests/unit/test_prd_v8_task9_scientific_runtime_fix1.py",
            "tests/unit/test_prd_v8_task9_scientific_runtime_fix2.py",
            "tests/unit/test_prd_v8_task9_scientific_runtime_fix3.py",
            "tests/unit/test_prd_v8_task9_scientific_runtime_fix4.py",
            "tests/unit/test_prd_v8_task9_scientific_runtime_fix5.py",
        },
    },
    "protected-training-boundary": {
        "current_paths": {
            "packages/ntruth/training/preparation.py",
            "packages/ntruth/training/mlx_dataset.py",
            "packages/ntruth/training/mlx_fd_entrypoint.py",
        },
        "test_paths": {
            "tests/unit/test_prd_v8_task9_jsonl_physical_lines.py",
            "tests/unit/test_prd_v8_task9_jsonl_physical_lines_fix2.py",
            "tests/unit/test_prd_v8_task9_jsonl_physical_lines_fix3.py",
            "tests/unit/test_prd_v8_task9_jsonl_physical_lines_fix4.py",
            "tests/unit/test_prd_v8_task9_validation_eligibility.py",
            "tests/unit/test_prd_v8_task9_validation_eligibility_fix2.py",
            "tests/unit/test_prd_v8_task9_validation_eligibility_fix3.py",
            "tests/unit/test_prd_v8_task9_validation_eligibility_fix4.py",
        },
    },
    "evaluation-residual-cluster": {
        "test_paths": {
            "tests/unit/test_prd_v8_task9_evaluation_copy_boundaries.py",
            "tests/unit/test_prd_v8_task9_evaluation_serialization_boundaries.py",
        },
    },
    "repository-contract-truth": {
        "test_paths": {
            "tests/integration/test_prd_v8_task8_final_refresh.py",
        },
    },
}


def _component_map() -> dict[str, dict[str, object]]:
    payload = json.loads(
        (REPOSITORY_ROOT / "docs/architecture/prd-v8-current-to-target.yaml").read_text(
            encoding="utf-8"
        )
    )
    return {component["component_id"]: component for component in payload["components"]}


def test_final_kernel_snapshot_matches_runtime_contracts() -> None:
    assert load_installed_kernel_schema_snapshot() == build_kernel_schema_snapshot()


def test_architecture_map_names_every_task9_boundary_and_regression() -> None:
    components = _component_map()

    for component_id, fields in REQUIRED_TASK9_PATHS.items():
        component = components[component_id]
        for field_name, required_paths in fields.items():
            assert required_paths.issubset(set(component[field_name])), (
                component_id,
                field_name,
                sorted(required_paths - set(component[field_name])),
            )
