from __future__ import annotations

import importlib
from decimal import Decimal

import pytest
from pydantic import ValidationError

import ntruth.evaluation_v8 as evaluation
from ntruth.schemas.claims import DeterminabilityState
from ntruth.schemas.core import content_checksum
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue

base = importlib.import_module("test_prd_v8_task7_evaluation")
fix1 = importlib.import_module("test_prd_v8_task7_evaluation_fix1")


def _query_value(value: object, *, scope: str, evidence_id: str = "E-PROCESS") -> KnowledgeValue:
    return KnowledgeValue(
        knowledge_state=KnowledgeState.PRESENT,
        value=value,
        evidence_ids=(evidence_id,),
        query_scope_id=scope,
    )


def _one_wrong_decisive_claim() -> tuple[object, object]:
    observed = base._snapshot(
        claims=(
            base._claim(
                "C-DECISIVE",
                state=DeterminabilityState.DETERMINATE,
                value="wrong",
            ),
        )
    )
    reference = base._snapshot(
        claims=(
            base._claim(
                "C-DECISIVE",
                state=DeterminabilityState.DETERMINATE,
                value="correct",
            ),
        )
    )
    return observed, reference


def test_false_certainty_rate_is_unknown_without_a_resolved_protocol() -> None:
    observed, reference = _one_wrong_decisive_claim()

    result = evaluation.evaluate_end_to_end(observed, fix1._reference_value(reference))

    summary = result.false_certainty.value
    assert summary is not None
    assert summary.event_count.knowledge_state is KnowledgeState.PRESENT
    assert summary.event_count.value == 1
    assert summary.scope.knowledge_state is KnowledgeState.UNKNOWN
    assert summary.denominator.knowledge_state is KnowledgeState.UNKNOWN
    assert summary.rate.knowledge_state is KnowledgeState.UNKNOWN
    assert summary.severity.knowledge_state is KnowledgeState.UNKNOWN
    assert "SRR-V8-FALSE-CERTAINTY-PROTOCOL" in {item.issue_id for item in result.blockers}


def test_resolved_false_certainty_protocol_pins_scope_denominator_and_rate() -> None:
    observed, reference = _one_wrong_decisive_claim()
    builder = getattr(evaluation, "build_false_certainty_metric_protocol", None)
    assert builder is not None, "content-addressed false-certainty protocol builder is missing"
    protocol = builder(
        report_scope_id="REPORT-1",
        denominator_scope_id="PREREGISTERED-DEFINITIVE-OUTPUTS-V1",
        denominator=10,
        event_unit="one materially unsupported definitive conclusion",
        severity_policy_id="FALSE-CERTAINTY-SEVERITY-V1",
        severity_policy_checksum=base._digest("false-certainty-severity-v1"),
        evidence_ids=("E-REFERENCE",),
    )

    result = evaluation.evaluate_end_to_end(
        observed,
        fix1._reference_value(reference),
        false_certainty_protocol=protocol,
    )

    summary = result.false_certainty.value
    assert summary is not None
    assert summary.scope.value == "PREREGISTERED-DEFINITIVE-OUTPUTS-V1"
    assert summary.denominator.value == 10
    assert summary.event_count.value == 1
    assert summary.rate.value == Decimal("0.1")
    assert summary.rate.evidence_ids == protocol.evidence_ids
    assert "SRR-V8-FALSE-CERTAINTY-PROTOCOL" not in {item.issue_id for item in result.blockers}


