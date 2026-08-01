"""Orchestrazione locale: progetto -> Document IR -> grafo -> regole -> report.

Il flusso e quello della Figura 2 del PRD. Ogni passaggio e deterministico e
offline: nessuna chiamata di rete, nessun upload (PRD NFR-01, FR-035).
"""

from __future__ import annotations

from dataclasses import dataclass

from ntruth import GRAPH_VERSION, ONTOLOGY_VERSION, PARSER_VERSION, SCHEMA_VERSION
from ntruth.calibration.abstention import (
    AbstentionDecision,
    enforce_evidence_floor,
    evaluate_abstention,
)
from ntruth.design import DesignCompilation, compile_experiment_block
from ntruth.extract import extract
from ntruth.extract.blocks import SegmentedDocument, segment_document_ir
from ntruth.graph.builder import BuildResult, build_graph
from ntruth.graph.determinability import derive_determinability
from ntruth.graph.units import resolve_units
from ntruth.graph.validation import (
    GraphValidationError,
    assert_valid_experiment_block,
    blocking_violations,
)
from ntruth.ingest.project import Project
from ntruth.ingest.safety import SafetyError
from ntruth.parsers.registry import build_document_ir
from ntruth.reporting.positive import build_positive_output
from ntruth.rules.engine import apply_rules
from ntruth.rules.loader import load_ruleset
from ntruth.schemas.core import Severity, stable_id
from ntruth.schemas.document import DocumentIR, ParserStatus
from ntruth.schemas.experiment import ExperimentBlock, Versions
from ntruth.schemas.report import BlockSummary, Report
from ntruth.schemas.rules import RuleEvaluation, Ruleset
from ntruth.transparency import assess_domain

NO_ML_LIMIT = (
    "Estrazione interamente deterministica (regole e regex): il richiamo su testi non "
    "standard e inferiore a quello atteso dal layer ML, non ancora presente."
)


@dataclass
class BlockAnalysis:
    """Intermediate and final products for one structurally isolated block."""

    document: DocumentIR
    block: ExperimentBlock
    build: BuildResult
    abstention: AbstentionDecision
    evaluations: tuple[RuleEvaluation, ...]
    compilation: DesignCompilation
    rule_warnings: tuple[str, ...] = ()


@dataclass
class AnalysisResult:
    """Esito completo di un'analisi locale, con compatibilita sul primo blocco."""

    report: Report
    document: DocumentIR
    block_analyses: tuple[BlockAnalysis, ...]

    @property
    def block(self) -> ExperimentBlock:
        return self.report.blocks[0]

    @property
    def build(self) -> BuildResult:
        return self.block_analyses[0].build

    @property
    def abstention(self) -> AbstentionDecision:
        return self.block_analyses[0].abstention

    @property
    def evaluations(self) -> tuple[RuleEvaluation, ...]:
        return self.block_analyses[0].evaluations


