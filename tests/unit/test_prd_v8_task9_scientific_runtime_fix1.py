"""RED regressions for the final PRD v8 scientific runtime audit, Wave A."""

from __future__ import annotations

from typing import Any

import pytest
import test_prd_v8_derivation_runtime as runtime_fixture
from pydantic import JsonValue, ValidationError

from ntruth.derivation_theory.contracts import ConformanceBundle
from ntruth.derivation_theory.runtime import V8DerivationInput
from ntruth.graph.equality_v8 import (
    ExactGraphView,
    GraphNodeSemanticIdentity,
    exact_graph_equal,
)
from ntruth.pipeline_v8 import V8PipelineVerificationError, run_v8_pipeline
from ntruth.schemas.causal_context import QueryCausalEventAggregate
from ntruth.schemas.events import EventRegistry, RelativeTiming, TemporalRelation
from ntruth.schemas.graph_v8 import (
    V8ExperimentGraph,
    V8GraphNode,
    V8GraphNodeType,
    V8GraphRelation,
    V8GraphRelationType,
)
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.verifier.v8 import verify_v8_pipeline_request


def _assert_runtime_tree_rejected(
    request: V8DerivationInput,
    *,
    bundle: ConformanceBundle = runtime_fixture.CANONICAL_BUNDLE,
) -> None:
    with pytest.raises(V8PipelineVerificationError) as error:
        run_v8_pipeline(request, conformance_bundle=bundle)
    assert error.value.report.passed is False
    assert error.value.report.issues[0].code == "RUNTIME_TREE_MISMATCH"


class _SplitViewPredicateMap(dict[str, KnowledgeValue[JsonValue]]):
    """Serialize the stored value while returning a different scientific value."""

    def __init__(self, values: dict[str, KnowledgeValue[JsonValue]]) -> None:
        super().__init__(values)
        self._replacement = runtime_fixture._present(False)

    def __getitem__(self, key: str) -> KnowledgeValue[JsonValue]:
        if key == "assignment_separability_support":
            return self._replacement
        return super().__getitem__(key)

    def get(
        self,
        key: str,
        default: KnowledgeValue[JsonValue] | None = None,
    ) -> KnowledgeValue[JsonValue] | None:
        if key == "assignment_separability_support":
            return self._replacement
        return super().get(key, default)


def test_runtime_rejects_root_and_nested_undeclared_state_before_derivation() -> None:
    _, request = runtime_fixture._request()
    root_extra = request.model_copy(update={"determinability": "DETERMINATE"})
    nested_extra = request.model_copy(
        update={
            "query": request.query.model_copy(
                update={
                    "timepoint_id": request.query.timepoint_id.model_copy(
                        update={"design_verdict": "ADEQUATE"}
                    )
                }
            )
        }
    )

    _assert_runtime_tree_rejected(root_extra)
    _assert_runtime_tree_rejected(nested_extra)


def test_runtime_rejects_non_builtin_container_with_divergent_scientific_view() -> None:
    _, request = runtime_fixture._request()
    predicates = _SplitViewPredicateMap(dict(request.predicate_values))
    forged = request.model_copy(update={"predicate_values": predicates})

    serialized = forged.model_dump(mode="json")["predicate_values"]
    assert serialized["assignment_separability_support"]["value"] is True
    assert forged.predicate_values["assignment_separability_support"].value is False

    _assert_runtime_tree_rejected(forged)


def test_runtime_rejects_request_subclass_and_incomplete_model_construct() -> None:
    _, request = runtime_fixture._request()

    class RequestSubclass(V8DerivationInput):
        pass

    subclassed = RequestSubclass.model_validate(request.model_dump(mode="python"))
    incomplete = V8DerivationInput.model_construct(experiment_block_id=request.experiment_block_id)

    _assert_runtime_tree_rejected(subclassed)
    _assert_runtime_tree_rejected(incomplete)


def test_runtime_rejects_noncanonical_conformance_bundle_tree() -> None:
    _, request = runtime_fixture._request()
    bundle = runtime_fixture.CANONICAL_BUNDLE.model_copy(update={"determinability": "DETERMINATE"})

    _assert_runtime_tree_rejected(request, bundle=bundle)


