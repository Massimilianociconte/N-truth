"""Preregistered H/A/H+A team evaluation contracts (PRD v9 §18.9, §24.2-24.7, Appendix AM).

These models describe the preregistered experimental protocol only. They contain
no collected data, no observed results and no release authority: a protocol
record can never promote an AI or team claim by itself.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Final, Literal, Self

from pydantic import AwareDatetime, ConfigDict, Field, model_validator

from ntruth.schemas.core import FrozenModel
from ntruth.schemas.kernel import NonBlankStr

TEAM_EVALUATION_SCHEMA_VERSION: Literal["9.0.0"] = "9.0.0"
Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class TeamEvaluationModel(FrozenModel):
    """Strict, immutable base for preregistered team-evaluation contracts."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
        use_enum_values=False,
    )


class PreregistrationStatus(StrEnum):
    PREREGISTRATION_DRAFT = "PREREGISTRATION_DRAFT"
    FROZEN_PREREGISTRATION = "FROZEN_PREREGISTRATION"


class ExperimentalDesign(StrEnum):
    CROSSOVER_COUNTERBALANCED = "CROSSOVER_COUNTERBALANCED"
    PARALLEL_CLUSTER_RANDOMIZED = "PARALLEL_CLUSTER_RANDOMIZED"


class ReferencePolicy(StrEnum):
    INDEPENDENT_BLIND = "INDEPENDENT_BLIND"
    SAME_TEAM_UNBLINDED = "SAME_TEAM_UNBLINDED"
    AI_SELF_REVIEW = "AI_SELF_REVIEW"
    CONFORMANCE_FIXTURE_ONLY = "CONFORMANCE_FIXTURE_ONLY"


class TeamCondition(StrEnum):
    H = "H"
    A = "A"
    H_PLUS_A = "H_PLUS_A"
    H_PLUS_A_NO_EXPLANATIONS = "H_PLUS_A_NO_EXPLANATIONS"
    UI_VARIANT = "UI_VARIANT"


MANDATORY_CONDITIONS: Final[frozenset[TeamCondition]] = frozenset(
    {
        TeamCondition.H,
        TeamCondition.A,
        TeamCondition.H_PLUS_A,
    }
)


class PrimaryOutcomeMetric(StrEnum):
    DECISIVE_CLAIM_CORRECTNESS = "DECISIVE_CLAIM_CORRECTNESS"
    CRITICAL_FALSE_CERTAINTY_RATE = "CRITICAL_FALSE_CERTAINTY_RATE"
    ACTIVE_REVIEW_TIME = "ACTIVE_REVIEW_TIME"
    UNRESOLVED_MATERIAL_GAP_DETECTION = "UNRESOLVED_MATERIAL_GAP_DETECTION"

    @classmethod
    def required_set(cls) -> frozenset[PrimaryOutcomeMetric]:
        return frozenset(cls)


class SecondaryOutcomeMetric(StrEnum):
    EVIDENCE_INSPECTION = "EVIDENCE_INSPECTION"
    CORRECTION_ACCEPTANCE_PATTERNS = "CORRECTION_ACCEPTANCE_PATTERNS"
    CONFIDENCE_CALIBRATION = "CONFIDENCE_CALIBRATION"
    QUESTION_USEFULNESS = "QUESTION_USEFULNESS"
    SUBJECTIVE_BURDEN_COMPREHENSION = "SUBJECTIVE_BURDEN_COMPREHENSION"
    SUBGROUP_HETEROGENEITY = "SUBGROUP_HETEROGENEITY"

    @classmethod
    def required_set(cls) -> frozenset[SecondaryOutcomeMetric]:
        return frozenset(cls)


class DecisionRegionKind(StrEnum):
    SUPERIORITY = "SUPERIORITY"
    NON_INFERIORITY = "NON_INFERIORITY"


class ClusterAwarenessDimension(StrEnum):
    PARTICIPANT = "PARTICIPANT"
    CASE_FAMILY = "CASE_FAMILY"


class ClaimKind(StrEnum):
    TIME_SAVING = "TIME_SAVING"
    SAFETY_ACCURACY_IMPROVEMENT = "SAFETY_ACCURACY_IMPROVEMENT"
    COMPLEMENTARITY = "COMPLEMENTARITY"


