"""Regressions for complete specialized KnowledgeValue boundary revalidation."""

from __future__ import annotations

import pickle
from typing import Any, Literal

import pytest
from pydantic import BaseModel, ValidationError
from pydantic_core import PydanticSerializationError

from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue


class _StringEnvelope(BaseModel):
    knowledge: KnowledgeValue[str]


class _MappingEnvelope(BaseModel):
    knowledge: KnowledgeValue[dict[str, list[str]]]


def _valid_payload(value: object) -> dict[str, object]:
    return {
        "schema_version": "8.0.0",
        "knowledge_state": KnowledgeState.PRESENT,
        "value": value,
        "conflicting_values": (),
        "evidence_ids": ("EV-001",),
        "source_scope_ids": (),
        "rationale": None,
        "claim_scope_id": None,
        "query_scope_id": None,
    }


_SPECIALIZED_DEFECTS: tuple[
    tuple[
        str,
        type[BaseModel],
        type[KnowledgeValue[Any]],
        dict[str, object],
    ],
    ...,
] = (
    (
        "string-value-type",
        _StringEnvelope,
        KnowledgeValue[str],
        {**_valid_payload("documented"), "value": 7},
    ),
    (
        "mapping-value-type",
        _MappingEnvelope,
        KnowledgeValue[dict[str, list[str]]],
        {**_valid_payload({"documented": ["value"]}), "value": {"documented": [7]}},
    ),
    (
        "schema-version",
        _StringEnvelope,
        KnowledgeValue[str],
        {**_valid_payload("documented"), "schema_version": "7.0.0"},
    ),
    (
        "incoherent-state",
        _StringEnvelope,
        KnowledgeValue[str],
        {**_valid_payload("documented"), "conflicting_values": ("A", "B")},
    ),
)


@pytest.mark.parametrize("representation", ("instance", "mapping"))
@pytest.mark.parametrize(
    "case_name,envelope_type,model_type,payload",
    _SPECIALIZED_DEFECTS,
    ids=lambda value: str(value),
)
def test_nested_serializer_revalidates_complete_effective_specialization(
    representation: Literal["instance", "mapping"],
    case_name: str,
    envelope_type: type[BaseModel],
    model_type: type[KnowledgeValue[Any]],
    payload: dict[str, object],
) -> None:
    del case_name
    nested: object
    if representation == "instance":
        nested = BaseModel.model_construct.__func__(model_type, **payload)
    else:
        nested = dict(payload)
    envelope = BaseModel.model_construct.__func__(envelope_type, knowledge=nested)

    with pytest.raises(PydanticSerializationError):
        BaseModel.model_dump(
            envelope,
            mode="python",
            round_trip=True,
            warnings="none",
        )


@pytest.mark.parametrize(
    "envelope_type,model_type,value",
    (
        (_StringEnvelope, KnowledgeValue[str], "documented"),
        (
            _MappingEnvelope,
            KnowledgeValue[dict[str, list[str]]],
            {"documented": ["value"]},
        ),
    ),
)
def test_valid_nested_raw_mapping_uses_its_effective_specialization(
    envelope_type: type[BaseModel],
    model_type: type[KnowledgeValue[Any]],
    value: object,
) -> None:
    raw = _valid_payload(value)
    envelope = BaseModel.model_construct.__func__(envelope_type, knowledge=raw)

    serialized = BaseModel.model_dump(
        envelope,
        mode="python",
        round_trip=True,
        warnings="error",
    )

    assert model_type.model_validate(serialized["knowledge"]).value == value


@pytest.mark.parametrize("deep", (False, True))
def test_model_copy_revalidates_the_copied_result_when_update_is_none(
    monkeypatch: pytest.MonkeyPatch,
    deep: bool,
) -> None:
    value = KnowledgeValue[str](
        knowledge_state=KnowledgeState.PRESENT,
        value="documented",
        evidence_ids=("EV-001",),
    )
    forged = BaseModel.model_construct.__func__(
        type(value),
        **{**value.__dict__, "value": None},
    )

    def return_forged_copy(
        _value: BaseModel,
        *,
        update: dict[str, object] | None = None,
        deep: bool = False,
    ) -> BaseModel:
        del update, deep
        return forged

    monkeypatch.setattr(BaseModel, "model_copy", return_forged_copy)

    with pytest.raises(ValidationError):
        value.model_copy(deep=deep)


class _SlottedKnowledge(KnowledgeValue[str]):
    __slots__ = ("public_runtime_state",)


def _slotted_knowledge() -> _SlottedKnowledge:
    value = _SlottedKnowledge(
        knowledge_state=KnowledgeState.PRESENT,
        value="documented",
        evidence_ids=("EV-001",),
    )
    object.__setattr__(value, "public_runtime_state", "undeclared")
    return value


@pytest.mark.parametrize("boundary", ("model-dump", "model-copy", "pickle"))
def test_public_slotted_subclass_state_is_rejected(boundary: str) -> None:
    value = _slotted_knowledge()

    with pytest.raises(TypeError, match="slotted"):
        if boundary == "model-dump":
            value.model_dump(mode="python")
        elif boundary == "model-copy":
            value.model_copy()
        else:
            pickle.dumps(value)


def test_unbound_serialization_rejects_public_slotted_subclass_state() -> None:
    with pytest.raises(PydanticSerializationError, match="slotted"):
        BaseModel.model_dump(_slotted_knowledge(), mode="python")


@pytest.mark.parametrize(
    "model_type,value",
    (
        (KnowledgeValue[str], "documented"),
        (KnowledgeValue[dict[str, list[str]]], {"documented": ["value"]}),
    ),
)
def test_canonical_pydantic_specializations_remain_supported(
    model_type: type[KnowledgeValue[Any]],
    value: object,
) -> None:
    original = model_type(
        knowledge_state=KnowledgeState.PRESENT,
        value=value,
        evidence_ids=("EV-001",),
    )

    assert original.model_copy() == original
    assert model_type.model_validate(original.model_dump(mode="python")) == original


class _AbortSerialization(BaseException):
    pass


def test_nested_mapping_revalidation_preserves_baseexception_as_direct_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_type = KnowledgeValue[str]
    envelope = BaseModel.model_construct.__func__(
        _StringEnvelope,
        knowledge=_valid_payload("documented"),
    )

    def abort(*_args: object, **_kwargs: object) -> Any:
        raise _AbortSerialization

    monkeypatch.setattr(model_type, "model_validate", abort)

    with pytest.raises(PydanticSerializationError) as captured:
        BaseModel.model_dump(envelope, mode="python")

    assert isinstance(captured.value.__cause__, _AbortSerialization)
