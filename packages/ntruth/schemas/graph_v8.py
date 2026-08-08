"""Version-isolated PRD v8 Experiment Graph vocabulary and structural model."""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from ntruth.schemas.kernel import KernelModel, NonBlankStr


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
        known_nodes = set(node_ids)
        for relation in self.relations:
            if relation.source_node_id not in known_nodes:
                raise ValueError(f"unknown source_node_id: {relation.source_node_id}")
            if relation.target_node_id not in known_nodes:
                raise ValueError(f"unknown target_node_id: {relation.target_node_id}")
        return self


__all__ = [
    "V8ExperimentGraph",
    "V8GraphNode",
    "V8GraphNodeType",
    "V8GraphRelation",
    "V8GraphRelationType",
]
