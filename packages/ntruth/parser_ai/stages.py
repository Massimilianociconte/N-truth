"""Contratti di fase versionati per la pipeline parser/verifier del PRD v6.

I modelli in questo modulo descrivono artefatti di scambio immutabili. In
particolare ``CandidateGraphSet`` contiene esclusivamente fatti candidati,
evidenze, alternative e missing facts: determinability e verdict appartengono
al motore deterministico e non sono campi ammessi del contratto parser.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, JsonValue, field_validator, model_validator

from ntruth.parser_ai.contract import (
    CandidateAlternative,
    CandidateContrast,
    CandidateEdge,
    CandidateEndpoint,
    CandidateEstimand,
    CandidateExperimentBlock,
    CandidateFact,
    CandidateFactor,
    CandidateNode,
    NodeOntologyValue,
    ParserAIEvidenceSpan,
    ParserAIInput,
    ParserAISectionInput,
)
from ntruth.schemas.core import FrozenModel, content_checksum
from ntruth.schemas.experiment import CountKind, CountQuantifier, LifecycleStatus, TriState

STAGE_CONTRACT_VERSION: Literal["1.0.0"] = "1.0.0"


class StageName(StrEnum):
    DOCUMENT_ROUTE = "document_route"
    EVIDENCE_EXTRACTION = "evidence_extraction"
    ENTITY_COUNT = "entity_count"
    PROCEDURAL_EVENT = "procedural_event"
    CANDIDATE_GRAPH_SET = "candidate_graph_set"
    VERIFIER = "verifier"
    HUMAN_REVISION_PATCH = "human_revision_patch"
    RULE_RESULT = "rule_result"
    QUESTION_RECORD = "question_record"
    REPORT_BUNDLE = "report_bundle"


class StageStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class StageAuthority(StrEnum):
    DETERMINISTIC = "deterministic"
    MODEL = "model"
    USER = "user"
    ADJUDICATION = "adjudication"


class StageErrorCode(StrEnum):
    """Tassonomia minima normativa del PRD §13.6 (v6 prima, v8.0 poi).

    ``RULE_THEORY_MISMATCH`` e' aggiunto dal PRD v8.0: un ruleset che dichiara
    una Derivation Theory ma contiene regole non collegabili a una clausola
    esistente e' rifiutato in modo fail-closed (§10.11, §20.3, NFR-33).
    """

    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    CHUNK_COVERAGE_INCOMPLETE = "CHUNK_COVERAGE_INCOMPLETE"
    MISSING_REQUIRED_EVIDENCE = "MISSING_REQUIRED_EVIDENCE"
    AMBIGUOUS_COREFERENCE = "AMBIGUOUS_COREFERENCE"
    CONFLICTING_SOURCES = "CONFLICTING_SOURCES"
    INVALID_COUNT_INVARIANT = "INVALID_COUNT_INVARIANT"
    UNSUPPORTED_DESIGN_PROFILE = "UNSUPPORTED_DESIGN_PROFILE"
    VERIFIER_DISAGREEMENT = "VERIFIER_DISAGREEMENT"
    RULE_THEORY_MISMATCH = "RULE_THEORY_MISMATCH"


class StageWarningCode(StrEnum):
    CHUNK_COVERAGE_INCOMPLETE = "CHUNK_COVERAGE_INCOMPLETE"
    AMBIGUOUS_COREFERENCE = "AMBIGUOUS_COREFERENCE"
    CONFLICTING_SOURCES = "CONFLICTING_SOURCES"
    VERIFIER_DISAGREEMENT = "VERIFIER_DISAGREEMENT"
    DEGRADED_INPUT = "DEGRADED_INPUT"
    FALLBACK_USED = "FALLBACK_USED"
    INFORMATION_NOT_REPORTED = "INFORMATION_NOT_REPORTED"


class StageProvenance(FrozenModel):
    """Identita riproducibile di una singola esecuzione di fase."""

    stage_run_id: str
    stage: StageName
    authority: StageAuthority
    producer: str
    producer_version: str
    input_artifact_ids: tuple[str, ...] = ()
    input_checksums: dict[str, str] = Field(default_factory=dict)
    parent_result_ids: tuple[str, ...] = ()
    actor_role: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @field_validator("stage_run_id", "producer", "producer_version")
    @classmethod
    def _required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("provenance di stage con campo testuale vuoto")
        return normalized

    @field_validator("actor_role")
    @classmethod
    def _optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("actor_role non puo essere vuoto")
        return normalized

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        for field_name, values in (
            ("input_artifact_ids", self.input_artifact_ids),
            ("parent_result_ids", self.parent_result_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} contiene ID duplicati")
        for artifact_id, checksum in self.input_checksums.items():
            if not artifact_id.strip():
                raise ValueError("input_checksums contiene artifact ID vuoto")
            if len(checksum) != 64 or any(
                character not in "0123456789abcdef" for character in checksum
            ):
                raise ValueError(f"checksum non SHA-256 per {artifact_id}")
        if (
            self.started_at is not None
            and self.completed_at is not None
            and self.completed_at < self.started_at
        ):
            raise ValueError("completed_at precede started_at")
        return self


class StageError(FrozenModel):
    error_id: str
    code: StageErrorCode
    message: str
    recoverable: bool = False
    path: str | None = None
    artifact_ids: tuple[str, ...] = ()
    details: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("error_id", "message")
    @classmethod
    def _required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("errore di stage con campo testuale vuoto")
        return value.strip()

    @model_validator(mode="after")
    def _unique_artifacts(self) -> Self:
        if len(self.artifact_ids) != len(set(self.artifact_ids)):
            raise ValueError("artifact_ids duplicati nell'errore")
        return self


class StageWarning(FrozenModel):
    warning_id: str
    code: StageWarningCode
    message: str
    path: str | None = None
    artifact_ids: tuple[str, ...] = ()
    details: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("warning_id", "message")
    @classmethod
    def _required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("warning di stage con campo testuale vuoto")
        return value.strip()

    @model_validator(mode="after")
    def _unique_artifacts(self) -> Self:
        if len(self.artifact_ids) != len(set(self.artifact_ids)):
            raise ValueError("artifact_ids duplicati nel warning")
        return self


class ParserStageResult(FrozenModel):
    """Envelope comune; le sottoclassi congelano nome e versione della fase."""

    schema_version: str
    result_id: str
    stage: StageName
    status: StageStatus
    provenance: StageProvenance
    errors: tuple[StageError, ...] = ()
    warnings: tuple[StageWarning, ...] = ()

    @field_validator("result_id", "schema_version")
    @classmethod
    def _required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("envelope di stage con campo testuale vuoto")
        return value.strip()

    @model_validator(mode="after")
    def _envelope_is_coherent(self) -> Self:
        if self.provenance.stage is not self.stage:
            raise ValueError("provenance.stage non coincide con lo stage del risultato")
        if self.status is StageStatus.COMPLETE and self.errors:
            raise ValueError("status=complete non ammette errors")
        if self.status is StageStatus.PARTIAL and not (self.errors or self.warnings):
            raise ValueError("status=partial richiede almeno un errore o warning tipizzato")
        if self.status is StageStatus.FAILED and not self.errors:
            raise ValueError("status=failed richiede almeno un errore tipizzato")
        error_ids = [item.error_id for item in self.errors]
        warning_ids = [item.warning_id for item in self.warnings]
        if len(error_ids) != len(set(error_ids)):
            raise ValueError("error_id duplicati")
        if len(warning_ids) != len(set(warning_ids)):
            raise ValueError("warning_id duplicati")
        return self


class DocumentRouteKind(StrEnum):
    TEXT = "text"
    TABLE = "table"
    STATISTICAL_CODE = "statistical_code"
    IMAGE_METADATA = "image_metadata"
    UNSUPPORTED = "unsupported"


class DocumentRouteRecord(FrozenModel):
    file_id: str
    route: DocumentRouteKind
    parser_id: str | None = None
    mime_type: str | None = None
    language: str | None = None
    supported: bool

    @model_validator(mode="after")
    def _route_is_coherent(self) -> Self:
        if self.supported == (self.route is DocumentRouteKind.UNSUPPORTED):
            raise ValueError("route e supported non coerenti")
        if self.supported and not (self.parser_id and self.parser_id.strip()):
            raise ValueError("route supportata senza parser_id")
        return self


class DocumentRouteResult(ParserStageResult):
    schema_version: Literal["1.0.0"] = STAGE_CONTRACT_VERSION
    stage: Literal[StageName.DOCUMENT_ROUTE] = StageName.DOCUMENT_ROUTE
    routes: tuple[DocumentRouteRecord, ...] = ()

    @model_validator(mode="after")
    def _unique_files(self) -> Self:
        _require_unique(self.routes, "file_id", "route file_id")
        return self


class EvidenceExtractionResult(ParserStageResult):
    schema_version: Literal["1.0.0"] = STAGE_CONTRACT_VERSION
    stage: Literal[StageName.EVIDENCE_EXTRACTION] = StageName.EVIDENCE_EXTRACTION
    evidence_spans: tuple[ParserAIEvidenceSpan, ...] = ()
    chunk_coverage: tuple[ChunkCoverageRecord, ...] = ()

    @model_validator(mode="after")
    def _unique_records(self) -> Self:
        _require_unique(self.evidence_spans, "evidence_id", "evidence_id")
        _require_unique(self.chunk_coverage, "file_id", "chunk coverage file_id")
        return self


class ChunkCoverageRecord(FrozenModel):
    file_id: str
    total_chunks: int = Field(ge=1)
    processed_chunks: tuple[int, ...] = ()
    failed_chunks: tuple[int, ...] = ()

    @model_validator(mode="after")
    def _coverage_is_coherent(self) -> Self:
        processed = set(self.processed_chunks)
        failed = set(self.failed_chunks)
        if len(processed) != len(self.processed_chunks) or len(failed) != len(self.failed_chunks):
            raise ValueError("chunk index duplicati")
        if processed & failed:
            raise ValueError("uno stesso chunk non puo essere processed e failed")
        invalid = {index for index in processed | failed if index < 0 or index >= self.total_chunks}
        if invalid:
            raise ValueError(f"chunk index fuori range: {sorted(invalid)}")
        missing = set(range(self.total_chunks)) - processed - failed
        if missing:
            raise ValueError(
                "ogni chunk deve essere classificato come processed o failed; "
                f"indici mancanti: {sorted(missing)}"
            )
        return self


class CandidateCountRecord(CandidateFact):
    count_id: str
    block_id: str
    kind: CountKind
    quantifier: CountQuantifier
    value: int | float | None = Field(default=None, ge=0)
    lower_bound: int | float | None = Field(default=None, ge=0)
    upper_bound: int | float | None = Field(default=None, ge=0)
    unit_type: NodeOntologyValue | None = None
    factor_id: str | None = None
    contrast_id: str | None = None
    group_or_level: str | None = None
    endpoint_id: str | None = None
    timepoint: str | None = None
    lifecycle: LifecycleStatus | None = None
    population_scope: str | None = None
    condition: str | None = None

    @model_validator(mode="after")
    def _count_is_coherent(self) -> Self:
        if (
            isinstance(self.value, bool)
            or isinstance(self.lower_bound, bool)
            or isinstance(self.upper_bound, bool)
        ):
            raise ValueError("un count non puo essere booleano")
        if self.quantifier in {CountQuantifier.EXACT, CountQuantifier.APPROXIMATE}:
            if self.value is None or self.lower_bound is not None or self.upper_bound is not None:
                raise ValueError(f"{self.quantifier} richiede soltanto value")
        elif self.quantifier in {CountQuantifier.LOWER_BOUND, CountQuantifier.UPPER_BOUND}:
            if self.value is None or self.lower_bound is not None or self.upper_bound is not None:
                raise ValueError(f"{self.quantifier} usa value come limite")
        elif self.quantifier is CountQuantifier.RANGE:
            if self.value is not None or self.lower_bound is None or self.upper_bound is None:
                raise ValueError("RANGE richiede lower_bound e upper_bound")
            if self.upper_bound < self.lower_bound:
                raise ValueError("RANGE con upper_bound < lower_bound")
        elif self.value is not None or self.lower_bound is not None or self.upper_bound is not None:
            raise ValueError(f"{self.quantifier} non ammette valori numerici")
        if self.kind is not CountKind.EFFECTIVE_N:
            numeric_values = (self.value, self.lower_bound, self.upper_bound)
            if any(value is not None and not float(value).is_integer() for value in numeric_values):
                raise ValueError("i count non effective_n devono essere interi")
        expected_lifecycle = {
            CountKind.PLANNED_N: LifecycleStatus.PLANNED,
            CountKind.ALLOCATED_N: LifecycleStatus.ALLOCATED,
            CountKind.TREATED_N: LifecycleStatus.TREATED,
            CountKind.OBSERVED_N: LifecycleStatus.OBSERVED,
            CountKind.EXCLUDED_N: LifecycleStatus.EXCLUDED,
            CountKind.ANALYSED_N: LifecycleStatus.ANALYSED,
        }.get(self.kind)
        if expected_lifecycle is not None and self.lifecycle is not expected_lifecycle:
            raise ValueError(f"{self.kind} richiede lifecycle={expected_lifecycle}")
        return self


class EntityCountResult(ParserStageResult):
    schema_version: Literal["1.0.0"] = STAGE_CONTRACT_VERSION
    stage: Literal[StageName.ENTITY_COUNT] = StageName.ENTITY_COUNT
    entities: tuple[CandidateNode, ...] = ()
    counts: tuple[CandidateCountRecord, ...] = ()

    @model_validator(mode="after")
    def _unique_records(self) -> Self:
        _require_unique(self.entities, "node_id", "entity node_id")
        _require_unique(self.counts, "count_id", "count_id")
        return self


class CandidateProceduralEvent(CandidateFact):
    event_id: str
    block_id: str
    event_type: str
    subject_node_ids: tuple[str, ...] = ()
    before_event_ids: tuple[str, ...] = ()
    after_event_ids: tuple[str, ...] = ()
    timing_text: str | None = None

    @model_validator(mode="after")
    def _event_is_coherent(self) -> Self:
        if not self.event_type.strip():
            raise ValueError("event_type non puo essere vuoto")
        for field_name, values in (
            ("subject_node_ids", self.subject_node_ids),
            ("before_event_ids", self.before_event_ids),
            ("after_event_ids", self.after_event_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} contiene ID duplicati")
        if set(self.before_event_ids) & set(self.after_event_ids):
            raise ValueError("lo stesso evento non puo essere sia prima sia dopo")
        return self


class ProceduralEventResult(ParserStageResult):
    schema_version: Literal["1.0.0"] = STAGE_CONTRACT_VERSION
    stage: Literal[StageName.PROCEDURAL_EVENT] = StageName.PROCEDURAL_EVENT
    events: tuple[CandidateProceduralEvent, ...] = ()

    @model_validator(mode="after")
    def _unique_events(self) -> Self:
        _require_unique(self.events, "event_id", "event_id")
        return self


class CandidateOperationalIndependence(CandidateFact):
    independence_id: str
    block_id: str
    factor_id: str
    independently_assigned: TriState
    randomization_unit: NodeOntologyValue | None = None
    independence_mechanism: str | None = None
    shared_environment: tuple[str, ...] = ()
    confounded_with: tuple[str, ...] = ()
    source_biological_preparation: str | None = None
    allocation_event_id: str | None = None
    allocation_timing: str | None = None


class MissingFactRecord(FrozenModel):
    missing_fact_id: str
    block_id: str
    predicate: str
    reason: str
    evidence_ids: tuple[str, ...] = ()

    @field_validator("missing_fact_id", "block_id", "predicate", "reason")
    @classmethod
    def _required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("missing fact con campo testuale vuoto")
        return value.strip()


class CandidateGraphSet(ParserStageResult):
    """Output parser v6 privo, per schema, di determinability e verdict."""

    schema_version: Literal["1.0.0"] = STAGE_CONTRACT_VERSION
    stage: Literal[StageName.CANDIDATE_GRAPH_SET] = StageName.CANDIDATE_GRAPH_SET
    graph_set_id: str
    source_result_ids: tuple[str, ...] = ()
    experiment_blocks: tuple[CandidateExperimentBlock, ...] = ()
    evidence_spans: tuple[ParserAIEvidenceSpan, ...] = ()
    candidate_nodes: tuple[CandidateNode, ...] = ()
    candidate_edges: tuple[CandidateEdge, ...] = ()
    factors: tuple[CandidateFactor, ...] = ()
    endpoints: tuple[CandidateEndpoint, ...] = ()
    contrasts: tuple[CandidateContrast, ...] = ()
    candidate_estimands: tuple[CandidateEstimand, ...] = ()
    counts: tuple[CandidateCountRecord, ...] = ()
    operational_independence: tuple[CandidateOperationalIndependence, ...] = ()
    procedural_events: tuple[CandidateProceduralEvent, ...] = ()
    alternatives: tuple[CandidateAlternative, ...] = ()
    missing_facts: tuple[MissingFactRecord, ...] = ()
    chunk_coverage: tuple[ChunkCoverageRecord, ...] = ()

    @model_validator(mode="after")
    def _referential_integrity(self) -> Self:
        blocks = _unique_map(self.experiment_blocks, "block_id", "block_id")
        evidence = _unique_map(self.evidence_spans, "evidence_id", "evidence_id")
        nodes = _unique_map(self.candidate_nodes, "node_id", "node_id")
        edges = _unique_map(self.candidate_edges, "edge_id", "edge_id")
        factors = _unique_map(self.factors, "factor_id", "factor_id")
        endpoints = _unique_map(self.endpoints, "endpoint_id", "endpoint_id")
        contrasts = _unique_map(self.contrasts, "contrast_id", "contrast_id")
        estimands = _unique_map(self.candidate_estimands, "estimand_id", "estimand_id")
        _unique_map(self.counts, "count_id", "count_id")
        _unique_map(self.operational_independence, "independence_id", "independence_id")
        events = _unique_map(self.procedural_events, "event_id", "event_id")
        _unique_map(self.alternatives, "alternative_id", "alternative_id")
        _unique_map(self.missing_facts, "missing_fact_id", "missing_fact_id")
        _unique_map(self.chunk_coverage, "file_id", "chunk coverage file_id")

        candidate_facts: tuple[CandidateFact, ...] = (
            *self.experiment_blocks,
            *self.candidate_nodes,
            *self.candidate_edges,
            *self.factors,
            *self.endpoints,
            *self.contrasts,
            *self.candidate_estimands,
            *self.counts,
            *self.operational_independence,
            *self.procedural_events,
            *self.alternatives,
        )
        for fact in candidate_facts:
            _require_subset(fact.evidence_ids, evidence, "evidence_id")
        for item in self.missing_facts:
            _require_subset(item.evidence_ids, evidence, "evidence_id")

        block_references = (
            *(item.block_id for item in self.candidate_nodes),
            *(item.block_id for item in self.candidate_edges),
            *(item.block_id for item in self.factors),
            *(item.block_id for item in self.endpoints),
            *(item.block_id for item in self.contrasts),
            *(item.block_id for item in self.candidate_estimands),
            *(item.block_id for item in self.counts),
            *(item.block_id for item in self.operational_independence),
            *(item.block_id for item in self.procedural_events),
            *(item.block_id for item in self.missing_facts),
        )
        _require_subset(block_references, blocks, "block_id")
        for edge in self.candidate_edges:
            _require_subset((edge.source_id, edge.target_id), nodes, "node_id")
            if any(
                nodes[node_id].block_id != edge.block_id
                for node_id in (edge.source_id, edge.target_id)
            ):
                raise ValueError("edge riferito a nodi di un altro experiment block")
        for contrast in self.contrasts:
            _require_subset(contrast.factor_ids, factors, "factor_id")
            _require_subset(contrast.endpoint_ids, endpoints, "endpoint_id")
        for estimand in estimands.values():
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
        for count in self.counts:
            if count.factor_id is not None:
                _require_subset((count.factor_id,), factors, "factor_id")
            if count.contrast_id is not None:
                _require_subset((count.contrast_id,), contrasts, "contrast_id")
            if count.endpoint_id is not None:
                _require_subset((count.endpoint_id,), endpoints, "endpoint_id")
        for independence in self.operational_independence:
            _require_subset((independence.factor_id,), factors, "factor_id")
            if independence.allocation_event_id is not None:
                _require_subset((independence.allocation_event_id,), events, "event_id")
        for event in self.procedural_events:
            _require_subset(event.subject_node_ids, nodes, "node_id")
            _require_subset((*event.before_event_ids, *event.after_event_ids), events, "event_id")
        for alternative in self.alternatives:
            _require_subset(alternative.candidate_node_ids, nodes, "node_id")
            _require_subset(alternative.candidate_edge_ids, edges, "edge_id")
        return self


def validate_candidate_graph_pair(
    parser_input: ParserAIInput,
    graph_set: CandidateGraphSet,
    *,
    require_model_authority: bool = True,
) -> CandidateGraphSet:
    """Canonizza il perimetro model-owned e valida la coppia input/output.

    La provenance dichiarata nel testo generato non e una fonte autorevole: in
    modalita modello viene sempre sostituita con lineage derivata dall'input
    effettivamente fornito all'host. Nessun verdict viene derivato qui.
    """

    if require_model_authority and graph_set.provenance.authority is not StageAuthority.MODEL:
        raise ValueError("l'output del parser deve dichiarare authority=model")
    if require_model_authority:
        graph_set = canonicalize_model_candidate_graph(parser_input, graph_set)
    text_by_file = {item.file_id: item.text for item in parser_input.documents}
    sections_by_file: dict[str, dict[str, ParserAISectionInput]] = {}
    for document in parser_input.documents:
        sections: dict[str, ParserAISectionInput] = {}
        for section in document.sections:
            if section.section_id in sections:
                raise ValueError(
                    f"document {document.file_id}: section_id duplicato {section.section_id}"
                )
            if (
                section.end > len(document.text)
                or document.text[section.start : section.end] != section.text
            ):
                raise ValueError(
                    f"document {document.file_id}: coordinate section non coincidono "
                    f"per {section.section_id}"
                )
            sections[section.section_id] = section
        sections_by_file[document.file_id] = sections
    code_by_id = {item.id: item for item in parser_input.statistical_code}
    text_by_file.update({item.file_id: item.text for item in parser_input.statistical_code})
    known_file_ids = set(text_by_file)
    coverage_by_file = {item.file_id: item for item in graph_set.chunk_coverage}
    unknown_coverage = sorted(coverage_by_file.keys() - known_file_ids)
    if unknown_coverage:
        raise ValueError(f"chunk coverage riferita a file_id sconosciuti: {unknown_coverage}")
    missing_coverage = sorted(known_file_ids - coverage_by_file.keys())
    failed_coverage = sorted(
        file_id for file_id, coverage in coverage_by_file.items() if coverage.failed_chunks
    )
    coverage_incomplete = bool(missing_coverage or failed_coverage)
    if graph_set.status is StageStatus.COMPLETE and coverage_incomplete:
        raise ValueError(
            "status=complete richiede copertura integrale senza chunk falliti; "
            f"file mancanti={missing_coverage}, file con fallimenti={failed_coverage}"
        )
    if graph_set.status is not StageStatus.COMPLETE and coverage_incomplete:
        issue_codes = {item.code.value for item in graph_set.errors}
        issue_codes.update(item.code.value for item in graph_set.warnings)
        if StageErrorCode.CHUNK_COVERAGE_INCOMPLETE.value not in issue_codes:
            raise ValueError(
                "copertura incompleta richiede CHUNK_COVERAGE_INCOMPLETE "
                "negli errori o warning tipizzati"
            )
    tables = {item.table_id: item for item in parser_input.tables}
    for span in graph_set.evidence_spans:
        if span.file_id not in text_by_file:
            raise ValueError(f"evidence {span.evidence_id}: file_id sconosciuto")
        if span.start is not None and span.end is not None:
            source = text_by_file[span.file_id]
            if span.end > len(source) or source[span.start : span.end] != span.text:
                raise ValueError(f"evidence {span.evidence_id}: coordinate testuali non coincidono")
        if span.section_id is not None:
            matched_section = sections_by_file.get(span.file_id, {}).get(span.section_id)
            if matched_section is None:
                raise ValueError(f"evidence {span.evidence_id}: section_id sconosciuto per il file")
            if (
                span.start is not None
                and span.end is not None
                and (span.start < matched_section.start or span.end > matched_section.end)
            ):
                raise ValueError(
                    f"evidence {span.evidence_id}: coordinate fuori dalla section dichiarata"
                )
        if span.table_id is not None:
            table = tables.get(span.table_id)
            if table is None or table.file_id != span.file_id:
                raise ValueError(f"evidence {span.evidence_id}: table_id non appartiene al file")
            assert span.row is not None and span.column is not None
            if span.row >= len(table.rows) or span.column not in table.columns:
                raise ValueError(f"evidence {span.evidence_id}: cella fuori dai limiti")
            if table.rows[span.row].get(span.column, "") != span.text:
                raise ValueError(f"evidence {span.evidence_id}: contenuto cella non coincide")
        if span.code_artifact_id is not None:
            artifact = code_by_id.get(span.code_artifact_id)
            if artifact is None or artifact.file_id != span.file_id:
                raise ValueError(f"evidence {span.evidence_id}: code_artifact_id sconosciuto")
    return graph_set


def canonicalize_model_candidate_graph(
    parser_input: ParserAIInput,
    graph_set: CandidateGraphSet,
) -> CandidateGraphSet:
    """Sostituisce ogni campo di provenance controllabile dal modello.

    Gli identificatori e i checksum di input sono derivati esclusivamente dai
    contratti host. I parent result, i ruoli umani, i timestamp e la lineage di
    stage precedenti non possono quindi essere inventati o appresi dal target.
    """

    if graph_set.provenance.authority is not StageAuthority.MODEL:
        raise ValueError("la canonicalizzazione model-owned richiede authority=model")
    input_checksums = {item.file_id: item.sha256 for item in parser_input.documents}
    input_checksums.update({item.file_id: item.sha256 for item in parser_input.statistical_code})
    input_artifact_ids = tuple(sorted(input_checksums))
    graph_payload = graph_set.model_dump(
        mode="json",
        exclude={"provenance", "source_result_ids"},
    )
    stage_digest = content_checksum(
        {
            "parser_input": parser_input.model_dump(mode="json"),
            "candidate_graph": graph_payload,
        }
    )[:20]
    provenance = StageProvenance(
        stage_run_id=f"model-stage-{stage_digest}",
        stage=StageName.CANDIDATE_GRAPH_SET,
        authority=StageAuthority.MODEL,
        producer="ntruth-model-candidate-host",
        producer_version=STAGE_CONTRACT_VERSION,
        input_artifact_ids=input_artifact_ids,
        input_checksums=input_checksums,
        parent_result_ids=(),
        actor_role=None,
        started_at=None,
        completed_at=None,
    )
    return graph_set.model_copy(
        update={
            "source_result_ids": (),
            "provenance": provenance,
        }
    )


class VerifierKind(StrEnum):
    HARD = "hard"
    SEMANTIC = "semantic"


class VerificationStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    NOT_RUN = "not_run"


class VerificationCheck(FrozenModel):
    check_id: str
    kind: VerifierKind
    status: VerificationStatus
    code: str
    message: str
    related_ids: tuple[str, ...] = ()


class VerifierResult(ParserStageResult):
    schema_version: Literal["1.0.0"] = STAGE_CONTRACT_VERSION
    stage: Literal[StageName.VERIFIER] = StageName.VERIFIER
    graph_set_id: str
    checks: tuple[VerificationCheck, ...] = ()
    hard_verifier_passed: bool
    semantic_verifier_invoked: bool = False
    accepted_graph_ids: tuple[str, ...] = ()
    rejected_graph_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _checks_are_coherent(self) -> Self:
        _require_unique(self.checks, "check_id", "check_id")
        hard = [item for item in self.checks if item.kind is VerifierKind.HARD]
        if self.status is not StageStatus.FAILED and not hard:
            raise ValueError("hard verifier sempre attivo: manca un hard check")
        expected_hard_pass = bool(hard) and all(
            item.status is VerificationStatus.PASS for item in hard
        )
        if self.hard_verifier_passed != expected_hard_pass:
            raise ValueError("hard_verifier_passed incoerente con i check")
        semantic = [item for item in self.checks if item.kind is VerifierKind.SEMANTIC]
        if self.semantic_verifier_invoked != bool(semantic):
            raise ValueError("semantic_verifier_invoked incoerente con i check")
        if set(self.accepted_graph_ids) & set(self.rejected_graph_ids):
            raise ValueError("un grafo non puo essere sia accepted sia rejected")
        return self


class JsonPatchOperation(FrozenModel):
    op: Literal["add", "remove", "replace", "move", "copy", "test"]
    path: str
    from_path: str | None = Field(default=None, alias="from", serialization_alias="from")
    value: JsonValue | None = None

    @model_validator(mode="after")
    def _operation_is_coherent(self) -> Self:
        if not self.path.startswith("/"):
            raise ValueError("JSON Pointer path deve iniziare con '/'")
        if self.op in {"move", "copy"}:
            if self.from_path is None or not self.from_path.startswith("/"):
                raise ValueError(f"{self.op} richiede from come JSON Pointer")
        elif self.from_path is not None:
            raise ValueError(f"{self.op} non ammette from")
        if self.op in {"add", "replace", "test"} and "value" not in self.model_fields_set:
            raise ValueError(f"{self.op} richiede value")
        if self.op in {"remove", "move", "copy"} and "value" in self.model_fields_set:
            raise ValueError(f"{self.op} non ammette value")
        return self


class HumanRevisionPatch(ParserStageResult):
    schema_version: Literal["1.0.0"] = STAGE_CONTRACT_VERSION
    stage: Literal[StageName.HUMAN_REVISION_PATCH] = StageName.HUMAN_REVISION_PATCH
    patch_id: str
    target_graph_set_id: str
    base_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    operations: tuple[JsonPatchOperation, ...] = Field(min_length=1)
    rationale: str

    @model_validator(mode="after")
    def _human_authority_required(self) -> Self:
        if self.provenance.authority not in {StageAuthority.USER, StageAuthority.ADJUDICATION}:
            raise ValueError("HumanRevisionPatch richiede authority user o adjudication")
        if not self.rationale.strip():
            raise ValueError("HumanRevisionPatch richiede rationale")
        return self


class RuleApplicationStatus(StrEnum):
    MATCHED = "matched"
    NOT_MATCHED = "not_matched"
    NOT_APPLICABLE = "not_applicable"
    BLOCKED = "blocked"


class RuleApplicationRecord(FrozenModel):
    application_id: str
    rule_id: str
    ruleset_version: str
    status: RuleApplicationStatus
    scope_id: str | None = None
    evidence_ids: tuple[str, ...] = ()
    derived_fact_ids: tuple[str, ...] = ()
    message: str = ""


class RuleResult(ParserStageResult):
    schema_version: Literal["1.0.0"] = STAGE_CONTRACT_VERSION
    stage: Literal[StageName.RULE_RESULT] = StageName.RULE_RESULT
    graph_set_id: str
    ruleset_id: str
    ruleset_version: str
    applications: tuple[RuleApplicationRecord, ...] = ()

    @model_validator(mode="after")
    def _unique_applications(self) -> Self:
        _require_unique(self.applications, "application_id", "application_id")
        return self


class QuestionScenario(FrozenModel):
    scenario_id: str
    condition: str
    changed_output_fields: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _scenario_is_coherent(self) -> Self:
        if not self.condition.strip():
            raise ValueError("scenario condition non puo essere vuota")
        if len(self.changed_output_fields) != len(set(self.changed_output_fields)):
            raise ValueError("changed_output_fields duplicati")
        return self


class QuestionRecord(ParserStageResult):
    schema_version: Literal["1.0.0"] = STAGE_CONTRACT_VERSION
    stage: Literal[StageName.QUESTION_RECORD] = StageName.QUESTION_RECORD
    question_id: str
    block_id: str
    missing_predicate: str
    text: str
    scenarios: tuple[QuestionScenario, ...] = Field(min_length=2)
    priority: int = Field(default=0, ge=0, le=100)

    @model_validator(mode="after")
    def _question_is_discriminating(self) -> Self:
        _require_unique(self.scenarios, "scenario_id", "scenario_id")
        conditions = [item.condition.strip().casefold() for item in self.scenarios]
        if len(conditions) != len(set(conditions)):
            raise ValueError("QuestionRecord contiene condizioni duplicate")
        for value in (self.missing_predicate, self.text):
            if not value.strip():
                raise ValueError("QuestionRecord con campo testuale vuoto")
        return self


class ReportArtifactKind(StrEnum):
    JSON = "json"
    YAML = "yaml"
    HTML = "html"
    GRAPH = "graph"
    RO_CRATE = "ro_crate"


class ReportArtifact(FrozenModel):
    artifact_id: str
    kind: ReportArtifactKind
    media_type: str
    relative_path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _safe_relative_path(self) -> Self:
        if not self.relative_path or self.relative_path.startswith("/"):
            raise ValueError("ReportArtifact richiede un path relativo")
        if ".." in self.relative_path.split("/"):
            raise ValueError("ReportArtifact path non puo attraversare directory parent")
        return self


class ReportBundle(ParserStageResult):
    schema_version: Literal["1.0.0"] = STAGE_CONTRACT_VERSION
    stage: Literal[StageName.REPORT_BUNDLE] = StageName.REPORT_BUNDLE
    report_id: str
    graph_set_id: str
    stage_result_ids: tuple[str, ...] = ()
    block_ids: tuple[str, ...] = ()
    artifacts: tuple[ReportArtifact, ...] = ()

    @model_validator(mode="after")
    def _bundle_is_coherent(self) -> Self:
        _require_unique(self.artifacts, "artifact_id", "artifact_id")
        for field_name, values in (
            ("stage_result_ids", self.stage_result_ids),
            ("block_ids", self.block_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} contiene ID duplicati")
        return self


def parser_stage_json_schemas() -> dict[str, dict[str, object]]:
    """Restituisce i dieci contratti staged v6 per export e constrained decoding."""

    stage_models = (
        DocumentRouteResult,
        EvidenceExtractionResult,
        EntityCountResult,
        ProceduralEventResult,
        CandidateGraphSet,
        VerifierResult,
        HumanRevisionPatch,
        RuleResult,
        QuestionRecord,
        ReportBundle,
    )
    return {
        model.model_fields["stage"].default.value: model.model_json_schema()
        for model in stage_models
    }


def _require_unique[T](items: tuple[T, ...], attribute: str, label: str) -> None:
    _unique_map(items, attribute, label)


def _unique_map[T](items: tuple[T, ...], attribute: str, label: str) -> dict[str, T]:
    values = [str(getattr(item, attribute)) for item in items]
    if len(values) != len(set(values)):
        raise ValueError(f"{label} duplicati")
    return dict(zip(values, items, strict=True))


def _require_subset(values: tuple[str, ...], known: Mapping[str, object], label: str) -> None:
    missing = sorted(set(values) - known.keys())
    if missing:
        raise ValueError(f"{label} sconosciuti: {missing}")


__all__ = [
    "STAGE_CONTRACT_VERSION",
    "CandidateCountRecord",
    "CandidateGraphSet",
    "CandidateOperationalIndependence",
    "CandidateProceduralEvent",
    "ChunkCoverageRecord",
    "DocumentRouteKind",
    "DocumentRouteRecord",
    "DocumentRouteResult",
    "EntityCountResult",
    "EvidenceExtractionResult",
    "HumanRevisionPatch",
    "JsonPatchOperation",
    "MissingFactRecord",
    "ParserStageResult",
    "ProceduralEventResult",
    "QuestionRecord",
    "QuestionScenario",
    "ReportArtifact",
    "ReportArtifactKind",
    "ReportBundle",
    "RuleApplicationRecord",
    "RuleApplicationStatus",
    "RuleResult",
    "StageAuthority",
    "StageError",
    "StageErrorCode",
    "StageName",
    "StageProvenance",
    "StageStatus",
    "StageWarning",
    "StageWarningCode",
    "VerificationCheck",
    "VerificationStatus",
    "VerifierKind",
    "VerifierResult",
    "canonicalize_model_candidate_graph",
    "parser_stage_json_schemas",
    "validate_candidate_graph_pair",
]
