"""Schemi stage-level per structured decoding B4 (forma, non scienza).

Più semplici del grafo completo: ``additionalProperties`` false, array vuoti
ammessi, nessun n_independent / verdict / RuleResult.

Un array vuoto = «nessun candidato estratto dal modello», non «assenza
scientificamente dimostrata».
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StageProvenanceMini(_Strict):
    stage_run_id: str = ""
    stage: str
    authority: Literal["model"] = "model"
    producer: str = "granite-constrained"
    producer_version: str = "1.0.0"


class EvidenceSpanMini(_Strict):
    evidence_id: str
    file_id: str
    text: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class EvidenceExtractionStage(_Strict):
    """Stage A: solo span di evidenza candidati."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    stage: Literal["evidence_extraction"] = "evidence_extraction"
    result_id: str
    status: Literal["complete", "partial", "failed"] = "complete"
    provenance: StageProvenanceMini
    evidence_spans: list[EvidenceSpanMini] = Field(default_factory=list)


class EntityMini(_Strict):
    node_id: str
    label: str
    node_type: str
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class CountMini(_Strict):
    count_id: str
    quantifier: Literal[
        "EXACT", "APPROXIMATE", "RANGE", "LOWER_BOUND", "UPPER_BOUND", "UNKNOWN", "NOT_REPORTED"
    ]
    value: int | None = None
    lower_bound: int | None = None
    upper_bound: int | None = None
    unit_label: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class EntityCountStage(_Strict):
    """Stage B: entità e conteggi candidati."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    stage: Literal["entity_count"] = "entity_count"
    result_id: str
    status: Literal["complete", "partial", "failed"] = "complete"
    provenance: StageProvenanceMini
    entities: list[EntityMini] = Field(default_factory=list)
    counts: list[CountMini] = Field(default_factory=list)


class RelationMini(_Strict):
    edge_id: str
    source_label: str
    target_label: str
    relation_type: Literal["nested_in", "derived_from", "other"]
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class CandidateRelationStage(_Strict):
    """Stage C: relazioni esplicite candidate."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    stage: Literal["candidate_relations"] = "candidate_relations"
    result_id: str
    status: Literal["complete", "partial", "failed"] = "complete"
    provenance: StageProvenanceMini
    relations: list[RelationMini] = Field(default_factory=list)


class FactorMini(_Strict):
    factor_id: str
    name: str
    levels: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class EndpointMini(_Strict):
    endpoint_id: str
    name: str
    evidence_ids: list[str] = Field(default_factory=list)


class MinimalCandidateGraphStage(_Strict):
    """Stage D: CandidateGraphSet *minimale* (non il grafo completo PRD)."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    stage: Literal["candidate_graph_set"] = "candidate_graph_set"
    result_id: str
    graph_set_id: str
    status: Literal["complete", "partial", "failed"] = "complete"
    provenance: StageProvenanceMini
    experiment_block_title: str = ""
    evidence_spans: list[EvidenceSpanMini] = Field(default_factory=list)
    entities: list[EntityMini] = Field(default_factory=list)
    counts: list[CountMini] = Field(default_factory=list)
    factors: list[FactorMini] = Field(default_factory=list)
    endpoints: list[EndpointMini] = Field(default_factory=list)
    relations: list[RelationMini] = Field(default_factory=list)
    # Array vuoto = nessun missing fact *emesso*, non «nulla manca scientificamente».
    missing_fact_predicates: list[str] = Field(default_factory=list)


STAGE_SCHEMA_REGISTRY: dict[str, type[BaseModel]] = {
    "evidence_extraction": EvidenceExtractionStage,
    "entity_count": EntityCountStage,
    "candidate_relations": CandidateRelationStage,
    "candidate_graph_minimal": MinimalCandidateGraphStage,
}


def stage_schema(name: str) -> type[BaseModel]:
    try:
        return STAGE_SCHEMA_REGISTRY[name]
    except KeyError as exc:
        raise KeyError(
            f"schema stage sconosciuto {name!r}; noti={sorted(STAGE_SCHEMA_REGISTRY)}"
        ) from exc


def stage_json_schema(name: str) -> dict[str, Any]:
    return stage_schema(name).model_json_schema()


STAGE_PROMPTS: dict[str, str] = {
    "evidence_extraction": (
        "Extract candidate evidence spans only. Return JSON matching EvidenceExtractionStage. "
        "Use empty evidence_spans if none. Never emit verdicts, n_independent, or statistical tests."
    ),
    "entity_count": (
        "Extract candidate entities and counts only. Return JSON matching EntityCountStage. "
        "Empty arrays mean no candidates extracted. Never invent final independent n or verdicts."
    ),
    "candidate_relations": (
        "Extract explicit nested_in / derived_from candidate relations only. "
        "Return JSON matching CandidateRelationStage. Empty relations if none explicit."
    ),
    "candidate_graph_minimal": (
        "Extract a minimal candidate graph (evidence, entities, counts, factors, endpoints, "
        "relations). Return JSON matching MinimalCandidateGraphStage. "
        "missing_fact_predicates empty means no missing-fact strings emitted, not scientific "
        "completeness. Never emit determinability, verdict, or final independent n."
    ),
}


__all__ = [
    "CandidateRelationStage",
    "CountMini",
    "EndpointMini",
    "EntityCountStage",
    "EntityMini",
    "EvidenceExtractionStage",
    "EvidenceSpanMini",
    "FactorMini",
    "MinimalCandidateGraphStage",
    "RelationMini",
    "STAGE_PROMPTS",
    "STAGE_SCHEMA_REGISTRY",
    "StageProvenanceMini",
    "stage_json_schema",
    "stage_schema",
]
