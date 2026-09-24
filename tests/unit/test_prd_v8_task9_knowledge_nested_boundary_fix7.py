"""PurePath regressions for opaque KnowledgeValue JSON boundaries."""

from __future__ import annotations

import json
import pickle
import sys
from collections.abc import Callable
from copy import copy, deepcopy
from pathlib import Path, PosixPath, PurePosixPath, PureWindowsPath
from typing import Any, ClassVar, cast

import pytest
from pydantic import ValidationError
from pydantic_core import PydanticSerializationError, core_schema

from ntruth.runtime_tree import ExactRuntimeTreeError
from ntruth.schemas.core import FrozenModel
from ntruth.schemas.knowledge import (
    KnowledgeState,
    KnowledgeValue,
    ScientificKnowledgeValue,
)


class _OpaqueKnowledgeEnvelope(FrozenModel):
    knowledge: KnowledgeValue[object]


class _HostilePath(PurePosixPath):
    pass


class _AbortTraversal(BaseException):
    pass


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


_PATHS = (
    Path("/evidence/local-source.json"),
    PurePosixPath("/evidence/source.json"),
    PureWindowsPath("C:/evidence/source.json"),
)

_PATH_IDS = ("local-concrete", "pure-posix", "pure-windows")


def _present(
    payload: object,
    model_type: type[KnowledgeValue[object]] = KnowledgeValue[object],
) -> KnowledgeValue[object]:
    return model_type(
        knowledge_state=KnowledgeState.PRESENT,
        value=payload,
        evidence_ids=("EV-001",),
    )


@pytest.mark.parametrize(
    "model_type",
    (KnowledgeValue[object], ScientificKnowledgeValue),
    ids=("object", "scientific-alias"),
)
@pytest.mark.parametrize("path", _PATHS, ids=_PATH_IDS)
def test_exact_pure_paths_have_reversible_canonical_json(
    model_type: type[KnowledgeValue[object]],
    path: PosixPath | PurePosixPath | PureWindowsPath,
) -> None:
    original = _present(path, model_type)

    json_tree = original.model_dump(mode="json", round_trip=True)
    json_text = original.model_dump_json(round_trip=True)
    restored = model_type.model_validate_json(json_text)

    assert json.loads(json_text) == json_tree
    assert restored == original
    assert type(restored.value) is type(path)


@pytest.mark.parametrize("path", _PATHS, ids=_PATH_IDS)
@pytest.mark.parametrize("shape", ("list", "tuple", "mapping"))
def test_nested_exact_pure_paths_round_trip_through_json(
    path: PosixPath | PurePosixPath | PureWindowsPath,
    shape: str,
) -> None:
    payloads: dict[str, object] = {
        "list": [path],
        "tuple": (path,),
        "mapping": {"primary": path},
    }
    original = _present(payloads[shape])

    restored = KnowledgeValue[object].model_validate_json(original.model_dump_json(round_trip=True))

    assert restored == original
    if shape == "mapping":
        restored_path = cast(dict[str, object], restored.value)["primary"]
    else:
        restored_path = cast(list[object] | tuple[object, ...], restored.value)[0]
    assert type(restored_path) is type(path)


@pytest.mark.parametrize("path", _PATHS, ids=_PATH_IDS)
def test_parent_model_preserves_nested_pure_path_json_round_trip(
    path: PosixPath | PurePosixPath | PureWindowsPath,
) -> None:
    original = _OpaqueKnowledgeEnvelope(
        knowledge=_present({"sources": [path]}),
    )

    json_text = original.model_dump_json(round_trip=True)
    restored = _OpaqueKnowledgeEnvelope.model_validate_json(json_text)

    assert restored == original
    sources = cast(dict[str, list[object]], restored.knowledge.value)["sources"]
    assert type(sources[0]) is type(path)


def test_conflicting_pure_paths_have_reversible_canonical_json() -> None:
    original = KnowledgeValue[object](
        knowledge_state=KnowledgeState.CONFLICTING,
        conflicting_values=_PATHS,
        evidence_ids=("EV-001",),
    )

    json_tree = original.model_dump(mode="json", round_trip=True)
    json_text = original.model_dump_json(round_trip=True)
    restored = KnowledgeValue[object].model_validate_json(json_text)

    assert json.loads(json_text) == json_tree
    assert restored == original
    assert tuple(type(item) for item in restored.conflicting_values) == (
        type(_PATHS[0]),
        PurePosixPath,
        PureWindowsPath,
    )


