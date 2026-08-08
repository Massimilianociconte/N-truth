from __future__ import annotations

import hashlib
import importlib
from decimal import Decimal

import pytest
from prd_v8_cluster_authority_fixtures import reviewed_cluster_authority
from pydantic import ValidationError

import ntruth.evaluation_v8 as evaluation
from ntruth.evaluation_v8.models import (
    AdequacyAxisSnapshot,
    ClaimEvaluationSnapshot,
    QueryEvaluationSnapshot,
)
from ntruth.schemas.claims import DeterminabilityState
from ntruth.schemas.core import content_checksum
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue

base = importlib.import_module("test_prd_v8_task7_evaluation")


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _reference_value(
    snapshot: evaluation.ReportEvaluationSnapshot,
    *,
    reference_stability_report: object | None = None,
) -> KnowledgeValue[evaluation.IndependentReportReference]:
    kwargs: dict[str, object] = {}
    if reference_stability_report is not None:
        kwargs["reference_stability_report"] = reference_stability_report
    reference = evaluation.build_independent_report_reference(
        reference_id="REF-CONFORMANCE-FIX1",
        purpose=evaluation.IndependentReferencePurpose.CONFORMANCE_ONLY,
        report_scope_id="REPORT-1",
        snapshot=snapshot,
        source_record_ids=("SRC-CONFORMANCE",),
        evidence_ids=("E-REFERENCE",),
        reviewer_actor_ids=("REVIEWER-INDEPENDENT",),
        **kwargs,
    )
    return KnowledgeValue[evaluation.IndependentReportReference](
        knowledge_state=KnowledgeState.PRESENT,
        value=reference,
        evidence_ids=("E-REFERENCE",),
        query_scope_id="REPORT-1",
    )


def _query(
    query_id: str,
    *,
    claims: tuple[ClaimEvaluationSnapshot, ...],
    resolution: str,
    axes: tuple[AdequacyAxisSnapshot, ...],
) -> QueryEvaluationSnapshot:
    return QueryEvaluationSnapshot(
        query_id=query_id,
        report_resolution_checksum=_digest(resolution),
        claims=tuple(claim.model_copy(update={"query_id": query_id}) for claim in claims),
        adequacy_axes=tuple(axis.model_copy(update={"query_id": query_id}) for axis in axes),
    )