def test_false_certainty_retains_every_definitive_mismatch_dimension() -> None:
    required_dimensions = {
        "COUNT_CORRECTNESS",
        "SCENARIO_COVERAGE",
        "PROFILE_COVERAGE",
        "SUPPORT_CORRECTNESS",
    }
    assert required_dimensions.issubset({item.value for item in evaluation.ResidualDimension})

    observed = base._snapshot(
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
        axis_value="unsupported-positive",
    )
    observed_query = observed.query_snapshots[0].model_copy(
        update={
            "report_resolution_checksum": base._digest("wrong-query-resolution"),
            "adequacy_axes": (
                observed.query_snapshots[0]
                .adequacy_axes[0]
                .model_copy(
                    update={
                        "communicated_positive": base._adequacy_communication("IQ-1", positive=True)
                    }
                ),
            ),
        }
    )
    observed = evaluation.build_report_evaluation_snapshot(
        report_id=observed.report_id,
        report_checksum=observed.report_checksum,
        global_report_resolution_checksum=observed.global_report_resolution_checksum,
        query_snapshots=(observed_query,),
    )
    reference = base._snapshot(
        claims=(
            base._claim(
                "C-1",
                state=DeterminabilityState.DETERMINATE,
                value="correct",
                evidence=("E-CORRECT",),
                proof="correct-proof",
            ),
        ),
        axis_value="not-positive",
    )

    result = evaluation.evaluate_end_to_end(observed, fix1._reference_value(reference))

    definitive_dimensions = {
        evaluation.ResidualDimension.CLAIM_SEMANTICS,
        evaluation.ResidualDimension.ADEQUACY_AXIS,
        evaluation.ResidualDimension.EVIDENCE_CORRECTNESS,
        evaluation.ResidualDimension.PROOF_CORRECTNESS,
    }
    retained = [
        item
        for item in result.residuals.value or ()
        if item.dimension in definitive_dimensions
        and item.match_outcome
        in {evaluation.MatchOutcome.INCORRECT, evaluation.MatchOutcome.UNEXPECTED}
    ]
    assert retained
    assert all(item.false_certainty.knowledge_state is KnowledgeState.PRESENT for item in retained)
    assert all(item.false_certainty.value is True for item in retained)


def test_actionable_claim_question_without_closed_attribution_is_rejected() -> None:
    claim = base._claim(
        "C-UNRESOLVED",
        state=DeterminabilityState.INSUFFICIENT_INFORMATION,
        value="unknown",
    )

    with pytest.raises(ValidationError, match=r"actionable question.*attribution"):
        evaluation.QueryEvaluationSnapshot(
            query_id="IQ-1",
            report_resolution_checksum=base._digest("partial"),
            claims=(claim,),
            adequacy_axes=(
                evaluation.AdequacyAxisSnapshot(
                    query_id="IQ-1",
                    axis_id="interference",
                    outcome_checksum=base._digest("axis"),
                    communicated_positive=base._adequacy_communication("IQ-1"),
                ),
            ),
            question_attributions=(),
        )


def test_negative_process_counts_and_durations_are_rejected() -> None:
    with pytest.raises(ValidationError, match="non-negative"):
        evaluation.QuestionUsefulnessObservation(
            query_id="IQ-1",
            question_id="Q-1",
            reviewer_actor_ids=("REVIEWER-A", "REVIEWER-B"),
            answerable=_query_value(True, scope="IQ-1"),
            relevance=_query_value(5, scope="IQ-1"),
            scenario_resolved=_query_value(True, scope="IQ-1"),
            output_changing=_query_value(True, scope="IQ-1"),
            redundant=_query_value(False, scope="IQ-1"),
            recipient_correct=_query_value(True, scope="IQ-1"),
            response_time_seconds=_query_value(Decimal("-1"), scope="IQ-1"),
            evidence_requested=_query_value(("E-PROCESS",), scope="IQ-1"),
            remaining_scenario_coverage=_query_value("reviewed coverage", scope="IQ-1"),
        )

    question = evaluation.QuestionUsefulnessObservation(
        query_id="IQ-1",
        question_id="Q-1",
        reviewer_actor_ids=("REVIEWER-A", "REVIEWER-B"),
        answerable=_query_value(True, scope="IQ-1"),
        relevance=_query_value(5, scope="IQ-1"),
        scenario_resolved=_query_value(True, scope="IQ-1"),
        output_changing=_query_value(True, scope="IQ-1"),
        redundant=_query_value(False, scope="IQ-1"),
        recipient_correct=_query_value(True, scope="IQ-1"),
        response_time_seconds=_query_value(Decimal("1"), scope="IQ-1"),
        evidence_requested=_query_value(("E-PROCESS",), scope="IQ-1"),
        remaining_scenario_coverage=_query_value("reviewed coverage", scope="IQ-1"),
    )

    with pytest.raises(ValidationError, match="non-negative"):
        evaluation.EvaluationProcessObservations(
            observation_id="EVAL-PROCESS-INVALID",
            content_checksum="0" * 64,
            report_scope_id="REPORT-1",
            report_checksum=base._digest("report"),
            evidence_ids=("E-PROCESS",),
            question_attributions=(
                evaluation.QuestionAttributionSnapshot(
                    query_id="IQ-1",
                    question_id="Q-1",
                    claim_ids=KnowledgeValue[tuple[str, ...]](
                        knowledge_state=KnowledgeState.PRESENT,
                        value=("C-1",),
                        evidence_ids=("E-PROCESS",),
                        query_scope_id="IQ-1",
                    ),
                ),
            ),
            time_to_confirmed_report=_query_value(
                evaluation.TimeToConfirmedReportObservation(
                    report_seconds=Decimal("1"), manual_baseline_seconds=Decimal("2")
                ),
                scope="REPORT-1",
            ),
            decisive_human_correction_count=_query_value(-1, scope="REPORT-1"),
            question_usefulness=_query_value((question,), scope="REPORT-1"),
        )


