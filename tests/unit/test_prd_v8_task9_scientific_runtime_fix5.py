"""Regressions for complete exact-graph reconstruction and fail-closed equality."""

from __future__ import annotations

from typing import Literal

import pytest
import test_prd_v8_task9_scientific_runtime_fix3 as fix3
from pydantic import BaseModel

import ntruth.graph.equality_v8 as equality_v8
from ntruth.graph.equality_v8 import ExactGraphView, exact_graph_equal
from ntruth.schemas.graph_v8 import V8ExperimentGraph, V8GraphRelation


def _with_hidden_legacy_schema_version(
    view: ExactGraphView,
    *,
    level: Literal["view", "graph", "relation"],
) -> ExactGraphView:
    if level == "view":
        return ExactGraphView.model_construct(
            _fields_set={"graph", "node_semantics"},
            schema_version="7.0.0",
            graph=view.graph,
            node_semantics=view.node_semantics,
        )

    if level == "graph":
        graph = V8ExperimentGraph.model_construct(
            _fields_set={"nodes", "relations"},
            schema_version="7.0.0",
            nodes=view.graph.nodes,
            relations=view.graph.relations,
        )
    else:
        relation = view.graph.relations[0]
        relation_fields = {
            field_name: getattr(relation, field_name) for field_name in V8GraphRelation.model_fields
        }
        forged_relation = V8GraphRelation.model_construct(
            _fields_set=set(V8GraphRelation.model_fields) - {"schema_version"},
            **{**relation_fields, "schema_version": "7.0.0"},
        )
        graph = BaseModel.model_copy(
            view.graph,
            update={"relations": (forged_relation,)},
        )
    return BaseModel.model_copy(view, update={"graph": graph})


@pytest.mark.parametrize("level", ("view", "graph", "relation"))
def test_exact_graph_equality_rejects_hidden_legacy_schema_version(
    level: Literal["view", "graph", "relation"],
) -> None:
    left = _with_hidden_legacy_schema_version(
        fix3._present_view("left", {"literal": "baseline"}),
        level=level,
    )
    right = fix3._present_view("right", {"literal": "baseline"})

    assert exact_graph_equal(left, right) is False


def test_exact_graph_equality_fails_closed_on_ordinary_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(_: object, *, path: str) -> ExactGraphView:
        raise RuntimeError(path)

    monkeypatch.setattr(equality_v8, "_validated_graph_view", fail)

    assert (
        exact_graph_equal(
            fix3._present_view("left", {"literal": "baseline"}),
            fix3._present_view("right", {"literal": "baseline"}),
        )
        is False
    )


class _AbortEquality(BaseException):
    pass


def test_exact_graph_equality_propagates_baseexception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def abort(_: object, *, path: str) -> ExactGraphView:
        raise _AbortEquality(path)

    monkeypatch.setattr(equality_v8, "_validated_graph_view", abort)

    with pytest.raises(_AbortEquality):
        exact_graph_equal(
            fix3._present_view("left", {"literal": "baseline"}),
            fix3._present_view("right", {"literal": "baseline"}),
        )
