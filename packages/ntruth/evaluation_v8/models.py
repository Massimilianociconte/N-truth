"""Fail-closed PRD v8 contracts for end-to-end and residual evaluation.

These models describe deterministic comparisons and the evidence needed to
interpret them.  They do not contain release thresholds and a conformance
reference can never be promoted to scientific evidence.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Self

from pydantic import Field, model_validator

from ntruth.schemas.claims import DeterminabilityState
from ntruth.schemas.core import content_checksum
from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.support import ScientificReviewRequirement

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

EVALUATION_REFERENCE_REVIEW_ISSUE_ID = "SRR-V8-EVAL-REFERENCE"
EVALUATION_SCIENTIFIC_HOLD_ISSUE_ID = "SRR-V8-EVAL-SCIENTIFIC-HOLD"
CONFORMANCE_REFERENCE_REVIEW_ISSUE_ID = "SRR-V8-CONFORMANCE-REFERENCE-NONSCIENTIFIC"
REFERENCE_STABILITY_REVIEW_ISSUE_ID = "SRR-V8-REFERENCE-STABILITY"
PARTIAL_CLAIM_MATCH_REVIEW_ISSUE_ID = "SRR-V8-PARTIAL-CLAIM-MATCH"
EVALUATION_PROCESS_METRICS_REVIEW_ISSUE_ID = "SRR-V8-EVAL-PROCESS-METRICS"


class FalseCertaintyCategory(StrEnum):
    """Operational categories from PRD v8 §24.3."""

    EU_OR_COUNT_ERROR = "EU_OR_COUNT_ERROR"
    DECISIVE_PRECONDITION_UNSUPPORTED = "DECISIVE_PRECONDITION_UNSUPPORTED"
    MATERIAL_SCENARIO_OMITTED = "MATERIAL_SCENARIO_OMITTED"
    HIDDEN_CONFLICT = "HIDDEN_CONFLICT"
    PROFILE_COVERAGE_UNDECLARED = "PROFILE_COVERAGE_UNDECLARED"
    INFERENCE_OR_ESTIMAND_SCOPE_OVERREACH = "INFERENCE_OR_ESTIMAND_SCOPE_OVERREACH"
    ADEQUACY_UNSUPPORTED_POSITIVE = "ADEQUACY_UNSUPPORTED_POSITIVE"


class ResidualOrigin(StrEnum):
    PARSER = "PARSER"
    VERIFIER = "VERIFIER"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    DERIVATION_THEORY = "DERIVATION_THEORY"
    RULEBOOK = "RULEBOOK"
    REPORT_ASSEMBLY = "REPORT_ASSEMBLY"
    REFERENCE_UNCERTAINTY = "REFERENCE_UNCERTAINTY"


class ResidualSeverity(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    LOW = "LOW"


class AbstentionDisposition(StrEnum):
    RESOLVED = "RESOLVED"
    ACTIONABLE_ABSTENTION = "ACTIONABLE_ABSTENTION"
    UNRESOLVED_RISK_DETECTED = "UNRESOLVED_RISK_DETECTED"
    UNACTIONABLE_ABSTENTION = "UNACTIONABLE_ABSTENTION"
    FALSE_CERTAINTY = "FALSE_CERTAINTY"
    NOT_EVALUABLE_MISSING_OUTPUT = "NOT_EVALUABLE_MISSING_OUTPUT"


class MatchOutcome(StrEnum):
    EXACT = "EXACT"
    PARTIAL = "PARTIAL"
    INCORRECT = "INCORRECT"
    MISSING = "MISSING"
    UNEXPECTED = "UNEXPECTED"


class EvaluationStatus(StrEnum):
    BLOCKED = "BLOCKED"
    CONFORMANCE_ONLY = "CONFORMANCE_ONLY"
    EVALUATED_WITH_INDEPENDENT_REFERENCE = "EVALUATED_WITH_INDEPENDENT_REFERENCE"


class IndependentReferencePurpose(StrEnum):
    CONFORMANCE_ONLY = "CONFORMANCE_ONLY"
    INDEPENDENT_EVALUATION = "INDEPENDENT_EVALUATION"


class ResidualDimension(StrEnum):
    COMPLETE_REPORT = "COMPLETE_REPORT"
    GLOBAL_REPORT_RESOLUTION = "GLOBAL_REPORT_RESOLUTION"
    QUERY_MEMBERSHIP = "QUERY_MEMBERSHIP"
    QUERY_REPORT_RESOLUTION = "QUERY_REPORT_RESOLUTION"
    CLAIM_SEMANTICS = "CLAIM_SEMANTICS"
    ADEQUACY_AXIS = "ADEQUACY_AXIS"
    EVIDENCE_CORRECTNESS = "EVIDENCE_CORRECTNESS"
    PROOF_CORRECTNESS = "PROOF_CORRECTNESS"


class ResidualScopeKind(StrEnum):
    REPORT = "REPORT"
    QUERY = "QUERY"
    CLAIM = "CLAIM"
    ADEQUACY_AXIS = "ADEQUACY_AXIS"


class FalseCertaintyDenominatorScope(StrEnum):
    DECISIVE_REFERENCE_CLAIMS = "DECISIVE_REFERENCE_CLAIMS"


class QuestionAttributionSnapshot(KernelModel):
    """Query-owned question whose claim attribution stays open-world until reviewed."""

    query_id: NonBlankStr
    question_id: NonBlankStr
    claim_ids: KnowledgeValue[tuple[NonBlankStr, ...]]

    @model_validator(mode="after")
    def _query_scoped(self) -> Self:
        if self.claim_ids.query_scope_id != self.query_id:
            raise ValueError("question attribution must retain the exact query scope")
        return self


class FalseCertaintySummary(KernelModel):
    scope: FalseCertaintyDenominatorScope
    denominator: int = Field(ge=1)
    event_count: int = Field(ge=0)
    severity: KnowledgeValue[tuple[ResidualSeverity, ...]]

    @model_validator(mode="after")
    def _bounded_and_scoped(self) -> Self:
        if self.event_count > self.denominator:
            raise ValueError("false-certainty event count exceeds its preregistered denominator")
        return self


class TimeToConfirmedReportObservation(KernelModel):
    report_seconds: Decimal = Field(ge=Decimal("0"))
    manual_baseline_seconds: Decimal = Field(ge=Decimal("0"))


class QuestionUsefulnessObservation(KernelModel):
    query_id: NonBlankStr
    question_id: NonBlankStr
    reviewer_actor_ids: tuple[NonBlankStr, ...] = Field(min_length=2)
    answerable: KnowledgeValue[bool]
    relevance: KnowledgeValue[int]
    scenario_resolved: KnowledgeValue[bool]
    output_changing: KnowledgeValue[bool]
    redundant: KnowledgeValue[bool]
    recipient_correct: KnowledgeValue[bool]
    response_time_seconds: KnowledgeValue[Decimal]
    evidence_requested: KnowledgeValue[tuple[NonBlankStr, ...]]
    remaining_scenario_coverage: KnowledgeValue[NonBlankStr]

    @model_validator(mode="after")
    def _independently_reviewed_and_query_scoped(self) -> Self:
        if len(set(self.reviewer_actor_ids)) != len(self.reviewer_actor_ids):
            raise ValueError("question usefulness requires distinct independent reviewers")
        for label, value in (
            ("answerable", self.answerable),
            ("relevance", self.relevance),
            ("scenario_resolved", self.scenario_resolved),
            ("output_changing", self.output_changing),
            ("redundant", self.redundant),
            ("recipient_correct", self.recipient_correct),
            ("response_time_seconds", self.response_time_seconds),
            ("evidence_requested", self.evidence_requested),
            ("remaining_scenario_coverage", self.remaining_scenario_coverage),
        ):
            if value.query_scope_id != self.query_id:
                raise ValueError(f"question usefulness {label} has the wrong query scope")
        if self.relevance.knowledge_state is KnowledgeState.PRESENT and not (
            1 <= int(self.relevance.value or 0) <= 5
        ):
            raise ValueError("question usefulness relevance must be between 1 and 5")
        return self


class EvaluationProcessObservations(KernelModel):
    report_scope_id: NonBlankStr
    time_to_confirmed_report: KnowledgeValue[TimeToConfirmedReportObservation]
    decisive_human_correction_count: KnowledgeValue[int]
    question_usefulness: KnowledgeValue[tuple[QuestionUsefulnessObservation, ...]]

    @model_validator(mode="after")
    def _report_scoped(self) -> Self:
        for label, value in (
            ("time_to_confirmed_report", self.time_to_confirmed_report),
            ("decisive_human_correction_count", self.decisive_human_correction_count),
            ("question_usefulness", self.question_usefulness),
        ):
            if value.query_scope_id != self.report_scope_id:
                raise ValueError(f"process observation {label} has the wrong report scope")
        return self


class PartialClaimEquivalence(KernelModel):
    """One reviewed, evidence-backed partial-equivalence decision."""

    query_id: NonBlankStr
    reference_claim_id: NonBlankStr
    accepted_observed_semantic_checksum: Sha256
    rationale: NonBlankStr
    evidence_ids: tuple[NonBlankStr, ...] = Field(min_length=1)


class AdequacyAxisSnapshot(KernelModel):
    query_id: NonBlankStr
    axis_id: NonBlankStr
    outcome_checksum: Sha256


class ClaimEvaluationSnapshot(KernelModel):
    """Comparison-safe projection of one complete, query-scoped claim."""

    query_id: NonBlankStr
    claim_id: NonBlankStr
    decisive: KnowledgeValue[bool]
    semantic_value_checksum: Sha256
    determinability_state: DeterminabilityState
    evidence_record_ids: KnowledgeValue[tuple[NonBlankStr, ...]]
    evidence_content_checksum: KnowledgeValue[Sha256]
    proof_trace_checksum: Sha256
    unresolved_risk_ids: KnowledgeValue[tuple[NonBlankStr, ...]]
    actionable_question_ids: KnowledgeValue[tuple[NonBlankStr, ...]]
    false_certainty_categories: KnowledgeValue[tuple[FalseCertaintyCategory, ...]]

    @model_validator(mode="after")
    def _open_world_abstention_contract(self) -> Self:
        for label, value in (
            ("decisive", self.decisive),
            ("evidence_record_ids", self.evidence_record_ids),
            ("evidence_content_checksum", self.evidence_content_checksum),
            ("unresolved_risk_ids", self.unresolved_risk_ids),
            ("actionable_question_ids", self.actionable_question_ids),
            ("false_certainty_categories", self.false_certainty_categories),
        ):
            if value.claim_scope_id != self.claim_id:
                raise ValueError(f"{label} must retain the exact claim scope")
        if self.evidence_record_ids.knowledge_state is KnowledgeState.PRESENT and set(
            self.evidence_record_ids.value or ()
        ) != set(self.evidence_record_ids.evidence_ids):
            raise ValueError("evidence-record projection must be self-addressing")
        is_resolved = self.determinability_state is DeterminabilityState.DETERMINATE
        for label, value in (
            ("unresolved_risk_ids", self.unresolved_risk_ids),
            ("actionable_question_ids", self.actionable_question_ids),
        ):
            if is_resolved and value.knowledge_state is not KnowledgeState.NOT_APPLICABLE:
                raise ValueError(f"resolved claim requires {label}=NOT_APPLICABLE")
            if not is_resolved and value.knowledge_state is KnowledgeState.NOT_APPLICABLE:
                raise ValueError(f"unresolved claim cannot mark {label} NOT_APPLICABLE")
        return self


class QueryEvaluationSnapshot(KernelModel):
    query_id: NonBlankStr
    report_resolution_checksum: Sha256
    claims: tuple[ClaimEvaluationSnapshot, ...] = Field(min_length=1)
    adequacy_axes: tuple[AdequacyAxisSnapshot, ...] = Field(min_length=1)
    question_attributions: tuple[QuestionAttributionSnapshot, ...] = ()

    @model_validator(mode="after")
    def _one_query_complete(self) -> Self:
        if any(claim.query_id != self.query_id for claim in self.claims):
            raise ValueError("query snapshot contains a claim from another query")
        if any(axis.query_id != self.query_id for axis in self.adequacy_axes):
            raise ValueError("query snapshot contains an adequacy axis from another query")
        if any(item.query_id != self.query_id for item in self.question_attributions):
            raise ValueError("query snapshot contains a question from another query")
        claim_ids = [claim.claim_id for claim in self.claims]
        if len(set(claim_ids)) != len(claim_ids):
            raise ValueError("query snapshot contains duplicate claim IDs")
        axis_ids = [axis.axis_id for axis in self.adequacy_axes]
        if len(set(axis_ids)) != len(axis_ids):
            raise ValueError("query snapshot contains duplicate adequacy axes")
        question_ids = [item.question_id for item in self.question_attributions]
        if len(set(question_ids)) != len(question_ids):
            raise ValueError("query snapshot contains duplicate question attributions")
        known_claim_ids = set(claim_ids)
        for item in self.question_attributions:
            if item.claim_ids.knowledge_state is KnowledgeState.PRESENT and not set(
                item.claim_ids.value or ()
            ).issubset(known_claim_ids):
                raise ValueError("question attribution references a claim outside its query")
        return self


class ReportEvaluationSnapshot(KernelModel):
    snapshot_id: NonBlankStr
    content_checksum: Sha256
    report_id: NonBlankStr
    report_checksum: Sha256
    global_report_resolution_checksum: Sha256
    query_snapshots: tuple[QueryEvaluationSnapshot, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _content_addressed_complete_report(self) -> Self:
        query_ids = [query.query_id for query in self.query_snapshots]
        if len(set(query_ids)) != len(query_ids):
            raise ValueError("report evaluation snapshot contains duplicate query IDs")
        expected = content_checksum(
            self.model_dump(mode="json", exclude={"snapshot_id", "content_checksum"})
        )
        if self.content_checksum != expected:
            raise ValueError("report evaluation snapshot checksum mismatch")
        if self.snapshot_id != f"EVAL-SNAPSHOT-{expected[:20]}":
            raise ValueError("report evaluation snapshot ID mismatch")
        return self


class ReferenceStabilityArtifactReference(KernelModel):
    artifact_id: NonBlankStr
    content_checksum: Sha256
    report_scope_id: NonBlankStr


class IndependentReportReference(KernelModel):
    reference_id: NonBlankStr
    content_checksum: Sha256
    purpose: IndependentReferencePurpose
    report_scope_id: NonBlankStr
    snapshot: ReportEvaluationSnapshot
    source_record_ids: tuple[NonBlankStr, ...] = Field(min_length=1)
    evidence_ids: tuple[NonBlankStr, ...] = Field(min_length=1)
    reviewer_actor_ids: tuple[NonBlankStr, ...] = Field(min_length=1)
    reference_stability_report: KnowledgeValue[ReferenceStabilityArtifactReference]
    partial_claim_equivalences: KnowledgeValue[tuple[PartialClaimEquivalence, ...]]

    @model_validator(mode="after")
    def _content_addressed_reference(self) -> Self:
        if len(set(self.reviewer_actor_ids)) != len(self.reviewer_actor_ids):
            raise ValueError("independent reference contains duplicate reviewers")
        if self.snapshot.report_id != self.report_scope_id:
            raise ValueError("independent reference has the wrong report scope")
        for label, value in (
            ("reference_stability_report", self.reference_stability_report),
            ("partial_claim_equivalences", self.partial_claim_equivalences),
        ):
            if value.query_scope_id != self.report_scope_id:
                raise ValueError(f"{label} must retain the exact report scope")
        if self.purpose is IndependentReferencePurpose.CONFORMANCE_ONLY:
            if self.reference_stability_report.knowledge_state is not KnowledgeState.NOT_APPLICABLE:
                raise ValueError("conformance reference cannot assert reference stability")
            if self.partial_claim_equivalences.knowledge_state is not KnowledgeState.NOT_APPLICABLE:
                raise ValueError("conformance reference uses exact matching, not partial policy")
        elif self.reference_stability_report.knowledge_state not in {
            KnowledgeState.PRESENT,
            KnowledgeState.UNKNOWN,
        }:
            raise ValueError("independent reference must address reference-stability evidence")
        elif self.partial_claim_equivalences.knowledge_state not in {
            KnowledgeState.PRESENT,
            KnowledgeState.ABSENT_EXPLICIT,
            KnowledgeState.UNKNOWN,
        }:
            raise ValueError("independent reference must address partial-claim equivalence")
        if self.reference_stability_report.knowledge_state is KnowledgeState.PRESENT and not set(
            self.reference_stability_report.evidence_ids
        ).issubset(set(self.evidence_ids)):
            raise ValueError("reference-stability pin has dangling evidence IDs")
        if (
            self.reference_stability_report.knowledge_state is KnowledgeState.PRESENT
            and self.reference_stability_report.value is not None
            and self.reference_stability_report.value.report_scope_id != self.report_scope_id
        ):
            raise ValueError("reference-stability artifact reference has the wrong report scope")
        if self.partial_claim_equivalences.knowledge_state is KnowledgeState.PRESENT:
            known_queries = {
                query.query_id: {claim.claim_id for claim in query.claims}
                for query in self.snapshot.query_snapshots
            }
            identities: set[tuple[str, str, str]] = set()
            for equivalence in self.partial_claim_equivalences.value or ():
                if not set(equivalence.evidence_ids).issubset(set(self.evidence_ids)):
                    raise ValueError("partial equivalence has dangling evidence IDs")
                if equivalence.reference_claim_id not in known_queries.get(
                    equivalence.query_id, set()
                ):
                    raise ValueError("partial equivalence references an unknown reference claim")
                identity = (
                    equivalence.query_id,
                    equivalence.reference_claim_id,
                    equivalence.accepted_observed_semantic_checksum,
                )
                if identity in identities:
                    raise ValueError("duplicate partial claim equivalence")
                identities.add(identity)
            if not set(self.partial_claim_equivalences.evidence_ids).issubset(
                set(self.evidence_ids)
            ):
                raise ValueError("partial-equivalence ledger has dangling evidence IDs")
        expected = content_checksum(self.model_dump(mode="json", exclude={"content_checksum"}))
        if self.content_checksum != expected:
            raise ValueError("independent reference checksum mismatch")
        return self


class EvaluationDenominators(KernelModel):
    report_count: int = Field(ge=1, le=1)
    query_count: int = Field(ge=1)
    missing_query_count: int = Field(ge=0)
    unexpected_query_count: int = Field(ge=0)
    global_report_resolution_count: int = Field(ge=1, le=1)
    claim_count: int = Field(ge=1)
    decisive_claim_count: KnowledgeValue[int]
    adequacy_axis_count: int = Field(ge=1)
    evidence_correctness_count: int = Field(ge=1)
    proof_correctness_count: int = Field(ge=1)


class MatchSummary(KernelModel):
    denominator: int = Field(ge=1)
    unexpected_count: int = Field(ge=0)
    by_outcome: dict[MatchOutcome, int]

    @model_validator(mode="after")
    def _closed_partition(self) -> Self:
        expected = set(MatchOutcome)
        if set(self.by_outcome) != expected:
            raise ValueError("match summary must retain every outcome category")
        if any(value < 0 for value in self.by_outcome.values()):
            raise ValueError("match counts cannot be negative")
        reference_partition = sum(
            value
            for outcome, value in self.by_outcome.items()
            if outcome is not MatchOutcome.UNEXPECTED
        )
        if reference_partition != self.denominator:
            raise ValueError("match outcome counts do not equal the reference denominator")
        if self.by_outcome[MatchOutcome.UNEXPECTED] != self.unexpected_count:
            raise ValueError("unexpected count differs from outcome partition")
        return self


class QueryEvaluationResult(KernelModel):
    query_id: NonBlankStr
    report_resolution_match: bool
    claim_match: MatchSummary
    decisive_claim_match: KnowledgeValue[MatchSummary]
    adequacy_axis_match: MatchSummary
    evidence_correctness: MatchSummary
    proof_correctness: MatchSummary
    abstention_dispositions: dict[AbstentionDisposition, int]
    false_certainty_claim_ids: tuple[NonBlankStr, ...]

    @model_validator(mode="after")
    def _complete_abstention_partition(self) -> Self:
        if set(self.abstention_dispositions) != set(AbstentionDisposition):
            raise ValueError("abstention result must retain every disposition")
        if sum(self.abstention_dispositions.values()) != self.claim_match.denominator:
            raise ValueError("abstention counts do not equal the claim denominator")
        if len(set(self.false_certainty_claim_ids)) != len(self.false_certainty_claim_ids):
            raise ValueError("false-certainty claim IDs contain duplicates")
        if (
            len(self.false_certainty_claim_ids)
            != self.abstention_dispositions[AbstentionDisposition.FALSE_CERTAINTY]
        ):
            raise ValueError("false-certainty claim IDs differ from the abstention partition")
        if (
            self.decisive_claim_match.knowledge_state is KnowledgeState.PRESENT
            and self.decisive_claim_match.value is not None
            and self.decisive_claim_match.value.denominator > self.claim_match.denominator
        ):
            raise ValueError("decisive claim denominator exceeds the complete claim denominator")
        return self


class ResidualEvent(KernelModel):
    residual_id: NonBlankStr
    dimension: ResidualDimension
    scope_kind: ResidualScopeKind
    scope_id: NonBlankStr
    query_id: NonBlankStr | None = None
    claim_id: NonBlankStr | None = None
    axis_id: NonBlankStr | None = None
    match_outcome: MatchOutcome
    false_certainty_category: KnowledgeValue[FalseCertaintyCategory]
    origin: KnowledgeValue[ResidualOrigin]
    severity: KnowledgeValue[ResidualSeverity]
    impact_on_claim: NonBlankStr


class EndToEndEvaluationReport(KernelModel):
    evaluation_id: NonBlankStr
    content_checksum: Sha256
    report_scope_id: NonBlankStr
    observed_snapshot_checksum: Sha256
    reference_checksum: KnowledgeValue[Sha256]
    status: EvaluationStatus
    scientific_use_permitted: bool
    denominators: KnowledgeValue[EvaluationDenominators]
    complete_report_match: KnowledgeValue[bool]
    global_report_resolution_match: KnowledgeValue[bool]
    query_results: KnowledgeValue[tuple[QueryEvaluationResult, ...]]
    residuals: KnowledgeValue[tuple[ResidualEvent, ...]]
    false_certainty: KnowledgeValue[FalseCertaintySummary]
    time_to_confirmed_report_seconds: KnowledgeValue[Decimal]
    review_time_delta_seconds: KnowledgeValue[Decimal]
    decisive_human_correction_count: KnowledgeValue[int]
    question_usefulness: KnowledgeValue[tuple[QuestionUsefulnessObservation, ...]]
    blockers: tuple[ScientificReviewRequirement, ...]

    @model_validator(mode="after")
    def _blocked_states_are_not_numeric_results(self) -> Self:
        for label, value in (
            ("reference_checksum", self.reference_checksum),
            ("denominators", self.denominators),
            ("complete_report_match", self.complete_report_match),
            ("global_report_resolution_match", self.global_report_resolution_match),
            ("query_results", self.query_results),
            ("residuals", self.residuals),
            ("false_certainty", self.false_certainty),
            ("time_to_confirmed_report_seconds", self.time_to_confirmed_report_seconds),
            ("review_time_delta_seconds", self.review_time_delta_seconds),
            ("decisive_human_correction_count", self.decisive_human_correction_count),
            ("question_usefulness", self.question_usefulness),
        ):
            if value.query_scope_id != self.report_scope_id:
                raise ValueError(f"evaluation {label} has the wrong report scope")
        blocker_ids = {blocker.issue_id for blocker in self.blockers}
        if self.denominators.knowledge_state is KnowledgeState.PRESENT:
            denominator_value = self.denominators.value
            if (
                denominator_value is None
                or denominator_value.decisive_claim_count.query_scope_id != self.report_scope_id
            ):
                raise ValueError("decisive claim denominator has the wrong report scope")
        if self.scientific_use_permitted:
            raise ValueError("deterministic evaluation is not a scientific release authority")
        if self.status is EvaluationStatus.BLOCKED:
            if self.denominators.knowledge_state is KnowledgeState.PRESENT:
                raise ValueError("blocked evaluation cannot fabricate denominators")
            if self.query_results.knowledge_state is KnowledgeState.PRESENT:
                raise ValueError("blocked evaluation cannot fabricate query results")
            if self.complete_report_match.knowledge_state is KnowledgeState.PRESENT:
                raise ValueError("blocked evaluation cannot fabricate complete-report match")
            if self.global_report_resolution_match.knowledge_state is KnowledgeState.PRESENT:
                raise ValueError("blocked evaluation cannot fabricate report-resolution match")
            if EVALUATION_REFERENCE_REVIEW_ISSUE_ID not in blocker_ids:
                raise ValueError("blocked evaluation requires the missing-reference blocker")
        if (
            self.status is EvaluationStatus.CONFORMANCE_ONLY
            and CONFORMANCE_REFERENCE_REVIEW_ISSUE_ID not in blocker_ids
        ):
            raise ValueError("conformance evaluation requires the nonscientific fixture blocker")
        if (
            self.status is EvaluationStatus.EVALUATED_WITH_INDEPENDENT_REFERENCE
            and EVALUATION_SCIENTIFIC_HOLD_ISSUE_ID not in blocker_ids
        ):
            raise ValueError("independent evaluation requires the scientific HOLD blocker")
        process_values = (
            self.time_to_confirmed_report_seconds,
            self.review_time_delta_seconds,
            self.decisive_human_correction_count,
            self.question_usefulness,
        )
        if (
            any(value.knowledge_state is not KnowledgeState.PRESENT for value in process_values)
            and EVALUATION_PROCESS_METRICS_REVIEW_ISSUE_ID not in blocker_ids
        ):
            raise ValueError("unclosed process metrics require their scientific-review blocker")
        expected = content_checksum(
            self.model_dump(mode="json", exclude={"evaluation_id", "content_checksum"})
        )
        if self.content_checksum != expected:
            raise ValueError("end-to-end evaluation checksum mismatch")
        if self.evaluation_id != f"E2E-{expected[:20]}":
            raise ValueError("end-to-end evaluation ID mismatch")
        return self


class AuditRole(StrEnum):
    ORIGINAL_ANNOTATOR = "ORIGINAL_ANNOTATOR"
    ORIGINAL_REVIEWER = "ORIGINAL_REVIEWER"
    ADJUDICATOR = "ADJUDICATOR"
    REPORT_GENERATOR = "REPORT_GENERATOR"
    RESIDUAL_AUDITOR = "RESIDUAL_AUDITOR"


class AuditRoleAssignment(KernelModel):
    actor_id: NonBlankStr
    role: AuditRole


class ResidualAuditStratum(StrEnum):
    SUPPORT_GRADE = "SUPPORT_GRADE"
    DETERMINABILITY_STATE = "DETERMINABILITY_STATE"
    COMPLEXITY_TIER = "COMPLEXITY_TIER"
    SOURCE_CLASS = "SOURCE_CLASS"
    LAB_OR_ARTICLE_LINEAGE = "LAB_OR_ARTICLE_LINEAGE"
    CLAIM_TYPE = "CLAIM_TYPE"


class ResidualAuditSampleItem(KernelModel):
    report_id: NonBlankStr
    query_id: NonBlankStr
    claim_id: NonBlankStr
    reference_id: NonBlankStr

    @property
    def identity(self) -> tuple[str, str, str, str]:
        return (self.report_id, self.query_id, self.claim_id, self.reference_id)


class BlindResidualAuditProtocol(KernelModel):
    protocol_id: NonBlankStr
    sample_manifest_checksum: Sha256
    sample_items: tuple[ResidualAuditSampleItem, ...] = Field(min_length=1)
    strata: tuple[ResidualAuditStratum, ...] = Field(min_length=6, max_length=6)
    blind_to_original_output: bool
    role_assignments: tuple[AuditRoleAssignment, ...] = Field(min_length=5)
    evidence_ids: tuple[NonBlankStr, ...] = Field(min_length=1)

    @property
    def residual_auditor_ids(self) -> tuple[str, ...]:
        return tuple(
            assignment.actor_id
            for assignment in self.role_assignments
            if assignment.role is AuditRole.RESIDUAL_AUDITOR
        )

    @property
    def report_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item.report_id for item in self.sample_items))

    @property
    def claim_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item.claim_id for item in self.sample_items))

    @property
    def reference_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item.reference_id for item in self.sample_items))

    @model_validator(mode="after")
    def _blind_and_separated(self) -> Self:
        if not self.blind_to_original_output:
            raise ValueError("residual audit must be blind to the original output")
        if set(self.strata) != set(ResidualAuditStratum):
            raise ValueError("residual audit requires the complete Appendix H.3 strata")
        sample_identities = [item.identity for item in self.sample_items]
        if len(set(sample_identities)) != len(sample_identities):
            raise ValueError("residual audit contains duplicate exact sample identities")
        role_set = {assignment.role for assignment in self.role_assignments}
        if role_set != set(AuditRole):
            raise ValueError("residual audit requires every protocol role")
        identities = [
            (assignment.actor_id, assignment.role) for assignment in self.role_assignments
        ]
        if len(set(identities)) != len(identities):
            raise ValueError("residual audit contains duplicate role assignments")
        by_role = {
            role: {
                assignment.actor_id
                for assignment in self.role_assignments
                if assignment.role is role
            }
            for role in AuditRole
        }
        auditors = by_role[AuditRole.RESIDUAL_AUDITOR]
        involved = set().union(
            *(actors for role, actors in by_role.items() if role is not AuditRole.RESIDUAL_AUDITOR)
        )
        if auditors & involved:
            raise ValueError(
                "residual auditor must be a reviewer not involved in the original work"
            )
        return self


class AuditCountSummary(KernelModel):
    numerator: int = Field(ge=0)
    denominator: int = Field(ge=1)

    @model_validator(mode="after")
    def _bounded_count(self) -> Self:
        if self.numerator > self.denominator:
            raise ValueError("audit numerator cannot exceed denominator")
        return self


class ResidualAuditFinding(KernelModel):
    finding_id: NonBlankStr
    report_id: NonBlankStr
    query_id: NonBlankStr
    claim_id: NonBlankStr
    reference_id: NonBlankStr
    decisive_error: KnowledgeValue[bool]
    false_certainty: KnowledgeValue[bool]
    human_review_introduced_error: KnowledgeValue[bool]
    origin: KnowledgeValue[ResidualOrigin]
    severity: KnowledgeValue[ResidualSeverity]
    stratum_values: dict[ResidualAuditStratum, NonBlankStr]
    impact_on_claim: KnowledgeValue[NonBlankStr]
    evidence_ids: tuple[NonBlankStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _claim_scoped_and_stratified(self) -> Self:
        if set(self.stratum_values) != set(ResidualAuditStratum):
            raise ValueError("residual finding requires every Appendix H.3 stratum")
        for label, value in (
            ("decisive_error", self.decisive_error),
            ("false_certainty", self.false_certainty),
            ("human_review_introduced_error", self.human_review_introduced_error),
            ("origin", self.origin),
            ("severity", self.severity),
            ("impact_on_claim", self.impact_on_claim),
        ):
            if value.claim_scope_id != self.claim_id:
                raise ValueError(f"residual {label} must retain the exact claim scope")
            if not set(value.evidence_ids).issubset(set(self.evidence_ids)):
                raise ValueError(f"residual {label} has dangling evidence IDs")
        return self


class BlindResidualAuditResult(KernelModel):
    result_id: NonBlankStr
    content_checksum: Sha256
    protocol: BlindResidualAuditProtocol
    findings: tuple[ResidualAuditFinding, ...] = Field(min_length=1)
    decisive_error_count: KnowledgeValue[AuditCountSummary]
    false_certainty_count: KnowledgeValue[AuditCountSummary]
    human_review_introduced_error_count: KnowledgeValue[AuditCountSummary]
    scientific_use_permitted: bool = False
    blocker: ScientificReviewRequirement

    @model_validator(mode="after")
    def _closed_sample_and_content(self) -> Self:
        finding_identities = [
            (finding.report_id, finding.query_id, finding.claim_id, finding.reference_id)
            for finding in self.findings
        ]
        expected_identities = [item.identity for item in self.protocol.sample_items]
        if len(set(finding_identities)) != len(finding_identities) or set(
            finding_identities
        ) != set(expected_identities):
            raise ValueError("residual findings do not close the exact blinded sample identity")
        for finding_field, summary in (
            ("decisive_error", self.decisive_error_count),
            ("false_certainty", self.false_certainty_count),
            ("human_review_introduced_error", self.human_review_introduced_error_count),
        ):
            values = [getattr(finding, finding_field) for finding in self.findings]
            if all(value.knowledge_state is KnowledgeState.PRESENT for value in values):
                expected_numerator = sum(bool(value.value) for value in values)
                if (
                    summary.knowledge_state is not KnowledgeState.PRESENT
                    or summary.value is None
                    or summary.value.numerator != expected_numerator
                    or summary.value.denominator != len(values)
                ):
                    raise ValueError("residual audit summary differs from sealed findings")
            elif summary.knowledge_state is not KnowledgeState.UNKNOWN:
                raise ValueError("residual audit summary differs from sealed findings")
            if summary.query_scope_id != self.protocol.protocol_id:
                raise ValueError("residual audit summary has the wrong protocol scope")
        if self.scientific_use_permitted:
            raise ValueError("residual audit result is not itself a release authority")
        if self.blocker.issue_id != EVALUATION_SCIENTIFIC_HOLD_ISSUE_ID:
            raise ValueError("residual audit must retain the scientific HOLD blocker")
        expected = content_checksum(
            self.model_dump(mode="json", exclude={"result_id", "content_checksum"})
        )
        if self.content_checksum != expected:
            raise ValueError("residual audit result checksum mismatch")
        if self.result_id != f"RESIDUAL-AUDIT-{expected[:20]}":
            raise ValueError("residual audit result ID mismatch")
        return self


class AgreementObservation(KernelModel):
    metric_id: NonBlankStr
    numerator: int = Field(ge=0)
    denominator: int = Field(ge=1)
    unit: NonBlankStr

    @model_validator(mode="after")
    def _valid_fraction(self) -> Self:
        if self.numerator > self.denominator:
            raise ValueError("agreement numerator cannot exceed denominator")
        return self


class StabilityComponentObservation(KernelModel):
    observation_id: NonBlankStr
    artifact_checksum: Sha256
    summary: NonBlankStr


class ReferenceStabilityComponent(StrEnum):
    PRE_ADJUDICATION_AGREEMENT = "PRE_ADJUDICATION_AGREEMENT"
    ADJUDICATOR_TEST_RETEST = "ADJUDICATOR_TEST_RETEST"
    BIOLOGY_STATISTICS_DISAGREEMENT = "BIOLOGY_STATISTICS_DISAGREEMENT"
    NEW_INFORMATION_SENSITIVITY = "NEW_INFORMATION_SENSITIVITY"
    BLIND_RESIDUAL_READJUDICATION = "BLIND_RESIDUAL_READJUDICATION"
    GRAPH_MATCHING_UNCERTAINTY = "GRAPH_MATCHING_UNCERTAINTY"


class ReferenceStabilityConclusion(StrEnum):
    REVIEWED_WITHIN_PREREGISTERED_DECISION_REGION = "REVIEWED_WITHIN_PREREGISTERED_DECISION_REGION"
    REVIEWED_OUTSIDE_PREREGISTERED_DECISION_REGION = (
        "REVIEWED_OUTSIDE_PREREGISTERED_DECISION_REGION"
    )


class ReferenceStabilityPolicyPin(KernelModel):
    policy_id: NonBlankStr
    policy_version: NonBlankStr
    policy_checksum: Sha256
    decision_region_id: NonBlankStr


class ReferenceStabilityComponentRecord(KernelModel):
    component: ReferenceStabilityComponent
    observation: KnowledgeValue[AgreementObservation | StabilityComponentObservation]
    reviewer_actor_ids: tuple[NonBlankStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _agreement_only_in_agreement_component(self) -> Self:
        if (
            self.observation.knowledge_state is KnowledgeState.PRESENT
            and isinstance(self.observation.value, AgreementObservation)
            and self.component is not ReferenceStabilityComponent.PRE_ADJUDICATION_AGREEMENT
        ):
            raise ValueError("agreement cannot stand in for another reference-stability component")
        return self


class ReferenceStabilityReport(KernelModel):
    artifact_id: NonBlankStr
    report_id: NonBlankStr
    content_checksum: Sha256
    protocol_id: NonBlankStr
    component_records: tuple[ReferenceStabilityComponentRecord, ...]
    evidence_ids: tuple[NonBlankStr, ...] = Field(min_length=1)
    interpretation_policy: KnowledgeValue[ReferenceStabilityPolicyPin]
    reference_stability_conclusion: KnowledgeValue[ReferenceStabilityConclusion]
    blocker: ScientificReviewRequirement | None

    @property
    def component_evidence_complete(self) -> bool:
        return all(
            record.observation.knowledge_state is KnowledgeState.PRESENT
            for record in self.component_records
        )

    @model_validator(mode="after")
    def _six_components_and_no_agreement_shortcut(self) -> Self:
        components = [record.component for record in self.component_records]
        if len(set(components)) != 6 or set(components) != set(ReferenceStabilityComponent):
            raise ValueError("reference stability requires exactly six distinct components")
        known_evidence = set(self.evidence_ids)
        if any(
            record.observation.knowledge_state is KnowledgeState.PRESENT
            and not set(record.observation.evidence_ids).issubset(known_evidence)
            for record in self.component_records
        ):
            raise ValueError("reference-stability component has dangling evidence IDs")
        if any(
            record.observation.query_scope_id != self.report_id for record in self.component_records
        ):
            raise ValueError("reference-stability component has the wrong report scope")
        conclusion_state = self.reference_stability_conclusion.knowledge_state
        if self.reference_stability_conclusion.query_scope_id != self.report_id:
            raise ValueError("reference-stability conclusion has the wrong report scope")
        if self.interpretation_policy.query_scope_id != self.report_id:
            raise ValueError("reference-stability policy has the wrong report scope")
        if self.interpretation_policy.knowledge_state is KnowledgeState.PRESENT and not set(
            self.interpretation_policy.evidence_ids
        ).issubset(known_evidence):
            raise ValueError("reference-stability policy has dangling evidence IDs")
        if conclusion_state is KnowledgeState.PRESENT:
            if not self.component_evidence_complete:
                raise ValueError("reference-stability conclusion requires all six components")
            if self.interpretation_policy.knowledge_state is not KnowledgeState.PRESENT:
                raise ValueError("reference-stability conclusion requires a pinned policy")
            if not set(self.reference_stability_conclusion.evidence_ids).issubset(known_evidence):
                raise ValueError("reference-stability conclusion has dangling evidence IDs")
            if self.blocker is not None:
                raise ValueError("reviewed reference-stability conclusion cannot retain blocker")
        elif (
            conclusion_state is not KnowledgeState.UNKNOWN
            or self.blocker is None
            or self.blocker.issue_id != REFERENCE_STABILITY_REVIEW_ISSUE_ID
        ):
            raise ValueError("unclosed reference stability requires UNKNOWN and its blocker")
        expected = content_checksum(
            self.model_dump(mode="json", exclude={"artifact_id", "content_checksum"})
        )
        if self.content_checksum != expected:
            raise ValueError("reference stability report checksum mismatch")
        if self.artifact_id != f"REFERENCE-STABILITY-{expected[:20]}":
            raise ValueError("reference stability report artifact ID mismatch")
        return self


__all__ = [
    "CONFORMANCE_REFERENCE_REVIEW_ISSUE_ID",
    "EVALUATION_PROCESS_METRICS_REVIEW_ISSUE_ID",
    "EVALUATION_REFERENCE_REVIEW_ISSUE_ID",
    "EVALUATION_SCIENTIFIC_HOLD_ISSUE_ID",
    "PARTIAL_CLAIM_MATCH_REVIEW_ISSUE_ID",
    "REFERENCE_STABILITY_REVIEW_ISSUE_ID",
    "AbstentionDisposition",
    "AdequacyAxisSnapshot",
    "AgreementObservation",
    "AuditCountSummary",
    "AuditRole",
    "AuditRoleAssignment",
    "BlindResidualAuditProtocol",
    "BlindResidualAuditResult",
    "ClaimEvaluationSnapshot",
    "EndToEndEvaluationReport",
    "EvaluationDenominators",
    "EvaluationProcessObservations",
    "EvaluationStatus",
    "FalseCertaintyCategory",
    "FalseCertaintyDenominatorScope",
    "FalseCertaintySummary",
    "IndependentReferencePurpose",
    "IndependentReportReference",
    "MatchOutcome",
    "MatchSummary",
    "PartialClaimEquivalence",
    "QueryEvaluationResult",
    "QueryEvaluationSnapshot",
    "QuestionAttributionSnapshot",
    "QuestionUsefulnessObservation",
    "ReferenceStabilityArtifactReference",
    "ReferenceStabilityComponent",
    "ReferenceStabilityComponentRecord",
    "ReferenceStabilityConclusion",
    "ReferenceStabilityPolicyPin",
    "ReferenceStabilityReport",
    "ReportEvaluationSnapshot",
    "ResidualAuditFinding",
    "ResidualAuditSampleItem",
    "ResidualAuditStratum",
    "ResidualDimension",
    "ResidualEvent",
    "ResidualOrigin",
    "ResidualScopeKind",
    "ResidualSeverity",
    "StabilityComponentObservation",
    "TimeToConfirmedReportObservation",
]
