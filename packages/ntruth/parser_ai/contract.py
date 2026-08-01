"""Contratto JSON stabile e backend-agnostic del parser AI (PRD v3, sezione 13).

Il contratto descrive soltanto candidate facts. Non contiene verdetti e non
consente al modello di scrivere nel grafo scientifico confermato.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from pydantic import Field, JsonValue, model_validator

from ntruth.schemas.core import Determinability, EvidenceType, FrozenModel
from ntruth.schemas.document import DocumentIR, StatisticalCodeArtifact
from ntruth.schemas.graph import ALLOCATABLE_NODE_TYPES, NodeType, RelationType

PARSER_AI_CONTRACT_VERSION = "2.0.0"

type ConfidenceScore = float


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


class DeterminabilityAssessment(FrozenModel):
    status: Determinability
    rationale: str
    confidence: ConfidenceScore = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _determinate_requires_evidence(self) -> DeterminabilityAssessment:
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


class ParserAIModelMetadata(FrozenModel):
    adapter_name: str
    model_name: str
    model_version: str
    model_checksum: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    prompt_template_version: str
    contract_version: Literal["2.0.0"] = "2.0.0"
    local_execution: bool = True


class ParserAIOutput(FrozenModel):
    """Output candidato completo; ``extra=forbid`` esclude verdetti nascosti."""

    contract_version: Literal["2.0.0"] = "2.0.0"
    experiment_blocks: tuple[CandidateExperimentBlock, ...] = ()
    evidence_spans: tuple[ParserAIEvidenceSpan, ...] = ()
    candidate_nodes: tuple[CandidateNode, ...] = ()
    candidate_edges: tuple[CandidateEdge, ...] = ()
    factors: tuple[CandidateFactor, ...] = ()
    endpoints: tuple[CandidateEndpoint, ...] = ()
    contrasts: tuple[CandidateContrast, ...] = ()
    candidate_estimands: tuple[CandidateEstimand, ...] = ()
    determinability: DeterminabilityAssessment
    alternatives: tuple[CandidateAlternative, ...] = ()
    clarification_questions: tuple[ClarificationQuestion, ...] = ()
    model_metadata: ParserAIModelMetadata

    @model_validator(mode="after")
    def _referential_integrity(self) -> ParserAIOutput:
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


def validate_contract_pair(request: ParserAIInput, response: ParserAIOutput) -> ParserAIOutput:
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
        "output": ParserAIOutput.model_json_schema(),
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
