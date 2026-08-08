from __future__ import annotations

import hashlib
import importlib
from decimal import Decimal

import pytest
from prd_v8_cluster_authority_fixtures import reviewed_cluster_authority
from pydantic import ValidationError

from ntruth.derivation_theory.loader import load_canonical_bundle
from ntruth.evaluation_v8 import (
    SUPPORTED_CLUSTER_ESTIMATOR_CHECKSUM,
    SUPPORTED_CLUSTER_ESTIMATOR_ID,
    AbstentionDisposition,
    AgreementObservation,
    AuditRole,
    AuditRoleAssignment,
    BlindResidualAuditProtocol,
    ClusterBootstrapProtocol,
    EvaluationStatus,
    FalseCertaintyCategory,
    GeneralizationUnit,
    GeneralizationUnitKind,
    IndependentReferencePurpose,
    IndependentReportReference,
    MatchOutcome,
    MetricGeneralizationContract,
    ReferenceStabilityComponent,
    ReferenceStabilityComponentRecord,
    ReportEvaluationSnapshot,
    ResidualAuditFinding,
    ResidualAuditSampleItem,
    ResidualAuditStratum,
    ResidualOrigin,
    ResidualSeverity,
    StabilityComponentObservation,
    build_cluster_metric_observation,
    build_independent_report_reference,
    build_reference_stability_report,
    build_report_evaluation_snapshot,
    cluster_bootstrap_precision,
    evaluate_end_to_end,
    snapshot_report_bundle,
    summarize_blind_residual_audit,
)
from ntruth.evaluation_v8.models import (
    AdequacyAxisSnapshot,
    ClaimEvaluationSnapshot,
    QueryEvaluationSnapshot,
    QuestionAttributionSnapshot,
)
from ntruth.schemas.claims import DeterminabilityState
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _not_applicable(scope: str) -> KnowledgeValue[tuple[str, ...]]:
    return KnowledgeValue[tuple[str, ...]](
        knowledge_state=KnowledgeState.NOT_APPLICABLE,
        rationale="The claim is resolved, so abstention metadata does not apply.",
        claim_scope_id=scope,
    )


def _present(values: tuple[str, ...], scope: str) -> KnowledgeValue[tuple[str, ...]]:
    return KnowledgeValue[tuple[str, ...]](
        knowledge_state=KnowledgeState.PRESENT,
        value=values,
        evidence_ids=(f"E-{scope}",),
        claim_scope_id=scope,
    )


def _adequacy_communication(query_id: str, *, positive: bool = False) -> KnowledgeValue[bool]:
    return KnowledgeValue[bool](
        knowledge_state=KnowledgeState.PRESENT,
        value=positive,
        evidence_ids=(f"E-ADEQUACY-{query_id}",),
        query_scope_id=query_id,
    )


def _claim(
    claim_id: str,
    *,
    state: DeterminabilityState,
    value: str,
    evidence: tuple[str, ...] = ("E-1",),
    proof: str = "proof",
    false_certainty: tuple[FalseCertaintyCategory, ...] | None = None,
) -> ClaimEvaluationSnapshot:
    unresolved = (
        _not_applicable(claim_id)
        if state is DeterminabilityState.DETERMINATE
        else _present((f"RISK-{claim_id}",), claim_id)
    )
    questions = (
        _not_applicable(claim_id)
        if state is DeterminabilityState.DETERMINATE
        else _present((f"Q-{claim_id}",), claim_id)
    )
    category_value: KnowledgeValue[tuple[FalseCertaintyCategory, ...]]
    if false_certainty:
        category_value = KnowledgeValue[tuple[FalseCertaintyCategory, ...]](
            knowledge_state=KnowledgeState.PRESENT,
            value=false_certainty,
            evidence_ids=(f"E-{claim_id}",),
            claim_scope_id=claim_id,
        )
    else:
        category_value = KnowledgeValue[tuple[FalseCertaintyCategory, ...]](
            knowledge_state=KnowledgeState.NOT_APPLICABLE,
            rationale="No material false-certainty condition is asserted for this claim.",
            claim_scope_id=claim_id,
        )
    return ClaimEvaluationSnapshot(
        query_id="IQ-1",
        claim_id=claim_id,
        decisive=KnowledgeValue[bool](
            knowledge_state=KnowledgeState.PRESENT,
            value=True,
            evidence_ids=(f"E-{claim_id}",),
            claim_scope_id=claim_id,
        ),
        semantic_value_checksum=_digest(value),
        determinability_state=state,
        evidence_record_ids=KnowledgeValue[tuple[str, ...]](
            knowledge_state=KnowledgeState.PRESENT,
            value=evidence,
            evidence_ids=evidence,
            claim_scope_id=claim_id,
        ),
        evidence_content_checksum=KnowledgeValue[str](
            knowledge_state=KnowledgeState.PRESENT,
            value=_digest("\0".join(evidence)),
            evidence_ids=evidence,
            claim_scope_id=claim_id,
        ),
        proof_trace_checksum=_digest(proof),
        unresolved_risk_ids=unresolved,
        actionable_question_ids=questions,
        false_certainty_categories=category_value,
    )


