"""Normative PRD v8 KnowledgeState and open-world value wrapper."""

from __future__ import annotations

import json
import math
import sys
import warnings
from collections.abc import Callable, Mapping, Sequence, Set
from dataclasses import MISSING, is_dataclass
from dataclasses import fields as dataclass_fields
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import Enum, Flag, StrEnum
from pathlib import Path, PosixPath, PurePath, PurePosixPath, PureWindowsPath, WindowsPath
from types import UnionType
from typing import (
    Annotated,
    Any,
    Self,
    SupportsIndex,
    TypeVar,
    Union,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)
from uuid import UUID

from pydantic import (
    BaseModel,
    GetCoreSchemaHandler,
    PydanticDeprecatedSince20,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    TypeAdapter,
    ValidationInfo,
    model_validator,
)
from pydantic.errors import PydanticSchemaGenerationError
from pydantic_core import core_schema

from ntruth.runtime_tree import (
    ExactRuntimeTreeError,
    _compare_exact_tree,
    _preflight_exact_tree,
    canonicalize_exact_model,
)
from ntruth.schemas.kernel import KernelModel, NonBlankStr


class KnowledgeState(StrEnum):
    PRESENT = "PRESENT"
    ABSENT_EXPLICIT = "ABSENT_EXPLICIT"
    NOT_REPORTED = "NOT_REPORTED"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    CONFLICTING = "CONFLICTING"


_KNOWLEDGE_VALUE_PICKLE_FORMAT = "ntruth-knowledge-value-v1"
_OPAQUE_JSON_TAG = "__ntruth_opaque_json_v1__"
_CANONICAL_ENUM_STATE_FIELDS = {
    "_value_",
    "_name_",
    "__objclass__",
    "_sort_order_",
}
_CANONICAL_PATH_TYPES = {
    Path,
    PosixPath,
    PurePath,
    PurePosixPath,
    PureWindowsPath,
    WindowsPath,
}
_CANONICAL_PATH_TYPES_BY_NAME = {
    "Path": Path,
    "PosixPath": PosixPath,
    "PurePath": PurePath,
    "PurePosixPath": PurePosixPath,
    "PureWindowsPath": PureWindowsPath,
    "WindowsPath": WindowsPath,
}


def _opaque_json_envelope(payload: dict[str, object]) -> dict[str, object]:
    return {_OPAQUE_JSON_TAG: payload}


def _encode_opaque_pure_paths_for_json(value: object) -> tuple[object, bool]:
    """Encode only exact portable PurePath leaves in an opaque JSON tree."""

    if type(value) in _CANONICAL_PATH_TYPES_BY_NAME.values():
        return (
            _opaque_json_envelope(
                {
                    "kind": "pure-path",
                    "path_type": type(value).__name__,
                    "value": str(value),
                }
            ),
            True,
        )
    if type(value) is list:
        encoded_items = [
            _encode_opaque_pure_paths_for_json(item) for item in cast(list[object], value)
        ]
        return [item for item, _ in encoded_items], any(changed for _, changed in encoded_items)
    if type(value) is tuple:
        encoded_items = [
            _encode_opaque_pure_paths_for_json(item) for item in cast(tuple[object, ...], value)
        ]
        if any(changed for _, changed in encoded_items):
            return (
                _opaque_json_envelope(
                    {
                        "kind": "tuple",
                        "items": [item for item, _ in encoded_items],
                    }
                ),
                True,
            )
        return value, False
    if type(value) is dict:
        encoded_mapping_items: list[tuple[tuple[object, bool], tuple[object, bool]]] = [
            (
                _encode_opaque_pure_paths_for_json(key),
                _encode_opaque_pure_paths_for_json(item),
            )
            for key, item in dict.items(cast(dict[object, object], value))
        ]
        encoded_key_changed = any(key_changed for (_, key_changed), _ in encoded_mapping_items)
        encoded_value_changed = any(item_changed for _, (_, item_changed) in encoded_mapping_items)
        tag_collision = _OPAQUE_JSON_TAG in value
        if encoded_key_changed or tag_collision:
            return (
                _opaque_json_envelope(
                    {
                        "kind": "mapping",
                        "items": [
                            [encoded_key, encoded_item]
                            for (encoded_key, _), (encoded_item, _) in encoded_mapping_items
                        ],
                    }
                ),
                True,
            )
        return (
            {
                encoded_key: encoded_item
                for (encoded_key, _), (encoded_item, _) in encoded_mapping_items
            },
            encoded_value_changed,
        )
    return value, False


def _replace_opaque_pure_paths_in_serialized_tree(
    serialized: object,
    raw: object,
    *,
    path: str,
) -> object:
    """Replace serializer placeholders using the exact validated runtime tree."""

    if type(raw) in _CANONICAL_PATH_TYPES_BY_NAME.values():
        encoded, changed = _encode_opaque_pure_paths_for_json(raw)
        if not changed:
            raise ExactRuntimeTreeError(path=path, reason="invalid opaque path encoding")
        return encoded
    if type(raw) is list:
        if type(serialized) is not list or len(serialized) != len(raw):
            raise ExactRuntimeTreeError(path=path, reason="serialized container mismatch")
        return [
            _replace_opaque_pure_paths_in_serialized_tree(
                serialized_item,
                raw_item,
                path=f"{path}[{index}]",
            )
            for index, (serialized_item, raw_item) in enumerate(
                zip(cast(list[object], serialized), cast(list[object], raw), strict=True)
            )
        ]
    if type(raw) is tuple:
        if type(serialized) is not list or len(serialized) != len(raw):
            raise ExactRuntimeTreeError(path=path, reason="serialized container mismatch")
        return _opaque_json_envelope(
            {
                "kind": "tuple",
                "items": [
                    _replace_opaque_pure_paths_in_serialized_tree(
                        serialized_item,
                        raw_item,
                        path=f"{path}[{index}]",
                    )
                    for index, (serialized_item, raw_item) in enumerate(
                        zip(
                            cast(list[object], serialized),
                            cast(tuple[object, ...], raw),
                            strict=True,
                        )
                    )
                ],
            }
        )
    if type(raw) is dict:
        if type(serialized) is not dict or len(serialized) != len(raw):
            raise ExactRuntimeTreeError(path=path, reason="serialized mapping mismatch")
        if any(type(key) in _CANONICAL_PATH_TYPES_BY_NAME.values() for key in raw):
            encoded, changed = _encode_opaque_pure_paths_for_json(raw)
            if not changed:
                raise ExactRuntimeTreeError(path=path, reason="invalid opaque path encoding")
            return encoded
        if _OPAQUE_JSON_TAG in raw:
            encoded, changed = _encode_opaque_pure_paths_for_json(raw)
            if not changed:
                raise ExactRuntimeTreeError(path=path, reason="invalid opaque mapping encoding")
            return encoded
        restored: dict[object, object] = {}
        raw_items = list(dict.items(cast(dict[object, object], raw)))
        serialized_items = list(dict.items(cast(dict[object, object], serialized)))
        if tuple(key for key, _ in raw_items) != tuple(key for key, _ in serialized_items):
            raise ExactRuntimeTreeError(path=path, reason="serialized mapping key mismatch")
        for index, ((key, raw_item), (_, serialized_item)) in enumerate(
            zip(raw_items, serialized_items, strict=True)
        ):
            restored[key] = _replace_opaque_pure_paths_in_serialized_tree(
                serialized_item,
                raw_item,
                path=f"{path}.value[{index}]",
            )
        return restored
    return serialized