@pytest.mark.parametrize("path", _PATHS, ids=_PATH_IDS)
@pytest.mark.parametrize(
    "boundary",
    (
        lambda value: value.model_dump(mode="python", round_trip=True)["value"],
        lambda value: pickle.loads(pickle.dumps(value)).value,
        lambda value: value.model_copy().value,
        lambda value: copy(value).value,
        lambda value: deepcopy(value).value,
    ),
    ids=("python-dump", "pickle", "model-copy", "copy", "deepcopy"),
)
def test_non_json_boundaries_preserve_exact_pure_path_type(
    path: PosixPath | PurePosixPath | PureWindowsPath,
    boundary: Callable[[KnowledgeValue[object]], object],
) -> None:
    restored_path = boundary(_present(path))

    assert type(restored_path) is type(path)
    assert restored_path == path


@pytest.mark.parametrize(
    "boundary",
    (
        lambda value: value.model_dump(mode="json", round_trip=True),
        lambda value: value.model_dump_json(round_trip=True),
        pickle.dumps,
        lambda value: value.model_copy(),
        copy,
        deepcopy,
    ),
    ids=("json-tree", "json-text", "pickle", "model-copy", "copy", "deepcopy"),
)
def test_hostile_pure_path_subclass_stays_fail_closed(
    boundary: Callable[[KnowledgeValue[object]], object],
) -> None:
    hostile_path = _HostilePath("/evidence/source.json")
    object.__setattr__(hostile_path, "determinability", "hidden")
    hostile = _present(hostile_path)

    with pytest.raises(ExactRuntimeTreeError, match=r"scalar runtime type"):
        boundary(hostile)


@pytest.mark.parametrize(
    "payload",
    (
        {"__ntruth_opaque_json_v1__": "literal user value"},
        {
            "nested": {
                "__ntruth_opaque_json_v1__": {
                    "kind": "pure-path",
                    "path_type": "PureWindowsPath",
                    "value": "C:/literal",
                }
            }
        },
    ),
    ids=("root", "nested"),
)
def test_user_mappings_that_look_like_path_envelopes_remain_mappings(
    payload: dict[str, object],
) -> None:
    original = _present(payload)

    restored = KnowledgeValue[object].model_validate_json(original.model_dump_json(round_trip=True))

    assert restored.value == payload
    assert type(restored.value) is dict


@pytest.mark.parametrize("json_text", (False, True), ids=("tree", "text"))
@pytest.mark.parametrize(
    "kwargs,expected",
    (
        ({"include": {"value"}}, {"value"}),
        (
            {"exclude": {"evidence_ids"}},
            {
                "schema_version",
                "knowledge_state",
                "value",
                "conflicting_values",
                "source_scope_ids",
                "rationale",
                "claim_scope_id",
                "query_scope_id",
            },
        ),
        (
            {"exclude_none": True},
            {
                "schema_version",
                "knowledge_state",
                "value",
                "conflicting_values",
                "evidence_ids",
                "source_scope_ids",
            },
        ),
        ({"exclude_defaults": True}, {"knowledge_state", "value", "evidence_ids"}),
        ({"exclude_unset": True}, {"knowledge_state", "value", "evidence_ids"}),
    ),
    ids=("include", "exclude", "exclude-none", "exclude-defaults", "exclude-unset"),
)
def test_pure_path_transport_preserves_pydantic_field_filters(
    json_text: bool,
    kwargs: dict[str, object],
    expected: set[str],
) -> None:
    original = _present(PurePosixPath("/evidence/source.json"))

    if json_text:
        serialized = json.loads(cast(Any, original).model_dump_json(round_trip=True, **kwargs))
    else:
        serialized = cast(Any, original).model_dump(mode="json", round_trip=True, **kwargs)

    assert set(serialized) == expected


def test_pure_path_transport_preserves_sparse_field_set_across_json() -> None:
    original = _present(PurePosixPath("/evidence/source.json"))

    json_text = original.model_dump_json(exclude_unset=True, round_trip=True)
    restored = KnowledgeValue[object].model_validate_json(json_text)

    assert restored.__pydantic_fields_set__ == {"knowledge_state", "value", "evidence_ids"}
    assert restored == original