def test_causal_aggregate_rejects_every_event_outside_its_exact_block() -> None:
    _, request = runtime_fixture._request()
    payload = request.causal_aggregate.model_dump(mode="json")
    foreign = payload["event_registry"]["events"][0].copy()
    foreign.update(
        event_id="EVT-FOREIGN-UNREFERENCED",
        experiment_block_id="BLOCK-FOREIGN",
    )
    payload["event_registry"]["events"].append(foreign)

    with pytest.raises(ValidationError, match=r"event registry.*Experiment Block"):
        QueryCausalEventAggregate.model_validate(payload)


def _timing(
    subject: str,
    reference: str,
    relation: TemporalRelation,
) -> RelativeTiming:
    return RelativeTiming(
        subject_event_id=subject,
        reference_event_id=reference,
        relation=relation,
        evidence_refs=("EV-TIMING-REVIEWED",),
    )


@pytest.mark.parametrize(
    "timings",
    (
        (_timing("EVT-ASSIGN-001", "EVT-ASSIGN-001", TemporalRelation.BEFORE),),
        (
            _timing("EVT-ASSIGN-001", "EVT-APPLY-001", TemporalRelation.BEFORE),
            _timing("EVT-ASSIGN-001", "EVT-APPLY-001", TemporalRelation.BEFORE),
        ),
        (
            _timing("EVT-ASSIGN-001", "EVT-APPLY-001", TemporalRelation.BEFORE),
            _timing("EVT-ASSIGN-001", "EVT-APPLY-001", TemporalRelation.AFTER),
        ),
        (
            _timing("EVT-ASSIGN-001", "EVT-APPLY-001", TemporalRelation.BEFORE),
            _timing("EVT-APPLY-001", "EVT-ASSIGN-001", TemporalRelation.BEFORE),
        ),
        (
            _timing("EVT-ASSIGN-001", "EVT-APPLY-001", TemporalRelation.BEFORE),
            _timing("EVT-APPLY-001", "EVT-EXPOSURE-001", TemporalRelation.BEFORE),
            _timing("EVT-EXPOSURE-001", "EVT-ASSIGN-001", TemporalRelation.BEFORE),
        ),
    ),
)
def test_event_registry_rejects_incoherent_temporal_contracts(
    timings: tuple[RelativeTiming, ...],
) -> None:
    _, request = runtime_fixture._request()

    with pytest.raises(ValidationError, match="temporal"):
        EventRegistry(
            events=request.causal_aggregate.event_registry.events,
            relative_timings=timings,
        )


def test_event_registry_accepts_exact_reverse_timing_and_explicit_unknown() -> None:
    _, request = runtime_fixture._request()
    unknown = RelativeTiming(
        subject_event_id="EVT-APPLY-001",
        reference_event_id="EVT-EXPOSURE-001",
        relation=TemporalRelation.UNKNOWN,
        rationale="The reviewed sources do not order these events.",
    )

    registry = EventRegistry(
        events=request.causal_aggregate.event_registry.events,
        relative_timings=(
            _timing("EVT-ASSIGN-001", "EVT-APPLY-001", TemporalRelation.BEFORE),
            _timing("EVT-APPLY-001", "EVT-ASSIGN-001", TemporalRelation.AFTER),
            unknown,
        ),
    )

    assert registry.relative_timings[-1].relation is TemporalRelation.UNKNOWN


def _relation_scope(value: str, *, query_id: str) -> KnowledgeValue[str]:
    return KnowledgeValue[str](
        knowledge_state=KnowledgeState.PRESENT,
        value=value,
        evidence_ids=("EV-GRAPH-SCOPE",),
        query_scope_id=query_id,
    )


def _decisive_attributes(
    value: dict[str, JsonValue],
    *,
    query_id: str,
) -> KnowledgeValue[dict[str, JsonValue]]:
    return KnowledgeValue[dict[str, JsonValue]](
        knowledge_state=KnowledgeState.PRESENT,
        value=value,
        evidence_ids=("EV-GRAPH-ATTRIBUTE",),
        query_scope_id=query_id,
    )


def _not_applicable_scope(rationale: str, *, query_id: str) -> KnowledgeValue[Any]:
    return KnowledgeValue[Any](
        knowledge_state=KnowledgeState.NOT_APPLICABLE,
        rationale=rationale,
        query_scope_id=query_id,
    )


