"""Deterministic report-level scoring for the PRD v8 evaluation boundary."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any

from ntruth.evaluation_v8.models import (
    CONFORMANCE_REFERENCE_REVIEW_ISSUE_ID,
    EVALUATION_REFERENCE_REVIEW_ISSUE_ID,
    EVALUATION_SCIENTIFIC_HOLD_ISSUE_ID,
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
    EvaluationStatus,
    FalseCertaintyCategory,
    IndependentReferencePurpose,
    IndependentReportReference,
    MatchOutcome,
    MatchSummary,
    PartialClaimEquivalence,
    QueryEvaluationResult,
    QueryEvaluationSnapshot,
    ReferenceStabilityComponentRecord,
    ReferenceStabilityConclusion,
    ReferenceStabilityPolicyPin,
    ReferenceStabilityReport,
    ReportEvaluationSnapshot,
    ResidualAuditFinding,
    ResidualEvent,
    ResidualOrigin,
    ResidualSeverity,
)
from ntruth.schemas.claims import DeterminabilityState
from ntruth.schemas.core import content_checksum
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.report_resolution import TrivialExplicitReportResolutionPolicy
from ntruth.schemas.support import ScientificReviewRequirement

if TYPE_CHECKING:
    from ntruth.schemas.report_bundle import ReportBundle


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


def build_independent_report_reference(
    *,
    reference_id: str,
    purpose: IndependentReferencePurpose,
    report_scope_id: str,
    snapshot: ReportEvaluationSnapshot,
    source_record_ids: tuple[str, ...],
    evidence_ids: tuple[str, ...],
    reviewer_actor_ids: tuple[str, ...],
    reference_stability_report_checksum: KnowledgeValue[str] | None = None,
    partial_claim_equivalences: KnowledgeValue[tuple[PartialClaimEquivalence, ...]] | None = None,
) -> IndependentReportReference:
    """Address a reference and make conformance-only purpose non-upgradable."""

    if reference_stability_report_checksum is None:
        if purpose is IndependentReferencePurpose.CONFORMANCE_ONLY:
            reference_stability_report_checksum = _not_applicable_checksum(
                scope=report_scope_id,
                rationale="Conformance fixtures are not scientific reference-stability evidence.",
            )
        else:
            reference_stability_report_checksum = _unknown(
                scope=report_scope_id,
                rationale="No independently reviewed reference-stability report was supplied.",
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
        "reference_stability_report_checksum": reference_stability_report_checksum,
        "partial_claim_equivalences": partial_claim_equivalences,
    }
    draft = IndependentReportReference.model_construct(content_checksum="0" * 64, **fields)
    checksum = content_checksum(draft.model_dump(mode="json", exclude={"content_checksum"}))
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
    draft = ReferenceStabilityReport.model_construct(content_checksum="0" * 64, **fields)
    checksum = content_checksum(draft.model_dump(mode="json", exclude={"content_checksum"}))
    return ReferenceStabilityReport(content_checksum=checksum, **fields)


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
    draft = BlindResidualAuditResult.model_construct(
        result_id="RESIDUAL-AUDIT-PENDING", content_checksum="0" * 64, **fields
    )
    checksum = content_checksum(
        draft.model_dump(mode="json", exclude={"result_id", "content_checksum"})
    )
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
) -> AbstentionDisposition:
    if (
        observed.determinability_state is DeterminabilityState.DETERMINATE
        and reference.determinability_state is not DeterminabilityState.DETERMINATE
    ):
        return AbstentionDisposition.FALSE_CERTAINTY
    if observed.determinability_state is DeterminabilityState.DETERMINATE:
        return AbstentionDisposition.RESOLVED
    if observed.actionable_question_ids.knowledge_state is KnowledgeState.PRESENT:
        return AbstentionDisposition.ACTIONABLE_ABSTENTION
    if observed.unresolved_risk_ids.knowledge_state is KnowledgeState.PRESENT:
        return AbstentionDisposition.UNRESOLVED_RISK_DETECTED
    return AbstentionDisposition.UNACTIONABLE_ABSTENTION


def _unknown_residual_dimension[T](claim_id: str, rationale: str) -> KnowledgeValue[T]:
    return KnowledgeValue[T](
        knowledge_state=KnowledgeState.UNKNOWN,
        rationale=rationale,
        claim_scope_id=claim_id,
    )


def _false_certainty_residuals(
    *,
    observed: ClaimEvaluationSnapshot,
    reference: ClaimEvaluationSnapshot,
) -> tuple[ResidualEvent, ...]:
    categories = reference.false_certainty_categories
    if categories.knowledge_state is KnowledgeState.PRESENT:
        category_values: tuple[FalseCertaintyCategory | None, ...] = tuple(categories.value or ())
    else:
        category_values = (None,)
    residuals: list[ResidualEvent] = []
    for index, category in enumerate(category_values):
        category_value: KnowledgeValue[FalseCertaintyCategory]
        if category is None:
            category_value = _unknown_residual_dimension(
                observed.claim_id,
                "The independent audit has not classified the false-certainty condition.",
            )
        else:
            category_value = KnowledgeValue[FalseCertaintyCategory](
                knowledge_state=KnowledgeState.PRESENT,
                value=category,
                evidence_ids=categories.evidence_ids,
                claim_scope_id=observed.claim_id,
            )
        origin: KnowledgeValue[ResidualOrigin] = _unknown_residual_dimension(
            observed.claim_id,
            "Error origin requires blind residual re-adjudication.",
        )
        severity: KnowledgeValue[ResidualSeverity] = _unknown_residual_dimension(
            observed.claim_id,
            "Severity requires the preregistered residual-audit rubric.",
        )
        residuals.append(
            ResidualEvent(
                residual_id=f"RESIDUAL-{content_checksum((observed.claim_id, category, index))[:20]}",
                query_id=observed.query_id,
                claim_id=observed.claim_id,
                false_certainty_category=category_value,
                origin=origin,
                severity=severity,
                impact_on_claim=(
                    "Observed output was DETERMINATE while the independent reference retained "
                    "an unresolved state."
                ),
            )
        )
    return tuple(residuals)


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
    residuals: list[ResidualEvent] = []
    for claim_id, expected in reference_claims.items():
        actual = observed_claims.get(claim_id)
        if actual is None:
            claim_outcomes[claim_id] = MatchOutcome.MISSING
            evidence_outcomes[claim_id] = MatchOutcome.MISSING
            proof_outcomes[claim_id] = MatchOutcome.MISSING
            abstention[AbstentionDisposition.NOT_EVALUABLE_MISSING_OUTPUT] += 1
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
        disposition = _abstention_disposition(actual, expected)
        abstention[disposition] += 1
        if disposition is AbstentionDisposition.FALSE_CERTAINTY:
            residuals.extend(_false_certainty_residuals(observed=actual, reference=expected))

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
    observed_claim_ids = set(observed_claims)
    reference_claim_ids = set(reference_claims)
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
    )
    return result, tuple(residuals)


def evaluate_end_to_end(
    observed: ReportEvaluationSnapshot,
    reference_value: KnowledgeValue[IndependentReportReference],
) -> EndToEndEvaluationReport:
    """Score a complete report or emit explicit UNKNOWNs when reference is absent."""

    if reference_value.query_scope_id != observed.report_id:
        raise ValueError("reference KnowledgeValue belongs to another report scope")
    evaluation_id = f"E2E-{content_checksum((observed.content_checksum, reference_value.model_dump(mode='json')))[:20]}"
    if (
        reference_value.knowledge_state is not KnowledgeState.PRESENT
        or reference_value.value is None
    ):
        rationale = "End-to-end evaluation requires an independently reviewed report reference."
        return EndToEndEvaluationReport(
            evaluation_id=evaluation_id,
            observed_snapshot_checksum=observed.content_checksum,
            reference_checksum=_unknown(scope=observed.report_id, rationale=rationale),
            status=EvaluationStatus.BLOCKED,
            scientific_use_permitted=False,
            denominators=_unknown(scope=observed.report_id, rationale=rationale),
            global_report_resolution_match=_unknown(scope=observed.report_id, rationale=rationale),
            query_results=_unknown(scope=observed.report_id, rationale=rationale),
            residuals=_unknown(scope=observed.report_id, rationale=rationale),
            blockers=(
                ScientificReviewRequirement(
                    issue_id=EVALUATION_REFERENCE_REVIEW_ISSUE_ID,
                    rationale=rationale,
                ),
            ),
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
    for query_id, expected in reference_queries.items():
        result, query_residuals = _score_query(
            observed_queries.get(query_id), expected, partial_equivalences
        )
        query_results.append(result)
        residuals.extend(query_residuals)

    claim_count = sum(len(query.claims) for query in reference.snapshot.query_snapshots)
    axis_count = sum(len(query.adequacy_axes) for query in reference.snapshot.query_snapshots)
    denominators = EvaluationDenominators(
        query_count=len(reference_queries),
        missing_query_count=len(set(reference_queries) - set(observed_queries)),
        unexpected_query_count=len(set(observed_queries) - set(reference_queries)),
        global_report_resolution_count=1,
        claim_count=claim_count,
        adequacy_axis_count=axis_count,
        evidence_correctness_count=claim_count,
        proof_correctness_count=claim_count,
    )
    blockers: list[ScientificReviewRequirement] = []
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
        if (
            reference.reference_stability_report_checksum.knowledge_state
            is not KnowledgeState.PRESENT
        ):
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
    return EndToEndEvaluationReport(
        evaluation_id=evaluation_id,
        observed_snapshot_checksum=observed.content_checksum,
        reference_checksum=KnowledgeValue[str](
            knowledge_state=KnowledgeState.PRESENT,
            value=reference.content_checksum,
            evidence_ids=reference_value.evidence_ids,
            query_scope_id=observed.report_id,
        ),
        status=status,
        scientific_use_permitted=scientific_use_permitted,
        denominators=KnowledgeValue[EvaluationDenominators](
            knowledge_state=KnowledgeState.PRESENT,
            value=denominators,
            evidence_ids=reference.evidence_ids,
            query_scope_id=observed.report_id,
        ),
        global_report_resolution_match=KnowledgeValue[bool](
            knowledge_state=KnowledgeState.PRESENT,
            value=(
                observed.global_report_resolution_checksum
                == reference.snapshot.global_report_resolution_checksum
            ),
            evidence_ids=reference.evidence_ids,
            query_scope_id=observed.report_id,
        ),
        query_results=KnowledgeValue[tuple[QueryEvaluationResult, ...]](
            knowledge_state=KnowledgeState.PRESENT,
            value=tuple(query_results),
            evidence_ids=reference.evidence_ids,
            query_scope_id=observed.report_id,
        ),
        residuals=residual_value,
        blockers=tuple(blockers),
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
                    knowledge_state=KnowledgeState.PRESENT,
                    value=questions,
                    evidence_ids=report_evidence_ids,
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
                    )
                    for evaluation in section.adequacy_evaluations
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
    "build_independent_report_reference",
    "build_reference_stability_report",
    "build_report_evaluation_snapshot",
    "evaluate_end_to_end",
    "snapshot_report_bundle",
    "summarize_blind_residual_audit",
]
