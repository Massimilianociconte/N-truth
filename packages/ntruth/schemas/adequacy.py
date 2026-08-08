"""Epistemic design-adequacy evaluations kept orthogonal to determinability."""

from __future__ import annotations

from pydantic import Field, JsonValue, model_validator

from ntruth.schemas.claims import IrrelevantPredicate
from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.support import ScientificReviewRequirement


class DesignAdequacyEvaluation(KernelModel):
    """One explicit axis evaluation; it is never a good/bad-design verdict."""

    evaluation_id: NonBlankStr
    inferential_query_id: NonBlankStr
    axis: NonBlankStr
    outcome: KnowledgeValue[JsonValue]
    rationale: NonBlankStr
    theory_clause_id: NonBlankStr
    rule_id: NonBlankStr
    rule_version: NonBlankStr
    rule_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    dependency_claim_ids: tuple[NonBlankStr, ...] = Field(min_length=1)
    required_predicates: tuple[NonBlankStr, ...] = Field(min_length=1)
    irrelevant_predicates: tuple[IrrelevantPredicate, ...] = Field(min_length=1)
    review_requirement: ScientificReviewRequirement

    @model_validator(mode="after")
    def _pinned_review_boundary(self) -> DesignAdequacyEvaluation:
        if self.outcome.query_scope_id != self.inferential_query_id:
            raise ValueError("adequacy outcome must be explicitly query-scoped")
        if self.review_requirement.issue_id != "SRR-V8-017":
            raise ValueError("interference adequacy remains blocked by SRR-V8-017")
        return self

    @property
    def finding_type(self) -> str | None:
        """Deprecated presentation label; the serialized contract is epistemic."""

        if self.outcome.knowledge_state is not KnowledgeState.PRESENT:
            return None
        return f"INTERFERENCE_{str(self.outcome.value).upper()}"


DesignAdequacyFinding = DesignAdequacyEvaluation


__all__ = ["DesignAdequacyEvaluation", "DesignAdequacyFinding"]
