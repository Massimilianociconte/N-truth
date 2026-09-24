"""Regressions for identity-preserving KnowledgeValue pickle specialization arguments."""

from __future__ import annotations

import pickle
from collections.abc import Callable
from typing import Any, TypeVar

import pytest

from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue

_MODULE_GLOBAL_T = TypeVar("_MODULE_GLOBAL_T")


def _constrained_knowledge[T: (str, bytes)](value: T) -> KnowledgeValue[T]:
    return KnowledgeValue[T](
        knowledge_state=KnowledgeState.PRESENT,
        value=value,
        evidence_ids=("EV-001",),
    )


def test_function_local_constrained_typevar_fails_closed_before_pickle_emission() -> None:
    original = _constrained_knowledge("documented")

    with pytest.raises(TypeError, match=r"pickle-stable|importable"):
        pickle.dumps(original)


@pytest.mark.parametrize("specialization", ("str", "global-typevar"))
def test_pickle_stable_specialization_roundtrip_preserves_exact_type_identity(
    specialization: str,
) -> None:
    model_type: type[KnowledgeValue[Any]]
    if specialization == "str":
        model_type = KnowledgeValue[str]
    else:
        model_type = KnowledgeValue[_MODULE_GLOBAL_T]
    original = model_type(
        knowledge_state=KnowledgeState.PRESENT,
        value="documented",
        evidence_ids=("EV-001",),
    )

    restored = pickle.loads(pickle.dumps(original))

    assert restored == original
    assert type(restored) is model_type
    assert restored.__pydantic_fields_set__ == original.__pydantic_fields_set__


class _PickleWithState:
    def __init__(
        self,
        factory: Callable[..., object],
        args: tuple[object, ...],
        state: dict[str, Any],
    ) -> None:
        self.factory = factory
        self.args = args
        self.state = state

    def __reduce__(self) -> tuple[Callable[..., object], tuple[object, ...], dict[str, Any]]:
        return self.factory, self.args, self.state


def test_stable_specialization_pickle_rejects_tampered_state() -> None:
    original = KnowledgeValue[str](
        knowledge_state=KnowledgeState.PRESENT,
        value="documented",
        evidence_ids=("EV-001",),
    )
    reduction = original.__reduce_ex__(pickle.HIGHEST_PROTOCOL)
    state = original.__getstate__()
    state["format"] = "ntruth-knowledge-value-v0"

    with pytest.raises(ValueError, match="unsupported KnowledgeValue pickle envelope"):
        pickle.loads(
            pickle.dumps(
                _PickleWithState(
                    reduction[0],
                    reduction[1],
                    state,
                )
            )
        )


class _AbortPickleRestore(BaseException):
    pass


def test_stable_specialization_pickle_restore_propagates_baseexception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = KnowledgeValue[str](
        knowledge_state=KnowledgeState.PRESENT,
        value="documented",
        evidence_ids=("EV-001",),
    )
    payload = pickle.dumps(original)
    error = _AbortPickleRestore()

    def abort(*_args: object, **_kwargs: object) -> Any:
        raise error

    monkeypatch.setattr(type(original), "model_validate", abort)

    with pytest.raises(_AbortPickleRestore) as captured:
        pickle.loads(payload)

    assert captured.value is error
