"""Regressions for canonical KnowledgeValue copy and subclass boundaries."""

from __future__ import annotations

import pickle
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import BaseModel, PydanticDeprecatedSince20, TypeAdapter
from pydantic_core import PydanticSerializationError

from ntruth.schemas.knowledge import (
    KnowledgeState,
    KnowledgeValue,
    ScientificKnowledgeValue,
)


class _ApplicationKnowledge(KnowledgeValue[str]):
    application_note: str


def _canonical_mapping_value() -> KnowledgeValue[object]:
    return KnowledgeValue[object](
        knowledge_state=KnowledgeState.PRESENT,
        value={"documented": ["value"]},
        evidence_ids=("EV-001",),
    )


def _generic_knowledge[T](value: T) -> KnowledgeValue[T]:
    return KnowledgeValue[T](
        knowledge_state=KnowledgeState.PRESENT,
        value=value,
        evidence_ids=("EV-001",),
    )


@pytest.mark.parametrize("deep", (False, True))
def test_update_none_copy_rejects_coercible_noncanonical_provenance_container(
    deep: bool,
) -> None:
    canonical = KnowledgeValue[str](
        knowledge_state=KnowledgeState.PRESENT,
        value="documented",
        evidence_ids=("EV-001",),
    )
    forged = BaseModel.model_construct.__func__(
        type(canonical),
        **{**canonical.__dict__, "evidence_ids": ["EV-001"]},
    )

    with pytest.raises((TypeError, ValueError), match=r"canonical|runtime type"):
        forged.model_copy(deep=deep)


@pytest.mark.parametrize("deep", (False, True))
def test_update_none_copy_preserves_canonical_shallow_and_deep_identity(
    deep: bool,
) -> None:
    original = _canonical_mapping_value()

    copied = original.model_copy(deep=deep)

    assert copied == original
    assert copied is not original
    assert copied.value is not None
    assert original.value is not None
    if deep:
        assert copied.value is not original.value
        assert copied.value["documented"] is not original.value["documented"]
    else:
        assert copied.value is original.value


def _application_knowledge() -> _ApplicationKnowledge:
    return _ApplicationKnowledge(
        knowledge_state=KnowledgeState.PRESENT,
        value="documented",
        evidence_ids=("EV-001",),
        application_note="must not cross the governed parent boundary",
    )


def _restore_application_pickle_state(value: _ApplicationKnowledge) -> None:
    object.__new__(type(value)).__setstate__(
        {
            "format": "ntruth-knowledge-value-v1",
            "payload": dict(value.__dict__),
            "fields_set": set(value.__pydantic_fields_set__),
        }
    )


_APPLICATION_BOUNDARIES: tuple[tuple[str, Callable[[_ApplicationKnowledge], object]], ...] = (
    ("model-dump", lambda value: value.model_dump(mode="python")),
    ("model-dump-json", lambda value: value.model_dump_json()),
    (
        "parent-adapter-dump",
        lambda value: TypeAdapter(KnowledgeValue[str]).dump_python(value),
    ),
    (
        "parent-adapter-json",
        lambda value: TypeAdapter(KnowledgeValue[str]).dump_json(value),
    ),
    (
        "parent-adapter-validate",
        lambda value: TypeAdapter(KnowledgeValue[str]).validate_python(value),
    ),
    ("model-copy-shallow", lambda value: value.model_copy()),
    ("model-copy-deep", lambda value: value.model_copy(deep=True)),
    ("pickle", pickle.dumps),
    ("pickle-load", _restore_application_pickle_state),
)


@pytest.mark.parametrize(
    "boundary_name,boundary",
    _APPLICATION_BOUNDARIES,
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_application_subclass_with_declared_field_is_rejected_at_parent_boundaries(
    boundary_name: str,
    boundary: Callable[[_ApplicationKnowledge], object],
) -> None:
    del boundary_name

    with pytest.raises(
        (TypeError, ValueError, PydanticSerializationError),
        match=r"canonical|subclass|Extra inputs",
    ):
        boundary(_application_knowledge())


def test_deprecated_copy_rejects_application_subclass_with_declared_field() -> None:
    with (
        pytest.warns(PydanticDeprecatedSince20, match=r"copy.*deprecated"),
        pytest.raises((TypeError, ValueError), match=r"canonical|subclass"),
    ):
        _application_knowledge().copy()


@pytest.mark.parametrize(
    "model_type,value",
    (
        (KnowledgeValue, "documented"),
        (KnowledgeValue[str], "documented"),
        (ScientificKnowledgeValue, {"documented": ["value"]}),
    ),
)
def test_canonical_base_specializations_and_scientific_alias_remain_supported(
    model_type: type[KnowledgeValue[Any]],
    value: object,
) -> None:
    original = model_type(
        knowledge_state=KnowledgeState.PRESENT,
        value=value,
        evidence_ids=("EV-001",),
    )

    shallow = original.model_copy()
    deep = original.model_copy(deep=True)
    restored = pickle.loads(pickle.dumps(original))

    assert shallow == original
    assert deep == original
    assert restored == original
    assert type(shallow) is model_type
    assert type(deep) is model_type
    assert type(restored) is model_type
    assert model_type.model_validate_json(original.model_dump_json()) == original


def test_canonical_typevar_specialization_remains_supported() -> None:
    original = _generic_knowledge("documented")

    copied = original.model_copy()

    assert copied == original
    assert type(copied) is type(original)
    assert original.model_dump(mode="python")["value"] == "documented"


class _AbortCopyBoundary(BaseException):
    pass


@pytest.mark.parametrize("error", (RuntimeError("validation failed"), _AbortCopyBoundary()))
def test_copy_validation_fails_closed_without_swallowing_baseexception(
    monkeypatch: pytest.MonkeyPatch,
    error: BaseException,
) -> None:
    value = KnowledgeValue[str](
        knowledge_state=KnowledgeState.PRESENT,
        value="documented",
        evidence_ids=("EV-001",),
    )

    def fail_validation(*_args: object, **_kwargs: object) -> Any:
        raise error

    monkeypatch.setattr(type(value), "model_validate", fail_validation)

    with pytest.raises(type(error)) as captured:
        value.model_copy()

    assert captured.value is error
