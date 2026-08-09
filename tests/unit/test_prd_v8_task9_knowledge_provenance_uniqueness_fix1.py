"""Fail-closed boundaries for KnowledgeValue provenance identity."""

from __future__ import annotations

import pickle
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import BaseModel, PydanticDeprecatedSince20, ValidationError
from pydantic_core import PydanticSerializationError

from ntruth.schemas.core import content_checksum
from ntruth.schemas.kernel import KernelModel
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue


class _KnowledgeEnvelope(KernelModel):
    knowledge: KnowledgeValue[object]


class _SentinelBaseException(BaseException):
    pass


_STATE_PAYLOADS: tuple[tuple[str, dict[str, object]], ...] = (
    (
        "present",
        {
            "knowledge_state": KnowledgeState.PRESENT,
            "value": "documented",
            "evidence_ids": ("EV-002", "EV-001"),
            "source_scope_ids": ("SOURCE-002", "SOURCE-001"),
        },
    ),
    (
        "absent",
        {
            "knowledge_state": KnowledgeState.ABSENT_EXPLICIT,
            "evidence_ids": ("EV-002", "EV-001"),
            "source_scope_ids": ("SOURCE-002", "SOURCE-001"),
        },
    ),
    (
        "not-reported",
        {
            "knowledge_state": KnowledgeState.NOT_REPORTED,
            "evidence_ids": ("EV-002", "EV-001"),
            "source_scope_ids": ("SOURCE-002", "SOURCE-001"),
        },
    ),
    (
        "unknown",
        {
            "knowledge_state": KnowledgeState.UNKNOWN,
            "rationale": "The reviewed evidence does not resolve this value.",
            "query_scope_id": "IQ-001",
            "evidence_ids": ("EV-002", "EV-001"),
            "source_scope_ids": ("SOURCE-002", "SOURCE-001"),
        },
    ),
    (
        "not-applicable",
        {
            "knowledge_state": KnowledgeState.NOT_APPLICABLE,
            "rationale": "This value is outside the declared query scope.",
            "query_scope_id": "IQ-001",
            "evidence_ids": ("EV-002", "EV-001"),
            "source_scope_ids": ("SOURCE-002", "SOURCE-001"),
        },
    ),
    (
        "conflicting",
        {
            "knowledge_state": KnowledgeState.CONFLICTING,
            "conflicting_values": ("A", "B"),
            "evidence_ids": ("EV-002", "EV-001"),
            "source_scope_ids": ("SOURCE-002", "SOURCE-001"),
        },
    ),
)


_GENERIC_SPECIALIZATIONS: tuple[
    tuple[str, type[KnowledgeValue[Any]], object], ...
] = (
    ("object", KnowledgeValue[object], "documented"),
    ("string", KnowledgeValue[str], "documented"),
    (
        "mapping",
        KnowledgeValue[dict[str, list[str]]],
        {"documented": ["value"]},
    ),
)


def _duplicate_payload(
    payload: dict[str, object],
    field_name: str,
) -> dict[str, object]:
    duplicated = "EV-DUPLICATE" if field_name == "evidence_ids" else "SOURCE-DUPLICATE"
    return {**payload, field_name: (duplicated, duplicated)}


@pytest.mark.parametrize("state_name,payload", _STATE_PAYLOADS, ids=lambda value: str(value))
@pytest.mark.parametrize("field_name", ("evidence_ids", "source_scope_ids"))
@pytest.mark.parametrize("construction", ("model_copy", "copy", "model_construct"))
def test_duplicate_provenance_is_rejected_at_every_public_construction_boundary(
    state_name: str,
    payload: dict[str, object],
    field_name: str,
    construction: str,
) -> None:
    del state_name
    valid = KnowledgeValue[object].model_validate(payload)
    duplicate = _duplicate_payload(payload, field_name)[field_name]

    with pytest.raises(ValidationError, match="unique and order-preserving"):
        if construction == "model_copy":
            valid.model_copy(update={field_name: duplicate})
        elif construction == "copy":
            with pytest.warns(PydanticDeprecatedSince20, match=r"copy.*deprecated"):
                valid.copy(update={field_name: duplicate})
        else:
            KnowledgeValue[object].model_construct(
                **{**valid.__dict__, field_name: duplicate}
            )


