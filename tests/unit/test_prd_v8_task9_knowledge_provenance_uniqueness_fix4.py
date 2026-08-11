"""Regressions for stable canonical KnowledgeValue pickle reconstruction."""

from __future__ import annotations

import pickle
import subprocess
import sys
from collections.abc import Callable
from typing import Any

import pytest

from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue


@pytest.mark.parametrize(
    "type_expression",
    ("str", "PayloadT"),
    ids=("str", "typevar"),
)
def test_first_canonical_specialization_created_inside_function_is_picklable(
    type_expression: str,
) -> None:
    script = f"""
import pickle
from typing import TypeVar

from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue

PayloadT = TypeVar("PayloadT")

def exercise():
    model_type = KnowledgeValue[{type_expression}]
    original = model_type(
        knowledge_state=KnowledgeState.PRESENT,
        value="documented",
        evidence_ids=("EV-001",),
    )
    restored = pickle.loads(pickle.dumps(original))
    assert restored == original
    assert type(restored) is model_type
    assert restored.__pydantic_fields_set__ == original.__pydantic_fields_set__

exercise()
print("roundtrip-ok")
"""

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == "roundtrip-ok\n"


def _generic_knowledge[T](value: T) -> KnowledgeValue[T]:
    return KnowledgeValue[T](
        knowledge_state=KnowledgeState.PRESENT,
        value=value,
        evidence_ids=("EV-001",),
    )


def test_function_local_typevar_specialization_fails_closed_at_pickle_boundary() -> None:
    original = _generic_knowledge("documented")

    with pytest.raises(TypeError, match=r"pickle-stable|importable"):
        pickle.dumps(original)


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


def _restore_with_state(
    original: KnowledgeValue[str],
    state: dict[str, Any],
) -> object:
    reduction = original.__reduce_ex__(pickle.HIGHEST_PROTOCOL)
    factory = reduction[0]
    args = reduction[1]
    assert callable(factory)
    assert type(args) is tuple
    return pickle.loads(pickle.dumps(_PickleWithState(factory, args, state)))


@pytest.mark.parametrize("tamper", ("legacy-format", "duplicate-provenance"))
def test_stable_pickle_reconstruction_rejects_legacy_or_tampered_state(
    tamper: str,
) -> None:
    original = KnowledgeValue[str](
        knowledge_state=KnowledgeState.PRESENT,
        value="documented",
        evidence_ids=("EV-001",),
    )
    state = original.__getstate__()
    if tamper == "legacy-format":
        state["format"] = "ntruth-knowledge-value-v0"
    else:
        state["payload"] = {
            **state["payload"],
            "evidence_ids": ("EV-001", "EV-001"),
        }

    with pytest.raises((TypeError, ValueError)):
        _restore_with_state(original, state)


class _AbortPickleRestore(BaseException):
    pass


@pytest.mark.parametrize("error", (RuntimeError("validation failed"), _AbortPickleRestore()))
def test_stable_pickle_restore_fails_closed_without_swallowing_baseexception(
    monkeypatch: pytest.MonkeyPatch,
    error: BaseException,
) -> None:
    original = KnowledgeValue[str](
        knowledge_state=KnowledgeState.PRESENT,
        value="documented",
        evidence_ids=("EV-001",),
    )
    payload = pickle.dumps(original)

    def fail_validation(*_args: object, **_kwargs: object) -> Any:
        raise error

    monkeypatch.setattr(type(original), "model_validate", fail_validation)

    with pytest.raises(type(error)) as captured:
        pickle.loads(payload)

    assert captured.value is error
