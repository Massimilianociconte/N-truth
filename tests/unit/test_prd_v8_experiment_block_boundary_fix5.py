from __future__ import annotations

import importlib
import pickle
from typing import Any, Literal

import pytest

from ntruth.mvt_a.verifier import hard_verify_candidates
from ntruth.parser_ai.contract import ParserCandidateOutput
from ntruth.schemas import block_boundary as boundary

fix1 = importlib.import_module("test_prd_v8_experiment_block_boundary_fix1")


class _FinalStateCarrier:
    def __init__(self) -> None:
        self.determinability = "DETERMINATE"


class _ModelStateDict(dict[str, Any]):
    pass


def _unsafe_copy(
    model: Any,
    *,
    construction: Literal["model_copy", "model_construct"],
) -> Any:
    if construction == "model_copy":
        return model.model_copy()
    return type(model).model_construct(**model.__dict__)


def _with_public_state(
    valid: ParserCandidateOutput,
    *,
    location: Literal["root", "nested"],
    injection: Literal["benign_extra", "carrier_extra", "custom_state_dict"],
    construction: Literal["model_copy", "model_construct"],
) -> ParserCandidateOutput:
    target = valid if location == "root" else valid.block_boundaries[0]
    forged_target = _unsafe_copy(target, construction=construction)

    if injection == "benign_extra":
        forged_target.__dict__["undeclared_candidate_state"] = "not part of the contract"
    elif injection == "carrier_extra":
        forged_target.__dict__["undeclared_candidate_state"] = _FinalStateCarrier()
    else:
        state = _ModelStateDict(forged_target.__dict__)
        state.determinability = "DETERMINATE"
        object.__setattr__(forged_target, "__dict__", state)

    if location == "root":
        return forged_target
    return valid.model_copy(update={"block_boundaries": (forged_target,)})


@pytest.mark.parametrize("consumer", ("hard", "direct"))
@pytest.mark.parametrize("construction", ("model_copy", "model_construct"))
@pytest.mark.parametrize(
    "injection",
    ("benign_extra", "carrier_extra", "custom_state_dict"),
)
@pytest.mark.parametrize("location", ("root", "nested"))
def test_verifiers_reject_pickle_visible_undeclared_public_model_state(
    consumer: Literal["hard", "direct"],
    construction: Literal["model_copy", "model_construct"],
    injection: Literal["benign_extra", "carrier_extra", "custom_state_dict"],
    location: Literal["root", "nested"],
) -> None:
    """Catches public state being silently stripped instead of rejected."""

    valid = ParserCandidateOutput.model_validate(fix1._parser_payload())
    forged = _with_public_state(
        valid,
        location=location,
        injection=injection,
        construction=construction,
    )
    restored = pickle.loads(pickle.dumps(forged))

    if consumer == "hard":
        result = hard_verify_candidates(restored)
        assert result.passed is False
        assert any(
            "canonical" in error.detail or "undeclared" in error.detail or "runtime" in error.detail
            for error in result.errors
        )
    else:
        with pytest.raises(ValueError, match=r"canonical|undeclared|runtime"):
            boundary.verify_candidate_experiment_block_boundaries(restored)


@pytest.mark.parametrize("consumer", ("hard", "direct"))
@pytest.mark.parametrize(
    "extra_values",
    ({}, {1: "undeclared state"}),
    ids=("empty-extra-store", "non-string-key"),
)
def test_verifiers_fail_closed_for_noncanonical_pydantic_extra_storage(
    consumer: Literal["hard", "direct"],
    extra_values: dict[object, object],
) -> None:
    """Catches accepting or dereferencing unsafe Pydantic-extra storage."""

    valid = ParserCandidateOutput.model_validate(fix1._parser_payload()).model_copy()
    object.__setattr__(valid, "__pydantic_extra__", extra_values)
    restored = pickle.loads(pickle.dumps(valid))

    if consumer == "hard":
        result = hard_verify_candidates(restored)
        assert result.passed is False
        assert any(
            "extra" in error.detail or "canonical" in error.detail for error in result.errors
        )
    else:
        with pytest.raises(ValueError, match=r"extra|canonical"):
            boundary.verify_candidate_experiment_block_boundaries(restored)


@pytest.mark.parametrize("consumer", ("hard", "direct"))
def test_verifiers_fail_closed_for_declared_field_container_cycles(
    consumer: Literal["hard", "direct"],
) -> None:
    """Catches a raw cycle reaching Pydantic serialization and recursing."""

    valid = ParserCandidateOutput.model_validate(fix1._parser_payload())
    cycle: list[object] = []
    cycle.append(cycle)
    forged = valid.model_copy(update={"block_boundaries": cycle})
    restored = pickle.loads(pickle.dumps(forged))

    if consumer == "hard":
        result = hard_verify_candidates(restored)
        assert result.passed is False
        assert any(
            "recursive" in error.detail or "cycle" in error.detail for error in result.errors
        )
    else:
        with pytest.raises(ValueError, match=r"recursive|cycle"):
            boundary.verify_candidate_experiment_block_boundaries(restored)


@pytest.mark.parametrize("consumer", ("hard", "direct"))
def test_verifiers_reject_public_state_on_a_canonical_enum_member(
    consumer: Literal["hard", "direct"],
) -> None:
    """Catches exact enum identity masking mutable public scientific state."""

    valid = ParserCandidateOutput.model_validate(fix1._parser_payload())
    criterion = valid.block_boundaries[0].boundary_predicates[0].criterion
    object.__setattr__(criterion, "determinability", "DETERMINATE")
    try:
        restored = pickle.loads(pickle.dumps(valid))
        assert restored.block_boundaries[0].boundary_predicates[0].criterion is criterion

        if consumer == "hard":
            result = hard_verify_candidates(restored)
            assert result.passed is False
            assert any(
                "enum" in error.detail or "canonical" in error.detail for error in result.errors
            )
        else:
            with pytest.raises(ValueError, match=r"enum|canonical"):
                boundary.verify_candidate_experiment_block_boundaries(restored)
    finally:
        object.__delattr__(criterion, "determinability")


def test_hard_verifier_stops_after_runtime_tree_canonicalization_failure() -> None:
    """Catches later checks iterating a raw bundle that the hard gate rejected."""

    valid = ParserCandidateOutput.model_validate(fix1._parser_payload())
    forged = valid.model_copy(update={"candidate_counts": 1})
    restored = pickle.loads(pickle.dumps(forged))

    result = hard_verify_candidates(restored)

    assert result.passed is False
    assert len(result.errors) == 1
    assert result.errors[0].code.value == "VERIFIER_DISAGREEMENT"
    assert "candidate_counts" in result.errors[0].detail