def test_every_material_report_mismatch_produces_a_scoped_residual() -> None:
    observed = evaluation.build_report_evaluation_snapshot(
        report_id="REPORT-1",
        report_checksum=_digest("observed-report"),
        global_report_resolution_checksum=_digest("observed-global-resolution"),
        query_snapshots=(
            _query(
                "IQ-1",
                claims=(
                    base._claim(
                        "C-1",
                        state=DeterminabilityState.DETERMINATE,
                        value="wrong",
                        evidence=("E-WRONG",),
                        proof="wrong-proof",
                    ),
                    base._claim(
                        "C-UNEXPECTED",
                        state=DeterminabilityState.DETERMINATE,
                        value="unexpected",
                    ),
                ),
                resolution="observed-query-resolution",
                axes=(
                    AdequacyAxisSnapshot(
                        query_id="IQ-1",
                        axis_id="interference",
                        outcome_checksum=_digest("wrong-axis"),
                        communicated_positive=base._adequacy_communication("IQ-1"),
                    ),
                    AdequacyAxisSnapshot(
                        query_id="IQ-1",
                        axis_id="unexpected-axis",
                        outcome_checksum=_digest("unexpected-axis"),
                        communicated_positive=base._adequacy_communication("IQ-1"),
                    ),
                ),
            ),
            _query(
                "IQ-UNEXPECTED",
                claims=(
                    base._claim(
                        "C-QUERY-UNEXPECTED",
                        state=DeterminabilityState.DETERMINATE,
                        value="unexpected-query",
                    ),
                ),
                resolution="unexpected-query-resolution",
                axes=(
                    AdequacyAxisSnapshot(
                        query_id="IQ-UNEXPECTED",
                        axis_id="interference",
                        outcome_checksum=_digest("unexpected-query-axis"),
                        communicated_positive=base._adequacy_communication("IQ-UNEXPECTED"),
                    ),
                ),
            ),
        ),
    )
    reference = evaluation.build_report_evaluation_snapshot(
        report_id="REPORT-1",
        report_checksum=_digest("reference-report"),
        global_report_resolution_checksum=_digest("reference-global-resolution"),
        query_snapshots=(
            _query(
                "IQ-1",
                claims=(
                    base._claim(
                        "C-1",
                        state=DeterminabilityState.DETERMINATE,
                        value="correct",
                        evidence=("E-CORRECT",),
                        proof="correct-proof",
                    ),
                    base._claim(
                        "C-MISSING",
                        state=DeterminabilityState.DETERMINATE,
                        value="missing",
                    ),
                ),
                resolution="reference-query-resolution",
                axes=(
                    AdequacyAxisSnapshot(
                        query_id="IQ-1",
                        axis_id="interference",
                        outcome_checksum=_digest("correct-axis"),
                        communicated_positive=base._adequacy_communication("IQ-1"),
                    ),
                    AdequacyAxisSnapshot(
                        query_id="IQ-1",
                        axis_id="missing-axis",
                        outcome_checksum=_digest("missing-axis"),
                        communicated_positive=base._adequacy_communication("IQ-1"),
                    ),
                ),
            ),
            _query(
                "IQ-MISSING",
                claims=(
                    base._claim(
                        "C-QUERY-MISSING",
                        state=DeterminabilityState.DETERMINATE,
                        value="missing-query",
                    ),
                ),
                resolution="missing-query-resolution",
                axes=(
                    AdequacyAxisSnapshot(
                        query_id="IQ-MISSING",
                        axis_id="interference",
                        outcome_checksum=_digest("missing-query-axis"),
                        communicated_positive=base._adequacy_communication("IQ-MISSING"),
                    ),
                ),
            ),
        ),
    )

    result = evaluation.evaluate_end_to_end(observed, _reference_value(reference))

    assert result.denominators.value.report_count == 1
    assert result.complete_report_match.value is False
    assert result.residuals.knowledge_state is KnowledgeState.PRESENT
    residuals = result.residuals.value or ()
    dimensions = {item.dimension.value for item in residuals}
    assert {
        "COMPLETE_REPORT",
        "GLOBAL_REPORT_RESOLUTION",
        "QUERY_MEMBERSHIP",
        "QUERY_REPORT_RESOLUTION",
        "CLAIM_SEMANTICS",
        "ADEQUACY_AXIS",
        "EVIDENCE_CORRECTNESS",
        "PROOF_CORRECTNESS",
    }.issubset(dimensions)
    assert {item.scope_id for item in residuals}.issuperset(
        {"REPORT-1", "IQ-MISSING", "IQ-UNEXPECTED", "C-MISSING", "C-UNEXPECTED"}
    )


def test_false_certainty_retains_scope_denominator_and_unknown_severity() -> None:
    observed_claim = base._claim(
        "C-DECISIVE",
        state=DeterminabilityState.DETERMINATE,
        value="wrong-count",
    )
    reference_claim = base._claim(
        "C-DECISIVE",
        state=DeterminabilityState.DETERMINATE,
        value="correct-count",
    )
    observed = base._snapshot(claims=(observed_claim,))
    reference = base._snapshot(claims=(reference_claim,))

    result = evaluation.evaluate_end_to_end(observed, _reference_value(reference))

    summary = getattr(result, "false_certainty", None)
    assert summary is not None
    assert summary.knowledge_state is KnowledgeState.PRESENT
    assert summary.value.scope.knowledge_state is KnowledgeState.UNKNOWN
    assert summary.value.denominator.knowledge_state is KnowledgeState.UNKNOWN
    assert summary.value.event_count.value == 1
    assert summary.value.rate.knowledge_state is KnowledgeState.UNKNOWN
    assert summary.value.severity.knowledge_state is KnowledgeState.UNKNOWN
    false_certainty_residuals = [
        item
        for item in result.residuals.value or ()
        if item.claim_id == "C-DECISIVE" and item.dimension.value == "CLAIM_SEMANTICS"
    ]
    assert len(false_certainty_residuals) == 1
    assert (
        false_certainty_residuals[0].false_certainty_category.knowledge_state
        is KnowledgeState.UNKNOWN
    )


