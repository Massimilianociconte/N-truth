"""Contratto JSON candidate-only e backend-agnostic del parser AI (PRD v8 §13).

Il contratto descrive soltanto candidate facts. Non contiene verdetti e non
consente al modello di scrivere nel grafo scientifico confermato.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from typing import Any, Literal, cast

from pydantic import BaseModel, Field, JsonValue, model_validator

from ntruth.mvt_a.stage_schema import (
    ALLOWED_CANDIDATE_COUNT_KINDS,
    StageCoverage,
    assert_no_final_scientific_fields,
)
from ntruth.schemas.block_boundary import BlockBoundaryPredicate
from ntruth.schemas.core import Determinability, EvidenceType, FrozenModel
from ntruth.schemas.document import DocumentIR, StatisticalCodeArtifact
from ntruth.schemas.graph import ALLOCATABLE_NODE_TYPES, NodeType, RelationType

PARSER_AI_CONTRACT_VERSION = "8.0.0"
PARSER_AI_V3_CONTRACT_VERSION = "2.0.0"

type ConfidenceScore = float


def _raw_candidate_contract_tree(
    value: object,
    *,
    seen: set[int] | None = None,
) -> object:
    """Expose public raw model state before Pydantic can omit invalid extras."""

    if seen is None:
        seen = set()
    tracked = isinstance(value, (BaseModel, Mapping, list, tuple, set, frozenset))
    identity = id(value)
    if tracked:
        if identity in seen:
            raise ValueError("candidate runtime tree contains a recursive container cycle")
        seen.add(identity)
    try:
        if isinstance(value, BaseModel):
            raw_values = value.__dict__
            if type(raw_values) is not dict:
                raise ValueError(
                    "candidate runtime model state must be exact builtin dict, "
                    f"got {type(raw_values).__name__}"
                )
            declared_fields = type(value).model_fields
            payload: dict[object, object] = {
                field_name: _raw_candidate_contract_tree(raw_values[field_name], seen=seen)
                for field_name in declared_fields
                if field_name in raw_values
            }
            for field_name in raw_values:
                if not isinstance(field_name, str):
                    raise ValueError(
                        f"candidate runtime model state key {field_name!r} is not canonical"
                    )
                if field_name in declared_fields or field_name.startswith("_"):
                    continue
                raise ValueError(
                    "candidate runtime model has non-canonical undeclared public field "
                    f"{field_name!r}"
                )
            extra_values = value.__pydantic_extra__
            if extra_values is not None:
                if type(extra_values) is not dict:
                    raise ValueError(
                        "candidate runtime container type for Pydantic extras must be "
                        f"exact builtin dict, got {type(extra_values).__name__}"
                    )
                if extra_values:
                    extra_field = next(iter(extra_values))
                    raise ValueError(
                        "candidate runtime model has non-canonical undeclared Pydantic "
                        f"extra field {extra_field!r}"
                    )
                raise ValueError(
                    "candidate runtime model has a non-canonical empty Pydantic extra store"
                )
            return payload
        if isinstance(value, Mapping):
            if type(value) is not dict:
                raise ValueError(
                    "candidate runtime container type must be exact builtin dict, "
                    f"got {type(value).__name__}"
                )
            mapping_payload: dict[object, object] = {}
            for key, item in value.items():
                raw_key = _raw_candidate_contract_tree(key, seen=seen)
                raw_item = _raw_candidate_contract_tree(item, seen=seen)
                try:
                    mapping_payload[raw_key] = raw_item
                except TypeError as exc:
                    raise ValueError("candidate runtime mapping key is not canonical") from exc
            return mapping_payload
        if isinstance(value, (list, tuple, set, frozenset)):
            if type(value) not in {list, tuple, set, frozenset}:
                raise ValueError(
                    "candidate runtime container type must be an exact builtin, "
                    f"got {type(value).__name__}"
                )
            return tuple(_raw_candidate_contract_tree(item, seen=seen) for item in value)
        if isinstance(value, Enum):
            enum_state = value.__dict__
            if type(enum_state) is not dict:
                raise ValueError(
                    "candidate runtime enum state must be exact builtin dict, "
                    f"got {type(enum_state).__name__}"
                )
            public_enum_fields = tuple(
                field_name
                for field_name in enum_state
                if not isinstance(field_name, str) or not field_name.startswith("_")
            )
            if public_enum_fields:
                raise ValueError(
                    f"candidate runtime enum has non-canonical public state {public_enum_fields!r}"
                )
            return value
        if isinstance(value, (str, int, float, bool, bytes)) and type(value) not in {
            str,
            int,
            float,
            bool,
            bytes,
        }:
            raise ValueError(
                "candidate runtime scalar type must be an exact builtin or canonical enum, "
                f"got {type(value).__name__}"
            )
        return value
    finally:
        if tracked:
            seen.remove(identity)


def _assert_exact_candidate_model_types(
    actual: object,
    canonical: object,
    *,
    path: str = "$",
    seen: set[tuple[int, int]] | None = None,
) -> None:
    """Reject non-canonical Pydantic runtime types anywhere in the candidate tree."""

    if seen is None:
        seen = set()
    identity = (id(actual), id(canonical))
    if identity in seen:
        return
    seen.add(identity)
    if isinstance(canonical, BaseModel):
        if type(actual) is not type(canonical):
            raise ValueError(
                f"candidate runtime type at {path} must be exact canonical "
                f"{type(canonical).__name__}, got {type(actual).__name__}"
            )
        actual_values = actual.__dict__
        canonical_values = canonical.__dict__
        for field_name in type(canonical).model_fields:
            if field_name not in actual_values or field_name not in canonical_values:
                raise ValueError(f"candidate runtime field {path}.{field_name} is not canonical")
            _assert_exact_candidate_model_types(
                actual_values[field_name],
                canonical_values[field_name],
                path=f"{path}.{field_name}",
                seen=seen,
            )
        return
    if type(canonical) is dict:
        if type(actual) is not dict or len(actual) != len(canonical):
            raise ValueError(f"candidate runtime mapping at {path} is not canonical")
        unmatched_mapping_items = list(canonical.items())
        for index, (actual_key, actual_item) in enumerate(actual.items()):
            match_index = next(
                (
                    candidate_index
                    for candidate_index, (canonical_key, _) in enumerate(unmatched_mapping_items)
                    if type(actual_key) is type(canonical_key) and actual_key == canonical_key
                ),
                None,
            )
            if match_index is None:
                raise ValueError(f"candidate runtime mapping key at {path} is not canonical")
            canonical_key, canonical_item = unmatched_mapping_items.pop(match_index)
            _assert_exact_candidate_model_types(
                actual_key,
                canonical_key,
                path=f"{path}.<key:{index}>",
                seen=seen,
            )
            _assert_exact_candidate_model_types(
                actual_item,
                canonical_item,
                path=f"{path}[{canonical_key!r}]",
                seen=seen,
            )
        return
    if type(canonical) in {list, tuple}:
        if type(actual) is not type(canonical):
            raise ValueError(f"candidate runtime container at {path} is not canonical")
        actual_sequence = cast(list[object] | tuple[object, ...], actual)
        canonical_sequence = cast(list[object] | tuple[object, ...], canonical)
        if len(actual_sequence) != len(canonical_sequence):
            raise ValueError(f"candidate runtime container at {path} is not canonical")
        for index, (actual_item, canonical_item) in enumerate(
            zip(actual_sequence, canonical_sequence, strict=True)
        ):
            _assert_exact_candidate_model_types(
                actual_item,
                canonical_item,
                path=f"{path}[{index}]",
                seen=seen,
            )
        return
    if type(canonical) in {set, frozenset}:
        if type(actual) is not type(canonical):
            raise ValueError(f"candidate runtime container at {path} is not canonical")
        actual_set = cast(set[object] | frozenset[object], actual)
        canonical_set = cast(set[object] | frozenset[object], canonical)
        if len(actual_set) != len(canonical_set):
            raise ValueError(f"candidate runtime container at {path} is not canonical")
        unmatched_set_items = list(canonical_set)
        for index, actual_item in enumerate(actual_set):
            match_index = next(
                (
                    candidate_index
                    for candidate_index, canonical_item in enumerate(unmatched_set_items)
                    if actual_item == canonical_item
                ),
                None,
            )
            if match_index is None:
                raise ValueError(f"candidate runtime set item at {path}[{index}] is not canonical")
            canonical_item = unmatched_set_items.pop(match_index)
            _assert_exact_candidate_model_types(
                actual_item,
                canonical_item,
                path=f"{path}[{index}]",
                seen=seen,
            )
        return
    if type(actual) is not type(canonical):
        raise ValueError(
            f"candidate runtime type at {path} must be exact canonical "
            f"{type(canonical).__name__}, got {type(actual).__name__}"
        )


class ParserAISectionInput(FrozenModel):
    section_id: str
    role: str
    title: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    text: str

    @model_validator(mode="after")
    def _valid_coordinates(self) -> ParserAISectionInput:
        if self.end < self.start:
            raise ValueError("section input: end < start")
        return self


class ParserAIDocumentInput(FrozenModel):
    file_id: str
    filename: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    text: str
    sections: tuple[ParserAISectionInput, ...] = ()


class ParserAITableInput(FrozenModel):
    table_id: str
    file_id: str
    name: str
    columns: tuple[str, ...] = ()
    rows: tuple[dict[str, str], ...] = ()


class ParserAIInput(FrozenModel):
    """Input serializzabile con le chiavi stabilite dal PRD."""

    contract_version: Literal["2.0.0"] = "2.0.0"
    documents: tuple[ParserAIDocumentInput, ...] = ()
    tables: tuple[ParserAITableInput, ...] = ()
    metadata: dict[str, JsonValue] = Field(default_factory=dict)
    statistical_code: tuple[StatisticalCodeArtifact, ...] = ()
    domain_hint: str | None = None
    language: str = "en"

    @model_validator(mode="after")
    def _unique_and_referential(self) -> ParserAIInput:
        document_ids = [document.file_id for document in self.documents]
        code_file_ids = [artifact.file_id for artifact in self.statistical_code]
        if len(document_ids) != len(set(document_ids)):
            raise ValueError("document file_id duplicati")
        if len(code_file_ids) != len(set(code_file_ids)):
            raise ValueError("statistical_code file_id duplicati")
        if set(document_ids) & set(code_file_ids):
            raise ValueError("uno script non puo essere duplicato anche in documents")
        known_file_ids = set(document_ids) | set(code_file_ids)
        table_ids = [table.table_id for table in self.tables]
        if len(table_ids) != len(set(table_ids)):
            raise ValueError("table_id duplicati")
        missing = {table.file_id for table in self.tables} - known_file_ids
        if missing:
            raise ValueError(f"tabelle riferite a file sconosciuti: {sorted(missing)}")
        return self

    @classmethod
    def from_document_ir(
        cls,
        document_ir: DocumentIR,
        *,
        metadata: Mapping[str, JsonValue] | None = None,
        domain_hint: str | None = None,
        language: str = "en",
    ) -> ParserAIInput:
        """Adapter deterministico dal Document IR, senza chiamare alcun modello."""

        code_file_ids = {artifact.file_id for artifact in document_ir.statistical_code}
        documents = []
        for source in document_ir.files:
            if source.id in code_file_ids:
                continue
            sections = tuple(
                ParserAISectionInput(
                    section_id=section.id,
                    role=section.role,
                    title=section.title,
                    start=section.start,
                    end=section.end,
                    text=document_ir.snippet(source.id, section.start, section.end),
                )
                for section in document_ir.sections
                if section.file_id == source.id
            )
            documents.append(
                ParserAIDocumentInput(
                    file_id=source.id,
                    filename=source.filename,
                    sha256=source.sha256,
                    text=document_ir.texts.get(source.id, ""),
                    sections=sections,
                )
            )
        tables = tuple(
            ParserAITableInput(
                table_id=table.id,
                file_id=table.file_id,
                name=table.name,
                columns=table.columns,
                rows=table.rows,
            )
            for table in document_ir.tables
        )
        return cls(
            documents=tuple(documents),
            tables=tables,
            metadata=dict(metadata or {}),
            statistical_code=document_ir.statistical_code,
            domain_hint=domain_hint,
            language=language,
        )


class NodeOntologyValue(FrozenModel):
    value: NodeType | Literal["OTHER"]
    original_text: str | None = None

    @model_validator(mode="after")
    def _other_keeps_original(self) -> NodeOntologyValue:
        if self.value == "OTHER" and not self.original_text:
            raise ValueError("NodeType OTHER richiede original_text")
        return self


class RelationOntologyValue(FrozenModel):
    value: RelationType | Literal["OTHER"]
    original_text: str | None = None

    @model_validator(mode="after")
    def _other_keeps_original(self) -> RelationOntologyValue:
        if self.value == "OTHER" and not self.original_text:
            raise ValueError("RelationType OTHER richiede original_text")
        return self


class ParserAIEvidenceSpan(FrozenModel):
    evidence_id: str
    file_id: str
    evidence_type: EvidenceType
    text: str
    confidence: ConfidenceScore = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    section_id: str | None = None
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=0)
    table_id: str | None = None
    row: int | None = Field(default=None, ge=0)
    column: str | None = None
    code_artifact_id: str | None = None

    @model_validator(mode="after")
    def _one_complete_locator(self) -> ParserAIEvidenceSpan:
        text_locator = self.start is not None or self.end is not None
        cell_locator = self.table_id is not None or self.row is not None or self.column is not None
        if text_locator and (self.start is None or self.end is None):
            raise ValueError("evidence span richiede start e end")
        if self.start is not None and self.end is not None and self.end <= self.start:
            raise ValueError("evidence span: end deve essere > start")
        if cell_locator and (self.table_id is None or self.row is None or self.column is None):
            raise ValueError("evidence cell richiede table_id, row e column")
        if text_locator == cell_locator:
            raise ValueError("evidence richiede esattamente un locator testuale o cella")
        if self.evidence_type is EvidenceType.STATISTICAL_CODE and not self.code_artifact_id:
            raise ValueError("STATISTICAL_CODE richiede code_artifact_id")
        return self


class CandidateFact(FrozenModel):
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    confidence: ConfidenceScore = Field(ge=0.0, le=1.0, allow_inf_nan=False)

    @model_validator(mode="after")
    def _unique_evidence(self) -> CandidateFact:
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("evidence_ids duplicati")
        return self


class CandidateExperimentBlock(CandidateFact):
    block_id: str
    title: str


class CandidateBlockBoundary(CandidateFact):
    """Router proposal only; ``rationale`` is descriptive and never decisive."""

    block_id: str
    boundary_predicates: tuple[BlockBoundaryPredicate, ...] = Field(min_length=1)
    rationale: str

    @model_validator(mode="after")
    def _described_candidate(self) -> CandidateBlockBoundary:
        if not self.block_id.strip() or not self.rationale.strip():
            raise ValueError("block boundary candidate requires block_id and rationale")
        criteria = tuple(predicate.criterion for predicate in self.boundary_predicates)
        if len(criteria) != len(set(criteria)):
            raise ValueError(
                "block boundary criterion must be unique; contradictory states are forbidden"
            )
        return self


class CandidateNode(CandidateFact):
    node_id: str
    block_id: str
    node_type: NodeOntologyValue
    label: str


class CandidateEdge(CandidateFact):
    edge_id: str
    block_id: str
    source_id: str
    target_id: str
    relation_type: RelationOntologyValue


class CandidateFactor(CandidateFact):
    factor_id: str
    block_id: str
    name: str
    levels: tuple[str, ...] = ()
    allocation_level: NodeOntologyValue | None
    application_level: NodeOntologyValue | None

    @model_validator(mode="after")
    def _levels_are_units(self) -> CandidateFactor:
        for field_name, level in (
            ("allocation_level", self.allocation_level),
            ("application_level", self.application_level),
        ):
            if (
                level is not None
                and level.value != "OTHER"
                and level.value not in ALLOCATABLE_NODE_TYPES
            ):
                raise ValueError(f"{field_name} non e un NodeType allocabile")
        return self


class CandidateEndpoint(CandidateFact):
    endpoint_id: str
    block_id: str
    name: str


class CandidateContrast(CandidateFact):
    contrast_id: str
    block_id: str
    factor_ids: tuple[str, ...] = Field(min_length=1)
    compared_levels: tuple[str, ...] = Field(min_length=2)
    endpoint_ids: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _minimum_is_explicit(self) -> CandidateContrast:
        for field_name, values in (
            ("factor_ids", self.factor_ids),
            ("compared_levels", self.compared_levels),
            ("endpoint_ids", self.endpoint_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} contiene valori duplicati")
        return self


class CandidateEstimand(CandidateFact):
    estimand_id: str
    block_id: str
    factor_ids: tuple[str, ...] = Field(min_length=1)
    contrast_id: str | None = None
    endpoint_id: str
    effect_measure: str
    target_population_or_unit: str
    generalization_level: str
    timepoint: str | None = None
    condition: str | None = None

    @model_validator(mode="after")
    def _minimum_is_explicit(self) -> CandidateEstimand:
        for field_name, value in (
            ("endpoint_id", self.endpoint_id),
            ("effect_measure", self.effect_measure),
            ("target_population_or_unit", self.target_population_or_unit),
            ("generalization_level", self.generalization_level),
        ):
            if not value.strip():
                raise ValueError(f"estimand senza {field_name}")
        if len(self.factor_ids) != len(set(self.factor_ids)):
            raise ValueError("estimand factor_ids duplicati")
        return self


class DeterminabilityAssessmentV3(FrozenModel):
    status: Determinability
    rationale: str
    confidence: ConfidenceScore = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _determinate_requires_evidence(self) -> DeterminabilityAssessmentV3:
        if self.status is Determinability.DETERMINATE and not self.evidence_ids:
            raise ValueError("DETERMINATE richiede evidence_ids")
        return self


class CandidateAlternative(CandidateFact):
    alternative_id: str
    block_id: str
    description: str
    candidate_node_ids: tuple[str, ...] = ()
    candidate_edge_ids: tuple[str, ...] = ()


class ClarificationQuestion(FrozenModel):
    question_id: str
    block_id: str
    question: str
    resolves_candidate_ids: tuple[str, ...] = ()
    rationale: str


class ParserAIModelMetadataV3(FrozenModel):
    adapter_name: str
    model_name: str
    model_version: str
    model_checksum: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    prompt_template_version: str
    contract_version: Literal["2.0.0"] = "2.0.0"
    local_execution: bool = True


class ParserAIOutputV3(FrozenModel):
    """Deprecated PRD-v3 output accepted only by the named v3 adapter."""

    contract_version: Literal["2.0.0"] = "2.0.0"
    experiment_blocks: tuple[CandidateExperimentBlock, ...] = ()
    evidence_spans: tuple[ParserAIEvidenceSpan, ...] = ()
    candidate_nodes: tuple[CandidateNode, ...] = ()
    candidate_edges: tuple[CandidateEdge, ...] = ()
    factors: tuple[CandidateFactor, ...] = ()
    endpoints: tuple[CandidateEndpoint, ...] = ()
    contrasts: tuple[CandidateContrast, ...] = ()
    candidate_estimands: tuple[CandidateEstimand, ...] = ()
    determinability: DeterminabilityAssessmentV3
    alternatives: tuple[CandidateAlternative, ...] = ()
    clarification_questions: tuple[ClarificationQuestion, ...] = ()
    model_metadata: ParserAIModelMetadataV3

    @model_validator(mode="after")
    def _referential_integrity(self) -> ParserAIOutputV3:
        evidence_by_id = _unique_map(self.evidence_spans, "evidence_id")
        blocks = _unique_map(self.experiment_blocks, "block_id")
        nodes = _unique_map(self.candidate_nodes, "node_id")
        edges = _unique_map(self.candidate_edges, "edge_id")
        factors = _unique_map(self.factors, "factor_id")
        endpoints = _unique_map(self.endpoints, "endpoint_id")
        contrasts = _unique_map(self.contrasts, "contrast_id")
        estimands = _unique_map(self.candidate_estimands, "estimand_id")
        _unique_map(self.alternatives, "alternative_id")
        questions = _unique_map(self.clarification_questions, "question_id")

        candidates: tuple[CandidateFact, ...] = (
            *self.experiment_blocks,
            *self.candidate_nodes,
            *self.candidate_edges,
            *self.factors,
            *self.endpoints,
            *self.contrasts,
            *self.candidate_estimands,
            *self.alternatives,
        )
        for candidate in candidates:
            _require_subset(candidate.evidence_ids, evidence_by_id, "evidence_id")
        _require_subset(self.determinability.evidence_ids, evidence_by_id, "evidence_id")
        for node in self.candidate_nodes:
            _require_subset((node.block_id,), blocks, "block_id")
        for candidate_edge in self.candidate_edges:
            _require_subset((candidate_edge.block_id,), blocks, "block_id")
        for factor in self.factors:
            _require_subset((factor.block_id,), blocks, "block_id")
        for endpoint in self.endpoints:
            _require_subset((endpoint.block_id,), blocks, "block_id")
        for contrast in self.contrasts:
            _require_subset((contrast.block_id,), blocks, "block_id")
            _require_subset(contrast.factor_ids, factors, "factor_id")
            _require_subset(contrast.endpoint_ids, endpoints, "endpoint_id")
            if any(
                factors[factor_id].block_id != contrast.block_id
                for factor_id in contrast.factor_ids
            ):
                raise ValueError("contrasto riferito a factor di un altro experiment block")
            if any(
                endpoints[endpoint_id].block_id != contrast.block_id
                for endpoint_id in contrast.endpoint_ids
            ):
                raise ValueError("contrasto riferito a endpoint di un altro experiment block")
        for edge in self.candidate_edges:
            _require_subset((edge.source_id, edge.target_id), nodes, "node_id")
            if any(
                nodes[node_id].block_id != edge.block_id
                for node_id in (edge.source_id, edge.target_id)
            ):
                raise ValueError("edge riferito a nodi di un altro experiment block")
            relation = edge.relation_type.value
            if relation in {
                RelationType.ASSIGNED_TO,
                RelationType.ALLOCATED_TO,
                RelationType.RANDOMIZED_AT,
                RelationType.APPLIED_TO,
            } and any(
                evidence_by_id[evidence_id].evidence_type is EvidenceType.STATISTICAL_CODE
                for evidence_id in edge.evidence_ids
            ):
                raise ValueError("STATISTICAL_CODE non puo sostenere una relazione di allocazione")
        for estimand in self.candidate_estimands:
            _require_subset((estimand.block_id,), blocks, "block_id")
            _require_subset(estimand.factor_ids, factors, "factor_id")
            _require_subset((estimand.endpoint_id,), endpoints, "endpoint_id")
            if any(
                factors[factor_id].block_id != estimand.block_id
                for factor_id in estimand.factor_ids
            ):
                raise ValueError("estimand riferito a factor di un altro experiment block")
            if endpoints[estimand.endpoint_id].block_id != estimand.block_id:
                raise ValueError("estimand riferito a endpoint di un altro experiment block")
            if estimand.contrast_id is not None:
                _require_subset((estimand.contrast_id,), contrasts, "contrast_id")
                contrast = contrasts[estimand.contrast_id]
                if contrast.block_id != estimand.block_id:
                    raise ValueError("estimand riferito a contrasto di un altro experiment block")
                if not set(contrast.factor_ids).issubset(estimand.factor_ids):
                    raise ValueError("estimand non copre tutti i factor_ids del contrasto")
        candidate_ids = (
            set(nodes)
            | set(edges)
            | set(factors)
            | set(endpoints)
            | set(contrasts)
            | set(estimands)
        )
        candidate_count = sum(
            len(items) for items in (nodes, edges, factors, endpoints, contrasts, estimands)
        )
        if len(candidate_ids) != candidate_count:
            raise ValueError("candidate_id duplicati tra tipi diversi")
        candidate_blocks = {
            **{item_id: item.block_id for item_id, item in nodes.items()},
            **{item_id: item.block_id for item_id, item in edges.items()},
            **{item_id: item.block_id for item_id, item in factors.items()},
            **{item_id: item.block_id for item_id, item in endpoints.items()},
            **{item_id: item.block_id for item_id, item in contrasts.items()},
            **{item_id: item.block_id for item_id, item in estimands.items()},
        }
        for alternative in self.alternatives:
            _require_subset((alternative.block_id,), blocks, "block_id")
            _require_subset(alternative.candidate_node_ids, nodes, "node_id")
            _require_subset(alternative.candidate_edge_ids, edges, "edge_id")
            referenced = (*alternative.candidate_node_ids, *alternative.candidate_edge_ids)
            if any(candidate_blocks[item_id] != alternative.block_id for item_id in referenced):
                raise ValueError("alternativa riferita a candidate di un altro experiment block")
        for question in self.clarification_questions:
            _require_subset((question.block_id,), blocks, "block_id")
            _require_subset(question.resolves_candidate_ids, candidate_ids, "candidate_id")
            if any(
                candidate_blocks[item_id] != question.block_id
                for item_id in question.resolves_candidate_ids
            ):
                raise ValueError("domanda riferita a candidate di un altro experiment block")
        if self.model_metadata.contract_version != self.contract_version:
            raise ValueError("model_metadata contract_version non coerente")
        if questions and not blocks:
            raise ValueError("clarification questions senza experiment block")
        return self


class CandidateCount(CandidateFact):
    count_id: str
    block_id: str
    kind: str
    candidate_value: int | float | str
    raw_text: str

    @model_validator(mode="after")
    def _candidate_kind_only(self) -> CandidateCount:
        if self.kind not in ALLOWED_CANDIDATE_COUNT_KINDS:
            raise ValueError(f"unrecognised candidate count kind: {self.kind!r}")
        return self


class CandidateEvent(CandidateFact):
    event_id: str
    block_id: str
    event_type: str
    participant_candidate_ids: tuple[str, ...] = ()


class CandidateGraph(CandidateFact):
    graph_id: str
    block_id: str
    candidate_node_ids: tuple[str, ...] = ()
    candidate_edge_ids: tuple[str, ...] = ()
    candidate_event_ids: tuple[str, ...] = ()


class MissingPredicateCandidate(FrozenModel):
    predicate_name: str
    block_id: str
    rationale: str
    evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _described(self) -> MissingPredicateCandidate:
        if not self.predicate_name.strip() or not self.rationale.strip():
            raise ValueError("missing predicate requires a name and rationale")
        return self


class ParserModelMetadata(FrozenModel):
    adapter_name: str
    model_name: str
    model_version: str
    model_checksum: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    prompt_template_version: str
    contract_version: Literal["8.0.0"] = "8.0.0"
    local_execution: bool = True


class ParserCandidateOutput(FrozenModel):
    """Canonical v8 parser output: candidates and coverage, never final claims."""

    contract_version: Literal["8.0.0"] = "8.0.0"
    experiment_blocks: tuple[CandidateExperimentBlock, ...] = ()
    block_boundaries: tuple[CandidateBlockBoundary, ...] = ()
    evidence_spans: tuple[ParserAIEvidenceSpan, ...] = ()
    candidate_nodes: tuple[CandidateNode, ...] = ()
    candidate_edges: tuple[CandidateEdge, ...] = ()
    factors: tuple[CandidateFactor, ...] = ()
    endpoints: tuple[CandidateEndpoint, ...] = ()
    contrasts: tuple[CandidateContrast, ...] = ()
    candidate_estimands: tuple[CandidateEstimand, ...] = ()
    candidate_counts: tuple[CandidateCount, ...] = ()
    candidate_events: tuple[CandidateEvent, ...] = ()
    candidate_graphs: tuple[CandidateGraph, ...] = ()
    alternatives: tuple[CandidateAlternative, ...] = ()
    clarification_questions: tuple[ClarificationQuestion, ...] = ()
    missing_predicates: tuple[MissingPredicateCandidate, ...] = ()
    coverage: StageCoverage
    model_metadata: ParserModelMetadata

    def assert_raw_candidate_only(self) -> ParserCandidateOutput:
        """Reject hidden final fields and return an exact canonical runtime tree."""

        try:
            assert_no_final_scientific_fields(_raw_candidate_contract_tree(self))
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"candidate runtime tree is not canonical: {exc}") from exc
        if type(self) is not ParserCandidateOutput:
            raise ValueError(
                "candidate runtime type at $ must be exact canonical ParserCandidateOutput, "
                f"got {type(self).__name__}"
            )
        try:
            canonical = ParserCandidateOutput.model_validate(
                ParserCandidateOutput.model_dump(
                    self,
                    mode="python",
                    round_trip=True,
                    warnings="none",
                )
            )
            _assert_exact_candidate_model_types(self, canonical)
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"candidate runtime tree cannot be canonicalized: {exc}") from exc
        return canonical

    @model_validator(mode="before")
    @classmethod
    def _raw_candidate_only(cls, value: Any) -> Any:
        assert_no_final_scientific_fields(value)
        return value

    @model_validator(mode="after")
    def _referential_integrity(self) -> ParserCandidateOutput:
        evidence_by_id = _unique_map(self.evidence_spans, "evidence_id")
        blocks = _unique_map(self.experiment_blocks, "block_id")
        boundaries = _unique_map(self.block_boundaries, "block_id")
        nodes = _unique_map(self.candidate_nodes, "node_id")
        edges = _unique_map(self.candidate_edges, "edge_id")
        factors = _unique_map(self.factors, "factor_id")
        endpoints = _unique_map(self.endpoints, "endpoint_id")
        contrasts = _unique_map(self.contrasts, "contrast_id")
        estimands = _unique_map(self.candidate_estimands, "estimand_id")
        counts = _unique_map(self.candidate_counts, "count_id")
        events = _unique_map(self.candidate_events, "event_id")
        graphs = _unique_map(self.candidate_graphs, "graph_id")
        alternatives = _unique_map(self.alternatives, "alternative_id")
        questions = _unique_map(self.clarification_questions, "question_id")

        globally_scoped_candidate_ids = (
            *nodes,
            *edges,
            *factors,
            *endpoints,
            *contrasts,
            *estimands,
            *counts,
            *events,
            *graphs,
            *alternatives,
        )
        if len(globally_scoped_candidate_ids) != len(set(globally_scoped_candidate_ids)):
            raise ValueError("candidate IDs must be globally unique across active types")

        candidates: tuple[CandidateFact, ...] = (
            *self.experiment_blocks,
            *self.block_boundaries,
            *self.candidate_nodes,
            *self.candidate_edges,
            *self.factors,
            *self.endpoints,
            *self.contrasts,
            *self.candidate_estimands,
            *self.candidate_counts,
            *self.candidate_events,
            *self.candidate_graphs,
            *self.alternatives,
        )
        for candidate in candidates:
            _require_subset(candidate.evidence_ids, evidence_by_id, "evidence_id")

        if set(boundaries) != set(blocks):
            raise ValueError("every experiment block requires exactly one boundary candidate")

        scoped_block_ids = (
            *(item.block_id for item in self.block_boundaries),
            *(item.block_id for item in self.candidate_nodes),
            *(item.block_id for item in self.candidate_edges),
            *(item.block_id for item in self.factors),
            *(item.block_id for item in self.endpoints),
            *(item.block_id for item in self.contrasts),
            *(item.block_id for item in self.candidate_estimands),
            *(item.block_id for item in self.candidate_counts),
            *(item.block_id for item in self.candidate_events),
            *(item.block_id for item in self.candidate_graphs),
            *(item.block_id for item in self.alternatives),
            *(item.block_id for item in self.clarification_questions),
            *(item.block_id for item in self.missing_predicates),
        )
        _require_subset(scoped_block_ids, blocks, "block_id")

        for edge in self.candidate_edges:
            _require_subset((edge.source_id, edge.target_id), nodes, "node_id")
            if (
                nodes[edge.source_id].block_id != edge.block_id
                or nodes[edge.target_id].block_id != edge.block_id
            ):
                raise ValueError("candidate edge crosses experiment blocks")
        for contrast in self.contrasts:
            _require_subset(contrast.factor_ids, factors, "factor_id")
            _require_subset(contrast.endpoint_ids, endpoints, "endpoint_id")
            if any(
                factors[item_id].block_id != contrast.block_id for item_id in contrast.factor_ids
            ):
                raise ValueError("candidate contrast crosses experiment block")
            if any(
                endpoints[item_id].block_id != contrast.block_id
                for item_id in contrast.endpoint_ids
            ):
                raise ValueError("candidate contrast crosses experiment block")
        for estimand in self.candidate_estimands:
            _require_subset(estimand.factor_ids, factors, "factor_id")
            _require_subset((estimand.endpoint_id,), endpoints, "endpoint_id")
            if any(
                factors[item_id].block_id != estimand.block_id for item_id in estimand.factor_ids
            ):
                raise ValueError("candidate estimand crosses experiment block")
            if endpoints[estimand.endpoint_id].block_id != estimand.block_id:
                raise ValueError("candidate estimand crosses experiment block")
            if estimand.contrast_id is not None:
                _require_subset((estimand.contrast_id,), contrasts, "contrast_id")
                if contrasts[estimand.contrast_id].block_id != estimand.block_id:
                    raise ValueError("candidate estimand contrast crosses experiment block")
        candidate_ids = set(nodes) | set(edges) | set(factors) | set(endpoints) | set(contrasts)
        candidate_ids |= set(estimands) | set(counts) | set(events) | set(graphs)
        candidate_blocks = {
            **{item_id: item.block_id for item_id, item in nodes.items()},
            **{item_id: item.block_id for item_id, item in edges.items()},
            **{item_id: item.block_id for item_id, item in factors.items()},
            **{item_id: item.block_id for item_id, item in endpoints.items()},
            **{item_id: item.block_id for item_id, item in contrasts.items()},
            **{item_id: item.block_id for item_id, item in estimands.items()},
            **{item_id: item.block_id for item_id, item in counts.items()},
            **{item_id: item.block_id for item_id, item in events.items()},
            **{item_id: item.block_id for item_id, item in graphs.items()},
        }
        for event in self.candidate_events:
            _require_subset(event.participant_candidate_ids, nodes, "node candidate_id")
            if any(
                nodes[item_id].block_id != event.block_id
                for item_id in event.participant_candidate_ids
            ):
                raise ValueError("candidate event participant has wrong type or experiment block")
        for graph in self.candidate_graphs:
            _require_subset(graph.candidate_node_ids, nodes, "node_id")
            _require_subset(graph.candidate_edge_ids, edges, "edge_id")
            _require_subset(graph.candidate_event_ids, events, "event_id")
            references = (
                *graph.candidate_node_ids,
                *graph.candidate_edge_ids,
                *graph.candidate_event_ids,
            )
            if any(candidate_blocks[item_id] != graph.block_id for item_id in references):
                raise ValueError("candidate graph crosses experiment block")
        for alternative in self.alternatives:
            _require_subset(alternative.candidate_node_ids, nodes, "node_id")
            _require_subset(alternative.candidate_edge_ids, edges, "edge_id")
            references = (*alternative.candidate_node_ids, *alternative.candidate_edge_ids)
            if any(candidate_blocks[item_id] != alternative.block_id for item_id in references):
                raise ValueError("candidate alternative crosses experiment block")
        for question in self.clarification_questions:
            _require_subset(question.resolves_candidate_ids, candidate_ids, "candidate_id")
            if any(
                candidate_blocks[item_id] != question.block_id
                for item_id in question.resolves_candidate_ids
            ):
                raise ValueError("clarification question crosses experiment block")
        for missing in self.missing_predicates:
            _require_subset(missing.evidence_ids, evidence_by_id, "evidence_id")
        if self.model_metadata.contract_version != self.contract_version:
            raise ValueError("model metadata contract version mismatch")
        if questions and not blocks:
            raise ValueError("clarification questions require an experiment block")
        if alternatives and not blocks:
            raise ValueError("alternatives require an experiment block")
        return self


class GoldSubmissionReference(FrozenModel):
    submission_id: str
    submission_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewer_id: str
    reviewer_role: str

    @model_validator(mode="after")
    def _non_blank(self) -> GoldSubmissionReference:
        if not all(
            value.strip() for value in (self.submission_id, self.reviewer_id, self.reviewer_role)
        ):
            raise ValueError("gold submission reference fields must not be blank")
        return self


class GoldMaterialDifference(FrozenModel):
    field_path: str
    submission_a_value_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    submission_b_value_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    adjudicated_value_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    resolution_rationale: str

    @model_validator(mode="after")
    def _non_blank(self) -> GoldMaterialDifference:
        if not self.field_path.strip() or not self.resolution_rationale.strip():
            raise ValueError("gold material difference requires path and rationale")
        return self


class GoldParserTarget(FrozenModel):
    """Human-adjudicated supervision envelope, distinct from model output."""

    schema_version: Literal["8.0.0"] = "8.0.0"
    candidate_target: ParserCandidateOutput
    adjudication_id: str
    reviewer_ids: tuple[str, ...] = Field(min_length=2)
    adjudication_rationale: str
    submission_references: tuple[GoldSubmissionReference, ...]
    comparison_status: Literal[
        "AGREED",
        "MATERIAL_DIFFERENCES_RESOLVED",
        "CONFLICT_ADJUDICATED",
    ]
    material_differences: tuple[GoldMaterialDifference, ...]

    @model_validator(mode="before")
    @classmethod
    def _raw_candidate_only(cls, value: Any) -> Any:
        assert_no_final_scientific_fields(value)
        return value

    @model_validator(mode="after")
    def _adjudicated(self) -> GoldParserTarget:
        if not self.adjudication_id.strip() or not self.adjudication_rationale.strip():
            raise ValueError("GoldParserTarget requires adjudication evidence")
        if any(not reviewer.strip() for reviewer in self.reviewer_ids):
            raise ValueError("GoldParserTarget reviewer IDs must not be blank")
        if len(self.reviewer_ids) != len(set(self.reviewer_ids)):
            raise ValueError("GoldParserTarget reviewer IDs must be unique")
        if len(self.submission_references) != 2:
            raise ValueError("GoldParserTarget requires exactly two submission references")
        submission_ids = tuple(item.submission_id for item in self.submission_references)
        if len(set(submission_ids)) != 2:
            raise ValueError("GoldParserTarget submission IDs must be distinct")
        submission_reviewers = tuple(item.reviewer_id for item in self.submission_references)
        if submission_reviewers != self.reviewer_ids:
            raise ValueError(
                "GoldParserTarget reviewer IDs must match submission reviewers exactly"
            )
        if self.comparison_status == "AGREED" and self.material_differences:
            raise ValueError("AGREED submissions cannot retain material differences")
        if self.comparison_status != "AGREED" and not self.material_differences:
            raise ValueError("non-agreed submissions require material differences")
        return self


class ParserV3MigrationReviewRequired(ValueError):
    """Legacy direct-verdict targets require explicit human re-adjudication."""


def migrate_parser_ai_output_v3_to_gold(_payload: Any) -> GoldParserTarget:
    raise ParserV3MigrationReviewRequired(
        "SCIENTIFIC_REVIEW_REQUIRED: ParserAIOutput v3 contains direct determinability; "
        "it cannot be silently promoted to GoldParserTarget"
    )


def validate_contract_pair_v3(
    request: ParserAIInput, response: ParserAIOutputV3
) -> ParserAIOutputV3:
    """Deprecated v3 request/response validation for the named legacy adapter."""

    return cast(ParserAIOutputV3, _validate_contract_coordinates(request, response))


def validate_candidate_contract_pair(
    request: ParserAIInput, response: ParserCandidateOutput
) -> ParserCandidateOutput:
    """Validate v8 candidate evidence coordinates against immutable source input."""

    assert_no_final_scientific_fields(response.model_dump(mode="json"))
    return cast(ParserCandidateOutput, _validate_contract_coordinates(request, response))


def _validate_contract_coordinates(
    request: ParserAIInput,
    response: ParserAIOutputV3 | ParserCandidateOutput,
) -> ParserAIOutputV3 | ParserCandidateOutput:
    """Valida coordinate e file dell'output rispetto all'input immutabile."""

    text_by_file = {document.file_id: document.text for document in request.documents}
    code_by_id = {artifact.id: artifact for artifact in request.statistical_code}
    text_by_file.update({artifact.file_id: artifact.text for artifact in request.statistical_code})
    tables = {table.table_id: table for table in request.tables}
    for evidence in response.evidence_spans:
        if evidence.file_id not in text_by_file:
            raise ValueError(f"evidence riferita a file sconosciuto: {evidence.file_id}")
        if evidence.start is not None and evidence.end is not None:
            source_text = text_by_file[evidence.file_id]
            if evidence.end > len(source_text):
                raise ValueError(f"evidence fuori dai limiti: {evidence.evidence_id}")
            if source_text[evidence.start : evidence.end] != evidence.text:
                raise ValueError(f"evidence text non coincide con la fonte: {evidence.evidence_id}")
        if evidence.table_id is not None:
            table = tables.get(evidence.table_id)
            if table is None or table.file_id != evidence.file_id:
                raise ValueError(f"evidence riferita a tabella sconosciuta: {evidence.table_id}")
            assert evidence.row is not None and evidence.column is not None
            if evidence.row >= len(table.rows) or evidence.column not in table.columns:
                raise ValueError(f"cella evidence fuori dai limiti: {evidence.evidence_id}")
            if table.rows[evidence.row].get(evidence.column, "") != evidence.text:
                raise ValueError(f"evidence cell non coincide con la fonte: {evidence.evidence_id}")
        if evidence.code_artifact_id is not None:
            artifact = code_by_id.get(evidence.code_artifact_id)
            if artifact is None or artifact.file_id != evidence.file_id:
                raise ValueError("code_artifact_id sconosciuto o riferito a un altro file")
    return response


def parser_ai_json_schemas() -> dict[str, dict[str, object]]:
    """JSON Schema per constrained decoding e validazione esterna."""

    return {
        "input": ParserAIInput.model_json_schema(),
        "candidate_output": ParserCandidateOutput.model_json_schema(),
        "gold_parser_target": GoldParserTarget.model_json_schema(),
        "legacy_v3_output": ParserAIOutputV3.model_json_schema(),
    }


def _unique_map(items: tuple[Any, ...], field_name: str) -> dict[str, Any]:
    values = [str(getattr(item, field_name)) for item in items]
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} duplicati")
    return dict(zip(values, items, strict=True))


def _require_subset(
    values: tuple[str, ...], known: Mapping[str, object] | set[str], label: str
) -> None:
    missing = set(values) - set(known)
    if missing:
        raise ValueError(f"{label} sconosciuti: {sorted(missing)}")
