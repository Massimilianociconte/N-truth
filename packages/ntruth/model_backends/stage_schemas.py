"""Schemi stage-level per structured decoding Granite/MLX (sintassi, non scienza).

Cluster 3A — stage minimi fail-closed:

- EvidenceExtractionResult
- EntityCountResult
- FactorEndpointResult
- CandidateRelationSet

``schema_version`` = 0.1.0 e ``schema_status`` = EXPERIMENTAL finché non
esiste una versione normativa approvata (non usare 1.0.0 di default).

additionalProperties false; array vuoti ammessi (= nessun candidato estratto,
non «assenza scientificamente dimostrata»). Nessun n_independent / verdict /
RuleResult / determinability.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION: Literal["0.1.0"] = "0.1.0"
SCHEMA_STATUS: Literal["EXPERIMENTAL"] = "EXPERIMENTAL"

# Campi vietati nei payload stage (candidate-only; rules engine owns consequences).
FORBIDDEN_STAGE_FIELDS: frozenset[str] = frozenset(
    {
        "n",
        "n_independent",
        "final_independent_n",
        "verdict",
        "RuleResult",
        "rule_result",
        "determinability",
        "determinability_verdict",
        "experiment_validity",
        "statistical_test",
        "paper_quality_score",
    }
)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StageProvenanceMini(_Strict):
    stage_run_id: str = ""
    stage: str
    authority: Literal["model"] = "model"
    producer: str = "granite-structured"
    producer_version: str = "0.1.0"


class EvidenceSpanMini(_Strict):
    evidence_id: str
    file_id: str
    text: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class EvidenceExtractionResult(_Strict):
    """Stage: solo span di evidenza candidati."""

    schema_version: Literal["0.1.0"] = SCHEMA_VERSION
    schema_status: Literal["EXPERIMENTAL"] = SCHEMA_STATUS
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
        "EXACT",
        "APPROXIMATE",
        "RANGE",
        "LOWER_BOUND",
        "UPPER_BOUND",
        "UNKNOWN",
        "NOT_REPORTED",
    ]
    value: int | None = None
    lower_bound: int | None = None
    upper_bound: int | None = None
    unit_label: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class EntityCountResult(_Strict):
    """Stage: entità e conteggi candidati."""

    schema_version: Literal["0.1.0"] = SCHEMA_VERSION
    schema_status: Literal["EXPERIMENTAL"] = SCHEMA_STATUS
    stage: Literal["entity_count"] = "entity_count"
    result_id: str
    status: Literal["complete", "partial", "failed"] = "complete"
    provenance: StageProvenanceMini
    entities: list[EntityMini] = Field(default_factory=list)
    counts: list[CountMini] = Field(default_factory=list)


class FactorMini(_Strict):
    factor_id: str
    name: str
    levels: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class EndpointMini(_Strict):
    endpoint_id: str
    name: str
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class FactorEndpointResult(_Strict):
    """Stage: fattori ed endpoint candidati (senza relazioni né grafo completo)."""

    schema_version: Literal["0.1.0"] = SCHEMA_VERSION
    schema_status: Literal["EXPERIMENTAL"] = SCHEMA_STATUS
    stage: Literal["factor_endpoint"] = "factor_endpoint"
    result_id: str
    status: Literal["complete", "partial", "failed"] = "complete"
    provenance: StageProvenanceMini
    factors: list[FactorMini] = Field(default_factory=list)
    endpoints: list[EndpointMini] = Field(default_factory=list)


class RelationMini(_Strict):
    edge_id: str
    source_label: str
    target_label: str
    relation_type: Literal["nested_in", "derived_from", "other"]
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class CandidateRelationSet(_Strict):
    """Stage: relazioni esplicite candidate."""

    schema_version: Literal["0.1.0"] = SCHEMA_VERSION
    schema_status: Literal["EXPERIMENTAL"] = SCHEMA_STATUS
    stage: Literal["candidate_relations"] = "candidate_relations"
    result_id: str
    status: Literal["complete", "partial", "failed"] = "complete"
    provenance: StageProvenanceMini
    relations: list[RelationMini] = Field(default_factory=list)


# Registry chiavi stabili (nome stage) → tipo Pydantic.
STAGE_SCHEMA_REGISTRY: dict[str, type[BaseModel]] = {
    "evidence_extraction": EvidenceExtractionResult,
    "entity_count": EntityCountResult,
    "factor_endpoint": FactorEndpointResult,
    "candidate_relations": CandidateRelationSet,
}

# Alias espliciti sui nomi Result del perimetro Cluster 3A.
STAGE_RESULT_ALIASES: dict[str, type[BaseModel]] = {
    "EvidenceExtractionResult": EvidenceExtractionResult,
    "EntityCountResult": EntityCountResult,
    "FactorEndpointResult": FactorEndpointResult,
    "CandidateRelationSet": CandidateRelationSet,
}

# Array che possono ricevere null → [] solo se presenti nella allowlist.
NULL_TO_EMPTY_ARRAY_ALLOWLIST: frozenset[str] = frozenset(
    {
        "evidence_spans",
        "entities",
        "counts",
        "factors",
        "endpoints",
        "relations",
        "evidence_ids",
        "levels",
    }
)


def resolve_stage_schema(name_or_type: str | type[BaseModel]) -> type[BaseModel]:
    """Risolve uno stage schema per nome o tipo; solleva KeyError se sconosciuto."""

    if isinstance(name_or_type, type) and issubclass(name_or_type, BaseModel):
        return name_or_type
    if not isinstance(name_or_type, str):
        raise TypeError(f"schema non supportato: {type(name_or_type)!r}")
    key = name_or_type.strip()
    if key in STAGE_SCHEMA_REGISTRY:
        return STAGE_SCHEMA_REGISTRY[key]
    if key in STAGE_RESULT_ALIASES:
        return STAGE_RESULT_ALIASES[key]
    raise KeyError(
        f"schema stage sconosciuto {key!r}; "
        f"noti={sorted(STAGE_SCHEMA_REGISTRY) + sorted(STAGE_RESULT_ALIASES)}"
    )


def stage_schema(name: str) -> type[BaseModel]:
    return resolve_stage_schema(name)


def stage_json_schema(name: str) -> dict[str, Any]:
    return stage_schema(name).model_json_schema()


def schema_identity(model_cls: type[BaseModel]) -> dict[str, str]:
    """Nome e versione dichiarati dallo schema stage (senza claim scientifici)."""

    fields = getattr(model_cls, "model_fields", {})
    version = "0.1.0"
    status = "EXPERIMENTAL"
    stage = model_cls.__name__
    if "schema_version" in fields:
        default = fields["schema_version"].default
        if default is not None:
            version = str(default)
    if "schema_status" in fields:
        default = fields["schema_status"].default
        if default is not None:
            status = str(default)
    if "stage" in fields:
        default = fields["stage"].default
        if default is not None:
            stage = str(default)
    return {
        "schema_name": model_cls.__name__,
        "schema_version": version,
        "schema_status": status,
        "stage": stage,
    }


STAGE_PROMPTS: dict[str, str] = {
    "evidence_extraction": (
        "Extract candidate evidence spans only. Return JSON matching "
        "EvidenceExtractionResult schema_version 0.1.0 EXPERIMENTAL. "
        "Use empty evidence_spans if none. Never emit verdicts, n_independent, "
        "RuleResult, or determinability."
    ),
    "entity_count": (
        "Extract candidate entities and counts only. Return JSON matching "
        "EntityCountResult schema_version 0.1.0 EXPERIMENTAL. "
        "Empty arrays mean no candidates extracted. Never invent final independent n."
    ),
    "factor_endpoint": (
        "Extract candidate experimental factors and endpoints only. Return JSON "
        "matching FactorEndpointResult schema_version 0.1.0 EXPERIMENTAL. "
        "Empty arrays if none. Never emit allocation, independence, or verdicts."
    ),
    "candidate_relations": (
        "Extract explicit nested_in / derived_from candidate relations only. "
        "Return JSON matching CandidateRelationSet schema_version 0.1.0 EXPERIMENTAL. "
        "Empty relations if none explicit."
    ),
}


__all__ = [
    "FORBIDDEN_STAGE_FIELDS",
    "NULL_TO_EMPTY_ARRAY_ALLOWLIST",
    "SCHEMA_STATUS",
    "SCHEMA_VERSION",
    "STAGE_PROMPTS",
    "STAGE_RESULT_ALIASES",
    "STAGE_SCHEMA_REGISTRY",
    "CandidateRelationSet",
    "CountMini",
    "EndpointMini",
    "EntityCountResult",
    "EntityMini",
    "EvidenceExtractionResult",
    "EvidenceSpanMini",
    "FactorEndpointResult",
    "FactorMini",
    "RelationMini",
    "StageProvenanceMini",
    "resolve_stage_schema",
    "schema_identity",
    "stage_json_schema",
    "stage_schema",
]
