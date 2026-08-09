"""Regressions for the second Wave A scientific-runtime hardening round."""

from __future__ import annotations

from typing import Any, ClassVar, Self

import pytest
import test_prd_v8_derivation_runtime as runtime_fixture
from pydantic import BaseModel, JsonValue, model_validator

from ntruth.derivation_theory.runtime import V8DerivationInput
from ntruth.graph.equality_v8 import (
    ExactGraphView,
    GraphNodeSemanticIdentity,
    exact_graph_equal,
)
from ntruth.pipeline_v8 import V8PipelineVerificationError, run_v8_pipeline
from ntruth.runtime_tree import ExactRuntimeTreeError, canonicalize_exact_model
from ntruth.schemas.graph_v8 import (
    V8ExperimentGraph,
    V8GraphNode,
    V8GraphNodeType,
    V8GraphRelation,
    V8GraphRelationType,
)
from ntruth.schemas.kernel import KernelModel
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.verifier.v8 import V8VerificationCode, verify_v8_pipeline_request


def _assert_runtime_tree_failure(request: V8DerivationInput, boundary: str) -> None:
    if boundary == "pipeline":
        with pytest.raises(V8PipelineVerificationError) as error:
            run_v8_pipeline(request, conformance_bundle=runtime_fixture.CANONICAL_BUNDLE)
        report = error.value.report
    else:
        report = verify_v8_pipeline_request(
            request,
            conformance_bundle=runtime_fixture.CANONICAL_BUNDLE,
        )
    assert report.passed is False
    assert report.issues[0].code is V8VerificationCode.RUNTIME_TREE_MISMATCH


@pytest.mark.parametrize("boundary", ("pipeline", "verifier"))
def test_missing_pydantic_runtime_metadata_is_a_typed_boundary_failure(boundary: str) -> None:
    _, request = runtime_fixture._request()
    forged = request.model_copy()
    object.__delattr__(forged, "__pydantic_fields_set__")

    _assert_runtime_tree_failure(forged, boundary)


def _recursive_request(kind: str) -> V8DerivationInput:
    _, request = runtime_fixture._request()
    forged = request.model_copy()
    if kind == "mapping":
        recursive_mapping: dict[str, object] = {}
        recursive_mapping["self"] = recursive_mapping
        object.__setattr__(forged, "predicate_values", recursive_mapping)
    elif kind == "container":
        recursive_list: list[object] = []
        recursive_list.append(recursive_list)
        object.__setattr__(forged, "scenario_coverages", recursive_list)
    else:
        object.__setattr__(forged, "query", forged)
    return forged


@pytest.mark.parametrize("boundary", ("pipeline", "verifier"))
@pytest.mark.parametrize("kind", ("mapping", "container", "model"))
def test_recursive_runtime_tree_is_a_typed_boundary_failure(
    boundary: str,
    kind: str,
) -> None:
    _assert_runtime_tree_failure(_recursive_request(kind), boundary)


def test_shared_non_recursive_runtime_values_remain_canonicalizable() -> None:
    _, request = runtime_fixture._request()
    predicates = dict(request.predicate_values)
    shared = predicates["assignment_separability_support"]
    predicates["assignment_separability"] = shared
    aliased = request.model_copy(update={"predicate_values": predicates})

    canonical = canonicalize_exact_model(
        aliased,
        V8DerivationInput,
        path="$.request",
    )

    assert canonical.predicate_values["assignment_separability"] == shared
    assert canonical.predicate_values["assignment_separability_support"] == shared


class _AbortRuntime(BaseException):
    pass


class _ExplodingValidatorModel(KernelModel):
    value: int
    armed: ClassVar[bool] = False

    @model_validator(mode="after")
    def _explode(self) -> Self:
        if type(self).armed:
            raise _AbortRuntime
        return self


def test_runtime_canonicalization_does_not_swallow_baseexception() -> None:
    value = _ExplodingValidatorModel(value=1)
    _ExplodingValidatorModel.armed = True

    try:
        with pytest.raises(_AbortRuntime):
            canonicalize_exact_model(value, _ExplodingValidatorModel, path="$.value")
    finally:
        _ExplodingValidatorModel.armed = False


class _PoisonedRequest(V8DerivationInput):
    state_was_inspected: ClassVar[bool] = False
    __slots__ = ("_poison_slot",)

    def __getattribute__(self, name: str) -> Any:
        if name in {
            "__dict__",
            "__pydantic_extra__",
            "__pydantic_fields_set__",
            "__pydantic_private__",
        }:
            type(self).state_was_inspected = True
            raise _AbortRuntime
        return super().__getattribute__(name)