def _decode_opaque_pure_paths_from_json(value: object, *, path: str) -> object:
    """Decode the exact class-owned envelope emitted for opaque PurePath leaves."""

    if type(value) is list:
        return [
            _decode_opaque_pure_paths_from_json(item, path=f"{path}[{index}]")
            for index, item in enumerate(cast(list[object], value))
        ]
    if type(value) is not dict:
        return value
    mapping = cast(dict[object, object], value)
    if set(mapping) != {_OPAQUE_JSON_TAG}:
        return {
            key: _decode_opaque_pure_paths_from_json(
                item,
                path=f"{path}.value[{index}]",
            )
            for index, (key, item) in enumerate(dict.items(mapping))
        }

    envelope = dict.__getitem__(mapping, _OPAQUE_JSON_TAG)
    if type(envelope) is not dict:
        raise ExactRuntimeTreeError(path=path, reason="invalid opaque JSON envelope")
    payload = cast(dict[object, object], envelope)
    kind = dict.get(payload, "kind")
    if kind == "pure-path":
        if set(payload) != {"kind", "path_type", "value"}:
            raise ExactRuntimeTreeError(path=path, reason="invalid opaque JSON envelope")
        path_type_name = dict.get(payload, "path_type")
        raw_path = dict.get(payload, "value")
        path_type = (
            _CANONICAL_PATH_TYPES_BY_NAME.get(path_type_name)
            if type(path_type_name) is str
            else None
        )
        if path_type is None or type(raw_path) is not str:
            raise ExactRuntimeTreeError(path=path, reason="invalid opaque JSON envelope")
        try:
            canonical = path_type(raw_path)
        except Exception as error:
            raise ExactRuntimeTreeError(
                path=path,
                reason="incompatible opaque path type",
            ) from error
        if str(canonical) != raw_path:
            raise ExactRuntimeTreeError(path=path, reason="non-canonical opaque path")
        return canonical
    if kind == "tuple":
        if set(payload) != {"kind", "items"} or type(payload.get("items")) is not list:
            raise ExactRuntimeTreeError(path=path, reason="invalid opaque JSON envelope")
        return tuple(
            _decode_opaque_pure_paths_from_json(item, path=f"{path}[{index}]")
            for index, item in enumerate(cast(list[object], payload["items"]))
        )
    if kind == "mapping":
        if set(payload) != {"kind", "items"} or type(payload.get("items")) is not list:
            raise ExactRuntimeTreeError(path=path, reason="invalid opaque JSON envelope")
        restored: dict[object, object] = {}
        for index, pair in enumerate(cast(list[object], payload["items"])):
            if type(pair) is not list or len(pair) != 2:
                raise ExactRuntimeTreeError(path=path, reason="invalid opaque JSON envelope")
            restored_key = _decode_opaque_pure_paths_from_json(
                pair[0],
                path=f"{path}.key[{index}]",
            )
            restored_item = _decode_opaque_pure_paths_from_json(
                pair[1],
                path=f"{path}.value[{index}]",
            )
            try:
                if restored_key in restored:
                    raise ExactRuntimeTreeError(
                        path=path,
                        reason="duplicate opaque JSON mapping key",
                    )
                restored[restored_key] = restored_item
            except TypeError as error:
                raise ExactRuntimeTreeError(
                    path=f"{path}.key[{index}]",
                    reason="unhashable opaque JSON mapping key",
                ) from error
        return restored
    raise ExactRuntimeTreeError(path=path, reason="invalid opaque JSON envelope")


def _is_dataclass_instance(value: object) -> bool:
    return not isinstance(value, type) and is_dataclass(value)


def _exact_dataclass_items(
    value: object,
    *,
    path: str,
) -> tuple[tuple[str, object, bool], ...]:
    declared = dataclass_fields(cast(Any, value))
    field_names = tuple(field.name for field in declared)
    if any(type(field_name) is not str for field_name in field_names) or len(
        set(field_names)
    ) != len(field_names):
        raise ExactRuntimeTreeError(path=path, reason="invalid dataclass state")

    try:
        state = object.__getattribute__(value, "__dict__")
    except AttributeError:
        state = None
    if state is not None and (
        type(state) is not dict
        or any(type(field_name) is not str for field_name in state)
        or not set(state).issubset(field_names)
    ):
        raise ExactRuntimeTreeError(path=path, reason="undeclared dataclass state")

    field_name_set = set(field_names)
    field_slots: set[str] = set()
    for runtime_type in type(value).__mro__:
        slots = runtime_type.__dict__.get("__slots__", ())
        if type(slots) is str:
            slot_names = (slots,)
        elif type(slots) is tuple:
            slot_names = slots
        else:
            raise ExactRuntimeTreeError(path=path, reason="invalid dataclass state")
        for slot_name in slot_names:
            if type(slot_name) is not str:
                raise ExactRuntimeTreeError(path=path, reason="invalid dataclass state")
            if slot_name in field_name_set:
                field_slots.add(slot_name)
                continue
            if slot_name in {"__dict__", "__weakref__"}:
                continue
            try:
                object.__getattribute__(value, slot_name)
            except AttributeError:
                continue
            raise ExactRuntimeTreeError(path=path, reason="undeclared dataclass state")

    items: list[tuple[str, object, bool]] = []
    for field in declared:
        if type(state) is dict and field.name in state:
            item = dict.__getitem__(state, field.name)
        elif field.name in field_slots:
            try:
                item = object.__getattribute__(value, field.name)
            except AttributeError as error:
                raise ExactRuntimeTreeError(
                    path=path,
                    reason="missing dataclass state",
                ) from error
        elif not field.init and field.default is not MISSING:
            item = object.__getattribute__(value, field.name)
            if type(item) is not type(field.default) or item != field.default:
                raise ExactRuntimeTreeError(
                    path=path,
                    reason="non-canonical dataclass default",
                )
        else:
            raise ExactRuntimeTreeError(path=path, reason="missing dataclass state")
        items.append((field.name, item, field.init))
    return tuple(items)


def _assert_exact_enum_state(value: Enum, *, path: str) -> None:
    state = object.__getattribute__(value, "__dict__")
    if type(state) is not dict:
        raise ExactRuntimeTreeError(path=path, reason="non-canonical enum state")

    enum_type = type(value)
    value_map = enum_type.__dict__.get("_value2member_map_")
    if type(value_map) is not dict:
        raise ExactRuntimeTreeError(path=path, reason="non-canonical enum state")
    try:
        registered_member = dict.get(value_map, value.value)
    except TypeError:
        unhashable_map = enum_type.__dict__.get("_unhashable_values_map_")
        registered_values = (
            None if type(unhashable_map) is not dict else dict.get(unhashable_map, value.name)
        )
        registered_member = (
            value
            if type(registered_values) is list
            and any(candidate is value.value for candidate in registered_values)
            else None
        )
    if registered_member is not value:
        raise ExactRuntimeTreeError(path=path, reason="non-canonical enum state")

    if isinstance(value, Flag) and set(state) == {"_value_", "_name_"}:
        canonical = enum_type(value.value)
        if (
            canonical is not value
            or state["_value_"] != value.value
            or state["_name_"] != value.name
        ):
            raise ExactRuntimeTreeError(path=path, reason="non-canonical enum state")
        return

    if set(state) != _CANONICAL_ENUM_STATE_FIELDS:
        raise ExactRuntimeTreeError(path=path, reason="non-canonical enum state")
    name = state["_name_"]
    member_names = tuple(enum_type.__members__)
    if (
        type(name) is not str
        or any(type(member_name) is not str for member_name in member_names)
        or name not in member_names
        or enum_type.__members__.get(name) is not value
        or state["__objclass__"] is not enum_type
        or type(state["_sort_order_"]) is not int
        or state["_sort_order_"] != member_names.index(name)
    ):
        raise ExactRuntimeTreeError(path=path, reason="non-canonical enum state")

    raw_value = state["_value_"]
    expected_values = [candidate for candidate, member in dict.items(value_map) if member is value]
    if not expected_values:
        unhashable_map = enum_type.__dict__.get("_unhashable_values_map_")
        unhashable_values = (
            None if type(unhashable_map) is not dict else dict.get(unhashable_map, name)
        )
        if type(unhashable_values) is not list:
            raise ExactRuntimeTreeError(path=path, reason="non-canonical enum state")
        expected_values = unhashable_values
    if not any(
        type(raw_value) is type(expected) and raw_value == expected for expected in expected_values
    ):
        raise ExactRuntimeTreeError(path=path, reason="non-canonical enum state")


