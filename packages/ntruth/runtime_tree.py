"""Exact runtime-tree reconstruction for public PRD v8 execution boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from pydantic import BaseModel


class ExactRuntimeTreeError(ValueError):
    """A typed, content-independent failure at an exact runtime-tree path."""

    def __init__(self, *, path: str, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"non-canonical runtime tree at {path}: {reason}")


def _model_state(value: BaseModel, *, path: str) -> dict[str, object]:
    state = object.__getattribute__(value, "__dict__")
    if type(state) is not dict:
        raise ExactRuntimeTreeError(path=path, reason="non-builtin model state")
    declared = set(type(value).model_fields)
    if set(state) != declared:
        raise ExactRuntimeTreeError(path=path, reason="undeclared or missing model field")
    fields_set = object.__getattribute__(value, "__pydantic_fields_set__")
    if type(fields_set) is not set or not fields_set.issubset(declared):
        raise ExactRuntimeTreeError(path=path, reason="invalid field-set metadata")
    extra = object.__getattribute__(value, "__pydantic_extra__")
    if extra:
        raise ExactRuntimeTreeError(path=path, reason="undeclared extra model state")
    private = object.__getattribute__(value, "__pydantic_private__")
    if private:
        raise ExactRuntimeTreeError(path=path, reason="undeclared private model state")
    return state


def _preflight_exact_tree(value: object, *, path: str) -> None:
    if isinstance(value, BaseModel):
        state = _model_state(value, path=path)
        for field_name, item in state.items():
            _preflight_exact_tree(item, path=f"{path}.{field_name}")
        return
    if isinstance(value, Mapping):
        if type(value) is not dict:
            raise ExactRuntimeTreeError(path=path, reason="non-builtin mapping")
        for index, (key, item) in enumerate(dict.items(value)):
            _preflight_exact_tree(key, path=f"{path}.key[{index}]")
            _preflight_exact_tree(item, path=f"{path}.value[{index}]")
        return
    if isinstance(value, tuple):
        if type(value) is not tuple:
            raise ExactRuntimeTreeError(path=path, reason="non-builtin tuple")
        for index, item in enumerate(value):
            _preflight_exact_tree(item, path=f"{path}[{index}]")
        return
    if isinstance(value, list):
        if type(value) is not list:
            raise ExactRuntimeTreeError(path=path, reason="non-builtin list")
        for index, item in enumerate(value):
            _preflight_exact_tree(item, path=f"{path}[{index}]")
        return
    if isinstance(value, (set, frozenset)):
        if type(value) not in {set, frozenset}:
            raise ExactRuntimeTreeError(path=path, reason="non-builtin set")
        for index, item in enumerate(value):
            _preflight_exact_tree(item, path=f"{path}[{index}]")


def _compare_exact_tree(raw: object, canonical: object, *, path: str) -> None:
    if type(raw) is not type(canonical):
        raise ExactRuntimeTreeError(path=path, reason="runtime type mismatch")
    if isinstance(raw, BaseModel):
        canonical_model = cast(BaseModel, canonical)
        raw_state = _model_state(raw, path=path)
        canonical_state = _model_state(canonical_model, path=path)
        raw_fields_set = object.__getattribute__(raw, "__pydantic_fields_set__")
        canonical_fields_set = object.__getattribute__(canonical_model, "__pydantic_fields_set__")
        if raw_fields_set != canonical_fields_set:
            raise ExactRuntimeTreeError(path=path, reason="field-set mismatch")
        for field_name in raw_state:
            _compare_exact_tree(
                raw_state[field_name],
                canonical_state[field_name],
                path=f"{path}.{field_name}",
            )
        return
    if isinstance(raw, dict):
        canonical_mapping = cast(dict[Any, Any], canonical)
        if raw.keys() != canonical_mapping.keys():
            raise ExactRuntimeTreeError(path=path, reason="mapping key mismatch")
        pairs = zip(dict.items(raw), dict.items(canonical_mapping), strict=True)
        for index, ((raw_key, raw_item), (canonical_key, canonical_item)) in enumerate(pairs):
            _compare_exact_tree(raw_key, canonical_key, path=f"{path}.key[{index}]")
            _compare_exact_tree(raw_item, canonical_item, path=f"{path}.value[{index}]")
        return
    if isinstance(raw, (tuple, list)):
        canonical_sequence = cast(tuple[Any, ...] | list[Any], canonical)
        if len(raw) != len(canonical_sequence):
            raise ExactRuntimeTreeError(path=path, reason="container length mismatch")
        pairs = zip(raw, canonical_sequence, strict=True)
        for index, (raw_item, canonical_item) in enumerate(pairs):
            _compare_exact_tree(raw_item, canonical_item, path=f"{path}[{index}]")
        return
    if isinstance(raw, (set, frozenset)):
        canonical_set = cast(set[Any] | frozenset[Any], canonical)
        unmatched = list(canonical_set)
        for index, raw_item in enumerate(raw):
            match_index = next(
                (
                    candidate_index
                    for candidate_index, candidate in enumerate(unmatched)
                    if type(raw_item) is type(candidate) and raw_item == candidate
                ),
                None,
            )
            if match_index is None:
                raise ExactRuntimeTreeError(path=path, reason="set item mismatch")
            canonical_item = unmatched.pop(match_index)
            _compare_exact_tree(raw_item, canonical_item, path=f"{path}[{index}]")
        if unmatched:
            raise ExactRuntimeTreeError(path=path, reason="set length mismatch")
        return
    if raw != canonical:
        raise ExactRuntimeTreeError(path=path, reason="canonical value mismatch")


def canonicalize_exact_model[ModelT: BaseModel](
    value: object,
    expected_type: type[ModelT],
    *,
    path: str,
) -> ModelT:
    """Validate, reconstruct and return an exact built-in runtime tree.

    The raw object is never returned.  Scientific execution must use the
    reconstructed object produced here.
    """

    if type(value) is not expected_type:
        raise ExactRuntimeTreeError(path=path, reason="root runtime type mismatch")
    _preflight_exact_tree(value, path=path)
    try:
        payload = BaseModel.model_dump(
            value,
            mode="python",
            exclude_unset=True,
            round_trip=True,
        )
        canonical = expected_type.model_validate(payload)
    except Exception as error:
        raise ExactRuntimeTreeError(path=path, reason="canonical reconstruction failed") from error
    _compare_exact_tree(value, canonical, path=path)
    return canonical


__all__ = [
    "ExactRuntimeTreeError",
    "canonicalize_exact_model",
]
