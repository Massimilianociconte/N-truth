"""Nodi e relazioni tipizzati dell'Experiment Graph (PRD 7.2 e 7.3).

Il grafo e l'unica struttura che le regole possono leggere (PRD 11.3):
il rules engine non vede mai il testo grezzo ne l'output del modello.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from ntruth.schemas.core import NTruthModel, Provenance, stable_id


class NodeType(StrEnum):
    """Nodi minimi del grafo (PRD 7.2)."""

    # Documentali
    DOCUMENT = "Document"
    SECTION = "Section"
    PARAGRAPH = "Paragraph"
    TABLE = "Table"
    FIGURE_LEGEND = "FigureLegend"
    EVIDENCE_SPAN = "EvidenceSpan"
    TABLE_CELL = "TableCell"
    METADATA_RECORD = "MetadataRecord"
    CODE_SPAN = "CodeSpan"
    USER_CONFIRMATION = "UserConfirmation"
    FILE = "File"

    # Disegno
    STUDY = "Study"
    EXPERIMENT_BLOCK = "ExperimentBlock"
    COHORT = "Cohort"
    GROUP = "Group"
    FACTOR = "Factor"
    FACTOR_LEVEL = "FactorLevel"
    LEVEL = "Level"
    TREATMENT = "Treatment"
    INTERVENTION = "Intervention"
    CONTRAST = "Contrast"
    ENDPOINT = "Endpoint"
    ESTIMAND = "Estimand"
    INFERENCE_TARGET = "InferenceTarget"
    ANALYTICAL_UNIT = "AnalyticalUnit"
    ANALYSIS = "Analysis"
    BLOCK = "Block"
    RANDOMISATION = "Randomisation"

    # Biologici
    HUMAN_DONOR = "HumanDonor"
    ANIMAL = "Animal"
    DAM = "Dam"
    LITTER = "Litter"
    CAGE = "Cage"
    TISSUE = "Tissue"
    PRIMARY_SAMPLE = "PrimarySample"
    PRIMARY_CULTURE = "PrimaryCulture"
    CELL_LINE = "CellLine"
    CELL_CULTURE = "CellCulture"
    ORGANOID = "Organoid"
    EXPLANT = "Explant"

    # Tecnici
    ALIQUOT = "Aliquot"
    POOL = "Pool"
    PLATE = "Plate"
    WELL = "Well"
    SECTION_SLICE = "Section_"  # sezione istologica, distinta da Section documentale
    FIELD = "Field"
    ROI = "ROI"
    CELL = "Cell"
    LIBRARY = "Library"
    RUN = "Run"
    INSTRUMENT = "Instrument"
    BATCH = "Batch"
    THAW = "Thaw"
    PASSAGE = "Passage"

    # Osservazioni
    IMAGE = "Image"
    OBJECT = "Object"
    SIGNAL = "Signal"
    TIMEPOINT = "Timepoint"
    ASSAY_RESULT = "AssayResult"

    # Numerici
    N_STATEMENT = "NStatement"
    COUNT = "Count"
    EXCLUSION = "Exclusion"
    AGGREGATION_RULE = "AggregationRule"
    STATISTICAL_MODEL = "StatisticalModel"

    # Governance
    MODEL_VERSION = "ModelVersion"
    RULE_VERSION = "RuleVersion"
    ONTOLOGY_VERSION = "OntologyVersion"
    USER_CORRECTION = "UserCorrection"
    ADJUDICATION = "Adjudication"
    LICENSE_RECORD = "LicenseRecord"


class RelationType(StrEnum):
    """Relazioni minime (PRD 7.3)."""

    CONTAINS = "contains"
    NESTED_IN = "nested_in"
    DERIVED_FROM = "derived_from"
    SPLIT_FROM = "split_from"
    SPLIT_INTO = "split_into"
    POOLED_FROM = "pooled_from"
    POOLED_INTO = "pooled_into"
    MEMBER_OF_POOL = "member_of_pool"

    PAIRED_WITH = "paired_with"
    MATCHED_WITH = "matched_with"
    BLOCKED_BY = "blocked_by"
    CROSSED_WITH = "crossed_with"
    SAME_SOURCE_AS = "same_source_as"

    TECHNICAL_REPLICATE_OF = "technical_replicate_of"
    BIOLOGICAL_REPLICATE_OF = "biological_replicate_of"
    REPEATED_MEASURE_OF = "repeated_measure_of"

    ASSIGNED_TO = "assigned_to"
    ALLOCATED_TO = "allocated_to"
    APPLIED_TO = "applied_to"
    RANDOMIZED_AT = "randomized_at"
    EXPOSED_TO = "exposed_to"
    MEASURED_ON = "measured_on"
    BELONGS_TO_GROUP = "belongs_to_group"

    PROCESSED_IN_BATCH = "processed_in_batch"
    ACQUIRED_IN_RUN = "acquired_in_run"
    AGGREGATED_BY = "aggregated_by"
    ANALYZED_AS = "analyzed_as"

    HAS_FACTOR = "has_factor"
    HAS_LEVEL = "has_level"
    DEFINES_CONTRAST = "defines_contrast"
    HAS_ENDPOINT = "has_endpoint"

    HAS_DECLARED_N = "has_declared_n"
    EXCLUDED_FROM = "excluded_from"
    CONTRADICTS = "contradicts"
    COREFERS_WITH = "corefers_with"
    SUPPORTS = "supports"
    SUPPORTED_BY_EVIDENCE = "supported_by_evidence"
    DECLARES_CLUSTERING = "declares_clustering"


#: Ordine di annidamento: rank piu basso = livello piu alto (piu vicino alla sorgente
#: biologica). Serve a decidere quale livello puo essere unita indipendente
#: (PRD 7.1: l'unita e relativa al fattore).
CONTAINMENT_RANK: dict[NodeType, int] = {
    NodeType.COHORT: 5,
    NodeType.CAGE: 10,
    NodeType.DAM: 15,
    NodeType.LITTER: 20,
    NodeType.HUMAN_DONOR: 30,
    NodeType.ANIMAL: 30,
    NodeType.CELL_LINE: 32,
    NodeType.TISSUE: 40,
    NodeType.PRIMARY_SAMPLE: 45,
    NodeType.EXPLANT: 48,
    NodeType.CELL_CULTURE: 50,
    NodeType.PRIMARY_CULTURE: 50,
    NodeType.ORGANOID: 50,
    NodeType.POOL: 55,
    NodeType.ALIQUOT: 58,
    NodeType.PLATE: 60,
    NodeType.RUN: 62,
    NodeType.LIBRARY: 65,
    NodeType.WELL: 70,
    NodeType.SECTION_SLICE: 75,
    NodeType.FIELD: 80,
    NodeType.IMAGE: 82,
    NodeType.ROI: 85,
    NodeType.OBJECT: 88,
    NodeType.CELL: 90,
}

#: Tipi che possono rappresentare una vera unita alla quale un livello viene
#: allocato o sulla quale una procedura viene applicata. Gli oggetti
#: documentali, inferenziali, numerici e di governance sono esclusi: un
#: ``Endpoint`` o un ``Estimand`` non puo diventare unita sperimentale solo
#: perche il client ne invia il valore enum corretto.
ALLOCATABLE_NODE_TYPES: frozenset[NodeType] = frozenset(
    {
        *CONTAINMENT_RANK,
        NodeType.BATCH,
        NodeType.THAW,
        NodeType.PASSAGE,
    }
)

#: Nodi che possono essere unita biologica sorgente (PRD 7: unita biologica).
BIOLOGICAL_SOURCE_TYPES: frozenset[NodeType] = frozenset(
    {
        NodeType.HUMAN_DONOR,
        NodeType.ANIMAL,
        NodeType.DAM,
        NodeType.LITTER,
        NodeType.CELL_LINE,
        NodeType.TISSUE,
        NodeType.PRIMARY_SAMPLE,
        NodeType.PRIMARY_CULTURE,
    }
)

#: Livelli puramente tecnici: non aumentano mai da soli l'n indipendente
#: (PRD MIC-003, SC-003, CC-003).
TECHNICAL_TYPES: frozenset[NodeType] = frozenset(
    {
        NodeType.ALIQUOT,
        NodeType.THAW,
        NodeType.PASSAGE,
        NodeType.PLATE,
        NodeType.WELL,
        NodeType.SECTION_SLICE,
        NodeType.FIELD,
        NodeType.IMAGE,
        NodeType.ROI,
        NodeType.OBJECT,
        NodeType.CELL,
        NodeType.SIGNAL,
        NodeType.TIMEPOINT,
        NodeType.ASSAY_RESULT,
        NodeType.LIBRARY,
        NodeType.RUN,
        NodeType.INSTRUMENT,
        NodeType.BATCH,
    }
)

#: Fonti di correlazione trasversali, non contenitori gerarchici (PRD 7: Batch, Cage).
CLUSTER_TYPES: frozenset[NodeType] = frozenset(
    {NodeType.BATCH, NodeType.CAGE, NodeType.LITTER, NodeType.RUN, NodeType.INSTRUMENT}
)


def rank_of(node_type: NodeType) -> int | None:
    """Posizione nella gerarchia di contenimento, None se il nodo non e un livello."""
    return CONTAINMENT_RANK.get(node_type)


class GraphNode(NTruthModel):
    """Nodo tipizzato. `count` rappresenta un livello aggregato (es. 120 cellule)."""

    id: str
    type: NodeType
    label: str
    count: int | None = Field(default=None, ge=0)
    attributes: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    evidence_ids: tuple[str, ...] = ()
    provenance: Provenance
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @property
    def rank(self) -> int | None:
        return rank_of(self.type)


class GraphRelation(NTruthModel):
    """Arco tipizzato fra due nodi."""

    id: str
    type: RelationType
    source: str
    target: str
    attributes: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    evidence_ids: tuple[str, ...] = ()
    provenance: Provenance
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class GraphViolation(NTruthModel):
    """Violazione di schema o invariante rilevata dal validatore."""

    code: str
    message: str
    node_ids: tuple[str, ...] = ()
    relation_ids: tuple[str, ...] = ()
    blocking: bool = True


def make_node_id(block_id: str, node_type: NodeType, label: str) -> str:
    return stable_id("nd", block_id, str(node_type), label.strip().lower())


def make_relation_id(rel_type: RelationType, source: str, target: str) -> str:
    return stable_id("rl", str(rel_type), source, target)