def _snapshot(
    *,
    claims: tuple[ClaimEvaluationSnapshot, ...],
    axis_value: str = "axis-a",
) -> ReportEvaluationSnapshot:
    return build_report_evaluation_snapshot(
        report_id="REPORT-1",
        report_checksum=_digest("full-report"),
        global_report_resolution_checksum=_digest("global-resolution"),
        query_snapshots=(
            QueryEvaluationSnapshot(
                query_id="IQ-1",
                report_resolution_checksum=_digest("partial"),
                claims=claims,
                adequacy_axes=(
                    AdequacyAxisSnapshot(
                        query_id="IQ-1",
                        axis_id="interference",
                        outcome_checksum=_digest(axis_value),
                        communicated_positive=_adequacy_communication("IQ-1"),
                    ),
                ),
                question_attributions=tuple(
                    QuestionAttributionSnapshot(
                        query_id="IQ-1",
                        question_id=question_id,
                        claim_ids=KnowledgeValue[tuple[str, ...]](
                            knowledge_state=KnowledgeState.PRESENT,
                            value=(claim.claim_id,),
                            evidence_ids=claim.actionable_question_ids.evidence_ids,
                            query_scope_id="IQ-1",
                        ),
                    )
                    for claim in claims
                    if claim.actionable_question_ids.knowledge_state is KnowledgeState.PRESENT
                    for question_id in claim.actionable_question_ids.value or ()
                ),
            ),
        ),
    )


def test_missing_reference_blocks_without_zero_denominator_claims() -> None:
    observed = _snapshot(claims=(_claim("C-1", state=DeterminabilityState.DETERMINATE, value="x"),))
    missing_reference = KnowledgeValue[IndependentReportReference](
        knowledge_state=KnowledgeState.UNKNOWN,
        rationale="No independently reviewed ReportBundle reference exists.",
        query_scope_id="REPORT-1",
    )

    result = evaluate_end_to_end(observed, missing_reference)

    assert result.status is EvaluationStatus.BLOCKED
    assert result.denominators.knowledge_state is KnowledgeState.UNKNOWN
    assert result.query_results.knowledge_state is KnowledgeState.UNKNOWN
    assert {item.issue_id for item in result.blockers} == {
        "SRR-V8-EVAL-REFERENCE",
        "SRR-V8-EVAL-PROCESS-METRICS",
    }


def test_snapshot_is_derived_from_the_actual_complete_report_bundle() -> None:
    quick_design_fixture = importlib.import_module("test_prd_v8_quick_design")
    module, submission = quick_design_fixture._submission()
    quick_design = module.run_quick_design_v8(
        submission,
        conformance_bundle=load_canonical_bundle(
            quick_design_fixture.runtime_fixture.REPOSITORY_ROOT
        ),
    )

    snapshot = snapshot_report_bundle(quick_design.report_bundle)

    assert snapshot.report_id == quick_design.report_bundle.report_id
    assert snapshot.report_checksum == quick_design.report_bundle.content_checksum
    assert tuple(query.query_id for query in snapshot.query_snapshots) == tuple(
        section.inferential_query.id for section in quick_design.report_bundle.query_sections
    )
    assert sum(len(query.claims) for query in snapshot.query_snapshots) == sum(
        len(claim_set.claims) for claim_set in quick_design.report_bundle.claim_sets
    )