def test_nondecisive_false_certainty_is_retained_without_an_implicit_denominator() -> None:
    decisive_true = KnowledgeValue[bool](
        knowledge_state=KnowledgeState.PRESENT,
        value=True,
        evidence_ids=("E-DECISIVE",),
        claim_scope_id="C-DECISIVE",
    )
    decisive_false = KnowledgeValue[bool](
        knowledge_state=KnowledgeState.PRESENT,
        value=False,
        evidence_ids=("E-NONDECISIVE",),
        claim_scope_id="C-NONDECISIVE",
    )
    observed = base._snapshot(
        claims=(
            base._claim(
                "C-DECISIVE", state=DeterminabilityState.DETERMINATE, value="stable"
            ).model_copy(update={"decisive": decisive_true}),
            base._claim(
                "C-NONDECISIVE", state=DeterminabilityState.DETERMINATE, value="wrong"
            ).model_copy(update={"decisive": decisive_false}),
        )
    )
    reference = base._snapshot(
        claims=(
            base._claim(
                "C-DECISIVE", state=DeterminabilityState.DETERMINATE, value="stable"
            ).model_copy(update={"decisive": decisive_true}),
            base._claim(
                "C-NONDECISIVE", state=DeterminabilityState.DETERMINATE, value="correct"
            ).model_copy(update={"decisive": decisive_false}),
        )
    )

    result = evaluation.evaluate_end_to_end(observed, _reference_value(reference))

    assert result.false_certainty.value.scope.knowledge_state is KnowledgeState.UNKNOWN
    assert result.false_certainty.value.denominator.knowledge_state is KnowledgeState.UNKNOWN
    assert result.false_certainty.value.event_count.value == 1


def test_report_questions_remain_query_scoped_without_invented_claim_attribution() -> None:
    quick_design_fixture = importlib.import_module("test_prd_v8_quick_design")
    module, submission = quick_design_fixture._submission()
    report = module.run_quick_design_v8(
        submission,
        conformance_bundle=base.load_canonical_bundle(
            quick_design_fixture.runtime_fixture.REPOSITORY_ROOT
        ),
    ).report_bundle

    snapshot = evaluation.snapshot_report_bundle(report)

    for section, query in zip(report.query_sections, snapshot.query_snapshots, strict=True):
        attributions = getattr(query, "question_attributions", None)
        assert attributions is not None
        assert tuple(item.question_id for item in attributions) == tuple(
            question.question_id for question in section.questions
        )
        assert all(item.query_id == section.inferential_query.id for item in attributions)
        assert all(
            item.claim_ids.knowledge_state is KnowledgeState.UNKNOWN for item in attributions
        )
        assert all(
            claim.actionable_question_ids.knowledge_state is KnowledgeState.UNKNOWN
            for claim in query.claims
            if claim.determinability_state is not DeterminabilityState.DETERMINATE
        )


def _complete_stability_report() -> object:
    components = list(evaluation.ReferenceStabilityComponent)
    assert "GRAPH_MATCHING_UNCERTAINTY" in {item.value for item in components}
    assert "GOLD_NOISE_BUDGET" not in {item.value for item in components}
    records: list[evaluation.ReferenceStabilityComponentRecord] = []
    evidence_ids: list[str] = []
    for component in components:
        evidence_id = f"E-{component.value}"
        evidence_ids.append(evidence_id)
        if component is evaluation.ReferenceStabilityComponent.PRE_ADJUDICATION_AGREEMENT:
            value: evaluation.AgreementObservation | evaluation.StabilityComponentObservation = (
                evaluation.AgreementObservation(
                    metric_id="pre-adjudication-agreement",
                    numerator=8,
                    denominator=10,
                    unit="decisive predicate",
                )
            )
        else:
            value = evaluation.StabilityComponentObservation(
                observation_id=f"OBS-{component.value}",
                artifact_checksum=_digest(component.value),
                summary=f"Conformance-only observation for {component.value}.",
            )
        records.append(
            evaluation.ReferenceStabilityComponentRecord(
                component=component,
                observation=KnowledgeValue(
                    knowledge_state=KnowledgeState.PRESENT,
                    value=value,
                    evidence_ids=(evidence_id,),
                    query_scope_id="REPORT-1",
                ),
                reviewer_actor_ids=(f"REVIEWER-{component.value}",),
            )
        )
    evidence_ids.extend(("E-POLICY", "E-CONCLUSION"))
    return evaluation.build_reference_stability_report(
        report_id="REPORT-1",
        protocol_id="REFERENCE-PILOT-CONFORMANCE",
        component_records=tuple(records),
        evidence_ids=tuple(evidence_ids),
        interpretation_policy=KnowledgeValue[evaluation.ReferenceStabilityPolicyPin](
            knowledge_state=KnowledgeState.PRESENT,
            value=evaluation.ReferenceStabilityPolicyPin(
                policy_id="POLICY-CONFORMANCE",
                policy_version="1",
                policy_checksum=_digest("policy-conformance"),
                decision_region_id="REGION-CONFORMANCE",
            ),
            evidence_ids=("E-POLICY",),
            query_scope_id="REPORT-1",
        ),
        reviewed_conclusion=KnowledgeValue[evaluation.ReferenceStabilityConclusion](
            knowledge_state=KnowledgeState.PRESENT,
            value=(
                evaluation.ReferenceStabilityConclusion.REVIEWED_WITHIN_PREREGISTERED_DECISION_REGION
            ),
            evidence_ids=("E-CONCLUSION",),
            query_scope_id="REPORT-1",
        ),
    )


