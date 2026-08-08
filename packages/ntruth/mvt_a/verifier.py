"""Hard verifier hook for MVT-A candidate bundles (PRD v8 §13.6).

Structural checks only: schema shape, forbidden finals, empty candidates.
Does not score scientific correctness.
"""

from __future__ import annotations

from ntruth.mvt_a.stage_schema import (
    FORBIDDEN_FINAL_FIELDS,
    MvtAStageOutput,
    MvtAStageOutputV7,
    ParserCandidateBundle,
    StageErrorCode,
    StageIssue,
    assert_no_final_scientific_fields,
)
from ntruth.schemas.core import FrozenModel


class HardVerifierResult(FrozenModel):
    passed: bool
    errors: tuple[StageIssue, ...] = ()
    checks_run: tuple[str, ...] = ()


def hard_verify_candidates(bundle: ParserCandidateBundle) -> HardVerifierResult:
    errors: list[StageIssue] = []
    checks = (
        "forbidden_final_fields",
        "non_empty_or_explicit_empty",
        "count_kinds_candidate_only",
    )
    try:
        assert_no_final_scientific_fields(bundle.model_dump(mode="json"))
    except ValueError as exc:
        errors.append(
            StageIssue(
                code=StageErrorCode.VERIFIER_DISAGREEMENT,
                detail=str(exc),
            )
        )

    # empty bundle is allowed only if notes explain abstention candidate
    if (
        not bundle.entities
        and not bundle.factors
        and not bundle.counts
        and not bundle.evidence
        and not bundle.relations
        and not bundle.events
        and not bundle.graphs
        and not bundle.alternatives
        and not bundle.missing_predicates
        and not bundle.notes
    ):
        errors.append(
            StageIssue(
                code=StageErrorCode.MISSING_REQUIRED_EVIDENCE,
                detail="empty candidate bundle without an explicit abstention artifact",
            )
        )

    for count in bundle.counts:
        if count.kind in FORBIDDEN_FINAL_FIELDS or count.kind == "independent_n":
            errors.append(
                StageIssue(
                    code=StageErrorCode.INVALID_COUNT_INVARIANT,
                    detail=f"forbidden final count kind: {count.kind}",
                )
            )

    return HardVerifierResult(passed=not errors, errors=tuple(errors), checks_run=checks)


def attach_verifier(stage: MvtAStageOutput) -> MvtAStageOutput:
    result = hard_verify_candidates(stage.candidates)
    return stage.model_copy(
        update={
            "verifier_passed": result.passed,
            "verifier_errors": result.errors,
        }
    )


def attach_verifier_v7(stage: MvtAStageOutputV7) -> MvtAStageOutputV7:
    """Explicit deprecated adapter preserving the v7 bool/string envelope."""

    result = hard_verify_candidates(stage.candidates)
    return stage.model_copy(
        update={
            "verifier_passed": result.passed,
            "verifier_errors": tuple(error.detail for error in result.errors),
        }
    )
