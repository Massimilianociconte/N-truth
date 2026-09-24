"""Deterministic report-level scoring for the PRD v8 evaluation boundary."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError
from pydantic_core import to_jsonable_python

from ntruth.evaluation_v8.models import (
    CONFORMANCE_REFERENCE_REVIEW_ISSUE_ID,
    EVALUATION_PROCESS_METRICS_REVIEW_ISSUE_ID,
    EVALUATION_REFERENCE_REVIEW_ISSUE_ID,
    EVALUATION_SCIENTIFIC_HOLD_ISSUE_ID,
    FALSE_CERTAINTY_PROTOCOL_REVIEW_ISSUE_ID,
    PARTIAL_CLAIM_MATCH_REVIEW_ISSUE_ID,
    REFERENCE_STABILITY_REVIEW_ISSUE_ID,
    AbstentionDisposition,
    AdequacyAxisSnapshot,
    AuditCountSummary,
    BlindResidualAuditProtocol,
    BlindResidualAuditResult,
    ClaimEvaluationSnapshot,
    EndToEndEvaluationReport,
    EvaluationDenominators,
    EvaluationProcessObservations,
    EvaluationStatus,
    FalseCertaintyCategory,
    FalseCertaintyMetricProtocol,
    FalseCertaintySummary,
    IndependentReferencePurpose,
    IndependentReportReference,
    MatchOutcome,
    MatchSummary,
    PartialClaimEquivalence,
    QueryEvaluationResult,
    QueryEvaluationSnapshot,
    QuestionAttributionSnapshot,
    QuestionUsefulnessObservation,
    ReferenceStabilityArtifactReference,
    ReferenceStabilityComponentRecord,
    ReferenceStabilityConclusion,
    ReferenceStabilityPolicyPin,
    ReferenceStabilityReport,
    ReportEvaluationSnapshot,
    ResidualAuditFinding,
    ResidualDimension,
    ResidualEvent,
    ResidualOrigin,
    ResidualScopeKind,
    ResidualSeverity,
)
from ntruth.schemas.claims import DeterminabilityState
from ntruth.schemas.core import content_checksum
from ntruth.schemas.kernel import KERNEL_SCHEMA_VERSION
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.report_resolution import TrivialExplicitReportResolutionPolicy
from ntruth.schemas.support import ScientificReviewRequirement

if TYPE_CHECKING:
    from ntruth.schemas.report_bundle import ReportBundle


def _addressed_fields_checksum(fields: dict[str, Any]) -> str:
    """Hash builder fields without constructing an intentionally invalid draft model."""

    return content_checksum(to_jsonable_python({"schema_version": KERNEL_SCHEMA_VERSION, **fields}))


def _not_applicable_checksum(*, scope: str, rationale: str) -> KnowledgeValue[str]:
    return KnowledgeValue[str](
        knowledge_state=KnowledgeState.NOT_APPLICABLE,
        rationale=rationale,
        query_scope_id=scope,
    )


def _unknown[T](*, scope: str, rationale: str) -> KnowledgeValue[T]:
    return KnowledgeValue[T](
        knowledge_state=KnowledgeState.UNKNOWN,
        rationale=rationale,
        query_scope_id=scope,
    )


def build_report_evaluation_snapshot(
    *,
    report_id: str,
    report_checksum: str,
    global_report_resolution_checksum: str,
    query_snapshots: tuple[QueryEvaluationSnapshot, ...],
) -> ReportEvaluationSnapshot:
    """Create an immutable projection that pins the complete ReportBundle digest."""

    fields: dict[str, Any] = {
        "report_id": report_id,
        "report_checksum": report_checksum,
        "global_report_resolution_checksum": global_report_resolution_checksum,
        "query_snapshots": query_snapshots,
    }
    draft = ReportEvaluationSnapshot.model_construct(
        snapshot_id="EVAL-SNAPSHOT-PENDING",
        content_checksum="0" * 64,
        **fields,
    )
    checksum = content_checksum(
        draft.model_dump(mode="json", exclude={"snapshot_id", "content_checksum"})
    )
    return ReportEvaluationSnapshot(
        snapshot_id=f"EVAL-SNAPSHOT-{checksum[:20]}",
        content_checksum=checksum,
        **fields,
    )


def build_false_certainty_metric_protocol(
    *,
    report_scope_id: str,
    denominator_scope_id: str,
    denominator: int,
    event_unit: str,
    severity_policy_id: str,
    severity_policy_checksum: str,
    evidence_ids: tuple[str, ...],
) -> FalseCertaintyMetricProtocol:
    """Address a protocol declaration without treating the caller as a review authority."""

    fields: dict[str, Any] = {
        "report_scope_id": report_scope_id,
        "denominator_scope_id": denominator_scope_id,
        "denominator": denominator,
        "event_unit": event_unit,
        "severity_policy_id": severity_policy_id,
        "severity_policy_checksum": severity_policy_checksum,
        "evidence_ids": evidence_ids,
    }
    draft = FalseCertaintyMetricProtocol.model_construct(
        protocol_id="FALSE-CERTAINTY-PROTOCOL-PENDING",
        content_checksum="0" * 64,
        **fields,
    )
    checksum = content_checksum(
        draft.model_dump(mode="json", exclude={"protocol_id", "content_checksum"})
    )
    return FalseCertaintyMetricProtocol(
        protocol_id=f"FALSE-CERTAINTY-PROTOCOL-{checksum[:20]}",
        content_checksum=checksum,
        **fields,
    )


def build_evaluation_process_observations(
    *,
    report: ReportBundle,
    time_to_confirmed_report: KnowledgeValue[Any],
    decisive_human_correction_count: KnowledgeValue[int],
    question_attributions: tuple[QuestionAttributionSnapshot, ...],
    question_usefulness: tuple[QuestionUsefulnessObservation, ...],
    evidence_ids: tuple[str, ...],
) -> EvaluationProcessObservations:
    """Build a report-bound draft; this alone cannot authorize process metrics."""

    from ntruth.schemas.report_bundle import ReportBundle

    checked_report = ReportBundle.model_validate(report.model_dump(mode="python"))
    known_evidence = {item.evidence_id for item in checked_report.evidence_records}
    if not set(evidence_ids).issubset(known_evidence):
        raise ValueError("process observations reference evidence outside the ReportBundle")
    questions_by_id = {item.question_id: item for item in checked_report.questions}
    claims_by_query = {
        section.inferential_query.id: {claim.claim_id for claim in section.claim_set.claims}
        for section in checked_report.query_sections
    }
    for attribution in question_attributions:
        question = questions_by_id.get(attribution.question_id)
        if question is None or question.inferential_query_id != attribution.query_id:
            raise ValueError("process attribution references a question outside the report")
        if attribution.claim_ids.knowledge_state is not KnowledgeState.PRESENT:
            raise ValueError("process attribution must be reviewed and PRESENT")
        if not set(attribution.claim_ids.value or ()).issubset(
            claims_by_query.get(attribution.query_id, set())
        ):
            raise ValueError("process attribution references a claim outside its query")
    attribution_identities = {(item.query_id, item.question_id) for item in question_attributions}
    report_question_identities = {
        (item.inferential_query_id, item.question_id) for item in checked_report.questions
    }
    if attribution_identities != report_question_identities:
        raise ValueError("process attribution ledger differs from the complete report questions")
    for item in question_usefulness:
        question = questions_by_id.get(item.question_id)
        if question is None or question.inferential_query_id != item.query_id:
            raise ValueError("question-usefulness row references a question outside the report")
        if (item.query_id, item.question_id) not in attribution_identities:
            raise ValueError("question usefulness lacks a reviewed claim attribution")
    usefulness_evidence = tuple(
        sorted(
            {
                evidence_id
                for item in question_usefulness
                for value in (
                    item.answerable,
                    item.relevance,
                    item.scenario_resolved,
                    item.output_changing,
                    item.redundant,
                    item.recipient_correct,
                    item.response_time_seconds,
                    item.evidence_requested,
                    item.remaining_scenario_coverage,
                )
                for evidence_id in value.evidence_ids
            }
        )
    )
    fields: dict[str, Any] = {
        "report_scope_id": checked_report.report_id,
        "report_checksum": checked_report.content_checksum,
        "evidence_ids": evidence_ids,
        "question_attributions": question_attributions,
        "time_to_confirmed_report": time_to_confirmed_report,
        "decisive_human_correction_count": decisive_human_correction_count,
        "question_usefulness": KnowledgeValue[tuple[QuestionUsefulnessObservation, ...]](
            knowledge_state=KnowledgeState.PRESENT,
            value=question_usefulness,
            evidence_ids=usefulness_evidence,
            query_scope_id=checked_report.report_id,
        ),
    }
    draft = EvaluationProcessObservations.model_construct(
        observation_id="EVAL-PROCESS-PENDING",
        content_checksum="0" * 64,
        **fields,
    )
    checksum = content_checksum(
        draft.model_dump(mode="json", exclude={"observation_id", "content_checksum"})
    )
    return EvaluationProcessObservations(
        observation_id=f"EVAL-PROCESS-{checksum[:20]}",
        content_checksum=checksum,
        **fields,
    )


def build_independent_report_reference(
    *,
    reference_id: str,
    purpose: IndependentReferencePurpose,
    report_scope_id: str,
    snapshot: ReportEvaluationSnapshot,
    source_record_ids: tuple[str, ...],
    evidence_ids: tuple[str, ...],
    reviewer_actor_ids: tuple[str, ...],
    reference_stability_report: ReferenceStabilityReport | None = None,
    reference_stability_report_checksum: KnowledgeValue[str] | None = None,
    partial_claim_equivalences: KnowledgeValue[tuple[PartialClaimEquivalence, ...]] | None = None,
) -> IndependentReportReference:
    """Address a reference and make conformance-only purpose non-upgradable."""

    purpose = IndependentReferencePurpose(purpose)
    snapshot = ReportEvaluationSnapshot.model_validate(
        snapshot.model_dump(mode="python", round_trip=True, warnings="none")
    )
    if reference_stability_report is not None:
        reference_stability_report = ReferenceStabilityReport.model_validate(
            reference_stability_report.model_dump(mode="python", round_trip=True, warnings="none")
        )
    if partial_claim_equivalences is not None:
        partial_claim_equivalences = KnowledgeValue[
            tuple[PartialClaimEquivalence, ...]
        ].model_validate(
            partial_claim_equivalences.model_dump(mode="python", round_trip=True, warnings="none")
        )
    if reference_stability_report_checksum is not None:
        raise ValueError(
            "raw reference-stability checksum is not authoritative; resolve the addressed report"
        )
    reference_stability_value: KnowledgeValue[ReferenceStabilityArtifactReference]
    if purpose is IndependentReferencePurpose.CONFORMANCE_ONLY:
        reference_stability_value = KnowledgeValue[ReferenceStabilityArtifactReference](
            knowledge_state=KnowledgeState.NOT_APPLICABLE,
            rationale="Conformance fixtures are not scientific reference-stability evidence.",
            query_scope_id=report_scope_id,
        )
    elif reference_stability_report is None:
        reference_stability_value = _unknown(
            scope=report_scope_id,
            rationale="No independently reviewed reference-stability report was supplied.",
        )
    else:
        if reference_stability_report.report_id != report_scope_id:
            raise ValueError("reference-stability report belongs to another report scope")
        reference_stability_value = KnowledgeValue[ReferenceStabilityArtifactReference](
            knowledge_state=KnowledgeState.PRESENT,
            value=ReferenceStabilityArtifactReference(
                artifact_id=reference_stability_report.artifact_id,
                content_checksum=reference_stability_report.content_checksum,
                report_scope_id=reference_stability_report.report_id,
            ),
            evidence_ids=(evidence_ids[0],),
            query_scope_id=report_scope_id,
        )
    if partial_claim_equivalences is None:
        if purpose is IndependentReferencePurpose.CONFORMANCE_ONLY:
            partial_claim_equivalences = KnowledgeValue[tuple[PartialClaimEquivalence, ...]](
                knowledge_state=KnowledgeState.NOT_APPLICABLE,
                rationale="Conformance fixtures use exact deterministic matching only.",
                query_scope_id=report_scope_id,
            )
        else:
            partial_claim_equivalences = _unknown(
                scope=report_scope_id,
                rationale="No reviewed partial-claim equivalence policy was supplied.",
            )
    fields: dict[str, Any] = {
        "reference_id": reference_id,
        "purpose": purpose,
        "report_scope_id": report_scope_id,
        "snapshot": snapshot,
        "source_record_ids": source_record_ids,
        "evidence_ids": evidence_ids,
        "reviewer_actor_ids": reviewer_actor_ids,
        "reference_stability_report": reference_stability_value,
        "partial_claim_equivalences": partial_claim_equivalences,
    }
    checksum = _addressed_fields_checksum(fields)
    return IndependentReportReference(content_checksum=checksum, **fields)


def build_reference_stability_report(
    *,
    report_id: str,
    protocol_id: str,
    component_records: tuple[ReferenceStabilityComponentRecord, ...],
    evidence_ids: tuple[str, ...],
    interpretation_policy: KnowledgeValue[ReferenceStabilityPolicyPin] | None = None,
    reviewed_conclusion: KnowledgeValue[ReferenceStabilityConclusion] | None = None,
) -> ReferenceStabilityReport:
    """Record all six components without converting agreement into stability."""

    if (interpretation_policy is None) != (reviewed_conclusion is None):
        raise ValueError("reviewed conclusion and interpretation policy must be supplied together")
    blocker: ScientificReviewRequirement | None
    if interpretation_policy is None or reviewed_conclusion is None:
        interpretation_policy = KnowledgeValue[ReferenceStabilityPolicyPin](
            knowledge_state=KnowledgeState.UNKNOWN,
            rationale="No externally reviewed interpretation policy was supplied.",
            query_scope_id=report_id,
        )
        conclusion = KnowledgeValue[ReferenceStabilityConclusion](
            knowledge_state=KnowledgeState.UNKNOWN,
            rationale=(
                "Reference stability requires all six components plus an externally reviewed, "
                "preregistered interpretation policy; agreement alone is insufficient."
            ),
            query_scope_id=report_id,
        )
        blocker = ScientificReviewRequirement(
            issue_id=REFERENCE_STABILITY_REVIEW_ISSUE_ID,
            rationale=(
                "No independently reviewed reference-stability conclusion is available in this "
                "engineering migration."
            ),
        )
    else:
        conclusion = reviewed_conclusion
        blocker = None
    fields: dict[str, Any] = {
        "report_id": report_id,
        "protocol_id": protocol_id,
        "component_records": component_records,
        "evidence_ids": evidence_ids,
        "interpretation_policy": interpretation_policy,
        "reference_stability_conclusion": conclusion,
        "blocker": blocker,
    }
    checksum = _addressed_fields_checksum(fields)
    return ReferenceStabilityReport(
        artifact_id=f"REFERENCE-STABILITY-{checksum[:20]}",
        content_checksum=checksum,
        **fields,
    )


def _summarize_audit_boolean(
    *,
    protocol: BlindResidualAuditProtocol,
    findings: tuple[ResidualAuditFinding, ...],
    field_name: str,
) -> KnowledgeValue[AuditCountSummary]:
    values = [getattr(finding, field_name) for finding in findings]
    if all(value.knowledge_state is KnowledgeState.PRESENT for value in values):
        evidence_ids = tuple(
            sorted({evidence_id for value in values for evidence_id in value.evidence_ids})
        )
        return KnowledgeValue[AuditCountSummary](
            knowledge_state=KnowledgeState.PRESENT,
            value=AuditCountSummary(
                numerator=sum(bool(value.value) for value in values),
                denominator=len(values),
            ),
            evidence_ids=evidence_ids,
            query_scope_id=protocol.protocol_id,
        )
    return KnowledgeValue[AuditCountSummary](
        knowledge_state=KnowledgeState.UNKNOWN,
        rationale=(
            f"At least one sampled claim has unresolved {field_name}; no zero or rate is imputed."
        ),
        query_scope_id=protocol.protocol_id,
    )


def summarize_blind_residual_audit(
    protocol: BlindResidualAuditProtocol,
    findings: tuple[ResidualAuditFinding, ...],
) -> BlindResidualAuditResult:
    """Summarize a closed blind sample without imputing unknown findings as no error."""

    protocol = BlindResidualAuditProtocol.model_validate(
        protocol.model_dump(mode="python", round_trip=True, warnings="none")
    )
    findings = tuple(
        ResidualAuditFinding.model_validate(
            finding.model_dump(mode="python", round_trip=True, warnings="none")
        )
        for finding in findings
    )
    summaries = {
        "decisive_error_count": _summarize_audit_boolean(
            protocol=protocol, findings=findings, field_name="decisive_error"
        ),
        "false_certainty_count": _summarize_audit_boolean(
            protocol=protocol, findings=findings, field_name="false_certainty"
        ),
        "human_review_introduced_error_count": _summarize_audit_boolean(
            protocol=protocol,
            findings=findings,
            field_name="human_review_introduced_error",
        ),
    }
    fields: dict[str, Any] = {
        "protocol": protocol,
        "findings": findings,
        **summaries,
        "scientific_use_permitted": False,
        "blocker": ScientificReviewRequirement(
            issue_id=EVALUATION_SCIENTIFIC_HOLD_ISSUE_ID,
            rationale=(
                "Residual observations require governed reference stability, cluster-aware "
                "precision and a policy-pinned release decision before scientific use."
            ),
        ),
    }
    checksum = _addressed_fields_checksum(fields)
    return BlindResidualAuditResult(
        result_id=f"RESIDUAL-AUDIT-{checksum[:20]}", content_checksum=checksum, **fields
    )


def _match_summary(
    *,
    reference_ids: set[str],
    observed_ids: set[str],
    outcomes: dict[str, MatchOutcome],
) -> MatchSummary:
    counts = {outcome: 0 for outcome in MatchOutcome}
    for identifier in reference_ids:
        counts[outcomes.get(identifier, MatchOutcome.MISSING)] += 1
    unexpected = len(observed_ids - reference_ids)
    counts[MatchOutcome.UNEXPECTED] = unexpected
    return MatchSummary(
        denominator=len(reference_ids),
        unexpected_count=unexpected,
        by_outcome=counts,
    )


def _abstention_disposition(
    observed: ClaimEvaluationSnapshot,
    reference: ClaimEvaluationSnapshot,
    claim_outcome: MatchOutcome,
    *,
    independently_reviewed_actionable_question_ids: frozenset[str] = frozenset(),
) -> AbstentionDisposition:
    if observed.determinability_state is DeterminabilityState.DETERMINATE and (
        reference.determinability_state is not DeterminabilityState.DETERMINATE
        or claim_outcome is MatchOutcome.INCORRECT
    ):
        return AbstentionDisposition.FALSE_CERTAINTY
    if observed.determinability_state is DeterminabilityState.DETERMINATE:
        return AbstentionDisposition.RESOLVED
    if observed.actionable_question_ids.knowledge_state is KnowledgeState.PRESENT and bool(
        set(observed.actionable_question_ids.value or ())
        & independently_reviewed_actionable_question_ids
    ):
        return AbstentionDisposition.ACTIONABLE_ABSTENTION
    if observed.unresolved_risk_ids.knowledge_state is KnowledgeState.PRESENT:
        return AbstentionDisposition.UNRESOLVED_RISK_DETECTED
    return AbstentionDisposition.UNACTIONABLE_ABSTENTION


def _unknown_residual_dimension[T](
    *, scope_id: str, claim_id: str | None, query_id: str | None, rationale: str
) -> KnowledgeValue[T]:
    if claim_id is not None:
        return KnowledgeValue[T](
            knowledge_state=KnowledgeState.UNKNOWN,
            rationale=rationale,
            claim_scope_id=claim_id,
        )
    return KnowledgeValue[T](
        knowledge_state=KnowledgeState.UNKNOWN,
        rationale=rationale,
        query_scope_id=query_id or scope_id,
    )


def _residual_event(
    *,
    dimension: ResidualDimension,
    scope_kind: ResidualScopeKind,
    scope_id: str,
    match_outcome: MatchOutcome,
    impact_on_claim: str,
    query_id: str | None = None,
    claim_id: str | None = None,
    axis_id: str | None = None,
    false_certainty_category: KnowledgeValue[FalseCertaintyCategory] | None = None,
    false_certainty: bool | None = None,
    false_certainty_evidence_ids: tuple[str, ...] = (),
) -> ResidualEvent:
    if false_certainty_category is None:
        false_certainty_category = _unknown_residual_dimension(
            scope_id=scope_id,
            claim_id=claim_id,
            query_id=query_id,
            rationale="False-certainty classification requires independent residual review.",
        )
    origin: KnowledgeValue[ResidualOrigin] = _unknown_residual_dimension(
        scope_id=scope_id,
        claim_id=claim_id,
        query_id=query_id,
        rationale="Error origin requires blind residual re-adjudication.",
    )
    severity: KnowledgeValue[ResidualSeverity] = _unknown_residual_dimension(
        scope_id=scope_id,
        claim_id=claim_id,
        query_id=query_id,
        rationale="Severity requires the preregistered residual-audit rubric.",
    )
    false_certainty_value: KnowledgeValue[bool]
    if false_certainty is not None and false_certainty_evidence_ids:
        false_certainty_value = KnowledgeValue[bool](
            knowledge_state=KnowledgeState.PRESENT,
            value=false_certainty,
            evidence_ids=false_certainty_evidence_ids,
            claim_scope_id=claim_id,
            query_scope_id=None if claim_id is not None else (query_id or scope_id),
        )
    else:
        false_certainty_value = _unknown_residual_dimension(
            scope_id=scope_id,
            claim_id=claim_id,
            query_id=query_id,
            rationale=(
                "False-certainty status requires a definitive output and reviewed comparator."
            ),
        )
    identity = (
        dimension,
        scope_kind,
        scope_id,
        match_outcome,
        query_id,
        claim_id,
        axis_id,
        false_certainty_value.model_dump(mode="json"),
        false_certainty_category.model_dump(mode="json"),
    )
    return ResidualEvent(
        residual_id=f"RESIDUAL-{content_checksum(identity)[:20]}",
        dimension=dimension,
        scope_kind=scope_kind,
        scope_id=scope_id,
        query_id=query_id,
        claim_id=claim_id,
        axis_id=axis_id,
        match_outcome=match_outcome,
        false_certainty=false_certainty_value,
        false_certainty_category=false_certainty_category,
        origin=origin,
        severity=severity,
        impact_on_claim=impact_on_claim,
    )


def _false_certainty_residuals(
    *,
    observed: ClaimEvaluationSnapshot,
    reference: ClaimEvaluationSnapshot,
) -> tuple[ResidualEvent, ...]:
    dimension_by_category = {
        FalseCertaintyCategory.EU_OR_COUNT_ERROR: ResidualDimension.COUNT_CORRECTNESS,
        FalseCertaintyCategory.DECISIVE_PRECONDITION_UNSUPPORTED: (
            ResidualDimension.SUPPORT_CORRECTNESS
        ),
        FalseCertaintyCategory.MATERIAL_SCENARIO_OMITTED: ResidualDimension.SCENARIO_COVERAGE,
        FalseCertaintyCategory.HIDDEN_CONFLICT: ResidualDimension.SUPPORT_CORRECTNESS,
        FalseCertaintyCategory.PROFILE_COVERAGE_UNDECLARED: ResidualDimension.PROFILE_COVERAGE,
        FalseCertaintyCategory.INFERENCE_OR_ESTIMAND_SCOPE_OVERREACH: (
            ResidualDimension.CLAIM_SEMANTICS
        ),
        FalseCertaintyCategory.ADEQUACY_UNSUPPORTED_POSITIVE: ResidualDimension.ADEQUACY_AXIS,
    }
    categories = reference.false_certainty_categories
    if categories.knowledge_state is KnowledgeState.PRESENT:
        category_values: tuple[FalseCertaintyCategory | None, ...] = tuple(categories.value or ())
    else:
        category_values = (None,)
    residuals: list[ResidualEvent] = []
    for category in category_values:
        category_value: KnowledgeValue[FalseCertaintyCategory]
        if category is None:
            category_value = _unknown_residual_dimension(
                scope_id=observed.claim_id,
                claim_id=observed.claim_id,
                query_id=observed.query_id,
                rationale="The independent audit has not classified the false-certainty condition.",
            )
        else:
            category_value = KnowledgeValue[FalseCertaintyCategory](
                knowledge_state=KnowledgeState.PRESENT,
                value=category,
                evidence_ids=categories.evidence_ids,
                claim_scope_id=observed.claim_id,
            )
        residuals.append(
            _residual_event(
                dimension=(
                    ResidualDimension.CLAIM_SEMANTICS
                    if category is None
                    else dimension_by_category[category]
                ),
                scope_kind=ResidualScopeKind.CLAIM,
                scope_id=observed.claim_id,
                query_id=observed.query_id,
                claim_id=observed.claim_id,
                match_outcome=MatchOutcome.INCORRECT,
                false_certainty_category=category_value,
                false_certainty=True,
                false_certainty_evidence_ids=(
                    categories.evidence_ids or reference.decisive.evidence_ids
                ),
                impact_on_claim=(
                    "Observed output was DETERMINATE while the independent reference retained "
                    "an unresolved state or a materially different semantic value."
                ),
            )
        )
    return tuple(residuals)


def _build_end_to_end_report(fields: dict[str, Any]) -> EndToEndEvaluationReport:
    checksum = _addressed_fields_checksum(fields)
    return EndToEndEvaluationReport(
        evaluation_id=f"E2E-{checksum[:20]}",
        content_checksum=checksum,
        **fields,
    )


def _score_query(
    observed: QueryEvaluationSnapshot | None,
    reference: QueryEvaluationSnapshot,
    partial_equivalences: dict[tuple[str, str], set[str]],
) -> tuple[QueryEvaluationResult, tuple[ResidualEvent, ...]]:
    reference_claims = {claim.claim_id: claim for claim in reference.claims}
    observed_claims = (
        {} if observed is None else {claim.claim_id: claim for claim in observed.claims}
    )
    claim_outcomes: dict[str, MatchOutcome] = {}
    evidence_outcomes: dict[str, MatchOutcome] = {}
    proof_outcomes: dict[str, MatchOutcome] = {}
    abstention = Counter({item: 0 for item in AbstentionDisposition})
    false_certainty_claim_ids: list[str] = []
    residuals: list[ResidualEvent] = []
    if (
        observed is None
        or observed.report_resolution_checksum != reference.report_resolution_checksum
    ):
        residuals.append(
            _residual_event(
                dimension=ResidualDimension.QUERY_REPORT_RESOLUTION,
                scope_kind=ResidualScopeKind.QUERY,
                scope_id=reference.query_id,
                query_id=reference.query_id,
                match_outcome=(
                    MatchOutcome.MISSING if observed is None else MatchOutcome.INCORRECT
                ),
                impact_on_claim="The query-level report resolution differs from the reference.",
            )
        )
    for claim_id, expected in reference_claims.items():
        actual = observed_claims.get(claim_id)
        if actual is None:
            claim_outcomes[claim_id] = MatchOutcome.MISSING
            evidence_outcomes[claim_id] = MatchOutcome.MISSING
            proof_outcomes[claim_id] = MatchOutcome.MISSING
            abstention[AbstentionDisposition.NOT_EVALUABLE_MISSING_OUTPUT] += 1
            for dimension, impact in (
                (
                    ResidualDimension.CLAIM_SEMANTICS,
                    "A reference claim is missing from the observed report.",
                ),
                (
                    ResidualDimension.EVIDENCE_CORRECTNESS,
                    "Evidence correctness is not evaluable because the reference claim is missing.",
                ),
                (
                    ResidualDimension.PROOF_CORRECTNESS,
                    "Proof correctness is not evaluable because the reference claim is missing.",
                ),
            ):
                residuals.append(
                    _residual_event(
                        dimension=dimension,
                        scope_kind=ResidualScopeKind.CLAIM,
                        scope_id=claim_id,
                        query_id=reference.query_id,
                        claim_id=claim_id,
                        match_outcome=MatchOutcome.MISSING,
                        impact_on_claim=impact,
                    )
                )
            continue
        if (
            actual.semantic_value_checksum == expected.semantic_value_checksum
            and actual.determinability_state is expected.determinability_state
        ):
            claim_outcomes[claim_id] = MatchOutcome.EXACT
        elif (
            actual.determinability_state is expected.determinability_state
            and actual.semantic_value_checksum
            in partial_equivalences.get((reference.query_id, claim_id), set())
        ):
            claim_outcomes[claim_id] = MatchOutcome.PARTIAL
        else:
            claim_outcomes[claim_id] = MatchOutcome.INCORRECT
        evidence_outcomes[claim_id] = (
            MatchOutcome.EXACT
            if (
                actual.evidence_record_ids == expected.evidence_record_ids
                and actual.evidence_content_checksum == expected.evidence_content_checksum
            )
            else MatchOutcome.INCORRECT
        )
        proof_outcomes[claim_id] = (
            MatchOutcome.EXACT
            if actual.proof_trace_checksum == expected.proof_trace_checksum
            else MatchOutcome.INCORRECT
        )
        disposition = _abstention_disposition(actual, expected, claim_outcomes[claim_id])
        definitive_false_certainty = disposition is AbstentionDisposition.FALSE_CERTAINTY
        definitive_evidence = tuple(
            sorted(
                {
                    *actual.decisive.evidence_ids,
                    *expected.decisive.evidence_ids,
                    *actual.evidence_record_ids.evidence_ids,
                    *expected.evidence_record_ids.evidence_ids,
                }
            )
        )
        abstention[disposition] += 1
        if disposition is AbstentionDisposition.FALSE_CERTAINTY:
            false_certainty_claim_ids.append(claim_id)
            residuals.extend(_false_certainty_residuals(observed=actual, reference=expected))
        elif claim_outcomes[claim_id] is not MatchOutcome.EXACT:
            residuals.append(
                _residual_event(
                    dimension=ResidualDimension.CLAIM_SEMANTICS,
                    scope_kind=ResidualScopeKind.CLAIM,
                    scope_id=claim_id,
                    query_id=reference.query_id,
                    claim_id=claim_id,
                    match_outcome=claim_outcomes[claim_id],
                    impact_on_claim="Observed claim semantics differ from the independent reference.",
                )
            )
        if evidence_outcomes[claim_id] is not MatchOutcome.EXACT:
            residuals.append(
                _residual_event(
                    dimension=ResidualDimension.EVIDENCE_CORRECTNESS,
                    scope_kind=ResidualScopeKind.CLAIM,
                    scope_id=claim_id,
                    query_id=reference.query_id,
                    claim_id=claim_id,
                    match_outcome=evidence_outcomes[claim_id],
                    false_certainty=True if definitive_false_certainty else None,
                    false_certainty_evidence_ids=(
                        definitive_evidence if definitive_false_certainty else ()
                    ),
                    impact_on_claim="Observed evidence lineage differs from the independent reference.",
                )
            )
        if proof_outcomes[claim_id] is not MatchOutcome.EXACT:
            residuals.append(
                _residual_event(
                    dimension=ResidualDimension.PROOF_CORRECTNESS,
                    scope_kind=ResidualScopeKind.CLAIM,
                    scope_id=claim_id,
                    query_id=reference.query_id,
                    claim_id=claim_id,
                    match_outcome=proof_outcomes[claim_id],
                    false_certainty=True if definitive_false_certainty else None,
                    false_certainty_evidence_ids=(
                        definitive_evidence if definitive_false_certainty else ()
                    ),
                    impact_on_claim="Observed proof lineage differs from the independent reference.",
                )
            )

    for claim_id in sorted(set(observed_claims) - set(reference_claims)):
        unexpected_claim = observed_claims[claim_id]
        unexpected_is_definitive = (
            unexpected_claim.determinability_state is DeterminabilityState.DETERMINATE
        )
        unexpected_evidence = tuple(
            sorted(
                {
                    *unexpected_claim.decisive.evidence_ids,
                    *unexpected_claim.evidence_record_ids.evidence_ids,
                }
            )
        )
        for dimension, impact in (
            (
                ResidualDimension.CLAIM_SEMANTICS,
                "The observed report contains a claim absent from the independent reference.",
            ),
            (
                ResidualDimension.EVIDENCE_CORRECTNESS,
                "Unexpected claim evidence has no reference comparator.",
            ),
            (
                ResidualDimension.PROOF_CORRECTNESS,
                "Unexpected claim proof has no reference comparator.",
            ),
        ):
            residuals.append(
                _residual_event(
                    dimension=dimension,
                    scope_kind=ResidualScopeKind.CLAIM,
                    scope_id=claim_id,
                    query_id=reference.query_id,
                    claim_id=claim_id,
                    match_outcome=MatchOutcome.UNEXPECTED,
                    false_certainty=True if unexpected_is_definitive else None,
                    false_certainty_evidence_ids=(
                        unexpected_evidence if unexpected_is_definitive else ()
                    ),
                    impact_on_claim=impact,
                )
            )

    reference_axes = {axis.axis_id: axis for axis in reference.adequacy_axes}
    observed_axes = (
        {} if observed is None else {axis.axis_id: axis for axis in observed.adequacy_axes}
    )
    axis_outcomes = {
        axis_id: (
            MatchOutcome.EXACT
            if axis_id in observed_axes
            and observed_axes[axis_id].outcome_checksum == expected.outcome_checksum
            else MatchOutcome.INCORRECT
            if axis_id in observed_axes
            else MatchOutcome.MISSING
        )
        for axis_id, expected in reference_axes.items()
    }
    for axis_id, outcome in axis_outcomes.items():
        if outcome is not MatchOutcome.EXACT:
            observed_axis = observed_axes.get(axis_id)
            communicated_positive = (
                observed_axis is not None
                and observed_axis.communicated_positive.knowledge_state is KnowledgeState.PRESENT
                and observed_axis.communicated_positive.value is True
            )
            residuals.append(
                _residual_event(
                    dimension=ResidualDimension.ADEQUACY_AXIS,
                    scope_kind=ResidualScopeKind.ADEQUACY_AXIS,
                    scope_id=axis_id,
                    query_id=reference.query_id,
                    axis_id=axis_id,
                    match_outcome=outcome,
                    false_certainty=True if communicated_positive else None,
                    false_certainty_evidence_ids=(
                        observed_axis.communicated_positive.evidence_ids
                        if communicated_positive and observed_axis is not None
                        else ()
                    ),
                    impact_on_claim="Observed design-adequacy axis differs from the reference.",
                )
            )
    for axis_id in sorted(set(observed_axes) - set(reference_axes)):
        observed_axis = observed_axes[axis_id]
        communicated_positive = (
            observed_axis.communicated_positive.knowledge_state is KnowledgeState.PRESENT
            and observed_axis.communicated_positive.value is True
        )
        residuals.append(
            _residual_event(
                dimension=ResidualDimension.ADEQUACY_AXIS,
                scope_kind=ResidualScopeKind.ADEQUACY_AXIS,
                scope_id=axis_id,
                query_id=reference.query_id,
                axis_id=axis_id,
                match_outcome=MatchOutcome.UNEXPECTED,
                false_certainty=True if communicated_positive else None,
                false_certainty_evidence_ids=(
                    observed_axis.communicated_positive.evidence_ids
                    if communicated_positive
                    else ()
                ),
                impact_on_claim="Observed report contains an adequacy axis absent from the reference.",
            )
        )
    observed_claim_ids = set(observed_claims)
    reference_claim_ids = set(reference_claims)
    decisive_values = [claim.decisive for claim in reference.claims]
    if all(value.knowledge_state is KnowledgeState.PRESENT for value in decisive_values):
        decisive_ids = {claim.claim_id for claim in reference.claims if bool(claim.decisive.value)}
        if decisive_ids:
            decisive_match = KnowledgeValue[MatchSummary](
                knowledge_state=KnowledgeState.PRESENT,
                value=_match_summary(
                    reference_ids=decisive_ids,
                    observed_ids=observed_claim_ids & decisive_ids,
                    outcomes={
                        key: value for key, value in claim_outcomes.items() if key in decisive_ids
                    },
                ),
                evidence_ids=tuple(
                    sorted(
                        {
                            evidence_id
                            for claim in reference.claims
                            if claim.claim_id in decisive_ids
                            for evidence_id in claim.decisive.evidence_ids
                        }
                    )
                ),
                query_scope_id=reference.query_id,
            )
        else:
            decisive_match = KnowledgeValue[MatchSummary](
                knowledge_state=KnowledgeState.ABSENT_EXPLICIT,
                query_scope_id=reference.query_id,
            )
    else:
        decisive_match = KnowledgeValue[MatchSummary](
            knowledge_state=KnowledgeState.UNKNOWN,
            rationale="Decisive-claim designation is not closed for every reference claim.",
            query_scope_id=reference.query_id,
        )
    result = QueryEvaluationResult(
        query_id=reference.query_id,
        report_resolution_match=(
            observed is not None
            and observed.report_resolution_checksum == reference.report_resolution_checksum
        ),
        claim_match=_match_summary(
            reference_ids=reference_claim_ids,
            observed_ids=observed_claim_ids,
            outcomes=claim_outcomes,
        ),
        decisive_claim_match=decisive_match,
        adequacy_axis_match=_match_summary(
            reference_ids=set(reference_axes),
            observed_ids=set(observed_axes),
            outcomes=axis_outcomes,
        ),
        evidence_correctness=_match_summary(
            reference_ids=reference_claim_ids,
            observed_ids=observed_claim_ids,
            outcomes=evidence_outcomes,
        ),
        proof_correctness=_match_summary(
            reference_ids=reference_claim_ids,
            observed_ids=observed_claim_ids,
            outcomes=proof_outcomes,
        ),
        abstention_dispositions=dict(abstention),
        false_certainty_claim_ids=tuple(false_certainty_claim_ids),
    )
    return result, tuple(residuals)


def _unknown_process_fields(report_scope_id: str) -> dict[str, KnowledgeValue[Any]]:
    rationale = (
        "No independently governed report timing, correction or question-usefulness record exists."
    )
    return {
        "time_to_confirmed_report_seconds": _unknown(scope=report_scope_id, rationale=rationale),
        "review_time_delta_seconds": _unknown(scope=report_scope_id, rationale=rationale),
        "decisive_human_correction_count": _unknown(scope=report_scope_id, rationale=rationale),
        "question_usefulness": _unknown(scope=report_scope_id, rationale=rationale),
    }


def _process_fields(
    observed: ReportEvaluationSnapshot,
    observations: EvaluationProcessObservations | None,
    report_bundles: tuple[ReportBundle, ...],
) -> tuple[dict[str, KnowledgeValue[Any]], bool]:
    report_scope_id = observed.report_id
    if observations is None:
        return _unknown_process_fields(report_scope_id), False
    from pydantic import ValidationError

    from ntruth.schemas.report_bundle import ReportBundle

    try:
        checked = EvaluationProcessObservations.model_validate(
            observations.model_dump(mode="python")
        )
        checked_reports = tuple(
            ReportBundle.model_validate(item.model_dump(mode="python")) for item in report_bundles
        )
    except (AttributeError, TypeError, ValidationError, ValueError):
        return _unknown_process_fields(report_scope_id), False
    matching_reports = [
        item
        for item in checked_reports
        if item.report_id == checked.report_scope_id
        and item.content_checksum == checked.report_checksum
    ]
    if (
        len(matching_reports) != 1
        or checked.report_scope_id != report_scope_id
        or checked.report_checksum != observed.report_checksum
    ):
        return _unknown_process_fields(report_scope_id), False
    report = matching_reports[0]
    known_evidence = {item.evidence_id for item in report.evidence_records}
    known_questions = {(item.inferential_query_id, item.question_id) for item in report.questions}
    known_claims = {
        section.inferential_query.id: {claim.claim_id for claim in section.claim_set.claims}
        for section in report.query_sections
    }
    attribution_identities = {
        (item.query_id, item.question_id) for item in checked.question_attributions
    }
    if (
        set(checked.evidence_ids) - known_evidence
        or attribution_identities != known_questions
        or any(
            item.claim_ids.knowledge_state is not KnowledgeState.PRESENT
            or not set(item.claim_ids.value or ()).issubset(known_claims.get(item.query_id, set()))
            for item in checked.question_attributions
        )
    ):
        return _unknown_process_fields(report_scope_id), False
    # A valid draft proves report linkage and internal integrity only.  PRD v8
    # process metrics need governed timing/correction event ledgers, reviewer
    # custody/separation evidence and an independently adjudicated H.1 record.
    # None of those authorities exists in this repository, so caller-authored
    # values must stay open-world UNKNOWN.
    return _unknown_process_fields(report_scope_id), False


def _reference_stability_is_resolved(
    reference: IndependentReportReference,
    reports: tuple[ReferenceStabilityReport, ...],
) -> bool:
    try:
        checked_reference = IndependentReportReference.model_validate(
            reference.model_dump(mode="python", round_trip=True, warnings="none")
        )
        checked_reports = tuple(
            ReferenceStabilityReport.model_validate(
                report.model_dump(mode="python", round_trip=True, warnings="none")
            )
            for report in reports
        )
    except (AttributeError, TypeError, ValidationError, ValueError):
        return False
    addressed = checked_reference.reference_stability_report
    if addressed.knowledge_state is not KnowledgeState.PRESENT or addressed.value is None:
        return False
    matches = [
        report for report in checked_reports if report.artifact_id == addressed.value.artifact_id
    ]
    if len(matches) != 1:
        return False
    report = matches[0]
    return (
        report.content_checksum == addressed.value.content_checksum
        and report.report_id == addressed.value.report_scope_id == checked_reference.report_scope_id
        and report.component_evidence_complete
        and report.interpretation_policy.knowledge_state is KnowledgeState.PRESENT
        and report.reference_stability_conclusion.knowledge_state is KnowledgeState.PRESENT
        and report.blocker is None
    )


def evaluate_end_to_end(
    observed: ReportEvaluationSnapshot,
    reference_value: KnowledgeValue[IndependentReportReference],
    *,
    reference_stability_reports: tuple[ReferenceStabilityReport, ...] = (),
    process_observations: EvaluationProcessObservations | None = None,
    process_report_bundles: tuple[ReportBundle, ...] = (),
    false_certainty_protocol: FalseCertaintyMetricProtocol | None = None,
) -> EndToEndEvaluationReport:
    """Score a complete report or emit explicit UNKNOWNs when reference is absent."""

    observed = ReportEvaluationSnapshot.model_validate(
        observed.model_dump(mode="python", round_trip=True, warnings="none")
    )
    reference_value = KnowledgeValue[IndependentReportReference].model_validate(
        reference_value.model_dump(mode="python", round_trip=True, warnings="none")
    )
    if false_certainty_protocol is not None:
        try:
            false_certainty_protocol = FalseCertaintyMetricProtocol.model_validate(
                false_certainty_protocol.model_dump(mode="python", round_trip=True, warnings="none")
            )
        except (AttributeError, TypeError, ValidationError, ValueError):
            false_certainty_protocol = None
    if reference_value.query_scope_id != observed.report_id:
        raise ValueError("reference KnowledgeValue belongs to another report scope")
    if (
        reference_value.knowledge_state is not KnowledgeState.PRESENT
        or reference_value.value is None
    ):
        rationale = "End-to-end evaluation requires an independently reviewed report reference."
        process_fields, _ = _process_fields(observed, process_observations, process_report_bundles)
        return _build_end_to_end_report(
            {
                "report_scope_id": observed.report_id,
                "observed_snapshot_checksum": observed.content_checksum,
                "reference_checksum": _unknown(scope=observed.report_id, rationale=rationale),
                "status": EvaluationStatus.BLOCKED,
                "scientific_use_permitted": False,
                "denominators": _unknown(scope=observed.report_id, rationale=rationale),
                "complete_report_match": _unknown(scope=observed.report_id, rationale=rationale),
                "global_report_resolution_match": _unknown(
                    scope=observed.report_id, rationale=rationale
                ),
                "query_results": _unknown(scope=observed.report_id, rationale=rationale),
                "residuals": _unknown(scope=observed.report_id, rationale=rationale),
                "false_certainty": _unknown(scope=observed.report_id, rationale=rationale),
                **process_fields,
                "blockers": (
                    ScientificReviewRequirement(
                        issue_id=EVALUATION_REFERENCE_REVIEW_ISSUE_ID,
                        rationale=rationale,
                    ),
                    ScientificReviewRequirement(
                        issue_id=EVALUATION_PROCESS_METRICS_REVIEW_ISSUE_ID,
                        rationale=(
                            "Timing, correction and question-usefulness observations are not closed."
                        ),
                    ),
                ),
            }
        )

    reference = reference_value.value
    if observed.report_id != reference.report_scope_id:
        raise ValueError("independent reference belongs to another report scope")
    reference_queries = {query.query_id: query for query in reference.snapshot.query_snapshots}
    observed_queries = {query.query_id: query for query in observed.query_snapshots}
    partial_equivalences: dict[tuple[str, str], set[str]] = {}
    if reference.partial_claim_equivalences.knowledge_state is KnowledgeState.PRESENT:
        for equivalence in reference.partial_claim_equivalences.value or ():
            partial_equivalences.setdefault(
                (equivalence.query_id, equivalence.reference_claim_id), set()
            ).add(equivalence.accepted_observed_semantic_checksum)
    query_results: list[QueryEvaluationResult] = []
    residuals: list[ResidualEvent] = []
    if observed.report_checksum != reference.snapshot.report_checksum:
        residuals.append(
            _residual_event(
                dimension=ResidualDimension.COMPLETE_REPORT,
                scope_kind=ResidualScopeKind.REPORT,
                scope_id=observed.report_id,
                match_outcome=MatchOutcome.INCORRECT,
                impact_on_claim="The complete user-consumed ReportBundle differs from the reference.",
            )
        )
    if (
        observed.global_report_resolution_checksum
        != reference.snapshot.global_report_resolution_checksum
    ):
        residuals.append(
            _residual_event(
                dimension=ResidualDimension.GLOBAL_REPORT_RESOLUTION,
                scope_kind=ResidualScopeKind.REPORT,
                scope_id=observed.report_id,
                match_outcome=MatchOutcome.INCORRECT,
                impact_on_claim="Global report resolution differs from the independent reference.",
            )
        )
    for query_id in sorted(set(reference_queries) - set(observed_queries)):
        residuals.append(
            _residual_event(
                dimension=ResidualDimension.QUERY_MEMBERSHIP,
                scope_kind=ResidualScopeKind.QUERY,
                scope_id=query_id,
                query_id=query_id,
                match_outcome=MatchOutcome.MISSING,
                impact_on_claim="A reference query is missing from the observed report.",
            )
        )
    for query_id in sorted(set(observed_queries) - set(reference_queries)):
        residuals.append(
            _residual_event(
                dimension=ResidualDimension.QUERY_MEMBERSHIP,
                scope_kind=ResidualScopeKind.QUERY,
                scope_id=query_id,
                query_id=query_id,
                match_outcome=MatchOutcome.UNEXPECTED,
                impact_on_claim="The observed report contains a query absent from the reference.",
            )
        )
    for query_id, expected in reference_queries.items():
        result, query_residuals = _score_query(
            observed_queries.get(query_id), expected, partial_equivalences
        )
        query_results.append(result)
        residuals.extend(query_residuals)

    claim_count = sum(len(query.claims) for query in reference.snapshot.query_snapshots)
    axis_count = sum(len(query.adequacy_axes) for query in reference.snapshot.query_snapshots)
    reference_claims = [
        claim for query in reference.snapshot.query_snapshots for claim in query.claims
    ]
    decisive_claim_ids_by_query: dict[str, set[str]] = {}
    if all(claim.decisive.knowledge_state is KnowledgeState.PRESENT for claim in reference_claims):
        decisive_claim_ids_by_query = {
            query.query_id: {claim.claim_id for claim in query.claims if bool(claim.decisive.value)}
            for query in reference.snapshot.query_snapshots
        }
        decisive_count = KnowledgeValue[int](
            knowledge_state=KnowledgeState.PRESENT,
            value=sum(len(claim_ids) for claim_ids in decisive_claim_ids_by_query.values()),
            evidence_ids=tuple(
                sorted(
                    {
                        evidence_id
                        for claim in reference_claims
                        for evidence_id in claim.decisive.evidence_ids
                    }
                )
            ),
            query_scope_id=observed.report_id,
        )
    else:
        decisive_count = KnowledgeValue[int](
            knowledge_state=KnowledgeState.UNKNOWN,
            rationale="Decisive-claim designation is not closed for every reference claim.",
            query_scope_id=observed.report_id,
        )
    denominators = EvaluationDenominators(
        report_count=1,
        query_count=len(reference_queries),
        missing_query_count=len(set(reference_queries) - set(observed_queries)),
        unexpected_query_count=len(set(observed_queries) - set(reference_queries)),
        global_report_resolution_count=1,
        claim_count=claim_count,
        decisive_claim_count=decisive_count,
        adequacy_axis_count=axis_count,
        evidence_correctness_count=claim_count,
        proof_correctness_count=claim_count,
    )
    blockers: list[ScientificReviewRequirement] = []
    process_fields, process_complete = _process_fields(
        observed, process_observations, process_report_bundles
    )
    if not process_complete:
        blockers.append(
            ScientificReviewRequirement(
                issue_id=EVALUATION_PROCESS_METRICS_REVIEW_ISSUE_ID,
                rationale=(
                    "Timing, correction and question-usefulness observations require independent "
                    "review before interpretation."
                ),
            )
        )
    if reference.purpose is IndependentReferencePurpose.CONFORMANCE_ONLY:
        status = EvaluationStatus.CONFORMANCE_ONLY
        scientific_use_permitted = False
        blockers.append(
            ScientificReviewRequirement(
                issue_id=CONFORMANCE_REFERENCE_REVIEW_ISSUE_ID,
                rationale=(
                    "Tiny deterministic fixtures verify implementation only; they are not gold, "
                    "reference-stability evidence or measured scientific performance."
                ),
            )
        )
    else:
        status = EvaluationStatus.EVALUATED_WITH_INDEPENDENT_REFERENCE
        scientific_use_permitted = False
        if not _reference_stability_is_resolved(reference, reference_stability_reports):
            blockers.append(
                ScientificReviewRequirement(
                    issue_id=REFERENCE_STABILITY_REVIEW_ISSUE_ID,
                    rationale="Independent reference lacks a reviewed reference-stability report.",
                )
            )
        if reference.partial_claim_equivalences.knowledge_state is KnowledgeState.UNKNOWN:
            blockers.append(
                ScientificReviewRequirement(
                    issue_id=PARTIAL_CLAIM_MATCH_REVIEW_ISSUE_ID,
                    rationale=(
                        "Partial claim matching requires a reviewed equivalence policy; exact "
                        "matches remain reportable but partial performance is not closed."
                    ),
                )
            )
        blockers.append(
            ScientificReviewRequirement(
                issue_id=EVALUATION_SCIENTIFIC_HOLD_ISSUE_ID,
                rationale=(
                    "The deterministic evaluator is not a release authority. Scientific use "
                    "requires externally governed reference stability, residual audit, precision "
                    "analysis and a policy-pinned decision."
                ),
            )
        )

    if residuals:
        residual_value = KnowledgeValue[tuple[ResidualEvent, ...]](
            knowledge_state=KnowledgeState.PRESENT,
            value=tuple(residuals),
            evidence_ids=reference.evidence_ids,
            query_scope_id=observed.report_id,
        )
    else:
        residual_value = KnowledgeValue[tuple[ResidualEvent, ...]](
            knowledge_state=KnowledgeState.ABSENT_EXPLICIT,
            evidence_ids=reference.evidence_ids,
            query_scope_id=observed.report_id,
        )
    false_certainty_events = {
        (item.scope_kind, item.scope_id)
        for item in residuals
        if item.false_certainty.knowledge_state is KnowledgeState.PRESENT
        and item.false_certainty.value is True
    }
    false_certainty_event_count = len(false_certainty_events)
    false_certainty_classification_closed = all(
        item.false_certainty.knowledge_state is KnowledgeState.PRESENT for item in residuals
    )
    count_evidence = tuple(
        sorted(
            {
                *reference.evidence_ids,
                *(
                    evidence_id
                    for item in residuals
                    if item.false_certainty.knowledge_state is KnowledgeState.PRESENT
                    and item.false_certainty.value is True
                    for evidence_id in item.false_certainty.evidence_ids
                ),
            }
        )
    )
    summary_scope: KnowledgeValue[str]
    summary_denominator: KnowledgeValue[int]
    summary_event_count: KnowledgeValue[int]
    summary_rate: KnowledgeValue[Decimal]
    if false_certainty_classification_closed:
        summary_event_count = KnowledgeValue[int](
            knowledge_state=KnowledgeState.PRESENT,
            value=false_certainty_event_count,
            evidence_ids=count_evidence,
            query_scope_id=observed.report_id,
        )
    else:
        summary_event_count = _unknown(
            scope=observed.report_id,
            rationale=(
                "At least one material residual lacks a reviewed false-certainty classification."
            ),
        )
    blockers.append(
        ScientificReviewRequirement(
            issue_id=FALSE_CERTAINTY_PROTOCOL_REVIEW_ISSUE_ID,
            rationale=(
                "False-certainty scope, denominator, rate and severity remain UNKNOWN until an "
                "independently governed preregistration, population manifest, event-unit pin and "
                "severity-policy review are resolved outside caller control."
            ),
        )
    )
    summary_scope = _unknown(
        scope=observed.report_id,
        rationale="No independently governed false-certainty scope has been resolved.",
    )
    summary_denominator = _unknown(
        scope=observed.report_id,
        rationale="No independently governed population manifest has been resolved.",
    )
    summary_rate = _unknown(
        scope=observed.report_id,
        rationale=(
            "A false-certainty rate requires a governed scope, recomputed denominator, exact "
            "event-unit identity and complete residual classification."
        ),
    )
    false_certainty_value = KnowledgeValue[FalseCertaintySummary](
        knowledge_state=KnowledgeState.PRESENT,
        value=FalseCertaintySummary(
            scope=summary_scope,
            denominator=summary_denominator,
            event_count=summary_event_count,
            rate=summary_rate,
            severity=KnowledgeValue[tuple[ResidualSeverity, ...]](
                knowledge_state=KnowledgeState.UNKNOWN,
                rationale=(
                    "False-certainty severity requires application of the independently reviewed "
                    "severity policy to blind residual findings."
                ),
                query_scope_id=observed.report_id,
            ),
        ),
        evidence_ids=count_evidence,
        query_scope_id=observed.report_id,
    )
    return _build_end_to_end_report(
        {
            "report_scope_id": observed.report_id,
            "observed_snapshot_checksum": observed.content_checksum,
            "reference_checksum": KnowledgeValue[str](
                knowledge_state=KnowledgeState.PRESENT,
                value=reference.content_checksum,
                evidence_ids=reference_value.evidence_ids,
                query_scope_id=observed.report_id,
            ),
            "status": status,
            "scientific_use_permitted": scientific_use_permitted,
            "denominators": KnowledgeValue[EvaluationDenominators](
                knowledge_state=KnowledgeState.PRESENT,
                value=denominators,
                evidence_ids=reference.evidence_ids,
                query_scope_id=observed.report_id,
            ),
            "complete_report_match": KnowledgeValue[bool](
                knowledge_state=KnowledgeState.PRESENT,
                value=observed.report_checksum == reference.snapshot.report_checksum,
                evidence_ids=reference.evidence_ids,
                query_scope_id=observed.report_id,
            ),
            "global_report_resolution_match": KnowledgeValue[bool](
                knowledge_state=KnowledgeState.PRESENT,
                value=(
                    observed.global_report_resolution_checksum
                    == reference.snapshot.global_report_resolution_checksum
                ),
                evidence_ids=reference.evidence_ids,
                query_scope_id=observed.report_id,
            ),
            "query_results": KnowledgeValue[tuple[QueryEvaluationResult, ...]](
                knowledge_state=KnowledgeState.PRESENT,
                value=tuple(query_results),
                evidence_ids=reference.evidence_ids,
                query_scope_id=observed.report_id,
            ),
            "residuals": residual_value,
            "false_certainty": false_certainty_value,
            **process_fields,
            "blockers": tuple(blockers),
        }
    )


def snapshot_report_bundle(report: ReportBundle) -> ReportEvaluationSnapshot:
    """Project the actual Task-6 ReportBundle; no evaluator-supplied verdict is accepted."""

    query_snapshots: list[QueryEvaluationSnapshot] = []
    for section in report.query_sections:
        report_evidence_ids = tuple(record.evidence_id for record in report.evidence_records)
        questions = tuple(question.question_id for question in section.questions)
        claims: list[ClaimEvaluationSnapshot] = []
        for claim in section.claim_set.claims:
            if claim.determinability_state is DeterminabilityState.DETERMINATE:
                unresolved_risk_ids = KnowledgeValue[tuple[str, ...]](
                    knowledge_state=KnowledgeState.NOT_APPLICABLE,
                    rationale="The derived claim is resolved.",
                    claim_scope_id=claim.claim_id,
                )
                actionable_question_ids = KnowledgeValue[tuple[str, ...]](
                    knowledge_state=KnowledgeState.NOT_APPLICABLE,
                    rationale="The derived claim is resolved.",
                    claim_scope_id=claim.claim_id,
                )
            else:
                unresolved = tuple(
                    sorted(
                        {
                            reference.predicate_id
                            for step in claim.proof_trace
                            for reference in step.predicate_references
                            if reference.predicate_value.knowledge_state
                            not in {
                                KnowledgeState.PRESENT,
                                KnowledgeState.ABSENT_EXPLICIT,
                                KnowledgeState.NOT_APPLICABLE,
                            }
                        }
                    )
                )
                if not unresolved and claim.state_contract_review is not None:
                    unresolved = (claim.state_contract_review.issue_id,)
                unresolved_risk_ids = KnowledgeValue[tuple[str, ...]](
                    knowledge_state=KnowledgeState.PRESENT,
                    value=unresolved,
                    evidence_ids=tuple(
                        sorted(
                            {
                                evidence_id
                                for step in claim.proof_trace
                                for reference in step.predicate_references
                                for evidence_id in reference.predicate_value.evidence_ids
                            }
                        )
                    )
                    or report_evidence_ids,
                    claim_scope_id=claim.claim_id,
                )
                actionable_question_ids = KnowledgeValue[tuple[str, ...]](
                    knowledge_state=KnowledgeState.UNKNOWN,
                    rationale=(
                        "Report questions are query-scoped; no reviewed claim-question attribution "
                        "is available."
                    ),
                    claim_scope_id=claim.claim_id,
                )
            evidence_ids = tuple(
                sorted(
                    {
                        *claim.value.evidence_ids,
                        *(
                            evidence_id
                            for step in claim.proof_trace
                            for reference in step.predicate_references
                            for evidence_id in reference.predicate_value.evidence_ids
                        ),
                    }
                )
            )
            evidence_record_ids: KnowledgeValue[tuple[str, ...]]
            evidence_content_checksum: KnowledgeValue[str]
            if evidence_ids:
                evidence_record_ids = KnowledgeValue[tuple[str, ...]](
                    knowledge_state=KnowledgeState.PRESENT,
                    value=evidence_ids,
                    evidence_ids=evidence_ids,
                    claim_scope_id=claim.claim_id,
                )
                records_by_id = {record.evidence_id: record for record in report.evidence_records}
                evidence_content_checksum = KnowledgeValue[str](
                    knowledge_state=KnowledgeState.PRESENT,
                    value=content_checksum(
                        [
                            records_by_id[evidence_id].model_dump(mode="json")
                            for evidence_id in evidence_ids
                        ]
                    ),
                    evidence_ids=evidence_ids,
                    claim_scope_id=claim.claim_id,
                )
            else:
                evidence_record_ids = KnowledgeValue[tuple[str, ...]](
                    knowledge_state=KnowledgeState.UNKNOWN,
                    rationale="The report claim has no directly linked evidence record.",
                    claim_scope_id=claim.claim_id,
                )
                evidence_content_checksum = KnowledgeValue[str](
                    knowledge_state=KnowledgeState.UNKNOWN,
                    rationale="Evidence content cannot be compared without linked records.",
                    claim_scope_id=claim.claim_id,
                )
            claims.append(
                ClaimEvaluationSnapshot(
                    query_id=section.inferential_query.id,
                    claim_id=claim.claim_id,
                    decisive=KnowledgeValue[bool](
                        knowledge_state=KnowledgeState.UNKNOWN,
                        rationale=(
                            "The ReportBundle does not carry an independently reviewed decisive-"
                            "claim designation."
                        ),
                        claim_scope_id=claim.claim_id,
                    ),
                    semantic_value_checksum=content_checksum(
                        {
                            "claim_type": claim.claim_type,
                            "value": claim.value.model_dump(mode="json"),
                            "support_grade": claim.support_grade.model_dump(mode="json"),
                            "assumptions": claim.assumptions,
                            "theory_clauses": claim.theory_clauses,
                        }
                    ),
                    determinability_state=claim.determinability_state,
                    evidence_record_ids=evidence_record_ids,
                    evidence_content_checksum=evidence_content_checksum,
                    proof_trace_checksum=content_checksum(
                        [step.model_dump(mode="json") for step in claim.proof_trace]
                    ),
                    unresolved_risk_ids=unresolved_risk_ids,
                    actionable_question_ids=actionable_question_ids,
                    false_certainty_categories=KnowledgeValue[tuple[FalseCertaintyCategory, ...]](
                        knowledge_state=KnowledgeState.UNKNOWN,
                        rationale=(
                            "False-certainty category is assigned by the independent audit, "
                            "not by report generation."
                        ),
                        claim_scope_id=claim.claim_id,
                    ),
                )
            )
        resolution = TrivialExplicitReportResolutionPolicy().resolve(section.claim_set)
        query_snapshots.append(
            QueryEvaluationSnapshot(
                query_id=section.inferential_query.id,
                report_resolution_checksum=content_checksum(resolution.model_dump(mode="json")),
                claims=tuple(claims),
                adequacy_axes=tuple(
                    AdequacyAxisSnapshot(
                        query_id=evaluation.inferential_query_id,
                        axis_id=evaluation.axis,
                        outcome_checksum=content_checksum(
                            evaluation.outcome.model_dump(mode="json")
                        ),
                        communicated_positive=KnowledgeValue[bool](
                            knowledge_state=KnowledgeState.NOT_APPLICABLE,
                            rationale=(
                                "The canonical PRD v8 ReportBundle communicates an epistemic "
                                "adequacy axis, never a positive design verdict."
                            ),
                            query_scope_id=evaluation.inferential_query_id,
                        ),
                    )
                    for evaluation in section.adequacy_evaluations
                ),
                question_attributions=tuple(
                    QuestionAttributionSnapshot(
                        query_id=section.inferential_query.id,
                        question_id=question_id,
                        claim_ids=KnowledgeValue[tuple[str, ...]](
                            knowledge_state=KnowledgeState.UNKNOWN,
                            rationale=(
                                "Question-to-claim attribution requires independent review; the "
                                "report question is retained only at query scope."
                            ),
                            query_scope_id=section.inferential_query.id,
                        ),
                    )
                    for question_id in questions
                ),
            )
        )
    return build_report_evaluation_snapshot(
        report_id=report.report_id,
        report_checksum=report.content_checksum,
        global_report_resolution_checksum=content_checksum(
            report.report_resolution.model_dump(mode="json")
        ),
        query_snapshots=tuple(query_snapshots),
    )


__all__ = [
    "build_evaluation_process_observations",
    "build_false_certainty_metric_protocol",
    "build_independent_report_reference",
    "build_reference_stability_report",
    "build_report_evaluation_snapshot",
    "evaluate_end_to_end",
    "snapshot_report_bundle",
    "summarize_blind_residual_audit",
]
