"""Claim-specific deterministic output foundations for PRD v8."""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import Field, JsonValue, model_validator

from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.support import ScientificReviewStatus, SupportGrade


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


class ScientificReviewRequirement(KernelModel):
    status: ScientificReviewStatus = ScientificReviewStatus.SCIENTIFIC_REVIEW_REQUIRED
    issue_id: NonBlankStr
    rationale: NonBlankStr


class ProfileCoverageReference(KernelModel):
    """Pinned reference only; Task 4 must close the inconsistent statement shape."""

    statement_id: NonBlankStr
    profile_id: NonBlankStr
    profile_version: NonBlankStr
    predicate_closure_argument_id: NonBlankStr
    contract_review: ScientificReviewRequirement

    @model_validator(mode="after")
    def _known_profile_contract_gap(self) -> ProfileCoverageReference:
        if self.contract_review.issue_id != "SRR-V8-008":
            raise ValueError("ProfileCoverageReference must retain blocker SRR-V8-008")
        return self


class PredicateProofReference(KernelModel):
    predicate_id: NonBlankStr
    predicate_value: KnowledgeValue[JsonValue]


class ProofTraceStep(KernelModel):
    step_id: NonBlankStr
    predicate_references: tuple[PredicateProofReference, ...] = Field(min_length=1)
    theory_clause_id: NonBlankStr
    rule_id: NonBlankStr

    @model_validator(mode="after")
    def _unique_predicate_references(self) -> ProofTraceStep:
        predicate_ids = [reference.predicate_id for reference in self.predicate_references]
        if len(set(predicate_ids)) != len(predicate_ids):
            raise ValueError("proof step contains duplicate predicate references")
        return self


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
    proof_trace: tuple[ProofTraceStep, ...] = Field(min_length=1)
    profile_coverage: ProfileCoverageReference
    state_contract_review: ScientificReviewRequirement | None = None

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
        proof_ids = [step.step_id for step in self.proof_trace]
        if len(set(proof_ids)) != len(proof_ids):
            raise ValueError("proof_trace contains duplicate step_id values")
        traced_predicates = {
            reference.predicate_id
            for step in self.proof_trace
            for reference in step.predicate_references
        }
        missing_proof = required - traced_predicates
        if missing_proof:
            raise ValueError(
                f"proof_trace does not cover required predicates: {sorted(missing_proof)}"
            )
        for step in self.proof_trace:
            if step.theory_clause_id not in self.theory_clauses:
                raise ValueError("proof_trace references an undeclared theory clause")
            if step.rule_id not in self.rule_trace:
                raise ValueError("proof_trace references an undeclared rule")

        state = self.determinability_state
        knowledge_state = self.value.knowledge_state
        determinate_value_states = {
            KnowledgeState.PRESENT,
            KnowledgeState.ABSENT_EXPLICIT,
            KnowledgeState.NOT_APPLICABLE,
        }
        if state is DeterminabilityState.DETERMINATE:
            if knowledge_state not in determinate_value_states:
                raise ValueError("DETERMINATE forbids this scientific value state")
            required_proof_states = {
                reference.predicate_value.knowledge_state
                for step in self.proof_trace
                for reference in step.predicate_references
                if reference.predicate_id in required
            }
            if not required_proof_states.issubset(determinate_value_states):
                raise ValueError("DETERMINATE requires resolved required predicates in proof_trace")
        elif self.state_contract_review is None:
            raise ValueError(
                f"{state.value} requires SCIENTIFIC_REVIEW_REQUIRED until Task 4 closes its "
                "state/output payload contract"
            )

        if (
            state
            in {
                DeterminabilityState.OUT_OF_SCOPE,
                DeterminabilityState.INVALID_GRAPH,
                DeterminabilityState.CONFLICTING_INFORMATION,
            }
            and knowledge_state is KnowledgeState.PRESENT
        ):
            raise ValueError(f"{state.value} forbids this scientific value state")
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
    "PredicateProofReference",
    "ProfileCoverageReference",
    "ProofTraceStep",
    "ScientificReviewRequirement",
]
