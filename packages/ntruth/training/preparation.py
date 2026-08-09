"""Pipeline deterministica: valida, normalizza, deduplica, separa e manifesta."""

from __future__ import annotations

from collections.abc import Iterable

from ntruth.governance.lineage import CorpusSplit
from ntruth.schemas.core import content_checksum
from ntruth.training.dedup import deduplicate_records, duplicate_id_issues
from ntruth.training.manifest import (
    build_dataset_manifest,
    build_manifest_records,
    manifest_records_checksum,
)
from ntruth.training.records import (
    DuplicateKind,
    IssueSeverity,
    PreparationConfig,
    PreparationReport,
    PreparedDataset,
    PreparedRecord,
    SupervisedRecord,
    ValidationIssue,
    normalize_record,
)
from ntruth.training.splits import assign_group_aware_splits


class DatasetValidationError(ValueError):
    """Uno o piu invarianti impediscono di dichiarare pronto il dataset."""

    def __init__(self, issues: tuple[ValidationIssue, ...]) -> None:
        self.issues = issues
        codes = ", ".join(sorted({issue.code for issue in issues}))
        super().__init__(f"preparazione dataset non valida: {codes}")


def _ordered_issues(issues: Iterable[ValidationIssue]) -> tuple[ValidationIssue, ...]:
    return tuple(
        sorted(
            issues,
            key=lambda issue: (issue.severity.value, issue.code, issue.record_ids),
        )
    )


def _raise_if_errors(
    issues: tuple[ValidationIssue, ...],
    *,
    fail_on_error: bool,
    always: bool = False,
) -> None:
    errors = tuple(issue for issue in issues if issue.severity is IssueSeverity.ERROR)
    if errors and (fail_on_error or always):
        raise DatasetValidationError(errors)


def _raise_if_split_membership_is_unrepresentable(
    issues: tuple[ValidationIssue, ...],
) -> None:
    structural = tuple(
        issue
        for issue in issues
        if issue.code
        in {
            "conflicting_requested_splits",
            "conflicting_duplicate_requested_splits",
        }
    )
    if structural:
        raise DatasetValidationError(structural)


def _revalidate_source_record(record: SupervisedRecord) -> SupervisedRecord:
    try:
        payload = record.model_dump(mode="python", round_trip=True, warnings="error")
        return SupervisedRecord.model_validate(payload)
    except Exception as exc:
        raise DatasetValidationError(
            (
                ValidationIssue(
                    code="invalid_supervised_record",
                    severity=IssueSeverity.ERROR,
                    detail="SupervisedRecord non valido al confine di preparazione",
                ),
            )
        ) from exc


def prepare_dataset(
    records: Iterable[SupervisedRecord],
    *,
    config: PreparationConfig | None = None,
) -> PreparedDataset:
    """Prepara un artefatto riproducibile senza addestrare o scaricare modelli."""

    active_config = config or PreparationConfig()
    source_records = tuple(records)
    validated_records = tuple(_revalidate_source_record(record) for record in source_records)
    normalized_all = tuple(
        normalize_record(record, shingle_size=active_config.shingle_size)
        for record in validated_records
    )

    # Un ID ambiguo non puo essere rappresentato in manifest: e sempre fatale,
    # anche in modalita diagnostica fail_on_error=False.
    identity_issues = duplicate_id_issues(normalized_all)
    _raise_if_errors(identity_issues, fail_on_error=True, always=True)

    issues: list[ValidationIssue] = []
    # Preparation preserves the complete membership ledger. Training eligibility
    # controls only the physical training view produced later; it is never a data
    # quality filter and must not erase TEST/EXTERNAL_CHALLENGE membership.
    selected = normalized_all
    excluded_ids: tuple[str, ...] = ()
    diagnostic_ids = tuple(
        sorted(
            record.record.record_id for record in selected if not record.record.training_eligible
        )
    )
    if diagnostic_ids:
        issues.append(
            ValidationIssue(
                code="training_ineligible_membership_preserved",
                severity=IssueSeverity.WARNING,
                detail=(
                    "non-training membership is preserved but excluded from every "
                    "physical training view"
                ),
                record_ids=diagnostic_ids,
            )
        )

    if not selected:
        issues.append(
            ValidationIssue(
                code="no_records_selected",
                severity=IssueSeverity.ERROR,
                detail="nessun record soddisfa i criteri di preparazione",
            )
        )

    deduplication = deduplicate_records(
        selected,
        near_threshold=active_config.near_duplicate_threshold,
    )
    issues.extend(deduplication.issues)
    _raise_if_split_membership_is_unrepresentable(_ordered_issues(issues))
    _raise_if_errors(
        _ordered_issues(issues),
        fail_on_error=active_config.fail_on_error,
    )

    split_result = assign_group_aware_splits(
        selected,
        ratios=active_config.split_ratios,
        seed=active_config.seed,
        duplicate_decisions=deduplication.decisions,
        related_record_pairs=deduplication.leakage_links,
    )
    issues.extend(split_result.issues)
    ordered_issues = _ordered_issues(issues)
    _raise_if_split_membership_is_unrepresentable(ordered_issues)
    _raise_if_errors(ordered_issues, fail_on_error=active_config.fail_on_error)

    assignment_by_id = {assignment.record_id: assignment for assignment in split_result.assignments}
    split_order = {
        CorpusSplit.UNASSIGNED: -1,
        CorpusSplit.TRAIN: 0,
        CorpusSplit.VALIDATION: 1,
        CorpusSplit.TEST: 2,
        CorpusSplit.EXTERNAL_CHALLENGE: 3,
    }
    prepared_records = tuple(
        sorted(
            (
                PreparedRecord(
                    record=normalized.record,
                    normalized_input=normalized.normalized_input,
                    canonical_target=normalized.canonical_target,
                    exact_fingerprint=normalized.exact_fingerprint,
                    near_fingerprint=normalized.near_fingerprint,
                    leakage_group_id=assignment_by_id[normalized.record.record_id].leakage_group_id,
                    split=assignment_by_id[normalized.record.record_id].split,
                )
                for normalized in deduplication.kept
            ),
            key=lambda prepared: (
                split_order[prepared.split],
                prepared.record.record_id,
            ),
        )
    )
    manifest_records = build_manifest_records(prepared_records)
    records_checksum = manifest_records_checksum(manifest_records)

    exact_count = sum(decision.kind is DuplicateKind.EXACT for decision in deduplication.decisions)
    near_count = sum(decision.kind is DuplicateKind.NEAR for decision in deduplication.decisions)
    split_counts = {
        split.value: sum(record.split is split for record in prepared_records)
        for split in CorpusSplit
    }
    report = PreparationReport(
        input_count=len(source_records),
        eligible_count=len(selected),
        excluded_count=len(excluded_ids),
        kept_count=len(prepared_records),
        exact_duplicate_count=exact_count,
        near_duplicate_count=near_count,
        leakage_group_count=split_result.leakage_group_count,
        split_counts=split_counts,
        dataset_records_checksum=records_checksum,
        issues=ordered_issues,
        duplicate_decisions=deduplication.decisions,
    )
    manifest = build_dataset_manifest(
        records=manifest_records,
        config=active_config,
        decisions=deduplication.decisions,
        report=report,
    )
    # Calcolo esplicito per rendere evidente che non entra alcun timestamp.
    if manifest.records_checksum != content_checksum(
        sorted(
            (record.model_dump(mode="json") for record in manifest.records),
            key=lambda item: str(item["record_id"]),
        )
    ):
        raise RuntimeError("checksum manifest non deterministico")
    return PreparedDataset(records=prepared_records, manifest=manifest, report=report)
