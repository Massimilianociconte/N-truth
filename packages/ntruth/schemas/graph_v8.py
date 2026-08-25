"""Version-isolated PRD v8 Experiment Graph vocabulary and structural model."""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import Field, JsonValue, model_validator

from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue


class V8GraphNodeType(StrEnum):
    EXPERIMENT_BLOCK = "ExperimentBlock"
    UNIT_TYPE = "UnitType"
    UNIT_INSTANCE = "UnitInstance"
    BIOLOGICAL_SOURCE = "BiologicalSource"
    PREPARATION = "Preparation"
    FACTOR = "Factor"
    FACTOR_LEVEL = "FactorLevel"
    CONTRAST = "Contrast"
    INFERENTIAL_QUERY = "InferentialQuery"
    ENDPOINT = "Endpoint"
    ASSIGNMENT_EVENT = "AssignmentEvent"
    APPLICATION_EVENT = "ApplicationEvent"
    EXPOSURE_EVENT = "ExposureEvent"
    SPLIT_EVENT = "SplitEvent"
    POOL_EVENT = "PoolEvent"
    OBSERVATION = "Observation"
    ANALYSIS_AGGREGATE = "AnalysisAggregate"
    MEASUREMENT_PROCESS = "MeasurementProcess"
    EVIDENCE_SPAN = "EvidenceSpan"
    COUNT_RECORD = "CountRecord"
    EXCLUSION_RECORD = "ExclusionRecord"
    CONFLICT_RECORD = "ConflictRecord"
    CONFIRMATION_EVENT = "ConfirmationEvent"
    QUESTION_RECORD = "QuestionRecord"
    CONDITION_RECORD = "ConditionRecord"
    RULE_CHALLENGE = "RuleChallenge"
    DERIVED_CLAIM = "DerivedClaim"
    SENSITIVITY_RECORD = "SensitivityRecord"
    PROFILE_COVERAGE_STATEMENT = "ProfileCoverageStatement"


class V8GraphRelationType(StrEnum):
    DERIVED_FROM = "derived_from"
    NESTED_IN = "nested_in"
    CONTAINED_IN = "contained_in"
    ALLOCATED_TO = "allocated_to"
    APPLIED_TO = "applied_to"
    EXPOSED_AS = "exposed_as"
    MEASURED_ON = "measured_on"
    OBSERVED_IN = "observed_in"
    ACQUIRED_FROM = "acquired_from"
    AGGREGATED_TO = "aggregated_to"
    BELONGS_TO_GROUP = "belongs_to_group"
    EXCLUDED_FROM = "excluded_from"
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    SPLIT_FROM = "split_from"
    POOLED_FROM = "pooled_from"
    PAIRED_WITH = "paired_with"
    MATCHED_WITH = "matched_with"
    BLOCKED_BY = "blocked_by"
    CROSSED_WITH = "crossed_with"
    SAME_SOURCE_AS = "same_source_as"
    REPEATED_MEASURE_OF = "repeated_measure_of"
    SHARES_EXPOSURE_WITH = "shares_exposure_with"
    MAY_INTERFERE_WITH = "may_interfere_with"
    GENERATED_BY = "generated_by"
    COMPUTED_FROM = "computed_from"
    SEGMENTED_INTO = "segmented_into"


class V8GraphNode(KernelModel):
    node_id: NonBlankStr
    node_type: V8GraphNodeType


class V8GraphRelation(KernelModel):
    relation_id: NonBlankStr
    relation_type: V8GraphRelationType
    source_node_id: NonBlankStr
    target_node_id: NonBlankStr
    query_scope: KnowledgeValue[NonBlankStr]
    factor_scope: KnowledgeValue[NonBlankStr]
    decisive_attributes: KnowledgeValue[dict[NonBlankStr, JsonValue]]

    @model_validator(mode="after")
    def _coherent_scope_metadata(self) -> Self:
        scoped_values = (self.query_scope, self.factor_scope, self.decisive_attributes)
        metadata = {value.query_scope_id for value in scoped_values}
        if None in metadata or len(metadata) != 1:
            raise ValueError("graph relation KnowledgeValue query scopes must match")
        if (
            self.query_scope.knowledge_state is KnowledgeState.PRESENT
            and self.query_scope.value != self.query_scope.query_scope_id
        ):
            raise ValueError("PRESENT graph query_scope must equal its query_scope_id")
        return self


class V8ExperimentGraph(KernelModel):
    nodes: tuple[V8GraphNode, ...] = Field(min_length=1)
    relations: tuple[V8GraphRelation, ...] = ()

    @model_validator(mode="after")
    def _referential_integrity(self) -> Self:
        node_ids = [node.node_id for node in self.nodes]
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("duplicate v8 graph node_id")
        relation_ids = [relation.relation_id for relation in self.relations]
        if len(set(relation_ids)) != len(relation_ids):
            raise ValueError("duplicate v8 graph relation_id")
        nodes_by_id = {node.node_id: node for node in self.nodes}
        known_nodes = set(nodes_by_id)
        for relation in self.relations:
            if relation.source_node_id not in known_nodes:
                raise ValueError(f"unknown source_node_id: {relation.source_node_id}")
            if relation.target_node_id not in known_nodes:
                raise ValueError(f"unknown target_node_id: {relation.target_node_id}")
            if relation.query_scope.knowledge_state is KnowledgeState.PRESENT:
                query_scope = relation.query_scope.value
                if not isinstance(query_scope, str):
                    raise ValueError("PRESENT query_scope must contain an identifier")
                query_node = nodes_by_id.get(query_scope)
                if (
                    query_node is None
                    or query_node.node_type is not V8GraphNodeType.INFERENTIAL_QUERY
                ):
                    raise ValueError("PRESENT query_scope must reference an InferentialQuery node")
            if relation.factor_scope.knowledge_state is KnowledgeState.PRESENT:
                factor_scope = relation.factor_scope.value
                if not isinstance(factor_scope, str):
                    raise ValueError("PRESENT factor_scope must contain an identifier")
                factor_node = nodes_by_id.get(factor_scope)
                if factor_node is None or factor_node.node_type is not V8GraphNodeType.FACTOR:
                    raise ValueError("PRESENT factor_scope must reference a Factor node")

            source = nodes_by_id[relation.source_node_id]
            target = nodes_by_id[relation.target_node_id]
            if (
                source.node_type is V8GraphNodeType.INFERENTIAL_QUERY
                and target.node_type is V8GraphNodeType.EXPERIMENT_BLOCK
            ):
                if relation.relation_type is not V8GraphRelationType.NESTED_IN:
                    raise ValueError("InferentialQuery-to-block binding requires NESTED_IN")
                if (
                    relation.query_scope.knowledge_state is not KnowledgeState.PRESENT
                    or relation.query_scope.value != source.node_id
                    or relation.factor_scope.knowledge_state is not KnowledgeState.NOT_APPLICABLE
                    or relation.decisive_attributes.knowledge_state
                    is not KnowledgeState.NOT_APPLICABLE
                ):
                    raise ValueError(
                        "InferentialQuery-to-block NESTED_IN requires PRESENT query scope "
                        "and NOT_APPLICABLE factor/attribute scopes"
                    )
        return self


__all__ = [
    "V8ExperimentGraph",
    "V8GraphNode",
    "V8GraphNodeType",
    "V8GraphRelation",
    "V8GraphRelationType",
]
