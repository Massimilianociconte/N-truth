"""Contratto formale e neutro del disegno sperimentale.

Il design IR raccoglie esclusivamente fatti gia presenti nell'ExperimentBlock.
Non sceglie test, non costruisce formule e non esegue power analysis.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Final, Literal, Self

from pydantic import Field, model_validator

from ntruth.schemas.core import EvidenceSpan, NTruthModel, content_checksum, stable_id
from ntruth.schemas.experiment import (
    Contradiction,
    Contrast,
    Endpoint,
    Estimand,
    ExperimentBlock,
    Factor,
    Hierarchy,
    InferenceTarget,
    InferenceTargetStatus,
    NStatement,
    ProcessFact,
    Question,
    StatisticalModelFact,
    UnitAssessment,
    Versions,
)
from ntruth.schemas.graph import NodeType, RelationType

DESIGN_SPECIFICATION_VERSION: Final[Literal["0.2.0"]] = "0.2.0"


class TargetPopulationSupport(StrEnum):
    """Completezza del collegamento target-popolazione, non validita del claim."""

    UNKNOWN = "unknown"
    CONDITIONAL = "conditional"
    SUPPORTED = "supported"


class CompilationStatus(StrEnum):
    """Esito del compiler rispetto al contratto inferenziale."""

    READY = "ready"
    ABSTAINED = "abstained"


class DesignSpecification(NTruthModel):
    """Snapshot JSON autosufficiente del design IR di un ExperimentBlock."""

    specification_version: Literal["0.2.0"] = DESIGN_SPECIFICATION_VERSION
    specification_id: str
    block_id: str
    title: str = ""
    document_id: str
    source_file_ids: tuple[str, ...] = ()
    inference_targets: tuple[InferenceTarget, ...] = ()
    factors: tuple[Factor, ...] = ()
    contrasts: tuple[Contrast, ...] = ()
    endpoints: tuple[Endpoint, ...] = ()
    estimands: tuple[Estimand, ...] = ()
    models: tuple[StatisticalModelFact, ...] = ()
    processes: tuple[ProcessFact, ...] = ()
    hierarchy: Hierarchy = Field(default_factory=Hierarchy)
    n_statements: tuple[NStatement, ...] = ()
    unit_assessments: tuple[UnitAssessment, ...] = ()
    questions: tuple[Question, ...] = ()
    contradictions: tuple[Contradiction, ...] = ()
    evidence: tuple[EvidenceSpan, ...] = ()
    versions: Versions

    @model_validator(mode="before")
    @classmethod
    def _upgrade_v01_payload(cls, data: object) -> object:
        """Accetta snapshot 0.1 e li normalizza al contratto 0.2.

        Gli adapter dei singoli fatti preservano ``assignment_*`` e gli altri
        alias legacy. Campi scientifici mancanti, come l'estimand, restano
        mancanti e faranno astenere il compiler: non vengono sintetizzati.
        """

        if not isinstance(data, Mapping):
            return data
        payload = dict(data)
        if payload.get("specification_version") == "0.1.0":
            payload["specification_version"] = DESIGN_SPECIFICATION_VERSION
        return payload

    @classmethod
    def from_experiment_block(cls, block: ExperimentBlock) -> Self:
        """Copia il solo stato scientifico necessario, senza alert o correzioni."""

        design_payload = block.model_dump(
            mode="json",
            include={
                "id",
                "title",
                "document_id",
                "source_file_ids",
                "inference_targets",
                "factors",
                "contrasts",
                "endpoints",
                "estimands",
                "models",
                "processes",
                "hierarchy",
                "n_statements",
                "unit_assessments",
                "questions",
                "contradictions",
                "evidence",
                "versions",
            },
        )
        return cls(
            specification_id=stable_id(
                "dsg",
                DESIGN_SPECIFICATION_VERSION,
                block.id,
                content_checksum(design_payload),
            ),
            block_id=block.id,
            title=block.title,
            document_id=block.document_id,
            source_file_ids=block.source_file_ids,
            inference_targets=block.inference_targets,
            factors=block.factors,
            contrasts=block.contrasts,
            endpoints=block.endpoints,
            estimands=block.estimands,
            models=block.models,
            processes=block.processes,
            hierarchy=block.hierarchy,
            n_statements=block.n_statements,
            unit_assessments=block.unit_assessments,
            questions=block.questions,
            contradictions=block.contradictions,
            evidence=block.evidence,
            versions=block.versions,
        )

    @model_validator(mode="after")
    def _references_are_local(self) -> Self:
        """Valida i riferimenti anche quando lo schema arriva da JSON esterno."""

        collections = {
            "inference target": tuple(target.id for target in self.inference_targets),
            "factor": tuple(factor.id for factor in self.factors),
            "contrast": tuple(contrast.id for contrast in self.contrasts),
            "endpoint": tuple(endpoint.id for endpoint in self.endpoints),
            "estimand": tuple(estimand.id for estimand in self.estimands),
            "model": tuple(model.id for model in self.models),
            "process": tuple(process.id for process in self.processes),
            "evidence": tuple(evidence.id for evidence in self.evidence),
        }
        for name, identifiers in collections.items():
            if len(identifiers) != len(set(identifiers)):
                raise ValueError(f"DesignSpecification: ID {name} duplicati")

        target_ids = set(collections["inference target"])
        factor_ids = set(collections["factor"])
        contrast_ids = set(collections["contrast"])
        endpoint_ids = set(collections["endpoint"])
        evidence_ids = set(collections["evidence"])
        contrasts_by_id = {contrast.id: contrast for contrast in self.contrasts}

        for target in self.inference_targets:
            checks = (
                ("factor", set(target.factor_ids) - factor_ids),
                ("contrast", set(target.contrast_ids) - contrast_ids),
                ("endpoint", set(target.endpoint_ids) - endpoint_ids),
                ("evidence", set(target.evidence_ids) - evidence_ids),
            )
            for kind, unknown in checks:
                if unknown:
                    raise ValueError(
                        f"DesignSpecification target {target.id}: {kind} refs sconosciuti "
                        f"{sorted(unknown)}"
                    )
            linked_contrasts = [contrasts_by_id[item] for item in target.contrast_ids]
            linked_factor_ids = {
                factor_id for contrast in linked_contrasts for factor_id in contrast.factor_ids
            }
            if target.factor_ids and not linked_factor_ids.issubset(target.factor_ids):
                raise ValueError(
                    f"DesignSpecification target {target.id}: contrast factor fuori scope"
                )
            linked_endpoint_ids = {
                endpoint_id
                for contrast in linked_contrasts
                for endpoint_id in contrast.endpoint_ids
            }
            if linked_endpoint_ids and not set(target.endpoint_ids).issubset(linked_endpoint_ids):
                raise ValueError(
                    f"DesignSpecification target {target.id}: endpoint fuori contrasto"
                )

        for estimand in self.estimands:
            unknown_factors = set(estimand.factor_ids) - factor_ids
            unknown_evidence = set(estimand.evidence_ids) - evidence_ids
            if estimand.endpoint_id not in endpoint_ids:
                raise ValueError(
                    f"DesignSpecification estimand {estimand.id}: endpoint ref sconosciuto"
                )
            if unknown_factors:
                raise ValueError(
                    f"DesignSpecification estimand {estimand.id}: factor refs sconosciuti "
                    f"{sorted(unknown_factors)}"
                )
            if unknown_evidence:
                raise ValueError(
                    f"DesignSpecification estimand {estimand.id}: evidence refs sconosciuti "
                    f"{sorted(unknown_evidence)}"
                )

        for label, facts in (("model", self.models), ("process", self.processes)):
            for fact in facts:
                unknown_evidence = set(fact.evidence_ids) - evidence_ids
                if unknown_evidence:
                    raise ValueError(
                        f"DesignSpecification {label} {fact.id}: evidence refs sconosciuti "
                        f"{sorted(unknown_evidence)}"
                    )

        scoped_references = [
            *((item.id, item.scope) for item in self.n_statements),
            *((item.id, item.scope) for item in self.unit_assessments),
            *((item.id, item.scope) for item in self.questions),
        ]
        for item_id, scope in scoped_references:
            target_id = scope.inference_target_id if scope is not None else None
            if target_id is not None and target_id not in target_ids:
                raise ValueError(
                    f"DesignSpecification: scope di {item_id} riferisce target sconosciuto "
                    f"{target_id}"
                )
        return self


class ElicitationResult(NTruthModel):
    """Domande deterministiche necessarie a completare il design IR."""

    specification_id: str
    questions: tuple[Question, ...] = ()
    blocking_question_ids: tuple[str, ...] = ()
    complete: bool = False


class AllocationHandoff(NTruthModel):
    """Allocation indipendente del fattore, distinta dall'applicazione fisica."""

    factor_id: str
    factor_name: str
    allocation_level: NodeType | None = None
    allocation_confidence: float = Field(ge=0.0, le=1.0)
    randomized: bool | None = None
    allocation_evidence_ids: tuple[str, ...] = ()
    # Adapter di lettura/scrittura per snapshot v0.1.
    assignment_level: NodeType | None = None
    assignment_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="before")
    @classmethod
    def _upgrade_assignment_alias(cls, data: object) -> object:
        if not isinstance(data, Mapping):
            return data
        payload = dict(data)
        if "allocation_level" not in payload and "assignment_level" in payload:
            payload["allocation_level"] = payload["assignment_level"]
        elif "assignment_level" not in payload and "allocation_level" in payload:
            payload["assignment_level"] = payload["allocation_level"]
        if "allocation_confidence" not in payload and "assignment_confidence" in payload:
            payload["allocation_confidence"] = payload["assignment_confidence"]
        elif "assignment_confidence" not in payload and "allocation_confidence" in payload:
            payload["assignment_confidence"] = payload["allocation_confidence"]
        if "allocation_evidence_ids" not in payload and payload.get("evidence_ids"):
            payload["allocation_evidence_ids"] = payload["evidence_ids"]
        return payload

    @model_validator(mode="after")
    def _aliases_are_coherent(self) -> Self:
        if self.assignment_level is not self.allocation_level:
            raise ValueError("assignment_level incoerente con allocation_level")
        if self.assignment_confidence != self.allocation_confidence:
            raise ValueError("assignment_confidence incoerente con allocation_confidence")
        return self


