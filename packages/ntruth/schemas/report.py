"""Report: sintesi, limiti, alert, fonti ed export (PRD 20, FR-027).

Il renderer non puo introdurre fatti assenti dal JSON (PRD 11.3). Il campo
`generated_at` e escluso dal checksum: due run sullo stesso input devono
produrre lo stesso contenuto (PRD NFR-02).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from ntruth import DISCLAIMER
from ntruth.design.schema import DesignCompilation
from ntruth.schemas.core import NTruthModel, Severity, content_checksum
from ntruth.schemas.experiment import ExperimentBlock, Versions
from ntruth.schemas.graph import GraphViolation
from ntruth.schemas.rules import RuleEvaluation


class DomainValidationStatus(StrEnum):
    """Stato esplicito della validazione scientifica del dominio (PRD NFR-14)."""

    VALIDATED = "validated"
    UNVALIDATED = "unvalidated"
    OUT_OF_SCOPE = "out_of_scope"
    UNKNOWN = "unknown"


class PositivePathStatus(StrEnum):
    """Esito prudente del percorso positivo del report.

    ``ready_for_review`` significa che il materiale consente una bozza da
    controllare, non che il disegno sia stato validato o certificato.
    """

    READY_FOR_REVIEW = "ready_for_review"
    CONDITIONAL = "conditional"
    INCOMPLETE = "incomplete"


class ChecklistStatus(StrEnum):
    """Stato osservazionale di una voce di checklist non certificante."""

    PRESENT = "present"
    PARTIAL = "partial"
    MISSING = "missing"
    NOT_ASSESSED = "not_assessed"


class StatementLayer(StrEnum):
    """Separazione esplicita fra cio che la fonte dice e cio che il sistema deduce."""

    FACT = "fact"
    INFERENCE = "inference"
    HYPOTHESIS = "hypothesis"
    LIMITATION = "limitation"


class ReportStatement(NTruthModel):
    """Affermazione evidence-linked mostrata nel layer corretto del report."""

    id: str
    layer: StatementLayer
    text: str
    evidence_ids: tuple[str, ...] = ()
    source: str = "deterministic_engine"


class MethodsStatement(NTruthModel):
    """Bozza Methods prodotta soltanto da campi gia presenti nel report."""

    text: str
    language: str
    evidence_ids: tuple[str, ...] = ()
    status: PositivePathStatus = PositivePathStatus.INCOMPLETE
    non_certifying: bool = True
    limitations: tuple[str, ...] = ()


class NTableRow(NTruthModel):
    """Riga machine-readable della tabella n, sempre legata a uno scope."""

    assessment_id: str
    scope: str
    biological_unit: str | None = None
    experimental_unit: str | None = None
    observational_unit: str | None = None
    analytical_unit: str | None = None
    n_declared: int | None = None
    n_observational: int | None = None
    n_independent: int | None = None
    n_allocated: int | None = None
    n_analyzed: int | None = None
    inferability: str
    conditional_scenarios: tuple[dict[str, object], ...] = ()
    evidence_ids: tuple[str, ...] = ()


class DriverChecklistItem(NTruthModel):
    """Mapping informativo alle sei voci DRIVER, senza dichiarare conformita."""

    item_id: str
    title: str
    status: ChecklistStatus = ChecklistStatus.NOT_ASSESSED
    note: str
    evidence_ids: tuple[str, ...] = ()
    source_url: str


class BlockPositiveOutput(NTruthModel):
    """Output utilizzabile del compilatore, separato dagli alert negativi."""

    block_id: str
    path_status: PositivePathStatus
    status_reason: str
    methods_statement: MethodsStatement
    n_table: tuple[NTableRow, ...] = ()
    driver_checklist: tuple[DriverChecklistItem, ...] = ()
    statements: tuple[ReportStatement, ...] = ()
    candidate_analysis_strategies: tuple[str, ...] = ()
    decisive_question_ids: tuple[str, ...] = ()
    non_certifying: bool = True


class DomainTransparency(NTruthModel):
    """Avviso machine-readable mostrabile prima di avviare l'analisi.

    Il campo descrive la validazione del prodotto, non una predizione OOD appresa.
    Finche non esiste una validazione indipendente, un dominio supportato dal codice
    resta comunque ``unvalidated``.
    """

    declared_domain: str = "unknown"
    validation_status: DomainValidationStatus = DomainValidationStatus.UNKNOWN
    supported_domains: tuple[str, ...] = ()
    validated_domains: tuple[str, ...] = ()
    ood_assessment: str = "not_evaluated"
    warning: str = "Dominio non dichiarato: validazione scientifica non determinabile."
    requires_acknowledgement: bool = True


class BlockSummary(NTruthModel):
    """Riga di sintesi per blocco, senza aggregazioni che nascondono i gap (FR-014)."""

    block_id: str
    title: str
    max_severity: Severity | None = None
    n_alerts: int = 0
    n_questions: int = 0
    n_unresolved_conflicts: int = 0
    assessments_with_independent_n: int = 0
    assessments_total: int = 0
    abstained: bool = False


class Report(NTruthModel):
    """Envelope del report, esportabile in JSON e HTML."""

    report_id: str
    project_id: str
    project_name: str
    language: str = "it"
    domain_transparency: DomainTransparency = Field(default_factory=DomainTransparency)
    versions: Versions
    blocks: tuple[ExperimentBlock, ...] = ()
    summaries: tuple[BlockSummary, ...] = ()
    design_compilations: dict[str, DesignCompilation] = Field(default_factory=dict)
    rule_evaluations: dict[str, tuple[RuleEvaluation, ...]] = Field(default_factory=dict)
    positive_outputs: dict[str, BlockPositiveOutput] = Field(default_factory=dict)
    graph_violations: tuple[GraphViolation, ...] = ()
    parser_warnings: tuple[str, ...] = ()
    limits: tuple[str, ...] = ()
    disclaimer: str = DISCLAIMER
    generated_at: str | None = None
    input_checksum: str = ""
    ruleset_checksum: str = ""
    extras: dict[str, str] = Field(default_factory=dict)

    def content_checksum(self) -> str:
        """Checksum del contenuto, escluso il timestamp di generazione."""
        payload = self.model_dump(mode="json", exclude={"generated_at", "report_id"})
        return content_checksum(payload)

    def totals(self) -> dict[str, int]:
        return {
            "blocks": len(self.blocks),
            "compiler_abstained": sum(
                1 for item in self.design_compilations.values() if item.abstained
            ),
            "alerts": sum(len(b.alerts) for b in self.blocks),
            "critical": sum(
                1 for b in self.blocks for a in b.alerts if a.severity is Severity.CRITICAL
            ),
            "insufficient": sum(
                1 for b in self.blocks for a in b.alerts if a.severity is Severity.INSUFFICIENT
            ),
            "questions": sum(len(b.questions) for b in self.blocks),
            "unresolved_conflicts": sum(
                1 for b in self.blocks for c in b.contradictions if c.status == "unresolved"
            ),
        }