def test_report_evaluation_retains_every_denominator_and_false_certainty_residual() -> None:
    observed = _snapshot(
        claims=(
            _claim("C-1", state=DeterminabilityState.DETERMINATE, value="wrong", proof="bad"),
            _claim(
                "C-2",
                state=DeterminabilityState.INSUFFICIENT_INFORMATION,
                value="unknown",
            ),
        ),
        axis_value="wrong-axis",
    )
    reference_snapshot = _snapshot(
        claims=(
            _claim(
                "C-1",
                state=DeterminabilityState.INSUFFICIENT_INFORMATION,
                value="reference",
                evidence=("E-reference",),
                proof="reference-proof",
                false_certainty=(FalseCertaintyCategory.DECISIVE_PRECONDITION_UNSUPPORTED,),
            ),
            _claim(
                "C-2",
                state=DeterminabilityState.INSUFFICIENT_INFORMATION,
                value="unknown",
            ),
        ),
        axis_value="reference-axis",
    )
    reference = build_independent_report_reference(
        reference_id="REF-CONFORMANCE-1",
        purpose=IndependentReferencePurpose.CONFORMANCE_ONLY,
        report_scope_id="REPORT-1",
        snapshot=reference_snapshot,
        source_record_ids=("SRC-CONFORMANCE",),
        evidence_ids=("E-REFERENCE",),
        reviewer_actor_ids=("REVIEWER-INDEPENDENT",),
    )
    reference_value = KnowledgeValue(
        knowledge_state=KnowledgeState.PRESENT,
        value=reference,
        evidence_ids=("E-REFERENCE",),
        query_scope_id="REPORT-1",
    )

    result = evaluate_end_to_end(observed, reference_value)

    assert result.status is EvaluationStatus.CONFORMANCE_ONLY
    assert result.scientific_use_permitted is False
    assert result.denominators.value is not None
    assert result.denominators.value.query_count == 1
    assert result.denominators.value.claim_count == 2
    assert result.denominators.value.adequacy_axis_count == 1
    assert result.denominators.value.evidence_correctness_count == 2
    assert result.denominators.value.proof_correctness_count == 2
    assert result.global_report_resolution_match.value is True
    query = result.query_results.value[0]  # type: ignore[index]
    assert query.claim_match.by_outcome[MatchOutcome.EXACT] == 1
    assert query.claim_match.by_outcome[MatchOutcome.INCORRECT] == 1
    assert query.adequacy_axis_match.by_outcome[MatchOutcome.INCORRECT] == 1
    assert query.evidence_correctness.by_outcome[MatchOutcome.INCORRECT] == 1
    assert query.proof_correctness.by_outcome[MatchOutcome.INCORRECT] == 1
    assert query.abstention_dispositions[AbstentionDisposition.FALSE_CERTAINTY] == 1
    assert result.residuals.knowledge_state is KnowledgeState.PRESENT
    residuals = result.residuals.value or ()
    assert {item.dimension.value for item in residuals} == {
        "EVIDENCE_CORRECTNESS",
        "PROOF_CORRECTNESS",
        "ADEQUACY_AXIS",
        "SUPPORT_CORRECTNESS",
    }
    false_certainty_residual = next(
        item
        for item in residuals
        if item.false_certainty_category.knowledge_state is KnowledgeState.PRESENT
    )
    assert false_certainty_residual.false_certainty_category.value == (
        FalseCertaintyCategory.DECISIVE_PRECONDITION_UNSUPPORTED
    )
    assert "SRR-V8-CONFORMANCE-REFERENCE-NONSCIENTIFIC" in {
        item.issue_id for item in result.blockers
    }
    with pytest.raises(ValidationError, match="not a scientific release authority"):
        type(result).model_validate(
            result.model_copy(update={"scientific_use_permitted": True}).model_dump(mode="python")
        )
    with pytest.raises(ValidationError, match="evaluation checksum mismatch"):
        type(result).model_validate(
            result.model_copy(
                update={"observed_snapshot_checksum": _digest("mutated-observation")}
            ).model_dump(mode="python")
        )