def _is_canonical_scalar_leaf(value: object, *, path: str) -> bool:
    if isinstance(value, (str, bytes, bytearray, int, float, complex, bool)):
        if type(value) not in {str, bytes, bytearray, int, float, complex, bool}:
            raise ExactRuntimeTreeError(path=path, reason="non-builtin scalar runtime type")
        return True
    if isinstance(value, Decimal):
        if type(value) is not Decimal:
            raise ExactRuntimeTreeError(path=path, reason="non-builtin scalar runtime type")
        return True
    if isinstance(value, (datetime, date, time, timedelta)):
        if type(value) not in {datetime, date, time, timedelta}:
            raise ExactRuntimeTreeError(path=path, reason="non-builtin scalar runtime type")
        return True
    if isinstance(value, UUID):
        if type(value) is not UUID:
            raise ExactRuntimeTreeError(path=path, reason="non-builtin scalar runtime type")
        return True
    if isinstance(value, PurePath):
        if type(value) not in _CANONICAL_PATH_TYPES:
            raise ExactRuntimeTreeError(path=path, reason="non-builtin scalar runtime type")
        return True
    return value is None


def _assert_exact_opaque_leaf(value: object, *, path: str) -> None:
    try:
        state = object.__getattribute__(value, "__dict__")
    except AttributeError:
        state = None
    if state is not None and (type(state) is not dict or state):
        raise ExactRuntimeTreeError(path=path, reason="undeclared opaque runtime state")

    try:
        adapter = TypeAdapter(type(value))
    except PydanticSchemaGenerationError:
        for runtime_type in type(value).__mro__:
            slots = runtime_type.__dict__.get("__slots__", ())
            if type(slots) is str:
                slot_names = (slots,)
            elif type(slots) is tuple:
                slot_names = slots
            else:
                raise ExactRuntimeTreeError(
                    path=path,
                    reason="invalid opaque runtime state",
                ) from None
            for slot_name in slot_names:
                if type(slot_name) is not str:
                    raise ExactRuntimeTreeError(
                        path=path,
                        reason="invalid opaque runtime state",
                    ) from None
                if slot_name in {"__dict__", "__weakref__"}:
                    continue
                try:
                    object.__getattribute__(value, slot_name)
                except AttributeError:
                    continue
                raise ExactRuntimeTreeError(
                    path=path,
                    reason="undeclared opaque runtime state",
                ) from None
        return

    serialized = adapter.dump_python(value, mode="python", round_trip=True)
    canonical = adapter.validate_python(serialized)
    _compare_exact_tree(value, canonical, path=path)


def _assert_no_undeclared_public_model_slots(value: BaseModel, *, path: str) -> None:
    declared_fields = set(type(value).model_fields)
    for model_type in type(value).__mro__:
        if model_type is BaseModel:
            break
        slots = model_type.__dict__.get("__slots__", ())
        if type(slots) is str:
            slot_names = (slots,)
        elif type(slots) is tuple:
            slot_names = slots
        else:
            raise ExactRuntimeTreeError(path=path, reason="invalid slotted model state")
        for slot_name in slot_names:
            if type(slot_name) is not str:
                raise ExactRuntimeTreeError(path=path, reason="invalid slotted model state")
            if slot_name in declared_fields or slot_name in {
                "__dict__",
                "__pydantic_fields_set__",
                "__pydantic_extra__",
                "__pydantic_private__",
            }:
                continue
            try:
                object.__getattribute__(value, slot_name)
            except AttributeError:
                continue
            raise ExactRuntimeTreeError(path=path, reason="undeclared public slotted model state")


def _nested_model_validation_tree(
    value: object,
    *,
    path: str,
    active_dataclasses: set[int] | None = None,
) -> object:
    """Materialize a preflighted model tree as sparse validation input."""

    if active_dataclasses is None:
        active_dataclasses = set()
    if isinstance(value, BaseModel):
        _assert_no_undeclared_public_model_slots(value, path=path)
        state = object.__getattribute__(value, "__dict__")
        fields_set = object.__getattribute__(value, "__pydantic_fields_set__")
        return {
            _model_validation_field_name(type(value), field_name): _nested_model_validation_tree(
                item,
                path=f"{path}.{field_name}",
                active_dataclasses=active_dataclasses,
            )
            for field_name, item in dict.items(state)
            if field_name in fields_set
        }
    if _is_dataclass_instance(value):
        identity = id(value)
        if identity in active_dataclasses:
            raise ExactRuntimeTreeError(path=path, reason="recursive dataclass state")
        active_dataclasses.add(identity)
        try:
            return {
                field_name: _nested_model_validation_tree(
                    item,
                    path=f"{path}.{field_name}",
                    active_dataclasses=active_dataclasses,
                )
                for field_name, item, init in _exact_dataclass_items(value, path=path)
                if init
            }
        finally:
            active_dataclasses.remove(identity)
    if isinstance(value, dict):
        return {
            _nested_mapping_key_validation_tree(
                key,
                path=f"{path}.key[{index}]",
                active_dataclasses=active_dataclasses,
            ): _nested_model_validation_tree(
                item,
                path=f"{path}.value[{index}]",
                active_dataclasses=active_dataclasses,
            )
            for index, (key, item) in enumerate(dict.items(value))
        }
    if isinstance(value, tuple):
        return tuple(
            _nested_model_validation_tree(
                item,
                path=f"{path}[{index}]",
                active_dataclasses=active_dataclasses,
            )
            for index, item in enumerate(value)
        )
    if isinstance(value, list):
        return [
            _nested_model_validation_tree(
                item,
                path=f"{path}[{index}]",
                active_dataclasses=active_dataclasses,
            )
            for index, item in enumerate(value)
        ]
    if isinstance(value, (set, frozenset)):
        return [
            _nested_model_validation_tree(
                item,
                path=f"{path}[{index}]",
                active_dataclasses=active_dataclasses,
            )
            for index, item in enumerate(value)
        ]
    if _is_nonfinite_scientific_scalar(value):
        raise ExactRuntimeTreeError(path=path, reason="non-finite scientific payload")
    if isinstance(value, Enum):
        _assert_exact_enum_state(value, path=path)
        return value
    if not _is_canonical_scalar_leaf(value, path=path):
        _assert_exact_opaque_leaf(value, path=path)
    return value


def _nested_mapping_key_validation_tree(
    value: object,
    *,
    path: str,
    active_dataclasses: set[int],
) -> object:
    """Reconstruct structured hashable keys without materializing them as dicts."""

    if isinstance(value, BaseModel):
        return canonicalize_exact_model(value, type(value), path=path)
    return _nested_model_validation_tree(
        value,
        path=path,
        active_dataclasses=active_dataclasses,
    )


