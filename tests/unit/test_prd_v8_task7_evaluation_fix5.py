from __future__ import annotations

import importlib
from decimal import Decimal

import pytest
from prd_v8_cluster_authority_fixtures import implementation_conformance_cluster_authority
from pydantic import ValidationError

import ntruth.evaluation_v8 as evaluation
from ntruth.schemas.core import content_checksum
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue

fix2 = importlib.import_module("test_prd_v8_task7_evaluation_fix2")


def _assert_governed_precision_unresolved(result: object) -> None:
    assert result.interval.knowledge_state is KnowledgeState.UNKNOWN  # type: ignore[attr-defined]
    assert result.authority_resolution.knowledge_state is KnowledgeState.UNKNOWN  # type: ignore[attr-defined]
    assert result.scientific_use_permitted is False  # type: ignore[attr-defined]
    blocker_ids = {item.issue_id for item in result.blockers}  # type: ignore[attr-defined]
    assert "SRR-V8-CLUSTER-PRECISION" in blocker_ids
    assert "SRR-V8-EVAL-SCIENTIFIC-HOLD" in blocker_ids


def test_canonical_precision_api_rejects_caller_conformance_argument() -> None:
    """Catches reintroducing a caller-controlled sibling authority argument."""

    contract, rows = fix2._cluster_fixture()
    caller_built = implementation_conformance_cluster_authority(contract, rows)

    with pytest.raises(TypeError, match="implementation_conformance"):
        evaluation.cluster_bootstrap_precision(
            contract,
            rows,
            implementation_conformance=caller_built,
        )


@pytest.mark.parametrize(
    "mutation",
    (
        "baseline",
        "source-evidence-alias",
        "restratify",
        "unit-reorder",
        "unit-replace",
        "reviewers",
    ),
)
def test_caller_built_matching_registry_and_pin_cannot_clear_governed_precision(
    mutation: str,
) -> None:
    """Catches treating a fully caller-issued checksum chain as external authority."""

    contract, rows = fix2._cluster_fixture()
    reviewer_actor_ids = ("REVIEWER-INDEPENDENT-A", "REVIEWER-INDEPENDENT-B")
    if mutation == "source-evidence-alias":
        original = rows[0]
        rows = (
            *rows,
            evaluation.build_cluster_metric_observation(
                metric_id=original.metric_id,
                elementary_source_id="SOURCE-CALLER-ALIAS",
                generalization_unit_id=original.generalization_unit_id,
                value=original.value,
                stratum_values=original.stratum_values,
                evidence_ids=("E-CALLER-ALIAS",),
            ),
        )
    elif mutation == "restratify":
        rows = tuple(
            evaluation.build_cluster_metric_observation(
                metric_id=row.metric_id,
                elementary_source_id=row.elementary_source_id,
                generalization_unit_id=row.generalization_unit_id,
                value=row.value,
                stratum_values={"profile": "B"}
                if row.generalization_unit_id == "SF-3"
                else row.stratum_values,
                evidence_ids=row.evidence_ids,
            )
            for row in rows
        )
    elif mutation == "unit-reorder":
        contract = evaluation.MetricGeneralizationContract.model_validate(
            {**contract.model_dump(mode="python"), "units": tuple(reversed(contract.units))}
        )
    elif mutation == "unit-replace":
        contract = evaluation.MetricGeneralizationContract.model_validate(
            {
                **contract.model_dump(mode="python"),
                "units": (
                    *contract.units[:-1],
                    evaluation.GeneralizationUnit(
                        metric_id=contract.metric_id,
                        generalization_unit_id="SF-CALLER-ALIAS",
                    ),
                ),
            }
        )
        rows = tuple(
            evaluation.build_cluster_metric_observation(
                metric_id=row.metric_id,
                elementary_source_id=row.elementary_source_id,
                generalization_unit_id="SF-CALLER-ALIAS"
                if row.generalization_unit_id == "SF-3"
                else row.generalization_unit_id,
                value=row.value,
                stratum_values=row.stratum_values,
                evidence_ids=row.evidence_ids,
            )
            for row in rows
        )
    elif mutation == "reviewers":
        reviewer_actor_ids = ("CALLER-REISSUED-REVIEWER-A", "CALLER-REISSUED-REVIEWER-B")
    caller_built = implementation_conformance_cluster_authority(
        contract,
        rows,
        reviewer_actor_ids=reviewer_actor_ids,
    )

    conformance = evaluation.build_cluster_precision_conformance_artifact(
        contract,
        rows,
        implementation_conformance=caller_built,
    )
    assert "SRR-V8-CLUSTER-PRECISION" in {item.issue_id for item in conformance.blockers}
    result = evaluation.cluster_bootstrap_precision(contract, rows)

    _assert_governed_precision_unresolved(result)


def test_coherent_bootstrap_reissue_cannot_clear_governed_precision() -> None:
    """Catches re-preregistering seed/iterations/CI through the same caller chain."""

    contract, rows = fix2._cluster_fixture()
    bootstrap_payload = contract.bootstrap.model_dump(mode="python")
    bootstrap_payload.update(
        seed="caller-reissued-seed",
        iterations=301,
        confidence_level=Decimal("0.9"),
    )
    changed_contract = evaluation.MetricGeneralizationContract.model_validate(
        {
            **contract.model_dump(mode="python"),
            "bootstrap": bootstrap_payload,
        }
    )
    caller_built = implementation_conformance_cluster_authority(changed_contract, rows)

    conformance = evaluation.build_cluster_precision_conformance_artifact(
        changed_contract,
        rows,
        implementation_conformance=caller_built,
    )
    assert "SRR-V8-CLUSTER-PRECISION" in {item.issue_id for item in conformance.blockers}
    result = evaluation.cluster_bootstrap_precision(changed_contract, rows)

    _assert_governed_precision_unresolved(result)