def test_unresolved_caller_process_record_cannot_remove_review_blocker() -> None:
    observed, reference = _one_wrong_decisive_claim()
    untrusted = evaluation.EvaluationProcessObservations.model_construct(
        report_scope_id="REPORT-1",
        time_to_confirmed_report=_query_value(
            evaluation.TimeToConfirmedReportObservation(
                report_seconds=Decimal("1"), manual_baseline_seconds=Decimal("2")
            ),
            scope="REPORT-1",
        ),
        decisive_human_correction_count=_query_value(0, scope="REPORT-1"),
        question_usefulness=_query_value(
            (
                evaluation.QuestionUsefulnessObservation(
                    query_id="IQ-NOT-IN-REPORT",
                    question_id="Q-NOT-IN-REPORT",
                    reviewer_actor_ids=("REVIEWER-A", "REVIEWER-B"),
                    answerable=_query_value(True, scope="IQ-NOT-IN-REPORT"),
                    relevance=_query_value(5, scope="IQ-NOT-IN-REPORT"),
                    scenario_resolved=_query_value(True, scope="IQ-NOT-IN-REPORT"),
                    output_changing=_query_value(True, scope="IQ-NOT-IN-REPORT"),
                    redundant=_query_value(False, scope="IQ-NOT-IN-REPORT"),
                    recipient_correct=_query_value(True, scope="IQ-NOT-IN-REPORT"),
                    response_time_seconds=_query_value(Decimal("1"), scope="IQ-NOT-IN-REPORT"),
                    evidence_requested=_query_value(("E-PROCESS",), scope="IQ-NOT-IN-REPORT"),
                    remaining_scenario_coverage=_query_value(
                        "invented coverage", scope="IQ-NOT-IN-REPORT"
                    ),
                ),
            ),
            scope="REPORT-1",
        ),
    )

    result = evaluation.evaluate_end_to_end(
        observed,
        fix1._reference_value(reference),
        process_observations=untrusted,
    )

    assert "SRR-V8-EVAL-PROCESS-METRICS" in {item.issue_id for item in result.blockers}
    assert result.decisive_human_correction_count.knowledge_state is KnowledgeState.UNKNOWN


