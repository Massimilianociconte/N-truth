"""Generic nested-model regressions for KnowledgeValue serialization boundaries."""

from __future__ import annotations

import json
import pickle
from collections.abc import Callable, Mapping, Sequence
from copy import copy, deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum, Flag, IntFlag, StrEnum, auto
from ipaddress import IPv4Address
from pathlib import PurePosixPath
from typing import Annotated, Any, ClassVar, Literal, cast
from uuid import UUID

import pytest
from pydantic import AfterValidator, BaseModel, Field, ValidationError
from pydantic_core import PydanticSerializationError, core_schema

from ntruth.runtime_tree import ExactRuntimeTreeError
from ntruth.schemas.core import FrozenModel
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue


class _Payload(FrozenModel):
    label: str


class _PayloadSubclass(_Payload):
    application_note: str


class _AlternatePayload(FrozenModel):
    code: str


class _AliasPayload(FrozenModel):
    label: str = Field(alias="LABEL")


class _SlottedPayload(_Payload):
    __slots__ = ("determinability",)


class _PrivateSlottedPayload(_Payload):
    __slots__ = ("_determinability",)


class _SparsePayload(FrozenModel):
    label: str
    optional_note: str | None = None


class _OpaquePayload(FrozenModel):
    item: object


@dataclass(frozen=True)
class _OpaqueDataclassPayload:
    item: object


class _FloatPayload(FrozenModel):
    measurement: float


class _DecimalPayload(FrozenModel):
    measurement: Decimal


@dataclass(frozen=True)
class _DataclassPayload:
    label: str


@dataclass(frozen=True)
class _DefaultDataclassPayload:
    label: str
    note: str = "default"


@dataclass(frozen=True)
class _DerivedDataclassPayload:
    label: str
    derived_note: str = field(init=False, default="derived")


class _KnowledgeEnvelope(FrozenModel):
    knowledge: KnowledgeValue[_Payload]


class _OpaqueKnowledgeEnvelope(FrozenModel):
    knowledge: KnowledgeValue[object]


class _DataclassKnowledgeEnvelope(FrozenModel):
    knowledge: KnowledgeValue[_DataclassPayload]


class _AbortTraversal(BaseException):
    pass


class _Token(StrEnum):
    DOCUMENTED = "documented"


class _ListToken(Enum):
    DOCUMENTED = [1, 2]  # noqa: RUF012 - intentionally unhashable Enum value


class _Permission(Flag):
    READ = auto()
    WRITE = auto()


class _IntegerPermission(IntFlag):
    READ = 1
    WRITE = 2


class _ComparisonBomb:
    __slots__ = ()
    error: ClassVar[BaseException]

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source: object,
        handler: object,
    ) -> core_schema.CoreSchema:
        del source, handler
        return core_schema.no_info_after_validator_function(
            lambda value: cls(),
            core_schema.any_schema(),
        )

    def __eq__(self, other: object) -> bool:
        del other
        raise self.error

    def __ne__(self, other: object) -> bool:
        del other
        raise self.error


class _HostileStr(str):
    pass


class _HostileDecimal(Decimal):
    pass


class _HostileDate(date):
    pass


class _HostileDateTime(datetime):
    pass


class _HostileTime(time):
    pass


class _HostileUuid(UUID):
    pass


class _HostilePath(PurePosixPath):
    pass


class _HostileIp(IPv4Address):
    pass


_Shape = Literal["root", "list", "tuple", "mapping"]
_Mutation = Literal["undeclared", "private", "extra", "subclass", "model-construct"]
_Boundary = Callable[[KnowledgeValue[Any]], object]
_BASE_MODEL_CONSTRUCT = cast(Any, BaseModel.model_construct).__func__


def _wrap_payload(shape: _Shape, payload: _Payload) -> object:
    if shape == "root":
        return payload
    if shape == "list":
        return [payload]
    if shape == "tuple":
        return (payload,)
    return {"primary": payload}


def _model_type(shape: _Shape) -> type[KnowledgeValue[Any]]:
    if shape == "root":
        return cast(type[KnowledgeValue[Any]], KnowledgeValue[_Payload])
    if shape == "list":
        return cast(type[KnowledgeValue[Any]], KnowledgeValue[list[_Payload]])
    if shape == "tuple":
        return cast(type[KnowledgeValue[Any]], KnowledgeValue[tuple[_Payload, ...]])
    return cast(type[KnowledgeValue[Any]], KnowledgeValue[dict[str, _Payload]])


def _knowledge(shape: _Shape, payload: _Payload) -> KnowledgeValue[Any]:
    return _model_type(shape)(
        knowledge_state=KnowledgeState.PRESENT,
        value=_wrap_payload(shape, payload),
        evidence_ids=("EV-001",),
    )


def _hostile_payload(mutation: _Mutation) -> _Payload:
    if mutation == "subclass":
        return _PayloadSubclass(
            label="documented",
            application_note="must not cross the declared parent boundary",
        )
    if mutation == "model-construct":
        return cast(
            _Payload,
            _BASE_MODEL_CONSTRUCT(
                _Payload,
                _fields_set={"label"},
                label=7,
            ),
        )

    payload = _Payload(label="documented")
    if mutation == "undeclared":
        object.__getattribute__(payload, "__dict__")["undeclared"] = "hidden"
    elif mutation == "private":
        object.__setattr__(payload, "__pydantic_private__", {"_hidden": "secret"})
    else:
        object.__setattr__(payload, "__pydantic_extra__", {"hidden": "secret"})
    return payload


def _slotted_payload() -> _SlottedPayload:
    payload = _SlottedPayload(label="documented")
    object.__setattr__(payload, "determinability", "hidden")
    return payload


def _private_slotted_payload() -> _PrivateSlottedPayload:
    payload = _PrivateSlottedPayload(label="documented")
    object.__setattr__(payload, "_determinability", "hidden")
    return payload


def _payload_from_shape(value: object, shape: _Shape) -> _Payload:
    if shape == "root":
        return cast(_Payload, value)
    if shape == "list":
        return cast(list[_Payload], value)[0]
    if shape == "tuple":
        return cast(tuple[_Payload, ...], value)[0]
    return cast(dict[str, _Payload], value)["primary"]


def _dataclass_model_type(shape: _Shape) -> type[KnowledgeValue[Any]]:
    if shape == "root":
        return cast(type[KnowledgeValue[Any]], KnowledgeValue[_DataclassPayload])
    if shape == "list":
        return cast(
            type[KnowledgeValue[Any]],
            KnowledgeValue[list[_DataclassPayload]],
        )
    if shape == "tuple":
        return cast(
            type[KnowledgeValue[Any]],
            KnowledgeValue[tuple[_DataclassPayload, ...]],
        )
    return cast(
        type[KnowledgeValue[Any]],
        KnowledgeValue[dict[str, _DataclassPayload]],
    )


def _dataclass_knowledge(
    shape: _Shape,
    payload: _DataclassPayload,
) -> KnowledgeValue[Any]:
    return _dataclass_model_type(shape)(
        knowledge_state=KnowledgeState.PRESENT,
        value=_wrap_payload(shape, cast(_Payload, payload)),
        evidence_ids=("EV-001",),
    )


_DIRECT_BOUNDARIES: tuple[tuple[str, _Boundary], ...] = (
    ("model-dump", lambda value: value.model_dump(mode="python", round_trip=True)),
    ("model-dump-json", lambda value: value.model_dump_json(round_trip=True)),
    ("pickle", pickle.dumps),
)

_EXACT_BOUNDARIES: tuple[tuple[str, _Boundary], ...] = (
    *_DIRECT_BOUNDARIES,
    ("model-copy", lambda value: value.model_copy()),
)


