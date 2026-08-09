"""Normative PRD v8 KnowledgeState and open-world value wrapper."""

from __future__ import annotations

import json
import warnings
from collections.abc import Mapping, Sequence, Set
from enum import StrEnum
from typing import Any, Self, cast

from pydantic import (
    BaseModel,
    GetCoreSchemaHandler,
    PydanticDeprecatedSince20,
    SerializerFunctionWrapHandler,
    model_validator,
)
from pydantic_core import core_schema

from ntruth.schemas.kernel import KernelModel, NonBlankStr


class KnowledgeState(StrEnum):
    PRESENT = "PRESENT"
    ABSENT_EXPLICIT = "ABSENT_EXPLICIT"
    NOT_REPORTED = "NOT_REPORTED"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    CONFLICTING = "CONFLICTING"


_KNOWLEDGE_VALUE_PICKLE_FORMAT = "ntruth-knowledge-value-v1"


def _blank_or_empty(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (tuple, list, dict, set, frozenset)):
        return not value
    return False


def _ambiguous_scientific_path(value: object, path: str = "$") -> str | None:
    if value is None:
        return path
    if isinstance(value, str):
        return path if not value.strip() else None
    if isinstance(value, Mapping):
        if not value:
            return path
        for key, item in value.items():
            if isinstance(key, str) and not key.strip():
                return f"{path}.<blank-key>"
            issue = _ambiguous_scientific_path(item, f"{path}.{key}")
            if issue is not None:
                return issue
        return None
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if not value:
            return path
        for index, item in enumerate(value):
            issue = _ambiguous_scientific_path(item, f"{path}[{index}]")
            if issue is not None:
                return issue
        return None
    if isinstance(value, (set, frozenset)):
        if not value:
            return path
        for index, item in enumerate(value):
            issue = _ambiguous_scientific_path(item, f"{path}[{index}]")
            if issue is not None:
                return issue
    return None


def ensure_unambiguous_scientific_payload(value: object) -> None:
    """Reject any nested bare null, blank string or empty scientific container."""

    issue = _ambiguous_scientific_path(value)
    if issue is not None:
        raise ValueError(f"ambiguous scientific payload at {issue}")


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
        ) -> Any:
            if type(candidate) is dict:
                raw = candidate
                raw_fields = tuple(dict.keys(raw))
                if any(type(field_name) is not str for field_name in raw_fields) or set(
                    raw_fields
                ) != set(cls.model_fields):
                    raise TypeError("undeclared or missing KnowledgeValue serialized field")
                checked = cls.model_validate(raw)
            else:
                if not isinstance(candidate, KnowledgeValue):
                    raise TypeError("invalid KnowledgeValue serialized value")
                checked = cls.model_validate(KnowledgeValue._raw_contract_payload(candidate))
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
            return serializer(checked)

        return cast(
            core_schema.CoreSchema,
            {
                **schema,
                "serialization": core_schema.wrap_serializer_function_ser_schema(
                    serialize_revalidated
                ),
            },
        )

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

    def _raw_contract_payload(self) -> dict[str, Any]:
        KnowledgeValue._assert_no_undeclared_public_slot_state(self)
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
        copied = BaseModel.model_copy(self, update=update, deep=deep)
        copied_state = object.__getattribute__(copied, "__dict__")
        if type(copied_state) is not dict:
            raise TypeError("invalid KnowledgeValue runtime state")
        checked = type(self).model_validate(dict(copied_state))
        KnowledgeValue._raw_contract_payload(copied)
        if update is None:
            return copied
        object.__setattr__(
            checked,
            "__pydantic_fields_set__",
            set(object.__getattribute__(copied, "__pydantic_fields_set__")),
        )
        return checked

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """Serialize only after reconstructing a complete valid value."""

        KnowledgeValue._revalidated_for_boundary(self)
        return BaseModel.model_dump(self, **kwargs)

    def model_dump_json(self, **kwargs: Any) -> str:
        """Serialize JSON only after reconstructing a complete valid value."""

        KnowledgeValue._revalidated_for_boundary(self)
        return BaseModel.model_dump_json(self, **kwargs)

    def __getstate__(self) -> dict[str, Any]:
        checked = KnowledgeValue._revalidated_for_boundary(self)
        return {
            "format": _KNOWLEDGE_VALUE_PICKLE_FORMAT,
            "payload": KnowledgeValue._raw_contract_payload(checked),
            "fields_set": set(object.__getattribute__(self, "__pydantic_fields_set__")),
        }

    def __setstate__(self, state: dict[str, Any]) -> None:
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
        checked = type(self).model_validate(state["payload"])
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