class ComplementarityBasis(StrEnum):
    EXCEEDS_BOTH_ON_PREREGISTERED_CRITERION = "EXCEEDS_BOTH_ON_PREREGISTERED_CRITERION"
    JUSTIFIED_PARETO_TRADE_OFF = "JUSTIFIED_PARETO_TRADE_OFF"


class StratificationFactor(StrEnum):
    ROLE = "ROLE"
    EXPERIENCE = "EXPERIENCE"


class CaseGroupingLevel(StrEnum):
    STUDY_FAMILY = "STUDY_FAMILY"
    LAB_CLUSTER = "LAB_CLUSTER"


class AutomationBiasEventKind(StrEnum):
    COMMISSION_ERROR = "COMMISSION_ERROR"
    OMISSION_ERROR = "OMISSION_ERROR"
    ANCHORING = "ANCHORING"
    CONFIRMATION_FATIGUE = "CONFIRMATION_FATIGUE"
    SELECTIVE_DISTRUST = "SELECTIVE_DISTRUST"
    EXPLANATION_INDUCED_OVERACCEPTANCE = "EXPLANATION_INDUCED_OVERACCEPTANCE"


AUTOMATION_BIAS_EVENT_KINDS: Final[tuple[AutomationBiasEventKind, ...]] = tuple(
    AutomationBiasEventKind
)