def _scoped_relation(
    *,
    relation_id: str,
    source: str,
    target: str,
    query_id: str = runtime_fixture.QUERY_ID,
    factor_id: str = "treatment",
    attributes: dict[str, JsonValue] | None = None,
    relation_type: V8GraphRelationType = V8GraphRelationType.CONTAINED_IN,
    structural_binding: bool = False,
) -> V8GraphRelation:
    factor_scope = (
        _not_applicable_scope(
            "InferentialQuery-to-block nesting is not factor-scoped.",
            query_id=query_id,
        )
        if structural_binding
        else _relation_scope(factor_id, query_id=query_id)
    )
    decisive_attributes = (
        _not_applicable_scope(
            "InferentialQuery-to-block nesting has no additional decisive attributes.",
            query_id=query_id,
        )
        if structural_binding
        else _decisive_attributes(
            attributes or {"scope_binding": "explicit"},
            query_id=query_id,
        )
    )
    fields: dict[str, object] = {
        "relation_id": relation_id,
        "relation_type": relation_type,
        "source_node_id": source,
        "target_node_id": target,
        "query_scope": _relation_scope(query_id, query_id=query_id),
        "factor_scope": factor_scope,
        "decisive_attributes": decisive_attributes,
    }
    return V8GraphRelation.model_validate(fields)


def test_graph_relation_requires_explicit_open_world_scope_and_attributes() -> None:
    with pytest.raises(ValidationError, match=r"query_scope|factor_scope"):
        V8GraphRelation(
            relation_id="REL-UNSCOPED",
            relation_type=V8GraphRelationType.CONTAINED_IN,
            source_node_id=runtime_fixture.QUERY_ID,
            target_node_id=runtime_fixture.BLOCK_ID,
        )

    relation = V8GraphRelation(
        relation_id="REL-SCOPED",
        relation_type=V8GraphRelationType.CONTAINED_IN,
        source_node_id=runtime_fixture.QUERY_ID,
        target_node_id=runtime_fixture.BLOCK_ID,
        query_scope=_relation_scope(
            runtime_fixture.QUERY_ID,
            query_id=runtime_fixture.QUERY_ID,
        ),
        factor_scope=_relation_scope(
            "treatment",
            query_id=runtime_fixture.QUERY_ID,
        ),
        decisive_attributes=_decisive_attributes(
            {"scope_binding": "explicit"},
            query_id=runtime_fixture.QUERY_ID,
        ),
    )
    assert relation.query_scope.value == runtime_fixture.QUERY_ID


def _exact_graph_view(
    *,
    relation: V8GraphRelation,
) -> ExactGraphView:
    return ExactGraphView(
        graph=V8ExperimentGraph(
            nodes=(
                V8GraphNode(node_id="UNIT-LOCAL-A", node_type=V8GraphNodeType.UNIT_INSTANCE),
                V8GraphNode(node_id="UNIT-LOCAL-B", node_type=V8GraphNodeType.UNIT_INSTANCE),
                V8GraphNode(
                    node_id=runtime_fixture.QUERY_ID,
                    node_type=V8GraphNodeType.INFERENTIAL_QUERY,
                ),
                V8GraphNode(
                    node_id="IQ-DIFFERENT",
                    node_type=V8GraphNodeType.INFERENTIAL_QUERY,
                ),
                V8GraphNode(node_id="treatment", node_type=V8GraphNodeType.FACTOR),
                V8GraphNode(node_id="different-factor", node_type=V8GraphNodeType.FACTOR),
            ),
            relations=(relation,),
        ),
        node_semantics=(
            GraphNodeSemanticIdentity(
                node_id="UNIT-LOCAL-A",
                role="contained_unit",
                semantic_key="unit:a",
            ),
            GraphNodeSemanticIdentity(
                node_id="UNIT-LOCAL-B",
                role="container_unit",
                semantic_key="unit:b",
            ),
            GraphNodeSemanticIdentity(
                node_id=runtime_fixture.QUERY_ID,
                role="primary_query",
                semantic_key="query:primary",
            ),
            GraphNodeSemanticIdentity(
                node_id="IQ-DIFFERENT",
                role="alternative_query",
                semantic_key="query:alternative",
            ),
            GraphNodeSemanticIdentity(
                node_id="treatment",
                role="factor",
                semantic_key="factor:treatment",
            ),
            GraphNodeSemanticIdentity(
                node_id="different-factor",
                role="factor",
                semantic_key="factor:different",
            ),
        ),
    )