def _invalid_knowledge(
    field_name: str,
    model_type: type[KnowledgeValue[Any]] = KnowledgeValue[object],
    value: object = "documented",
) -> KnowledgeValue[Any]:
    payload = _duplicate_payload(
        {**_STATE_PAYLOADS[0][1], "value": value},
        field_name,
    )
    return BaseModel.model_construct.__func__(model_type, **payload)


def _invalid_state_knowledge(
    payload: dict[str, object],
    field_name: str,
) -> KnowledgeValue[object]:
    return BaseModel.model_construct.__func__(
        KnowledgeValue[object],
        **_duplicate_payload(payload, field_name),
    )


@pytest.mark.parametrize("field_name", ("evidence_ids", "source_scope_ids"))
@pytest.mark.parametrize(
    "specialization_name,model_type,value",
    _GENERIC_SPECIALIZATIONS,
    ids=lambda value: str(value),
)
@pytest.mark.parametrize(
    "serialize",
    (
        lambda value: value.model_dump(mode="python", round_trip=True),
        lambda value: value.model_dump_json(round_trip=True),
        lambda value: content_checksum(value.model_dump(mode="json")),
        pickle.dumps,
    ),
    ids=("model-dump", "model-dump-json", "address", "pickle"),
)
def test_invalid_provenance_cannot_cross_direct_serialization_boundaries(
    field_name: str,
    specialization_name: str,
    model_type: type[KnowledgeValue[Any]],
    value: object,
    serialize: Callable[[KnowledgeValue[Any]], object],
) -> None:
    del specialization_name
    with pytest.raises(ValidationError, match="unique and order-preserving"):
        serialize(_invalid_knowledge(field_name, model_type, value))


@pytest.mark.parametrize("state_name,payload", _STATE_PAYLOADS, ids=lambda value: str(value))
@pytest.mark.parametrize("field_name", ("evidence_ids", "source_scope_ids"))
@pytest.mark.parametrize(
    "serialize",
    (
        lambda value: value.model_dump(mode="python", round_trip=True),
        lambda value: value.model_dump_json(round_trip=True),
        pickle.dumps,
    ),
    ids=("model-dump", "model-dump-json", "pickle"),
)
def test_duplicate_provenance_cannot_cross_serialization_in_any_state(
    state_name: str,
    payload: dict[str, object],
    field_name: str,
    serialize: Callable[[KnowledgeValue[object]], object],
) -> None:
    del state_name
    with pytest.raises(ValidationError, match="unique and order-preserving"):
        serialize(_invalid_state_knowledge(payload, field_name))


@pytest.mark.parametrize("field_name", ("evidence_ids", "source_scope_ids"))
@pytest.mark.parametrize(
    "specialization_name,model_type,value",
    _GENERIC_SPECIALIZATIONS,
    ids=lambda value: str(value),
)
def test_invalid_provenance_cannot_cross_unbound_base_serialization(
    field_name: str,
    specialization_name: str,
    model_type: type[KnowledgeValue[Any]],
    value: object,
) -> None:
    del specialization_name
    with pytest.raises(PydanticSerializationError, match="unique and order-preserving"):
        BaseModel.model_dump(
            _invalid_knowledge(field_name, model_type, value),
            mode="python",
            round_trip=True,
        )


@pytest.mark.parametrize("field_name", ("evidence_ids", "source_scope_ids"))
@pytest.mark.parametrize(
    "specialization_name,model_type,value",
    _GENERIC_SPECIALIZATIONS,
    ids=lambda value: str(value),
)
def test_invalid_provenance_cannot_cross_nested_serialization(
    field_name: str,
    specialization_name: str,
    model_type: type[KnowledgeValue[Any]],
    value: object,
) -> None:
    del specialization_name
    envelope = BaseModel.model_construct.__func__(
        _KnowledgeEnvelope,
        knowledge=_invalid_knowledge(field_name, model_type, value),
    )

    with pytest.raises(PydanticSerializationError, match="unique and order-preserving"):
        envelope.model_dump(mode="json")


@pytest.mark.parametrize("extra_state", ({}, {"undeclared": "value"}))
def test_non_none_pydantic_extra_state_cannot_cross_serialization(
    extra_state: dict[str, object],
) -> None:
    invalid = BaseModel.model_copy(
        KnowledgeValue[object].model_validate(_STATE_PAYLOADS[0][1])
    )
    object.__setattr__(invalid, "__pydantic_extra__", extra_state)

    with pytest.raises(TypeError, match="undeclared extra model state"):
        invalid.model_dump(mode="python")


