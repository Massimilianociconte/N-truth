"""Design adequacy findings kept orthogonal to claim determinability."""

from pydantic import Field

from ntruth.schemas.kernel import KernelModel, NonBlankStr


class DesignAdequacyFinding(KernelModel):
    finding_id: NonBlankStr
    inferential_query_id: NonBlankStr
    finding_type: NonBlankStr
    rationale: NonBlankStr
    theory_clause_ids: tuple[NonBlankStr, ...] = Field(min_length=1)
    rule_ids: tuple[NonBlankStr, ...] = Field(min_length=1)
    evidence_ids: tuple[NonBlankStr, ...] = Field(min_length=1)


__all__ = ["DesignAdequacyFinding"]