def test_missing_query_is_counted_and_never_borrows_another_query_claim() -> None:
    observed = _snapshot(claims=(_claim("C-1", state=DeterminabilityState.DETERMINATE, value="x"),))
    first_query = observed.query_snapshots[0]
    second_query = QueryEvaluationSnapshot(
        query_id="IQ-2",
        report_resolution_checksum=_digest("iq-2-resolution"),
        claims=(
            _claim("C-2", state=DeterminabilityState.DETERMINATE, value="y").model_copy(
                update={"query_id": "IQ-2"}
            ),
        ),
        adequacy_axes=(
            AdequacyAxisSnapshot(
                query_id="IQ-2",
                axis_id="interference",
                outcome_checksum=_digest("iq-2-axis"),
                communicated_positive=_adequacy_communication("IQ-2"),
            ),
        ),
    )
    reference_snapshot = build_report_evaluation_snapshot(
        report_id="REPORT-1",
        report_checksum=_digest("two-query-reference"),
        global_report_resolution_checksum=observed.global_report_resolution_checksum,
        query_snapshots=(first_query, second_query),
    )
    reference = build_independent_report_reference(
        reference_id="REF-CONFORMANCE-TWO-QUERY",
        purpose=IndependentReferencePurpose.CONFORMANCE_ONLY,
        report_scope_id="REPORT-1",
        snapshot=reference_snapshot,
        source_record_ids=("SRC-CONFORMANCE",),
        evidence_ids=("E-REFERENCE",),
        reviewer_actor_ids=("REVIEWER-INDEPENDENT",),
    )

    result = evaluate_end_to_end(
        observed,
        KnowledgeValue[IndependentReportReference](
            knowledge_state=KnowledgeState.PRESENT,
            value=reference,
            evidence_ids=("E-REFERENCE",),
            query_scope_id="REPORT-1",
        ),
    )

    assert result.denominators.value is not None
    assert result.denominators.value.query_count == 2
    assert result.denominators.value.missing_query_count == 1
    assert result.denominators.value.unexpected_query_count == 0
    missing_query = (result.query_results.value or ())[1]
    assert missing_query.query_id == "IQ-2"
    assert missing_query.claim_match.by_outcome[MatchOutcome.MISSING] == 1
    assert missing_query.claim_match.by_outcome[MatchOutcome.EXACT] == 0


def _audit_assignments(*, auditor: str) -> tuple[AuditRoleAssignment, ...]:
    return (
        AuditRoleAssignment(actor_id="ANNOTATOR-A", role=AuditRole.ORIGINAL_ANNOTATOR),
        AuditRoleAssignment(actor_id="REVIEWER-B", role=AuditRole.ORIGINAL_REVIEWER),
        AuditRoleAssignment(actor_id="ADJUDICATOR-C", role=AuditRole.ADJUDICATOR),
        AuditRoleAssignment(actor_id="GENERATOR-D", role=AuditRole.REPORT_GENERATOR),
        AuditRoleAssignment(actor_id=auditor, role=AuditRole.RESIDUAL_AUDITOR),
    )


def test_blind_residual_audit_enforces_role_separation() -> None:
    with pytest.raises(ValidationError, match=r"residual auditor.*not involved"):
        BlindResidualAuditProtocol(
            protocol_id="AUDIT-1",
            sample_manifest_checksum=_digest("sample"),
            sample_items=(
                ResidualAuditSampleItem(
                    report_id="REPORT-1",
                    query_id="IQ-1",
                    claim_id="C-1",
                    reference_id="REF-1",
                ),
            ),
            strata=tuple(ResidualAuditStratum),
            blind_to_original_output=True,
            role_assignments=_audit_assignments(auditor="GENERATOR-D"),
            evidence_ids=("E-AUDIT",),
        )

    protocol = BlindResidualAuditProtocol(
        protocol_id="AUDIT-1",
        sample_manifest_checksum=_digest("sample"),
        sample_items=(
            ResidualAuditSampleItem(
                report_id="REPORT-1",
                query_id="IQ-1",
                claim_id="C-1",
                reference_id="REF-1",
            ),
        ),
        strata=tuple(ResidualAuditStratum),
        blind_to_original_output=True,
        role_assignments=_audit_assignments(auditor="AUDITOR-E"),
        evidence_ids=("E-AUDIT",),
    )
    assert protocol.residual_auditor_ids == ("AUDITOR-E",)


