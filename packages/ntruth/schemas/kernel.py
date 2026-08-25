"""Profile-invariant foundations for the PRD v8 Core Semantic Kernel."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

from ntruth.schemas.core import FrozenModel

KERNEL_SCHEMA_VERSION: Literal["8.0.0"] = "8.0.0"
NonBlankStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class KernelModel(FrozenModel):
    """Strict, immutable and explicitly versioned v8 contract base."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
        use_enum_values=False,
    )
    schema_version: Literal["8.0.0"] = KERNEL_SCHEMA_VERSION


class KernelIdentity(KernelModel):
    """Stable identity for a profile-invariant kernel object."""

    object_id: NonBlankStr
    object_type: NonBlankStr
    namespace: NonBlankStr = "ntruth"


def kernel_json_schemas() -> dict[str, dict[str, Any]]:
    """Return runtime-derived JSON Schemas for the Task 1 kernel contracts."""

    from pydantic import JsonValue

    from ntruth.schemas.adequacy import DesignAdequacyEvaluation
    from ntruth.schemas.block_boundary import (
        BlockBoundaryPredicate,
        BoundaryChangeReference,
        ExperimentBlockBoundaryChangeLedger,
        ExperimentBlockBoundaryChangeRecord,
        ExperimentBlockBoundaryRecord,
    )
    from ntruth.schemas.causal_context import QueryCausalContext, QueryCausalEventAggregate
    from ntruth.schemas.claims import DerivedClaim, DerivedClaimSet
    from ntruth.schemas.count_registry import (
        CanonicalCountRecord,
        CanonicalCountRegistry,
        CountInterval,
        CountScope,
        CountScopeIdentity,
    )
    from ntruth.schemas.coverage import ProfileCoverageStatement, ScenarioCoverage
    from ntruth.schemas.events import (
        ApplicationEvent,
        AssignmentEvent,
        EventRegistry,
        ExposureEvent,
        ObservationEvent,
        PoolEvent,
        RelativeTiming,
        SplitEvent,
    )
    from ntruth.schemas.execution import V8ExecutionManifest
    from ntruth.schemas.graph_v8 import V8ExperimentGraph, V8GraphNode, V8GraphRelation
    from ntruth.schemas.knowledge import KnowledgeValue
    from ntruth.schemas.prospective import (
        ConfirmationTarget,
        ExecutedDesignRecord,
        ExecutedInputLedger,
        PlanExecutionReconciliation,
        PlannedDesignRecord,
        ProspectiveArtifact,
        ProspectiveInputLedger,
        SupportEvidenceBinding,
    )
    from ntruth.schemas.query import InferentialQuery
    from ntruth.schemas.report_bundle import (
        ConflictRecord,
        HandoffItem,
        QueryReportSection,
        ReportBundle,
        VerifiedPipelineContext,
    )
    from ntruth.schemas.report_resolution import ReportResolutionOutcome
    from ntruth.schemas.support import (
        ConfirmationEvent,
        EvidenceRecord,
        RuleChallenge,
        SensitivityRecord,
        SourceRecord,
    )

    models: dict[str, type[BaseModel]] = {
        "kernel_identity": KernelIdentity,
        "knowledge_value": KnowledgeValue[JsonValue],
        "inferential_query": InferentialQuery,
        "count_interval": CountInterval,
        "count_scope_identity": CountScopeIdentity,
        "count_scope": CountScope,
        "canonical_count_record": CanonicalCountRecord,
        "canonical_count_registry": CanonicalCountRegistry,
        "assignment_event": AssignmentEvent,
        "application_event": ApplicationEvent,
        "exposure_event": ExposureEvent,
        "split_event": SplitEvent,
        "pool_event": PoolEvent,
        "observation_event": ObservationEvent,
        "relative_timing": RelativeTiming,
        "event_registry": EventRegistry,
        "query_causal_context": QueryCausalContext,
        "query_causal_event_aggregate": QueryCausalEventAggregate,
        "v8_graph_node": V8GraphNode,
        "v8_graph_relation": V8GraphRelation,
        "v8_experiment_graph": V8ExperimentGraph,
        "block_boundary_predicate": BlockBoundaryPredicate,
        "boundary_change_reference": BoundaryChangeReference,
        "experiment_block_boundary_record": ExperimentBlockBoundaryRecord,
        "experiment_block_boundary_change_record": ExperimentBlockBoundaryChangeRecord,
        "experiment_block_boundary_change_ledger": ExperimentBlockBoundaryChangeLedger,
        "source_record": SourceRecord,
        "evidence_record": EvidenceRecord,
        "confirmation_event": ConfirmationEvent,
        "sensitivity_record": SensitivityRecord,
        "rule_challenge": RuleChallenge,
        "derived_claim": DerivedClaim,
        "derived_claim_set": DerivedClaimSet,
        "profile_coverage_statement": ProfileCoverageStatement,
        "scenario_coverage": ScenarioCoverage,
        "design_adequacy_finding": DesignAdequacyEvaluation,
        "design_adequacy_evaluation": DesignAdequacyEvaluation,
        "v8_execution_manifest": V8ExecutionManifest,
        "report_resolution_outcome": ReportResolutionOutcome,
        "planned_design_record": PlannedDesignRecord,
        "executed_design_record": ExecutedDesignRecord,
        "executed_input_ledger": ExecutedInputLedger,
        "plan_execution_reconciliation": PlanExecutionReconciliation,
        "prospective_artifact": ProspectiveArtifact,
        "prospective_input_ledger": ProspectiveInputLedger,
        "support_evidence_binding": SupportEvidenceBinding,
        "confirmation_target": ConfirmationTarget,
        "conflict_record_v8": ConflictRecord,
        "handoff_item": HandoffItem,
        "query_report_section": QueryReportSection,
        "verified_pipeline_context": VerifiedPipelineContext,
        "report_bundle": ReportBundle,
    }
    return {name: model.model_json_schema(mode="validation") for name, model in models.items()}


def write_kernel_json_schemas(directory: Path) -> dict[str, Path]:
    """Write canonical runtime schemas without maintaining hand-edited duplicates."""

    directory.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for name, schema in kernel_json_schemas().items():
        path = directory / f"{name}.schema.json"
        path.write_text(
            json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        written[name] = path
    return written


__all__ = [
    "KERNEL_SCHEMA_VERSION",
    "KernelIdentity",
    "KernelModel",
    "NonBlankStr",
    "kernel_json_schemas",
    "write_kernel_json_schemas",
]
