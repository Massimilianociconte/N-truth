"""Strict PRD v8 contracts separating Derivation Theory from its Rulebook."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, JsonValue, model_validator

from ntruth.schemas.claims import DeterminabilityState, IrrelevantPredicate
from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.knowledge import KnowledgeValue
from ntruth.schemas.support import ScientificReviewRequirement

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class ClauseLetter(StrEnum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"
    F = "F"
    G = "G"


class RuleExecutionStatus(StrEnum):
    EXECUTABLE = "EXECUTABLE"
    SCIENTIFIC_REVIEW_REQUIRED = "SCIENTIFIC_REVIEW_REQUIRED"


class FixtureKind(StrEnum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    MINIMAL_COUNTERFACTUAL = "MINIMAL_COUNTERFACTUAL"


class FixtureOutcome(StrEnum):
    DERIVED = "DERIVED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    SCIENTIFIC_REVIEW_REQUIRED = "SCIENTIFIC_REVIEW_REQUIRED"


class ReferenceRole(StrEnum):
    THEORY_REFERENCE_SET = "THEORY_REFERENCE_SET"
    IMPLEMENTATION_CONFORMANCE_FIXTURES = "IMPLEMENTATION_CONFORMANCE_FIXTURES"
    DERIVATION_GOLD = "DERIVATION_GOLD"


class ReferenceAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    SCIENTIFIC_REVIEW_REQUIRED = "SCIENTIFIC_REVIEW_REQUIRED"


class PredicateRequirement(KernelModel):
    predicate_id: NonBlankStr
    rationale: NonBlankStr


class TheoryClause(KernelModel):
    """Normative scientific statement; executable rules may only reference it."""

    clause_id: NonBlankStr
    letter: ClauseLetter
    clause_version: NonBlankStr
    title: NonBlankStr
    normative_statement: NonBlankStr
    required_predicates: tuple[PredicateRequirement, ...] = Field(min_length=1)
    output_claim_types: tuple[NonBlankStr, ...] = Field(min_length=1)
    forbidden_inferences: tuple[NonBlankStr, ...] = Field(min_length=1)
    review_requirements: tuple[ScientificReviewRequirement, ...] = ()

    @model_validator(mode="after")
    def _unique_contract_items(self) -> Self:
        predicate_ids = [item.predicate_id for item in self.required_predicates]
        if len(set(predicate_ids)) != len(predicate_ids):
            raise ValueError("theory clause contains duplicate required predicate IDs")
        if len(set(self.output_claim_types)) != len(self.output_claim_types):
            raise ValueError("theory clause contains duplicate output claim types")
        return self


class DerivationTheory(KernelModel):
    theory_id: NonBlankStr
    theory_version: NonBlankStr
    profile_id: NonBlankStr
    profile_version: NonBlankStr
    reference_registry_version: NonBlankStr
    clauses: tuple[TheoryClause, ...] = Field(min_length=7, max_length=7)
    declared_checksum: Sha256

    @model_validator(mode="after")
    def _exact_minimum_clause_set(self) -> Self:
        letters = [clause.letter for clause in self.clauses]
        if set(letters) != set(ClauseLetter) or len(set(letters)) != len(letters):
            raise ValueError("Derivation Theory v0.x must contain exactly clauses A-G")
        clause_ids = [clause.clause_id for clause in self.clauses]
        if len(set(clause_ids)) != len(clause_ids):
            raise ValueError("Derivation Theory contains duplicate clause IDs")
        return self


class ExpectedProofTraceStep(KernelModel):
    step_id: NonBlankStr
    theory_clause_id: NonBlankStr
    rule_id: NonBlankStr
    predicate_ids: tuple[NonBlankStr, ...] = Field(min_length=1)


class ExpectedDerivedClaim(KernelModel):
    """Fixture expectation, not scientific gold and not a runtime DerivedClaim."""

    claim_type: NonBlankStr
    determinability_state: DeterminabilityState
    value: KnowledgeValue[JsonValue]
    proof_trace: tuple[ExpectedProofTraceStep, ...] = Field(min_length=1)


class ConformanceFixture(KernelModel):
    fixture_id: NonBlankStr
    fixture_version: NonBlankStr
    role: Literal[ReferenceRole.IMPLEMENTATION_CONFORMANCE_FIXTURES] = (
        ReferenceRole.IMPLEMENTATION_CONFORMANCE_FIXTURES
    )
    kind: FixtureKind
    decisive_predicate_id: NonBlankStr
    predicate_values: dict[NonBlankStr, KnowledgeValue[JsonValue]] = Field(min_length=1)
    expected_outcome: FixtureOutcome
    expected_claims: tuple[ExpectedDerivedClaim, ...] = ()
    rationale: NonBlankStr

    @model_validator(mode="after")
    def _expected_output_shape(self) -> Self:
        if self.decisive_predicate_id not in self.predicate_values:
            raise ValueError("fixture must include its decisive predicate")
        if self.expected_outcome is FixtureOutcome.DERIVED and not self.expected_claims:
            raise ValueError("DERIVED fixture requires expected claims")
        if self.expected_outcome is FixtureOutcome.NOT_APPLICABLE and self.expected_claims:
            raise ValueError("NOT_APPLICABLE fixture cannot carry expected claims")
        return self


class KnownGapHandling(KernelModel):
    issue_id: NonBlankStr
    affected_predicates: tuple[NonBlankStr, ...] = Field(min_length=1)
    behavior: Literal["BLOCK_AND_EMIT_SCIENTIFIC_REVIEW_REQUIRED"] = (
        "BLOCK_AND_EMIT_SCIENTIFIC_REVIEW_REQUIRED"
    )
    rationale: NonBlankStr
    required_reviewer_role: NonBlankStr


class V8ConformanceRule(KernelModel):
    """Executable mapping that declares conformance; it never defines theory text."""

    rule_id: NonBlankStr
    rule_version: NonBlankStr
    theory_clause_id: NonBlankStr
    theory_clause_version: NonBlankStr
    profile_id: NonBlankStr
    profile_version: NonBlankStr
    execution_status: RuleExecutionStatus
    required_predicates: tuple[PredicateRequirement, ...] = Field(min_length=1)
    irrelevant_predicates: tuple[IrrelevantPredicate, ...] = Field(min_length=1)
    output_claim_types: tuple[NonBlankStr, ...] = Field(min_length=1)
    fixtures: tuple[ConformanceFixture, ...] = Field(min_length=3)
    known_gap_issue_ids: tuple[NonBlankStr, ...] = ()
    known_gap_handling: tuple[KnownGapHandling, ...] = ()
    required_reviewer_role: NonBlankStr
    release_review_requirement: ScientificReviewRequirement
    changelog_entry: NonBlankStr

    @model_validator(mode="after")
    def _unique_rule_contract_items(self) -> Self:
        predicate_ids = [item.predicate_id for item in self.required_predicates]
        if len(set(predicate_ids)) != len(predicate_ids):
            raise ValueError("rule contains duplicate required predicate IDs")
        irrelevant_ids = [item.id for item in self.irrelevant_predicates]
        if len(set(irrelevant_ids)) != len(irrelevant_ids):
            raise ValueError("rule contains duplicate irrelevant predicate IDs")
        fixture_ids = [item.fixture_id for item in self.fixtures]
        if len(set(fixture_ids)) != len(fixture_ids):
            raise ValueError("rule contains duplicate fixture IDs")
        if len(set(self.output_claim_types)) != len(self.output_claim_types):
            raise ValueError("rule contains duplicate output claim types")
        return self


class V8Rulebook(KernelModel):
    rulebook_id: NonBlankStr
    rulebook_version: NonBlankStr
    theory_id: NonBlankStr
    theory_version: NonBlankStr
    theory_checksum: Sha256
    profile_id: NonBlankStr
    profile_version: NonBlankStr
    reference_registry_id: NonBlankStr
    reference_registry_version: NonBlankStr
    reference_registry_checksum: Sha256
    fixture_set_checksum: Sha256
    rules: tuple[V8ConformanceRule, ...] = Field(min_length=7)
    scientific_review_requirements: tuple[ScientificReviewRequirement, ...] = Field(min_length=1)
    declared_checksum: Sha256

    @model_validator(mode="after")
    def _unique_rules(self) -> Self:
        rule_ids = [rule.rule_id for rule in self.rules]
        if len(set(rule_ids)) != len(rule_ids):
            raise ValueError("Rulebook contains duplicate rule IDs")
        return self


class ReferenceAsset(KernelModel):
    asset_id: NonBlankStr
    asset_version: NonBlankStr
    content_checksum: Sha256
    purpose: NonBlankStr


class ReferenceRoleSlot(KernelModel):
    role: ReferenceRole
    purpose: NonBlankStr
    availability: ReferenceAvailability
    assets: tuple[ReferenceAsset, ...] = ()
    review_requirement: ScientificReviewRequirement | None = None

    @model_validator(mode="after")
    def _availability_contract(self) -> Self:
        if self.availability is ReferenceAvailability.AVAILABLE:
            if not self.assets or self.review_requirement is not None:
                raise ValueError("AVAILABLE reference role requires assets and no blocker")
        elif self.assets or self.review_requirement is None:
            raise ValueError("blocked reference role requires review and cannot expose assets")
        return self


class ReferenceRoleRegistry(KernelModel):
    registry_id: NonBlankStr
    registry_version: NonBlankStr
    slots: tuple[ReferenceRoleSlot, ...] = Field(min_length=3, max_length=3)
    declared_checksum: Sha256

    @model_validator(mode="after")
    def _exact_roles(self) -> Self:
        roles = [slot.role for slot in self.slots]
        if set(roles) != set(ReferenceRole) or len(set(roles)) != len(roles):
            raise ValueError("reference registry requires exactly the three normative roles")
        return self


class ConformanceBundle(KernelModel):
    theory: DerivationTheory
    rulebook: V8Rulebook
    reference_registry: ReferenceRoleRegistry


__all__ = [
    "ClauseLetter",
    "ConformanceBundle",
    "ConformanceFixture",
    "DerivationTheory",
    "ExpectedDerivedClaim",
    "ExpectedProofTraceStep",
    "FixtureKind",
    "FixtureOutcome",
    "KnownGapHandling",
    "PredicateRequirement",
    "ReferenceAsset",
    "ReferenceAvailability",
    "ReferenceRole",
    "ReferenceRoleRegistry",
    "ReferenceRoleSlot",
    "RuleExecutionStatus",
    "Sha256",
    "TheoryClause",
    "V8ConformanceRule",
    "V8Rulebook",
]