def test_residual_audit_does_not_impute_unknown_as_zero() -> None:
    protocol = BlindResidualAuditProtocol(
        protocol_id="AUDIT-OPEN-WORLD",
        sample_manifest_checksum=_digest("sample-open-world"),
        sample_items=(
            ResidualAuditSampleItem(
                report_id="REPORT-1",
                query_id="IQ-1",
                claim_id="C-1",
                reference_id="REF-1",
            ),
        ),
        strata=tuple(ResidualAuditStratum),
        blind_to_original_output=True,
        role_assignments=_audit_assignments(auditor="AUDITOR-E"),
        evidence_ids=("E-AUDIT",),
    )
    finding = ResidualAuditFinding(
        finding_id="FINDING-1",
        report_id="REPORT-1",
        query_id="IQ-1",
        claim_id="C-1",
        reference_id="REF-1",
        decisive_error=KnowledgeValue[bool](
            knowledge_state=KnowledgeState.UNKNOWN,
            rationale="Blind re-adjudication is not complete.",
            claim_scope_id="C-1",
        ),
        false_certainty=KnowledgeValue[bool](
            knowledge_state=KnowledgeState.PRESENT,
            value=True,
            evidence_ids=("E-AUDIT",),
            claim_scope_id="C-1",
        ),
        human_review_introduced_error=KnowledgeValue[bool](
            knowledge_state=KnowledgeState.PRESENT,
            value=False,
            evidence_ids=("E-AUDIT",),
            claim_scope_id="C-1",
        ),
        origin=KnowledgeValue[ResidualOrigin](
            knowledge_state=KnowledgeState.UNKNOWN,
            rationale="Origin awaits blind residual classification.",
            claim_scope_id="C-1",
        ),
        severity=KnowledgeValue[ResidualSeverity](
            knowledge_state=KnowledgeState.UNKNOWN,
            rationale="Severity awaits the preregistered rubric.",
            claim_scope_id="C-1",
        ),
        stratum_values={
            stratum: f"CONFORMANCE-{stratum.value}" for stratum in ResidualAuditStratum
        },
        impact_on_claim=KnowledgeValue[str](
            knowledge_state=KnowledgeState.PRESENT,
            value="The reference retains a material caveat omitted by the report.",
            evidence_ids=("E-AUDIT",),
            claim_scope_id="C-1",
        ),
        evidence_ids=("E-AUDIT",),
    )

    result = summarize_blind_residual_audit(protocol, (finding,))

    assert result.decisive_error_count.knowledge_state is KnowledgeState.UNKNOWN
    assert result.false_certainty_count.value is not None
    assert result.false_certainty_count.value.numerator == 1
    assert result.false_certainty_count.value.denominator == 1
    assert result.scientific_use_permitted is False


def _component_record(
    component: ReferenceStabilityComponent,
    *,
    present: bool,
) -> ReferenceStabilityComponentRecord:
    observation: KnowledgeValue[AgreementObservation | StabilityComponentObservation]
    if present:
        observation = KnowledgeValue[AgreementObservation | StabilityComponentObservation](
            knowledge_state=KnowledgeState.PRESENT,
            value=AgreementObservation(
                metric_id="pre-adjudication-agreement",
                numerator=8,
                denominator=10,
                unit="decisive predicate",
            ),
            evidence_ids=("E-AGREEMENT",),
            query_scope_id="REFERENCE-PILOT-1",
        )
    else:
        observation = KnowledgeValue[AgreementObservation | StabilityComponentObservation](
            knowledge_state=KnowledgeState.UNKNOWN,
            rationale=f"No reviewed evidence for {component.value}.",
            query_scope_id="REFERENCE-PILOT-1",
        )
    return ReferenceStabilityComponentRecord(
        component=component,
        observation=observation,
        reviewer_actor_ids=("REVIEWER-1",),
    )


def test_agreement_is_not_reference_stability_or_gate_closure() -> None:
    records = tuple(
        _component_record(
            component,
            present=component is ReferenceStabilityComponent.PRE_ADJUDICATION_AGREEMENT,
        )
        for component in ReferenceStabilityComponent
    )
    report = build_reference_stability_report(
        report_id="REFERENCE-PILOT-1",
        protocol_id="PILOT-PROTOCOL-1",
        component_records=records,
        evidence_ids=("E-AGREEMENT",),
    )

    assert report.component_evidence_complete is False
    assert report.reference_stability_conclusion.knowledge_state is KnowledgeState.UNKNOWN
    assert report.blocker is not None
    assert report.blocker.issue_id == "SRR-V8-REFERENCE-STABILITY"

    with pytest.raises(ValidationError, match="exactly six"):
        build_reference_stability_report(
            report_id="REFERENCE-PILOT-1",
            protocol_id="PILOT-PROTOCOL-1",
            component_records=(records[0],),
            evidence_ids=("E-AGREEMENT",),
        )