def test_rejected_root_subclass_state_is_not_inspected() -> None:
    _, request = runtime_fixture._request()
    poisoned = _PoisonedRequest.model_validate(request.model_dump(mode="python"))
    _PoisonedRequest.state_was_inspected = False

    with pytest.raises(ExactRuntimeTreeError, match="root runtime type mismatch"):
        canonicalize_exact_model(poisoned, V8DerivationInput, path="$.request")

    assert _PoisonedRequest.state_was_inspected is False


def _present_scope(value: str, *, query_id: str, evidence_id: str) -> KnowledgeValue[str]:
    return KnowledgeValue[str](
        knowledge_state=KnowledgeState.PRESENT,
        value=value,
        evidence_ids=(evidence_id,),
        source_scope_ids=(f"SRC-{evidence_id}",),
        rationale=f"non-decisive-{evidence_id}",
        query_scope_id=query_id,
    )


def _present_attributes(
    value: dict[str, JsonValue],
    *,
    query_id: str,
    evidence_id: str,
) -> KnowledgeValue[dict[str, JsonValue]]:
    return KnowledgeValue[dict[str, JsonValue]](
        knowledge_state=KnowledgeState.PRESENT,
        value=value,
        evidence_ids=(evidence_id,),
        source_scope_ids=(f"SRC-{evidence_id}",),
        rationale=f"non-decisive-{evidence_id}",
        query_scope_id=query_id,
    )


def _conflicting_attributes(
    values: tuple[dict[str, JsonValue], ...],
    *,
    query_id: str,
    evidence_id: str,
) -> KnowledgeValue[dict[str, JsonValue]]:
    return KnowledgeValue[dict[str, JsonValue]](
        knowledge_state=KnowledgeState.CONFLICTING,
        conflicting_values=values,
        evidence_ids=(evidence_id,),
        source_scope_ids=(f"SRC-{evidence_id}",),
        rationale=f"non-decisive-{evidence_id}",
        query_scope_id=query_id,
    )


def _exact_view(
    prefix: str,
    decisive_attributes: KnowledgeValue[dict[str, JsonValue]],
) -> ExactGraphView:
    node_ids = {
        "subject": f"{prefix}-unit-a",
        "container": f"{prefix}-unit-b",
        "alternative": f"{prefix}-unit-c",
        "query": f"{prefix}-query",
        "factor": f"{prefix}-factor",
    }
    nodes = (
        V8GraphNode(node_id=node_ids["subject"], node_type=V8GraphNodeType.UNIT_INSTANCE),
        V8GraphNode(node_id=node_ids["container"], node_type=V8GraphNodeType.UNIT_INSTANCE),
        V8GraphNode(
            node_id=node_ids["alternative"],
            node_type=V8GraphNodeType.UNIT_INSTANCE,
        ),
        V8GraphNode(node_id=node_ids["query"], node_type=V8GraphNodeType.INFERENTIAL_QUERY),
        V8GraphNode(node_id=node_ids["factor"], node_type=V8GraphNodeType.FACTOR),
    )
    relation = V8GraphRelation(
        relation_id=f"{prefix}-relation",
        relation_type=V8GraphRelationType.CONTAINED_IN,
        source_node_id=node_ids["subject"],
        target_node_id=node_ids["container"],
        query_scope=_present_scope(
            node_ids["query"],
            query_id=node_ids["query"],
            evidence_id=f"EV-{prefix}-QUERY",
        ),
        factor_scope=_present_scope(
            node_ids["factor"],
            query_id=node_ids["query"],
            evidence_id=f"EV-{prefix}-FACTOR",
        ),
        decisive_attributes=decisive_attributes,
    )
    semantics = (
        GraphNodeSemanticIdentity(
            node_id=node_ids["subject"], role="subject", semantic_key="unit:a"
        ),
        GraphNodeSemanticIdentity(
            node_id=node_ids["container"], role="container", semantic_key="unit:b"
        ),
        GraphNodeSemanticIdentity(
            node_id=node_ids["alternative"], role="alternative", semantic_key="unit:c"
        ),
        GraphNodeSemanticIdentity(
            node_id=node_ids["query"], role="query", semantic_key="query:primary"
        ),
        GraphNodeSemanticIdentity(
            node_id=node_ids["factor"], role="factor", semantic_key="factor:treatment"
        ),
    )
    return ExactGraphView(
        graph=V8ExperimentGraph(nodes=nodes, relations=(relation,)),
        node_semantics=semantics,
    )