def test_undeclared_public_runtime_state_cannot_cross_serialization() -> None:
    invalid = BaseModel.model_copy(
        KnowledgeValue[object].model_validate(_STATE_PAYLOADS[0][1])
    )
    object.__getattribute__(invalid, "__dict__")["undeclared"] = "value"

    with pytest.raises(TypeError, match="undeclared or missing model field"):
        invalid.model_dump(mode="python")

    with pytest.raises(PydanticSerializationError, match="undeclared or missing model field"):
        BaseModel.model_dump(invalid, mode="python")


def test_nested_exact_raw_mapping_can_reach_governed_parent_revalidation() -> None:
    valid = KnowledgeValue[object].model_validate(_STATE_PAYLOADS[0][1])
    raw = BaseModel.model_dump(valid, mode="python", round_trip=True)
    envelope = BaseModel.model_construct.__func__(_KnowledgeEnvelope, knowledge=raw)

    serialized = BaseModel.model_dump(
        envelope,
        mode="python",
        round_trip=True,
        warnings="error",
    )

    assert serialized["knowledge"]["evidence_ids"] == ("EV-002", "EV-001")


def test_nested_raw_mapping_cannot_hide_duplicate_provenance() -> None:
    valid = KnowledgeValue[object].model_validate(_STATE_PAYLOADS[0][1])
    raw = BaseModel.model_dump(valid, mode="python", round_trip=True)
    raw["evidence_ids"] = ("EV-DUPLICATE", "EV-DUPLICATE")
    envelope = BaseModel.model_construct.__func__(_KnowledgeEnvelope, knowledge=raw)

    with pytest.raises(PydanticSerializationError, match="unique and order-preserving"):
        BaseModel.model_dump(
            envelope,
            mode="python",
            round_trip=True,
            warnings="error",
        )


@pytest.mark.parametrize("field_name", ("evidence_ids", "source_scope_ids"))
@pytest.mark.parametrize("projection", ("include", "exclude"))
@pytest.mark.parametrize("boundary", ("model_dump", "model_dump_json"))
def test_partial_serialization_cannot_hide_invalid_provenance(
    field_name: str,
    projection: str,
    boundary: str,
) -> None:
    invalid = _invalid_knowledge(field_name)
    selected = {"knowledge_state"} if projection == "include" else {field_name}

    with pytest.raises(ValidationError, match="unique and order-preserving"):
        getattr(invalid, boundary)(**{projection: selected})


@pytest.mark.parametrize("projection", ("include", "exclude"))
def test_deprecated_copy_rejects_partial_knowledge_values(projection: str) -> None:
    valid = KnowledgeValue[object].model_validate(_STATE_PAYLOADS[0][1])

    with (
        pytest.warns(PydanticDeprecatedSince20, match=r"copy.*deprecated"),
        pytest.raises(TypeError, match="partial KnowledgeValue copies are forbidden"),
    ):
        valid.copy(**{projection: {"knowledge_state"}})


@pytest.mark.parametrize(
    "update",
    (
        {"value": None},
        {"undeclared": "value"},
    ),
    ids=("invalid-non-provenance", "unknown-extra"),
)
def test_model_copy_revalidates_every_update(update: dict[str, object]) -> None:
    valid = KnowledgeValue[object].model_validate(_STATE_PAYLOADS[0][1])

    with pytest.raises(ValidationError):
        valid.model_copy(update=update)


@pytest.mark.parametrize("state_name,payload", _STATE_PAYLOADS, ids=lambda value: str(value))
def test_valid_order_and_roundtrips_are_preserved(
    state_name: str,
    payload: dict[str, object],
) -> None:
    del state_name
    value = KnowledgeValue[object].model_validate(payload)

    copied = value.model_copy()
    constructed = KnowledgeValue[object].model_construct(**value.__dict__)
    json_roundtrip = KnowledgeValue[object].model_validate_json(value.model_dump_json())
    pickle_roundtrip = pickle.loads(pickle.dumps(value))

    assert copied == value
    assert constructed == value
    assert json_roundtrip == value
    assert pickle_roundtrip == value
    for roundtrip in (copied, constructed, json_roundtrip, pickle_roundtrip):
        assert roundtrip.evidence_ids == ("EV-002", "EV-001")
        assert roundtrip.source_scope_ids == ("SOURCE-002", "SOURCE-001")