def test_reference_stability_requires_resolved_content_addressed_report() -> None:
    stability = _complete_stability_report()
    observed = base._snapshot(
        claims=(base._claim("C-1", state=DeterminabilityState.DETERMINATE, value="x"),)
    )
    reference = evaluation.build_independent_report_reference(
        reference_id="REF-INDEPENDENT-1",
        purpose=evaluation.IndependentReferencePurpose.INDEPENDENT_EVALUATION,
        report_scope_id="REPORT-1",
        snapshot=observed,
        source_record_ids=("SRC-INDEPENDENT",),
        evidence_ids=("E-REFERENCE", "E-POLICY", "E-CONCLUSION"),
        reviewer_actor_ids=("REVIEWER-INDEPENDENT",),
        reference_stability_report=stability,
    )
    reference_value = KnowledgeValue[evaluation.IndependentReportReference](
        knowledge_state=KnowledgeState.PRESENT,
        value=reference,
        evidence_ids=("E-REFERENCE",),
        query_scope_id="REPORT-1",
    )

    unresolved = evaluation.evaluate_end_to_end(observed, reference_value)
    assert "SRR-V8-REFERENCE-STABILITY" in {item.issue_id for item in unresolved.blockers}

    resolved = evaluation.evaluate_end_to_end(
        observed,
        reference_value,
        reference_stability_reports=(stability,),
    )
    assert "SRR-V8-REFERENCE-STABILITY" not in {item.issue_id for item in resolved.blockers}
    assert resolved.scientific_use_permitted is False
    assert "SRR-V8-EVAL-SCIENTIFIC-HOLD" in {item.issue_id for item in resolved.blockers}

    raw_hash = KnowledgeValue[str](
        knowledge_state=KnowledgeState.PRESENT,
        value=stability.content_checksum,
        evidence_ids=("E-REFERENCE",),
        query_scope_id="REPORT-1",
    )
    with pytest.raises(ValueError, match="raw reference-stability checksum"):
        evaluation.build_independent_report_reference(
            reference_id="REF-RAW-HASH",
            purpose=evaluation.IndependentReferencePurpose.INDEPENDENT_EVALUATION,
            report_scope_id="REPORT-1",
            snapshot=observed,
            source_record_ids=("SRC-INDEPENDENT",),
            evidence_ids=("E-REFERENCE",),
            reviewer_actor_ids=("REVIEWER-INDEPENDENT",),
            reference_stability_report_checksum=raw_hash,
        )


def _audit_finding(
    *, report_id: str, query_id: str, claim_id: str, reference_id: str
) -> evaluation.ResidualAuditFinding:
    present_false = KnowledgeValue[bool](
        knowledge_state=KnowledgeState.PRESENT,
        value=False,
        evidence_ids=("E-AUDIT",),
        claim_scope_id=claim_id,
    )
    return evaluation.ResidualAuditFinding(
        finding_id=f"F-{report_id}-{claim_id}",
        report_id=report_id,
        query_id=query_id,
        claim_id=claim_id,
        reference_id=reference_id,
        decisive_error=present_false,
        false_certainty=present_false,
        human_review_introduced_error=present_false,
        origin=KnowledgeValue[evaluation.ResidualOrigin](
            knowledge_state=KnowledgeState.UNKNOWN,
            rationale="Origin remains unknown in this conformance fixture.",
            claim_scope_id=claim_id,
        ),
        severity=KnowledgeValue[evaluation.ResidualSeverity](
            knowledge_state=KnowledgeState.UNKNOWN,
            rationale="Severity remains unknown in this conformance fixture.",
            claim_scope_id=claim_id,
        ),
        stratum_values={item: f"S-{item.value}" for item in evaluation.ResidualAuditStratum},
        impact_on_claim=KnowledgeValue[str](
            knowledge_state=KnowledgeState.PRESENT,
            value="No residual error was asserted by this conformance-only reviewer.",
            evidence_ids=("E-AUDIT",),
            claim_scope_id=claim_id,
        ),
        evidence_ids=("E-AUDIT",),
    )


