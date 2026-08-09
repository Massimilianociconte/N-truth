"""Exception-total semantic boundary for the MVT-A hard verifier."""

from __future__ import annotations

import importlib
from typing import NoReturn

import pytest

import ntruth.mvt_a.verifier as verifier
from ntruth.mvt_a.stage_schema import StageErrorCode
from ntruth.parser_ai.contract import ParserCandidateOutput

fix1 = importlib.import_module("test_prd_v8_experiment_block_boundary_fix1")


class _HostileSemanticError(RuntimeError):
    def __str__(self) -> str:
        raise RuntimeError("semantic error formatting failed")


class _ControlFlowSignal(BaseException):
    pass


def _valid_candidate() -> ParserCandidateOutput:
    return ParserCandidateOutput.model_validate(fix1._parser_payload())


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
