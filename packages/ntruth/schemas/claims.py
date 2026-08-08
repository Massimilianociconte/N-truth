"""Claim-specific deterministic output foundations for PRD v8."""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import Field, JsonValue, model_validator

from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.knowledge import KnowledgeValue
from ntruth.schemas.support import SupportGrade


class DeterminabilityState(StrEnum):
    DETERMINATE = "DETERMINATE"
    CONDITIONALLY_DETERMINATE = "CONDITIONALLY_DETERMINATE"
    MULTIPLE_PLAUSIBLE_GRAPHS = "MULTIPLE_PLAUSIBLE_GRAPHS"
    INSUFFICIENT_INFORMATION = "INSUFFICIENT_INFORMATION"
    CONFLICTING_INFORMATION = "CONFLICTING_INFORMATION"
    INVALID_GRAPH = "INVALID_GRAPH"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class IrrelevantPredicate(KernelModel):
    id: NonBlankStr
    rationale: NonBlankStr


class DerivedClaim(KernelModel):
    """One query-scoped scientific consequence with explicit epistemic state."""

    claim_id: NonBlankStr
    claim_type: NonBlankStr
    inferential_query_id: NonBlankStr
    value: KnowledgeValue[JsonValue]
    determinability_state: DeterminabilityState
    support_grade: SupportGrade
    required_predicates: tuple[NonBlankStr, ...] = Field(min_length=1)
    irrelevant_predicates: tuple[IrrelevantPredicate, ...]
    assumptions: tuple[NonBlankStr, ...] = ()
    sensitivity_records: tuple[NonBlankStr, ...] = ()
    theory_version: NonBlankStr
    theory_clauses: tuple[NonBlankStr, ...] = Field(min_length=1)
    ruleset_version: NonBlankStr
    rule_trace: tuple[NonBlankStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _predicate_and_trace_integrity(self) -> DerivedClaim:
        required = set(self.required_predicates)
        irrelevant = {item.id for item in self.irrelevant_predicates}
        if len(required) != len(self.required_predicates):
            raise ValueError("required_predicates contains duplicates")
        if len(irrelevant) != len(self.irrelevant_predicates):
            raise ValueError("irrelevant_predicates contains duplicates")
        overlap = required & irrelevant
        if overlap:
            raise ValueError(
                f"predicates cannot be both required and irrelevant: {sorted(overlap)}"
            )
        if len(set(self.theory_clauses)) != len(self.theory_clauses):
            raise ValueError("theory_clauses contains duplicates")
        if len(set(self.rule_trace)) != len(self.rule_trace):
            raise ValueError("rule_trace contains duplicates")
        return self


class DerivedClaimSet(KernelModel):
    claim_set_id: NonBlankStr
    inferential_query_id: NonBlankStr
    claims: tuple[DerivedClaim, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _one_query_and_unique_claims(self) -> Self:
        if any(claim.inferential_query_id != self.inferential_query_id for claim in self.claims):
            raise ValueError("all claims must share the set inferential_query_id")
        claim_ids = [claim.claim_id for claim in self.claims]
        if len(set(claim_ids)) != len(claim_ids):
            raise ValueError("DerivedClaimSet contains duplicate claim_id values")
        return self


__all__ = [
    "DerivedClaim",
    "DerivedClaimSet",
    "DeterminabilityState",
    "IrrelevantPredicate",
]