@pytest.mark.parametrize("json_text", (False, True), ids=("tree", "text"))
@pytest.mark.parametrize(
    "kwargs,expected",
    (
        ({"include": {"knowledge": {"value"}}}, {"value"}),
        (
            {"exclude": {"knowledge": {"evidence_ids"}}},
            {
                "schema_version",
                "knowledge_state",
                "value",
                "conflicting_values",
                "source_scope_ids",
                "rationale",
                "claim_scope_id",
                "query_scope_id",
            },
        ),
    ),
    ids=("include", "exclude"),
)
def test_parent_pure_path_transport_preserves_nested_field_filters(
    json_text: bool,
    kwargs: dict[str, object],
    expected: set[str],
) -> None:
    original = _OpaqueKnowledgeEnvelope(
        knowledge=_present(PurePosixPath("/evidence/source.json")),
    )

    if json_text:
        serialized = json.loads(cast(Any, original).model_dump_json(round_trip=True, **kwargs))
    else:
        serialized = cast(Any, original).model_dump(mode="json", round_trip=True, **kwargs)

    assert set(serialized["knowledge"]) == expected


@pytest.mark.parametrize("json_text", (False, True), ids=("tree", "text"))
@pytest.mark.parametrize("filter_kind", ("include", "exclude"))
@pytest.mark.parametrize("shape", ("list", "tuple", "mapping"))
def test_nested_pure_path_transport_preserves_value_filters_and_field_set(
    json_text: bool,
    filter_kind: str,
    shape: str,
) -> None:
    first = PurePosixPath("/evidence/first.json")
    retained = PurePosixPath("/evidence/retained.json")
    payloads: dict[str, object] = {
        "list": [first, retained],
        "tuple": (first, retained),
        "mapping": {"first": first, "retained": retained},
    }
    expected_values: dict[str, object] = {
        "list": [retained],
        "tuple": (retained,),
        "mapping": {"retained": retained},
    }
    selected = 1 if shape != "mapping" else "retained"
    omitted = 0 if shape != "mapping" else "first"
    kwargs: dict[str, object]
    if filter_kind == "include":
        kwargs = {
            "include": {
                "knowledge_state": True,
                "value": {selected},
                "evidence_ids": True,
            }
        }
    else:
        kwargs = {
            "exclude": {"value": {omitted}},
            "exclude_unset": True,
        }
    original = _present(payloads[shape])

    if json_text:
        serialized = cast(Any, original).model_dump_json(round_trip=True, **kwargs)
        restored = KnowledgeValue[object].model_validate_json(serialized)
    else:
        serialized = cast(Any, original).model_dump(mode="json", round_trip=True, **kwargs)
        restored = KnowledgeValue[object].model_validate_json(json.dumps(serialized))

    assert restored.value == expected_values[shape]
    assert restored.__pydantic_fields_set__ == {"knowledge_state", "value", "evidence_ids"}
    retained_value = (
        cast(dict[str, object], restored.value)["retained"]
        if shape == "mapping"
        else cast(list[object] | tuple[object, ...], restored.value)[0]
    )
    assert type(retained_value) is PurePosixPath


@pytest.mark.parametrize("json_text", (False, True), ids=("tree", "text"))
@pytest.mark.parametrize("filter_kind", ("include", "exclude"))
@pytest.mark.parametrize("shape", ("list", "tuple", "mapping"))
def test_nested_pure_path_transport_serializes_when_filter_removes_every_path(
    json_text: bool,
    filter_kind: str,
    shape: str,
) -> None:
    path = PurePosixPath("/evidence/removed.json")
    payloads: dict[str, object] = {
        "list": [path, "retained"],
        "tuple": (path, "retained"),
        "mapping": {"path": path, "retained": "retained"},
    }
    expected_values: dict[str, object] = {
        "list": ["retained"],
        "tuple": ["retained"],
        "mapping": {"retained": "retained"},
    }
    retained = 1 if shape != "mapping" else "retained"
    omitted = 0 if shape != "mapping" else "path"
    kwargs: dict[str, object]
    if filter_kind == "include":
        kwargs = {"include": {"value": {retained}}}
    else:
        kwargs = {"exclude": {"value": {omitted}}}
    original = _present(payloads[shape])

    if json_text:
        serialized = json.loads(cast(Any, original).model_dump_json(round_trip=True, **kwargs))
    else:
        serialized = cast(Any, original).model_dump(
            mode="json",
            round_trip=True,
            **kwargs,
        )

    assert serialized["value"] == expected_values[shape]


