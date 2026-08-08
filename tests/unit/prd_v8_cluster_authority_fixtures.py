from __future__ import annotations

import hashlib

import ntruth.evaluation_v8 as evaluation


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def implementation_conformance_cluster_authority(
    contract: object,
    rows: tuple[object, ...],
    *,
    reviewer_actor_ids: tuple[str, ...] = (
        "REVIEWER-INDEPENDENT-A",
        "REVIEWER-INDEPENDENT-B",
    ),
) -> object:
    """Build a content-addressed implementation-conformance closure fixture."""

    required_symbols = (
        "ImplementationConformanceClusterPin",
        "ClusterStratumAssignment",
        "build_cluster_evidence_ledger",
        "build_cluster_evidence_record",
        "build_cluster_elementary_source_ledger",
        "build_cluster_elementary_source_record",
        "build_implementation_conformance_cluster_authority",
        "build_implementation_conformance_cluster_registry",
        "build_metric_generalization_contract_artifact",
    )
    missing = tuple(name for name in required_symbols if not hasattr(evaluation, name))
    assert not missing, f"cluster conformance API is missing: {missing}"

    evidence_ids = {
        evidence_id
        for row in rows
        for evidence_id in row.evidence_ids  # type: ignore[attr-defined]
    }
    governance_ids = {"E-PREREGISTRATION", "E-CUSTODY", "E-INDEPENDENT-REVIEW"}
    evidence_records = {
        evidence_id: evaluation.build_cluster_evidence_record(
            evidence_record_id=evidence_id,
            evidence_content_checksum=_digest(f"evidence-payload:{evidence_id}"),
            custody_record_id=f"CUSTODY-{evidence_id}",
            custody_record_checksum=_digest(f"custody-payload:{evidence_id}"),
        )
        for evidence_id in sorted(evidence_ids | governance_ids)
    }
    evidence_ledger = evaluation.build_cluster_evidence_ledger(
        records=tuple(evidence_records.values())
    )
    strata_by_cluster = {
        row.generalization_unit_id: row.stratum_values  # type: ignore[attr-defined]
        for row in rows
    }
    contract_artifact = evaluation.build_metric_generalization_contract_artifact(
        contract=contract,
        cluster_strata=tuple(
            evaluation.ClusterStratumAssignment(
                generalization_unit_id=unit.generalization_unit_id,
                stratum_values=strata_by_cluster[unit.generalization_unit_id],
            )
            for unit in contract.units  # type: ignore[attr-defined]
        ),
        preregistration_evidence_records=(evidence_records["E-PREREGISTRATION"],),
        custody_evidence_records=(evidence_records["E-CUSTODY"],),
        review_evidence_records=(evidence_records["E-INDEPENDENT-REVIEW"],),
        reviewer_actor_ids=reviewer_actor_ids,
        review_scope_id=evaluation.IMPLEMENTATION_CONFORMANCE_REVIEW_SCOPE_ID,
    )
    source_records = tuple(
        evaluation.build_cluster_elementary_source_record(
            source_record_id=row.elementary_source_id,
            metric_id=row.metric_id,
            generalization_unit_id=row.generalization_unit_id,
            value=row.value,
            stratum_values=row.stratum_values,
            evidence_records=tuple(evidence_records[item] for item in row.evidence_ids),
        )
        for row in rows
    )
    source_ledger = evaluation.build_cluster_elementary_source_ledger(
        contract_artifact=contract_artifact,
        records=source_records,
    )
    registry = evaluation.build_implementation_conformance_cluster_registry(
        contract_artifact=contract_artifact,
        source_ledger=source_ledger,
        evidence_ledger=evidence_ledger,
    )
    pin = evaluation.ImplementationConformanceClusterPin(
        registry_id=registry.registry_id,
        registry_checksum=registry.content_checksum,
    )
    return evaluation.build_implementation_conformance_cluster_authority(
        registry=registry,
        pin=pin,
    )
