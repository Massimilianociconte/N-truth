from __future__ import annotations

import importlib
from decimal import Decimal

import pytest
from prd_v8_cluster_authority_fixtures import implementation_conformance_cluster_authority
from pydantic import ValidationError

import ntruth.evaluation_v8 as evaluation
from ntruth.schemas.knowledge import KnowledgeState

fix2 = importlib.import_module("test_prd_v8_task7_evaluation_fix2")


def _replace_contract(contract: object, **updates: object) -> object:
    payload = contract.model_dump(mode="python")  # type: ignore[attr-defined]
    payload.update(updates)
    return evaluation.MetricGeneralizationContract.model_validate(payload)


def test_cluster_precision_without_resolved_authority_fails_closed() -> None:
    contract, rows = fix2._cluster_fixture()

    result = evaluation.cluster_bootstrap_precision(contract, rows)

    assert result.interval.knowledge_state is KnowledgeState.UNKNOWN
    assert result.authority_resolution.knowledge_state is KnowledgeState.UNKNOWN
    assert result.scientific_use_permitted is False
    assert "SRR-V8-CLUSTER-PRECISION" in {item.issue_id for item in result.blockers}


def test_unknown_authority_state_cannot_be_reissued_with_caller_semantics() -> None:
    contract, rows = fix2._cluster_fixture()
    result = evaluation.cluster_bootstrap_precision(contract, rows)
    payload = result.model_dump(mode="python")
    payload["authority_resolution"]["rationale"] = "Caller-defined authority semantics."

    with pytest.raises(ValidationError, match=r"authority.*canonical|authority.*unresolved"):
        evaluation.ClusterPrecisionResult.model_validate(fix2._readdress_cluster_payload(payload))


def test_content_addressed_conformance_chain_only_builds_conformance_interval() -> None:
    contract, rows = fix2._cluster_fixture()
    authority = implementation_conformance_cluster_authority(contract, rows)

    result = evaluation.build_cluster_precision_conformance_artifact(
        contract,
        rows,
        implementation_conformance=authority,
    )

    assert result.implementation_conformance == authority
    assert result.interval.knowledge_state is KnowledgeState.PRESENT
    assert result.input_manifest.observation_count == 6
    assert result.scientific_use_permitted is False
    assert {item.issue_id for item in result.blockers} == {
        "SRR-V8-CLUSTER-PRECISION",
        "SRR-V8-EVAL-SCIENTIFIC-HOLD",
    }


def test_source_and_evidence_aliases_cannot_create_a_pseudo_observation() -> None:
    contract, rows = fix2._cluster_fixture()
    authority = implementation_conformance_cluster_authority(contract, rows)
    original = rows[4]
    alias = evaluation.build_cluster_metric_observation(
        metric_id=original.metric_id,
        elementary_source_id="SOURCE-ALIAS",
        generalization_unit_id=original.generalization_unit_id,
        value=original.value,
        stratum_values=original.stratum_values,
        evidence_ids=("E-EVIDENCE-ALIAS",),
    )

    with pytest.raises(ValueError, match=r"conformance source|evidence ledger"):
        evaluation.build_cluster_precision_conformance_artifact(
            contract,
            (*rows, alias),
            implementation_conformance=authority,
        )


def test_caller_restratification_cannot_change_the_precision_interval() -> None:
    contract, rows = fix2._cluster_fixture()
    authority = implementation_conformance_cluster_authority(contract, rows)
    changed = tuple(
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

    with pytest.raises(ValueError, match=r"strat|conformance source"):
        evaluation.build_cluster_precision_conformance_artifact(
            contract,
            changed,
            implementation_conformance=authority,
        )


@pytest.mark.parametrize("mutation", ["reorder", "replace"])
def test_embedded_contract_unit_mutation_fails_against_fixed_conformance_pin(
    mutation: str,
) -> None:
    contract, rows = fix2._cluster_fixture()
    authority = implementation_conformance_cluster_authority(contract, rows)
    units = contract.units
    if mutation == "reorder":
        changed_units = tuple(reversed(units))
        changed_rows = rows
    else:
        changed_units = (
            *units[:-1],
            evaluation.GeneralizationUnit(
                metric_id=contract.metric_id,
                generalization_unit_id="SF-ALIAS",
            ),
        )
        changed_rows = tuple(
            evaluation.build_cluster_metric_observation(
                metric_id=row.metric_id,
                elementary_source_id=row.elementary_source_id,
                generalization_unit_id="SF-ALIAS"
                if row.generalization_unit_id == "SF-3"
                else row.generalization_unit_id,
                value=row.value,
                stratum_values=row.stratum_values,
                evidence_ids=row.evidence_ids,
            )
            for row in rows
        )
    changed_contract = _replace_contract(contract, units=changed_units)

    with pytest.raises(ValueError, match=r"contract artifact|authority|metric contract"):
        evaluation.build_cluster_precision_conformance_artifact(
            changed_contract,
            changed_rows,
            implementation_conformance=authority,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("seed", "caller-seed"),
        ("iterations", 301),
        ("confidence_level", Decimal("0.9")),
    ],
)
def test_bootstrap_protocol_mutation_fails_against_fixed_conformance_pin(
    field: str,
    value: object,
) -> None:
    contract, rows = fix2._cluster_fixture()
    authority = implementation_conformance_cluster_authority(contract, rows)
    bootstrap_payload = contract.bootstrap.model_dump(mode="python")
    bootstrap_payload[field] = value
    changed_contract = _replace_contract(contract, bootstrap=bootstrap_payload)

    with pytest.raises(ValueError, match=r"contract artifact|authority|metric contract"):
        evaluation.build_cluster_precision_conformance_artifact(
            changed_contract,
            rows,
            implementation_conformance=authority,
        )


def test_conformance_resolution_rejects_readdressed_registry_with_stale_pin() -> None:
    contract, rows = fix2._cluster_fixture()
    authority = implementation_conformance_cluster_authority(contract, rows)
    registry = authority.registry.model_copy(
        update={"registry_id": "CLUSTER-CONFORMANCE-REGISTRY-CALLER-REISSUED"}
    )

    with pytest.raises((ValidationError, ValueError), match=r"registry|checksum|pin"):
        evaluation.build_implementation_conformance_cluster_authority(
            registry=registry,
            pin=authority.pin,
        )
