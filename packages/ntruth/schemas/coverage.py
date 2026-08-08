"""Structured PRD v8 profile and scenario coverage contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from ntruth.schemas.claims import ProfileCoverageReference
from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.knowledge import KnowledgeValue
from ntruth.schemas.support import ScientificReviewRequirement

PROFILE_COVERAGE_REVIEW_ISSUE_ID = "SRR-V8-008"


class ScenarioCoverageStatus(StrEnum):
    EXHAUSTIVE_WITHIN_PROFILE = "EXHAUSTIVE_WITHIN_PROFILE"
    NON_EXHAUSTIVE = "NON_EXHAUSTIVE"
    UNKNOWN = "UNKNOWN"


class ScenarioCoverage(KernelModel):
    status: ScenarioCoverageStatus
    profile_id: NonBlankStr
    theory_version: NonBlankStr
    emitting_clause_ids: tuple[NonBlankStr, ...] = Field(min_length=1)
    omitted_dimensions: KnowledgeValue[tuple[NonBlankStr, ...]]
    caveat: KnowledgeValue[NonBlankStr]


class ProfileCoverageStatement(KernelModel):
    """Structured candidate coverage that retains the open SRR-V8-008 blocker."""

    statement_id: NonBlankStr
    profile_id: NonBlankStr
    profile_version: NonBlankStr
    theory_version: NonBlankStr
    predicate_closure_argument_id: NonBlankStr
    covered_predicate_ids: tuple[NonBlankStr, ...] = Field(min_length=1)
    known_gap_ids: tuple[NonBlankStr, ...] = Field(min_length=1)
    contract_review: ScientificReviewRequirement

    @model_validator(mode="after")
    def _fail_closed_profile_contract(self) -> Self:
        if self.contract_review.issue_id != PROFILE_COVERAGE_REVIEW_ISSUE_ID:
            raise ValueError("ProfileCoverageStatement must retain blocker SRR-V8-008")
        if PROFILE_COVERAGE_REVIEW_ISSUE_ID not in self.known_gap_ids:
            raise ValueError("known_gap_ids must include SRR-V8-008")
        if len(set(self.covered_predicate_ids)) != len(self.covered_predicate_ids):
            raise ValueError("covered_predicate_ids contains duplicates")
        if len(set(self.known_gap_ids)) != len(self.known_gap_ids):
            raise ValueError("known_gap_ids contains duplicates")
        return self

    def claim_reference(self) -> ProfileCoverageReference:
        return ProfileCoverageReference(
            statement_id=self.statement_id,
            profile_id=self.profile_id,
            profile_version=self.profile_version,
            predicate_closure_argument_id=self.predicate_closure_argument_id,
            contract_review=self.contract_review,
        )


__all__ = [
    "PROFILE_COVERAGE_REVIEW_ISSUE_ID",
    "ProfileCoverageStatement",
    "ScenarioCoverage",
    "ScenarioCoverageStatus",
]
