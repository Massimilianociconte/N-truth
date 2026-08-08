from __future__ import annotations

import importlib
from decimal import Decimal

import pytest
from pydantic import ValidationError

import ntruth.evaluation_v8 as evaluation
from ntruth.schemas.claims import DeterminabilityState
from ntruth.schemas.core import content_checksum
from ntruth.schemas.knowledge import KnowledgeState

base = importlib.import_module("test_prd_v8_task7_evaluation")
fix1 = importlib.import_module("test_prd_v8_task7_evaluation_fix1")
fix2 = importlib.import_module("test_prd_v8_task7_evaluation_fix2")


def _readdress_manifest(payload: dict) -> dict:
    checksum = content_checksum(
        {
            key: value
            for key, value in payload.items()
            if key not in {"manifest_id", "content_checksum"}
        }
    )
    payload["content_checksum"] = checksum
    payload["manifest_id"] = f"CLUSTER-OBSERVATIONS-{checksum[:20]}"
    return payload


def test_forged_question_without_reviewed_usefulness_is_not_actionable() -> None:
    claim = base._claim(
        "C-UNRESOLVED",
        state=DeterminabilityState.INSUFFICIENT_INFORMATION,
        value="unknown",
    )
    observed = base._snapshot(claims=(claim,))

    result = evaluation.evaluate_end_to_end(observed, fix1._reference_value(observed))

    query = (result.query_results.value or ())[0]
    assert (
        query.abstention_dispositions[evaluation.AbstentionDisposition.ACTIONABLE_ABSTENTION] == 0
    )
    assert (
        query.abstention_dispositions[evaluation.AbstentionDisposition.UNRESOLVED_RISK_DETECTED]
        == 1
    )
    assert result.question_usefulness.knowledge_state is KnowledgeState.UNKNOWN
    assert "SRR-V8-EVAL-PROCESS-METRICS" in {item.issue_id for item in result.blockers}


def test_false_certainty_categories_emit_their_typed_residual_dimensions() -> None:
    categories = tuple(evaluation.FalseCertaintyCategory)
    observed = base._snapshot(
        claims=(
            base._claim(
                "C-FALSE-CERTAINTY",
                state=DeterminabilityState.DETERMINATE,
                value="unsupported",
            ),
        )
    )
    reference = base._snapshot(
        claims=(
            base._claim(
                "C-FALSE-CERTAINTY",
                state=DeterminabilityState.INSUFFICIENT_INFORMATION,
                value="unresolved",
                false_certainty=categories,
            ),
        )
    )

    result = evaluation.evaluate_end_to_end(observed, fix1._reference_value(reference))

    by_category = {
        residual.false_certainty_category.value: residual.dimension
        for residual in result.residuals.value or ()
        if residual.false_certainty_category.knowledge_state is KnowledgeState.PRESENT
    }
    assert by_category == {
        evaluation.FalseCertaintyCategory.EU_OR_COUNT_ERROR: (
            evaluation.ResidualDimension.COUNT_CORRECTNESS
        ),
        evaluation.FalseCertaintyCategory.DECISIVE_PRECONDITION_UNSUPPORTED: (
            evaluation.ResidualDimension.SUPPORT_CORRECTNESS
        ),
        evaluation.FalseCertaintyCategory.MATERIAL_SCENARIO_OMITTED: (
            evaluation.ResidualDimension.SCENARIO_COVERAGE
        ),
        evaluation.FalseCertaintyCategory.HIDDEN_CONFLICT: (
            evaluation.ResidualDimension.SUPPORT_CORRECTNESS
        ),
        evaluation.FalseCertaintyCategory.PROFILE_COVERAGE_UNDECLARED: (
            evaluation.ResidualDimension.PROFILE_COVERAGE
        ),
        evaluation.FalseCertaintyCategory.INFERENCE_OR_ESTIMAND_SCOPE_OVERREACH: (
            evaluation.ResidualDimension.CLAIM_SEMANTICS
        ),
        evaluation.FalseCertaintyCategory.ADEQUACY_UNSUPPORTED_POSITIVE: (
            evaluation.ResidualDimension.ADEQUACY_AXIS
        ),
    }


def test_readdressed_manifest_rejects_semantic_duplicate_with_evidence_alias() -> None:
    contract, rows = fix2._cluster_fixture()
    result = evaluation.cluster_bootstrap_precision(contract, rows)
    payload = result.input_manifest.model_dump(mode="python")
    duplicate = dict(payload["observations"][4])
    duplicate["evidence_ids"] = ("E-EVIDENCE-ALIAS",)
    payload["observations"] = (*payload["observations"], duplicate)
    payload["observation_count"] += 1
    estimate = next(
        item
        for item in payload["cluster_estimates"]
        if item["generalization_unit_id"] == duplicate["generalization_unit_id"]
    )
    cluster_rows = [
        item
        for item in payload["observations"]
        if item["generalization_unit_id"] == duplicate["generalization_unit_id"]
    ]
    estimate["estimate"] = sum((item["value"] for item in cluster_rows), Decimal("0")) / Decimal(
        len(cluster_rows)
    )
    estimate["evidence_ids"] = tuple(
        sorted({evidence_id for item in cluster_rows for evidence_id in item["evidence_ids"]})
    )

    with pytest.raises(ValidationError, match=r"duplicate observation|semantic duplicate"):
        evaluation.ClusterObservationManifest.model_validate(_readdress_manifest(payload))


def test_cluster_result_rejects_replaced_declared_cluster_after_readdressing() -> None:
    contract, rows = fix2._cluster_fixture()
    result = evaluation.cluster_bootstrap_precision(contract, rows)
    payload = result.model_dump(mode="python")
    manifest = payload["input_manifest"]
    for observation in manifest["observations"]:
        if observation["generalization_unit_id"] == "SF-3":
            observation["generalization_unit_id"] = "SF-ALIAS"
            checksum = evaluation.cluster_elementary_source_checksum(
                metric_id=observation["metric_id"],
                elementary_source_id=observation["elementary_source_id"],
                generalization_unit_id=observation["generalization_unit_id"],
                value=observation["value"],
                stratum_values=observation["stratum_values"],
            )
            observation["elementary_source_checksum"] = checksum
            observation["observation_id"] = f"CLUSTER-OBSERVATION-{checksum[:20]}"
    for estimate in manifest["cluster_estimates"]:
        if estimate["generalization_unit_id"] == "SF-3":
            estimate["generalization_unit_id"] = "SF-ALIAS"
    payload["input_manifest"] = _readdress_manifest(manifest)

    with pytest.raises(ValidationError, match=r"cluster.*contract|declared cluster"):
        evaluation.ClusterPrecisionResult.model_validate(fix2._readdress_cluster_payload(payload))