def test_exact_graph_equality_recursively_readdresses_nested_node_references() -> None:
    left_attributes = _present_attributes(
        {
            "anchor": "left-unit-a",
            "nested": {"peer_node_id": "left-unit-b"},
            "references": ["left-query", "left-factor"],
            "literal": "preserved scientific label",
        },
        query_id="left-query",
        evidence_id="EV-LEFT-ATTR",
    )
    right_attributes = _present_attributes(
        {
            "anchor": "right-unit-a",
            "nested": {"peer_node_id": "right-unit-b"},
            "references": ["right-query", "right-factor"],
            "literal": "preserved scientific label",
        },
        query_id="right-query",
        evidence_id="EV-RIGHT-ATTR",
    )
    left = _exact_view("left", left_attributes)
    right = _exact_view("right", right_attributes)
    left_before = left.model_dump(mode="json")
    right_before = right.model_dump(mode="json")

    assert exact_graph_equal(left, right) is True
    assert left.model_dump(mode="json") == left_before
    assert right.model_dump(mode="json") == right_before


def test_exact_graph_equality_recursively_readdresses_conflicting_values() -> None:
    left = _exact_view(
        "left",
        _conflicting_attributes(
            (
                {"node_id": "left-unit-a"},
                {"node_id": "left-unit-b"},
            ),
            query_id="left-query",
            evidence_id="EV-LEFT-CONFLICT",
        ),
    )
    right = _exact_view(
        "right",
        _conflicting_attributes(
            (
                {"node_id": "right-unit-a"},
                {"node_id": "right-unit-b"},
            ),
            query_id="right-query",
            evidence_id="EV-RIGHT-CONFLICT",
        ),
    )

    assert exact_graph_equal(left, right) is True


def test_exact_graph_equality_readdresses_node_identifiers_used_as_mapping_keys() -> None:
    left = _exact_view(
        "left",
        _present_attributes(
            {"members": {"left-unit-a": True, "left-unit-b": False}},
            query_id="left-query",
            evidence_id="EV-LEFT-ATTR",
        ),
    )
    right = _exact_view(
        "right",
        _present_attributes(
            {"members": {"right-unit-a": True, "right-unit-b": False}},
            query_id="right-query",
            evidence_id="EV-RIGHT-ATTR",
        ),
    )

    assert exact_graph_equal(left, right) is True


def test_exact_graph_equality_detects_nested_semantic_reference_change() -> None:
    left = _exact_view(
        "left",
        _present_attributes(
            {"nested": {"node_id": "left-unit-a"}},
            query_id="left-query",
            evidence_id="EV-LEFT-ATTR",
        ),
    )
    right = _exact_view(
        "right",
        _present_attributes(
            {"nested": {"node_id": "right-unit-c"}},
            query_id="right-query",
            evidence_id="EV-RIGHT-ATTR",
        ),
    )

    assert exact_graph_equal(left, right) is False


def test_exact_graph_equality_fails_closed_for_unresolved_node_identifier() -> None:
    left = _exact_view(
        "left",
        _present_attributes(
            {"nested": {"node_id": "UNIT-MISSING"}},
            query_id="left-query",
            evidence_id="EV-LEFT-ATTR",
        ),
    )
    right = _exact_view(
        "right",
        _present_attributes(
            {"nested": {"node_id": "UNIT-MISSING"}},
            query_id="right-query",
            evidence_id="EV-RIGHT-ATTR",
        ),
    )

    assert exact_graph_equal(left, right) is False


class _AttributeMappingSubclass(dict[str, JsonValue]):
    pass


def test_exact_graph_equality_fails_closed_for_non_builtin_attribute_container() -> None:
    valid = _exact_view(
        "left",
        _present_attributes(
            {"literal": "preserved scientific label"},
            query_id="left-query",
            evidence_id="EV-LEFT-ATTR",
        ),
    )
    relation = valid.graph.relations[0]
    forged_attributes = BaseModel.model_copy(
        relation.decisive_attributes,
        update={"value": _AttributeMappingSubclass(relation.decisive_attributes.value or {})},
    )
    forged_relation = relation.model_copy(update={"decisive_attributes": forged_attributes})
    forged_graph = valid.graph.model_copy(update={"relations": (forged_relation,)})
    forged = valid.model_copy(update={"graph": forged_graph})

    assert exact_graph_equal(forged, valid) is False
