from __future__ import annotations

import importlib
from typing import Any, Literal

import pytest

from ntruth.mvt_a.verifier import hard_verify_candidates
from ntruth.parser_ai.contract import ParserCandidateOutput
from ntruth.schemas import block_boundary as boundary

fix1 = importlib.import_module("test_prd_v8_experiment_block_boundary_fix1")


class _VerdictList(list[Any]):
    pass


class _VerdictTuple(tuple[Any, ...]):
    pass


class _VerdictDict(dict[str, Any]):
    pass


class _VerdictSet(set[Any]):
    pass


class _VerdictFrozenSet(frozenset[Any]):
    pass


class _VerdictStr(str):
    pass


class _VerdictFloat(float):
    pass


_CONTAINER_TYPES: tuple[tuple[str, type[Any]], ...] = (
    ("list", _VerdictList),
    ("tuple", _VerdictTuple),
    ("dict", _VerdictDict),
    ("set", _VerdictSet),
    ("frozenset", _VerdictFrozenSet),
)

_FINAL_FIELDS: tuple[tuple[str, object], ...] = (
    ("determinability", "DETERMINATE"),
    ("design_adequacy", "ADEQUATE"),
    ("n", 12),
    ("experimental_unit", "CAGE"),
    ("rule_result", {"verdict": "PASS"}),
)


def _verdict_container(
    container_name: str,
    container_type: type[Any],
    valid: ParserCandidateOutput,
    *,
    final_field: str,
    final_value: object,
) -> tuple[object, str]:
    if container_name == "dict":
        container = container_type({"boundaries": valid.block_boundaries})
        target_field = "container_payload"
    else:
        container = container_type(valid.block_boundaries)
        target_field = "block_boundaries"
    object.__setattr__(container, final_field, final_value)
    return container, target_field


@pytest.mark.parametrize(("final_field", "final_value"), _FINAL_FIELDS)
@pytest.mark.parametrize(("container_name", "container_type"), _CONTAINER_TYPES)
@pytest.mark.parametrize("construction", ("model_copy", "model_construct"))
def test_verifiers_reject_pickle_visible_container_subclass_final_fields(
    final_field: str,
    final_value: object,
    container_name: str,
    container_type: type[Any],
    construction: Literal["model_copy", "model_construct"],
) -> None:
    """Catches container normalization hiding public final-field state."""

    valid = ParserCandidateOutput.model_validate(fix1._parser_payload())
    container, target_field = _verdict_container(
        container_name,
        container_type,
        valid,
        final_field=final_field,
        final_value=final_value,
    )
    if construction == "model_copy":
        forged = valid.model_copy(update={target_field: container})
    else:
        forged = ParserCandidateOutput.model_construct(**valid.__dict__)
        forged.__dict__[target_field] = container

    restored = fix1._unsafe_candidate_pickle_roundtrip(forged)
    restored_container = restored.__dict__[target_field]
    assert getattr(restored_container, final_field) == final_value

    result = hard_verify_candidates(restored)
    assert result.passed is False
    assert any(
        "canonical" in error.detail or "runtime container" in error.detail
        for error in result.errors
    )
    with pytest.raises(ValueError, match=r"canonical|runtime container|container subclass"):
        boundary.verify_candidate_experiment_block_boundaries(restored)


@pytest.mark.parametrize("scalar_case", ("primitive", "enum"))
def test_verifiers_reject_noncanonical_scalar_and_enum_runtime_types(
    scalar_case: Literal["primitive", "enum"],
) -> None:
    """Catches validation coercion hiding a non-canonical declared-field runtime type."""

    valid = ParserCandidateOutput.model_validate(fix1._parser_payload())
    candidate = valid.block_boundaries[0]
    if scalar_case == "primitive":
        forged_candidate = candidate.model_copy(update={"confidence": 1})
    else:
        forged_predicate = candidate.boundary_predicates[0].model_copy(
            update={"criterion": "DISTINCT_EXPERIMENT_SOURCE_DOCUMENT"}
        )
        forged_candidate = candidate.model_copy(update={"boundary_predicates": (forged_predicate,)})
    forged = valid.model_copy(update={"block_boundaries": (forged_candidate,)})
    restored = fix1._unsafe_candidate_pickle_roundtrip(forged)

    result = hard_verify_candidates(restored)
    assert result.passed is False
    assert any(
        "runtime type" in error.detail or "canonical" in error.detail for error in result.errors
    )
    with pytest.raises(ValueError, match=r"canonical|runtime type"):
        boundary.verify_candidate_experiment_block_boundaries(restored)


@pytest.mark.parametrize(("final_field", "final_value"), _FINAL_FIELDS)
@pytest.mark.parametrize("scalar_case", ("primitive", "enum"))
@pytest.mark.parametrize("construction", ("model_copy", "model_construct"))
def test_verifiers_reject_pickle_visible_scalar_subclass_final_fields(
    final_field: str,
    final_value: object,
    scalar_case: Literal["primitive", "enum"],
    construction: Literal["model_copy", "model_construct"],
) -> None:
    """Scalar subclasses may not hide final-field state during canonicalization."""

    valid = ParserCandidateOutput.model_validate(fix1._parser_payload())
    candidate = valid.block_boundaries[0]
    if scalar_case == "primitive":
        scalar = _VerdictFloat(candidate.confidence)
        object.__setattr__(scalar, final_field, final_value)
        if construction == "model_copy":
            forged_candidate = candidate.model_copy(update={"confidence": scalar})
        else:
            forged_candidate = type(candidate).model_construct(**candidate.__dict__)
            forged_candidate.__dict__["confidence"] = scalar
    else:
        predicate = candidate.boundary_predicates[0]
        scalar = _VerdictStr(predicate.criterion.value)
        object.__setattr__(scalar, final_field, final_value)
        if construction == "model_copy":
            forged_predicate = predicate.model_copy(update={"criterion": scalar})
        else:
            forged_predicate = type(predicate).model_construct(**predicate.__dict__)
            forged_predicate.__dict__["criterion"] = scalar
        forged_candidate = candidate.model_copy(update={"boundary_predicates": (forged_predicate,)})
    forged = valid.model_copy(update={"block_boundaries": (forged_candidate,)})
    restored = fix1._unsafe_candidate_pickle_roundtrip(forged)

    restored_candidate = restored.block_boundaries[0]
    restored_scalar = (
        restored_candidate.confidence
        if scalar_case == "primitive"
        else restored_candidate.boundary_predicates[0].criterion
    )
    assert getattr(restored_scalar, final_field) == final_value

    result = hard_verify_candidates(restored)
    assert result.passed is False
    assert any(
        "runtime type" in error.detail or "canonical" in error.detail for error in result.errors
    )
    with pytest.raises(ValueError, match=r"canonical|runtime type"):
        boundary.verify_candidate_experiment_block_boundaries(restored)
