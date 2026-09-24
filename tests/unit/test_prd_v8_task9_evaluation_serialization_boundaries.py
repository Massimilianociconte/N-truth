from __future__ import annotations

import importlib
import pickle
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

import ntruth.evaluation_v8 as evaluation
from ntruth.schemas.support import ScientificReviewRequirement

copy_boundaries = importlib.import_module("test_prd_v8_task9_evaluation_copy_boundaries")
evaluation_fix1 = importlib.import_module("test_prd_v8_task7_evaluation_fix1")

OUTPUT_NAMES = ("reference", "end_to_end", "blind_audit", "reference_stability")


def _governed_output(name: str) -> BaseModel:
    if name == "reference":
        return copy_boundaries._reference_context(independent=False)[1]
    if name == "end_to_end":
        return copy_boundaries._end_to_end_result()
    if name == "blind_audit":
        return copy_boundaries._blind_audit_result()
    if name == "reference_stability":
        return evaluation_fix1._complete_stability_report()
    raise AssertionError(f"unknown governed output fixture: {name}")


def _invalid_update(name: str) -> dict[str, Any]:
    if name == "reference":
        return {"purpose": evaluation.IndependentReferencePurpose.INDEPENDENT_EVALUATION}
    if name == "end_to_end":
        return {"scientific_use_permitted": True, "blockers": ()}
    if name == "blind_audit":
        return {
            "scientific_use_permitted": True,
            "blocker": ScientificReviewRequirement(
                issue_id="SRR-CALLER-REISSUED",
                rationale="Caller attempted to replace the scientific HOLD.",
            ),
        }
    if name == "reference_stability":
        return {
            "blocker": ScientificReviewRequirement(
                issue_id=evaluation.REFERENCE_STABILITY_REVIEW_ISSUE_ID,
                rationale="Caller attempted to reopen an addressed reviewed conclusion.",
            )
        }
    raise AssertionError(f"unknown governed output mutation: {name}")


def _raw_invalid_output(name: str) -> BaseModel:
    valid = _governed_output(name)
    payload = valid.model_dump(mode="python", round_trip=True)
    payload.update(_invalid_update(name))
    return BaseModel.model_construct.__func__(type(valid), **payload)


def _restore_through_public_setstate(
    model_type: type[BaseModel], state: dict[Any, Any]
) -> BaseModel:
    restored = model_type.__new__(model_type)
    restored.__setstate__(state)
    return restored


class _InjectedPickleState:
    def __init__(self, model_type: type[BaseModel], state: dict[Any, Any]) -> None:
        self.model_type = model_type
        self.state = state

    def __reduce__(self) -> tuple[Callable[..., BaseModel], tuple[Any, ...]]:
        return _restore_through_public_setstate, (self.model_type, self.state)


@pytest.mark.parametrize("name", OUTPUT_NAMES)
@pytest.mark.parametrize("round_trip", (False, True))
def test_invalid_governed_output_cannot_use_supported_model_dump(
    name: str,
    round_trip: bool,
) -> None:
    """Catches a raw invalid Pydantic instance escaping as a Python payload."""

    forged = _raw_invalid_output(name)

    with pytest.raises(ValidationError):
        forged.model_dump(mode="python", round_trip=round_trip, warnings="none")


@pytest.mark.parametrize("name", OUTPUT_NAMES)
@pytest.mark.parametrize("round_trip", (False, True))
def test_invalid_governed_output_cannot_use_supported_model_dump_json(
    name: str,
    round_trip: bool,
) -> None:
    """Catches a raw invalid Pydantic instance escaping as JSON interchange."""

    forged = _raw_invalid_output(name)

    with pytest.raises(ValidationError):
        forged.model_dump_json(round_trip=round_trip, warnings="none")


@pytest.mark.parametrize("name", OUTPUT_NAMES)
def test_invalid_governed_output_cannot_be_pickled(name: str) -> None:
    """Catches pickle invoking an unchecked BaseModel state serializer."""

    with pytest.raises(ValidationError):
        pickle.dumps(_raw_invalid_output(name))


@pytest.mark.parametrize("name", OUTPUT_NAMES)
def test_invalid_pickle_state_is_revalidated_while_loading(name: str) -> None:
    """Catches unpickle restoring raw invalid model state without validators."""

    forged = _raw_invalid_output(name)
    legacy_state = BaseModel.__getstate__(forged)
    injected = _InjectedPickleState(type(forged), legacy_state)

    with pytest.raises((TypeError, ValueError)):
        pickle.loads(pickle.dumps(injected))


@pytest.mark.parametrize("name", OUTPUT_NAMES)
def test_valid_governed_output_dump_and_pickle_roundtrips(name: str) -> None:
    """Catches hardening that breaks valid governed serialization compatibility."""

    output = _governed_output(name)

    python_payload = output.model_dump(mode="python", round_trip=True, warnings="error")
    json_payload = output.model_dump_json(round_trip=True, warnings="error")
    restored_pickle = pickle.loads(pickle.dumps(output))

    assert type(output).model_validate(python_payload) == output
    assert type(output).model_validate_json(json_payload) == output
    assert restored_pickle == output
    assert restored_pickle is not output


@pytest.mark.parametrize("name", OUTPUT_NAMES)
def test_explicit_base_dump_is_untrusted_and_consumers_must_revalidate(name: str) -> None:
    """Documents the explicit BaseModel bypass outside the governed method boundary."""

    forged = _raw_invalid_output(name)

    raw_payload = BaseModel.model_dump(
        forged,
        mode="python",
        round_trip=True,
        warnings="none",
    )

    with pytest.raises(ValidationError):
        type(forged).model_validate(raw_payload)


def test_serialization_guard_does_not_catch_base_exceptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches a broad exception handler swallowing process-control exceptions."""

    output = _governed_output("end_to_end")

    def interrupt(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise KeyboardInterrupt

    monkeypatch.setattr(BaseModel, "model_dump", interrupt)

    with pytest.raises(KeyboardInterrupt):
        output.model_dump()
