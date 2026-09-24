"""Structured PRD v8 profile and scenario coverage contracts.

PRD v9 update (ScenarioCompleteness): ``EXHAUSTIVE_WITHIN_PROFILE`` is retired
as a writable state. The v9 triad is ``COMPLETE_UNDER_DECLARED_ASSUMPTION_SET``
(fail-closed: requires a versioned, finalized assumption set plus a
counterexample-search outcome that found none), ``INCOMPLETE_KNOWN`` and
``UNKNOWN_COMPLETENESS``. Read compatibility is preserved by an adapter that
maps the legacy token to ``COMPLETE_UNDER_DECLARED_ASSUMPTION_SET`` only when a
complete assumption-set declaration is present, otherwise to
``INCOMPLETE_KNOWN``; v9 writers can never emit the legacy value because it is
no longer part of the writable vocabulary.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from ntruth.schemas.claims import ProfileCoverageReference
from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.support import ScientificReviewRequirement

PROFILE_COVERAGE_REVIEW_ISSUE_ID = "SRR-V8-008"

LEGACY_EXHAUSTIVE_WITHIN_PROFILE_STATUS = "EXHAUSTIVE_WITHIN_PROFILE"


class ScenarioCoverageStatus(StrEnum):
    """Writable PRD v8/v9 scenario-completeness states."""

    NON_EXHAUSTIVE = "NON_EXHAUSTIVE"
    UNKNOWN = "UNKNOWN"
    COMPLETE_UNDER_DECLARED_ASSUMPTION_SET = "COMPLETE_UNDER_DECLARED_ASSUMPTION_SET"
    INCOMPLETE_KNOWN = "INCOMPLETE_KNOWN"
    UNKNOWN_COMPLETENESS = "UNKNOWN_COMPLETENESS"


class CounterexampleSearchStatus(StrEnum):
    NOT_PERFORMED = "NOT_PERFORMED"
    BOUNDED_SEARCH_COMPLETED_NO_COUNTEREXAMPLE = "BOUNDED_SEARCH_COMPLETED_NO_COUNTEREXAMPLE"
    COUNTEREXAMPLE_FOUND = "COUNTEREXAMPLE_FOUND"


class ScenarioCoverage(KernelModel):
    status: ScenarioCoverageStatus
    profile_id: NonBlankStr
    theory_version: NonBlankStr
    emitting_clause_ids: tuple[NonBlankStr, ...] = Field(min_length=1)
    omitted_dimensions: KnowledgeValue[tuple[NonBlankStr, ...]]
    caveat: KnowledgeValue[NonBlankStr]
    assumption_set_id: NonBlankStr | None = None
    assumption_set_version: NonBlankStr | None = None
    assumption_set_finalized: bool | None = None
    counterexample_search_status: CounterexampleSearchStatus | None = None

    @model_validator(mode="before")
    @classmethod
    def _adapt_legacy_exhaustive_status(cls, data: object) -> object:
        """Read-only legacy adapter; v9 writers cannot emit the legacy token."""

        if not isinstance(data, dict):
            return data
        if data.get("status") != LEGACY_EXHAUSTIVE_WITHIN_PROFILE_STATUS:
            return data
        declared_assumption_set = (
            isinstance(data.get("assumption_set_id"), str)
            and bool(str(data.get("assumption_set_id")).strip())
            and isinstance(data.get("assumption_set_version"), str)
            and bool(str(data.get("assumption_set_version")).strip())
            and data.get("assumption_set_finalized") is True
        )
        adapted = {
            **data,
            "status": (
                ScenarioCoverageStatus.COMPLETE_UNDER_DECLARED_ASSUMPTION_SET
                if declared_assumption_set
                else ScenarioCoverageStatus.INCOMPLETE_KNOWN
            ),
        }
        return adapted

    @model_validator(mode="after")
    def _status_specific_open_world_contract(self) -> Self:
        if len(set(self.emitting_clause_ids)) != len(self.emitting_clause_ids):
            raise ValueError("emitting_clause_ids contains duplicates")
        omitted_state = self.omitted_dimensions.knowledge_state
        caveat_state = self.caveat.knowledge_state
        completeness_machinery = any(
            value is not None
            for value in (
                self.assumption_set_id,
                self.assumption_set_version,
                self.assumption_set_finalized,
                self.counterexample_search_status,
            )
        )
        if self.status is ScenarioCoverageStatus.COMPLETE_UNDER_DECLARED_ASSUMPTION_SET:
            if (
                self.assumption_set_id is None
                or self.assumption_set_version is None
                or self.assumption_set_finalized is not True
            ):
                raise ValueError(
                    "COMPLETE_UNDER_DECLARED_ASSUMPTION_SET requires a versioned, "
                    "finalized assumption_set_id"
                )
            if self.counterexample_search_status is None:
                raise ValueError(
                    "COMPLETE_UNDER_DECLARED_ASSUMPTION_SET requires counterexample_search_status"
                )
            if self.counterexample_search_status is (
                CounterexampleSearchStatus.COUNTEREXAMPLE_FOUND
            ):
                raise ValueError(
                    "a recorded counterexample forbids COMPLETE_UNDER_DECLARED_ASSUMPTION_SET"
                )
            if omitted_state is not KnowledgeState.ABSENT_EXPLICIT:
                raise ValueError(
                    "COMPLETE_UNDER_DECLARED_ASSUMPTION_SET requires explicit absence "
                    "of omissions within the declared assumption set"
                )
            if caveat_state not in {
                KnowledgeState.ABSENT_EXPLICIT,
                KnowledgeState.NOT_APPLICABLE,
                KnowledgeState.PRESENT,
            }:
                raise ValueError(
                    "COMPLETE_UNDER_DECLARED_ASSUMPTION_SET requires an explicit caveat state"
                )
        elif self.status is ScenarioCoverageStatus.NON_EXHAUSTIVE:
            if completeness_machinery:
                raise ValueError(
                    "assumption-set declarations are reserved for "
                    "COMPLETE_UNDER_DECLARED_ASSUMPTION_SET"
                )
            if omitted_state is not KnowledgeState.PRESENT:
                raise ValueError("NON_EXHAUSTIVE requires named omitted dimensions")
            if caveat_state is not KnowledgeState.PRESENT:
                raise ValueError("NON_EXHAUSTIVE requires a present caveat")
        elif self.status in {
            ScenarioCoverageStatus.UNKNOWN,
            ScenarioCoverageStatus.UNKNOWN_COMPLETENESS,
        }:
            if completeness_machinery:
                raise ValueError(
                    "assumption-set declarations are reserved for "
                    "COMPLETE_UNDER_DECLARED_ASSUMPTION_SET"
                )
            if omitted_state not in {
                KnowledgeState.UNKNOWN,
                KnowledgeState.NOT_REPORTED,
                KnowledgeState.CONFLICTING,
            }:
                raise ValueError("UNKNOWN coverage must retain unresolved omission semantics")
        return self


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
    "LEGACY_EXHAUSTIVE_WITHIN_PROFILE_STATUS",
    "PROFILE_COVERAGE_REVIEW_ISSUE_ID",
    "CounterexampleSearchStatus",
    "ProfileCoverageStatement",
    "ScenarioCoverage",
    "ScenarioCoverageStatus",
]