@pytest.mark.parametrize(
    "specialization_name,model_type,value",
    _GENERIC_SPECIALIZATIONS,
    ids=lambda value: str(value),
)
def test_valid_generic_serialization_and_pickle_roundtrips_are_preserved(
    specialization_name: str,
    model_type: type[KnowledgeValue[Any]],
    value: object,
) -> None:
    del specialization_name
    original = model_type.model_validate(
        {
            "knowledge_state": KnowledgeState.PRESENT,
            "value": value,
            "evidence_ids": ("EV-002", "EV-001"),
            "source_scope_ids": ("SOURCE-002", "SOURCE-001"),
        }
    )

    assert model_type.model_validate_json(original.model_dump_json()) == original
    pickle_roundtrip = pickle.loads(pickle.dumps(original))
    assert pickle_roundtrip == original
    assert pickle_roundtrip.__pydantic_fields_set__ == original.__pydantic_fields_set__


def test_exclude_unset_dump_parity_and_field_set_are_preserved() -> None:
    original = KnowledgeValue[str](
        knowledge_state=KnowledgeState.PRESENT,
        value="documented",
        evidence_ids=("EV-001",),
    )
    original_fields_set = set(original.__pydantic_fields_set__)
    expected_python = BaseModel.model_dump(
        original,
        mode="python",
        exclude_unset=True,
        round_trip=True,
    )
    expected_json = BaseModel.model_dump_json(
        original,
        exclude_unset=True,
        round_trip=True,
    )

    assert (
        original.model_dump(mode="python", exclude_unset=True, round_trip=True)
        == expected_python
    )
    assert original.model_dump_json(exclude_unset=True, round_trip=True) == expected_json
    assert original.__pydantic_fields_set__ == original_fields_set


@pytest.mark.parametrize("copy_method", ("model_copy", "copy"))
def test_copy_update_preserves_original_field_set_metadata(copy_method: str) -> None:
    original = KnowledgeValue[str](
        knowledge_state=KnowledgeState.PRESENT,
        value="documented",
        evidence_ids=("EV-001",),
    )
    copier = getattr(original, copy_method)

    if copy_method == "copy":
        with pytest.warns(PydanticDeprecatedSince20, match=r"copy.*deprecated"):
            copied = copier(update={"source_scope_ids": ("SOURCE-001",)})
    else:
        copied = copier(update={"source_scope_ids": ("SOURCE-001",)})

    assert copied.__pydantic_fields_set__ == (
        original.__pydantic_fields_set__ | {"source_scope_ids"}
    )


@pytest.mark.parametrize("field_name", ("evidence_ids", "source_scope_ids"))
@pytest.mark.parametrize(
    "specialization_name,model_type,value",
    _GENERIC_SPECIALIZATIONS,
    ids=lambda value: str(value),
)
def test_invalid_provenance_cannot_cross_pickle_restore(
    field_name: str,
    specialization_name: str,
    model_type: type[KnowledgeValue[Any]],
    value: object,
) -> None:
    del specialization_name
    invalid = _invalid_knowledge(field_name, model_type, value)
    target = object.__new__(model_type)

    with pytest.raises(ValidationError, match="unique and order-preserving"):
        target.__setstate__(
            {
                "format": "ntruth-knowledge-value-v1",
                "payload": invalid.__dict__,
                "fields_set": set(invalid.__pydantic_fields_set__),
            }
        )


@pytest.mark.parametrize("state_name,payload", _STATE_PAYLOADS, ids=lambda value: str(value))
@pytest.mark.parametrize("field_name", ("evidence_ids", "source_scope_ids"))
def test_duplicate_provenance_cannot_cross_pickle_restore_in_any_state(
    state_name: str,
    payload: dict[str, object],
    field_name: str,
) -> None:
    del state_name
    invalid = _invalid_state_knowledge(payload, field_name)

    with pytest.raises(ValidationError, match="unique and order-preserving"):
        object.__new__(type(invalid)).__setstate__(
            {
                "format": "ntruth-knowledge-value-v1",
                "payload": invalid.__dict__,
                "fields_set": set(invalid.__pydantic_fields_set__),
            }
        )


