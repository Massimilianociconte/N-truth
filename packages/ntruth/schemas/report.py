"""Report: sintesi, limiti, alert, fonti ed export (PRD 20, FR-027).

Il renderer non puo introdurre fatti assenti dal JSON (PRD 11.3). Il campo
`generated_at` e escluso dal checksum: due run sullo stesso input devono
produrre lo stesso contenuto (PRD NFR-02).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, model_validator

from ntruth import DISCLAIMER
from ntruth.design.schema import DesignCompilation
from ntruth.schemas.core import Determinability, NTruthModel, Severity, content_checksum
from ntruth.schemas.experiment import (
    Contradiction,
    CountRecord,
    ExclusionRecord,
    ExperimentBlock,
    PlausibleGraphSet,
    Question,
    Versions,
)
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
    ASSERTION = "assertion"
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
    n_planned: int | None = None
    n_declared: int | None = None
    n_observational: int | None = None
    n_analytical: int | None = None
    n_independent: int | None = None
    n_allocated: int | None = None
    n_treated: int | None = None
    n_observed: int | None = None
    n_excluded: int | None = None
    n_analysed: int | None = None
    # Adapter v3; i nuovi consumer usano n_analysed.
    n_analyzed: int | None = None
    biological_source_count: int | None = None
    # Campo legacy mantenuto per compatibilita di schema. Gli exporter v6 lo
    # lasciano sempre null; effective_n appartiene ai count_records diagnostici.
    effective_n: float | None = None
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
    determinability: Determinability
    path_status: PositivePathStatus
    status_reason: str
    methods_statement: MethodsStatement
    n_table: tuple[NTableRow, ...] = ()
    # Conteggi fisici/pubblicabili e diagnostici restano registri separati:
    # effective_n non rappresenta repliche indipendenti.
    count_records: tuple[CountRecord, ...] = ()
    diagnostic_count_records: tuple[CountRecord, ...] = ()
    suppressed_count_record_ids: tuple[str, ...] = ()
    exclusion_records: tuple[ExclusionRecord, ...] = ()
    contradictions: tuple[Contradiction, ...] = ()
    plausible_graph_set: PlausibleGraphSet | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    discriminating_question: Question | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    driver_checklist: tuple[DriverChecklistItem, ...] = ()
    statements: tuple[ReportStatement, ...] = ()
    candidate_analysis_strategies: tuple[str, ...] = ()
    decisive_question_ids: tuple[str, ...] = ()
    non_certifying: bool = True

    @model_validator(mode="after")
    def _multiple_state_is_never_vacuous(self) -> Self:
        if self.determinability is not Determinability.MULTIPLE_PLAUSIBLE_GRAPHS:
            if self.plausible_graph_set is not None or self.discriminating_question is not None:
                raise ValueError("alternative graphs sono pubblicabili solo nello stato MULTIPLE")
            return self
        if self.plausible_graph_set is None or self.discriminating_question is None:
            raise ValueError("MULTIPLE richiede alternative e domanda discriminante")
        if self.discriminating_question.id != self.plausible_graph_set.discriminating_question_id:
            raise ValueError("domanda discriminante incoerente con plausible_graph_set")
        if not self.discriminating_question.decisive:
            raise ValueError("la domanda discriminante pubblicata deve essere decisiva")
        return self


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


class VerificationSummary(NTruthModel):
    """Esito serializzabile del verificatore hard per un ExperimentBlock."""

    status: str
    violation_codes: tuple[str, ...] = ()
    warning_codes: tuple[str, ...] = ()
    checked_invariants: tuple[str, ...] = ()


class Report(NTruthModel):
    """Envelope del report, esportabile in JSON e HTML."""

    report_id: str
    status: Literal["complete", "partial", "failed"] = "complete"
    project_id: str
    project_name: str
    language: str = "it"
    domain_transparency: DomainTransparency = Field(default_factory=DomainTransparency)
    versions: Versions
    blocks: tuple[ExperimentBlock, ...] = ()
    summaries: tuple[BlockSummary, ...] = ()
    design_compilations: dict[str, DesignCompilation] = Field(default_factory=dict)
    rule_evaluations: dict[str, tuple[RuleEvaluation, ...]] = Field(default_factory=dict)
    verifier_results: dict[str, VerificationSummary] = Field(default_factory=dict)
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
        """Checksum del contenuto, escluso soltanto il timestamp di generazione."""
        payload = self.model_dump(mode="json", exclude={"generated_at"})
        return content_checksum(payload)

    @model_validator(mode="after")
    def _canonical_disclaimer(self) -> Self:
        if self.disclaimer != DISCLAIMER:
            raise ValueError("disclaimer del report non canonico")
        return self

    @model_validator(mode="after")
    def _block_envelopes_are_coherent(self) -> Self:
        block_ids = [block.id for block in self.blocks]
        if len(block_ids) != len(set(block_ids)):
            raise ValueError("report contiene ExperimentBlock ID duplicati")
        known = set(block_ids)
        blocks_by_id = {block.id: block for block in self.blocks}

        summary_ids = [summary.block_id for summary in self.summaries]
        if len(summary_ids) != len(set(summary_ids)):
            raise ValueError("report contiene summary duplicate per block")
        if unknown := set(summary_ids) - known:
            raise ValueError(f"summary riferiscono block sconosciuti: {sorted(unknown)}")

        mapped_ids = (
            ("design_compilations", set(self.design_compilations)),
            ("rule_evaluations", set(self.rule_evaluations)),
            ("verifier_results", set(self.verifier_results)),
            ("positive_outputs", set(self.positive_outputs)),
        )
        for label, identifiers in mapped_ids:
            if unknown := identifiers - known:
                raise ValueError(f"{label} riferisce block sconosciuti: {sorted(unknown)}")

        for block in self.blocks:
            if block.versions != self.versions:
                raise ValueError(f"versioni del block {block.id} incoerenti col report")
        for block_id, output in self.positive_outputs.items():
            if output.block_id != block_id:
                raise ValueError(f"positive output {block_id} contiene block_id incoerente")
            if output.determinability is not blocks_by_id[block_id].determinability:
                raise ValueError(
                    f"positive output {block_id} ha determinability incoerente col block"
                )
        for block_id, compilation in self.design_compilations.items():
            if compilation.analysis_handoff.block_id != block_id:
                raise ValueError(f"design compilation {block_id} appartiene a un altro block")
            if compilation.analysis_handoff.specification_id != compilation.specification_id:
                raise ValueError(f"design compilation {block_id} ha specification_id incoerente")
        return self

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