def _compare_nested_boundary_tree(raw: object, canonical: object, *, path: str) -> None:
    if type(raw) is not type(canonical):
        raise ExactRuntimeTreeError(path=path, reason="runtime type mismatch")
    if isinstance(raw, BaseModel):
        canonical_model = cast(BaseModel, canonical)
        raw_state = object.__getattribute__(raw, "__dict__")
        canonical_state = object.__getattribute__(canonical_model, "__dict__")
        raw_fields_set = object.__getattribute__(raw, "__pydantic_fields_set__")
        canonical_fields_set = object.__getattribute__(
            canonical_model,
            "__pydantic_fields_set__",
        )
        if raw_fields_set != canonical_fields_set:
            raise ExactRuntimeTreeError(path=path, reason="field-set mismatch")
        for field_name, raw_item in dict.items(raw_state):
            _compare_nested_boundary_tree(
                raw_item,
                canonical_state[field_name],
                path=f"{path}.{field_name}",
            )
        return
    if _is_dataclass_instance(raw):
        raw_items = _exact_dataclass_items(raw, path=path)
        canonical_items = _exact_dataclass_items(canonical, path=path)
        if tuple(name for name, _, _ in raw_items) != tuple(name for name, _, _ in canonical_items):
            raise ExactRuntimeTreeError(path=path, reason="dataclass field mismatch")
        dataclass_pairs = zip(raw_items, canonical_items, strict=True)
        for (field_name, raw_item, _), (_, canonical_item, _) in dataclass_pairs:
            _compare_nested_boundary_tree(
                raw_item,
                canonical_item,
                path=f"{path}.{field_name}",
            )
        return
    if isinstance(raw, dict):
        canonical_mapping = cast(dict[Any, Any], canonical)
        if len(raw) != len(canonical_mapping):
            raise ExactRuntimeTreeError(path=path, reason="mapping length mismatch")
        mapping_pairs = zip(dict.items(raw), dict.items(canonical_mapping), strict=True)
        for index, ((raw_key, raw_item), (canonical_key, canonical_item)) in enumerate(
            mapping_pairs
        ):
            _compare_nested_boundary_tree(
                raw_key,
                canonical_key,
                path=f"{path}.key[{index}]",
            )
            _compare_nested_boundary_tree(
                raw_item,
                canonical_item,
                path=f"{path}.value[{index}]",
            )
        return
    if isinstance(raw, (tuple, list)):
        canonical_sequence = cast(tuple[Any, ...] | list[Any], canonical)
        if len(raw) != len(canonical_sequence):
            raise ExactRuntimeTreeError(path=path, reason="container length mismatch")
        for index, (raw_item, canonical_item) in enumerate(
            zip(raw, canonical_sequence, strict=True)
        ):
            _compare_nested_boundary_tree(
                raw_item,
                canonical_item,
                path=f"{path}[{index}]",
            )
        return
    _compare_exact_tree(raw, canonical, path=path)