def test_implementation_conformance_review_scope_never_clears_scientific_blocker() -> None:
    """Catches promoting implementation-conformance review to governed precision."""

    contract, rows = fix2._cluster_fixture()
    caller_built = implementation_conformance_cluster_authority(contract, rows)

    assert (
        caller_built.registry.contract_artifact.review_scope_id
        == evaluation.IMPLEMENTATION_CONFORMANCE_REVIEW_SCOPE_ID
    )
    conformance = evaluation.build_cluster_precision_conformance_artifact(
        contract,
        rows,
        implementation_conformance=caller_built,
    )
    assert "SRR-V8-CLUSTER-PRECISION" in {item.issue_id for item in conformance.blockers}
    result = evaluation.cluster_bootstrap_precision(contract, rows)

    _assert_governed_precision_unresolved(result)


def test_full_result_readdress_cannot_promote_caller_authority_to_present() -> None:
    """Catches bypassing the builder by readdressing a complete result payload."""

    contract, rows = fix2._cluster_fixture()
    caller_built = implementation_conformance_cluster_authority(contract, rows)
    result = evaluation.cluster_bootstrap_precision(contract, rows)
    payload = result.model_dump(mode="python")
    payload["authority_resolution"] = KnowledgeValue[evaluation.GovernedClusterPrecisionAuthority](
        knowledge_state=KnowledgeState.PRESENT,
        value=evaluation.GovernedClusterPrecisionAuthority(
            registry_id=caller_built.registry.registry_id,
            registry_checksum=caller_built.registry.content_checksum,
            resolver_configuration_id="CALLER-REISSUED-RESOLVER",
            resolver_configuration_checksum="0" * 64,
        ),
        evidence_ids=("E-PREREGISTRATION", "E-CUSTODY", "E-INDEPENDENT-REVIEW"),
        query_scope_id=contract.metric_id,
    ).model_dump(mode="python")
    payload["interval"] = KnowledgeValue[evaluation.PrecisionInterval](
        knowledge_state=KnowledgeState.PRESENT,
        value=evaluation.PrecisionInterval(
            method_id=contract.bootstrap.method_id,
            confidence_level=contract.bootstrap.confidence_level,
            point_estimate=Decimal("0.1666666666666666666666666666666666666667"),
            lower=Decimal("0"),
            upper=Decimal("0.3333333333333333333333333333333333333333"),
        ),
        evidence_ids=("E-1-1", "E-1-2", "E-2-1", "E-2-2", "E-3-1", "E-3-2"),
        query_scope_id=contract.metric_id,
    ).model_dump(mode="python")
    payload["blockers"] = tuple(
        item for item in payload["blockers"] if item["issue_id"] != "SRR-V8-CLUSTER-PRECISION"
    )

    with pytest.raises(ValidationError, match=r"governed.*resolver|authority.*unavailable"):
        evaluation.ClusterPrecisionResult.model_validate(fix2._readdress_cluster_payload(payload))


def test_deterministic_interval_is_exposed_only_as_conformance_artifact() -> None:
    """Catches losing algorithm tests or relabeling their output as governed precision."""

    contract, rows = fix2._cluster_fixture()
    caller_built = implementation_conformance_cluster_authority(contract, rows)
    builder = getattr(evaluation, "build_cluster_precision_conformance_artifact", None)

    assert callable(builder), "explicit implementation-conformance precision API is missing"
    artifact = builder(
        contract,
        rows,
        implementation_conformance=caller_built,
    )

    assert artifact.__class__.__name__ == "ClusterPrecisionConformanceArtifact"
    assert artifact.interval.knowledge_state is KnowledgeState.PRESENT
    assert artifact.scientific_use_permitted is False
    assert {item.issue_id for item in artifact.blockers} == {
        "SRR-V8-CLUSTER-PRECISION",
        "SRR-V8-EVAL-SCIENTIFIC-HOLD",
    }


def test_cluster_outputs_cannot_be_readdressed_as_scientific_authority() -> None:
    """Catches model-copy or full-readdress promotion of either output contract."""

    contract, rows = fix2._cluster_fixture()
    canonical = evaluation.cluster_bootstrap_precision(contract, rows)
    canonical_payload = canonical.model_dump(mode="python")
    canonical_payload["scientific_use_permitted"] = True
    with pytest.raises(ValidationError, match="not a scientific release authority"):
        evaluation.ClusterPrecisionResult.model_validate(
            fix2._readdress_cluster_payload(canonical_payload)
        )

    conformance = evaluation.build_cluster_precision_conformance_artifact(
        contract,
        rows,
        implementation_conformance=implementation_conformance_cluster_authority(contract, rows),
    )
    conformance_payload = conformance.model_dump(mode="python")
    conformance_payload["scientific_use_permitted"] = True
    checksum = content_checksum(
        {
            key: value
            for key, value in conformance_payload.items()
            if key not in {"artifact_id", "content_checksum"}
        }
    )
    conformance_payload["content_checksum"] = checksum
    conformance_payload["artifact_id"] = f"CLUSTER-PRECISION-CONFORMANCE-{checksum[:20]}"
    with pytest.raises(ValidationError, match="False"):
        evaluation.ClusterPrecisionConformanceArtifact.model_validate(conformance_payload)
