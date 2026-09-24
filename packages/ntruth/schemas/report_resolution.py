"""Versioned and fail-closed PRD v8 report-resolution policy contract."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol, Self

from pydantic import model_validator

from ntruth.schemas.claims import DerivedClaimSet, DeterminabilityState
from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.support import ScientificReviewRequirement

REPORT_AGGREGATION_REVIEW_ISSUE_ID = "SRR-V8-014"
TRIVIAL_REPORT_POLICY_VERSION = "ntruth-report-resolution-trivial-v8-0.1.0"


class ReportResolutionState(StrEnum):
    COMPLETE_FOR_REQUESTED_CLAIMS = "COMPLETE_FOR_REQUESTED_CLAIMS"
    PARTIAL_WITH_ACTIONABLE_GAPS = "PARTIAL_WITH_ACTIONABLE_GAPS"
    MULTI_SCENARIO = "MULTI_SCENARIO"
    CONFLICTED = "CONFLICTED"
    INVALID = "INVALID"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class ReportResolutionOutcome(KernelModel):
    policy_version: NonBlankStr
    resolution: KnowledgeValue[ReportResolutionState]
    review_requirement: ScientificReviewRequirement | None = None

    @property
    def state(self) -> ReportResolutionState | None:
        if self.resolution.knowledge_state is KnowledgeState.PRESENT:
            return self.resolution.value
        return None

    @model_validator(mode="after")
    def _resolution_xor_review(self) -> Self:
        if self.resolution.knowledge_state is KnowledgeState.PRESENT:
            if self.review_requirement is not None:
                raise ValueError("resolved report state cannot carry a review blocker")
        elif (
            self.review_requirement is None
            or self.review_requirement.issue_id != REPORT_AGGREGATION_REVIEW_ISSUE_ID
        ):
            raise ValueError("unresolved report aggregation requires blocker SRR-V8-014")
        return self


class ReportResolutionPolicy(Protocol):
    policy_version: str

    def resolve(self, claim_set: DerivedClaimSet) -> ReportResolutionOutcome: ...


class TrivialExplicitReportResolutionPolicy:
    """Resolve only homogeneous states; heterogeneous precedence remains unreviewed."""

    policy_version = TRIVIAL_REPORT_POLICY_VERSION

    def resolve(self, claim_set: DerivedClaimSet) -> ReportResolutionOutcome:
        states = {claim.determinability_state for claim in claim_set.claims}
        mapping = {
            DeterminabilityState.DETERMINATE: ReportResolutionState.COMPLETE_FOR_REQUESTED_CLAIMS,
            DeterminabilityState.CONDITIONALLY_DETERMINATE: (
                ReportResolutionState.PARTIAL_WITH_ACTIONABLE_GAPS
            ),
            DeterminabilityState.INSUFFICIENT_INFORMATION: (
                ReportResolutionState.PARTIAL_WITH_ACTIONABLE_GAPS
            ),
            DeterminabilityState.MULTIPLE_PLAUSIBLE_GRAPHS: ReportResolutionState.MULTI_SCENARIO,
            DeterminabilityState.CONFLICTING_INFORMATION: ReportResolutionState.CONFLICTED,
            DeterminabilityState.INVALID_GRAPH: ReportResolutionState.INVALID,
            DeterminabilityState.OUT_OF_SCOPE: ReportResolutionState.OUT_OF_SCOPE,
        }
        if len(states) == 1:
            state = mapping[next(iter(states))]
            return ReportResolutionOutcome(
                policy_version=self.policy_version,
                resolution=KnowledgeValue[ReportResolutionState](
                    knowledge_state=KnowledgeState.PRESENT,
                    value=state,
                    evidence_ids=tuple(claim.claim_id for claim in claim_set.claims),
                    query_scope_id=claim_set.inferential_query_id,
                ),
            )
        return ReportResolutionOutcome(
            policy_version=self.policy_version,
            resolution=KnowledgeValue[ReportResolutionState](
                knowledge_state=KnowledgeState.UNKNOWN,
                rationale="Mixed claim states require a reviewed aggregation policy.",
                query_scope_id=claim_set.inferential_query_id,
            ),
            review_requirement=ScientificReviewRequirement(
                issue_id=REPORT_AGGREGATION_REVIEW_ISSUE_ID,
                rationale="No precedence across heterogeneous claim states is specified.",
            ),
        )


__all__ = [
    "REPORT_AGGREGATION_REVIEW_ISSUE_ID",
    "TRIVIAL_REPORT_POLICY_VERSION",
    "ReportResolutionOutcome",
    "ReportResolutionPolicy",
    "ReportResolutionState",
    "TrivialExplicitReportResolutionPolicy",
]
