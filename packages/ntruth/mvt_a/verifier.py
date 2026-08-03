"""Hard verifier hook for MVT-A candidate bundles (PRD v7 §4.2).

Structural checks only: schema shape, forbidden finals, empty candidates.
Does not score scientific correctness.
"""

from __future__ import annotations

from ntruth.mvt_a.stage_schema import (
    FORBIDDEN_FINAL_FIELDS,
    MvtAStageOutput,
    ParserCandidateBundle,
    assert_no_final_scientific_fields,
)
from ntruth.schemas.core import FrozenModel


class HardVerifierResult(FrozenModel):
    passed: bool
    errors: tuple[str, ...] = ()
    checks_run: tuple[str, ...] = ()


def hard_verify_candidates(bundle: ParserCandidateBundle) -> HardVerifierResult:
    errors: list[str] = []
    checks = (
        "forbidden_final_fields",
        "non_empty_or_explicit_empty",
        "count_kinds_candidate_only",
    )
    try:
        assert_no_final_scientific_fields(bundle.model_dump(mode="json"))
    except ValueError as exc:
        errors.append(str(exc))

    # empty bundle is allowed only if notes explain abstention candidate
    if (
        not bundle.entities
        and not bundle.factors
        and not bundle.counts
        and not bundle.evidence
        and not bundle.notes
    ):
        errors.append("empty candidate bundle without notes is invalid")

    for count in bundle.counts:
        if count.kind in FORBIDDEN_FINAL_FIELDS or count.kind == "independent_n":
            errors.append(f"forbidden count kind: {count.kind}")

    return HardVerifierResult(passed=not errors, errors=tuple(errors), checks_run=checks)


def attach_verifier(stage: MvtAStageOutput) -> MvtAStageOutput:
    result = hard_verify_candidates(stage.candidates)
    return MvtAStageOutput(
        stage_id=stage.stage_id,
        input_kind=stage.input_kind,
        candidates=stage.candidates,
        verifier_passed=result.passed,
        verifier_errors=result.errors,
        model_id=stage.model_id,
        model_role=stage.model_role,
    )