@pytest.mark.parametrize(
    "right_relation",
    (
        _scoped_relation(
            relation_id="REL-RIGHT-FACTOR",
            source="UNIT-LOCAL-A",
            target="UNIT-LOCAL-B",
            factor_id="different-factor",
        ),
        _scoped_relation(
            relation_id="REL-RIGHT-QUERY",
            source="UNIT-LOCAL-A",
            target="UNIT-LOCAL-B",
            query_id="IQ-DIFFERENT",
        ),
        _scoped_relation(
            relation_id="REL-RIGHT-ATTRIBUTE",
            source="UNIT-LOCAL-A",
            target="UNIT-LOCAL-B",
            attributes={"scope_binding": "different"},
        ),
    ),
)
def test_exact_graph_equality_includes_edge_scope_and_decisive_attributes(
    right_relation: V8GraphRelation,
) -> None:
    left = _exact_graph_view(
        relation=_scoped_relation(
            relation_id="REL-LEFT",
            source="UNIT-LOCAL-A",
            target="UNIT-LOCAL-B",
        )
    )
    right = _exact_graph_view(relation=right_relation)

    assert exact_graph_equal(left, right) is False


def _graph_verification_report(graph: V8ExperimentGraph) -> object:
    _, request = runtime_fixture._request()
    return verify_v8_pipeline_request(
        request.model_copy(update={"graph": graph}),
        conformance_bundle=runtime_fixture.CANONICAL_BUNDLE,
    )


def _base_graph_nodes() -> tuple[V8GraphNode, V8GraphNode]:
    return (
        V8GraphNode(
            node_id=runtime_fixture.BLOCK_ID,
            node_type=V8GraphNodeType.EXPERIMENT_BLOCK,
        ),
        V8GraphNode(
            node_id=runtime_fixture.QUERY_ID,
            node_type=V8GraphNodeType.INFERENTIAL_QUERY,
        ),
    )


@pytest.mark.parametrize(
    "graph",
    (
        V8ExperimentGraph(nodes=_base_graph_nodes()),
        V8ExperimentGraph(
            nodes=_base_graph_nodes(),
            relations=(
                _scoped_relation(
                    relation_id="REL-SELF-CONTAINMENT",
                    source=runtime_fixture.QUERY_ID,
                    target=runtime_fixture.QUERY_ID,
                    relation_type=V8GraphRelationType.NESTED_IN,
                    structural_binding=True,
                ),
            ),
        ),
        V8ExperimentGraph(
            nodes=(
                *_base_graph_nodes(),
                V8GraphNode(node_id="UNIT-A", node_type=V8GraphNodeType.UNIT_INSTANCE),
                V8GraphNode(node_id="UNIT-B", node_type=V8GraphNodeType.UNIT_INSTANCE),
            ),
            relations=(
                _scoped_relation(
                    relation_id="REL-QUERY-BLOCK",
                    source=runtime_fixture.QUERY_ID,
                    target=runtime_fixture.BLOCK_ID,
                    relation_type=V8GraphRelationType.NESTED_IN,
                    structural_binding=True,
                ),
                _scoped_relation(
                    relation_id="REL-CYCLE-A-B",
                    source="UNIT-A",
                    target="UNIT-B",
                    structural_binding=True,
                ),
                _scoped_relation(
                    relation_id="REL-CYCLE-B-A",
                    source="UNIT-B",
                    target="UNIT-A",
                    structural_binding=True,
                ),
            ),
        ),
        V8ExperimentGraph(
            nodes=(
                *_base_graph_nodes(),
                V8GraphNode(
                    node_id="BLOCK-OTHER",
                    node_type=V8GraphNodeType.EXPERIMENT_BLOCK,
                ),
            ),
            relations=(
                _scoped_relation(
                    relation_id="REL-QUERY-WRONG-BLOCK",
                    source=runtime_fixture.QUERY_ID,
                    target="BLOCK-OTHER",
                    relation_type=V8GraphRelationType.NESTED_IN,
                    structural_binding=True,
                ),
            ),
        ),
    ),
)
def test_graph_topology_stops_fact_verification_before_derivation(
    graph: V8ExperimentGraph,
) -> None:
    report = _graph_verification_report(graph)

    assert report.passed is False
    assert report.failed_stage == "FACT_VERIFICATION"
    assert any(issue.code == "GRAPH_TOPOLOGY_MISMATCH" for issue in report.issues)
