"""Costruzione e serializzazione del manifest content-addressed del dataset."""

from __future__ import annotations

import json

from ntruth.schemas.core import content_checksum
from ntruth.training.records import (
    DatasetManifest,
    DuplicateDecision,
    ManifestRecord,
    PreparationConfig,
    PreparationReport,
    PreparedRecord,
    _family_evidence,
)


def build_manifest_records(records: tuple[PreparedRecord, ...]) -> tuple[ManifestRecord, ...]:
    """Riduce i record a un indice verificabile conservando la provenance critica."""

    return tuple(
        ManifestRecord(
            record_id=prepared.record.record_id,
            record_checksum=content_checksum(prepared.model_dump(mode="json")),
            input_checksum=_input_checksum(prepared.record.input_text),
            candidate_target_checksum=content_checksum(
                prepared.record.target.candidate_target.model_dump(mode="json")
            ),
            exact_fingerprint=prepared.exact_fingerprint,
            near_fingerprint=prepared.near_fingerprint,
            split=prepared.split,
            leakage_group_id=prepared.leakage_group_id,
            source_id=prepared.record.provenance.source_id,
            source_asset_id=prepared.record.provenance.source_asset_id,
            source_sha256=prepared.record.provenance.source_sha256,
            governance_hash=prepared.record.provenance.governance_hash,
            publication_id=prepared.record.provenance.publication_id,
            supplement_id=prepared.record.provenance.supplement_id,
            preprint_id=prepared.record.provenance.preprint_id,
            dataset_id=prepared.record.provenance.dataset_id,
            project_id=prepared.record.provenance.project_id,
            bundle_id=prepared.record.provenance.bundle_id,
            laboratory_id=prepared.record.provenance.laboratory_id,
            facility_id=prepared.record.provenance.facility_id,
            corresponding_author_id=prepared.record.provenance.corresponding_author_id,
            synthetic_family_id=prepared.record.provenance.synthetic_family_id,
            counterfactual_family_id=prepared.record.provenance.counterfactual_family_id,
            annotation_status=prepared.record.annotation_status,
            training_eligible=prepared.record.training_eligible,
            evaluation_eligible=prepared.record.evaluation_eligible,
            release_eligible=prepared.record.release_eligible,
            model_selection_eligible=prepared.record.model_selection_eligible,
            license_or_authorization_id=(prepared.record.provenance.license_or_authorization_id),
            reviewer_count=prepared.record.provenance.reviewer_count,
            reviewer_ids=prepared.record.provenance.reviewer_ids,
            reviewer_roles=prepared.record.provenance.reviewer_roles,
            adjudication_id=prepared.record.provenance.adjudication_id,
            target_adjudication_id=prepared.record.target.adjudication_id,
            submission_ids=tuple(
                reference.submission_id
                for reference in prepared.record.target.submission_references
            ),
            submission_checksums=tuple(
                reference.submission_sha256
                for reference in prepared.record.target.submission_references
            ),
            comparison_status=prepared.record.target.comparison_status,
            material_differences_checksum=content_checksum(
                [
                    difference.model_dump(mode="json")
                    for difference in prepared.record.target.material_differences
                ]
            ),
            candidate_count_kinds=tuple(
                count.kind for count in prepared.record.target.candidate_target.candidate_counts
            ),
            family_evidence=_family_evidence(prepared.record.provenance),
            external_challenge_dependency=(
                prepared.record.provenance.external_challenge_dependency
            ),
            synthetic=prepared.record.provenance.synthetic,
        )
        for prepared in sorted(records, key=lambda item: item.record.record_id)
    )


def _input_checksum(input_text: str) -> str:
    try:
        payload = json.loads(input_text)
    except json.JSONDecodeError:
        payload = input_text
    return content_checksum(payload)


def manifest_records_checksum(records: tuple[ManifestRecord, ...]) -> str:
    payload = sorted(
        (record.model_dump(mode="json") for record in records),
        key=lambda item: str(item["record_id"]),
    )
    return content_checksum(payload)


def build_dataset_manifest(
    *,
    records: tuple[ManifestRecord, ...],
    config: PreparationConfig,
    decisions: tuple[DuplicateDecision, ...],
    report: PreparationReport,
) -> DatasetManifest:
    decision_payload = [
        decision.model_dump(mode="json")
        for decision in sorted(
            decisions,
            key=lambda item: (
                item.kind.value,
                item.duplicate_record_id,
                item.canonical_record_id,
            ),
        )
    ]
    return DatasetManifest(
        parent_dataset_ids=config.parent_dataset_ids,
        record_schema_version=config.record_schema_version,
        normalization_version=config.normalization_version,
        config_checksum=config.checksum(),
        records_checksum=manifest_records_checksum(records),
        decisions_checksum=content_checksum(decision_payload),
        report_checksum=content_checksum(report.model_dump(mode="json")),
        records=records,
    )


def _dumps_model(model: DatasetManifest | PreparationReport) -> str:
    return (
        json.dumps(
            model.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def dumps_dataset_manifest(manifest: DatasetManifest) -> str:
    return _dumps_model(manifest)


def dumps_preparation_report(report: PreparationReport) -> str:
    return _dumps_model(report)