class JudgementDisposition(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    CORRECTED = "CORRECTED"


class ExperimentCondition(TeamEvaluationModel):
    condition: TeamCondition
    label: NonBlankStr
    workflow_spec: NonBlankStr
    diagnostic_only: bool = False
    ai_candidate_ref: NonBlankStr | None = None

    @model_validator(mode="after")
    def _condition_complete(self) -> Self:
        uses_ai = self.condition in {
            TeamCondition.A,
            TeamCondition.H_PLUS_A,
            TeamCondition.H_PLUS_A_NO_EXPLANATIONS,
            TeamCondition.UI_VARIANT,
        }
        if uses_ai and self.ai_candidate_ref is None:
            raise ValueError(
                f"condition {self.condition.value} requires an ai_candidate_ref to be complete"
            )
        if not uses_ai and self.ai_candidate_ref is not None:
            raise ValueError(f"condition {self.condition.value} must not reference an AI candidate")
        if self.condition is TeamCondition.A and not self.diagnostic_only:
            raise ValueError(
                "the A condition is diagnostic-only and must never be presented as intended use"
            )
        if (
            self.condition in {TeamCondition.H_PLUS_A, TeamCondition.H_PLUS_A_NO_EXPLANATIONS}
            and self.diagnostic_only
        ):
            raise ValueError(
                f"condition {self.condition.value} is the full workflow, not diagnostic"
            )
        return self


class StratificationSpec(TeamEvaluationModel):
    factors: tuple[StratificationFactor, ...] = Field(min_length=2)
    stratum_labels: tuple[NonBlankStr, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def _role_and_experience(self) -> Self:
        if set(self.factors) != {StratificationFactor.ROLE, StratificationFactor.EXPERIENCE}:
            raise ValueError("participant stratification must cover role and experience")
        if len(set(self.stratum_labels)) != len(self.stratum_labels):
            raise ValueError("stratification stratum labels must be distinct")
        return self


class CaseGroupingSpec(TeamEvaluationModel):
    levels: tuple[CaseGroupingLevel, ...] = Field(min_length=2)
    isolation_between_conditions: bool

    @model_validator(mode="after")
    def _family_and_lab_clusters(self) -> Self:
        if set(self.levels) != {CaseGroupingLevel.STUDY_FAMILY, CaseGroupingLevel.LAB_CLUSTER}:
            raise ValueError("case grouping must retain study-family and lab-cluster levels")
        if not self.isolation_between_conditions:
            raise ValueError("case families must be isolated across experimental conditions")
        return self


class WashoutTrainingPeriod(TeamEvaluationModel):
    washout_days: int = Field(ge=0)
    training_description: NonBlankStr
    learning_carryover_assessment_planned: bool

    @model_validator(mode="after")
    def _crossover_requires_washout(self) -> Self:
        if not self.learning_carryover_assessment_planned:
            raise ValueError("learning/carryover assessment must be preregistered")
        return self


class RandomizationSeedCommitment(TeamEvaluationModel):
    sealed_seed_fingerprint: Sha256Hex
    generator: NonBlankStr
    committed_before_enrollment_at: AwareDatetime
    covers_arm_allocation: bool
    covers_case_order: bool

    @model_validator(mode="after")
    def _covers_allocation_and_order(self) -> Self:
        if not (self.covers_arm_allocation and self.covers_case_order):
            raise ValueError(
                "randomization seed commitment must cover arm allocation and case order"
            )
        return self


class InitialJudgementCaptureSubset(TeamEvaluationModel):
    captured_before_ai_display: Literal[True]
    subset_fraction: Decimal = Field(gt=Decimal("0"), le=Decimal("1"))
    blinding_enforced_until_capture: bool
    rationale: NonBlankStr

    @model_validator(mode="after")
    def _blind_capture(self) -> Self:
        if not self.blinding_enforced_until_capture:
            raise ValueError("initial-judgement capture must be blinded to the AI candidate")
        return self


class LoggingContract(TeamEvaluationModel):
    log_accept_reject_override: Literal[True]
    log_evidence_inspection: Literal[True]
    log_active_review_time: Literal[True]


class MissingDataRule(TeamEvaluationModel):
    metric_scope: NonBlankStr
    policy: NonBlankStr
    rationale: NonBlankStr


class StoppingRule(TeamEvaluationModel):
    max_participants: int = Field(ge=1)
    max_cases: int = Field(ge=1)
    early_stop_criteria: tuple[NonBlankStr, ...] = Field(min_length=1)
    stop_on_unacceptable_critical_error_rate: bool

    @model_validator(mode="after")
    def _safety_stop_preregistered(self) -> Self:
        if not self.stop_on_unacceptable_critical_error_rate:
            raise ValueError("stopping rule must preregister a critical-error safety stop")
        return self


class DecisionRegion(TeamEvaluationModel):
    metric: PrimaryOutcomeMetric
    kind: DecisionRegionKind
    treatment_condition: TeamCondition
    comparator_condition: TeamCondition
    margin: Decimal | None = Field(default=None, ge=Decimal("0"))

    @model_validator(mode="after")
    def _closed_region(self) -> Self:
        if self.treatment_condition is self.comparator_condition:
            raise ValueError("decision region cannot compare a condition with itself")
        if self.kind is DecisionRegionKind.NON_INFERIORITY and self.margin is None:
            raise ValueError(
                f"non-inferiority region for {self.metric.value} requires a preregistered margin"
            )
        return self


class ClusteredAnalysisPlan(TeamEvaluationModel):
    clustered_by: tuple[ClusterAwarenessDimension, ...]
    estimation_description: NonBlankStr
    uncertainty_description: NonBlankStr

    @model_validator(mode="after")
    def _clustered_by_participant_and_case_family(self) -> Self:
        if set(self.clustered_by) != {
            ClusterAwarenessDimension.PARTICIPANT,
            ClusterAwarenessDimension.CASE_FAMILY,
        }:
            raise ValueError(
                "analysis plan must cluster by participant AND case family (PRD v9 §24.6/AM.2)"
            )
        return self


class ClaimPolicyRule(TeamEvaluationModel):
    claim_kind: ClaimKind
    criterion_metric: PrimaryOutcomeMetric | None = None
    comparator_condition: TeamCondition | None = None
    complementarity_basis: ComplementarityBasis | None = None
    pareto_justification: NonBlankStr | None = None

    @model_validator(mode="after")
    def _claim_specific_guards(self) -> Self:
        if self.claim_kind is ClaimKind.TIME_SAVING:
            if self.criterion_metric is not PrimaryOutcomeMetric.CRITICAL_FALSE_CERTAINTY_RATE:
                raise ValueError(
                    "time-saving claims require the preregistered critical-risk "
                    "(critical false-certainty) criterion"
                )
            return self
        if self.claim_kind is ClaimKind.SAFETY_ACCURACY_IMPROVEMENT:
            if self.comparator_condition is not TeamCondition.H:
                raise ValueError("accuracy/safety claims require the human-only comparator H")
            if self.criterion_metric is None:
                raise ValueError("accuracy/safety claims require a preregistered criterion metric")
            return self
        if self.complementarity_basis is None:
            raise ValueError("complementarity claims require a preregistered basis")
        if (
            self.complementarity_basis
            is ComplementarityBasis.EXCEEDS_BOTH_ON_PREREGISTERED_CRITERION
            and self.criterion_metric is None
        ):
            raise ValueError(
                "complementarity via exceeding both arms requires a preregistered criterion metric"
            )
        if (
            self.complementarity_basis is ComplementarityBasis.JUSTIFIED_PARETO_TRADE_OFF
            and self.pareto_justification is None
        ):
            raise ValueError(
                "complementarity via Pareto trade-off requires a preregistered justification"
            )
        return self


class TeamMetricPreregistration(TeamEvaluationModel):
    primary_outcomes: tuple[PrimaryOutcomeMetric, ...]
    secondary_outcomes: tuple[SecondaryOutcomeMetric, ...]
    decision_regions: tuple[DecisionRegion, ...]
    analysis_plan: ClusteredAnalysisPlan
    claim_policy: tuple[ClaimPolicyRule, ...]

    @model_validator(mode="after")
    def _preregistered_outcomes_regions_and_claims(self) -> Self:
        if not self.decision_regions:
            raise ValueError(
                "team metric preregistration requires at least one preregistered "
                "decision region (superiority or non-inferiority)"
            )
        if not self.claim_policy:
            raise ValueError("team metric preregistration requires the claim policy")
        if set(self.primary_outcomes) != PrimaryOutcomeMetric.required_set():
            raise ValueError(
                "primary outcomes must be exactly the four PRD v9 AM.3 outcomes: "
                "decisive-claim correctness, critical false-certainty rate, active review "
                "time, unresolved material gap detection"
            )
        if len(set(self.primary_outcomes)) != len(self.primary_outcomes):
            raise ValueError("primary outcomes contain duplicates")
        if set(self.secondary_outcomes) != SecondaryOutcomeMetric.required_set():
            raise ValueError("secondary outcomes must cover all six PRD v9 AM.3 secondary outcomes")
        if len(set(self.secondary_outcomes)) != len(self.secondary_outcomes):
            raise ValueError("secondary outcomes contain duplicates")
        covered_metrics = {region.metric for region in self.decision_regions}
        missing = set(PrimaryOutcomeMetric.required_set()) - covered_metrics
        if missing:
            missing_names = ", ".join(sorted(metric.value for metric in missing))
            raise ValueError(
                "every primary outcome requires a preregistered decision region; missing: "
                f"{missing_names}"
            )
        self._validate_claim_policy()
        return self

    def _validate_claim_policy(self) -> None:
        regions = self.decision_regions
        for rule in self.claim_policy:
            if rule.claim_kind is ClaimKind.TIME_SAVING:
                self._require_region(
                    regions,
                    metric=PrimaryOutcomeMetric.CRITICAL_FALSE_CERTAINTY_RATE,
                    kind=DecisionRegionKind.NON_INFERIORITY,
                    requirement="non-inferior critical-risk region",
                )
            elif rule.claim_kind is ClaimKind.SAFETY_ACCURACY_IMPROVEMENT:
                self._require_region(
                    regions,
                    metric=rule.criterion_metric,
                    kind=None,
                    comparator=TeamCondition.H,
                    treatment=TeamCondition.H_PLUS_A,
                    requirement="H+A vs H comparison on the claimed accuracy/safety criterion",
                )
            elif (
                rule.complementarity_basis
                is ComplementarityBasis.EXCEEDS_BOTH_ON_PREREGISTERED_CRITERION
            ):
                self._require_region(
                    regions,
                    metric=rule.criterion_metric,
                    kind=DecisionRegionKind.SUPERIORITY,
                    treatment=TeamCondition.H_PLUS_A,
                    requirement=(
                        "superiority of H+A over the preregistered complementarity criterion"
                    ),
                )

    def _require_region(
        self,
        regions: tuple[DecisionRegion, ...],
        *,
        requirement: str,
        metric: PrimaryOutcomeMetric | None,
        kind: DecisionRegionKind | None = None,
        comparator: TeamCondition | None = None,
        treatment: TeamCondition | None = None,
    ) -> None:
        for region in regions:
            if metric is not None and region.metric is not metric:
                continue
            if kind is not None and region.kind is not kind:
                continue
            if comparator is not None and region.comparator_condition is not comparator:
                continue
            if treatment is not None and region.treatment_condition is not treatment:
                continue
            return
        raise ValueError(
            f"claim policy is not backed by a preregistered decision region: {requirement}"
        )


class AutomationBiasEventRecord(TeamEvaluationModel):
    event_id: NonBlankStr
    session_id: NonBlankStr
    case_id: NonBlankStr
    event_kind: AutomationBiasEventKind
    disposition: JudgementDisposition
    initial_human_judgement: InitialHumanJudgement | None = None
    ai_candidate_ref: NonBlankStr | None = None
    evidence_opened_before_confirm: bool

    @model_validator(mode="after")
    def _event_specific_evidence(self) -> Self:
        if self.event_kind is AutomationBiasEventKind.COMMISSION_ERROR and (
            self.ai_candidate_ref is None or self.disposition is not JudgementDisposition.ACCEPTED
        ):
            raise ValueError("commission error requires an accepted AI candidate suggestion")
        if self.event_kind is AutomationBiasEventKind.OMISSION_ERROR and (
            self.evidence_opened_before_confirm
        ):
            raise ValueError(
                "omission error requires that supporting/contrary evidence was not opened"
            )
        if (
            self.event_kind is AutomationBiasEventKind.ANCHORING
            and self.initial_human_judgement is None
        ):
            raise ValueError(
                "anchoring requires the initial human judgement captured before AI display"
            )
        return self


class InitialHumanJudgement(TeamEvaluationModel):
    case_id: NonBlankStr
    summary: NonBlankStr
    recorded_content_fingerprint: Sha256Hex
    captured_before_ai_display: Literal[True]


class TrialArmAssignment(TeamEvaluationModel):
    participant_id: NonBlankStr
    stratum_id: NonBlankStr
    condition: TeamCondition
    case_family_cluster_id: NonBlankStr
    sequence_index: int = Field(ge=0)
    case_order_randomized: bool

    @model_validator(mode="after")
    def _randomized_case_order(self) -> Self:
        if not self.case_order_randomized:
            raise ValueError("trial arm assignment requires randomized case order")
        return self


class TeamSessionObservation(TeamEvaluationModel):
    session_id: NonBlankStr
    participant_id: NonBlankStr
    condition: TeamCondition
    case_family_id: NonBlankStr
    case_ids: tuple[NonBlankStr, ...] = Field(min_length=1)
    initial_judgement_captured: bool
    accepted_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    override_count: int = Field(ge=0)
    evidence_inspection_events: int = Field(ge=0)
    active_review_seconds: Decimal = Field(ge=Decimal("0"))
    total_elapsed_seconds: Decimal = Field(ge=Decimal("0"))
    automation_bias_events: tuple[AutomationBiasEventRecord, ...] = ()

    @model_validator(mode="after")
    def _internally_consistent_session(self) -> Self:
        if len(set(self.case_ids)) != len(self.case_ids):
            raise ValueError("session observation contains duplicate case IDs")
        if self.active_review_seconds > self.total_elapsed_seconds:
            raise ValueError("active review time cannot exceed total elapsed time")
        if self.condition is TeamCondition.H:
            if (self.accepted_count, self.rejected_count, self.override_count) != (0, 0, 0):
                raise ValueError(
                    "human-only sessions have no AI candidate to accept, reject or override"
                )
            if self.automation_bias_events:
                raise ValueError("human-only sessions cannot contain automation-bias events")
        for event in self.automation_bias_events:
            if event.session_id != self.session_id:
                raise ValueError(
                    "session observation contains an automation-bias event of another session"
                )
        return self


class TeamEvaluationProtocolRecord(TeamEvaluationModel):
    schema_version: Literal["9.0.0"] = TEAM_EVALUATION_SCHEMA_VERSION
    protocol_id: NonBlankStr
    status: PreregistrationStatus
    data_collection_started: bool
    preregistered_at: AwareDatetime
    design: ExperimentalDesign
    conditions: tuple[ExperimentCondition, ...]
    stratification: StratificationSpec
    case_grouping: CaseGroupingSpec
    washout_training: WashoutTrainingPeriod
    randomization_seed_commitment: RandomizationSeedCommitment
    reference_policy: ReferencePolicy
    uniform_source_access: bool
    time_budget_declared_uniform: bool
    initial_judgement_capture: InitialJudgementCaptureSubset
    logging_contract: LoggingContract
    missing_data_rules: tuple[MissingDataRule, ...] = Field(min_length=1)
    stopping_rule: StoppingRule
    metric_preregistrations: TeamMetricPreregistration

    @property
    def enrolled_conditions(self) -> frozenset[TeamCondition]:
        return frozenset(condition.condition for condition in self.conditions)

    @model_validator(mode="after")
    def _fail_closed_protocol(self) -> Self:
        self._validate_conditions()
        if self.reference_policy is not ReferencePolicy.INDEPENDENT_BLIND:
            raise ValueError(
                "team evaluation requires an independent, blind reference policy "
                "(ReferencePolicy.INDEPENDENT_BLIND); "
                f"got {self.reference_policy.value}"
            )
        if not self.uniform_source_access:
            raise ValueError("uniform source access is mandatory across conditions (PRD v9 §18.9)")
        if not self.time_budget_declared_uniform:
            raise ValueError("a uniform declared time budget is mandatory across conditions")
        if self.status is PreregistrationStatus.PREREGISTRATION_DRAFT and (
            self.data_collection_started
        ):
            raise ValueError(
                "a draft preregistration cannot have started data collection; freeze the "
                "protocol first"
            )
        self._validate_design_washout_consistency()
        self._validate_decision_regions_against_conditions()
        return self

    def _validate_conditions(self) -> None:
        condition_kinds = [condition.condition for condition in self.conditions]
        if len(set(condition_kinds)) != len(condition_kinds):
            raise ValueError("protocol conditions contain duplicates")
        missing = MANDATORY_CONDITIONS - set(condition_kinds)
        if missing:
            missing_names = ", ".join(sorted(condition.value for condition in missing))
            raise ValueError(
                "team evaluation protocol is invalid without complete mandatory conditions "
                f"H, A and H+A; missing or incomplete: {missing_names}"
            )

    def _validate_design_washout_consistency(self) -> None:
        if (
            self.design is ExperimentalDesign.CROSSOVER_COUNTERBALANCED
            and self.washout_training.washout_days < 1
        ):
            raise ValueError("crossover designs require an adequate washout period")

    def _validate_decision_regions_against_conditions(self) -> None:
        enrolled = self.enrolled_conditions
        for region in self.metric_preregistrations.decision_regions:
            outside = {
                region.treatment_condition,
                region.comparator_condition,
            } - enrolled
            if outside:
                unknown = ", ".join(sorted(item.value for item in outside))
                raise ValueError(
                    f"decision region for {region.metric.value} references conditions not "
                    f"enrolled in the protocol: {unknown}"
                )


__all__ = [
    "AUTOMATION_BIAS_EVENT_KINDS",
    "MANDATORY_CONDITIONS",
    "TEAM_EVALUATION_SCHEMA_VERSION",
    "AutomationBiasEventKind",
    "AutomationBiasEventRecord",
    "CaseGroupingLevel",
    "CaseGroupingSpec",
    "ClaimKind",
    "ClaimPolicyRule",
    "ClusterAwarenessDimension",
    "ClusteredAnalysisPlan",
    "ComplementarityBasis",
    "DecisionRegion",
    "DecisionRegionKind",
    "ExperimentCondition",
    "ExperimentalDesign",
    "InitialHumanJudgement",
    "InitialJudgementCaptureSubset",
    "JudgementDisposition",
    "LoggingContract",
    "MissingDataRule",
    "PreregistrationStatus",
    "PrimaryOutcomeMetric",
    "RandomizationSeedCommitment",
    "ReferencePolicy",
    "SecondaryOutcomeMetric",
    "StoppingRule",
    "StratificationFactor",
    "StratificationSpec",
    "TeamCondition",
    "TeamEvaluationModel",
    "TeamEvaluationProtocolRecord",
    "TeamMetricPreregistration",
    "TeamSessionObservation",
    "TrialArmAssignment",
    "WashoutTrainingPeriod",
]