@pytest.mark.parametrize("json_text", (False, True), ids=("tree", "text"))
def test_pure_path_mapping_key_uses_reversible_pair_envelope_before_json_key_encoding(
    json_text: bool,
) -> None:
    path_key = PurePosixPath("/evidence/key.json")
    original = _present({path_key: {"source": PurePosixPath("/evidence/value.json")}})

    if json_text:
        serialized_text = original.model_dump_json(round_trip=True)
    else:
        serialized_tree = original.model_dump(mode="json", round_trip=True)
        serialized_text = json.dumps(serialized_tree)
    restored = KnowledgeValue[object].model_validate_json(serialized_text)

    assert restored == original
    restored_mapping = cast(dict[object, object], restored.value)
    assert tuple(restored_mapping) == (path_key,)
    assert type(next(iter(restored_mapping))) is PurePosixPath


@pytest.mark.parametrize(
    "error_factory",
    (lambda: RuntimeError("comparison failed"), _AbortTraversal),
    ids=("ordinary-exception", "baseexception"),
)
@pytest.mark.parametrize("json_text", (False, True), ids=("tree", "text"))
def test_public_transport_context_cannot_bypass_parent_nested_revalidation(
    error_factory: Callable[[], BaseException],
    json_text: bool,
) -> None:
    error = error_factory()
    _ComparisonBomb.error = error
    parent = _OpaqueKnowledgeEnvelope(knowledge=_present(_ComparisonBomb()))
    context: dict[str, object] = {"ntruth_opaque_path_transport": True}

    def boundary(supplied_context: dict[str, object] | None) -> object:
        if json_text:
            return parent.model_dump_json(
                round_trip=True,
                context=supplied_context,
            )
        return parent.model_dump(
            mode="json",
            round_trip=True,
            context=supplied_context,
        )

    with pytest.raises(PydanticSerializationError) as baseline:
        boundary(None)
    with pytest.raises(PydanticSerializationError) as captured:
        boundary(context)

    assert type(captured.value) is type(baseline.value)
    assert str(captured.value) == str(baseline.value)
    expected_marker = (
        "canonical reconstruction failed" if type(error) is RuntimeError else "_AbortTraversal"
    )
    assert expected_marker in str(captured.value)
    assert "Unable to serialize unknown type" not in str(captured.value)


@pytest.mark.parametrize(
    "error_factory,expected_error",
    (
        (lambda: RuntimeError("comparison failed"), ExactRuntimeTreeError),
        (_AbortTraversal, _AbortTraversal),
    ),
    ids=("ordinary-exception", "baseexception"),
)
@pytest.mark.parametrize(
    "boundary",
    (
        lambda value: value.model_dump(mode="json", round_trip=True),
        lambda value: value.model_dump_json(round_trip=True),
        pickle.dumps,
        lambda value: value.model_copy(),
        copy,
        deepcopy,
    ),
    ids=("json-tree", "json-text", "pickle", "model-copy", "copy", "deepcopy"),
)
def test_exception_normalization_contract_is_unchanged(
    error_factory: Callable[[], BaseException],
    expected_error: type[BaseException],
    boundary: Callable[[KnowledgeValue[object]], object],
) -> None:
    error = error_factory()
    _ComparisonBomb.error = error
    value = _present(_ComparisonBomb())

    with pytest.raises(expected_error) as captured:
        boundary(value)

    if type(error) is RuntimeError:
        assert isinstance(captured.value, ExactRuntimeTreeError)
        assert "canonical reconstruction failed" in str(captured.value)
        assert captured.value.__cause__ is error
    else:
        assert captured.value is error


def test_unrelated_opaque_object_does_not_gain_a_lossy_json_fallback() -> None:
    class _Opaque:
        __slots__ = ()

    value = _present(_Opaque())

    with pytest.raises(PydanticSerializationError, match=r"Unable to serialize unknown type"):
        value.model_dump_json(round_trip=True)


def test_incompatible_concrete_path_envelope_fails_closed() -> None:
    path_type = "PosixPath" if sys.platform == "win32" else "WindowsPath"
    raw_path = "/evidence/source.json" if sys.platform == "win32" else "C:\\evidence\\source.json"
    json_payload = {
        "schema_version": "8.0.0",
        "knowledge_state": "PRESENT",
        "value": {
            "__ntruth_opaque_json_v1__": {
                "kind": "pure-path",
                "path_type": path_type,
                "value": raw_path,
            }
        },
        "conflicting_values": [],
        "evidence_ids": ["EV-001"],
        "source_scope_ids": [],
        "rationale": None,
        "claim_scope_id": None,
        "query_scope_id": None,
    }

    with pytest.raises(ValidationError, match=r"incompatible opaque path type"):
        KnowledgeValue[object].model_validate_json(json.dumps(json_payload))