def analyze_project(
    project: Project, *, ruleset: Ruleset | None = None, lang: str = "it"
) -> AnalysisResult:
    """Analizza tutti i file registrati in un progetto locale."""
    integrity_problems = project.verify_integrity()
    if integrity_problems:
        raise SafetyError("integrita del progetto non valida: " + "; ".join(integrity_problems))

    active_ruleset = ruleset or load_ruleset(
        project.manifest.ruleset_id, project.manifest.ruleset_version
    )
    domain_transparency = assess_domain(project.manifest.domain)

    document = build_document_ir(project)
    segmentation = segment_document_ir(document, project.manifest.name)

    versions = Versions(
        schema_version=SCHEMA_VERSION,
        parser_version=PARSER_VERSION,
        graph_version=GRAPH_VERSION,
        ruleset_id=active_ruleset.ruleset_id,
        ruleset_version=active_ruleset.version,
        ontology_version=ONTOLOGY_VERSION,
    )

    block_analyses = tuple(
        _analyze_block(
            segment,
            index=index,
            parent_document_id=document.id,
            ruleset=active_ruleset,
            versions=versions,
            lang=lang,
        )
        for index, segment in enumerate(segmentation.blocks)
    )
    blocks = tuple(analysis.block for analysis in block_analyses)
    report_limits = _report_limits(
        block_analyses,
        segmentation.warnings,
        domain_warning=domain_transparency.warning,
    )

    report = Report(
        report_id=stable_id("rep", *(block.id for block in blocks), active_ruleset.version),
        project_id=project.manifest.project_id,
        project_name=project.manifest.name,
        language=lang,
        domain_transparency=domain_transparency,
        versions=versions,
        blocks=blocks,
        summaries=tuple(
            _summarize(analysis.block, analysis.abstention) for analysis in block_analyses
        ),
        design_compilations={
            analysis.block.id: analysis.compilation for analysis in block_analyses
        },
        rule_evaluations={analysis.block.id: analysis.evaluations for analysis in block_analyses},
        positive_outputs={
            analysis.block.id: build_positive_output(
                analysis.block,
                language=lang,
                limits=report_limits,
                compilation=analysis.compilation,
            )
            for analysis in block_analyses
        },
        graph_violations=tuple(
            violation for analysis in block_analyses for violation in analysis.build.violations
        ),
        parser_warnings=_parser_warnings(document),
        limits=report_limits,
        input_checksum=project.manifest.checksum(),
        ruleset_checksum=active_ruleset.checksum(),
    )

    return AnalysisResult(
        report=report,
        document=document,
        block_analyses=block_analyses,
    )


def _analyze_block(
    segment: SegmentedDocument,
    *,
    index: int,
    parent_document_id: str,
    ruleset: Ruleset,
    versions: Versions,
    lang: str,
) -> BlockAnalysis:
    document = segment.document
    extraction = extract(document)
    block_id = stable_id("blk", parent_document_id, index, segment.key, segment.title)
    build = build_graph(block_id, extraction)
    blocking_build_violations = blocking_violations(build.violations)
    if blocking_build_violations:
        raise GraphValidationError(blocking_build_violations)
    candidate_block = ExperimentBlock(
        id=block_id,
        title=segment.title,
        document_id=document.id,
        source_file_ids=tuple(source.id for source in document.files),
        inference_targets=build.inference_targets,
        factors=build.factors,
        contrasts=build.contrasts,
        endpoints=build.endpoints,
        estimands=build.estimands,
        models=build.models,
        processes=build.processes,
        hierarchy=build.hierarchy,
        n_statements=build.n_statements,
        questions=build.questions,
        contradictions=build.contradictions,
        evidence=tuple(extraction.evidence),
        mentions=tuple(extraction.mentions),
        coreference_links=tuple(extraction.coreference_links),
        versions=versions,
    )
    # Il resolver e il rules engine leggono esclusivamente un grafo che ha gia
    # superato invarianti, riferimenti incrociati e provenance.
    assert_valid_experiment_block(candidate_block)
    assessments, resolver_questions = resolve_units(block_id, build)
    assessments = enforce_evidence_floor(assessments, document)
    rule_run = apply_rules(block_id, build, assessments, ruleset, lang=lang)
    abstention = evaluate_abstention(document, build, rule_run.assessments)
    questions_by_id = {
        question.id: question
        for question in (*build.questions, *resolver_questions, *rule_run.questions)
    }
    questions = tuple(
        sorted(
            questions_by_id.values(),
            key=lambda question: (
                not bool(getattr(question, "decisive", False)),
                -int(getattr(question, "priority", 0)),
                question.id,
            ),
        )
    )
    block = candidate_block.model_copy(
        update={
            "unit_assessments": rule_run.assessments,
            "alerts": rule_run.alerts,
            "questions": questions,
            "data_sufficiency": abstention.sufficiency,
        }
    )
    assert_valid_experiment_block(block)
    compilation = compile_experiment_block(block)
    block = block.model_copy(update={"determinability": derive_determinability(block, compilation)})
    return BlockAnalysis(
        document=document,
        block=block,
        build=build,
        abstention=abstention,
        evaluations=rule_run.evaluations,
        compilation=compilation,
        rule_warnings=rule_run.warnings,
    )


