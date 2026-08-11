from __future__ import annotations

import importlib
from typing import Any, Literal

import pytest

from ntruth.mvt_a.verifier import hard_verify_candidates
from ntruth.parser_ai.contract import ParserCandidateOutput
from ntruth.schemas import block_boundary as boundary

fix1 = importlib.import_module("test_prd_v8_experiment_block_boundary_fix1")


class _PrivatePretendingStr(str):
    def startswith(self, *args: Any, **kwargs: Any) -> bool:
        return True


def _unsafe_copy(
    model: Any,
    *,
    construction: Literal["model_copy", "model_construct"],
) -> Any:
    if construction == "model_copy":
        return model.model_copy()
    return type(model).model_construct(**model.__dict__)


def _forge_model_state_key(
    valid: ParserCandidateOutput,
    *,
    construction: Literal["model_copy", "model_construct"],
    location: Literal["root", "nested"],
) -> ParserCandidateOutput:
    target = valid if location == "root" else valid.block_boundaries[0]
    forged_target = _unsafe_copy(target, construction=construction)
    forged_target.__dict__[_PrivatePretendingStr("determinability")] = "DETERMINATE"
    if location == "root":
        return forged_target
    return valid.model_copy(update={"block_boundaries": (forged_target,)})


@pytest.mark.parametrize("consumer", ("hard", "direct"))
@pytest.mark.parametrize("construction", ("model_copy", "model_construct"))
@pytest.mark.parametrize("location", ("root", "nested"))
def test_verifiers_reject_pickle_visible_str_subclass_model_state_keys(
    consumer: Literal["hard", "direct"],
    construction: Literal["model_copy", "model_construct"],
    location: Literal["root", "nested"],
) -> None:
    """Catches an overridable ``startswith`` disguising public model state."""

    valid = ParserCandidateOutput.model_validate(fix1._parser_payload())
    forged = _forge_model_state_key(valid, construction=construction, location=location)
    restored = fix1._unsafe_candidate_pickle_roundtrip(forged)
    target = restored if location == "root" else restored.block_boundaries[0]
    hidden_key = next(key for key in target.__dict__ if type(key) is _PrivatePretendingStr)
    assert str(hidden_key) == "determinability"
    assert hidden_key.startswith("_") is True

    if consumer == "hard":
        result = hard_verify_candidates(restored)
        assert result.passed is False
        assert any("key" in error.detail or "canonical" in error.detail for error in result.errors)
    else:
        with pytest.raises(ValueError, match=r"key|canonical"):
            boundary.verify_candidate_experiment_block_boundaries(restored)


@pytest.mark.parametrize("consumer", ("hard", "direct"))
@pytest.mark.parametrize("construction", ("model_copy", "model_construct"))
def test_verifiers_reject_pickle_visible_str_subclass_enum_state_keys(
    consumer: Literal["hard", "direct"],
    construction: Literal["model_copy", "model_construct"],
) -> None:
    """Catches an overridable ``startswith`` disguising public enum state."""

    valid = ParserCandidateOutput.model_validate(fix1._parser_payload())
    forged = _unsafe_copy(valid, construction=construction)
    criterion = forged.block_boundaries[0].boundary_predicates[0].criterion
    hidden_key = _PrivatePretendingStr("determinability")
    criterion.__dict__[hidden_key] = "DETERMINATE"
    try:
        restored = fix1._unsafe_candidate_pickle_roundtrip(forged)
        restored_criterion = restored.block_boundaries[0].boundary_predicates[0].criterion
        restored_key = next(
            key for key in restored_criterion.__dict__ if type(key) is _PrivatePretendingStr
        )
        assert str(restored_key) == "determinability"
        assert restored_key.startswith("_") is True

        if consumer == "hard":
            result = hard_verify_candidates(restored)
            assert result.passed is False
            assert any(
                "enum" in error.detail or "key" in error.detail or "canonical" in error.detail
                for error in result.errors
            )
        else:
            with pytest.raises(ValueError, match=r"enum|key|canonical"):
                boundary.verify_candidate_experiment_block_boundaries(restored)
    finally:
        del criterion.__dict__[hidden_key]