def _generalization_contract() -> MetricGeneralizationContract:
    return MetricGeneralizationContract(
        metric_id="final-claim-correctness",
        elementary_unit=GeneralizationUnitKind.CLAIM,
        resampling_cluster=GeneralizationUnitKind.STUDY_FAMILY,
        stratification_variables=("complexity-tier", "profile"),
        cluster_estimator_id=SUPPORTED_CLUSTER_ESTIMATOR_ID,
        cluster_estimator_checksum=SUPPORTED_CLUSTER_ESTIMATOR_CHECKSUM,
        units=(
            GeneralizationUnit(
                metric_id="final-claim-correctness",
                generalization_unit_id="SF-1",
            ),
            GeneralizationUnit(
                metric_id="final-claim-correctness",
                generalization_unit_id="SF-2",
            ),
            GeneralizationUnit(
                metric_id="final-claim-correctness",
                generalization_unit_id="SF-3",
            ),
        ),
        bootstrap=ClusterBootstrapProtocol(
            method_id="cluster-bootstrap-sha256-v1",
            seed="conformance-seed",
            iterations=250,
            confidence_level=Decimal("0.95"),
        ),
        small_cluster_caveat=(
            "No cross-lab or cross-family claim is authorized without preregistered precision."
        ),
    )


def test_cluster_precision_is_invariant_to_duplicate_rows_inside_cluster() -> None:
    contract = _generalization_contract()
    base = (
        build_cluster_metric_observation(
            metric_id=contract.metric_id,
            elementary_source_id="SOURCE-SF-1",
            generalization_unit_id="SF-1",
            value=Decimal("0.2"),
            stratum_values={"complexity-tier": "T1", "profile": "P1"},
            evidence_ids=("E-SF-1",),
        ),
        build_cluster_metric_observation(
            metric_id=contract.metric_id,
            elementary_source_id="SOURCE-SF-2",
            generalization_unit_id="SF-2",
            value=Decimal("0.7"),
            stratum_values={"complexity-tier": "T1", "profile": "P1"},
            evidence_ids=("E-SF-2",),
        ),
        build_cluster_metric_observation(
            metric_id=contract.metric_id,
            elementary_source_id="SOURCE-SF-3",
            generalization_unit_id="SF-3",
            value=Decimal("0.9"),
            stratum_values={"complexity-tier": "T2", "profile": "P2"},
            evidence_ids=("E-SF-3",),
        ),
    )

    authority = reviewed_cluster_authority(contract, base)
    original = cluster_bootstrap_precision(
        contract,
        base,
        authority_resolution=authority,
    )
    duplicated = cluster_bootstrap_precision(
        contract,
        base + (base[0],) * 50,
        authority_resolution=authority,
    )

    assert original == duplicated
    assert original.effective_cluster_count == 3
    assert original.interval.knowledge_state is KnowledgeState.PRESENT
    with pytest.raises(ValidationError, match="precision result checksum mismatch"):
        type(original).model_validate(
            original.model_copy(update={"content_checksum": "0" * 64}).model_dump(mode="python")
        )

    with pytest.raises(ValueError, match=r"elementary source checksum|observation ID"):
        cluster_bootstrap_precision(
            contract,
            (
                *base,
                base[0].model_copy(update={"value": Decimal("0.8")}),
            ),
        )


def test_generalization_units_are_metric_specific() -> None:
    with pytest.raises(ValidationError, match="metric-specific"):
        MetricGeneralizationContract(
            **{
                **_generalization_contract().model_dump(mode="python"),
                "units": (
                    GeneralizationUnit(
                        metric_id="residual-error-rate",
                        generalization_unit_id="SF-1",
                    ),
                ),
            }
        )


def test_one_cluster_returns_unknown_precision_instead_of_a_spurious_interval() -> None:
    base = _generalization_contract()
    contract = MetricGeneralizationContract.model_validate(
        {**base.model_dump(mode="python"), "units": (base.units[0],)}
    )

    rows = (
        build_cluster_metric_observation(
            metric_id=contract.metric_id,
            elementary_source_id="SOURCE-SF-1",
            generalization_unit_id="SF-1",
            value=Decimal("0.5"),
            stratum_values={"complexity-tier": "T1", "profile": "P1"},
            evidence_ids=("E-SF-1",),
        ),
    )
    result = cluster_bootstrap_precision(
        contract,
        rows,
        authority_resolution=reviewed_cluster_authority(contract, rows),
    )

    assert result.interval.knowledge_state is KnowledgeState.UNKNOWN
    assert result.authority_resolution.knowledge_state is KnowledgeState.PRESENT
    assert "SRR-V8-CLUSTER-PRECISION" in {item.issue_id for item in result.blockers}