def test_blind_audit_closes_exact_report_query_claim_reference_identity_and_summaries() -> None:
    sample_item_type = getattr(evaluation, "ResidualAuditSampleItem", None)
    assert sample_item_type is not None, "typed residual sample identity is missing"
    sample_items = (
        sample_item_type(
            report_id="REPORT-1",
            query_id="IQ-1",
            claim_id="C-SHARED",
            reference_id="REF-1",
        ),
        sample_item_type(
            report_id="REPORT-2",
            query_id="IQ-2",
            claim_id="C-SHARED",
            reference_id="REF-2",
        ),
    )
    protocol = evaluation.BlindResidualAuditProtocol(
        protocol_id="AUDIT-PAIR-CLOSURE",
        sample_manifest_checksum=_digest("sample-pair-closure"),
        sample_items=sample_items,
        strata=tuple(evaluation.ResidualAuditStratum),
        blind_to_original_output=True,
        role_assignments=base._audit_assignments(auditor="AUDITOR-E"),
        evidence_ids=("E-AUDIT",),
    )
    findings = (
        _audit_finding(
            report_id="REPORT-1",
            query_id="IQ-1",
            claim_id="C-SHARED",
            reference_id="REF-1",
        ),
        _audit_finding(
            report_id="REPORT-2",
            query_id="IQ-2",
            claim_id="C-SHARED",
            reference_id="REF-2",
        ),
    )

    result = evaluation.summarize_blind_residual_audit(protocol, findings)

    assert result.decisive_error_count.value.denominator == 2
    swapped = findings[0].model_copy(update={"report_id": "REPORT-2"})
    with pytest.raises(ValidationError, match="exact blinded sample identity"):
        evaluation.summarize_blind_residual_audit(protocol, (swapped, findings[1]))

    payload = result.model_dump(mode="python")
    payload["decisive_error_count"] = KnowledgeValue[evaluation.AuditCountSummary](
        knowledge_state=KnowledgeState.PRESENT,
        value=evaluation.AuditCountSummary(numerator=1, denominator=2),
        evidence_ids=("E-AUDIT",),
        query_scope_id=protocol.protocol_id,
    )
    checksum = content_checksum(
        {
            key: value
            for key, value in payload.items()
            if key not in {"result_id", "content_checksum"}
        }
    )
    payload["content_checksum"] = checksum
    payload["result_id"] = f"RESIDUAL-AUDIT-{checksum[:20]}"
    with pytest.raises(ValidationError, match="summary differs from sealed findings"):
        evaluation.BlindResidualAuditResult.model_validate(payload)


