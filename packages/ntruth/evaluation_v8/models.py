"""Fail-closed PRD v8 contracts for end-to-end and residual evaluation.

These models describe deterministic comparisons and the evidence needed to
interpret them.  They do not contain release thresholds and a conformance
reference can never be promoted to scientific evidence.
"""

from __future__ import annotations

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
        if (
            self.false_certainty_categories.knowledge_state is KnowledgeState.PRESENT
            and self.determinability_state is DeterminabilityState.DETERMINATE
        ):
            raise ValueError("a determinate reference claim cannot assert false-certainty risks")
        return self


class QueryEvaluationSnapshot(KernelModel):
    query_id: NonBlankStr
    report_resolution_checksum: Sha256
    claims: tuple[ClaimEvaluationSnapshot, ...] = Field(min_length=1)
    adequacy_axes: tuple[AdequacyAxisSnapshot, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _one_query_complete(self) -> Self:
        if any(claim.query_id != self.query_id for claim in self.claims):
            raise ValueError("query snapshot contains a claim from another query")
        if any(axis.query_id != self.query_id for axis in self.adequacy_axes):
            raise ValueError("query snapshot contains an adequacy axis from another query")
        claim_ids = [claim.claim_id for claim in self.claims]
        if len(set(claim_ids)) != len(claim_ids):
            raise ValueError("query snapshot contains duplicate claim IDs")
        axis_ids = [axis.axis_id for axis in self.adequacy_axes]
        if len(set(axis_ids)) != len(axis_ids):
            raise ValueError("query snapshot contains duplicate adequacy axes")
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


class IndependentReportReference(KernelModel):
    reference_id: NonBlankStr
    content_checksum: Sha256
    purpose: IndependentReferencePurpose
    report_scope_id: NonBlankStr
    snapshot: ReportEvaluationSnapshot
    source_record_ids: tuple[NonBlankStr, ...] = Field(min_length=1)
    evidence_ids: tuple[NonBlankStr, ...] = Field(min_length=1)
    reviewer_actor_ids: tuple[NonBlankStr, ...] = Field(min_length=1)
    reference_stability_report_checksum: KnowledgeValue[Sha256]
    partial_claim_equivalences: KnowledgeValue[tuple[PartialClaimEquivalence, ...]]

    @model_validator(mode="after")
    def _content_addressed_reference(self) -> Self:
        if len(set(self.reviewer_actor_ids)) != len(self.reviewer_actor_ids):
            raise ValueError("independent reference contains duplicate reviewers")
        if self.snapshot.report_id != self.report_scope_id:
            raise ValueError("independent reference has the wrong report scope")
        for label, value in (
            ("reference_stability_report_checksum", self.reference_stability_report_checksum),
            ("partial_claim_equivalences", self.partial_claim_equivalences),
        ):
            if value.query_scope_id != self.report_scope_id:
                raise ValueError(f"{label} must retain the exact report scope")
        if self.purpose is IndependentReferencePurpose.CONFORMANCE_ONLY:
            if (
                self.reference_stability_report_checksum.knowledge_state
                is not KnowledgeState.NOT_APPLICABLE
            ):
                raise ValueError("conformance reference cannot assert reference stability")
            if self.partial_claim_equivalences.knowledge_state is not KnowledgeState.NOT_APPLICABLE:
                raise ValueError("conformance reference uses exact matching, not partial policy")
        elif self.reference_stability_report_checksum.knowledge_state not in {
            KnowledgeState.PRESENT,
            KnowledgeState.UNKNOWN,
        }:
            raise ValueError("independent reference must address reference-stability evidence")
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
    query_count: int = Field(ge=1)
    missing_query_count: int = Field(ge=0)
    unexpected_query_count: int = Field(ge=0)
    global_report_resolution_count: int = Field(ge=1, le=1)
    claim_count: int = Field(ge=1)
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
    adequacy_axis_match: MatchSummary
    evidence_correctness: MatchSummary
    proof_correctness: MatchSummary
    abstention_dispositions: dict[AbstentionDisposition, int]

    @model_validator(mode="after")
    def _complete_abstention_partition(self) -> Self:
        if set(self.abstention_dispositions) != set(AbstentionDisposition):
            raise ValueError("abstention result must retain every disposition")
        if sum(self.abstention_dispositions.values()) != self.claim_match.denominator:
            raise ValueError("abstention counts do not equal the claim denominator")
        return self


class ResidualEvent(KernelModel):
    residual_id: NonBlankStr
    query_id: NonBlankStr
    claim_id: NonBlankStr
    false_certainty_category: KnowledgeValue[FalseCertaintyCategory]
    origin: KnowledgeValue[ResidualOrigin]
    severity: KnowledgeValue[ResidualSeverity]
    impact_on_claim: NonBlankStr


class EndToEndEvaluationReport(KernelModel):
    evaluation_id: NonBlankStr
    observed_snapshot_checksum: Sha256
    reference_checksum: KnowledgeValue[Sha256]
    status: EvaluationStatus
    scientific_use_permitted: bool
    denominators: KnowledgeValue[EvaluationDenominators]
    global_report_resolution_match: KnowledgeValue[bool]
    query_results: KnowledgeValue[tuple[QueryEvaluationResult, ...]]
    residuals: KnowledgeValue[tuple[ResidualEvent, ...]]
    blockers: tuple[ScientificReviewRequirement, ...]

    @model_validator(mode="after")
    def _blocked_states_are_not_numeric_results(self) -> Self:
        if self.status is EvaluationStatus.BLOCKED:
            if self.scientific_use_permitted:
                raise ValueError("blocked evaluation cannot permit scientific use")
            if self.denominators.knowledge_state is KnowledgeState.PRESENT:
                raise ValueError("blocked evaluation cannot fabricate denominators")
            if self.query_results.knowledge_state is KnowledgeState.PRESENT:
                raise ValueError("blocked evaluation cannot fabricate query results")
            if self.global_report_resolution_match.knowledge_state is KnowledgeState.PRESENT:
                raise ValueError("blocked evaluation cannot fabricate report-resolution match")
        if self.status is EvaluationStatus.CONFORMANCE_ONLY and self.scientific_use_permitted:
            raise ValueError("conformance-only evaluation is never scientific evidence")
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


class BlindResidualAuditProtocol(KernelModel):
    protocol_id: NonBlankStr
    sample_manifest_checksum: Sha256
    report_ids: tuple[NonBlankStr, ...] = Field(min_length=1)
    claim_ids: tuple[NonBlankStr, ...] = Field(min_length=1)
    reference_ids: tuple[NonBlankStr, ...] = Field(min_length=1)
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

    @model_validator(mode="after")
    def _blind_and_separated(self) -> Self:
        if not self.blind_to_original_output:
            raise ValueError("residual audit must be blind to the original output")
        if set(self.strata) != set(ResidualAuditStratum):
            raise ValueError("residual audit requires the complete Appendix H.3 strata")
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
    claim_id: NonBlankStr
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
        finding_claim_ids = [finding.claim_id for finding in self.findings]
        if len(set(finding_claim_ids)) != len(finding_claim_ids):
            raise ValueError("residual audit contains duplicate claim findings")
        if set(finding_claim_ids) != set(self.protocol.claim_ids):
            raise ValueError("residual findings do not close the blinded sample")
        if any(finding.report_id not in self.protocol.report_ids for finding in self.findings):
            raise ValueError("residual finding references a report outside the sample")
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
    GOLD_NOISE_BUDGET = "GOLD_NOISE_BUDGET"


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
        expected = content_checksum(self.model_dump(mode="json", exclude={"content_checksum"}))
        if self.content_checksum != expected:
            raise ValueError("reference stability report checksum mismatch")
        return self


__all__ = [
    "CONFORMANCE_REFERENCE_REVIEW_ISSUE_ID",
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
    "EvaluationStatus",
    "FalseCertaintyCategory",
    "IndependentReferencePurpose",
    "IndependentReportReference",
    "MatchOutcome",
    "MatchSummary",
    "PartialClaimEquivalence",
    "QueryEvaluationResult",
    "QueryEvaluationSnapshot",
    "ReferenceStabilityComponent",
    "ReferenceStabilityComponentRecord",
    "ReferenceStabilityConclusion",
    "ReferenceStabilityPolicyPin",
    "ReferenceStabilityReport",
    "ReportEvaluationSnapshot",
    "ResidualAuditFinding",
    "ResidualAuditStratum",
    "ResidualEvent",
    "ResidualOrigin",
    "ResidualSeverity",
    "StabilityComponentObservation",
]
