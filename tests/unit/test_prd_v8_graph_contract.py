"""Version-isolated PRD v8 Experiment Graph vocabulary and models."""

from __future__ import annotations

import pytest
from pydantic import JsonValue, ValidationError

from ntruth.schemas.graph_v8 import (
    V8ExperimentGraph,
    V8GraphNode,
    V8GraphNodeType,
    V8GraphRelation,
    V8GraphRelationType,
)
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue


def test_v8_node_vocabulary_equals_section_8_4_minimum() -> None:
    assert {node_type.value for node_type in V8GraphNodeType} == {
        "ExperimentBlock",
        "UnitType",
        "UnitInstance",
        "BiologicalSource",
        "Preparation",
        "Factor",
        "FactorLevel",
        "Contrast",
        "InferentialQuery",
        "Endpoint",
        "AssignmentEvent",
        "ApplicationEvent",
        "ExposureEvent",
        "SplitEvent",
        "PoolEvent",
        "Observation",
        "AnalysisAggregate",
        "MeasurementProcess",
        "EvidenceSpan",
        "CountRecord",
        "ExclusionRecord",
        "ConflictRecord",
        "ConfirmationEvent",
        "QuestionRecord",
        "ConditionRecord",
        "RuleChallenge",
        "DerivedClaim",
        "SensitivityRecord",
        "ProfileCoverageStatement",
    }


def test_v8_relation_vocabulary_equals_section_8_5() -> None:
    assert {relation.value for relation in V8GraphRelationType} == {
        "derived_from",
        "nested_in",
        "contained_in",
        "allocated_to",
        "applied_to",
        "exposed_as",
        "measured_on",
        "observed_in",
        "acquired_from",
        "aggregated_to",
        "belongs_to_group",
        "excluded_from",
        "supports",
        "contradicts",
        "split_from",
        "pooled_from",
        "paired_with",
        "matched_with",
        "blocked_by",
        "crossed_with",
        "same_source_as",
        "repeated_measure_of",
        "shares_exposure_with",
        "may_interfere_with",
        "generated_by",
        "computed_from",
        "segmented_into",
    }
    assert V8GraphRelationType.CONTAINED_IN is not V8GraphRelationType.DERIVED_FROM


def test_v8_experiment_graph_is_versioned_and_referentially_closed() -> None:
    block = V8GraphNode(node_id="EB-01", node_type=V8GraphNodeType.EXPERIMENT_BLOCK)
    query = V8GraphNode(node_id="IQ-01", node_type=V8GraphNodeType.INFERENTIAL_QUERY)
    relation = V8GraphRelation(
        relation_id="REL-01",
        relation_type=V8GraphRelationType.NESTED_IN,
        source_node_id="IQ-01",
        target_node_id="EB-01",
        query_scope=KnowledgeValue[str](
            knowledge_state=KnowledgeState.PRESENT,
            value="IQ-01",
            evidence_ids=("EV-GRAPH-01",),
            query_scope_id="IQ-01",
        ),
        factor_scope=KnowledgeValue[str](
            knowledge_state=KnowledgeState.NOT_APPLICABLE,
            rationale="InferentialQuery nesting is not factor-scoped.",
            query_scope_id="IQ-01",
        ),
        decisive_attributes=KnowledgeValue[dict[str, JsonValue]](
            knowledge_state=KnowledgeState.NOT_APPLICABLE,
            rationale="InferentialQuery nesting has no additional attributes.",
            query_scope_id="IQ-01",
        ),
    )
    graph = V8ExperimentGraph(nodes=(block, query), relations=(relation,))
    assert graph.schema_version == "8.0.0"

    dangling = relation.model_copy(update={"target_node_id": "EB-MISSING"})
    with pytest.raises(ValidationError, match="unknown target_node_id"):
        V8ExperimentGraph(nodes=(block, query), relations=(dangling,))


def test_v7_graph_values_cross_the_version_boundary_only_via_adapter() -> None:
    from ntruth.migrations import (
        migrate_v7_graph_node_type,
        migrate_v7_graph_relation_type,
    )
    from ntruth.schemas.graph import NodeType, RelationType

    node = migrate_v7_graph_node_type(NodeType.EXPERIMENT_BLOCK)
    relation = migrate_v7_graph_relation_type(RelationType.NESTED_IN)

    assert node.value is V8GraphNodeType.EXPERIMENT_BLOCK
    assert relation.value is V8GraphRelationType.NESTED_IN
    assert node.lineage[0].source_contract == "ntruth-experiment-graph/v7"
    assert node.lineage[0].target_contract == "ntruth-experiment-graph/8.0.0"

    unsupported = migrate_v7_graph_node_type(NodeType.WELL)
    assert unsupported.value is None
    assert unsupported.requires_scientific_review
