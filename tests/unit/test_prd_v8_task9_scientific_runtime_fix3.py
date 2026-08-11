"""Adversarial regressions for exact identifier-invariant graph equality."""

from __future__ import annotations

from typing import Any

import pytest
import test_prd_v8_task9_scientific_runtime_fix2 as fix2
from pydantic import BaseModel

from ntruth.graph.equality_v8 import (
    ExactGraphView,
    GraphNodeSemanticIdentity,
    exact_graph_equal,
)


def _with_attribute_value(view: ExactGraphView, value: Any) -> ExactGraphView:
    relation = view.graph.relations[0]
    attributes = BaseModel.model_copy(
        relation.decisive_attributes,
        update={"value": value},
    )
    updated_relation = relation.model_copy(update={"decisive_attributes": attributes})
    return view.model_copy(
        update={"graph": view.graph.model_copy(update={"relations": (updated_relation,)})}
    )


def _present_view(prefix: str, value: Any) -> ExactGraphView:
    baseline = fix2._exact_view(
        prefix,
        fix2._present_attributes(
            {"literal": "baseline"},
            query_id=f"{prefix}-query",
            evidence_id=f"EV-{prefix}",
        ),
    )
    return _with_attribute_value(baseline, value)


@pytest.mark.parametrize("cycle_kind", ("mapping", "list", "conflicting"))
def test_exact_graph_equality_fails_closed_for_recursive_scientific_payload(
    cycle_kind: str,
) -> None:
    right = _present_view("right", {"literal": "baseline"})
    if cycle_kind == "mapping":
        recursive_mapping: dict[str, object] = {}
        recursive_mapping["self"] = recursive_mapping
        left = _present_view("left", recursive_mapping)
    elif cycle_kind == "list":
        recursive_list: list[object] = []
        recursive_list.append(recursive_list)
        left = _present_view("left", recursive_list)
    else:
        recursive_conflict: dict[str, object] = {}
        recursive_conflict["self"] = recursive_conflict
        baseline = fix2._exact_view(
            "left",
            fix2._conflicting_attributes(
                ({"node_id": "left-unit-a"}, {"node_id": "left-unit-b"}),
                query_id="left-query",
                evidence_id="EV-left-conflict",
            ),
        )
        relation = baseline.graph.relations[0]
        attributes = BaseModel.model_copy(
            relation.decisive_attributes,
            update={"conflicting_values": (recursive_conflict, {"literal": "other"})},
        )
        updated_relation = relation.model_copy(update={"decisive_attributes": attributes})
        left = baseline.model_copy(
            update={"graph": baseline.graph.model_copy(update={"relations": (updated_relation,)})}
        )

    assert exact_graph_equal(left, right) is False


@pytest.mark.parametrize(
    "payload",
    (
        {"references": ["ghost-alpha"]},
        {"members": {"ghost_id": True}},
        {"anchor": "ghost-alpha"},
    ),
)
def test_explicit_unresolved_node_reference_context_fails_closed(
    payload: dict[str, object],
) -> None:
    assert (
        exact_graph_equal(
            _present_view("left", payload),
            _present_view("right", payload),
        )
        is False
    )


def test_identifier_shaped_unmarked_scientific_literal_is_not_guessed_as_reference() -> None:
    assert (
        exact_graph_equal(
            _present_view("left", {"literal": "unit-level"}),
            _present_view("right", {"literal": "unit-level"}),
        )
        is True
    )


def test_explicit_renamed_reference_lists_remain_identifier_invariant() -> None:
    left_items: list[object] = ["left-unit-a", {"peer_node_id": "left-unit-b"}]
    right_items: list[object] = ["right-unit-a", {"peer_node_id": "right-unit-b"}]

    assert (
        exact_graph_equal(
            _present_view("left", {"references": left_items}),
            _present_view("right", {"references": right_items}),
        )
        is True
    )


def test_forged_tuple_reference_container_fails_closed() -> None:
    left_items = ("left-unit-a", {"peer_node_id": "left-unit-b"})
    right_items = ("right-unit-a", {"peer_node_id": "right-unit-b"})

    assert (
        exact_graph_equal(
            _present_view("left", {"references": left_items}),
            _present_view("right", {"references": right_items}),
        )
        is False
    )


def _with_ambiguous_semantics(view: ExactGraphView) -> ExactGraphView:
    semantics = list(view.node_semantics)
    subject = next(identity for identity in semantics if identity.role == "subject")
    for index, identity in enumerate(semantics):
        if identity.role == "alternative":
            semantics[index] = GraphNodeSemanticIdentity(
                node_id=identity.node_id,
                role=subject.role,
                semantic_key=subject.semantic_key,
            )
    return view.model_copy(update={"node_semantics": tuple(semantics)})


@pytest.mark.parametrize("right_reference", ("right-unit-a", "right-unit-c"))
def test_duplicate_semantic_identity_mapping_is_always_unaddressable(
    right_reference: str,
) -> None:
    left = _with_ambiguous_semantics(_present_view("left", {"node_id": "left-unit-a"}))
    right = _with_ambiguous_semantics(_present_view("right", {"node_id": right_reference}))

    assert exact_graph_equal(left, right) is False


def test_shared_acyclic_nested_container_remains_comparable() -> None:
    left_shared = {"peer_node_id": "left-unit-b"}
    right_shared = {"peer_node_id": "right-unit-b"}

    assert (
        exact_graph_equal(
            _present_view("left", {"first": left_shared, "second": left_shared}),
            _present_view("right", {"first": right_shared, "second": right_shared}),
        )
        is True
    )
