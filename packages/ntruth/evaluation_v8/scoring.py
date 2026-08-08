"""Deterministic report-level scoring for the PRD v8 evaluation boundary."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from ntruth.evaluation_v8.models import (
    CONFORMANCE_REFERENCE_REVIEW_ISSUE_ID,
    EVALUATION_PROCESS_METRICS_REVIEW_ISSUE_ID,
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
    EvaluationProcessObservations,
    EvaluationStatus,
    FalseCertaintyCategory,
    FalseCertaintyDenominatorScope,
    FalseCertaintySummary,
    IndependentReferencePurpose,
    IndependentReportReference,
    MatchOutcome,
    MatchSummary,
    PartialClaimEquivalence,
    QueryEvaluationResult,
    QueryEvaluationSnapshot,
    QuestionAttributionSnapshot,
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
    reference_stability_report: ReferenceStabilityReport | None = None,
    reference_stability_report_checksum: KnowledgeValue[str] | None = None,
    partial_claim_equivalences: KnowledgeValue[tuple[PartialClaimEquivalence, ...]] | None = None,
) -> IndependentReportReference:
    """Address a reference and make conformance-only purpose non-upgradable."""

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
    draft = ReferenceStabilityReport.model_construct(
        artifact_id="REFERENCE-STABILITY-PENDING", content_checksum="0" * 64, **fields
    )
    checksum = content_checksum(
        draft.model_dump(mode="json", exclude={"artifact_id", "content_checksum"})
    )
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
    claim_outcome: MatchOutcome,
) -> AbstentionDisposition:
    if observed.determinability_state is DeterminabilityState.DETERMINATE and (
        reference.determinability_state is not DeterminabilityState.DETERMINATE
        or claim_outcome is MatchOutcome.INCORRECT
    ):
        return AbstentionDisposition.FALSE_CERTAINTY
    if observed.determinability_state is DeterminabilityState.DETERMINATE:
        return AbstentionDisposition.RESOLVED
    if observed.actionable_question_ids.knowledge_state is KnowledgeState.PRESENT:
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
    identity = (
        dimension,
        scope_kind,
        scope_id,
        match_outcome,
        query_id,
        claim_id,
        axis_id,
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
                dimension=ResidualDimension.CLAIM_SEMANTICS,
                scope_kind=ResidualScopeKind.CLAIM,
                scope_id=observed.claim_id,
                query_id=observed.query_id,
                claim_id=observed.claim_id,
                match_outcome=MatchOutcome.INCORRECT,
                false_certainty_category=category_value,
                impact_on_claim=(
                    "Observed output was DETERMINATE while the independent reference retained "
                    "an unresolved state or a materially different semantic value."
                ),
            )
        )
    return tuple(residuals)


def _build_end_to_end_report(fields: dict[str, Any]) -> EndToEndEvaluationReport:
    draft = EndToEndEvaluationReport.model_construct(
        evaluation_id="E2E-PENDING",
        content_checksum="0" * 64,
        **fields,
    )
    checksum = content_checksum(
        draft.model_dump(mode="json", exclude={"evaluation_id", "content_checksum"})
    )
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
                    impact_on_claim="Observed proof lineage differs from the independent reference.",
                )
            )

    for claim_id in sorted(set(observed_claims) - set(reference_claims)):
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
            residuals.append(
                _residual_event(
                    dimension=ResidualDimension.ADEQUACY_AXIS,
                    scope_kind=ResidualScopeKind.ADEQUACY_AXIS,
                    scope_id=axis_id,
                    query_id=reference.query_id,
                    axis_id=axis_id,
                    match_outcome=outcome,
                    impact_on_claim="Observed design-adequacy axis differs from the reference.",
                )
            )
    for axis_id in sorted(set(observed_axes) - set(reference_axes)):
        residuals.append(
            _residual_event(
                dimension=ResidualDimension.ADEQUACY_AXIS,
                scope_kind=ResidualScopeKind.ADEQUACY_AXIS,
                scope_id=axis_id,
                query_id=reference.query_id,
                axis_id=axis_id,
                match_outcome=MatchOutcome.UNEXPECTED,
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
    report_scope_id: str,
    observations: EvaluationProcessObservations | None,
) -> tuple[dict[str, KnowledgeValue[Any]], bool]:
    if observations is None:
        return _unknown_process_fields(report_scope_id), False
    if observations.report_scope_id != report_scope_id:
        raise ValueError("process observations belong to another report scope")
    timing = observations.time_to_confirmed_report
    if timing.knowledge_state is KnowledgeState.PRESENT and timing.value is not None:
        time_value = KnowledgeValue[Decimal](
            knowledge_state=KnowledgeState.PRESENT,
            value=timing.value.report_seconds,
            evidence_ids=timing.evidence_ids,
            query_scope_id=report_scope_id,
        )
        delta_value = KnowledgeValue[Decimal](
            knowledge_state=KnowledgeState.PRESENT,
            value=timing.value.report_seconds - timing.value.manual_baseline_seconds,
            evidence_ids=timing.evidence_ids,
            query_scope_id=report_scope_id,
        )
    else:
        rationale = "Report timing or its manual baseline remains unavailable."
        time_value = _unknown(scope=report_scope_id, rationale=rationale)
        delta_value = _unknown(scope=report_scope_id, rationale=rationale)
    fields: dict[str, KnowledgeValue[Any]] = {
        "time_to_confirmed_report_seconds": time_value,
        "review_time_delta_seconds": delta_value,
        "decisive_human_correction_count": observations.decisive_human_correction_count,
        "question_usefulness": observations.question_usefulness,
    }
    return fields, all(value.knowledge_state is KnowledgeState.PRESENT for value in fields.values())


def _reference_stability_is_resolved(
    reference: IndependentReportReference,
    reports: tuple[ReferenceStabilityReport, ...],
) -> bool:
    addressed = reference.reference_stability_report
    if addressed.knowledge_state is not KnowledgeState.PRESENT or addressed.value is None:
        return False
    matches = [report for report in reports if report.artifact_id == addressed.value.artifact_id]
    if len(matches) != 1:
        return False
    report = matches[0]
    return (
        report.content_checksum == addressed.value.content_checksum
        and report.report_id == addressed.value.report_scope_id == reference.report_scope_id
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
) -> EndToEndEvaluationReport:
    """Score a complete report or emit explicit UNKNOWNs when reference is absent."""

    if reference_value.query_scope_id != observed.report_id:
        raise ValueError("reference KnowledgeValue belongs to another report scope")
    if (
        reference_value.knowledge_state is not KnowledgeState.PRESENT
        or reference_value.value is None
    ):
        rationale = "End-to-end evaluation requires an independently reviewed report reference."
        process_fields, _ = _process_fields(observed.report_id, process_observations)
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
    process_fields, process_complete = _process_fields(observed.report_id, process_observations)
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
    decisive_denominator = decisive_count.value
    if (
        decisive_count.knowledge_state is KnowledgeState.PRESENT
        and decisive_denominator is not None
        and decisive_denominator > 0
    ):
        false_certainty_event_count = sum(
            len(
                set(result.false_certainty_claim_ids)
                & decisive_claim_ids_by_query.get(result.query_id, set())
            )
            for result in query_results
        )
        false_certainty_value: KnowledgeValue[FalseCertaintySummary] = KnowledgeValue[
            FalseCertaintySummary
        ](
            knowledge_state=KnowledgeState.PRESENT,
            value=FalseCertaintySummary(
                scope=FalseCertaintyDenominatorScope.DECISIVE_REFERENCE_CLAIMS,
                denominator=decisive_denominator,
                event_count=false_certainty_event_count,
                severity=KnowledgeValue[tuple[ResidualSeverity, ...]](
                    knowledge_state=KnowledgeState.UNKNOWN,
                    rationale=(
                        "False-certainty severity requires the preregistered blind residual-audit "
                        "rubric."
                    ),
                    query_scope_id=observed.report_id,
                ),
            ),
            evidence_ids=reference.evidence_ids,
            query_scope_id=observed.report_id,
        )
    else:
        false_certainty_value = KnowledgeValue[FalseCertaintySummary](
            knowledge_state=KnowledgeState.UNKNOWN,
            rationale="False-certainty denominator requires closed decisive-claim designations.",
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
    "build_independent_report_reference",
    "build_reference_stability_report",
    "build_report_evaluation_snapshot",
    "evaluate_end_to_end",
    "snapshot_report_bundle",
    "summarize_blind_residual_audit",
]