def _summarize(block: ExperimentBlock, abstention: AbstentionDecision) -> BlockSummary:
    return BlockSummary(
        block_id=block.id,
        title=block.title,
        max_severity=block.max_severity(),
        n_alerts=len(block.alerts),
        n_questions=len(block.questions),
        n_unresolved_conflicts=sum(1 for c in block.contradictions if c.status == "unresolved"),
        assessments_with_independent_n=sum(
            1 for a in block.unit_assessments if a.n_independent is not None
        ),
        assessments_total=len(block.unit_assessments),
        abstained=abstention.abstained,
    )


def replace_block_analysis(result: AnalysisResult, replacement: BlockAnalysis) -> AnalysisResult:
    """Sostituisce un blocco ricalcolato mantenendo coerente l'envelope del report.

    Usato dal correction engine: non ripete parsing o estrazione e non riusa
    assessment/alert precedenti dopo una patch agli input scientifici.
    """

    found = False
    analyses: list[BlockAnalysis] = []
    for analysis in result.block_analyses:
        if analysis.block.id == replacement.block.id:
            analyses.append(replacement)
            found = True
        else:
            analyses.append(analysis)
    if not found:
        raise KeyError(f"blocco non presente nel risultato: {replacement.block.id}")

    current = tuple(analyses)
    stable_limits = tuple(
        limit for limit in result.report.limits if not limit.startswith("Astensione:")
    )
    recalculated_limits = tuple(
        analysis.abstention.describe() for analysis in current if analysis.abstention.abstained
    )
    report = result.report.model_copy(
        update={
            "blocks": tuple(analysis.block for analysis in current),
            "summaries": tuple(
                _summarize(analysis.block, analysis.abstention) for analysis in current
            ),
            "design_compilations": {
                analysis.block.id: analysis.compilation for analysis in current
            },
            "rule_evaluations": {analysis.block.id: analysis.evaluations for analysis in current},
            "positive_outputs": {
                analysis.block.id: build_positive_output(
                    analysis.block,
                    language=result.report.language,
                    limits=tuple(dict.fromkeys((*stable_limits, *recalculated_limits))),
                    compilation=analysis.compilation,
                )
                for analysis in current
            },
            "graph_violations": tuple(
                violation for analysis in current for violation in analysis.build.violations
            ),
            "limits": tuple(dict.fromkeys((*stable_limits, *recalculated_limits))),
        }
    )
    return AnalysisResult(
        report=report,
        document=result.document,
        block_analyses=current,
    )


def _parser_warnings(document: DocumentIR) -> tuple[str, ...]:
    warnings: list[str] = []
    for source in document.files:
        for warning in source.warnings:
            warnings.append(f"{source.filename}: {warning}")
        if source.status is ParserStatus.FAILED:
            warnings.append(f"{source.filename}: parsing fallito, contenuto non analizzato")
        if source.status is ParserStatus.IGNORED:
            warnings.append(f"{source.filename}: ignorato ({source.ignored_reason})")
    for table in document.tables:
        warnings.extend(f"{table.name}: {w}" for w in table.warnings)
    return tuple(dict.fromkeys(warnings))


def _report_limits(
    analyses: tuple[BlockAnalysis, ...],
    segmentation_warnings: tuple[str, ...],
    *,
    domain_warning: str = "",
) -> tuple[str, ...]:
    limits = [*segmentation_warnings, NO_ML_LIMIT]
    if domain_warning:
        limits.append(domain_warning)
    for analysis in analyses:
        limits.extend(analysis.build.warnings)
        limits.extend(analysis.rule_warnings)
        if analysis.abstention.abstained:
            limits.append(analysis.abstention.describe())
        if any(source.status is ParserStatus.DEGRADED for source in analysis.document.files):
            limits.append(
                "Almeno un file ha prodotto testo di bassa qualita: le evidenze relative sono "
                "a confidenza ridotta e non sostengono alert critical da sole."
            )
    return tuple(dict.fromkeys(limits))


def severity_order(severity: Severity | None) -> int:
    order = {
        Severity.CRITICAL: 0,
        Severity.HIGH: 1,
        Severity.MEDIUM: 2,
        Severity.INSUFFICIENT: 3,
        Severity.INFO: 4,
    }
    return order.get(severity, 5) if severity else 5