@pytest.mark.parametrize("shape", ("root", "list", "tuple", "mapping"))
@pytest.mark.parametrize(
    "boundary_name,boundary",
    _DIRECT_BOUNDARIES,
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_valid_nested_models_cross_direct_dump_json_and_pickle_boundaries(
    shape: _Shape,
    boundary_name: str,
    boundary: _Boundary,
) -> None:
    original = _knowledge(shape, _Payload(label="documented"))

    result = boundary(original)

    if boundary_name == "model-dump":
        assert (
            cast(dict[str, object], result)["value"]
            == {
                "root": {"label": "documented"},
                "list": [{"label": "documented"}],
                "tuple": ({"label": "documented"},),
                "mapping": {"primary": {"label": "documented"}},
            }[shape]
        )
    elif boundary_name == "model-dump-json":
        assert (
            json.loads(cast(str, result))["value"]
            == {
                "root": {"label": "documented"},
                "list": [{"label": "documented"}],
                "tuple": [{"label": "documented"}],
                "mapping": {"primary": {"label": "documented"}},
            }[shape]
        )
    else:
        restored = pickle.loads(cast(bytes, result))
        assert restored == original
        assert type(_payload_from_shape(restored.value, shape)) is _Payload


@pytest.mark.parametrize("shape", ("root", "list", "tuple", "mapping"))
@pytest.mark.parametrize(
    "boundary_name,boundary",
    _DIRECT_BOUNDARIES,
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_valid_dataclass_payloads_cross_direct_serialization_boundaries(
    shape: _Shape,
    boundary_name: str,
    boundary: _Boundary,
) -> None:
    original = _dataclass_knowledge(shape, _DataclassPayload(label="documented"))

    result = boundary(original)

    if boundary_name == "model-dump":
        assert (
            cast(dict[str, object], result)["value"]
            == {
                "root": {"label": "documented"},
                "list": [{"label": "documented"}],
                "tuple": ({"label": "documented"},),
                "mapping": {"primary": {"label": "documented"}},
            }[shape]
        )
    elif boundary_name == "model-dump-json":
        assert (
            json.loads(cast(str, result))["value"]
            == {
                "root": {"label": "documented"},
                "list": [{"label": "documented"}],
                "tuple": [{"label": "documented"}],
                "mapping": {"primary": {"label": "documented"}},
            }[shape]
        )
    else:
        restored = pickle.loads(cast(bytes, result))
        restored_payload = _payload_from_shape(restored.value, shape)
        assert type(restored_payload) is _DataclassPayload
        assert object.__getattribute__(restored_payload, "__dict__") == {"label": "documented"}


@pytest.mark.parametrize(
    "boundary_name,boundary",
    (
        *_DIRECT_BOUNDARIES,
        ("model-copy", lambda value: value.model_copy()),
        ("copy", copy),
        ("deepcopy", deepcopy),
    ),
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_opaque_dataclass_init_false_class_default_crosses_boundaries(
    boundary_name: str,
    boundary: _Boundary,
) -> None:
    payload = _DerivedDataclassPayload(label="documented")
    assert object.__getattribute__(payload, "__dict__") == {"label": "documented"}
    assert payload.derived_note == "derived"
    original = KnowledgeValue[object](
        knowledge_state=KnowledgeState.PRESENT,
        value=payload,
        evidence_ids=("EV-001",),
    )

    result = boundary(original)

    if boundary_name == "pickle":
        restored = pickle.loads(cast(bytes, result))
        assert isinstance(restored.value, _DerivedDataclassPayload)
        assert object.__getattribute__(restored.value, "__dict__") == {"label": "documented"}
        assert restored.value.derived_note == "derived"


@pytest.mark.parametrize(
    "boundary_name,boundary",
    (
        *_DIRECT_BOUNDARIES,
        ("model-copy", lambda value: value.model_copy()),
        ("copy", copy),
        ("deepcopy", deepcopy),
    ),
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_opaque_dataclass_init_false_does_not_hide_missing_stored_fields(
    boundary_name: str,
    boundary: _Boundary,
) -> None:
    del boundary_name
    payload = _DerivedDataclassPayload(label="documented")
    state = object.__getattribute__(payload, "__dict__")
    assert state.pop("label") == "documented"
    original = KnowledgeValue[object](
        knowledge_state=KnowledgeState.PRESENT,
        value=payload,
        evidence_ids=("EV-001",),
    )

    with pytest.raises(ExactRuntimeTreeError, match=r"missing dataclass state"):
        boundary(original)


@pytest.mark.parametrize("shape", ("root", "list", "tuple", "mapping"))
@pytest.mark.parametrize(
    "boundary_name,boundary",
    _DIRECT_BOUNDARIES,
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_mutated_dataclass_payloads_cannot_cross_serialization_boundaries(
    shape: _Shape,
    boundary_name: str,
    boundary: _Boundary,
) -> None:
    del boundary_name
    hostile = _dataclass_knowledge(shape, _DataclassPayload(label="documented"))
    stored = _payload_from_shape(hostile.value, shape)
    assert type(stored) is _DataclassPayload
    object.__setattr__(stored, "undeclared", "hidden")
    assert object.__getattribute__(stored, "__dict__")["undeclared"] == "hidden"

    with pytest.raises(ExactRuntimeTreeError, match=r"dataclass state"):
        boundary(hostile)


@pytest.mark.parametrize("deep", (False, True))
def test_copy_boundaries_reject_mutated_dataclass_payloads(deep: bool) -> None:
    hostile = _dataclass_knowledge("root", _DataclassPayload(label="documented"))
    stored = _payload_from_shape(hostile.value, "root")
    assert type(stored) is _DataclassPayload
    object.__setattr__(stored, "undeclared", "hidden")
    assert object.__getattribute__(stored, "__dict__")["undeclared"] == "hidden"

    with pytest.raises(ExactRuntimeTreeError, match=r"dataclass state"):
        hostile.model_copy(deep=deep)


@pytest.mark.parametrize("deep", (False, True))
@pytest.mark.parametrize("payload_kind", ("model", "dataclass"))
def test_copy_with_benign_update_rejects_hostile_nested_state(
    deep: bool,
    payload_kind: str,
) -> None:
    if payload_kind == "model":
        hostile: KnowledgeValue[Any] = _knowledge("root", _Payload(label="documented"))
    else:
        hostile = _dataclass_knowledge("root", _DataclassPayload(label="documented"))
    stored = _payload_from_shape(hostile.value, "root")
    object.__getattribute__(stored, "__dict__")["undeclared"] = "hidden"
    assert object.__getattribute__(stored, "__dict__")["undeclared"] == "hidden"

    with pytest.raises(ExactRuntimeTreeError, match=r"non-canonical runtime tree"):
        hostile.model_copy(
            update={"source_scope_ids": ("SOURCE-001",)},
            deep=deep,
        )


@pytest.mark.parametrize("deep", (False, True))
@pytest.mark.parametrize("nested", (False, True), ids=("root", "nested"))
@pytest.mark.parametrize("payload_kind", ("model", "dataclass"))
def test_copy_rejects_a_hostile_value_supplied_by_update(
    deep: bool,
    nested: bool,
    payload_kind: str,
) -> None:
    if payload_kind == "model":
        payload: object = _Payload(label="updated")
        model_type = cast(
            type[KnowledgeValue[Any]],
            KnowledgeValue[list[_Payload]] if nested else KnowledgeValue[_Payload],
        )
        canonical_payload: object = _Payload(label="documented")
    else:
        payload = _DataclassPayload(label="updated")
        model_type = cast(
            type[KnowledgeValue[Any]],
            KnowledgeValue[list[_DataclassPayload]]
            if nested
            else KnowledgeValue[_DataclassPayload],
        )
        canonical_payload = _DataclassPayload(label="documented")
    object.__getattribute__(payload, "__dict__")["undeclared"] = "hidden"
    valid = model_type(
        knowledge_state=KnowledgeState.PRESENT,
        value=[canonical_payload] if nested else canonical_payload,
        evidence_ids=("EV-001",),
    )

    with pytest.raises(ExactRuntimeTreeError, match=r"non-canonical runtime tree"):
        valid.model_copy(
            update={"value": [payload] if nested else payload},
            deep=deep,
        )


def test_pickle_restore_rejects_mutated_dataclass_payload() -> None:
    valid = _dataclass_knowledge("root", _DataclassPayload(label="documented"))
    state = valid.__getstate__()
    hostile = _DataclassPayload(label="documented")
    object.__setattr__(hostile, "undeclared", "hidden")
    state["payload"] = {**state["payload"], "value": hostile}

    with pytest.raises(ExactRuntimeTreeError, match=r"dataclass state"):
        object.__new__(type(valid)).__setstate__(state)


@pytest.mark.parametrize("nested", (False, True), ids=("root", "nested"))
@pytest.mark.parametrize(
    "boundary_name,boundary",
    _DIRECT_BOUNDARIES,
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_missing_default_dataclass_state_cannot_cross_serialization_boundaries(
    nested: bool,
    boundary_name: str,
    boundary: _Boundary,
) -> None:
    del boundary_name
    model_type = cast(
        type[KnowledgeValue[Any]],
        KnowledgeValue[list[_DefaultDataclassPayload]]
        if nested
        else KnowledgeValue[_DefaultDataclassPayload],
    )
    payload: object = (
        [_DefaultDataclassPayload(label="documented")]
        if nested
        else _DefaultDataclassPayload(label="documented")
    )
    hostile = model_type(
        knowledge_state=KnowledgeState.PRESENT,
        value=payload,
        evidence_ids=("EV-001",),
    )
    if nested:
        assert isinstance(hostile.value, list)
        stored = hostile.value[0]
    else:
        stored = hostile.value
    assert isinstance(stored, _DefaultDataclassPayload)
    state = object.__getattribute__(stored, "__dict__")
    assert state.pop("note") == "default"
    assert "note" not in state
    assert stored.note == "default"

    with pytest.raises(ExactRuntimeTreeError, match=r"missing dataclass state"):
        boundary(cast(KnowledgeValue[Any], hostile))


@pytest.mark.parametrize("deep", (False, True))
def test_copy_rejects_missing_default_dataclass_state(deep: bool) -> None:
    hostile = KnowledgeValue[_DefaultDataclassPayload](
        knowledge_state=KnowledgeState.PRESENT,
        value=_DefaultDataclassPayload(label="documented"),
        evidence_ids=("EV-001",),
    )
    assert hostile.value is not None
    state = object.__getattribute__(hostile.value, "__dict__")
    assert state.pop("note") == "default"

    with pytest.raises(ExactRuntimeTreeError, match=r"missing dataclass state"):
        hostile.model_copy(deep=deep)


def test_pickle_restore_rejects_missing_default_dataclass_state() -> None:
    valid = KnowledgeValue[_DefaultDataclassPayload](
        knowledge_state=KnowledgeState.PRESENT,
        value=_DefaultDataclassPayload(label="documented"),
        evidence_ids=("EV-001",),
    )
    state = valid.__getstate__()
    hostile = _DefaultDataclassPayload(label="documented")
    assert object.__getattribute__(hostile, "__dict__").pop("note") == "default"
    state["payload"] = {**state["payload"], "value": hostile}

    with pytest.raises(ExactRuntimeTreeError, match=r"missing dataclass state"):
        object.__new__(type(valid)).__setstate__(state)


@pytest.mark.parametrize("mutation", ("missing-default", "surplus"))
def test_pickle_restore_requires_the_complete_exact_payload_keyset(mutation: str) -> None:
    valid = KnowledgeValue[str](
        knowledge_state=KnowledgeState.PRESENT,
        value="documented",
        evidence_ids=("EV-001",),
    )
    state = valid.__getstate__()
    payload = dict(state["payload"])
    if mutation == "missing-default":
        assert payload.pop("schema_version") == "8.0.0"
        state["fields_set"].add("schema_version")
    else:
        payload["undeclared"] = "hidden"
    state["payload"] = payload

    with pytest.raises(TypeError, match=r"payload field|undeclared|missing"):
        object.__new__(type(valid)).__setstate__(state)


@pytest.mark.parametrize(
    "model_type",
    (KnowledgeValue, KnowledgeValue[object]),
    ids=("unbound", "object"),
)
@pytest.mark.parametrize(
    "boundary_name,boundary",
    _DIRECT_BOUNDARIES,
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_opaque_specializations_preserve_canonical_nested_models(
    model_type: type[KnowledgeValue[Any]],
    boundary_name: str,
    boundary: _Boundary,
) -> None:
    original = model_type(
        knowledge_state=KnowledgeState.PRESENT,
        value=_Payload(label="documented"),
        evidence_ids=("EV-001",),
    )

    result = boundary(original)

    if boundary_name == "model-dump":
        assert cast(dict[str, object], result)["value"] == {"label": "documented"}
    elif boundary_name == "model-dump-json":
        assert json.loads(cast(str, result))["value"] == {"label": "documented"}
    else:
        restored = pickle.loads(cast(bytes, result))
        assert type(restored) is model_type
        assert type(restored.value) is _Payload
        assert restored == original


@pytest.mark.parametrize("shape", ("list", "tuple", "mapping"))
@pytest.mark.parametrize(
    "boundary_name,boundary",
    _DIRECT_BOUNDARIES,
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_nested_object_specializations_preserve_canonical_models(
    shape: _Shape,
    boundary_name: str,
    boundary: _Boundary,
) -> None:
    model_types: dict[str, type[KnowledgeValue[Any]]] = {
        "list": cast(type[KnowledgeValue[Any]], KnowledgeValue[list[object]]),
        "tuple": cast(type[KnowledgeValue[Any]], KnowledgeValue[tuple[object, ...]]),
        "mapping": cast(type[KnowledgeValue[Any]], KnowledgeValue[dict[str, object]]),
    }
    original = model_types[shape](
        knowledge_state=KnowledgeState.PRESENT,
        value=_wrap_payload(shape, _Payload(label="documented")),
        evidence_ids=("EV-001",),
    )

    result = boundary(original)

    if boundary_name == "pickle":
        restored = pickle.loads(cast(bytes, result))
        assert type(_payload_from_shape(restored.value, shape)) is _Payload


@pytest.mark.parametrize("shape", ("list", "tuple", "mapping"))
@pytest.mark.parametrize(
    "boundary_name,boundary",
    _DIRECT_BOUNDARIES,
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_nested_object_specializations_reject_hostile_models(
    shape: _Shape,
    boundary_name: str,
    boundary: _Boundary,
) -> None:
    del boundary_name
    model_types: dict[str, type[KnowledgeValue[Any]]] = {
        "list": cast(type[KnowledgeValue[Any]], KnowledgeValue[list[object]]),
        "tuple": cast(type[KnowledgeValue[Any]], KnowledgeValue[tuple[object, ...]]),
        "mapping": cast(type[KnowledgeValue[Any]], KnowledgeValue[dict[str, object]]),
    }
    hostile = model_types[shape](
        knowledge_state=KnowledgeState.PRESENT,
        value=_wrap_payload(shape, _Payload(label="documented")),
        evidence_ids=("EV-001",),
    )
    stored = _payload_from_shape(hostile.value, shape)
    object.__getattribute__(stored, "__dict__")["undeclared"] = "hidden"

    with pytest.raises(ExactRuntimeTreeError, match=r"non-canonical runtime tree"):
        boundary(hostile)


@pytest.mark.parametrize(
    "boundary_name,boundary",
    _DIRECT_BOUNDARIES,
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_mixed_typed_and_opaque_positions_preserve_each_declared_contract(
    boundary_name: str,
    boundary: _Boundary,
) -> None:
    original = KnowledgeValue[tuple[_Payload, object]](
        knowledge_state=KnowledgeState.PRESENT,
        value=(
            _Payload(label="typed"),
            _Payload(label="opaque"),
        ),
        evidence_ids=("EV-001",),
    )

    result = boundary(original)

    if boundary_name == "pickle":
        restored = pickle.loads(cast(bytes, result))
        assert restored.value is not None
        assert type(restored.value[0]) is _Payload
        assert type(restored.value[1]) is _Payload


@pytest.mark.parametrize("nested", (False, True), ids=("tuple", "mapping"))
@pytest.mark.parametrize(
    "boundary_name,boundary",
    _DIRECT_BOUNDARIES,
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_mixed_typed_and_opaque_positions_reject_typed_model_subclasses(
    nested: bool,
    boundary_name: str,
    boundary: _Boundary,
) -> None:
    del boundary_name
    hostile_typed = _PayloadSubclass(
        label="typed",
        application_note="must not cross the parent position",
    )
    if nested:
        hostile: KnowledgeValue[Any] = KnowledgeValue[dict[str, tuple[_Payload, object]]](
            knowledge_state=KnowledgeState.PRESENT,
            value={"primary": (hostile_typed, "opaque")},
            evidence_ids=("EV-001",),
        )
    else:
        hostile = KnowledgeValue[tuple[_Payload, object]](
            knowledge_state=KnowledgeState.PRESENT,
            value=(hostile_typed, "opaque"),
            evidence_ids=("EV-001",),
        )

    with pytest.raises(ExactRuntimeTreeError, match=r"runtime type mismatch"):
        boundary(hostile)


@pytest.mark.parametrize("shape", ("list", "tuple", "mapping"))
@pytest.mark.parametrize(
    "boundary_name,boundary",
    (*_DIRECT_BOUNDARIES, ("model-copy", lambda value: value.model_copy())),
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_union_dispatch_tries_the_matching_opaque_container_branch(
    shape: _Shape,
    boundary_name: str,
    boundary: _Boundary,
) -> None:
    model_types: dict[str, type[KnowledgeValue[Any]]] = {
        "list": cast(
            type[KnowledgeValue[Any]],
            KnowledgeValue[list[_Payload] | list[object]],
        ),
        "tuple": cast(
            type[KnowledgeValue[Any]],
            KnowledgeValue[tuple[_Payload, ...] | tuple[object, ...]],
        ),
        "mapping": cast(
            type[KnowledgeValue[Any]],
            KnowledgeValue[dict[str, _Payload] | dict[str, object]],
        ),
    }
    original = model_types[shape](
        knowledge_state=KnowledgeState.PRESENT,
        value=_wrap_payload(shape, cast(_Payload, _AlternatePayload(code="ALT-001"))),
        evidence_ids=("EV-001",),
    )

    result = boundary(original)

    if boundary_name in {"pickle", "model-copy"}:
        restored = pickle.loads(cast(bytes, result)) if boundary_name == "pickle" else result
        assert type(_payload_from_shape(cast(Any, restored).value, shape)) is _AlternatePayload


@pytest.mark.parametrize(
    "annotation,value_factory,expected_container",
    (
        (
            Mapping[str, object],
            lambda: {"primary": _AlternatePayload(code="ALT-001")},
            dict,
        ),
        (
            Sequence[object],
            lambda: [_AlternatePayload(code="ALT-001")],
            list,
        ),
        (
            Sequence[object],
            lambda: (_AlternatePayload(code="ALT-001"),),
            tuple,
        ),
    ),
    ids=("mapping", "list-sequence", "tuple-sequence"),
)
@pytest.mark.parametrize(
    "boundary_name,boundary",
    _EXACT_BOUNDARIES,
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_opaque_abstract_containers_preserve_nested_models(
    annotation: object,
    value_factory: Callable[[], object],
    expected_container: type[object],
    boundary_name: str,
    boundary: _Boundary,
) -> None:
    model_type = cast(
        type[KnowledgeValue[Any]],
        KnowledgeValue.__class_getitem__(cast(Any, annotation)),
    )
    original = model_type(
        knowledge_state=KnowledgeState.PRESENT,
        value=value_factory(),
        evidence_ids=("EV-001",),
    )

    result = boundary(original)

    if boundary_name in {"pickle", "model-copy"}:
        restored = pickle.loads(cast(bytes, result)) if boundary_name == "pickle" else result
        assert type(cast(Any, restored).value) is expected_container
        nested = (
            cast(Any, restored).value["primary"]
            if expected_container is dict
            else cast(Any, restored).value[0]
        )
        assert type(nested) is _AlternatePayload


@pytest.mark.parametrize(
    "annotation,value_factory",
    (
        (
            Mapping[str, object],
            lambda: {"primary": _hostile_payload("undeclared")},
        ),
        (Sequence[object], lambda: [_hostile_payload("undeclared")]),
    ),
    ids=("mapping", "sequence"),
)
@pytest.mark.parametrize(
    "boundary_name,boundary",
    _EXACT_BOUNDARIES,
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_opaque_abstract_containers_reject_hostile_nested_models(
    annotation: object,
    value_factory: Callable[[], object],
    boundary_name: str,
    boundary: _Boundary,
) -> None:
    del boundary_name
    model_type = cast(
        type[KnowledgeValue[Any]],
        KnowledgeValue.__class_getitem__(cast(Any, annotation)),
    )
    hostile = model_type(
        knowledge_state=KnowledgeState.PRESENT,
        value=value_factory(),
        evidence_ids=("EV-001",),
    )

    with pytest.raises(ExactRuntimeTreeError, match=r"non-canonical runtime tree"):
        boundary(hostile)


def _reject_typed_union_arm(value: _Payload) -> _Payload:
    del value
    raise ValueError("typed arm rejected")


@pytest.mark.parametrize(
    "annotation,value_factory",
    (
        (
            Annotated[list[_Payload], Field(min_length=2)] | list[object],
            lambda: [_Payload(label="documented")],
        ),
        (
            Annotated[_Payload, AfterValidator(_reject_typed_union_arm)] | object,
            lambda: _Payload(label="documented"),
        ),
    ),
    ids=("field-constraint", "after-validator"),
)
@pytest.mark.parametrize(
    "boundary_name,boundary",
    _EXACT_BOUNDARIES,
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_union_dispatch_validates_annotated_constraints_before_selecting_an_arm(
    annotation: object,
    value_factory: Callable[[], object],
    boundary_name: str,
    boundary: _Boundary,
) -> None:
    model_type = cast(
        type[KnowledgeValue[Any]],
        KnowledgeValue.__class_getitem__(cast(Any, annotation)),
    )
    original = model_type(
        knowledge_state=KnowledgeState.PRESENT,
        value=value_factory(),
        evidence_ids=("EV-001",),
    )

    result = boundary(original)

    if boundary_name in {"pickle", "model-copy"}:
        restored = pickle.loads(cast(bytes, result)) if boundary_name == "pickle" else result
        nested = (
            cast(Any, restored).value[0]
            if isinstance(cast(Any, restored).value, list)
            else cast(Any, restored).value
        )
        assert type(nested) is _Payload


@pytest.mark.parametrize(
    "boundary_name,boundary",
    _EXACT_BOUNDARIES,
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_typed_aliased_model_uses_its_canonical_validation_alias(
    boundary_name: str,
    boundary: _Boundary,
) -> None:
    original = KnowledgeValue[_AliasPayload](
        knowledge_state=KnowledgeState.PRESENT,
        value=_AliasPayload(LABEL="documented"),
        evidence_ids=("EV-001",),
    )

    result = boundary(original)

    if boundary_name in {"pickle", "model-copy"}:
        restored = pickle.loads(cast(bytes, result)) if boundary_name == "pickle" else result
        assert type(cast(Any, restored).value) is _AliasPayload
        assert cast(Any, restored).value.label == "documented"


@pytest.mark.parametrize(
    "boundary_name,boundary",
    _EXACT_BOUNDARIES,
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_hashable_model_mapping_keys_still_reject_hostile_state(
    boundary_name: str,
    boundary: _Boundary,
) -> None:
    del boundary_name
    hostile_key = _Payload(label="documented")
    object.__getattribute__(hostile_key, "__dict__")["undeclared"] = "hidden"
    hostile = KnowledgeValue[dict[object, str]](
        knowledge_state=KnowledgeState.PRESENT,
        value={hostile_key: "retained"},
        evidence_ids=("EV-001",),
    )

    with pytest.raises(ExactRuntimeTreeError, match=r"non-canonical runtime tree"):
        boundary(hostile)


@pytest.mark.parametrize(
    "payload_type",
    (_OpaquePayload, _OpaqueDataclassPayload),
    ids=("model", "dataclass"),
)
@pytest.mark.parametrize(
    "boundary_name,boundary",
    _DIRECT_BOUNDARIES,
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_typed_holder_preserves_a_model_in_an_opaque_declared_field(
    payload_type: type[_OpaquePayload] | type[_OpaqueDataclassPayload],
    boundary_name: str,
    boundary: _Boundary,
) -> None:
    model_type = cast(
        type[KnowledgeValue[Any]],
        KnowledgeValue.__class_getitem__(payload_type),
    )
    original = model_type(
        knowledge_state=KnowledgeState.PRESENT,
        value=payload_type(item=_Payload(label="documented")),
        evidence_ids=("EV-001",),
    )

    result = boundary(original)

    if boundary_name == "pickle":
        restored = pickle.loads(cast(bytes, result))
        assert isinstance(restored.value, payload_type)
        assert type(restored.value.item) is _Payload


@pytest.mark.parametrize(
    "enum_type",
    (_Permission, _IntegerPermission),
    ids=("flag", "int-flag"),
)
@pytest.mark.parametrize(
    "typed",
    (True, False),
    ids=("typed", "object"),
)
@pytest.mark.parametrize(
    "boundary_name,boundary",
    _DIRECT_BOUNDARIES,
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_canonical_composite_flags_cross_serialization_boundaries(
    enum_type: type[_Permission] | type[_IntegerPermission],
    typed: bool,
    boundary_name: str,
    boundary: _Boundary,
) -> None:
    composite = enum_type(3)
    model_type = cast(
        type[KnowledgeValue[Any]],
        KnowledgeValue.__class_getitem__(enum_type if typed else object),
    )
    original = model_type(
        knowledge_state=KnowledgeState.PRESENT,
        value=composite,
        evidence_ids=("EV-001",),
    )

    result = boundary(original)

    if boundary_name == "pickle":
        restored = pickle.loads(cast(bytes, result))
        assert restored.value is composite


@pytest.mark.parametrize(
    "model_type",
    (KnowledgeValue[_ListToken], KnowledgeValue[object]),
    ids=("typed", "object"),
)
@pytest.mark.parametrize(
    "boundary",
    (
        lambda value: value.model_dump(mode="python", round_trip=True),
        lambda value: value.model_dump_json(round_trip=True),
        pickle.dumps,
        lambda value: value.model_copy(),
        copy,
        deepcopy,
    ),
    ids=("model-dump", "model-dump-json", "pickle", "model-copy", "copy", "deepcopy"),
)
def test_canonical_enum_with_an_unhashable_value_crosses_boundaries(
    model_type: type[KnowledgeValue[Any]],
    boundary: _Boundary,
) -> None:
    original = model_type(
        knowledge_state=KnowledgeState.PRESENT,
        value=_ListToken.DOCUMENTED,
        evidence_ids=("EV-001",),
    )

    result = boundary(original)

    if isinstance(result, bytes):
        restored = pickle.loads(result)
        assert restored.value is _ListToken.DOCUMENTED


@pytest.mark.parametrize(
    "model_type",
    (KnowledgeValue, KnowledgeValue[object]),
    ids=("unbound", "object"),
)
@pytest.mark.parametrize(
    "boundary_name,boundary",
    _DIRECT_BOUNDARIES,
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_opaque_specializations_reject_public_slotted_nested_model_state(
    model_type: type[KnowledgeValue[Any]],
    boundary_name: str,
    boundary: _Boundary,
) -> None:
    del boundary_name
    hostile = model_type(
        knowledge_state=KnowledgeState.PRESENT,
        value=_slotted_payload(),
        evidence_ids=("EV-001",),
    )

    with pytest.raises(ExactRuntimeTreeError, match=r"public slotted model state"):
        boundary(hostile)


@pytest.mark.parametrize(
    "model_type",
    (KnowledgeValue, KnowledgeValue[object]),
    ids=("unbound", "object"),
)
def test_opaque_pickle_restore_rejects_public_slotted_nested_model_state(
    model_type: type[KnowledgeValue[Any]],
) -> None:
    valid = model_type(
        knowledge_state=KnowledgeState.PRESENT,
        value=_Payload(label="documented"),
        evidence_ids=("EV-001",),
    )
    state = valid.__getstate__()
    state["payload"] = {**state["payload"], "value": _slotted_payload()}

    with pytest.raises(ExactRuntimeTreeError, match=r"public slotted model state"):
        object.__new__(type(valid)).__setstate__(state)


def test_parent_serialization_rejects_public_slotted_opaque_model_state() -> None:
    knowledge = KnowledgeValue[object](
        knowledge_state=KnowledgeState.PRESENT,
        value=_slotted_payload(),
        evidence_ids=("EV-001",),
    )
    envelope = _BASE_MODEL_CONSTRUCT(_OpaqueKnowledgeEnvelope, knowledge=knowledge)

    with pytest.raises(PydanticSerializationError, match=r"public slotted model state"):
        BaseModel.model_dump(envelope, mode="python", round_trip=True)


@pytest.mark.parametrize(
    "model_type",
    (KnowledgeValue, KnowledgeValue[object]),
    ids=("unbound", "object"),
)
@pytest.mark.parametrize(
    "boundary_name,boundary",
    _DIRECT_BOUNDARIES,
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_opaque_specializations_reject_private_slotted_model_state(
    model_type: type[KnowledgeValue[Any]],
    boundary_name: str,
    boundary: _Boundary,
) -> None:
    del boundary_name
    hostile = model_type(
        knowledge_state=KnowledgeState.PRESENT,
        value=_private_slotted_payload(),
        evidence_ids=("EV-001",),
    )

    with pytest.raises(ExactRuntimeTreeError, match=r"slotted model state"):
        boundary(hostile)


def test_parent_and_restore_reject_private_slotted_opaque_model_state() -> None:
    valid = KnowledgeValue[object](
        knowledge_state=KnowledgeState.PRESENT,
        value=_Payload(label="documented"),
        evidence_ids=("EV-001",),
    )
    state = valid.__getstate__()
    state["payload"] = {**state["payload"], "value": _private_slotted_payload()}
    with pytest.raises(ExactRuntimeTreeError, match=r"slotted model state"):
        object.__new__(type(valid)).__setstate__(state)

    hostile = KnowledgeValue[object](
        knowledge_state=KnowledgeState.PRESENT,
        value=_private_slotted_payload(),
        evidence_ids=("EV-001",),
    )
    envelope = _BASE_MODEL_CONSTRUCT(_OpaqueKnowledgeEnvelope, knowledge=hostile)
    with pytest.raises(PydanticSerializationError, match=r"slotted model state"):
        BaseModel.model_dump(envelope, mode="python", round_trip=True)


@pytest.mark.parametrize(
    "model_type",
    (KnowledgeValue[_Token], KnowledgeValue[object]),
    ids=("typed", "object"),
)
@pytest.mark.parametrize(
    "boundary_name,boundary",
    _DIRECT_BOUNDARIES,
    ids=lambda value: value if isinstance(value, str) else None,
)
@pytest.mark.parametrize(
    "state_key",
    ("determinability", "_determinability", 7),
    ids=("public", "private", "non-string"),
)
def test_mutated_enum_runtime_state_cannot_cross_serialization_boundaries(
    model_type: type[KnowledgeValue[Any]],
    boundary_name: str,
    boundary: _Boundary,
    state_key: object,
) -> None:
    del boundary_name
    token_state = object.__getattribute__(_Token.DOCUMENTED, "__dict__")
    token_state[state_key] = "hidden"
    try:
        hostile = model_type(
            knowledge_state=KnowledgeState.PRESENT,
            value=_Token.DOCUMENTED,
            evidence_ids=("EV-001",),
        )

        with pytest.raises(ExactRuntimeTreeError, match=r"enum state"):
            boundary(hostile)
    finally:
        del token_state[state_key]


@pytest.mark.parametrize(
    "model_type",
    (KnowledgeValue, KnowledgeValue[object]),
    ids=("unbound", "object"),
)
@pytest.mark.parametrize(
    "boundary_name,boundary",
    _DIRECT_BOUNDARIES,
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_opaque_builtin_scalar_subclass_cannot_cross_serialization_boundaries(
    model_type: type[KnowledgeValue[Any]],
    boundary_name: str,
    boundary: _Boundary,
) -> None:
    del boundary_name
    hostile_value = _HostileStr("documented")
    object.__setattr__(hostile_value, "determinability", "hidden")
    hostile = model_type(
        knowledge_state=KnowledgeState.PRESENT,
        value=hostile_value,
        evidence_ids=("EV-001",),
    )

    with pytest.raises(ExactRuntimeTreeError, match=r"scalar runtime type"):
        boundary(hostile)


@pytest.mark.parametrize(
    "model_type",
    (KnowledgeValue, KnowledgeValue[object]),
    ids=("unbound", "object"),
)
@pytest.mark.parametrize("nested", (False, True), ids=("root", "nested"))
@pytest.mark.parametrize(
    "boundary_name,boundary",
    _DIRECT_BOUNDARIES,
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_opaque_decimal_subclass_cannot_cross_serialization_boundaries(
    model_type: type[KnowledgeValue[Any]],
    nested: bool,
    boundary_name: str,
    boundary: _Boundary,
) -> None:
    del boundary_name
    hostile_value = _HostileDecimal("1.25")
    object.__setattr__(hostile_value, "determinability", "hidden")
    hostile = model_type(
        knowledge_state=KnowledgeState.PRESENT,
        value={"primary": hostile_value} if nested else hostile_value,
        evidence_ids=("EV-001",),
    )

    with pytest.raises(ExactRuntimeTreeError, match=r"scalar runtime type"):
        boundary(hostile)


@pytest.mark.parametrize(
    "model_type",
    (KnowledgeValue, KnowledgeValue[object]),
    ids=("unbound", "object"),
)
@pytest.mark.parametrize(
    "boundary_name,boundary",
    _DIRECT_BOUNDARIES,
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_exact_decimal_values_remain_serializable(
    model_type: type[KnowledgeValue[Any]],
    boundary_name: str,
    boundary: _Boundary,
) -> None:
    original = model_type(
        knowledge_state=KnowledgeState.PRESENT,
        value=Decimal("1.25"),
        evidence_ids=("EV-001",),
    )

    result = boundary(original)

    if boundary_name == "pickle":
        assert type(pickle.loads(cast(bytes, result)).value) is Decimal


@pytest.mark.parametrize(
    "hostile_value",
    (
        _HostileDate(2026, 8, 11),
        _HostileDateTime(2026, 8, 11, 12, 30),
        _HostileTime(12, 30),
        _HostileUuid("12345678-1234-5678-1234-567812345678"),
        _HostilePath("reports", "result.json"),
    ),
    ids=("date", "datetime", "time", "uuid", "path"),
)
@pytest.mark.parametrize(
    "boundary_name,boundary",
    _DIRECT_BOUNDARIES,
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_other_standard_scalar_subclasses_cannot_cross_opaque_boundaries(
    hostile_value: object,
    boundary_name: str,
    boundary: _Boundary,
) -> None:
    del boundary_name
    object.__setattr__(hostile_value, "determinability", "hidden")
    hostile = KnowledgeValue[object](
        knowledge_state=KnowledgeState.PRESENT,
        value=hostile_value,
        evidence_ids=("EV-001",),
    )

    with pytest.raises(ExactRuntimeTreeError, match=r"scalar runtime type"):
        boundary(hostile)


@pytest.mark.parametrize("nested", (False, True), ids=("root", "nested"))
@pytest.mark.parametrize(
    "boundary_name,boundary",
    _DIRECT_BOUNDARIES,
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_opaque_ip_subclass_state_cannot_cross_serialization_boundaries(
    nested: bool,
    boundary_name: str,
    boundary: _Boundary,
) -> None:
    del boundary_name
    hostile_value = _HostileIp("192.0.2.1")
    object.__setattr__(hostile_value, "determinability", "hidden")
    hostile = KnowledgeValue[object](
        knowledge_state=KnowledgeState.PRESENT,
        value=[hostile_value] if nested else hostile_value,
        evidence_ids=("EV-001",),
    )

    with pytest.raises(ExactRuntimeTreeError, match=r"opaque runtime state"):
        boundary(hostile)


@pytest.mark.parametrize(
    "boundary_name,boundary",
    _DIRECT_BOUNDARIES,
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_exact_ip_address_remains_serializable(
    boundary_name: str,
    boundary: _Boundary,
) -> None:
    original = KnowledgeValue[object](
        knowledge_state=KnowledgeState.PRESENT,
        value=IPv4Address("192.0.2.1"),
        evidence_ids=("EV-001",),
    )

    result = boundary(original)

    if boundary_name == "pickle":
        assert type(pickle.loads(cast(bytes, result)).value) is IPv4Address


@pytest.mark.parametrize("nonfinite", (float("nan"), float("inf"), float("-inf")))
@pytest.mark.parametrize(
    "model_type",
    (KnowledgeValue[float], KnowledgeValue[object]),
    ids=("typed", "object"),
)
def test_nonfinite_present_values_are_rejected_during_construction(
    model_type: type[KnowledgeValue[Any]],
    nonfinite: float,
) -> None:
    with pytest.raises(ValidationError, match=r"non-finite scientific payload"):
        model_type(
            knowledge_state=KnowledgeState.PRESENT,
            value=nonfinite,
            evidence_ids=("EV-001",),
        )


@pytest.mark.parametrize(
    "nonfinite",
    (Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")),
)
@pytest.mark.parametrize(
    "model_type",
    (KnowledgeValue[Decimal], KnowledgeValue[object]),
    ids=("typed", "object"),
)
def test_nonfinite_decimal_values_are_rejected_during_construction(
    model_type: type[KnowledgeValue[Any]],
    nonfinite: Decimal,
) -> None:
    with pytest.raises(
        ValidationError,
        match=r"non-finite scientific payload|finite number",
    ):
        model_type(
            knowledge_state=KnowledgeState.PRESENT,
            value=nonfinite,
            evidence_ids=("EV-001",),
        )


@pytest.mark.parametrize(
    "nonfinite",
    (complex(float("inf"), 0.0), complex(0.0, float("nan"))),
)
@pytest.mark.parametrize(
    "model_type",
    (KnowledgeValue[complex], KnowledgeValue[object]),
    ids=("typed", "object"),
)
def test_nonfinite_complex_values_are_rejected_during_construction(
    model_type: type[KnowledgeValue[Any]],
    nonfinite: complex,
) -> None:
    with pytest.raises(ValidationError, match=r"non-finite scientific payload"):
        model_type(
            knowledge_state=KnowledgeState.PRESENT,
            value=nonfinite,
            evidence_ids=("EV-001",),
        )


def test_nested_and_conflicting_nonfinite_decimals_are_rejected() -> None:
    with pytest.raises(ValidationError, match=r"non-finite scientific payload"):
        KnowledgeValue[object](
            knowledge_state=KnowledgeState.PRESENT,
            value={"measurements": [Decimal("Infinity")]},
            evidence_ids=("EV-001",),
        )

    with pytest.raises(
        ValidationError,
        match=r"non-finite scientific payload|finite number",
    ):
        KnowledgeValue[Decimal](
            knowledge_state=KnowledgeState.CONFLICTING,
            conflicting_values=(Decimal("1.0"), Decimal("Infinity")),
            evidence_ids=("EV-001",),
        )


@pytest.mark.parametrize(
    "model_type,payload",
    (
        (KnowledgeValue[list[float]], [float("inf")]),
        (KnowledgeValue[tuple[float, ...]], (float("-inf"),)),
        (KnowledgeValue[dict[str, float]], {"primary": float("nan")}),
    ),
    ids=("list", "tuple", "mapping"),
)
def test_nested_nonfinite_present_values_are_rejected_during_construction(
    model_type: type[KnowledgeValue[Any]],
    payload: object,
) -> None:
    with pytest.raises(ValidationError, match=r"non-finite scientific payload"):
        model_type(
            knowledge_state=KnowledgeState.PRESENT,
            value=payload,
            evidence_ids=("EV-001",),
        )


def test_nonfinite_conflicting_value_is_rejected_during_construction() -> None:
    with pytest.raises(ValidationError, match=r"non-finite scientific payload"):
        KnowledgeValue[float](
            knowledge_state=KnowledgeState.CONFLICTING,
            conflicting_values=(1.0, float("inf")),
            evidence_ids=("EV-001",),
        )


@pytest.mark.parametrize("nonfinite", (float("nan"), float("inf"), float("-inf")))
@pytest.mark.parametrize(
    "model_type",
    (KnowledgeValue[float], KnowledgeValue[object]),
    ids=("typed", "object"),
)
@pytest.mark.parametrize(
    "boundary_name,boundary",
    _DIRECT_BOUNDARIES,
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_forged_nonfinite_value_cannot_cross_serialization_boundaries(
    model_type: type[KnowledgeValue[Any]],
    nonfinite: float,
    boundary_name: str,
    boundary: _Boundary,
) -> None:
    del boundary_name
    hostile = model_type(
        knowledge_state=KnowledgeState.PRESENT,
        value=1.0,
        evidence_ids=("EV-001",),
    )
    object.__getattribute__(hostile, "__dict__")["value"] = nonfinite

    with pytest.raises(
        ValidationError,
        match=r"non-finite scientific payload|finite number",
    ):
        boundary(hostile)


@pytest.mark.parametrize(
    "model_type",
    (KnowledgeValue[Decimal], KnowledgeValue[object]),
    ids=("typed", "object"),
)
@pytest.mark.parametrize(
    "boundary_name,boundary",
    _DIRECT_BOUNDARIES,
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_forged_nonfinite_decimal_cannot_cross_serialization_boundaries(
    model_type: type[KnowledgeValue[Any]],
    boundary_name: str,
    boundary: _Boundary,
) -> None:
    del boundary_name
    hostile = model_type(
        knowledge_state=KnowledgeState.PRESENT,
        value=Decimal("1.0"),
        evidence_ids=("EV-001",),
    )
    object.__getattribute__(hostile, "__dict__")["value"] = Decimal("Infinity")

    with pytest.raises(
        ValidationError,
        match=r"non-finite scientific payload|finite number",
    ):
        boundary(hostile)


@pytest.mark.parametrize(
    "boundary_name,boundary",
    _DIRECT_BOUNDARIES,
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_nonfinite_float_inside_nested_model_cannot_cross_serialization_boundaries(
    boundary_name: str,
    boundary: _Boundary,
) -> None:
    del boundary_name
    hostile = KnowledgeValue[_FloatPayload](
        knowledge_state=KnowledgeState.PRESENT,
        value=_FloatPayload(measurement=float("inf")),
        evidence_ids=("EV-001",),
    )

    with pytest.raises(ExactRuntimeTreeError, match=r"non-finite scientific payload"):
        boundary(hostile)


@pytest.mark.parametrize(
    "boundary_name,boundary",
    _DIRECT_BOUNDARIES,
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_nonfinite_decimal_inside_nested_model_cannot_cross_boundaries(
    boundary_name: str,
    boundary: _Boundary,
) -> None:
    del boundary_name
    payload = cast(
        _DecimalPayload,
        _BASE_MODEL_CONSTRUCT(
            _DecimalPayload,
            measurement=Decimal("Infinity"),
        ),
    )
    hostile = KnowledgeValue[_DecimalPayload](
        knowledge_state=KnowledgeState.PRESENT,
        value=payload,
        evidence_ids=("EV-001",),
    )

    with pytest.raises(ExactRuntimeTreeError, match=r"non-finite scientific payload"):
        boundary(hostile)


@pytest.mark.parametrize("shape", ("root", "list", "tuple", "mapping"))
@pytest.mark.parametrize(
    "mutation",
    ("undeclared", "private", "extra", "subclass", "model-construct"),
)
@pytest.mark.parametrize(
    "boundary_name,boundary",
    _DIRECT_BOUNDARIES,
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_hostile_nested_models_cannot_cross_direct_serialization_boundaries(
    shape: _Shape,
    mutation: _Mutation,
    boundary_name: str,
    boundary: _Boundary,
) -> None:
    del boundary_name
    hostile = _knowledge(shape, _hostile_payload(mutation))

    with pytest.raises(ExactRuntimeTreeError, match="non-canonical runtime tree"):
        boundary(hostile)


@pytest.mark.parametrize("shape", ("root", "list", "tuple", "mapping"))
@pytest.mark.parametrize(
    "mutation",
    ("undeclared", "private", "extra", "subclass", "model-construct"),
)
def test_hostile_nested_models_cannot_cross_crafted_pickle_restore(
    shape: _Shape,
    mutation: _Mutation,
) -> None:
    valid = _knowledge(shape, _Payload(label="documented"))
    state = valid.__getstate__()
    state["payload"] = {
        **state["payload"],
        "value": _wrap_payload(shape, _hostile_payload(mutation)),
    }

    with pytest.raises(ExactRuntimeTreeError, match="non-canonical runtime tree"):
        object.__new__(type(valid)).__setstate__(state)


def test_parent_model_serialization_rejects_a_hostile_nested_knowledge_instance() -> None:
    knowledge = _knowledge("root", _Payload(label="documented"))
    payload = cast(_Payload, knowledge.value)
    object.__getattribute__(payload, "__dict__")["undeclared"] = "hidden"
    envelope = _BASE_MODEL_CONSTRUCT(_KnowledgeEnvelope, knowledge=knowledge)

    with pytest.raises(PydanticSerializationError, match="non-canonical runtime tree"):
        BaseModel.model_dump(envelope, mode="python", round_trip=True)


def test_parent_serialization_rejects_a_hostile_dataclass_knowledge_instance() -> None:
    knowledge = _dataclass_knowledge(
        "root",
        _DataclassPayload(label="documented"),
    )
    stored = _payload_from_shape(knowledge.value, "root")
    assert type(stored) is _DataclassPayload
    object.__setattr__(stored, "undeclared", "hidden")
    assert object.__getattribute__(stored, "__dict__")["undeclared"] == "hidden"
    envelope = _BASE_MODEL_CONSTRUCT(_DataclassKnowledgeEnvelope, knowledge=knowledge)

    with pytest.raises(PydanticSerializationError, match=r"dataclass state"):
        BaseModel.model_dump(envelope, mode="python", round_trip=True)


def test_parent_model_serialization_rejects_a_hostile_nested_knowledge_mapping() -> None:
    knowledge = _knowledge("root", _Payload(label="documented"))
    raw = knowledge.model_dump(mode="python", round_trip=True)
    payload = _Payload(label="documented")
    object.__getattribute__(payload, "__dict__")["undeclared"] = "hidden"
    raw["value"] = payload
    envelope = _BASE_MODEL_CONSTRUCT(_KnowledgeEnvelope, knowledge=raw)

    with pytest.raises(PydanticSerializationError, match="non-canonical runtime tree"):
        BaseModel.model_dump(envelope, mode="python", round_trip=True)


def test_parent_serialization_rejects_a_hostile_dataclass_knowledge_mapping() -> None:
    knowledge = _dataclass_knowledge(
        "root",
        _DataclassPayload(label="documented"),
    )
    raw = knowledge.model_dump(mode="python", round_trip=True)
    hostile = _DataclassPayload(label="documented")
    object.__setattr__(hostile, "undeclared", "hidden")
    assert object.__getattribute__(hostile, "__dict__")["undeclared"] == "hidden"
    raw["value"] = hostile
    envelope = _BASE_MODEL_CONSTRUCT(_DataclassKnowledgeEnvelope, knowledge=raw)

    with pytest.raises(PydanticSerializationError, match=r"dataclass state"):
        BaseModel.model_dump(envelope, mode="python", round_trip=True)


def test_valid_parent_mapping_serialization_remains_supported() -> None:
    knowledge = _knowledge("root", _Payload(label="documented"))
    raw = knowledge.model_dump(mode="python", round_trip=True)
    envelope = _BASE_MODEL_CONSTRUCT(_KnowledgeEnvelope, knowledge=raw)

    serialized = BaseModel.model_dump(
        envelope,
        mode="python",
        round_trip=True,
        warnings="error",
    )

    assert serialized["knowledge"]["value"] == {"label": "documented"}


@pytest.mark.parametrize("boundary", ("model-dump", "pickle"))
def test_sparse_nested_model_field_sets_are_preserved(boundary: str) -> None:
    payload = _SparsePayload(label="documented")
    knowledge = KnowledgeValue[_SparsePayload](
        knowledge_state=KnowledgeState.PRESENT,
        value=payload,
        evidence_ids=("EV-001",),
    )

    if boundary == "model-dump":
        serialized = knowledge.model_dump(mode="python", exclude_unset=True, round_trip=True)
        assert serialized == {
            "knowledge_state": KnowledgeState.PRESENT,
            "value": {"label": "documented"},
            "evidence_ids": ("EV-001",),
        }
    else:
        restored = pickle.loads(pickle.dumps(knowledge))
        assert restored.__pydantic_fields_set__ == knowledge.__pydantic_fields_set__
        assert restored.value is not None
        assert restored.value.__pydantic_fields_set__ == {"label"}


def _opaque_knowledge(error: BaseException) -> KnowledgeValue[_OpaquePayload]:
    _ComparisonBomb.error = error
    return KnowledgeValue[_OpaquePayload](
        knowledge_state=KnowledgeState.PRESENT,
        value=_OpaquePayload(item=_ComparisonBomb()),
        evidence_ids=("EV-001",),
    )


@pytest.mark.parametrize(
    "boundary",
    (
        lambda value: value.model_dump(mode="python", round_trip=True),
        lambda value: value.model_dump_json(round_trip=True),
        pickle.dumps,
    ),
    ids=("model-dump", "model-dump-json", "pickle"),
)
def test_ordinary_traversal_exception_is_normalized(
    boundary: Callable[[KnowledgeValue[_OpaquePayload]], object],
) -> None:
    error = RuntimeError("comparison failed")

    with pytest.raises(
        ExactRuntimeTreeError,
        match="canonical reconstruction failed",
    ) as captured:
        boundary(_opaque_knowledge(error))

    assert captured.value.__cause__ is error


@pytest.mark.parametrize(
    "boundary",
    (
        lambda value: value.model_dump(mode="python", round_trip=True),
        lambda value: value.model_dump_json(round_trip=True),
        pickle.dumps,
    ),
    ids=("model-dump", "model-dump-json", "pickle"),
)
def test_baseexception_from_traversal_is_propagated(
    boundary: Callable[[KnowledgeValue[_OpaquePayload]], object],
) -> None:
    error = _AbortTraversal()

    with pytest.raises(_AbortTraversal) as captured:
        boundary(_opaque_knowledge(error))

    assert captured.value is error


@pytest.mark.parametrize("deep", (False, True), ids=("shallow", "deep"))
def test_model_copy_normalizes_an_ordinary_traversal_exception(deep: bool) -> None:
    error = RuntimeError("comparison failed")

    with pytest.raises(
        ExactRuntimeTreeError,
        match="canonical reconstruction failed",
    ) as captured:
        _opaque_knowledge(error).model_copy(deep=deep)

    assert captured.value.__cause__ is error


@pytest.mark.parametrize("deep", (False, True), ids=("shallow", "deep"))
def test_model_copy_propagates_a_traversal_baseexception(deep: bool) -> None:
    error = _AbortTraversal()

    with pytest.raises(_AbortTraversal) as captured:
        _opaque_knowledge(error).model_copy(deep=deep)

    assert captured.value is error


@pytest.mark.parametrize(
    "error_factory,expected_error",
    (
        (lambda: RuntimeError("comparison failed"), ExactRuntimeTreeError),
        (_AbortTraversal, _AbortTraversal),
    ),
    ids=("ordinary-exception", "baseexception"),
)
def test_pickle_restore_normalizes_only_ordinary_traversal_exceptions(
    error_factory: Callable[[], BaseException],
    expected_error: type[BaseException],
) -> None:
    valid = KnowledgeValue[_OpaquePayload](
        knowledge_state=KnowledgeState.PRESENT,
        value=_OpaquePayload(item="documented"),
        evidence_ids=("EV-001",),
    )
    state = valid.__getstate__()
    error = error_factory()
    _ComparisonBomb.error = error
    state["payload"] = {
        **state["payload"],
        "value": _OpaquePayload(item=_ComparisonBomb()),
    }

    with pytest.raises(expected_error) as captured:
        object.__new__(type(valid)).__setstate__(state)

    if type(error) is RuntimeError:
        assert isinstance(captured.value, ExactRuntimeTreeError)
        assert "canonical reconstruction failed" in str(captured.value)
        assert captured.value.__cause__ is error
    else:
        assert captured.value is error


@pytest.mark.parametrize("deep", (False, True))
def test_existing_copy_boundaries_still_reject_hostile_nested_models(deep: bool) -> None:
    hostile = _knowledge("tuple", _hostile_payload("undeclared"))

    with pytest.raises(ExactRuntimeTreeError, match="non-canonical runtime tree"):
        hostile.model_copy(deep=deep)


@pytest.mark.parametrize("shape", ("root", "list", "tuple", "mapping"))
@pytest.mark.parametrize("deep", (False, True), ids=("shallow", "deep"))
def test_stdlib_copy_boundaries_reject_hostile_nested_models(
    shape: _Shape,
    deep: bool,
) -> None:
    hostile = _knowledge(shape, _Payload(label="documented"))
    stored = _payload_from_shape(hostile.value, shape)
    object.__getattribute__(stored, "__dict__")["undeclared"] = "hidden"
    assert object.__getattribute__(stored, "__dict__")["undeclared"] == "hidden"

    with pytest.raises(ExactRuntimeTreeError, match=r"non-canonical runtime tree"):
        deepcopy(hostile) if deep else copy(hostile)


@pytest.mark.parametrize("deep", (False, True), ids=("shallow", "deep"))
def test_stdlib_copy_preserves_valid_shallow_and_deep_semantics(deep: bool) -> None:
    original = KnowledgeValue[list[_Payload]](
        knowledge_state=KnowledgeState.PRESENT,
        value=[_Payload(label="documented")],
        evidence_ids=("EV-001",),
    )

    copied = deepcopy(original) if deep else copy(original)

    assert copied == original
    assert copied is not original
    assert copied.value is not None
    assert original.value is not None
    if deep:
        assert copied.value is not original.value
        assert copied.value[0] is not original.value[0]
    else:
        assert copied.value is original.value


def test_stdlib_deepcopy_is_memo_aware() -> None:
    original = KnowledgeValue[list[str]](
        knowledge_state=KnowledgeState.PRESENT,
        value=["documented"],
        evidence_ids=("EV-001",),
    )
    memo: dict[int, object] = {}

    copied = original.__deepcopy__(memo)

    assert memo[id(original)] is copied