def _canonicalize_opaque_nested_tree(
    value: object,
    *,
    path: str,
) -> object:
    """Canonicalize preflighted runtime models when the payload type is opaque."""

    if isinstance(value, BaseModel):
        return canonicalize_exact_model(value, type(value), path=path)
    if _is_dataclass_instance(value):
        arguments = {
            field_name: _canonicalize_opaque_nested_tree(
                item,
                path=f"{path}.{field_name}",
            )
            for field_name, item, init in _exact_dataclass_items(value, path=path)
            if init
        }
        canonical = cast(Any, type(value))(**arguments)
        _nested_model_validation_tree(canonical, path=path)
        _compare_nested_boundary_tree(value, canonical, path=path)
        return canonical
    if isinstance(value, dict):
        return {
            _canonicalize_opaque_nested_tree(
                key, path=f"{path}.key[{index}]"
            ): _canonicalize_opaque_nested_tree(item, path=f"{path}.value[{index}]")
            for index, (key, item) in enumerate(dict.items(value))
        }
    if isinstance(value, tuple):
        return tuple(
            _canonicalize_opaque_nested_tree(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        )
    if isinstance(value, list):
        return [
            _canonicalize_opaque_nested_tree(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, set):
        return {
            _canonicalize_opaque_nested_tree(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        }
    if isinstance(value, frozenset):
        return frozenset(
            _canonicalize_opaque_nested_tree(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        )
    return value


def _annotation_contains_opaque_value(
    annotation: object,
    *,
    active_types: set[type[object]] | None = None,
) -> bool:
    if active_types is None:
        active_types = set()
    if annotation is Any or annotation is object:
        return True
    if type(annotation) is TypeVar:
        if annotation.__bound__ is not None:
            return _annotation_contains_opaque_value(
                annotation.__bound__,
                active_types=active_types,
            )
        if annotation.__constraints__:
            return any(
                _annotation_contains_opaque_value(
                    constraint,
                    active_types=active_types,
                )
                for constraint in annotation.__constraints__
            )
        return True
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        if annotation in active_types:
            return False
        active_types.add(annotation)
        try:
            return any(
                _annotation_contains_opaque_value(
                    field.annotation,
                    active_types=active_types,
                )
                for field in annotation.model_fields.values()
            )
        finally:
            active_types.remove(annotation)
    if isinstance(annotation, type) and is_dataclass(annotation):
        if annotation in active_types:
            return False
        active_types.add(annotation)
        try:
            type_hints = get_type_hints(annotation)
            return any(
                _annotation_contains_opaque_value(
                    type_hints.get(field.name, field.type),
                    active_types=active_types,
                )
                for field in dataclass_fields(cast(Any, annotation))
            )
        finally:
            active_types.remove(annotation)
    return any(
        _annotation_contains_opaque_value(item, active_types=active_types)
        for item in get_args(annotation)
    )


def _canonicalize_nested_tree_for_annotation(
    value: object,
    annotation: object,
    *,
    path: str,
    preserve_hashable_model: bool = False,
) -> object:
    if annotation is Any or annotation is object:
        if preserve_hashable_model and isinstance(value, BaseModel):
            return canonicalize_exact_model(value, type(value), path=path)
        return _canonicalize_opaque_nested_tree(value, path=path)
    if type(annotation) is TypeVar:
        if annotation.__bound__ is not None:
            return _canonicalize_nested_tree_for_annotation(
                value,
                annotation.__bound__,
                path=path,
                preserve_hashable_model=preserve_hashable_model,
            )
        typevar_failures: list[ExactRuntimeTreeError] = []
        for constraint in annotation.__constraints__:
            try:
                return _canonicalize_nested_tree_for_annotation(
                    value,
                    constraint,
                    path=path,
                    preserve_hashable_model=preserve_hashable_model,
                )
            except ExactRuntimeTreeError as error:
                typevar_failures.append(error)
        if typevar_failures:
            raise typevar_failures[0]
        return _canonicalize_opaque_nested_tree(value, path=path)

    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if origin is Annotated and arguments:
        return _canonicalize_nested_tree_for_annotation(
            value,
            arguments[0],
            path=path,
            preserve_hashable_model=preserve_hashable_model,
        )
    if origin in {Union, UnionType}:
        union_failures: list[Exception] = []
        for member in arguments:
            try:
                candidate = _canonicalize_nested_tree_for_annotation(
                    value,
                    member,
                    path=path,
                    preserve_hashable_model=preserve_hashable_model,
                )
            except ExactRuntimeTreeError as error:
                union_failures.append(error)
                continue
            try:
                TypeAdapter(member).validate_python(candidate)
            except Exception as error:
                union_failures.append(error)
                continue
            return candidate
        if union_failures:
            raise union_failures[0]
        raise ExactRuntimeTreeError(path=path, reason="runtime type mismatch")
    if origin is list and len(arguments) == 1:
        if type(value) is not list:
            raise ExactRuntimeTreeError(path=path, reason="runtime type mismatch")
        return [
            _canonicalize_nested_tree_for_annotation(
                item,
                arguments[0],
                path=f"{path}[{index}]",
            )
            for index, item in enumerate(value)
        ]
    if origin is tuple:
        if type(value) is not tuple:
            raise ExactRuntimeTreeError(path=path, reason="runtime type mismatch")
        if len(arguments) == 2 and arguments[1] is Ellipsis:
            return tuple(
                _canonicalize_nested_tree_for_annotation(
                    item,
                    arguments[0],
                    path=f"{path}[{index}]",
                )
                for index, item in enumerate(value)
            )
        if len(arguments) == len(value):
            return tuple(
                _canonicalize_nested_tree_for_annotation(
                    item,
                    member,
                    path=f"{path}[{index}]",
                )
                for index, (item, member) in enumerate(zip(value, arguments, strict=True))
            )
        raise ExactRuntimeTreeError(path=path, reason="runtime type mismatch")
    if origin is dict and len(arguments) == 2:
        if type(value) is not dict:
            raise ExactRuntimeTreeError(path=path, reason="runtime type mismatch")
        key_annotation, value_annotation = arguments
        return {
            _canonicalize_nested_tree_for_annotation(
                key,
                key_annotation,
                path=f"{path}.key[{index}]",
                preserve_hashable_model=True,
            ): _canonicalize_nested_tree_for_annotation(
                item,
                value_annotation,
                path=f"{path}.value[{index}]",
            )
            for index, (key, item) in enumerate(dict.items(value))
        }
    if origin is Mapping and len(arguments) == 2:
        if type(value) is not dict:
            raise ExactRuntimeTreeError(path=path, reason="runtime type mismatch")
        key_annotation, value_annotation = arguments
        return {
            _canonicalize_nested_tree_for_annotation(
                key,
                key_annotation,
                path=f"{path}.key[{index}]",
                preserve_hashable_model=True,
            ): _canonicalize_nested_tree_for_annotation(
                item,
                value_annotation,
                path=f"{path}.value[{index}]",
            )
            for index, (key, item) in enumerate(dict.items(value))
        }
    if origin is Sequence and len(arguments) == 1:
        if type(value) not in {list, tuple}:
            raise ExactRuntimeTreeError(path=path, reason="runtime type mismatch")
        sequence = cast(list[Any] | tuple[Any, ...], value)
        items = (
            _canonicalize_nested_tree_for_annotation(
                item,
                arguments[0],
                path=f"{path}[{index}]",
            )
            for index, item in enumerate(sequence)
        )
        return tuple(items) if type(value) is tuple else list(items)
    if origin in {set, frozenset} and len(arguments) == 1:
        if type(value) is not origin:
            raise ExactRuntimeTreeError(path=path, reason="runtime type mismatch")
        collection = cast(set[Any] | frozenset[Any], value)
        return [
            _canonicalize_nested_tree_for_annotation(
                item,
                arguments[0],
                path=f"{path}[{index}]",
            )
            for index, item in enumerate(collection)
        ]
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        if type(value) is not annotation:
            raise ExactRuntimeTreeError(path=path, reason="runtime type mismatch")
        if preserve_hashable_model:
            return canonicalize_exact_model(value, annotation, path=path)
        state = object.__getattribute__(value, "__dict__")
        fields_set = object.__getattribute__(value, "__pydantic_fields_set__")
        return {
            _model_validation_field_name(annotation, field_name): (
                _canonicalize_nested_tree_for_annotation(
                    item,
                    annotation.model_fields[field_name].annotation,
                    path=f"{path}.{field_name}",
                )
            )
            for field_name, item in dict.items(state)
            if field_name in fields_set
        }
    return _canonicalize_dataclass_or_leaf_for_annotation(
        value,
        annotation,
        path=path,
    )


def _model_validation_field_name(
    model_type: type[BaseModel],
    field_name: str,
) -> str:
    validation_alias = model_type.model_fields[field_name].validation_alias
    return validation_alias if type(validation_alias) is str else field_name


def _canonicalize_dataclass_or_leaf_for_annotation(
    value: object,
    annotation: object,
    *,
    path: str,
) -> object:
    if isinstance(annotation, type) and is_dataclass(annotation):
        if type(value) is not annotation:
            raise ExactRuntimeTreeError(path=path, reason="runtime type mismatch")
        type_hints = get_type_hints(annotation)
        return {
            field_name: _canonicalize_nested_tree_for_annotation(
                item,
                type_hints.get(field_name, field.type),
                path=f"{path}.{field_name}",
            )
            for field, (field_name, item, init) in zip(
                dataclass_fields(cast(Any, annotation)),
                _exact_dataclass_items(value, path=path),
                strict=True,
            )
            if init
        }
    if isinstance(annotation, type) and not isinstance(value, annotation):
        raise ExactRuntimeTreeError(path=path, reason="runtime type mismatch")
    return _nested_model_validation_tree(value, path=path)


def _knowledge_value_pickle_argument(argument: object) -> object:
    if type(argument) is not TypeVar:
        return argument
    module_name = argument.__module__
    module = sys.modules.get(module_name) if type(module_name) is str else None
    if module is None or getattr(module, argument.__name__, None) is not argument:
        raise TypeError("KnowledgeValue TypeVar must be pickle-stable and importable")
    return argument


def _new_canonical_knowledge_value_for_pickle(
    specialized: bool,
    argument: object,
) -> KnowledgeValue[Any]:
    if type(specialized) is not bool:
        raise TypeError("invalid KnowledgeValue pickle specialization")
    if specialized:
        model_type = cast(
            type[KnowledgeValue[Any]],
            cast(Any, KnowledgeValue).__class_getitem__(argument),
        )
    else:
        if argument is not None:
            raise TypeError("invalid KnowledgeValue pickle specialization")
        model_type = cast(type[KnowledgeValue[Any]], KnowledgeValue)
    KnowledgeValue._assert_canonical_model_type(model_type)
    return object.__new__(model_type)


def _blank_or_empty(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (tuple, list, dict, set, frozenset)):
        return not value
    return False


def _is_nonfinite_scientific_scalar(value: object) -> bool:
    if type(value) is float:
        return not math.isfinite(value)
    if type(value) is Decimal:
        return not value.is_finite()
    if type(value) is complex:
        return not math.isfinite(value.real) or not math.isfinite(value.imag)
    return False


def _ambiguous_scientific_path(
    value: object,
    path: str = "$",
) -> tuple[str, str] | None:
    if value is None:
        return "ambiguous", path
    if _is_nonfinite_scientific_scalar(value):
        return "non-finite", path
    if isinstance(value, str):
        return ("ambiguous", path) if not value.strip() else None
    if isinstance(value, Mapping):
        if not value:
            return "ambiguous", path
        for key, item in value.items():
            if isinstance(key, str) and not key.strip():
                return "ambiguous", f"{path}.<blank-key>"
            issue = _ambiguous_scientific_path(item, f"{path}.{key}")
            if issue is not None:
                return issue
        return None
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if not value:
            return "ambiguous", path
        for index, item in enumerate(value):
            issue = _ambiguous_scientific_path(item, f"{path}[{index}]")
            if issue is not None:
                return issue
        return None
    if isinstance(value, (set, frozenset)):
        if not value:
            return "ambiguous", path
        for index, item in enumerate(value):
            issue = _ambiguous_scientific_path(item, f"{path}[{index}]")
            if issue is not None:
                return issue
    return None


def ensure_unambiguous_scientific_payload(value: object) -> None:
    """Reject any nested bare null, blank string or empty scientific container."""

    issue = _ambiguous_scientific_path(value)
    if issue is not None:
        reason, path = issue
        raise ValueError(f"{reason} scientific payload at {path}")


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


class KnowledgeValue[T](KernelModel):
    """A scientific value whose absence semantics are always explicit."""

    knowledge_state: KnowledgeState
    value: T | None = None
    conflicting_values: tuple[T, ...] = ()
    evidence_ids: tuple[NonBlankStr, ...] = ()
    source_scope_ids: tuple[NonBlankStr, ...] = ()
    rationale: NonBlankStr | None = None
    claim_scope_id: NonBlankStr | None = None
    query_scope_id: NonBlankStr | None = None

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source: Any,
        handler: GetCoreSchemaHandler,
    ) -> core_schema.CoreSchema:
        schema = handler(source)

        def serialize_revalidated(
            candidate: object,
            serializer: SerializerFunctionWrapHandler,
            info: SerializationInfo,
        ) -> Any:
            if (
                type(info.context) is dict
                and info.context.get("ntruth_opaque_path_transport") is True
            ):
                return serializer(candidate)
            if type(candidate) is dict:
                KnowledgeValue._assert_canonical_model_type(cls)
                raw = candidate
                raw_fields = tuple(dict.keys(raw))
                if any(type(field_name) is not str for field_name in raw_fields) or set(
                    raw_fields
                ) != set(cls.model_fields):
                    raise TypeError("undeclared or missing KnowledgeValue serialized field")
                try:
                    _preflight_exact_tree(raw, path="$.knowledge_value_mapping")
                    raw_tree = _nested_model_validation_tree(
                        raw,
                        path="$.knowledge_value_mapping",
                    )
                except ExactRuntimeTreeError:
                    raise
                except Exception as error:
                    raise ExactRuntimeTreeError(
                        path="$.knowledge_value_mapping",
                        reason="canonical reconstruction failed",
                    ) from error
                checked = cls.model_validate(raw)
                try:
                    checked_tree = _nested_model_validation_tree(
                        checked,
                        path="$.knowledge_value_mapping",
                    )
                    if type(raw_tree) is not dict or type(checked_tree) is not dict:
                        raise ExactRuntimeTreeError(
                            path="$.knowledge_value_mapping",
                            reason="non-builtin model payload",
                        )
                    for field_name, raw_item in dict.items(raw_tree):
                        _compare_nested_boundary_tree(
                            raw_item,
                            checked_tree[field_name],
                            path=f"$.knowledge_value_mapping.{field_name}",
                        )
                except ExactRuntimeTreeError:
                    raise
                except Exception as error:
                    raise ExactRuntimeTreeError(
                        path="$.knowledge_value_mapping",
                        reason="canonical reconstruction failed",
                    ) from error
            else:
                if not isinstance(candidate, KnowledgeValue):
                    raise TypeError("invalid KnowledgeValue serialized value")
                candidate_checked = KnowledgeValue._canonicalized_for_serialization_boundary(
                    candidate
                )
                checked = cls.model_validate(
                    KnowledgeValue._raw_contract_payload(candidate_checked)
                )
                object.__setattr__(
                    checked,
                    "__pydantic_fields_set__",
                    set(
                        object.__getattribute__(
                            candidate,
                            "__pydantic_fields_set__",
                        )
                    ),
                )
            checked = KnowledgeValue._canonicalized_for_serialization_boundary(checked)
            if info.mode_is_json():
                argument = KnowledgeValue._payload_type_argument(type(checked))
                if argument is object or argument is Any:
                    state = KnowledgeValue._raw_contract_payload(checked)
                    _, value_changed = _encode_opaque_pure_paths_for_json(state["value"])
                    _, conflicts_changed = _encode_opaque_pure_paths_for_json(
                        state["conflicting_values"]
                    )
                    if value_changed or conflicts_changed:

                        def path_only_fallback(value: object) -> object:
                            encoded, changed = _encode_opaque_pure_paths_for_json(value)
                            if not changed:
                                raise TypeError(
                                    f"unsupported opaque JSON type: {type(value).__name__}"
                                )
                            return encoded

                        transport = type(checked).__pydantic_serializer__.to_python(
                            checked,
                            mode="json",
                            include=cast(Any, info.include),
                            exclude=cast(Any, info.exclude),
                            by_alias=info.by_alias,
                            exclude_unset=info.exclude_unset,
                            exclude_defaults=info.exclude_defaults,
                            exclude_none=info.exclude_none,
                            exclude_computed_fields=info.exclude_computed_fields,
                            round_trip=info.round_trip,
                            serialize_as_any=info.serialize_as_any,
                            polymorphic_serialization=info.polymorphic_serialization,
                            warnings="error",
                            fallback=path_only_fallback,
                            context={"ntruth_opaque_path_transport": True},
                        )
                        if type(transport) is not dict:
                            raise ExactRuntimeTreeError(
                                path="$.knowledge_value",
                                reason="serialized model payload mismatch",
                            )
                        if value_changed and "value" in transport:
                            transport["value"] = _replace_opaque_pure_paths_in_serialized_tree(
                                transport["value"],
                                state["value"],
                                path="$.knowledge_value.value",
                            )
                        if conflicts_changed and "conflicting_values" in transport:
                            transport["conflicting_values"] = (
                                _replace_opaque_pure_paths_in_serialized_tree(
                                    transport["conflicting_values"],
                                    state["conflicting_values"],
                                    path="$.knowledge_value.conflicting_values",
                                )
                            )
                        return transport
            return serializer(checked)

        return cast(
            core_schema.CoreSchema,
            {
                **schema,
                "serialization": core_schema.wrap_serializer_function_ser_schema(
                    serialize_revalidated,
                    info_arg=True,
                ),
            },
        )

    @model_validator(mode="before")
    @classmethod
    def _restore_opaque_json_payload(
        cls,
        candidate: object,
        info: ValidationInfo,
    ) -> object:
        if info.mode != "json" or type(candidate) is not dict:
            return candidate
        argument = KnowledgeValue._payload_type_argument(cls)
        if argument is not object and argument is not Any:
            return candidate
        restored = dict(cast(dict[object, object], candidate))
        if "value" in restored:
            restored["value"] = _decode_opaque_pure_paths_from_json(
                restored["value"],
                path="$.knowledge_value.value",
            )
        if "conflicting_values" in restored:
            restored["conflicting_values"] = _decode_opaque_pure_paths_from_json(
                restored["conflicting_values"],
                path="$.knowledge_value.conflicting_values",
            )
        return restored

    @staticmethod
    def _non_default_contract_fields(state: Mapping[str, Any]) -> set[str]:
        non_default = {"knowledge_state"}
        if not (
            type(state.get("schema_version")) is str and state.get("schema_version") == "8.0.0"
        ):
            non_default.add("schema_version")
        if state.get("value") is not None:
            non_default.add("value")
        for field_name in (
            "conflicting_values",
            "evidence_ids",
            "source_scope_ids",
        ):
            value = state.get(field_name)
            if type(value) is not tuple or value:
                non_default.add(field_name)
        for field_name in ("rationale", "claim_scope_id", "query_scope_id"):
            if state.get(field_name) is not None:
                non_default.add(field_name)
        return non_default

    @staticmethod
    def _assert_canonical_model_type(model_type: type[object]) -> None:
        if model_type is KnowledgeValue:
            return
        metadata = model_type.__dict__.get("__pydantic_generic_metadata__")
        if type(metadata) is not dict:
            raise TypeError("non-canonical KnowledgeValue subclass")
        origin = dict.get(metadata, "origin")
        arguments = dict.get(metadata, "args")
        parameters = dict.get(metadata, "parameters")
        if (
            origin is not KnowledgeValue
            or type(arguments) is not tuple
            or len(arguments) != 1
            or type(parameters) is not tuple
        ):
            raise TypeError("non-canonical KnowledgeValue subclass")
        try:
            canonical_type = KnowledgeValue.__class_getitem__(arguments[0])
        except Exception as error:
            raise TypeError("non-canonical KnowledgeValue subclass") from error
        if model_type is not canonical_type:
            raise TypeError("non-canonical KnowledgeValue subclass")

    @staticmethod
    def _payload_type_argument(model_type: type[object]) -> object:
        if model_type is KnowledgeValue:
            return object
        metadata = model_type.__dict__.get("__pydantic_generic_metadata__")
        arguments = None if type(metadata) is not dict else dict.get(metadata, "args")
        if type(arguments) is not tuple or len(arguments) != 1:
            raise TypeError("invalid KnowledgeValue payload specialization")
        return arguments[0]

    def _raw_contract_payload(self) -> dict[str, Any]:
        KnowledgeValue._assert_no_undeclared_public_slot_state(self)
        KnowledgeValue._assert_canonical_model_type(type(self))
        state = object.__getattribute__(self, "__dict__")
        if type(state) is not dict:
            raise TypeError("invalid KnowledgeValue runtime state")
        declared_fields = set(type(self).model_fields)
        state_fields = tuple(dict.keys(state))
        if (
            any(type(field_name) is not str for field_name in state_fields)
            or set(state_fields) != declared_fields
        ):
            raise TypeError("undeclared or missing model field")
        if object.__getattribute__(self, "__pydantic_extra__") is not None:
            raise TypeError("undeclared extra model state")
        if object.__getattribute__(self, "__pydantic_private__") is not None:
            raise TypeError("undeclared private model state")
        fields_set = object.__getattribute__(self, "__pydantic_fields_set__")
        required_fields = KnowledgeValue._non_default_contract_fields(state)
        if (
            type(fields_set) is not set
            or any(type(field_name) is not str for field_name in fields_set)
            or not fields_set.issubset(declared_fields)
            or not required_fields.issubset(fields_set)
        ):
            raise TypeError("invalid KnowledgeValue field-set metadata")
        return dict(state)

    def _assert_no_undeclared_public_slot_state(self) -> None:
        declared_fields = set(type(self).model_fields)
        for model_type in type(self).__mro__:
            if model_type is KnowledgeValue:
                break
            slots = model_type.__dict__.get("__slots__", ())
            if type(slots) is str:
                slot_names = (slots,)
            elif type(slots) is tuple:
                slot_names = slots
            else:
                raise TypeError("invalid KnowledgeValue slotted model state")
            for slot_name in slot_names:
                if type(slot_name) is not str:
                    raise TypeError("invalid KnowledgeValue slotted model state")
                if slot_name.startswith("_") or slot_name in declared_fields:
                    continue
                try:
                    object.__getattribute__(self, slot_name)
                except AttributeError:
                    continue
                raise TypeError("undeclared public slotted model state")

    def _revalidated_for_boundary(self) -> Self:
        return type(self).model_validate(KnowledgeValue._raw_contract_payload(self))

    def _reconstructed_exact_runtime_tree(self) -> Self:
        path = "$.knowledge_value"
        _preflight_exact_tree(self, path=path)
        payload = _nested_model_validation_tree(self, path=path)
        if type(payload) is not dict:
            raise ExactRuntimeTreeError(path=path, reason="non-builtin model payload")
        argument = KnowledgeValue._payload_type_argument(type(self))
        if _annotation_contains_opaque_value(argument):
            state = object.__getattribute__(self, "__dict__")
            fields_set = object.__getattribute__(self, "__pydantic_fields_set__")
            if "value" in fields_set:
                payload["value"] = _canonicalize_nested_tree_for_annotation(
                    state["value"],
                    argument,
                    path=f"{path}.value",
                )
            if "conflicting_values" in fields_set:
                payload["conflicting_values"] = tuple(
                    _canonicalize_nested_tree_for_annotation(
                        item,
                        argument,
                        path=f"{path}.conflicting_values[{index}]",
                    )
                    for index, item in enumerate(state["conflicting_values"])
                )
        checked = type(self).model_validate(payload)
        _preflight_exact_tree(checked, path=path)
        _nested_model_validation_tree(checked, path=path)
        _compare_nested_boundary_tree(self, checked, path=path)
        return checked

    def _canonicalized_for_serialization_boundary(self) -> Self:
        KnowledgeValue._revalidated_for_boundary(self)
        return KnowledgeValue._normalized_exact_runtime_tree(self)

    def _normalized_exact_runtime_tree(self) -> Self:
        try:
            return KnowledgeValue._reconstructed_exact_runtime_tree(self)
        except ExactRuntimeTreeError:
            raise
        except Exception as error:
            raise ExactRuntimeTreeError(
                path="$.knowledge_value",
                reason="canonical reconstruction failed",
            ) from error

    def _assert_runtime_provenance_identity(self) -> None:
        state = KnowledgeValue._raw_contract_payload(self)
        KnowledgeValue._assert_provenance_fields(state)

    @staticmethod
    def _assert_provenance_fields(state: Mapping[str, Any]) -> None:
        for field_name in ("evidence_ids", "source_scope_ids"):
            identifiers = state.get(field_name)
            if type(identifiers) is not tuple or any(
                type(identifier) is not str or not str.strip(identifier)
                for identifier in identifiers
            ):
                raise TypeError(f"invalid KnowledgeValue {field_name} runtime state")
            if len(set(identifiers)) != len(identifiers):
                raise ValueError(f"{field_name} must be unique and order-preserving")

    @classmethod
    def model_construct(cls, _fields_set: set[str] | None = None, **values: Any) -> Self:
        """Retain construction compatibility without exposing validation bypasses."""

        del _fields_set
        return cls.model_validate(values)

    def copy(
        self,
        *,
        include: Set[int] | Set[str] | Mapping[int, Any] | Mapping[str, Any] | None = None,
        exclude: Set[int] | Set[str] | Mapping[int, Any] | Mapping[str, Any] | None = None,
        update: Mapping[str, Any] | None = None,
        deep: bool = False,
    ) -> Self:
        """Deprecated compatibility copy that retains the complete contract."""

        warnings.warn(
            "The `copy` method is deprecated; use `model_copy` instead.",
            category=PydanticDeprecatedSince20,
            stacklevel=2,
        )
        if include is not None or exclude is not None:
            raise TypeError(
                "partial KnowledgeValue copies are forbidden; use model_dump followed by "
                "model_validate"
            )
        return KnowledgeValue.model_copy(self, update=update, deep=deep)

    def model_copy(
        self,
        *,
        update: Mapping[str, Any] | None = None,
        deep: bool = False,
    ) -> Self:
        KnowledgeValue._revalidated_for_boundary(self)
        KnowledgeValue._normalized_exact_runtime_tree(self)
        copied = BaseModel.model_copy(self, update=update, deep=deep)
        copied_state = object.__getattribute__(copied, "__dict__")
        if type(copied_state) is not dict:
            raise TypeError("invalid KnowledgeValue runtime state")
        checked = type(self).model_validate(dict(copied_state))
        KnowledgeValue._raw_contract_payload(copied)
        KnowledgeValue._normalized_exact_runtime_tree(copied)
        object.__setattr__(
            checked,
            "__pydantic_fields_set__",
            set(object.__getattribute__(copied, "__pydantic_fields_set__")),
        )
        canonical_checked = KnowledgeValue._normalized_exact_runtime_tree(checked)
        if update is None:
            _compare_nested_boundary_tree(
                copied,
                canonical_checked,
                path="$.knowledge_value_copy",
            )
            return copied
        return canonical_checked

    def __copy__(self) -> Self:
        """Return a shallow copy only after exact-tree reconstruction succeeds."""

        KnowledgeValue._normalized_exact_runtime_tree(self)
        copied = BaseModel.__copy__(self)
        KnowledgeValue._normalized_exact_runtime_tree(copied)
        return copied

    def __deepcopy__(self, memo: dict[int, Any] | None = None) -> Self:
        """Return a memo-aware deep copy only across an exact runtime tree."""

        KnowledgeValue._normalized_exact_runtime_tree(self)
        if memo is None:
            memo = {}
        existing = memo.get(id(self))
        if existing is not None:
            return cast(Self, existing)
        copied = BaseModel.__deepcopy__(self, memo=memo)
        memo[id(self)] = copied
        KnowledgeValue._normalized_exact_runtime_tree(copied)
        return copied

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """Serialize only after reconstructing a complete valid value."""

        checked = KnowledgeValue._canonicalized_for_serialization_boundary(self)
        return BaseModel.model_dump(checked, **kwargs)

    def model_dump_json(self, **kwargs: Any) -> str:
        """Serialize JSON only after reconstructing a complete valid value."""

        checked = KnowledgeValue._canonicalized_for_serialization_boundary(self)
        return BaseModel.model_dump_json(checked, **kwargs)

    def __getstate__(self) -> dict[str, Any]:
        checked = KnowledgeValue._canonicalized_for_serialization_boundary(self)
        return {
            "format": _KNOWLEDGE_VALUE_PICKLE_FORMAT,
            "payload": KnowledgeValue._raw_contract_payload(checked),
            "fields_set": set(object.__getattribute__(self, "__pydantic_fields_set__")),
        }

    def __reduce_ex__(
        self,
        protocol: SupportsIndex,
    ) -> tuple[
        Callable[[bool, object], KnowledgeValue[Any]],
        tuple[bool, object],
        dict[str, Any],
    ]:
        del protocol
        state = self.__getstate__()
        model_type = type(self)
        descriptor: tuple[bool, object]
        if model_type is KnowledgeValue:
            descriptor = (False, None)
        else:
            metadata = model_type.__dict__.get("__pydantic_generic_metadata__")
            arguments = None if type(metadata) is not dict else dict.get(metadata, "args")
            if type(arguments) is not tuple or len(arguments) != 1:
                raise TypeError("non-canonical KnowledgeValue pickle specialization")
            descriptor = (True, _knowledge_value_pickle_argument(arguments[0]))
        return _new_canonical_knowledge_value_for_pickle, descriptor, state

    def __setstate__(self, state: dict[str, Any]) -> None:
        KnowledgeValue._assert_canonical_model_type(type(self))
        if type(state) is not dict or set(state) != {
            "format",
            "payload",
            "fields_set",
        }:
            raise TypeError("invalid KnowledgeValue pickle state")
        required_fields = {
            field_name
            for field_name, field in type(self).model_fields.items()
            if field.is_required()
        }
        if (
            state["format"] != _KNOWLEDGE_VALUE_PICKLE_FORMAT
            or type(state["payload"]) is not dict
            or type(state["fields_set"]) is not set
            or any(type(field_name) is not str for field_name in state["fields_set"])
            or not state["fields_set"].issubset(type(self).model_fields)
            or not required_fields.issubset(state["fields_set"])
        ):
            raise ValueError("unsupported KnowledgeValue pickle envelope")
        payload_fields = tuple(dict.keys(state["payload"]))
        if any(type(field_name) is not str for field_name in payload_fields) or set(
            payload_fields
        ) != set(type(self).model_fields):
            raise TypeError("undeclared or missing KnowledgeValue pickle payload field")
        try:
            _preflight_exact_tree(state["payload"], path="$.knowledge_value_pickle.payload")
            _nested_model_validation_tree(
                state["payload"],
                path="$.knowledge_value_pickle.payload",
            )
        except ExactRuntimeTreeError:
            raise
        except Exception as error:
            raise ExactRuntimeTreeError(
                path="$.knowledge_value_pickle.payload",
                reason="canonical reconstruction failed",
            ) from error
        checked = type(self).model_validate(state["payload"])
        checked = KnowledgeValue._canonicalized_for_serialization_boundary(checked)
        checked_state = object.__getattribute__(checked, "__dict__")
        non_default_fields = self._non_default_contract_fields(checked_state)
        if not non_default_fields.issubset(state["fields_set"]):
            raise ValueError("unsupported KnowledgeValue pickle envelope")
        BaseModel.__setstate__(self, BaseModel.__getstate__(checked))
        object.__setattr__(self, "__pydantic_fields_set__", set(state["fields_set"]))

    @model_validator(mode="after")
    def _open_world_invariants(self) -> KnowledgeValue[T]:
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("evidence_ids must be unique and order-preserving")
        if len(set(self.source_scope_ids)) != len(self.source_scope_ids):
            raise ValueError("source_scope_ids must be unique and order-preserving")

        state = self.knowledge_state
        if state is KnowledgeState.PRESENT:
            ensure_unambiguous_scientific_payload(self.value)
            if not self.evidence_ids:
                raise ValueError("PRESENT requires evidence_ids")
            if self.conflicting_values:
                raise ValueError("PRESENT cannot carry conflicting_values")
            return self

        if isinstance(self.value, str) and not self.value.strip():
            raise ValueError("blank scientific strings are forbidden")

        if state is KnowledgeState.CONFLICTING:
            if self.value is not None:
                raise ValueError("CONFLICTING retains alternatives, not one preferred value")
            if len(self.conflicting_values) < 2:
                raise ValueError("CONFLICTING requires at least two retained values")
            for item in self.conflicting_values:
                ensure_unambiguous_scientific_payload(item)
            if len({_canonical(item) for item in self.conflicting_values}) < 2:
                raise ValueError("CONFLICTING requires at least two distinct values")
            if not self.evidence_ids:
                raise ValueError("CONFLICTING requires evidence_ids")
            return self

        if self.conflicting_values:
            raise ValueError(f"{state.value} cannot carry conflicting_values")
        if self.value is not None and not _blank_or_empty(self.value):
            raise ValueError(f"{state.value} cannot carry a present scientific value")

        if state is KnowledgeState.ABSENT_EXPLICIT and not self.evidence_ids:
            raise ValueError("ABSENT_EXPLICIT requires evidence_ids")
        if state is KnowledgeState.NOT_REPORTED and not self.source_scope_ids:
            raise ValueError("NOT_REPORTED requires source_scope_ids")
        if state is KnowledgeState.UNKNOWN:
            if self.rationale is None:
                raise ValueError("UNKNOWN requires rationale")
            if self.claim_scope_id is None and self.query_scope_id is None:
                raise ValueError("UNKNOWN requires claim_scope_id or query_scope_id")
        if state is KnowledgeState.NOT_APPLICABLE:
            if self.rationale is None:
                raise ValueError("NOT_APPLICABLE requires rationale")
            if self.claim_scope_id is None and self.query_scope_id is None:
                raise ValueError("NOT_APPLICABLE requires claim_scope_id or query_scope_id")
        return self


ScientificKnowledgeValue = KnowledgeValue[object]

__all__ = [
    "KnowledgeState",
    "KnowledgeValue",
    "ScientificKnowledgeValue",
    "ensure_unambiguous_scientific_payload",
]
