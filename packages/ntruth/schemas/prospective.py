"""Immutable prospective plan and executed-design records for PRD v8.

The planned snapshot is never rewritten by reconciliation.  Every execution
links to the exact content-addressed plan and may therefore coexist with other
executions of the same plan.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Any, Self

from pydantic import Field, JsonValue, model_validator

from ntruth.schemas.core import content_checksum
from ntruth.schemas.count_registry import (
    CanonicalCountKind,
    CanonicalCountRecord,
    CountLifecyclePhase,
)
from ntruth.schemas.events import EventRegistry
from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.query import InferentialQuery
from ntruth.schemas.support import (
    ConfirmationEvent,
    EvidenceBasis,
    EvidenceRecord,
    EvidenceTypeV8,
    ScientificReviewRequirement,
    SourceContext,
    SourceRecord,
    SupportDescriptor,
)

if TYPE_CHECKING:
    from ntruth.derivation_theory.runtime import V8DerivationInput

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
INPUT_CLOSURE_REVIEW_ISSUE_ID = "QD-V8-INPUT-EVIDENCE-CLOSURE"
COUNT_RECONCILIATION_REVIEW_ISSUE_ID = "SRR-V8-011"


class ProspectiveArtifactKind(StrEnum):
    SAMPLE_SHEET = "SAMPLE_SHEET"
    METHODS_DRAFT = "METHODS_DRAFT"
    ID_CONVENTION = "ID_CONVENTION"
    EXECUTION_LOG = "EXECUTION_LOG"


class SupportBindingScope(StrEnum):
    THEORY_CLAUSE = "THEORY_CLAUSE"
    PREDICATE = "PREDICATE"


class SupportEvidenceBinding(KernelModel):
    """One exact support descriptor bound to inspectable ledger objects."""

    scope_kind: SupportBindingScope
    scope_id: NonBlankStr
    support: SupportDescriptor
    source_ids: tuple[NonBlankStr, ...] = Field(min_length=1)
    evidence_record_ids: tuple[NonBlankStr, ...] = Field(min_length=1)
    confirmation_event_ids: tuple[NonBlankStr, ...] = ()

    @model_validator(mode="after")
    def _unique_refs(self) -> Self:
        for label, values in (
            ("source_ids", self.source_ids),
            ("evidence_record_ids", self.evidence_record_ids),
            ("confirmation_event_ids", self.confirmation_event_ids),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"support binding contains duplicate {label}")
        return self


class ProspectiveArtifact(KernelModel):
    """Content carried with its digest so an artifact pin is independently checkable."""

    artifact_id: NonBlankStr
    kind: ProspectiveArtifactKind
    media_type: NonBlankStr
    content: Annotated[str, Field(min_length=1)]
    content_checksum: Sha256

    @model_validator(mode="after")
    def _addressed_artifact(self) -> Self:
        expected = content_checksum(self.content)
        if self.content_checksum != expected:
            raise ValueError("prospective artifact checksum mismatch")
        if self.artifact_id != f"ARTIFACT-{self.kind.value}-{expected[:20]}":
            raise ValueError("prospective artifact ID mismatch")
        return self


class ProspectiveInputScientificReviewRequired(ValueError):
    """Typed fail-closed boundary for an incomplete prospective evidence ledger."""

    def __init__(self, rationale: str) -> None:
        self.review_requirement = ScientificReviewRequirement(
            issue_id=INPUT_CLOSURE_REVIEW_ISSUE_ID,
            rationale=rationale,
        )
        super().__init__(f"SCIENTIFIC_REVIEW_REQUIRED: {rationale}")


class ProspectiveInputLedger(KernelModel):
    """Exact Task4 request plus source/evidence/confirmation/artifact closure."""

    ledger_id: NonBlankStr
    content_checksum: Sha256
    request_payload: dict[NonBlankStr, JsonValue]
    request_checksum: Sha256
    sources: tuple[SourceRecord, ...] = Field(min_length=1)
    evidence_records: tuple[EvidenceRecord, ...] = Field(min_length=1)
    confirmation_events: tuple[ConfirmationEvent, ...] = ()
    support_bindings: tuple[SupportEvidenceBinding, ...] = Field(min_length=1)
    artifacts: tuple[ProspectiveArtifact, ...] = Field(min_length=3)

    @property
    def request(self) -> V8DerivationInput:
        from ntruth.derivation_theory.runtime import V8DerivationInput

        return V8DerivationInput.model_validate(self.request_payload)

    @model_validator(mode="after")
    def _closed_and_addressed(self) -> Self:
        request = self.request
        expected_request = content_checksum(request.model_dump(mode="json"))
        if self.request_checksum != expected_request:
            raise ValueError("prospective ledger request checksum mismatch")
        _require_ledger_closure(
            request=request,
            sources=self.sources,
            evidence_records=self.evidence_records,
            confirmation_events=self.confirmation_events,
            support_bindings=self.support_bindings,
            artifacts=self.artifacts,
        )
        expected = content_checksum(
            self.model_dump(mode="json", exclude={"ledger_id", "content_checksum"})
        )
        if self.content_checksum != expected:
            raise ValueError("prospective input ledger checksum mismatch")
        if self.ledger_id != f"PROSPECTIVE-LEDGER-{expected[:20]}":
            raise ValueError("prospective input ledger ID mismatch")
        return self


def build_prospective_artifact(
    *,
    kind: ProspectiveArtifactKind,
    media_type: str,
    content: str,
) -> ProspectiveArtifact:
    checksum = content_checksum(content)
    return ProspectiveArtifact(
        artifact_id=f"ARTIFACT-{kind.value}-{checksum[:20]}",
        kind=kind,
        media_type=media_type,
        content=content,
        content_checksum=checksum,
    )


def _referenced_evidence_ids(value: object) -> set[str]:
    """Collect only explicit evidence-reference fields from a frozen model tree."""

    if isinstance(value, KernelModel):
        value = value.model_dump(mode="python")
    if isinstance(value, dict):
        references: set[str] = set()
        for key, item in value.items():
            if key in {"evidence_ids", "evidence_refs", "source_evidence"}:
                if isinstance(item, (tuple, list)):
                    references.update(str(entry) for entry in item)
                continue
            references.update(_referenced_evidence_ids(item))
        return references
    if isinstance(value, (tuple, list)):
        references = set()
        for item in value:
            references.update(_referenced_evidence_ids(item))
        return references
    return set()


def _require_ledger_closure(
    *,
    request: V8DerivationInput,
    sources: tuple[SourceRecord, ...],
    evidence_records: tuple[EvidenceRecord, ...],
    confirmation_events: tuple[ConfirmationEvent, ...],
    support_bindings: tuple[SupportEvidenceBinding, ...],
    artifacts: tuple[ProspectiveArtifact, ...],
) -> None:
    source_ids = [source.source_id for source in sources]
    evidence_ids = [record.evidence_id for record in evidence_records]
    confirmation_ids = [event.event_id for event in confirmation_events]
    artifact_ids = [artifact.artifact_id for artifact in artifacts]
    artifact_kinds = [artifact.kind for artifact in artifacts]
    binding_keys = [(binding.scope_kind, binding.scope_id) for binding in support_bindings]
    for label, identifiers in (
        ("source", source_ids),
        ("evidence", evidence_ids),
        ("confirmation", confirmation_ids),
        ("artifact", artifact_ids),
    ):
        if len(set(identifiers)) != len(identifiers):
            raise ValueError(f"prospective ledger contains duplicate {label} IDs")
    if len(set(binding_keys)) != len(binding_keys):
        raise ValueError("prospective ledger contains duplicate support bindings")
    if len(set(artifact_kinds)) != len(artifact_kinds):
        raise ValueError("prospective ledger contains duplicate artifact kinds")
    known_sources = set(source_ids)
    if any(record.source_id not in known_sources for record in evidence_records):
        raise ValueError("prospective evidence references a source outside the ledger")
    known_evidence = set(evidence_ids)
    missing_request_evidence = _referenced_evidence_ids(request) - known_evidence
    if missing_request_evidence:
        raise ProspectiveInputScientificReviewRequired(
            "Task4 request evidence is not closed by the prospective ledger: "
            + ", ".join(sorted(missing_request_evidence))
        )
    for event in confirmation_events:
        if not set(event.evidence_refs).issubset(known_evidence):
            raise ValueError(
                f"confirmation {event.event_id} references evidence outside the ledger"
            )
    expected_binding_keys = {
        *(
            (SupportBindingScope.THEORY_CLAUSE, clause_id)
            for clause_id in request.support_by_clause
        ),
        *(
            (SupportBindingScope.PREDICATE, predicate_id)
            for predicate_id in request.predicate_values
        ),
    }
    if set(binding_keys) != expected_binding_keys:
        missing = expected_binding_keys - set(binding_keys)
        extra = set(binding_keys) - expected_binding_keys
        raise ProspectiveInputScientificReviewRequired(
            "support binding coverage is not exact; "
            f"missing={sorted((kind.value, identifier) for kind, identifier in missing)}, "
            f"extra={sorted((kind.value, identifier) for kind, identifier in extra)}"
        )
    source_by_id = {source.source_id: source for source in sources}
    evidence_by_id = {record.evidence_id: record for record in evidence_records}
    confirmation_by_id = {event.event_id: event for event in confirmation_events}
    allowed_evidence_types = {
        EvidenceBasis.DIRECT_RECORD: {
            EvidenceTypeV8.STRUCTURAL_FACT,
            EvidenceTypeV8.PROCEDURAL_EVENT,
            EvidenceTypeV8.SAMPLE_METADATA_PLANNED,
            EvidenceTypeV8.SAMPLE_METADATA_EXECUTED,
            EvidenceTypeV8.INSTRUMENT_OR_EXECUTION_LOG,
            EvidenceTypeV8.IMAGE_METADATA,
            EvidenceTypeV8.STATISTICAL_CODE,
        },
        EvidenceBasis.STRUCTURED_DIRECT: {
            EvidenceTypeV8.STRUCTURAL_FACT,
            EvidenceTypeV8.PROCEDURAL_EVENT,
            EvidenceTypeV8.SAMPLE_METADATA_PLANNED,
            EvidenceTypeV8.SAMPLE_METADATA_EXECUTED,
            EvidenceTypeV8.INSTRUMENT_OR_EXECUTION_LOG,
            EvidenceTypeV8.IMAGE_METADATA,
        },
        EvidenceBasis.AUTHOR_ASSERTED: {
            EvidenceTypeV8.AUTHOR_ASSERTION,
            EvidenceTypeV8.AUTHOR_CLARIFICATION,
        },
        EvidenceBasis.SELF_REPORT: {
            EvidenceTypeV8.USER_CONFIRMATION,
            EvidenceTypeV8.AUTHOR_CLARIFICATION,
        },
        EvidenceBasis.CORROBORATED_CONFIRMATION: {
            EvidenceTypeV8.USER_CONFIRMATION,
            EvidenceTypeV8.AUTHOR_CLARIFICATION,
            EvidenceTypeV8.EXPERT_ADJUDICATION,
        },
        EvidenceBasis.INFERRED_CANDIDATE: {EvidenceTypeV8.MODEL_INFERENCE},
        EvidenceBasis.ADJUDICATED_REFERENCE: {EvidenceTypeV8.EXPERT_ADJUDICATION},
    }
    confirmation_required = {
        EvidenceBasis.SELF_REPORT,
        EvidenceBasis.CORROBORATED_CONFIRMATION,
    }
    request_supports = tuple(request.support_by_clause.values())
    for binding in support_bindings:
        unknown_sources = set(binding.source_ids) - source_by_id.keys()
        unknown_evidence = set(binding.evidence_record_ids) - evidence_by_id.keys()
        unknown_confirmations = set(binding.confirmation_event_ids) - confirmation_by_id.keys()
        if unknown_sources or unknown_evidence or unknown_confirmations:
            raise ValueError(
                f"support binding {binding.scope_id} contains dangling ledger references"
            )
        if binding.scope_kind is SupportBindingScope.THEORY_CLAUSE:
            if request.support_by_clause[binding.scope_id] != binding.support:
                raise ValueError(
                    f"clause support binding {binding.scope_id} differs from the Task4 request"
                )
        else:
            if binding.support not in request_supports:
                raise ValueError(
                    f"predicate support binding {binding.scope_id} is not a request support"
                )
            predicate_evidence = set(request.predicate_values[binding.scope_id].evidence_ids)
            if predicate_evidence != set(binding.evidence_record_ids):
                raise ValueError(
                    f"predicate support binding {binding.scope_id} does not exactly bind "
                    "the predicate evidence_ids"
                )
        bound_evidence = tuple(evidence_by_id[item] for item in binding.evidence_record_ids)
        if any(record.source_id not in binding.source_ids for record in bound_evidence):
            raise ValueError(
                f"support binding {binding.scope_id} evidence/source relation is inconsistent"
            )
        if any(
            source_by_id[source_id].source_class != binding.support.source_class
            for source_id in binding.source_ids
        ):
            raise ValueError(f"support binding {binding.scope_id} source class is inconsistent")
        if any(
            record.evidence_type not in allowed_evidence_types[binding.support.evidence_basis]
            for record in bound_evidence
        ):
            raise ValueError(f"support binding {binding.scope_id} evidence basis is inconsistent")
        bound_confirmations = tuple(
            confirmation_by_id[item] for item in binding.confirmation_event_ids
        )
        if binding.support.evidence_basis in confirmation_required and not bound_confirmations:
            raise ProspectiveInputScientificReviewRequired(
                f"support binding {binding.scope_id} lacks its required confirmation event"
            )
        if any(event.support != binding.support for event in bound_confirmations):
            raise ValueError(
                f"support binding {binding.scope_id} authority differs from confirmation"
            )
        if any(
            not set(event.evidence_refs).issubset(binding.evidence_record_ids)
            for event in bound_confirmations
        ):
            raise ValueError(
                f"support binding {binding.scope_id} confirmation/evidence relation is inconsistent"
            )
    required_artifact_kinds = {
        ProspectiveArtifactKind.SAMPLE_SHEET,
        ProspectiveArtifactKind.METHODS_DRAFT,
        ProspectiveArtifactKind.ID_CONVENTION,
    }
    kinds = {artifact.kind for artifact in artifacts}
    if not required_artifact_kinds.issubset(kinds):
        raise ProspectiveInputScientificReviewRequired(
            "prospective ledger must pin sample sheet, methods draft and ID convention artifacts"
        )


def build_prospective_input_ledger(
    *,
    request: V8DerivationInput,
    sources: tuple[SourceRecord, ...],
    evidence_records: tuple[EvidenceRecord, ...],
    confirmation_events: tuple[ConfirmationEvent, ...],
    artifacts: tuple[ProspectiveArtifact, ...],
    support_bindings: tuple[SupportEvidenceBinding, ...] = (),
) -> ProspectiveInputLedger:
    """Create one content-addressed ledger or raise a typed scientific blocker."""

    _require_ledger_closure(
        request=request,
        sources=sources,
        evidence_records=evidence_records,
        confirmation_events=confirmation_events,
        support_bindings=support_bindings,
        artifacts=artifacts,
    )
    fields: dict[str, Any] = {
        "request_payload": request.model_dump(mode="json"),
        "request_checksum": content_checksum(request.model_dump(mode="json")),
        "sources": sources,
        "evidence_records": evidence_records,
        "confirmation_events": confirmation_events,
        "support_bindings": support_bindings,
        "artifacts": artifacts,
    }
    draft = ProspectiveInputLedger.model_construct(
        ledger_id="PROSPECTIVE-LEDGER-PENDING",
        content_checksum="0" * 64,
        **fields,
    )
    checksum = content_checksum(
        draft.model_dump(mode="json", exclude={"ledger_id", "content_checksum"})
    )
    return ProspectiveInputLedger(
        ledger_id=f"PROSPECTIVE-LEDGER-{checksum[:20]}",
        content_checksum=checksum,
        **fields,
    )


class DeviationType(StrEnum):
    SUBSTITUTION = "SUBSTITUTION"
    EXCLUSION = "EXCLUSION"
    POOLING = "POOLING"
    LOST_SAMPLE = "LOST_SAMPLE"
    TREATMENT_CHANGE = "TREATMENT_CHANGE"
    OTHER_REVIEW_REQUIRED = "OTHER_REVIEW_REQUIRED"


class ReconciliationStatus(StrEnum):
    NO_RECORDED_DEVIATION = "NO_RECORDED_DEVIATION"
    DEVIATIONS_RECORDED = "DEVIATIONS_RECORDED"
    SCIENTIFIC_REVIEW_REQUIRED = "SCIENTIFIC_REVIEW_REQUIRED"


class DeviationRecord(KernelModel):
    deviation_id: NonBlankStr
    affected_query_ids: tuple[NonBlankStr, ...] = Field(min_length=1)
    field_path: NonBlankStr
    planned_value: KnowledgeValue[JsonValue]
    executed_value: KnowledgeValue[JsonValue]
    deviation_type: DeviationType
    evidence_refs: tuple[NonBlankStr, ...] = Field(min_length=1)
    rationale: NonBlankStr

    @model_validator(mode="after")
    def _values_are_distinct_and_supported(self) -> Self:
        if len(set(self.affected_query_ids)) != len(self.affected_query_ids):
            raise ValueError("affected_query_ids contains duplicates")
        if self.planned_value.model_dump(mode="json") == self.executed_value.model_dump(
            mode="json"
        ):
            raise ValueError("a deviation requires distinct planned and executed values")
        if not set(self.executed_value.evidence_ids).issubset(self.evidence_refs):
            raise ValueError("executed deviation evidence must be declared in evidence_refs")
        affected = set(self.affected_query_ids)
        for label, value in (
            ("planned_value", self.planned_value),
            ("executed_value", self.executed_value),
        ):
            if value.query_scope_id is not None and value.query_scope_id not in affected:
                raise ValueError(f"{label} query scope must be named in affected_query_ids")
        return self


class PlannedDesignRecord(KernelModel):
    plan_id: NonBlankStr
    content_checksum: Sha256
    experiment_block_id: NonBlankStr
    inferential_queries: tuple[InferentialQuery, ...] = Field(min_length=1)
    query_checksums: tuple[Sha256, ...] = Field(min_length=1)
    sources: tuple[SourceRecord, ...] = Field(min_length=1)
    evidence_records: tuple[EvidenceRecord, ...] = Field(min_length=1)
    confirmation_events: tuple[ConfirmationEvent, ...] = ()
    event_registry: EventRegistry
    count_records: tuple[CanonicalCountRecord, ...] = Field(min_length=1)
    sample_sheet_ref: NonBlankStr
    methods_draft_ref: NonBlankStr
    id_convention_ref: NonBlankStr
    user_confirmation_scopes: tuple[NonBlankStr, ...] = Field(min_length=1)

    @property
    def inferential_query_ids(self) -> tuple[str, ...]:
        return tuple(query.id for query in self.inferential_queries)

    @model_validator(mode="after")
    def _plan_contract(self) -> Self:
        if len(set(self.inferential_query_ids)) != len(self.inferential_query_ids):
            raise ValueError("inferential_query_ids contains duplicates")
        expected_query_checksums = tuple(
            content_checksum(query.model_dump(mode="json")) for query in self.inferential_queries
        )
        if self.query_checksums != expected_query_checksums:
            raise ValueError("query_checksums must pin each exact InferentialQuery snapshot")
        if len(set(self.user_confirmation_scopes)) != len(self.user_confirmation_scopes):
            raise ValueError("user_confirmation_scopes contains duplicates")
        source_identifiers = [source.source_id for source in self.sources]
        confirmation_identifiers = [event.event_id for event in self.confirmation_events]
        if len(set(source_identifiers)) != len(source_identifiers):
            raise ValueError("planned sources contain duplicate IDs")
        if len(set(confirmation_identifiers)) != len(confirmation_identifiers):
            raise ValueError("planned confirmations contain duplicate event IDs")
        if any(
            event.scope_id not in self.user_confirmation_scopes
            for event in self.confirmation_events
        ):
            raise ValueError("planned confirmation scope is not frozen in the plan")
        if any(source.source_context is not SourceContext.PLANNED for source in self.sources):
            raise ValueError("PlannedDesignRecord accepts only planned source context")
        source_ids = {source.source_id for source in self.sources}
        evidence_ids = {record.evidence_id for record in self.evidence_records}
        if len(evidence_ids) != len(self.evidence_records):
            raise ValueError("planned evidence records contain duplicate IDs")
        if any(record.source_id not in source_ids for record in self.evidence_records):
            raise ValueError("planned evidence references a source outside the plan")
        referenced = _referenced_evidence_ids(
            (self.inferential_queries, self.event_registry, self.count_records)
        )
        if not referenced.issubset(evidence_ids):
            raise ValueError("planned design has dangling evidence references")
        if any(
            not set(event.evidence_refs).issubset(evidence_ids)
            for event in self.confirmation_events
        ):
            raise ValueError("planned confirmation references evidence outside the plan")
        if any(
            event.experiment_block_id != self.experiment_block_id
            for event in self.event_registry.events
        ):
            raise ValueError("all planned events must reference experiment_block_id")
        if not self.event_registry.relative_timings:
            raise ValueError(
                "planned design requires event-referenced timing, including explicit UNKNOWN"
            )
        query_ids = set(self.inferential_query_ids)
        counts_by_query = {query_id: 0 for query_id in query_ids}
        for count in self.count_records:
            if count.kind is not CanonicalCountKind.PLANNED_UNIT_COUNT:
                raise ValueError("planned design counts must use planned_unit_count")
            if count.scope.query_id not in query_ids:
                raise ValueError("planned_unit_count scope must reference a plan query")
            counts_by_query[count.scope.query_id] += 1
            lifecycle = count.scope.lifecycle_phase
            if (
                lifecycle.knowledge_state is not KnowledgeState.PRESENT
                or lifecycle.value is not CountLifecyclePhase.PLANNED
            ):
                raise ValueError("planned_unit_count requires explicit planned lifecycle scope")
        if any(count != 1 for count in counts_by_query.values()):
            raise ValueError("each inferential query requires exactly one planned_unit_count")
        expected_checksum = _record_checksum(self)
        if self.content_checksum != expected_checksum:
            raise ValueError("planned design content checksum mismatch")
        if self.plan_id != f"PLAN-{expected_checksum[:20]}":
            raise ValueError("planned design ID must be derived from its content checksum")
        return self


class ExecutedDesignRecord(KernelModel):
    execution_id: NonBlankStr
    content_checksum: Sha256
    planned_design_id: NonBlankStr
    planned_design_checksum: Sha256
    experiment_block_id: NonBlankStr
    inferential_query_ids: tuple[NonBlankStr, ...] = Field(min_length=1)
    sources: tuple[SourceRecord, ...] = Field(min_length=1)
    evidence_records: tuple[EvidenceRecord, ...] = Field(min_length=1)
    confirmation_events: tuple[ConfirmationEvent, ...] = ()
    event_registry: EventRegistry
    count_records: tuple[CanonicalCountRecord, ...] = Field(min_length=1)
    deviations: KnowledgeValue[tuple[DeviationRecord, ...]]
    final_sample_sheet_ref: NonBlankStr
    execution_log_refs: tuple[NonBlankStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _execution_contract(self) -> Self:
        if len(set(self.inferential_query_ids)) != len(self.inferential_query_ids):
            raise ValueError("inferential_query_ids contains duplicates")
        source_identifiers = [source.source_id for source in self.sources]
        confirmation_identifiers = [event.event_id for event in self.confirmation_events]
        if len(set(source_identifiers)) != len(source_identifiers):
            raise ValueError("executed sources contain duplicate IDs")
        if len(set(confirmation_identifiers)) != len(confirmation_identifiers):
            raise ValueError("executed confirmations contain duplicate event IDs")
        if any(source.source_context is not SourceContext.EXECUTED for source in self.sources):
            raise ValueError("ExecutedDesignRecord accepts only executed source context")
        source_ids = {source.source_id for source in self.sources}
        evidence_ids = {record.evidence_id for record in self.evidence_records}
        if len(evidence_ids) != len(self.evidence_records):
            raise ValueError("executed evidence records contain duplicate IDs")
        if any(record.source_id not in source_ids for record in self.evidence_records):
            raise ValueError("executed evidence references a source outside the execution")
        referenced = _referenced_evidence_ids(
            (self.event_registry, self.count_records, self.deviations)
        )
        if not referenced.issubset(evidence_ids):
            raise ValueError("executed design has dangling evidence references")
        if any(
            not set(event.evidence_refs).issubset(evidence_ids)
            for event in self.confirmation_events
        ):
            raise ValueError("executed confirmation references evidence outside the execution")
        if any(
            event.experiment_block_id != self.experiment_block_id
            for event in self.event_registry.events
        ):
            raise ValueError("all executed events must reference experiment_block_id")
        query_ids = set(self.inferential_query_ids)
        for count in self.count_records:
            if count.kind is CanonicalCountKind.PLANNED_UNIT_COUNT:
                raise ValueError("executed design cannot restate planned_unit_count")
            if count.scope.query_id not in query_ids:
                raise ValueError("executed count scope must reference a plan query")
        if self.deviations.knowledge_state is KnowledgeState.PRESENT:
            if self.deviations.value is None:
                raise ValueError("present deviations require deviation records")
            for deviation in self.deviations.value:
                if not set(deviation.affected_query_ids).issubset(query_ids):
                    raise ValueError("deviation references a query outside the executed design")
        elif self.deviations.knowledge_state not in {
            KnowledgeState.ABSENT_EXPLICIT,
            KnowledgeState.UNKNOWN,
        }:
            raise ValueError("execution deviations must be present, explicitly absent or UNKNOWN")
        expected_checksum = _record_checksum(self)
        if self.content_checksum != expected_checksum:
            raise ValueError("executed design content checksum mismatch")
        if self.execution_id != f"EXECUTION-{expected_checksum[:20]}":
            raise ValueError("execution ID must be derived from its content checksum")
        return self


class PlanExecutionReconciliation(KernelModel):
    reconciliation_id: NonBlankStr
    content_checksum: Sha256
    planned_design_id: NonBlankStr
    planned_design_checksum: Sha256
    executed_design_id: NonBlankStr
    executed_design_checksum: Sha256
    status: ReconciliationStatus
    deviations: KnowledgeValue[tuple[DeviationRecord, ...]]
    review_requirement: ScientificReviewRequirement | None = None

    @model_validator(mode="after")
    def _reconciliation_contract(self) -> Self:
        expected_status = {
            KnowledgeState.PRESENT: ReconciliationStatus.DEVIATIONS_RECORDED,
            KnowledgeState.ABSENT_EXPLICIT: ReconciliationStatus.NO_RECORDED_DEVIATION,
            KnowledgeState.UNKNOWN: ReconciliationStatus.SCIENTIFIC_REVIEW_REQUIRED,
        }.get(self.deviations.knowledge_state)
        if expected_status is None:
            raise ValueError("reconciliation deviation state is unsupported")
        if self.status is not expected_status:
            raise ValueError("reconciliation status conflicts with deviation state")
        if self.status is ReconciliationStatus.SCIENTIFIC_REVIEW_REQUIRED:
            if (
                self.review_requirement is None
                or self.review_requirement.issue_id != COUNT_RECONCILIATION_REVIEW_ISSUE_ID
            ):
                raise ValueError("ambiguous count reconciliation requires SRR-V8-011")
        elif self.review_requirement is not None:
            raise ValueError("resolved reconciliation cannot carry a review requirement")
        expected_checksum = _record_checksum(self)
        if self.content_checksum != expected_checksum:
            raise ValueError("reconciliation content checksum mismatch")
        if self.reconciliation_id != f"RECONCILIATION-{expected_checksum[:20]}":
            raise ValueError("reconciliation ID must be derived from its content checksum")
        return self


def _record_checksum(record: KernelModel) -> str:
    return content_checksum(
        record.model_dump(
            mode="json",
            exclude={
                "plan_id",
                "execution_id",
                "reconciliation_id",
                "content_checksum",
            },
        )
    )


def _build_addressed[T: KernelModel](
    model: type[T],
    *,
    id_field: str,
    id_prefix: str,
    fields: dict[str, Any],
) -> T:
    draft_payload: Any = {
        **fields,
        id_field: f"{id_prefix}-PENDING",
        "content_checksum": "0" * 64,
    }
    draft = model.model_construct(**draft_payload)
    checksum = _record_checksum(draft)
    final_payload: Any = {
        **fields,
        id_field: f"{id_prefix}-{checksum[:20]}",
        "content_checksum": checksum,
    }
    return model.model_validate(final_payload)


def build_planned_design(
    *,
    experiment_block_id: str,
    inferential_queries: tuple[InferentialQuery, ...],
    sources: tuple[SourceRecord, ...],
    evidence_records: tuple[EvidenceRecord, ...],
    confirmation_events: tuple[ConfirmationEvent, ...],
    event_registry: EventRegistry,
    count_records: tuple[CanonicalCountRecord, ...],
    sample_sheet_ref: str,
    methods_draft_ref: str,
    id_convention_ref: str,
    user_confirmation_scopes: tuple[str, ...],
) -> PlannedDesignRecord:
    """Freeze one immutable, content-addressed prospective plan."""

    return _build_addressed(
        PlannedDesignRecord,
        id_field="plan_id",
        id_prefix="PLAN",
        fields={
            "experiment_block_id": experiment_block_id,
            "inferential_queries": inferential_queries,
            "query_checksums": tuple(
                content_checksum(query.model_dump(mode="json")) for query in inferential_queries
            ),
            "sources": sources,
            "evidence_records": evidence_records,
            "confirmation_events": confirmation_events,
            "event_registry": event_registry,
            "count_records": count_records,
            "sample_sheet_ref": sample_sheet_ref,
            "methods_draft_ref": methods_draft_ref,
            "id_convention_ref": id_convention_ref,
            "user_confirmation_scopes": user_confirmation_scopes,
        },
    )


def build_executed_design(
    *,
    planned_design: PlannedDesignRecord,
    sources: tuple[SourceRecord, ...],
    evidence_records: tuple[EvidenceRecord, ...],
    confirmation_events: tuple[ConfirmationEvent, ...],
    event_registry: EventRegistry,
    count_records: tuple[CanonicalCountRecord, ...],
    deviations: tuple[DeviationRecord, ...] | KnowledgeValue[tuple[DeviationRecord, ...]],
    final_sample_sheet_ref: str,
    execution_log_refs: tuple[str, ...],
) -> ExecutedDesignRecord:
    """Create a new execution linked to, but never overwriting, a frozen plan."""

    PlannedDesignRecord.model_validate(planned_design.model_dump(mode="python"))
    deviation_state: KnowledgeValue[tuple[DeviationRecord, ...]]
    if isinstance(deviations, KnowledgeValue):
        deviation_state = KnowledgeValue[tuple[DeviationRecord, ...]].model_validate(
            deviations.model_dump(mode="python")
        )
    elif deviations:
        deviation_state = KnowledgeValue[tuple[DeviationRecord, ...]](
            knowledge_state=KnowledgeState.PRESENT,
            value=deviations,
            evidence_ids=tuple(
                sorted({evidence for item in deviations for evidence in item.evidence_refs})
            ),
        )
    else:
        deviation_state = KnowledgeValue[tuple[DeviationRecord, ...]](
            knowledge_state=KnowledgeState.ABSENT_EXPLICIT,
            evidence_ids=tuple(record.evidence_id for record in evidence_records),
        )
    return _build_addressed(
        ExecutedDesignRecord,
        id_field="execution_id",
        id_prefix="EXECUTION",
        fields={
            "planned_design_id": planned_design.plan_id,
            "planned_design_checksum": planned_design.content_checksum,
            "experiment_block_id": planned_design.experiment_block_id,
            "inferential_query_ids": planned_design.inferential_query_ids,
            "sources": sources,
            "evidence_records": evidence_records,
            "confirmation_events": confirmation_events,
            "event_registry": event_registry,
            "count_records": count_records,
            "deviations": deviation_state,
            "final_sample_sheet_ref": final_sample_sheet_ref,
            "execution_log_refs": execution_log_refs,
        },
    )


def _count_comparison_scope(record: CanonicalCountRecord) -> str:
    return content_checksum(record.scope.model_dump(mode="json", exclude={"lifecycle_phase"}))


def _count_value_for_deviation(
    value: KnowledgeValue[Any],
) -> KnowledgeValue[JsonValue]:
    return KnowledgeValue[JsonValue].model_validate(value.model_dump(mode="python"))


def _declared_count_deviation(
    *,
    query_id: str,
    planned: CanonicalCountRecord,
    executed: CanonicalCountRecord,
    declarations: tuple[DeviationRecord, ...],
) -> DeviationRecord | None:
    candidates = tuple(
        item
        for item in declarations
        if query_id in item.affected_query_ids
        and executed.kind.value in item.field_path
        and item.planned_value.knowledge_state is planned.value.knowledge_state
        and item.executed_value.knowledge_state is executed.value.knowledge_state
        and item.planned_value.value == planned.value.value
        and item.executed_value.value == executed.value.value
    )
    if len(candidates) > 1:
        return None
    return candidates[0] if candidates else None


def _derived_count_differences(
    planned_design: PlannedDesignRecord,
    executed_design: ExecutedDesignRecord,
) -> tuple[tuple[DeviationRecord, ...], str | None]:
    declarations = executed_design.deviations.value or ()
    matched_declaration_ids: set[str] = set()
    differences: list[DeviationRecord] = []
    for planned in planned_design.count_records:
        comparable = tuple(
            executed
            for executed in executed_design.count_records
            if executed.scope.query_id == planned.scope.query_id
            and _count_comparison_scope(executed) == _count_comparison_scope(planned)
        )
        if not comparable:
            return (), (f"no execution count is comparable with planned count {planned.count_id}")
        for executed in comparable:
            if (
                planned.value.knowledge_state is not KnowledgeState.PRESENT
                or executed.value.knowledge_state is not KnowledgeState.PRESENT
                or planned.quantifier.value != "EXACT"
                or executed.quantifier.value != "EXACT"
            ):
                return (), (f"count comparison {planned.count_id}/{executed.count_id} is not exact")
            if planned.value.value == executed.value.value:
                continue
            declared = _declared_count_deviation(
                query_id=planned.scope.query_id,
                planned=planned,
                executed=executed,
                declarations=declarations,
            )
            if declared is not None:
                matched_declaration_ids.add(declared.deviation_id)
            evidence_refs = tuple(
                sorted(
                    {
                        *executed.source_evidence,
                        *executed.value.evidence_ids,
                        *(declared.evidence_refs if declared is not None else ()),
                    }
                )
            )
            field_path = (
                f"count_registry/{planned.scope.query_id}/{executed.kind.value}/{executed.count_id}"
            )
            identity = content_checksum(
                {
                    "field_path": field_path,
                    "planned": planned.value.model_dump(mode="json"),
                    "executed": executed.value.model_dump(mode="json"),
                }
            )
            differences.append(
                DeviationRecord(
                    deviation_id=f"DEVIATION-COUNT-{identity[:20]}",
                    affected_query_ids=(planned.scope.query_id,),
                    field_path=field_path,
                    planned_value=_count_value_for_deviation(planned.value),
                    executed_value=_count_value_for_deviation(executed.value),
                    deviation_type=(
                        declared.deviation_type
                        if declared is not None
                        else DeviationType.OTHER_REVIEW_REQUIRED
                    ),
                    evidence_refs=evidence_refs,
                    rationale=(
                        declared.rationale
                        if declared is not None
                        else "Executed count differs from the exact planned count."
                    ),
                )
            )
    if declarations and matched_declaration_ids != {item.deviation_id for item in declarations}:
        return (), "one or more declared deviations cannot be verified from comparable counts"
    return tuple(sorted(differences, key=lambda item: item.field_path)), None


def reconcile_plan_execution(
    planned_design: PlannedDesignRecord,
    executed_design: ExecutedDesignRecord,
) -> PlanExecutionReconciliation:
    """Produce an immutable diff for one exact plan/execution pair."""

    if executed_design.planned_design_id != planned_design.plan_id:
        raise ValueError("executed design references a different plan ID")
    if executed_design.planned_design_checksum != planned_design.content_checksum:
        raise ValueError("executed design references a different plan checksum")
    if executed_design.experiment_block_id != planned_design.experiment_block_id:
        raise ValueError("plan and execution use different experiment blocks")
    PlannedDesignRecord.model_validate(planned_design.model_dump(mode="python"))
    ExecutedDesignRecord.model_validate(executed_design.model_dump(mode="python"))
    review_rationale: str | None = None
    differences: tuple[DeviationRecord, ...] = ()
    if executed_design.deviations.knowledge_state is KnowledgeState.UNKNOWN:
        review_rationale = executed_design.deviations.rationale
    else:
        differences, review_rationale = _derived_count_differences(
            planned_design,
            executed_design,
        )
    if review_rationale is not None:
        status = ReconciliationStatus.SCIENTIFIC_REVIEW_REQUIRED
        deviation_state = KnowledgeValue[tuple[DeviationRecord, ...]](
            knowledge_state=KnowledgeState.UNKNOWN,
            rationale=review_rationale,
            claim_scope_id=f"RECONCILIATION-{planned_design.plan_id}",
        )
        review_requirement = ScientificReviewRequirement(
            issue_id=COUNT_RECONCILIATION_REVIEW_ISSUE_ID,
            rationale=review_rationale,
        )
    elif differences:
        status = ReconciliationStatus.DEVIATIONS_RECORDED
        deviation_state = KnowledgeValue[tuple[DeviationRecord, ...]](
            knowledge_state=KnowledgeState.PRESENT,
            value=differences,
            evidence_ids=tuple(sorted({ref for item in differences for ref in item.evidence_refs})),
        )
        review_requirement = None
    else:
        status = ReconciliationStatus.NO_RECORDED_DEVIATION
        deviation_state = KnowledgeValue[tuple[DeviationRecord, ...]](
            knowledge_state=KnowledgeState.ABSENT_EXPLICIT,
            evidence_ids=tuple(record.evidence_id for record in executed_design.evidence_records),
        )
        review_requirement = None
    return _build_addressed(
        PlanExecutionReconciliation,
        id_field="reconciliation_id",
        id_prefix="RECONCILIATION",
        fields={
            "planned_design_id": planned_design.plan_id,
            "planned_design_checksum": planned_design.content_checksum,
            "executed_design_id": executed_design.execution_id,
            "executed_design_checksum": executed_design.content_checksum,
            "status": status,
            "deviations": deviation_state,
            "review_requirement": review_requirement,
        },
    )


__all__ = [
    "COUNT_RECONCILIATION_REVIEW_ISSUE_ID",
    "INPUT_CLOSURE_REVIEW_ISSUE_ID",
    "DeviationRecord",
    "DeviationType",
    "ExecutedDesignRecord",
    "PlanExecutionReconciliation",
    "PlannedDesignRecord",
    "ProspectiveArtifact",
    "ProspectiveArtifactKind",
    "ProspectiveInputLedger",
    "ProspectiveInputScientificReviewRequired",
    "ReconciliationStatus",
    "SupportBindingScope",
    "SupportEvidenceBinding",
    "build_executed_design",
    "build_planned_design",
    "build_prospective_artifact",
    "build_prospective_input_ledger",
    "reconcile_plan_execution",
]