class ApplicationHandoff(NTruthModel):
    """Luogo fisico di applicazione, senza implicazioni automatiche sull'EU."""

    factor_id: str
    factor_name: str
    application_level: NodeType | None = None
    application_confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: tuple[str, ...] = ()


class EstimandHandoff(NTruthModel):
    """Estimand minimo riportato senza selezionare formula o test."""

    estimand_id: str
    endpoint_id: str
    effect_measure: str
    target_population_or_unit: str
    generalization_level: str
    factor_ids: tuple[str, ...]
    timepoint: str | None = None
    condition: str | None = None
    evidence_ids: tuple[str, ...] = ()


class NestingHandoff(NTruthModel):
    """Arco gerarchico riportato senza reinterpretazione statistica."""

    relation_id: str
    relation_type: RelationType
    source_node_id: str
    source_node_type: NodeType | None = None
    target_node_id: str
    target_node_type: NodeType | None = None
    evidence_ids: tuple[str, ...] = ()


class ClusterHandoff(NTruthModel):
    """Livello potenzialmente correlato gia dichiarato negli assessment/grafo."""

    node_type: NodeType
    node_ids: tuple[str, ...] = ()
    source_assessment_ids: tuple[str, ...] = ()
    source_model_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()


class RepeatedMeasureHandoff(NTruthModel):
    """Relazione repeated_measure_of esplicita; nessuna struttura e inventata."""

    relation_id: str
    source_node_id: str
    target_node_id: str
    evidence_ids: tuple[str, ...] = ()


