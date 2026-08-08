"""Fail-closed adapters from deprecated v7 values to v8 kernel contracts."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.support import SupportGrade


class MigrationDiagnosticCode(StrEnum):
    SCIENTIFIC_REVIEW_REQUIRED = "SCIENTIFIC_REVIEW_REQUIRED"


class MigrationDiagnostic(KernelModel):
    code: MigrationDiagnosticCode
    issue_id: NonBlankStr
    message: NonBlankStr
    field_name: NonBlankStr | None = None


class MigrationLineage(KernelModel):
    source_contract: NonBlankStr
    target_contract: NonBlankStr = "ntruth-core-semantic-kernel/8.0.0"
    field_name: NonBlankStr | None = None
    migration_rule_id: NonBlankStr | None = None
    review_decision_id: NonBlankStr | None = None


class MigrationResult[T](KernelModel):
    value: T | None = None
    diagnostics: tuple[MigrationDiagnostic, ...] = ()
    lineage: tuple[MigrationLineage, ...] = ()

    @property
    def requires_scientific_review(self) -> bool:
        return any(
            diagnostic.code is MigrationDiagnosticCode.SCIENTIFIC_REVIEW_REQUIRED
            for diagnostic in self.diagnostics
        )


def _review_required(
    *, issue_id: str, message: str, field_name: str | None = None
) -> MigrationDiagnostic:
    return MigrationDiagnostic(
        code=MigrationDiagnosticCode.SCIENTIFIC_REVIEW_REQUIRED,
        issue_id=issue_id,
        message=message,
        field_name=field_name,
    )


def _blank_or_empty(value: object) -> bool:
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (tuple, list, dict, set, frozenset)):
        return not value
    return False


def migrate_v7_scientific_field(
    *,
    field_name: str,
    value: object | None,
    source_contract: str,
    evidence_ids: tuple[str, ...] = (),
    null_semantics: KnowledgeState | None = None,
    migration_rule_id: str | None = None,
) -> MigrationResult[KnowledgeValue[object]]:
    """Wrap one v7 value without guessing legacy null or empty semantics."""

    lineage = MigrationLineage(
        source_contract=source_contract,
        field_name=field_name,
        migration_rule_id=migration_rule_id,
    )
    if value is None:
        if null_semantics is None or migration_rule_id is None:
            return MigrationResult(
                diagnostics=(
                    _review_required(
                        issue_id="PRD-V8-APP-AC",
                        field_name=field_name,
                        message=(
                            "v7 null requires a field-specific reviewed mapping to UNKNOWN or "
                            "NOT_REPORTED"
                        ),
                    ),
                ),
                lineage=(lineage,),
            )
        if null_semantics not in {KnowledgeState.UNKNOWN, KnowledgeState.NOT_REPORTED}:
            raise ValueError("v7 null may map only to UNKNOWN or NOT_REPORTED")
        return MigrationResult(
            value=KnowledgeValue[object](knowledge_state=null_semantics),
            lineage=(lineage,),
        )

    if _blank_or_empty(value):
        return MigrationResult(
            diagnostics=(
                _review_required(
                    issue_id="PRD-V8-APP-AC",
                    field_name=field_name,
                    message="v7 blank or empty value has no unambiguous v8 KnowledgeState",
                ),
            ),
            lineage=(lineage,),
        )

    if not evidence_ids:
        return MigrationResult(
            diagnostics=(
                _review_required(
                    issue_id="PRD-V8-9.5",
                    field_name=field_name,
                    message="v7 value cannot become PRESENT without evidence_ids",
                ),
            ),
            lineage=(lineage,),
        )
    return MigrationResult(
        value=KnowledgeValue[object](
            knowledge_state=KnowledgeState.PRESENT,
            value=value,
            evidence_ids=evidence_ids,
        ),
        lineage=(lineage,),
    )


def migrate_v7_claim_field_names(
    payload: Mapping[str, object],
    *,
    source_contract: str,
) -> MigrationResult[dict[str, object]]:
    """Normalize only reviewed v7 claim-key aliases, preserving explicit lineage."""

    migrated = dict(payload)
    diagnostics: list[MigrationDiagnostic] = []
    lineage: list[MigrationLineage] = []
    aliases = (
        (
            "query_id",
            "inferential_query_id",
            "SRR-V8-002",
            "SRR-V8-002-query-id",
        ),
        (
            "determinability",
            "determinability_state",
            "SRR-V8-004",
            "SRR-V8-004-determinability",
        ),
    )
    for legacy_name, canonical_name, issue_id, migration_rule_id in aliases:
        if legacy_name not in migrated:
            continue
        legacy_value = migrated[legacy_name]
        lineage.append(
            MigrationLineage(
                source_contract=source_contract,
                field_name=canonical_name,
                migration_rule_id=migration_rule_id,
            )
        )
        if canonical_name in migrated and migrated[canonical_name] != legacy_value:
            diagnostics.append(
                _review_required(
                    issue_id=issue_id,
                    field_name=canonical_name,
                    message=(
                        f"legacy {legacy_name} conflicts with canonical {canonical_name}; "
                        "no value was selected"
                    ),
                )
            )
            continue
        migrated[canonical_name] = legacy_value
        del migrated[legacy_name]

    if diagnostics:
        return MigrationResult(diagnostics=tuple(diagnostics), lineage=tuple(lineage))
    return MigrationResult(value=migrated, lineage=tuple(lineage))


def migrate_support_grade(
    source: SupportGrade,
    *,
    target_vocabulary_id: str,
    reviewed_mapping: Mapping[str, str] | None = None,
    review_decision_id: str | None = None,
) -> MigrationResult[SupportGrade]:
    """Convert SupportGrade only with an explicit reviewed cross-vocabulary map."""

    if source.vocabulary_id == target_vocabulary_id:
        return MigrationResult(
            value=source,
            lineage=(
                MigrationLineage(
                    source_contract=source.vocabulary_id,
                    target_contract=target_vocabulary_id,
                ),
            ),
        )

    target_token = reviewed_mapping.get(source.token) if reviewed_mapping is not None else None
    if target_token is None or review_decision_id is None or not review_decision_id.strip():
        return MigrationResult(
            diagnostics=(
                _review_required(
                    issue_id="SRR-V8-001",
                    message=(
                        "SupportGrade vocabularies conflict; a reviewed token mapping and "
                        "decision ID are required"
                    ),
                ),
            ),
            lineage=(
                MigrationLineage(
                    source_contract=source.vocabulary_id,
                    target_contract=target_vocabulary_id,
                ),
            ),
        )

    target = SupportGrade(vocabulary_id=target_vocabulary_id, token=target_token)
    return MigrationResult(
        value=target,
        lineage=(
            MigrationLineage(
                source_contract=source.vocabulary_id,
                target_contract=target_vocabulary_id,
                review_decision_id=review_decision_id,
            ),
        ),
    )


__all__ = [
    "MigrationDiagnostic",
    "MigrationDiagnosticCode",
    "MigrationLineage",
    "MigrationResult",
    "migrate_support_grade",
    "migrate_v7_claim_field_names",
    "migrate_v7_scientific_field",
]
