"""Regressions for exact graph-equality trust and reference contexts."""

from __future__ import annotations

from typing import Literal

import pytest
import test_prd_v8_task9_scientific_runtime_fix3 as fix3
from pydantic import BaseModel

import ntruth.graph.equality_v8 as equality_v8
from ntruth.graph.equality_v8 import (
    ExactGraphView,
    GraphNodeSemanticIdentity,
    exact_graph_equal,
)
from ntruth.runtime_tree import ExactRuntimeTreeError


@pytest.mark.parametrize(
    ("left_literal", "right_literal", "expected"),
    (
        ("left-unit-a", "right-unit-a", False),
        ("left-unit-a", "left-unit-a", True),
        ("right-unit-a", "right-unit-a", True),
    ),
)
def test_unmarked_literals_are_not_readdressed_when_they_collide_with_node_ids(
    left_literal: str,
    right_literal: str,
    expected: bool,
) -> None:
    assert (
        exact_graph_equal(
            fix3._present_view("left", {"literal": left_literal}),
            fix3._present_view("right", {"literal": right_literal}),
        )
        is expected
    )


@pytest.mark.parametrize(
    ("left_key", "right_key", "expected"),
    (
        ("left-unit-a", "right-unit-a", False),
        ("left-unit-a", "left-unit-a", True),
    ),
)
def test_unmarked_mapping_keys_are_preserved_as_literals(
    left_key: str,
    right_key: str,
    expected: bool,
) -> None:
    assert (
        exact_graph_equal(
            fix3._present_view("left", {"labels": {left_key: True}}),
            fix3._present_view("right", {"labels": {right_key: True}}),
        )
        is expected
    )


def test_nested_non_reference_literal_collision_remains_literal() -> None:
    payload = {"metadata": {"label": "left-unit-b"}}

    assert (
        exact_graph_equal(
            fix3._present_view("left", payload),
            fix3._present_view("right", payload),
        )
        is True
    )


@pytest.mark.parametrize(
    ("left_payload", "right_payload"),
    (
        ({"node_id": "left-unit-a"}, {"node_id": "right-unit-a"}),
        (
            {"references": ["left-unit-a", {"anchor": "left-unit-b"}]},
            {"references": ["right-unit-a", {"anchor": "right-unit-b"}]},
        ),
        (
            {"members": {"left-unit-a": True}},
            {"members": {"right-unit-a": True}},
        ),
    ),
)
def test_explicit_reference_contexts_remain_identifier_invariant(
    left_payload: dict[str, object],
    right_payload: dict[str, object],
) -> None:
    assert (
        exact_graph_equal(
            fix3._present_view("left", left_payload),
            fix3._present_view("right", right_payload),
        )
        is True
    )


def _with_forged_attribute_value(prefix: str, value: object) -> ExactGraphView:
    view = fix3._present_view(prefix, {"literal": "baseline"})
    relation = view.graph.relations[0]
    attributes = BaseModel.model_copy(
        relation.decisive_attributes,
        update={"value": value},
    )
    updated_relation = BaseModel.model_copy(
        relation,
        update={"decisive_attributes": attributes},
    )
    graph = BaseModel.model_copy(
        view.graph,
        update={"relations": (updated_relation,)},
    )
    return BaseModel.model_copy(view, update={"graph": graph})


@pytest.mark.parametrize(
    "payload",
    (
        {"node_id": 7},
        {"references": [7]},
        {"anchor": False},
        {"node_id": None},
        {"references": [1.5]},
    ),
)
def test_explicit_reference_context_rejects_non_string_scalar_or_null(
    payload: dict[str, object],
) -> None:
    assert (
        exact_graph_equal(
            _with_forged_attribute_value("left", payload),
            _with_forged_attribute_value("right", payload),
        )
        is False
    )


def _forged_identity(
    source: GraphNodeSemanticIdentity,
    *,
    method: Literal["copy", "construct"],
    node_id: object | None = None,
    semantic_key: object | None = None,
) -> GraphNodeSemanticIdentity:
    updates: dict[str, object] = {}
    if node_id is not None:
        updates["node_id"] = node_id
    if semantic_key is not None:
        updates["semantic_key"] = semantic_key
    if method == "copy":
        return source.model_copy(update=updates)
    return GraphNodeSemanticIdentity.model_construct(
        schema_version=source.schema_version,
        node_id=updates.get("node_id", source.node_id),
        role=source.role,
        semantic_key=updates.get("semantic_key", source.semantic_key),
    )


def _forge_view(
    view: ExactGraphView,
    *,
    method: Literal["copy", "construct"],
    defect: Literal["duplicate", "missing", "unhashable"],
) -> ExactGraphView:
    semantics = list(view.node_semantics)
    if defect == "duplicate":
        semantics[1] = _forged_identity(
            semantics[1],
            method=method,
            node_id=semantics[0].node_id,
        )
    elif defect == "missing":
        semantics.pop()
    else:
        semantics[0] = _forged_identity(
            semantics[0],
            method=method,
            semantic_key=["not", "hashable"],
        )
    if method == "copy":
        return view.model_copy(update={"node_semantics": tuple(semantics)})
    return ExactGraphView.model_construct(
        schema_version=view.schema_version,
        graph=view.graph,
        node_semantics=tuple(semantics),
    )


@pytest.mark.parametrize("method", ("copy", "construct"))
@pytest.mark.parametrize("defect", ("duplicate", "missing", "unhashable"))
def test_forged_semantic_identity_tree_fails_closed(
    method: Literal["copy", "construct"],
    defect: Literal["duplicate", "missing", "unhashable"],
) -> None:
    left = _forge_view(
        fix3._present_view("left", {"literal": "baseline"}),
        method=method,
        defect=defect,
    )
    right = fix3._present_view("right", {"literal": "baseline"})

    assert exact_graph_equal(left, right) is False


class _SemanticKeySubclass(str):
    pass


@pytest.mark.parametrize("intrusion", ("extra", "subclass"))
def test_field_set_mismatch_never_sanitizes_hostile_nested_state(
    intrusion: Literal["extra", "subclass"],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    left = fix3._present_view("left", {"literal": "baseline"})
    semantics = list(left.node_semantics)
    update: dict[str, object]
    if intrusion == "extra":
        update = {"undeclared_state": "trusted"}
    else:
        update = {"semantic_key": _SemanticKeySubclass(semantics[0].semantic_key)}
    semantics[0] = BaseModel.model_copy(semantics[0], update=update)
    forged = BaseModel.model_copy(left, update={"node_semantics": tuple(semantics)})

    def field_set_mismatch(*_: object, **__: object) -> ExactGraphView:
        raise ExactRuntimeTreeError(path="$.forged", reason="field-set mismatch")

    monkeypatch.setattr(equality_v8, "canonicalize_exact_model", field_set_mismatch)

    assert (
        exact_graph_equal(
            forged,
            fix3._present_view("right", {"literal": "baseline"}),
        )
        is False
    )


class _AbortEquality(BaseException):
    pass


def test_exact_graph_equality_does_not_swallow_baseexception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def abort(_: object) -> str:
        raise _AbortEquality

    monkeypatch.setattr(equality_v8, "canonical_checksum", abort)

    with pytest.raises(_AbortEquality):
        exact_graph_equal(
            fix3._present_view("left", {"literal": "baseline"}),
            fix3._present_view("right", {"literal": "baseline"}),
        )
