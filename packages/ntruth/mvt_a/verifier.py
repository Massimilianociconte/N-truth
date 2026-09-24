"""Hard verifier hook for MVT-A candidate bundles (PRD v8 §13.6).

Structural checks only: schema shape, forbidden finals, empty candidates.
Does not score scientific correctness.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ntruth.mvt_a.stage_schema import (
    FORBIDDEN_FINAL_FIELDS,
    MvtAStageOutput,
    MvtAStageOutputV7,
    ParserCandidateBundle,
    StageCompletionStatus,
    StageCoverage,
    StageErrorCode,
    StageIssue,
    assert_no_final_scientific_fields,
)
from ntruth.schemas.block_boundary import verify_candidate_experiment_block_boundaries
from ntruth.schemas.core import FrozenModel

if TYPE_CHECKING:
    from ntruth.parser_ai.contract import ParserCandidateOutput


class HardVerifierResult(FrozenModel):
    passed: bool
    errors: tuple[StageIssue, ...] = ()
    checks_run: tuple[str, ...] = ()


def _stable_error_detail(exc: Exception, *, fallback: str) -> str:
    try:
        detail = str(exc)
    except Exception:
        return fallback
    if type(detail) is not str:
        return fallback
    return detail if str.strip(detail) else fallback


def hard_verify_candidates(
    bundle: ParserCandidateOutput | None,
) -> HardVerifierResult:
    from ntruth.parser_ai.contract import ParserCandidateOutput

    if bundle is not None and not isinstance(bundle, ParserCandidateOutput):
        raise TypeError(
            "hard_verify_candidates is the v8 ParserCandidateOutput verifier; "
            "use hard_verify_candidates_v7 for ParserCandidateBundle"
        )
    errors: list[StageIssue] = []
    checks = (
        "forbidden_final_fields",
        "non_empty_or_explicit_empty",
        "count_kinds_candidate_only",
        "experiment_block_boundaries",
    )
    try:
        if bundle is None:
            raise ValueError("canonical parser candidate payload is absent")
        bundle = ParserCandidateOutput.assert_raw_candidate_only(bundle)
        assert_no_final_scientific_fields(bundle.model_dump(mode="json", warnings="none"))
    except Exception as exc:
        error = StageIssue(
            code=StageErrorCode.VERIFIER_DISAGREEMENT,
            detail=_stable_error_detail(
                exc,
                fallback="candidate parser payload failed canonical validation",
            ),
        )
        return HardVerifierResult(
            passed=False,
            errors=(error,),
            checks_run=("forbidden_final_fields",),
        )

    # empty bundle is allowed only if notes explain abstention candidate
    if bundle is not None and (
        not bundle.experiment_blocks
        and not bundle.evidence_spans
        and not bundle.candidate_nodes
        and not bundle.candidate_edges
        and not bundle.factors
        and not bundle.endpoints
        and not bundle.contrasts
        and not bundle.candidate_estimands
        and not bundle.candidate_counts
        and not bundle.candidate_events
        and not bundle.candidate_graphs
        and not bundle.alternatives
        and not bundle.clarification_questions
        and not bundle.missing_predicates
    ):
        errors.append(
            StageIssue(
                code=StageErrorCode.MISSING_REQUIRED_EVIDENCE,
                detail="empty candidate bundle without an explicit abstention artifact",
            )
        )

    for count in bundle.candidate_counts if bundle is not None else ():
        if count.kind in FORBIDDEN_FINAL_FIELDS or count.kind == "independent_n":
            errors.append(
                StageIssue(
                    code=StageErrorCode.INVALID_COUNT_INVARIANT,
                    detail=f"forbidden final count kind: {count.kind}",
                )
            )

    if bundle is not None:
        try:
            verify_candidate_experiment_block_boundaries(bundle)
        except Exception as exc:
            errors.append(
                StageIssue(
                    code=StageErrorCode.VERIFIER_DISAGREEMENT,
                    detail=_stable_error_detail(
                        exc,
                        fallback="candidate experiment-block boundary validation failed",
                    ),
                )
            )
            return HardVerifierResult(
                passed=False,
                errors=tuple(errors),
                checks_run=checks,
            )

    return HardVerifierResult(passed=not errors, errors=tuple(errors), checks_run=checks)


def attach_verifier(stage: MvtAStageOutput) -> MvtAStageOutput:
    result = hard_verify_candidates(stage.candidates)
    payload = stage.model_dump(mode="json")
    payload.update(
        {
            "verifier_passed": result.passed,
            "verifier_errors": [error.model_dump(mode="json") for error in result.errors],
        }
    )
    if not result.passed:
        preserved = set(stage.preserved_artifact_ids)
        preserved.update(stage.coverage.covered_artifact_ids)
        payload.update(
            {
                "status": StageCompletionStatus.FAILED,
                "coverage": StageCoverage(
                    status=StageCompletionStatus.FAILED,
                    missing_artifact_ids=stage.provenance.input_artifact_ids,
                    rationale="Hard verifier failed; candidate artifacts were preserved.",
                ).model_dump(mode="json"),
                "errors": [error.model_dump(mode="json") for error in result.errors],
                "preserved_artifact_ids": sorted(preserved),
            }
        )
    return MvtAStageOutput.model_validate(payload)


def attach_verifier_v7(stage: MvtAStageOutputV7) -> MvtAStageOutputV7:
    """Explicit deprecated adapter preserving the v7 bool/string envelope."""

    result = hard_verify_candidates_v7(stage.candidates)
    return stage.model_copy(
        update={
            "verifier_passed": result.passed,
            "verifier_errors": tuple(error.detail for error in result.errors),
        }
    )


def hard_verify_candidates_v7(bundle: ParserCandidateBundle) -> HardVerifierResult:
    """Deprecated structural verifier for the explicitly named v7 envelope."""

    errors: list[StageIssue] = []
    try:
        assert_no_final_scientific_fields(bundle.model_dump(mode="json"))
    except ValueError as exc:
        errors.append(
            StageIssue(
                code=StageErrorCode.VERIFIER_DISAGREEMENT,
                detail=_stable_error_detail(
                    exc,
                    fallback="legacy candidate payload failed structural validation",
                ),
            )
        )
    if not any(
        (
            bundle.entities,
            bundle.factors,
            bundle.counts,
            bundle.evidence,
            bundle.relations,
            bundle.events,
            bundle.graphs,
            bundle.alternatives,
            bundle.missing_predicates,
            bundle.notes,
        )
    ):
        errors.append(
            StageIssue(
                code=StageErrorCode.MISSING_REQUIRED_EVIDENCE,
                detail="empty legacy candidate bundle without abstention",
            )
        )
    return HardVerifierResult(
        passed=not errors,
        errors=tuple(errors),
        checks_run=("forbidden_final_fields", "non_empty_or_explicit_empty"),
    )