def _cluster_fixture() -> tuple[object, tuple[object, ...]]:
    contract = evaluation.MetricGeneralizationContract(
        metric_id="false-certainty-rate",
        elementary_unit=evaluation.GeneralizationUnitKind.CLAIM,
        resampling_cluster=evaluation.GeneralizationUnitKind.STUDY_FAMILY,
        stratification_variables=("profile",),
        cluster_estimator_id=evaluation.SUPPORTED_CLUSTER_ESTIMATOR_ID,
        cluster_estimator_checksum=evaluation.SUPPORTED_CLUSTER_ESTIMATOR_CHECKSUM,
        units=tuple(
            evaluation.GeneralizationUnit(
                metric_id="false-certainty-rate", generalization_unit_id=f"SF-{index}"
            )
            for index in range(1, 4)
        ),
        bootstrap=evaluation.ClusterBootstrapProtocol(
            method_id=evaluation.SUPPORTED_CLUSTER_BOOTSTRAP_METHOD,
            seed="fix2-seed",
            iterations=300,
            confidence_level=Decimal("0.8"),
        ),
        small_cluster_caveat="Conformance-only precision; no scientific use is authorized.",
    )
    values = {
        1: (Decimal("0"), Decimal("0")),
        2: (Decimal("0"), Decimal("0")),
        3: (Decimal("0"), Decimal("1")),
    }
    rows = tuple(
        evaluation.ClusterMetricObservation(
            metric_id=contract.metric_id,
            observation_id=f"OBS-{cluster}-{row}",
            generalization_unit_id=f"SF-{cluster}",
            value=value,
            stratum_values={"profile": "A"},
            evidence_ids=(f"E-{cluster}-{row}",),
        )
        for cluster, cluster_values in values.items()
        for row, value in enumerate(cluster_values, start=1)
    )
    return contract, rows


def _readdress_cluster_payload(payload: dict) -> dict:
    checksum = content_checksum(
        {
            key: value
            for key, value in payload.items()
            if key not in {"result_id", "content_checksum"}
        }
    )
    payload["content_checksum"] = checksum
    payload["result_id"] = f"CLUSTER-PRECISION-{checksum[:20]}"
    return payload


def test_cluster_result_recomputes_interval_from_sealed_inputs() -> None:
    contract, rows = _cluster_fixture()
    result = evaluation.cluster_bootstrap_precision(contract, rows)
    payload = result.model_dump(mode="python")
    payload["interval"]["value"].update(
        {
            "method_id": "caller-forged-method",
            "confidence_level": Decimal("0.5"),
            "point_estimate": Decimal("0.2"),
            "lower": Decimal("0.1"),
            "upper": Decimal("0.3"),
        }
    )

    with pytest.raises(ValidationError, match="interval differs from sealed inputs"):
        evaluation.ClusterPrecisionResult.model_validate(_readdress_cluster_payload(payload))


def test_cluster_manifest_rejects_cross_metric_estimate_after_readdressing() -> None:
    contract, rows = _cluster_fixture()
    result = evaluation.cluster_bootstrap_precision(contract, rows)
    payload = result.input_manifest.model_dump(mode="python")
    payload["cluster_estimates"][0]["metric_id"] = "different-metric"
    checksum = content_checksum(
        {
            key: value
            for key, value in payload.items()
            if key not in {"manifest_id", "content_checksum"}
        }
    )
    payload["content_checksum"] = checksum
    payload["manifest_id"] = f"CLUSTER-OBSERVATIONS-{checksum[:20]}"

    with pytest.raises(ValidationError, match="cluster estimate belongs to another metric"):
        evaluation.ClusterObservationManifest.model_validate(payload)


def test_semantic_duplicate_inside_cluster_cannot_narrow_precision() -> None:
    contract, rows = _cluster_fixture()
    original = evaluation.cluster_bootstrap_precision(contract, rows)
    duplicate = rows[4].model_copy(update={"observation_id": "REISSUED-SAME-SOURCE-ROW"})

    duplicated = evaluation.cluster_bootstrap_precision(contract, (*rows, duplicate))

    assert duplicated == original
    assert duplicated.input_manifest.observation_count == len(rows)
    assert duplicated.effective_cluster_count == original.effective_cluster_count


