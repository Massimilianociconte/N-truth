from __future__ import annotations

import importlib
from typing import Any, Literal

import pytest
from pydantic import BaseModel

from ntruth.mvt_a.verifier import hard_verify_candidates
from ntruth.parser_ai.contract import CandidateBlockBoundary, ParserCandidateOutput
from ntruth.schemas import block_boundary as boundary

fix1 = importlib.import_module("test_prd_v8_experiment_block_boundary_fix1")


class _SlottedParserCandidateOutput(ParserCandidateOutput):
    __slots__ = ("determinability",)

    def __getstate__(self) -> dict[str, Any]:
        state = BaseModel.__getstate__(self)
        state["slotted_determinability"] = self.determinability
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        determinability = state.pop("slotted_determinability")
        super().__setstate__(state)
        object.__setattr__(self, "determinability", determinability)


class _SlottedCandidateBlockBoundary(CandidateBlockBoundary):
    __slots__ = ("rule_result",)

    def __getstate__(self) -> dict[str, Any]:
        state = BaseModel.__getstate__(self)
        state["slotted_rule_result"] = self.rule_result
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        rule_result = state.pop("slotted_rule_result")
        super().__setstate__(state)
        object.__setattr__(self, "rule_result", rule_result)


class _BenignParserCandidateSubclass(ParserCandidateOutput):
    pass


def _slotted_root(
    valid: ParserCandidateOutput,
    construction: Literal["model_copy", "model_construct"],
) -> _SlottedParserCandidateOutput:
    if construction == "model_construct":
        forged = _SlottedParserCandidateOutput.model_construct(**valid.__dict__)
        object.__setattr__(forged, "determinability", "DETERMINATE")
        return forged
    seed = _SlottedParserCandidateOutput.model_validate(
        valid.model_dump(mode="python", round_trip=True)
    )
    forged = seed.model_copy()
    object.__setattr__(forged, "determinability", "DETERMINATE")
    return forged


def _slotted_boundary(
    valid: CandidateBlockBoundary,
    construction: Literal["model_copy", "model_construct"],
) -> _SlottedCandidateBlockBoundary:
    if construction == "model_construct":
        forged = _SlottedCandidateBlockBoundary.model_construct(**valid.__dict__)
        object.__setattr__(forged, "rule_result", {"verdict": "PASS"})
        return forged
    seed = _SlottedCandidateBlockBoundary.model_validate(
        valid.model_dump(mode="python", round_trip=True)
    )
    forged = seed.model_copy()
    object.__setattr__(forged, "rule_result", {"verdict": "PASS"})
    return forged


@pytest.mark.parametrize("construction", ("model_copy", "model_construct"))
@pytest.mark.parametrize("location", ("root", "nested"))
def test_verifiers_reject_pickle_visible_public_slot_subclasses(
    construction: Literal["model_copy", "model_construct"],
    location: Literal["root", "nested"],
) -> None:
    """Catches a subclass slot surviving pickle while remaining absent from model dumps."""

    valid = ParserCandidateOutput.model_validate(fix1._parser_payload())
    if location == "root":
        forged = _slotted_root(valid, construction)
        final_field = "determinability"
    else:
        forged_boundary = _slotted_boundary(valid.block_boundaries[0], construction)
        forged = valid.model_copy(update={"block_boundaries": (forged_boundary,)})
        final_field = "rule_result"

    restored = fix1._unsafe_candidate_pickle_roundtrip(forged)
    restored_target = restored if location == "root" else restored.block_boundaries[0]
    assert hasattr(restored_target, final_field)
    assert final_field not in type(restored_target).model_fields

    result = hard_verify_candidates(restored)
    assert result.passed is False
    assert any(
        "canonical" in error.detail or "runtime type" in error.detail for error in result.errors
    )
    with pytest.raises(ValueError, match=r"canonical|runtime type|subclass"):
        boundary.verify_candidate_experiment_block_boundaries(restored)


def test_verifiers_reject_even_a_fieldless_candidate_root_subclass() -> None:
    """Catches allowing a non-canonical runtime type merely because its dump is canonical."""

    valid = ParserCandidateOutput.model_validate(fix1._parser_payload())
    subclass = _BenignParserCandidateSubclass.model_validate(
        valid.model_dump(mode="python", round_trip=True)
    )

    assert hard_verify_candidates(subclass).passed is False
    with pytest.raises(ValueError, match=r"canonical|runtime type|subclass"):
        boundary.verify_candidate_experiment_block_boundaries(subclass)
