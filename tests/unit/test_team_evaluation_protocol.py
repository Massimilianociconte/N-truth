"""Fail-closed regressions for the preregistered H/A/H+A team evaluation protocol."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from ntruth.team_evaluation import (
    AUTOMATION_BIAS_EVENT_KINDS,
    MANDATORY_CONDITIONS,
    AutomationBiasEventKind,
    AutomationBiasEventRecord,
    CaseGroupingLevel,
    CaseGroupingSpec,
    ClaimKind,
    ClaimPolicyRule,
    ClusterAwarenessDimension,
    ClusteredAnalysisPlan,
    ComplementarityBasis,
    DecisionRegion,
    DecisionRegionKind,
    ExperimentalDesign,
    ExperimentCondition,
    InitialHumanJudgement,
    InitialJudgementCaptureSubset,
    JudgementDisposition,
    LoggingContract,
    MissingDataRule,
    PreregistrationStatus,
    PrimaryOutcomeMetric,
    RandomizationSeedCommitment,
    ReferencePolicy,
    SecondaryOutcomeMetric,
    StoppingRule,
    StratificationFactor,
    StratificationSpec,
    TeamCondition,
    TeamEvaluationProtocolRecord,
    TeamMetricPreregistration,
    TeamSessionObservation,
    TrialArmAssignment,
    WashoutTrainingPeriod,
)

PREREGISTERED_AT = datetime(2026, 8, 1, 9, 0, 0, tzinfo=UTC)
SEED_COMMITTED_AT = datetime(2026, 7, 15, 9, 0, 0, tzinfo=UTC)
SEALED_SEED_FINGERPRINT = hashlib.sha256(b"sealed-randomization-seed").hexdigest()


def _conditions() -> tuple[ExperimentCondition, ...]:
    return (
        ExperimentCondition(
            condition=TeamCondition.H,
            label="Human-only",
            workflow_spec="Reviewer completes the report without AI candidate output.",
        ),
        ExperimentCondition(
            condition=TeamCondition.A,
            label="AI-only diagnostic",
            workflow_spec="Candidate pipeline output, never presented as intended use.",
            diagnostic_only=True,
            ai_candidate_ref="candidate-pipeline-v0",
        ),
        ExperimentCondition(
            condition=TeamCondition.H_PLUS_A,
            label="Full human+AI workflow",
            workflow_spec="Reviewer works with candidate output, explanations and UI support.",
            ai_candidate_ref="candidate-pipeline-v0",
        ),
    )


def _decision_regions() -> tuple[DecisionRegion, ...]:
    return (
        DecisionRegion(
            metric=PrimaryOutcomeMetric.DECISIVE_CLAIM_CORRECTNESS,
            kind=DecisionRegionKind.SUPERIORITY,
            treatment_condition=TeamCondition.H_PLUS_A,
            comparator_condition=TeamCondition.H,
        ),
        DecisionRegion(
            metric=PrimaryOutcomeMetric.CRITICAL_FALSE_CERTAINTY_RATE,
            kind=DecisionRegionKind.NON_INFERIORITY,
            treatment_condition=TeamCondition.H_PLUS_A,
            comparator_condition=TeamCondition.H,
            margin=Decimal("0.02"),
        ),
        DecisionRegion(
            metric=PrimaryOutcomeMetric.ACTIVE_REVIEW_TIME,
            kind=DecisionRegionKind.NON_INFERIORITY,
            treatment_condition=TeamCondition.H_PLUS_A,
            comparator_condition=TeamCondition.H,
            margin=Decimal("300"),
        ),
        DecisionRegion(
            metric=PrimaryOutcomeMetric.UNRESOLVED_MATERIAL_GAP_DETECTION,
            kind=DecisionRegionKind.SUPERIORITY,
            treatment_condition=TeamCondition.H_PLUS_A,
            comparator_condition=TeamCondition.H,
        ),
    )


def _claim_policy() -> tuple[ClaimPolicyRule, ...]:
    return (
        ClaimPolicyRule(
            claim_kind=ClaimKind.TIME_SAVING,
            criterion_metric=PrimaryOutcomeMetric.CRITICAL_FALSE_CERTAINTY_RATE,
        ),
        ClaimPolicyRule(
            claim_kind=ClaimKind.SAFETY_ACCURACY_IMPROVEMENT,
            criterion_metric=PrimaryOutcomeMetric.DECISIVE_CLAIM_CORRECTNESS,
            comparator_condition=TeamCondition.H,
        ),
        ClaimPolicyRule(
            claim_kind=ClaimKind.COMPLEMENTARITY,
            complementarity_basis=ComplementarityBasis.EXCEEDS_BOTH_ON_PREREGISTERED_CRITERION,
            criterion_metric=PrimaryOutcomeMetric.UNRESOLVED_MATERIAL_GAP_DETECTION,
        ),
    )


def _metric_preregistrations() -> TeamMetricPreregistration:
    return TeamMetricPreregistration(
        primary_outcomes=tuple(PrimaryOutcomeMetric),
        secondary_outcomes=tuple(SecondaryOutcomeMetric),
        decision_regions=_decision_regions(),
        analysis_plan=ClusteredAnalysisPlan(
            clustered_by=(
                ClusterAwarenessDimension.PARTICIPANT,
                ClusterAwarenessDimension.CASE_FAMILY,
            ),
            estimation_description="Mixed-effects estimates per preregistered decision region.",
            uncertainty_description="Cluster-robust confidence intervals.",
        ),
        claim_policy=_claim_policy(),
    )


def _protocol(**overrides: object) -> TeamEvaluationProtocolRecord:
    payload: dict[str, object] = {
        "protocol_id": "TEAM-EVAL-V0.1",
        "status": PreregistrationStatus.PREREGISTRATION_DRAFT,
        "data_collection_started": False,
        "preregistered_at": PREREGISTERED_AT,
        "design": ExperimentalDesign.CROSSOVER_COUNTERBALANCED,
        "conditions": _conditions(),
        "stratification": StratificationSpec(
            factors=(StratificationFactor.ROLE, StratificationFactor.EXPERIENCE),
            stratum_labels=("staff-senior", "phd-junior"),
        ),
        "case_grouping": CaseGroupingSpec(
            levels=(CaseGroupingLevel.STUDY_FAMILY, CaseGroupingLevel.LAB_CLUSTER),
            isolation_between_conditions=True,
        ),
        "washout_training": WashoutTrainingPeriod(
            washout_days=14,
            training_description="Training cases with the UI before the first crossover arm.",
            learning_carryover_assessment_planned=True,
        ),
        "randomization_seed_commitment": RandomizationSeedCommitment(
            sealed_seed_fingerprint=SEALED_SEED_FINGERPRINT,
            generator="hashlib-based Fisher-Yates over frozen case bundle",
            committed_before_enrollment_at=SEED_COMMITTED_AT,
            covers_arm_allocation=True,
            covers_case_order=True,
        ),
        "reference_policy": ReferencePolicy.INDEPENDENT_BLIND,
        "uniform_source_access": True,
        "time_budget_declared_uniform": True,
        "initial_judgement_capture": InitialJudgementCaptureSubset(
            captured_before_ai_display=True,
            subset_fraction=Decimal("0.25"),
            blinding_enforced_until_capture=True,
            rationale="Estimate anchoring on a blinded case subset.",
        ),
        "logging_contract": LoggingContract(
            log_accept_reject_override=True,
            log_evidence_inspection=True,
            log_active_review_time=True,
        ),
        "missing_data_rules": (
            MissingDataRule(
                metric_scope="ACTIVE_REVIEW_TIME",
                policy="MULTIPLE_IMPUTATION_WITH_SENSITIVITY",
                rationale="Session crashes must not silently drop arm time.",
            ),
        ),
        "stopping_rule": StoppingRule(
            max_participants=24,
            max_cases=120,
            early_stop_criteria=("critical false-certainty above preregistered bound",),
            stop_on_unacceptable_critical_error_rate=True,
        ),
        "metric_preregistrations": _metric_preregistrations(),
    }
    payload.update(overrides)
    return TeamEvaluationProtocolRecord.model_validate(payload)


def test_valid_protocol_record_validates_and_enrolls_mandatory_conditions() -> None:
    protocol = _protocol()
    assert protocol.enrolled_conditions == set(TeamCondition) - {
        TeamCondition.H_PLUS_A_NO_EXPLANATIONS,
        TeamCondition.UI_VARIANT,
    }
    assert protocol.enrolled_conditions >= MANDATORY_CONDITIONS


def test_serialization_round_trip_preserves_the_preregistered_protocol() -> None:
    protocol = _protocol()
    encoded = protocol.model_dump_json()
    restored = TeamEvaluationProtocolRecord.model_validate_json(encoded)
    assert restored == protocol
    assert restored.model_dump_json() == encoded


def test_protocol_is_immutable() -> None:
    protocol = _protocol()
    with pytest.raises(ValidationError):
        protocol.uniform_source_access = False


def test_missing_h_plus_a_condition_is_rejected() -> None:
    incomplete = tuple(
        condition
        for condition in _conditions()
        if condition.condition is not TeamCondition.H_PLUS_A
    )
    with pytest.raises(ValueError, match="H_PLUS_A"):
        _protocol(conditions=incomplete)


def test_missing_human_only_condition_is_rejected() -> None:
    incomplete = tuple(
        condition for condition in _conditions() if condition.condition is not TeamCondition.H
    )
    with pytest.raises(ValueError, match="mandatory conditions"):
        _protocol(conditions=incomplete)


def test_diagnostic_ai_only_condition_must_be_marked_diagnostic() -> None:
    with pytest.raises(ValueError, match="diagnostic-only"):
        ExperimentCondition(
            condition=TeamCondition.A,
            label="AI-only diagnostic",
            workflow_spec="Candidate pipeline output.",
            diagnostic_only=False,
            ai_candidate_ref="candidate-pipeline-v0",
        )


@pytest.mark.parametrize(
    ("policy", "message"),
    [
        (ReferencePolicy.SAME_TEAM_UNBLINDED, "independent"),
        (ReferencePolicy.AI_SELF_REVIEW, "independent"),
        (ReferencePolicy.CONFORMANCE_FIXTURE_ONLY, "independent"),
    ],
)
def test_non_independent_reference_policy_is_fail_closed(
    policy: ReferencePolicy, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _protocol(reference_policy=policy)


def test_missing_decision_region_is_fail_closed() -> None:
    metrics = _metric_preregistrations()
    empty = metrics.model_copy(update={"decision_regions": ()})
    with pytest.raises(ValueError, match="decision region"):
        TeamMetricPreregistration.model_validate(empty.model_dump())


def test_primary_outcome_without_decision_region_is_fail_closed() -> None:
    regions = tuple(
        region
        for region in _decision_regions()
        if region.metric is not PrimaryOutcomeMetric.ACTIVE_REVIEW_TIME
    )
    with pytest.raises(ValueError, match="ACTIVE_REVIEW_TIME"):
        TeamMetricPreregistration.model_validate(
            _metric_preregistrations().model_copy(update={"decision_regions": regions}).model_dump()
        )


def test_missing_primary_outcome_is_fail_closed() -> None:
    reduced = tuple(
        metric
        for metric in PrimaryOutcomeMetric
        if metric is not PrimaryOutcomeMetric.CRITICAL_FALSE_CERTAINTY_RATE
    )
    with pytest.raises(ValueError, match="primary outcomes"):
        _protocol(
            metric_preregistrations=_metric_preregistrations().model_copy(
                update={"primary_outcomes": reduced}
            )
        )


def test_analysis_plan_must_cluster_by_participant_and_case_family() -> None:
    with pytest.raises(ValueError, match="participant AND case family"):
        ClusteredAnalysisPlan(
            clustered_by=(ClusterAwarenessDimension.PARTICIPANT,),
            estimation_description="Mixed-effects estimates.",
            uncertainty_description="Cluster-robust intervals.",
        )
    plan = ClusteredAnalysisPlan(
        clustered_by=(
            ClusterAwarenessDimension.PARTICIPANT,
            ClusterAwarenessDimension.CASE_FAMILY,
        ),
        estimation_description="Mixed-effects estimates per preregistered decision region.",
        uncertainty_description="Cluster-robust confidence intervals.",
    )
    assert set(plan.clustered_by) == {
        ClusterAwarenessDimension.PARTICIPANT,
        ClusterAwarenessDimension.CASE_FAMILY,
    }


def test_uniform_source_access_is_mandatory() -> None:
    with pytest.raises(ValueError, match="uniform source access"):
        _protocol(uniform_source_access=False)


def test_time_saving_claim_without_non_inferior_critical_risk_region_is_fail_closed() -> None:
    regions = tuple(
        region.model_copy(update={"kind": DecisionRegionKind.SUPERIORITY, "margin": None})
        if (
            region.metric is PrimaryOutcomeMetric.CRITICAL_FALSE_CERTAINTY_RATE
            and region.kind is DecisionRegionKind.NON_INFERIORITY
        )
        else region
        for region in _decision_regions()
    )
    with pytest.raises(ValueError, match="non-inferior critical-risk region"):
        _protocol(
            metric_preregistrations=_metric_preregistrations().model_copy(
                update={"decision_regions": regions}
            )
        )


def test_accuracy_claim_requires_human_comparator_region() -> None:
    with pytest.raises(ValueError, match="human-only comparator"):
        ClaimPolicyRule(
            claim_kind=ClaimKind.SAFETY_ACCURACY_IMPROVEMENT,
            criterion_metric=PrimaryOutcomeMetric.DECISIVE_CLAIM_CORRECTNESS,
            comparator_condition=TeamCondition.A,
        )
    rules = (
        ClaimPolicyRule(
            claim_kind=ClaimKind.SAFETY_ACCURACY_IMPROVEMENT,
            criterion_metric=PrimaryOutcomeMetric.DECISIVE_CLAIM_CORRECTNESS,
            comparator_condition=TeamCondition.H,
        ),
    )

    def _misaligned(region: DecisionRegion) -> DecisionRegion:
        if region.metric is not PrimaryOutcomeMetric.DECISIVE_CLAIM_CORRECTNESS:
            return region
        return region.model_copy(
            update={
                "treatment_condition": TeamCondition.A,
                "comparator_condition": TeamCondition.H_PLUS_A,
            }
        )

    misaligned_regions = tuple(_misaligned(region) for region in _decision_regions())
    with pytest.raises(ValueError, match="accuracy/safety criterion"):
        _protocol(
            metric_preregistrations=_metric_preregistrations().model_copy(
                update={"claim_policy": rules, "decision_regions": misaligned_regions}
            )
        )


def test_complementarity_requires_registered_basis_and_backing_region() -> None:
    with pytest.raises(ValueError, match="preregistered basis"):
        ClaimPolicyRule(claim_kind=ClaimKind.COMPLEMENTARITY)
    with pytest.raises(ValueError, match="Pareto"):
        ClaimPolicyRule(
            claim_kind=ClaimKind.COMPLEMENTARITY,
            complementarity_basis=ComplementarityBasis.JUSTIFIED_PARETO_TRADE_OFF,
        )
    exceeds_both = ClaimPolicyRule(
        claim_kind=ClaimKind.COMPLEMENTARITY,
        complementarity_basis=ComplementarityBasis.EXCEEDS_BOTH_ON_PREREGISTERED_CRITERION,
        criterion_metric=PrimaryOutcomeMetric.ACTIVE_REVIEW_TIME,
    )
    with pytest.raises(ValueError, match="superiority of H\\+A"):
        _protocol(
            metric_preregistrations=_metric_preregistrations().model_copy(
                update={"claim_policy": (exceeds_both,)}
            )
        )


def test_non_inferiority_region_requires_preregistered_margin() -> None:
    with pytest.raises(ValueError, match="margin"):
        DecisionRegion(
            metric=PrimaryOutcomeMetric.CRITICAL_FALSE_CERTAINTY_RATE,
            kind=DecisionRegionKind.NON_INFERIORITY,
            treatment_condition=TeamCondition.H_PLUS_A,
            comparator_condition=TeamCondition.H,
        )


def test_decision_region_cannot_compare_a_condition_with_itself() -> None:
    with pytest.raises(ValueError, match="itself"):
        DecisionRegion(
            metric=PrimaryOutcomeMetric.DECISIVE_CLAIM_CORRECTNESS,
            kind=DecisionRegionKind.SUPERIORITY,
            treatment_condition=TeamCondition.H,
            comparator_condition=TeamCondition.H,
        )


def test_draft_protocol_cannot_have_started_data_collection() -> None:
    with pytest.raises(ValueError, match="draft preregistration"):
        _protocol(data_collection_started=True)


def test_crossover_design_requires_washout_period() -> None:
    washout = WashoutTrainingPeriod(
        washout_days=0,
        training_description="Training session.",
        learning_carryover_assessment_planned=True,
    )
    with pytest.raises(ValueError, match="washout"):
        _protocol(washout_training=washout)


def test_extra_fields_are_forbidden() -> None:
    with pytest.raises(ValidationError, match="extra"):
        _protocol(observed_effect=Decimal("0.5"))


def test_automation_bias_event_kinds_match_prd_v9_am4() -> None:
    assert set(AUTOMATION_BIAS_EVENT_KINDS) == {
        AutomationBiasEventKind.COMMISSION_ERROR,
        AutomationBiasEventKind.OMISSION_ERROR,
        AutomationBiasEventKind.ANCHORING,
        AutomationBiasEventKind.CONFIRMATION_FATIGUE,
        AutomationBiasEventKind.SELECTIVE_DISTRUST,
        AutomationBiasEventKind.EXPLANATION_INDUCED_OVERACCEPTANCE,
    }


def _bias_event(**overrides: object) -> AutomationBiasEventRecord:
    payload: dict[str, object] = {
        "event_id": "ABE-001",
        "session_id": "SESSION-001",
        "case_id": "CASE-007",
        "event_kind": AutomationBiasEventKind.COMMISSION_ERROR,
        "disposition": JudgementDisposition.ACCEPTED,
        "ai_candidate_ref": "candidate-pipeline-v0",
        "evidence_opened_before_confirm": False,
    }
    payload.update(overrides)
    return AutomationBiasEventRecord.model_validate(payload)


def test_commission_error_requires_accepted_ai_candidate() -> None:
    with pytest.raises(ValueError, match="accepted AI candidate"):
        _bias_event(ai_candidate_ref=None)
    with pytest.raises(ValueError, match="accepted AI candidate"):
        _bias_event(disposition=JudgementDisposition.REJECTED)


def test_omission_error_requires_unopened_evidence() -> None:
    with pytest.raises(ValueError, match="evidence was not opened"):
        _bias_event(
            event_kind=AutomationBiasEventKind.OMISSION_ERROR,
            evidence_opened_before_confirm=True,
        )
    event = _bias_event(event_kind=AutomationBiasEventKind.OMISSION_ERROR)
    assert event.evidence_opened_before_confirm is False


def test_anchoring_requires_initial_human_judgement() -> None:
    with pytest.raises(ValueError, match="initial human judgement"):
        _bias_event(
            event_kind=AutomationBiasEventKind.ANCHORING,
            disposition=JudgementDisposition.CORRECTED,
        )
    anchored = _bias_event(
        event_kind=AutomationBiasEventKind.ANCHORING,
        disposition=JudgementDisposition.CORRECTED,
        initial_human_judgement=InitialHumanJudgement(
            case_id="CASE-007",
            summary="Initial judgement: contrast not supported.",
            recorded_content_fingerprint=hashlib.sha256(b"initial-judgement").hexdigest(),
            captured_before_ai_display=True,
        ),
    )
    assert anchored.initial_human_judgement is not None
    assert anchored.initial_human_judgement.captured_before_ai_display is True


def test_trial_arm_assignment_requires_randomized_case_order() -> None:
    with pytest.raises(ValueError, match="randomized case order"):
        TrialArmAssignment(
            participant_id="P-001",
            stratum_id="staff-senior",
            condition=TeamCondition.H_PLUS_A,
            case_family_cluster_id="FAMILY-LAB-A",
            sequence_index=0,
            case_order_randomized=False,
        )


def _session_observation(**overrides: object) -> TeamSessionObservation:
    payload: dict[str, object] = {
        "session_id": "SESSION-001",
        "participant_id": "P-001",
        "condition": TeamCondition.H_PLUS_A,
        "case_family_id": "FAMILY-LAB-A",
        "case_ids": ("CASE-007", "CASE-008"),
        "initial_judgement_captured": True,
        "accepted_count": 3,
        "rejected_count": 2,
        "override_count": 1,
        "evidence_inspection_events": 7,
        "active_review_seconds": Decimal("1800"),
        "total_elapsed_seconds": Decimal("2400"),
        "automation_bias_events": (_bias_event(),),
    }
    payload.update(overrides)
    return TeamSessionObservation.model_validate(payload)


def test_session_observation_round_trip() -> None:
    session = _session_observation()
    restored = TeamSessionObservation.model_validate_json(session.model_dump_json())
    assert restored == session


def test_session_active_time_cannot_exceed_elapsed_time() -> None:
    with pytest.raises(ValueError, match="exceed total elapsed"):
        _session_observation(active_review_seconds=Decimal("9999"))


def test_human_only_session_cannot_log_ai_interactions() -> None:
    with pytest.raises(ValueError, match="human-only"):
        _session_observation(condition=TeamCondition.H)
    with pytest.raises(ValueError, match="human-only"):
        _session_observation(
            condition=TeamCondition.H,
            accepted_count=0,
            rejected_count=0,
            override_count=0,
        )


def test_session_bias_events_must_belong_to_the_session() -> None:
    foreign = _bias_event(session_id="SESSION-999")
    with pytest.raises(ValueError, match="another session"):
        _session_observation(automation_bias_events=(foreign,))