def test_process_builder_resolves_only_real_report_questions_claims_and_evidence() -> None:
    builder = getattr(evaluation, "build_evaluation_process_observations", None)
    assert builder is not None, "content-addressed process-observation builder is missing"
    quick_design_fixture = importlib.import_module("test_prd_v8_quick_design")
    module, submission = quick_design_fixture._submission()
    report = module.run_quick_design_v8(
        submission,
        conformance_bundle=base.load_canonical_bundle(
            quick_design_fixture.runtime_fixture.REPOSITORY_ROOT
        ),
    ).report_bundle
    snapshot = evaluation.snapshot_report_bundle(report)
    section = report.query_sections[0]
    question_id = section.questions[0].question_id
    claim_id = section.claim_set.claims[0].claim_id
    evidence_id = report.evidence_records[0].evidence_id
    attribution = evaluation.QuestionAttributionSnapshot(
        query_id=section.inferential_query.id,
        question_id=question_id,
        claim_ids=KnowledgeValue[tuple[str, ...]](
            knowledge_state=KnowledgeState.PRESENT,
            value=(claim_id,),
            evidence_ids=(evidence_id,),
            query_scope_id=section.inferential_query.id,
        ),
    )
    usefulness = evaluation.QuestionUsefulnessObservation(
        query_id=section.inferential_query.id,
        question_id=question_id,
        reviewer_actor_ids=("REVIEWER-A", "REVIEWER-B"),
        answerable=_query_value(True, scope=section.inferential_query.id, evidence_id=evidence_id),
        relevance=_query_value(5, scope=section.inferential_query.id, evidence_id=evidence_id),
        scenario_resolved=_query_value(
            True, scope=section.inferential_query.id, evidence_id=evidence_id
        ),
        output_changing=_query_value(
            True, scope=section.inferential_query.id, evidence_id=evidence_id
        ),
        redundant=_query_value(False, scope=section.inferential_query.id, evidence_id=evidence_id),
        recipient_correct=_query_value(
            True, scope=section.inferential_query.id, evidence_id=evidence_id
        ),
        response_time_seconds=_query_value(
            Decimal("10"), scope=section.inferential_query.id, evidence_id=evidence_id
        ),
        evidence_requested=_query_value(
            (evidence_id,), scope=section.inferential_query.id, evidence_id=evidence_id
        ),
        remaining_scenario_coverage=_query_value(
            "reviewed remaining coverage",
            scope=section.inferential_query.id,
            evidence_id=evidence_id,
        ),
    )
    process = builder(
        report=report,
        time_to_confirmed_report=_query_value(
            evaluation.TimeToConfirmedReportObservation(
                report_seconds=Decimal("20"), manual_baseline_seconds=Decimal("40")
            ),
            scope=report.report_id,
            evidence_id=evidence_id,
        ),
        decisive_human_correction_count=_query_value(
            0, scope=report.report_id, evidence_id=evidence_id
        ),
        question_attributions=(attribution,),
        question_usefulness=(usefulness,),
        evidence_ids=(evidence_id,),
    )
    reference = evaluation.build_independent_report_reference(
        reference_id="REF-CONFORMANCE-PROCESS",
        purpose=evaluation.IndependentReferencePurpose.CONFORMANCE_ONLY,
        report_scope_id=report.report_id,
        snapshot=snapshot,
        source_record_ids=(report.source_records[0].source_id,),
        evidence_ids=(evidence_id,),
        reviewer_actor_ids=("REVIEWER-INDEPENDENT",),
    )
    result = evaluation.evaluate_end_to_end(
        snapshot,
        KnowledgeValue[evaluation.IndependentReportReference](
            knowledge_state=KnowledgeState.PRESENT,
            value=reference,
            evidence_ids=(evidence_id,),
            query_scope_id=report.report_id,
        ),
        process_observations=process,
        process_report_bundles=(report,),
    )

    assert process.report_checksum == report.content_checksum
    assert process.content_checksum
    assert "SRR-V8-EVAL-PROCESS-METRICS" not in {item.issue_id for item in result.blockers}
    assert result.question_usefulness.knowledge_state is KnowledgeState.PRESENT
