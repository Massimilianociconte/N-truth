from __future__ import annotations

from typing import NoReturn

import pytest

from ntruth.mvt_a.stage_schema import StageErrorCode
from ntruth.mvt_a.verifier import hard_verify_candidates
from ntruth.parser_ai.contract import ParserCandidateOutput


class _UnstringifiableValueError(ValueError):
    def __str__(self) -> str:
        raise RuntimeError("exception stringification is unavailable")


@pytest.mark.parametrize(
    "canonicalization_error_type",
    (ValueError, _UnstringifiableValueError),
    ids=("empty-message", "unsafe-stringification"),
)
def test_hard_verifier_fail_closes_when_canonicalization_error_has_no_safe_detail(
    monkeypatch: pytest.MonkeyPatch,
    canonicalization_error_type: type[ValueError],
) -> None:
    """Catches diagnostic formatting re-raising instead of denying the candidate."""

    canonicalization_error = canonicalization_error_type()

    def reject_without_safe_detail(_candidate: ParserCandidateOutput) -> NoReturn:
        raise canonicalization_error

    monkeypatch.setattr(
        ParserCandidateOutput,
        "assert_raw_candidate_only",
        reject_without_safe_detail,
    )
    empty_candidate = ParserCandidateOutput.model_construct()

    result = hard_verify_candidates(empty_candidate)

    assert result.passed is False
    assert len(result.errors) == 1
    assert result.errors[0].code is StageErrorCode.VERIFIER_DISAGREEMENT
    assert result.errors[0].detail == "candidate parser payload failed canonical validation"
    assert result.errors[0].detail.strip()
