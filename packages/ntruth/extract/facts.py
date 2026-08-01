"""Candidate facts prodotti dall'estrazione.

Tutto cio che esce dall'estrazione e un candidate fact con evidenza: il graph
builder decide come comporli, il rules engine legge solo il grafo (PRD 11.3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from ntruth.schemas.core import CellRef, EvidenceSpan, EvidenceType, ProvenanceKind, stable_id
from ntruth.schemas.coreference import CoreferenceLink, Mention
from ntruth.schemas.experiment import NKind
from ntruth.schemas.graph import NodeType, RelationType

FactorKind = Literal["treatment", "genotype", "dose", "time", "diet", "other"]


def make_evidence(
    *,
    file_id: str,
    text: str,
    section_id: str | None = None,
    section_title: str | None = None,
    start: int | None = None,
    end: int | None = None,
    cell: CellRef | None = None,
    parser_version: str = "0.0.0",
    evidence_type: EvidenceType = EvidenceType.AUTHOR_ASSERTION,
    extraction_method: str = "deterministic_extraction",
) -> EvidenceSpan:
    """Evidenza con ID deterministico: stessa fonte, stesso ID (PRD NFR-02)."""
    evidence_id = stable_id(
        "ev", file_id, section_id or "", start, end, cell.as_label() if cell else "", text[:160]
    )
    return EvidenceSpan(
        id=evidence_id,
        file_id=file_id,
        section_id=section_id,
        section_title=section_title,
        start=start,
        end=end,
        cell=cell,
        text=text[:400],
        parser_version=parser_version,
        evidence_type=evidence_type,
        extraction_method=extraction_method,
    )


@dataclass(slots=True)
class EntityFact:
    """Un livello sperimentale menzionato, con conteggio se dichiarato."""

    node_type: NodeType
    label: str
    count: int | None = None
    per_parent: bool = False
    evidence: EvidenceSpan | None = None
    origin: ProvenanceKind = ProvenanceKind.EXPLICIT
    confidence: float = 0.9
    attributes: dict[str, str | int | float | bool | None] = field(default_factory=dict)


@dataclass(slots=True)
class EntityInstanceFact:
    """Istanza osservata in una fonte strutturata.

    ``instance_key`` e gia pseudonimizzato/content-addressed: l'ID del grafo non
    incorpora mai il valore originale della cella (PRD 12.4). Il valore resta
    recuperabile soltanto tramite l'evidenza locale puntata dalla cella.
    """

    node_type: NodeType
    instance_key: str
    label: str
    evidence: EvidenceSpan | None = None
    origin: ProvenanceKind = ProvenanceKind.TABULAR
    confidence: float = 0.98
    attributes: dict[str, str | int | float | bool | None] = field(default_factory=dict)


@dataclass(slots=True)
class RelationFact:
    """Relazione tra due livelli, con eventuale cardinalita per genitore."""

    type: RelationType
    source_type: NodeType
    target_type: NodeType
    per_parent_count: int | None = None
    evidence: EvidenceSpan | None = None
    origin: ProvenanceKind = ProvenanceKind.EXPLICIT
    confidence: float = 0.9
    derivation: str | None = None


@dataclass(slots=True)
class InstanceRelationFact:
    """Relazione tra due istanze identificabili nel sample sheet."""

    type: RelationType
    source_type: NodeType
    source_key: str
    target_type: NodeType
    target_key: str
    evidence: EvidenceSpan | None = None
    origin: ProvenanceKind = ProvenanceKind.TABULAR
    confidence: float = 0.98
    derivation: str | None = None


@dataclass(slots=True)
class InstanceAssignmentFact:
    """Livello di fattore assegnato a una specifica istanza tabulare."""

    factor_name: str
    factor_level: str
    node_type: NodeType
    instance_key: str
    evidence: EvidenceSpan | None = None
    origin: ProvenanceKind = ProvenanceKind.TABULAR
    confidence: float = 0.95


@dataclass(slots=True)
class NFact:
    """Menzione di n, prima della risoluzione di scope e tipo."""

    value: int | None
    entity_text: str
    node_type: NodeType | None
    kind: NKind
    raw_text: str
    qualifiers: tuple[str, ...] = ()
    evidence: EvidenceSpan | None = None
    origin: ProvenanceKind = ProvenanceKind.EXPLICIT
    confidence: float = 0.9
    ambiguous_entity: bool = False
    endpoint_hint: str | None = None
    group_hint: str | None = None
    timepoint_hint: str | None = None


@dataclass(slots=True)
class FactorFact:
    """Fattore con allocazione e applicazione candidate ma distinte.

    ``assignment_*`` e mantenuto come alias legacy di ``allocation_*`` per le
    fixture e gli adapter v0.1. Non viene mai sincronizzato con
    ``application_*``: il livello che riceve materialmente un intervento non e
    necessariamente quello a cui i livelli del fattore sono stati allocati in
    modo indipendente.
    """

    name: str
    levels: tuple[str, ...] = ()
    kind: FactorKind = "other"
    allocation_level: NodeType | None = None
    application_level: NodeType | None = None
    allocation_confidence: float = 0.0
    application_confidence: float = 0.0
    allocation_evidence: EvidenceSpan | None = None
    application_evidence: EvidenceSpan | None = None
    # Deprecated compatibility aliases.
    assignment_level: NodeType | None = None
    assignment_confidence: float = 0.0
    assignment_evidence: EvidenceSpan | None = None
    evidence: EvidenceSpan | None = None
    origin: ProvenanceKind = ProvenanceKind.EXPLICIT
    randomized: bool = False

    def __post_init__(self) -> None:
        if (
            self.allocation_level is not None
            and self.assignment_level is not None
            and self.allocation_level is not self.assignment_level
        ):
            raise ValueError("allocation_level incoerente con assignment_level legacy")
        if self.allocation_level is None:
            self.allocation_level = self.assignment_level
        self.assignment_level = self.allocation_level

        if self.allocation_confidence == 0.0:
            self.allocation_confidence = self.assignment_confidence
        elif self.assignment_confidence not in {0.0, self.allocation_confidence}:
            raise ValueError("allocation_confidence incoerente con alias legacy")
        self.assignment_confidence = self.allocation_confidence

        if self.allocation_evidence is None:
            self.allocation_evidence = self.assignment_evidence
        elif (
            self.assignment_evidence is not None
            and self.assignment_evidence.id != self.allocation_evidence.id
        ):
            raise ValueError("allocation_evidence incoerente con alias legacy")
        self.assignment_evidence = self.allocation_evidence


@dataclass(slots=True)
class EndpointFact:
    """Variabile di risultato e livello su cui e misurata."""

    name: str
    measured_on: NodeType | None = None
    aggregation: str | None = None
    timepoints: tuple[str, ...] = ()
    evidence: EvidenceSpan | None = None
    origin: ProvenanceKind = ProvenanceKind.EXPLICIT


@dataclass(slots=True)
class StatisticalModelFact:
    """Modello statistico dichiarato e livelli che dichiara di modellare."""

    kind: str  # mixed | simple | unspecified
    accounts_for: tuple[NodeType, ...] = ()
    raw_text: str = ""
    evidence: EvidenceSpan | None = None
    origin: ProvenanceKind = ProvenanceKind.EXPLICIT


@dataclass(slots=True)
class ProcessFact:
    """Fatti di processo: pooling, esclusioni, blinding, batch."""

    kind: str  # pooling | exclusion | blinding | batch | repeated_measure
    detail: str = ""
    node_type: NodeType | None = None
    value: int | None = None
    evidence: EvidenceSpan | None = None
    endpoint_hint: str | None = None
    group_hint: str | None = None
    origin: ProvenanceKind = ProvenanceKind.EXPLICIT


@dataclass
class ExtractionResult:
    """Uscita completa dell'estrattore per un blocco."""

    entities: list[EntityFact] = field(default_factory=list)
    entity_instances: list[EntityInstanceFact] = field(default_factory=list)
    relations: list[RelationFact] = field(default_factory=list)
    instance_relations: list[InstanceRelationFact] = field(default_factory=list)
    instance_assignments: list[InstanceAssignmentFact] = field(default_factory=list)
    n_facts: list[NFact] = field(default_factory=list)
    factors: list[FactorFact] = field(default_factory=list)
    endpoints: list[EndpointFact] = field(default_factory=list)
    models: list[StatisticalModelFact] = field(default_factory=list)
    processes: list[ProcessFact] = field(default_factory=list)
    evidence: list[EvidenceSpan] = field(default_factory=list)
    mentions: list[Mention] = field(default_factory=list)
    coreference_links: list[CoreferenceLink] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def merge(self, other: ExtractionResult) -> ExtractionResult:
        self.entities.extend(other.entities)
        self.entity_instances.extend(other.entity_instances)
        self.relations.extend(other.relations)
        self.instance_relations.extend(other.instance_relations)
        self.instance_assignments.extend(other.instance_assignments)
        self.n_facts.extend(other.n_facts)
        self.factors.extend(other.factors)
        self.endpoints.extend(other.endpoints)
        self.models.extend(other.models)
        self.processes.extend(other.processes)
        self.evidence.extend(other.evidence)
        self.mentions.extend(other.mentions)
        self.coreference_links.extend(other.coreference_links)
        self.warnings.extend(other.warnings)
        return self

    def register(self, evidence: EvidenceSpan | None) -> EvidenceSpan | None:
        if evidence is not None and all(e.id != evidence.id for e in self.evidence):
            self.evidence.append(evidence)
        return evidence

    def dedupe_evidence(self) -> None:
        seen: dict[str, EvidenceSpan] = {}
        for span in self.evidence:
            seen.setdefault(span.id, span)
        self.evidence = list(seen.values())
