"""MVT-A stage schema: candidate-only parser outputs (PRD v7 §4.2, §11).

Parser stages may emit evidence/entity/count/factor *candidates*. They must
never emit final independent_n, pseudoreplication verdict, RuleResult, or final
DeterminabilityState.
"""

from __future__ import annotations

from typing import Any, Self

from pydantic import Field, model_validator

from ntruth.schemas.core import FrozenModel

FORBIDDEN_FINAL_FIELDS: frozenset[str] = frozenset(
    {
        "independent_n",
        "pseudoreplication_verdict",
        "rule_result",
        "RuleResult",
        "determinability_state",
        "DeterminabilityState",
        "final_determinability",
        "experimental_unit_count",  # final only; candidate form is allowed
    }
)

ALLOWED_CANDIDATE_COUNT_KINDS: frozenset[str] = frozenset(
    {
        "declared_n",
        "observational_n",
        "n_analyzed",
        "biological_source_count",
        "experimental_unit_count_candidate",
        "excluded_n",
        "planned_n",
        "allocated_n",
        "treated_n",
        "observed_n",
    }
)


class EntityCandidate(FrozenModel):
    """Candidate entity mention from Methods/caption text."""

    text: str
    entity_type: str
    start: int | None = None
    end: int | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence_span_id: str | None = None


class FactorCandidate(FrozenModel):
    factor_id: str
    levels: tuple[str, ...] = ()
    evidence_span_ids: tuple[str, ...] = ()


class CountCandidate(FrozenModel):
    kind: str
    value: int | None = Field(default=None, ge=0)
    raw_text: str = ""
    evidence_span_id: str | None = None

    @model_validator(mode="after")
    def _candidate_only(self) -> Self:
        if self.kind in FORBIDDEN_FINAL_FIELDS or self.kind == "independent_n":
            raise ValueError(f"parser must not emit final count kind {self.kind!r}")
        if self.kind not in ALLOWED_CANDIDATE_COUNT_KINDS and not self.kind.endswith("_candidate"):
            raise ValueError(f"unrecognised candidate count kind: {self.kind!r}")
        return self


class EvidenceCandidate(FrozenModel):
    span_id: str
    text: str
    section: str | None = None
    support_level: str = "INFERRED_CANDIDATE"


class ParserCandidateBundle(FrozenModel):
    """Candidate-only bundle: hard boundary before human review and rules."""

    stage: str = "mvt_a_candidate"
    source_text_checksum: str = ""
    entities: tuple[EntityCandidate, ...] = ()
    factors: tuple[FactorCandidate, ...] = ()
    counts: tuple[CountCandidate, ...] = ()
    evidence: tuple[EvidenceCandidate, ...] = ()
    notes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _no_final_fields_in_dump(self) -> Self:
        payload = self.model_dump(mode="json")
        assert_no_final_scientific_fields(payload)
        return self


class MvtAStageOutput(FrozenModel):
    """Stage envelope: candidates + optional hard-verifier status."""

    stage_id: str
    input_kind: str = "methods_or_caption"
    candidates: ParserCandidateBundle
    verifier_passed: bool | None = None
    verifier_errors: tuple[str, ...] = ()
    model_id: str | None = None  # challenger id only; never "validated"
    model_role: str = "unqualified_challenger"


def assert_no_final_scientific_fields(payload: Any, path: str = "$") -> None:
    """Recursively reject final scientific fields in parser-facing payloads."""
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in FORBIDDEN_FINAL_FIELDS:
                raise ValueError(
                    f"parser/stage payload must not contain final field {key!r} at {path}"
                )
            assert_no_final_scientific_fields(value, f"{path}.{key}")
    elif isinstance(payload, (list, tuple)):
        for i, item in enumerate(payload):
            assert_no_final_scientific_fields(item, f"{path}[{i}]")