def test_cluster_bootstrap_aggregates_elementary_rows_and_seals_numeric_inputs() -> None:
    observation_type = getattr(evaluation, "ClusterMetricObservation", None)
    estimator_id = getattr(evaluation, "SUPPORTED_CLUSTER_ESTIMATOR_ID", None)
    estimator_checksum = getattr(evaluation, "SUPPORTED_CLUSTER_ESTIMATOR_CHECKSUM", None)
    assert observation_type is not None, "elementary cluster observation contract is missing"
    assert estimator_id is not None and estimator_checksum is not None
    contract = evaluation.MetricGeneralizationContract(
        metric_id="final-claim-correctness",
        elementary_unit=evaluation.GeneralizationUnitKind.CLAIM,
        resampling_cluster=evaluation.GeneralizationUnitKind.STUDY_FAMILY,
        stratification_variables=("profile",),
        cluster_estimator_id=estimator_id,
        cluster_estimator_checksum=estimator_checksum,
        units=tuple(
            evaluation.GeneralizationUnit(
                metric_id="final-claim-correctness", generalization_unit_id=f"SF-{index}"
            )
            for index in range(1, 4)
        ),
        bootstrap=evaluation.ClusterBootstrapProtocol(
            method_id=evaluation.SUPPORTED_CLUSTER_BOOTSTRAP_METHOD,
            seed="conformance-seed",
            iterations=250,
            confidence_level=Decimal("0.95"),
        ),
        small_cluster_caveat="Conformance-only interval; no generalization claim is authorized.",
    )
    rows = tuple(
        evaluation.build_cluster_metric_observation(
            metric_id=contract.metric_id,
            elementary_source_id=f"SOURCE-{cluster}-{row}",
            generalization_unit_id=f"SF-{cluster}",
            value=value,
            stratum_values={"profile": "A" if cluster < 3 else "B"},
            evidence_ids=(f"E-{cluster}-{row}",),
        )
        for cluster, values in (
            (1, (Decimal("0"), Decimal("1"))),
            (2, (Decimal("1"), Decimal("1"))),
            (3, (Decimal("0"), Decimal("0"))),
        )
        for row, value in enumerate(values, start=1)
    )

    authority = reviewed_cluster_authority(contract, rows)
    original = evaluation.cluster_bootstrap_precision(
        contract,
        rows,
        authority_resolution=authority,
    )
    duplicated = evaluation.cluster_bootstrap_precision(
        contract,
        rows + (rows[0],) * 50,
        authority_resolution=authority,
    )

    assert original == duplicated
    assert original.input_manifest.observation_count == 6
    assert original.input_manifest.cluster_count == 3
    assert original.input_manifest.estimator_id == estimator_id
    assert original.input_manifest.stratification_variables == ("profile",)
    assert original.scientific_use_permitted is False
    assert "SRR-V8-EVAL-SCIENTIFIC-HOLD" in {item.issue_id for item in original.blockers}
    assert original.interval.knowledge_state is KnowledgeState.PRESENT

    payload = original.model_dump(mode="python")
    payload["input_manifest"]["observations"][0]["value"] = Decimal("0.5")
    outer_checksum = content_checksum(
        {
            key: value
            for key, value in payload.items()
            if key not in {"result_id", "content_checksum"}
        }
    )
    payload["content_checksum"] = outer_checksum
    payload["result_id"] = f"CLUSTER-PRECISION-{outer_checksum[:20]}"
    with pytest.raises(
        ValidationError,
        match=(
            r"cluster estimate differs|cluster observation manifest checksum mismatch|"
            r"cluster elementary source checksum mismatch"
        ),
    ):
        evaluation.ClusterPrecisionResult.model_validate(payload)


def test_decisive_and_process_metrics_are_typed_unknown_until_observed() -> None:
    claim_payload = base._claim(
        "C-DECISIVE",
        state=DeterminabilityState.DETERMINATE,
        value="x",
    ).model_dump(mode="python")
    claim_payload["decisive"] = KnowledgeValue[bool](
        knowledge_state=KnowledgeState.PRESENT,
        value=True,
        evidence_ids=("E-DECISIVE",),
        claim_scope_id="C-DECISIVE",
    )
    try:
        decisive_claim = ClaimEvaluationSnapshot.model_validate(claim_payload)
    except ValidationError as exc:
        pytest.fail(f"claim decisive designation is missing: {exc}")
    decisive = getattr(decisive_claim, "decisive", None)
    assert decisive is not None
    assert decisive.knowledge_state is KnowledgeState.PRESENT
    assert decisive.value is True
    observed = base._snapshot(claims=(decisive_claim,))

    result = evaluation.evaluate_end_to_end(observed, _reference_value(observed))

    assert result.denominators.value.decisive_claim_count.value == 1
    for field_name in (
        "time_to_confirmed_report_seconds",
        "review_time_delta_seconds",
        "decisive_human_correction_count",
        "question_usefulness",
    ):
        value = getattr(result, field_name, None)
        assert value is not None, f"{field_name} contract is missing"
        assert value.knowledge_state is KnowledgeState.UNKNOWN
        assert value.query_scope_id == "REPORT-1"
    assert "SRR-V8-EVAL-PROCESS-METRICS" in {item.issue_id for item in result.blockers}
    assert result.scientific_use_permitted is False
