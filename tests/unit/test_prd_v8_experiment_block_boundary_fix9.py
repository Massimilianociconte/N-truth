"""Exception-total semantic boundary for the MVT-A hard verifier."""

from __future__ import annotations

import importlib
from typing import NoReturn

import pytest

import ntruth.mvt_a.verifier as verifier
from ntruth.mvt_a.stage_schema import (
    MvtAStageOutput,
    StageCompletionStatus,
    StageCoverage,
    StageErrorCode,
    StageProvenance,
)
from ntruth.parser_ai.contract import ParserCandidateOutput

fix1 = importlib.import_module("test_prd_v8_experiment_block_boundary_fix1")


class _HostileSemanticError(RuntimeError):
    def __str__(self) -> str:
        raise RuntimeError("semantic error formatting failed")


class _HostileWhitespace(str):
    _str_calls: list[str]
    _strip_calls: list[str]

    def __new__(
        cls,
        str_calls: list[str],
        strip_calls: list[str],
    ) -> _HostileWhitespace:
        instance = super().__new__(cls, " \t\n")
        instance._str_calls = str_calls
        instance._strip_calls = strip_calls
        return instance

    def __str__(self) -> str:
        self._str_calls.append("override-called")
        return "forged-nonblank-detail"

    def strip(self, chars: str | None = None, /) -> str:
        self._strip_calls.append("override-called")
        return "forged-nonblank-detail"


class _SubclassSemanticError(RuntimeError):
    def __init__(self, detail: _HostileWhitespace) -> None:
        super().__init__()
        self._detail = detail

    def __str__(self) -> str:
        return self._detail


class _ControlFlowSignal(BaseException):
    pass


def _valid_candidate() -> ParserCandidateOutput:
    return ParserCandidateOutput.model_validate(fix1._parser_payload())


def _complete_stage() -> MvtAStageOutput:
    return MvtAStageOutput(
        stage_id="stage-fix9-semantic-probe",
        status=StageCompletionStatus.COMPLETE,
        candidates=_valid_candidate(),
        coverage=StageCoverage(
            status=StageCompletionStatus.COMPLETE,
            covered_artifact_ids=("file-a",),
            rationale="Complete canonical fixture.",
        ),
        provenance=StageProvenance(
            producer_id="fix9-test",
            producer_version="1",
            input_artifact_ids=("file-a",),
            input_checksum="a" * 64,
        ),
    )


def test_semantic_runtime_error_fail_closes_without_escaping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_semantics(_candidate: ParserCandidateOutput) -> NoReturn:
        raise RuntimeError("semantic boundary verifier crashed")

    monkeypatch.setattr(
        verifier,
        "verify_candidate_experiment_block_boundaries",
        reject_semantics,
    )

    result = verifier.hard_verify_candidates(_valid_candidate())

    assert result.passed is False
    assert len(result.errors) == 1
    assert result.errors[0].code is StageErrorCode.VERIFIER_DISAGREEMENT
    assert result.errors[0].detail == "semantic boundary verifier crashed"
    assert result.checks_run[-1] == "experiment_block_boundaries"


def test_semantic_error_with_hostile_string_uses_stable_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_semantics(_candidate: ParserCandidateOutput) -> NoReturn:
        raise _HostileSemanticError

    monkeypatch.setattr(
        verifier,
        "verify_candidate_experiment_block_boundaries",
        reject_semantics,
    )

    result = verifier.hard_verify_candidates(_valid_candidate())

    assert result.passed is False
    assert len(result.errors) == 1
    assert result.errors[0].code is StageErrorCode.VERIFIER_DISAGREEMENT
    assert result.errors[0].detail == ("candidate experiment-block boundary validation failed")


@pytest.mark.parametrize(
    "semantic_error",
    [RuntimeError(""), RuntimeError(" \t\n")],
    ids=("empty-detail", "whitespace-detail"),
)
def test_semantic_blank_error_detail_uses_stable_fallback(
    monkeypatch: pytest.MonkeyPatch,
    semantic_error: RuntimeError,
) -> None:
    def reject_semantics(_candidate: ParserCandidateOutput) -> NoReturn:
        raise semantic_error

    monkeypatch.setattr(
        verifier,
        "verify_candidate_experiment_block_boundaries",
        reject_semantics,
    )

    result = verifier.hard_verify_candidates(_valid_candidate())

    assert result.passed is False
    assert len(result.errors) == 1
    assert result.errors[0].code is StageErrorCode.VERIFIER_DISAGREEMENT
    assert result.errors[0].detail == "candidate experiment-block boundary validation failed"


def test_semantic_str_subclass_cannot_override_stable_detail_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    str_calls: list[str] = []
    strip_calls: list[str] = []
    semantic_error = _SubclassSemanticError(_HostileWhitespace(str_calls, strip_calls))

    def reject_semantics(_candidate: ParserCandidateOutput) -> NoReturn:
        raise semantic_error

    monkeypatch.setattr(
        verifier,
        "verify_candidate_experiment_block_boundaries",
        reject_semantics,
    )

    result = verifier.hard_verify_candidates(_valid_candidate())

    assert result.passed is False
    assert len(result.errors) == 1
    assert result.errors[0].code is StageErrorCode.VERIFIER_DISAGREEMENT
    assert result.errors[0].detail == "candidate experiment-block boundary validation failed"
    assert str_calls == []
    assert strip_calls == []


def test_semantic_boundary_does_not_swallow_base_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def interrupt_semantics(_candidate: ParserCandidateOutput) -> NoReturn:
        raise _ControlFlowSignal

    monkeypatch.setattr(
        verifier,
        "verify_candidate_experiment_block_boundaries",
        interrupt_semantics,
    )

    with pytest.raises(_ControlFlowSignal):
        verifier.hard_verify_candidates(_valid_candidate())


def test_attach_verifier_fails_stage_on_ordinary_semantic_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_semantics(_candidate: ParserCandidateOutput) -> NoReturn:
        raise RuntimeError("attach semantic boundary failed")

    monkeypatch.setattr(
        verifier,
        "verify_candidate_experiment_block_boundaries",
        reject_semantics,
    )

    attached = verifier.attach_verifier(_complete_stage())

    assert attached.status is StageCompletionStatus.FAILED
    assert attached.coverage.status is StageCompletionStatus.FAILED
    assert attached.coverage.missing_artifact_ids == ("file-a",)
    assert attached.verifier_passed is False
    assert len(attached.verifier_errors) == 1
    assert attached.verifier_errors[0].code is StageErrorCode.VERIFIER_DISAGREEMENT
    assert attached.verifier_errors[0].detail == "attach semantic boundary failed"
    assert attached.errors == attached.verifier_errors
    assert attached.preserved_artifact_ids == ("file-a",)


def test_canonical_candidate_still_passes_semantic_verification() -> None:
    result = verifier.hard_verify_candidates(_valid_candidate())

    assert result.passed is True
    assert result.errors == ()
    assert result.checks_run == (
        "forbidden_final_fields",
        "non_empty_or_explicit_empty",
        "count_kinds_candidate_only",
        "experiment_block_boundaries",
    )
