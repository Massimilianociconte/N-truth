from __future__ import annotations

from typing import NoReturn

import pytest

from ntruth.mvt_a.stage_schema import StageErrorCode
from ntruth.mvt_a.verifier import HardVerifierResult, hard_verify_candidates
from ntruth.parser_ai.contract import ParserCandidateOutput


class _PrimaryCanonicalizationError(Exception):
    def __str__(self) -> str:
        raise RuntimeError("secondary canonicalization formatting failed")


class _ArmedHashKey:
    def __init__(self) -> None:
        self.armed = False

    def __hash__(self) -> int:
        if self.armed:
            raise _PrimaryCanonicalizationError
        return 0

    def __eq__(self, other: object) -> bool:
        return self is other


class _SemanticContinuationSentinel:
    def __init__(self) -> None:
        self.probes = 0

    def __bool__(self) -> bool:
        self.probes += 1
        raise AssertionError("semantic verification continued after canonicalization failed")

    def __iter__(self) -> NoReturn:
        self.probes += 1
        raise AssertionError("semantic verification iterated a rejected candidate")


class _HostileWhitespace(str):
    _strip_calls: list[str]

    def __new__(cls, strip_calls: list[str]) -> _HostileWhitespace:
        instance = super().__new__(cls, " \t\n")
        instance._strip_calls = strip_calls
        return instance

    def strip(self, chars: str | None = None, /) -> str:
        self._strip_calls.append("override-called")
        return "forged-nonblank-detail"


class _SubclassDetailValueError(ValueError):
    def __init__(self, detail: _HostileWhitespace) -> None:
        super().__init__()
        self._detail = detail

    def __str__(self) -> str:
        return self._detail


class _ControlFlowSignal(BaseException):
    pass


def _assert_single_disagreement(
    result: HardVerifierResult,
    *,
    detail: str,
) -> None:
    assert result.passed is False
    assert len(result.errors) == 1
    assert result.errors[0].code is StageErrorCode.VERIFIER_DISAGREEMENT
    assert result.errors[0].detail == detail
    assert result.errors[0].detail.strip()


def test_hard_verifier_catches_secondary_formatting_exception_and_stops_semantic_checks() -> None:
    """Catches non-ValueError formatting failures escaping the canonical gate."""

    key = _ArmedHashKey()
    hostile_mapping = {key: "opaque structural value"}
    key.armed = True
    continuation = _SemanticContinuationSentinel()
    candidate = ParserCandidateOutput.model_construct(
        candidate_counts=continuation,
        model_metadata=hostile_mapping,
    )

    result = hard_verify_candidates(candidate)

    _assert_single_disagreement(
        result,
        detail="secondary canonicalization formatting failed",
    )
    assert continuation.probes == 0


def test_hard_verifier_rejects_str_subclass_without_calling_its_strip_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches a hostile string subclass making whitespace appear non-blank."""

    strip_calls: list[str] = []
    canonicalization_error = _SubclassDetailValueError(_HostileWhitespace(strip_calls))

    def reject_with_hostile_detail(_candidate: ParserCandidateOutput) -> NoReturn:
        raise canonicalization_error

    monkeypatch.setattr(
        ParserCandidateOutput,
        "assert_raw_candidate_only",
        reject_with_hostile_detail,
    )

    result = hard_verify_candidates(ParserCandidateOutput.model_construct())

    _assert_single_disagreement(
        result,
        detail="candidate parser payload failed canonical validation",
    )
    assert strip_calls == []


def test_hard_verifier_preserves_normal_non_value_error_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches the exception-total boundary replacing a safe diagnostic."""

    def reject_with_normal_detail(_candidate: ParserCandidateOutput) -> NoReturn:
        raise RuntimeError("canonical parser runtime formatting failed")

    monkeypatch.setattr(
        ParserCandidateOutput,
        "assert_raw_candidate_only",
        reject_with_normal_detail,
    )

    result = hard_verify_candidates(ParserCandidateOutput.model_construct())

    _assert_single_disagreement(
        result,
        detail="canonical parser runtime formatting failed",
    )


def test_hard_verifier_does_not_swallow_base_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keeps process-control signals outside the verifier error envelope."""

    def interrupt_canonicalization(_candidate: ParserCandidateOutput) -> NoReturn:
        raise _ControlFlowSignal

    monkeypatch.setattr(
        ParserCandidateOutput,
        "assert_raw_candidate_only",
        interrupt_canonicalization,
    )

    with pytest.raises(_ControlFlowSignal):
        hard_verify_candidates(ParserCandidateOutput.model_construct())