def test_pickle_restore_rejects_fields_set_without_required_knowledge_state() -> None:
    original = KnowledgeValue[str](
        knowledge_state=KnowledgeState.PRESENT,
        value="documented",
        evidence_ids=("EV-001",),
    )
    state = original.__getstate__()
    state["fields_set"] = {"value", "evidence_ids"}

    with pytest.raises(ValueError, match="unsupported KnowledgeValue pickle envelope"):
        object.__new__(type(original)).__setstate__(state)


@pytest.mark.parametrize(
    "state_name,payload",
    tuple(
        item
        for item in _STATE_PAYLOADS
        if item[0] in {"present", "conflicting", "unknown", "not-reported"}
    ),
    ids=lambda value: str(value),
)
def test_pickle_restore_rejects_fields_set_missing_non_default_state_fields(
    state_name: str,
    payload: dict[str, object],
) -> None:
    del state_name
    original = KnowledgeValue[object].model_validate(payload)
    state = original.__getstate__()
    state["fields_set"] = {"knowledge_state"}

    with pytest.raises(ValueError, match="unsupported KnowledgeValue pickle envelope"):
        object.__new__(type(original)).__setstate__(state)


def test_pickle_roundtrip_preserves_legitimate_sparse_default_field_set() -> None:
    original = KnowledgeValue[object](
        knowledge_state=KnowledgeState.NOT_REPORTED,
        source_scope_ids=("SOURCE-001",),
    )

    roundtrip = pickle.loads(pickle.dumps(original))

    assert roundtrip == original
    assert roundtrip.__pydantic_fields_set__ == {
        "knowledge_state",
        "source_scope_ids",
    }


@pytest.mark.parametrize("copy_method", ("model_copy", "copy"))
@pytest.mark.parametrize("deep", (False, True))
def test_valid_shallow_and_deep_copy_semantics_are_preserved(
    copy_method: str,
    deep: bool,
) -> None:
    original = KnowledgeValue[dict[str, list[str]]].model_validate(
        {
            "knowledge_state": KnowledgeState.PRESENT,
            "value": {"documented": ["value"]},
            "evidence_ids": ("EV-002", "EV-001"),
            "source_scope_ids": ("SOURCE-002", "SOURCE-001"),
        }
    )

    if copy_method == "copy":
        with pytest.warns(PydanticDeprecatedSince20, match=r"copy.*deprecated"):
            copied = original.copy(deep=deep)
    else:
        copied = original.model_copy(deep=deep)

    assert copied == original
    assert copied is not original
    assert copied.evidence_ids == ("EV-002", "EV-001")
    assert copied.source_scope_ids == ("SOURCE-002", "SOURCE-001")
    if deep:
        assert copied.value is not original.value
        assert copied.value is not None
        assert original.value is not None
        assert copied.value["documented"] is not original.value["documented"]
    else:
        assert copied.value is original.value


@pytest.mark.parametrize(
    "boundary",
    (
        "model_copy",
        "copy",
        "model_construct",
        "model_dump",
        "model_dump_json",
        "pickle",
        "pickle_load",
    ),
)
def test_boundary_revalidation_does_not_swallow_base_exception(
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
) -> None:
    value = KnowledgeValue[object].model_validate(_STATE_PAYLOADS[0][1])
    model_type = type(value)
    pickle_state = value.__getstate__()

    def interrupt_validation(*_args: object, **_kwargs: object) -> Any:
        raise _SentinelBaseException

    monkeypatch.setattr(model_type, "model_validate", interrupt_validation)

    with pytest.raises(_SentinelBaseException):
        if boundary == "model_copy":
            value.model_copy()
        elif boundary == "copy":
            with pytest.warns(PydanticDeprecatedSince20, match=r"copy.*deprecated"):
                value.copy()
        elif boundary == "model_construct":
            model_type.model_construct(**value.__dict__)
        elif boundary == "model_dump":
            value.model_dump(mode="python")
        elif boundary == "model_dump_json":
            value.model_dump_json()
        elif boundary == "pickle_load":
            object.__new__(model_type).__setstate__(pickle_state)
        else:
            pickle.dumps(value)