class EndpointHandoff(NTruthModel):
    """Endpoint e livello di misura dichiarati."""

    endpoint_id: str
    name: str
    measured_on: NodeType | None = None
    timepoints: tuple[str, ...] = ()
    aggregation: str | None = None
    evidence_ids: tuple[str, ...] = ()


class TargetHandoff(NTruthModel):
    """Scope inferenziale conservato separatamente dagli altri target."""

    inference_target_id: str
    status: InferenceTargetStatus
    question_text: str = ""
    claim_text: str = ""
    population_of_inference: str = ""
    target_biological_unit: NodeType | None = None
    factor_ids: tuple[str, ...] = ()
    contrast_ids: tuple[str, ...] = ()
    endpoint_ids: tuple[str, ...] = ()
    estimand_ids: tuple[str, ...] = ()
    assessment_ids: tuple[str, ...] = ()
    target_population_support: TargetPopulationSupport = TargetPopulationSupport.UNKNOWN


class UnresolvedAssumption(NTruthModel):
    """Informazione non disponibile che impedisce una compilazione piena."""

    id: str
    code: str
    message: str
    blocking: bool = True
    inference_target_id: str | None = None
    source_question_id: str | None = None
    source_contradiction_id: str | None = None


class AnalysisHandoff(NTruthModel):
    """Passaggio neutro a un biostatistico o a un plugin futuro validato."""

    specification_id: str
    block_id: str
    target_population_support: TargetPopulationSupport = TargetPopulationSupport.UNKNOWN
    targets: tuple[TargetHandoff, ...] = ()
    allocations: tuple[AllocationHandoff, ...] = ()
    applications: tuple[ApplicationHandoff, ...] = ()
    nesting: tuple[NestingHandoff, ...] = ()
    clusters: tuple[ClusterHandoff, ...] = ()
    repeated_measures: tuple[RepeatedMeasureHandoff, ...] = ()
    endpoints: tuple[EndpointHandoff, ...] = ()
    estimands: tuple[EstimandHandoff, ...] = ()
    unresolved_assumptions: tuple[UnresolvedAssumption, ...] = ()
    prohibited_outputs: tuple[str, ...] = (
        "statistical_test_selection",
        "model_formula",
        "power_analysis",
    )


class DesignCompilation(NTruthModel):
    """Esito riproducibile del compiler, incluse astensione e domande."""

    specification_id: str
    status: CompilationStatus
    abstained: bool
    elicitation: ElicitationResult
    analysis_handoff: AnalysisHandoff
