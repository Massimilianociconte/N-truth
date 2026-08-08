from __future__ import annotations

import importlib

import pytest
from prd_v8_cluster_authority_fixtures import implementation_conformance_cluster_authority
from pydantic import ValidationError

import ntruth.evaluation_v8 as evaluation
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue

fix2 = importlib.import_module("test_prd_v8_task7_evaluation_fix2")


def _cluster_outputs() -> tuple[
    evaluation.ClusterPrecisionResult,
    evaluation.ClusterPrecisionConformanceArtifact,
]:
    contract, rows = fix2._cluster_fixture()
    result = evaluation.cluster_bootstrap_precision(contract, rows)
    conformance = evaluation.build_cluster_precision_conformance_artifact(
        contract,
        rows,
        implementation_conformance=implementation_conformance_cluster_authority(contract, rows),
    )
    return result, conformance


def test_result_model_copy_cannot_skip_cluster_authority_validation() -> None:
    """Catches an unvalidated copy becoming a serializable governed result."""

    result, conformance = _cluster_outputs()
    authority = evaluation.GovernedClusterPrecisionAuthority(
        registry_id="CALLER-REGISTRY",
        registry_checksum="1" * 64,
        resolver_configuration_id="CALLER-RESOLVER",
        resolver_configuration_checksum="2" * 64,
    )
    authority_resolution = KnowledgeValue[evaluation.GovernedClusterPrecisionAuthority](
        knowledge_state=KnowledgeState.PRESENT,
        value=authority,
        evidence_ids=("E-CALLER-AUTHORITY",),
        query_scope_id=result.metric_id,
    )

    with pytest.raises(ValidationError):
        result.model_copy(
            update={
                "authority_resolution": authority_resolution,
                "interval": conformance.interval,
                "scientific_use_permitted": True,
                "blockers": (),
            }
        )


def test_conformance_model_copy_cannot_skip_non_authority_validation() -> None:
    """Catches an unvalidated conformance copy dropping its scientific boundary."""

    _result, conformance = _cluster_outputs()

    with pytest.raises(ValidationError):
        conformance.model_copy(
            update={
                "scientific_use_permitted": True,
                "blockers": (),
            }
        )


@pytest.mark.parametrize("deep", (False, True))
def test_cluster_output_model_copy_without_update_remains_supported(deep: bool) -> None:
    """Catches the local safety boundary breaking ordinary validated copies."""

    for output in _cluster_outputs():
        copied = output.model_copy(deep=deep)

        assert copied == output
        assert copied is not output
        assert type(output).model_validate(copied.model_dump(mode="python")) == output


def test_cluster_output_model_copy_accepts_a_validated_noop_update() -> None:
    """Catches replacing validation with a blanket ban on typed model updates."""

    result, conformance = _cluster_outputs()

    assert result.model_copy(update={"result_id": result.result_id}) == result
    assert conformance.model_copy(update={"artifact_id": conformance.artifact_id}) == conformance
