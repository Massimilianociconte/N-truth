"""Orchestrazione locale: progetto -> Document IR -> grafo -> regole -> report.

Il flusso e quello della Figura 2 del PRD. Ogni passaggio e deterministico e
offline: nessuna chiamata di rete, nessun upload (PRD NFR-01, FR-035).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ntruth import GRAPH_VERSION, ONTOLOGY_VERSION, PARSER_VERSION, SCHEMA_VERSION
from ntruth.calibration.abstention import (
    AbstentionDecision,
    enforce_evidence_floor,
    evaluate_abstention,
)
from ntruth.capabilities import (
    CORE_PROFILE_REFERENCE,
    assess_core_profile_capability,
)
from ntruth.design import (
    DesignCompilation,
    compile_experiment_block,
    finalize_experiment_block_compilation,
)
from ntruth.extract import extract
from ntruth.extract.blocks import SegmentedDocument, segment_document_ir
from ntruth.graph.builder import BuildResult, build_graph
from ntruth.graph.determinability import derive_determinability
from ntruth.graph.units import resolve_units
from ntruth.graph.validation import (
    assert_valid_experiment_block,
)
from ntruth.ingest.project import Project
from ntruth.ingest.safety import SafetyError
from ntruth.parsers.registry import build_document_ir
from ntruth.reporting.positive import build_positive_output
from ntruth.rules.engine import apply_rules
from ntruth.rules.loader import load_ruleset
from ntruth.schemas.core import Determinability, Severity, stable_id
from ntruth.schemas.document import DocumentIR, ParserStatus
from ntruth.schemas.experiment import (
    ExclusionRecord,
    ExperimentBlock,
    GraphStatus,
    TriState,
    Versions,
)
from ntruth.schemas.graph import GraphViolation
from ntruth.schemas.manifest import ReleaseProfile
from ntruth.schemas.report import BlockSummary, Report, VerificationSummary
from ntruth.schemas.rules import RuleEvaluation, Ruleset
from ntruth.transparency import assess_domain
from ntruth.verifier import (
    HardVerificationResult,
    SemanticVerificationResult,
    apply_output_policy,
    apply_rule_evaluation_output_policy,
    verify_block,
    verify_semantic,
)

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
    verification: HardVerificationResult
    release_profile: ReleaseProfile
    rule_warnings: tuple[str, ...] = ()
    semantic_verification: SemanticVerificationResult | None = None


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
    if not _has_usable_parser_output(document):
        raise SafetyError(
            "nessuna fonte ha prodotto testo, tabelle o codice utilizzabili; "
            "gli output scientifici non vengono generati"
        )
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
            release_profile=project.manifest.release_profile,
        )
        for index, segment in enumerate(segmentation.blocks)
    )
    blocks = tuple(analysis.block for analysis in block_analyses)
    global_limits = _global_report_limits(
        segmentation.warnings,
        domain_warning=domain_transparency.warning,
    )
    report_limits = _report_limits(
        block_analyses,
        segmentation.warnings,
        domain_warning=domain_transparency.warning,
    )

    report = Report(
        report_id=stable_id("rep", *(block.id for block in blocks), active_ruleset.version),
        status=_report_status(document, block_analyses),
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
        rule_evaluations={
            analysis.block.id: apply_rule_evaluation_output_policy(
                analysis.block,
                analysis.evaluations,
            )
            for analysis in block_analyses
        },
        verifier_results={
            analysis.block.id: _verification_summary(analysis.verification)
            for analysis in block_analyses
        },
        positive_outputs={
            analysis.block.id: build_positive_output(
                analysis.block,
                language=lang,
                limits=(*global_limits, *_analysis_limits(analysis)),
                compilation=analysis.compilation,
            )
            for analysis in block_analyses
        },
        graph_violations=_all_graph_violations(block_analyses),
        parser_warnings=_parser_warnings(document),
        limits=report_limits,
        input_checksum=project.manifest.checksum(),
        ruleset_checksum=active_ruleset.checksum(),
        extras={
            "release_profile": project.manifest.release_profile.value,
            "scientific_profile": CORE_PROFILE_REFERENCE,
            "train": "D",
            "prd_contract": "v6.0",
        },
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
    release_profile: ReleaseProfile,
) -> BlockAnalysis:
    document = segment.document
    extraction = extract(document)
    block_id = stable_id("blk", parent_document_id, index, segment.key, segment.title)
    build = build_graph(block_id, extraction)
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
        exclusion_records=_exclusion_records(build),
        hierarchy=build.hierarchy,
        n_statements=build.n_statements,
        questions=build.questions,
        contradictions=build.contradictions,
        evidence=tuple(extraction.evidence),
        mentions=tuple(extraction.mentions),
        coreference_links=tuple(extraction.coreference_links),
        versions=versions,
    )
    preflight = verify_block(
        candidate_block,
        check_output_policy=False,
        additional_violations=build.violations,
    )
    if preflight.violations:
        invalid_block = apply_output_policy(
            candidate_block.model_copy(
                update={
                    "graph_status": GraphStatus.INVALID,
                    "determinability": Determinability.INVALID_GRAPH,
                }
            )
        )
        abstention = evaluate_abstention(document, build, ())
        verification = verify_block(
            invalid_block,
            check_output_policy=False,
            # La proiezione INVALID_GRAPH rimuove intenzionalmente output
            # illeciti (per esempio un INDEPENDENT_N non autorizzato). La
            # causa hard osservata sul candidate preflight deve pero restare
            # nel record di verifica pubblico e auditabile.
            additional_violations=preflight.violations,
        )
        compilation = finalize_experiment_block_compilation(
            invalid_block,
            supported_profile=_supported_by_release_profile(invalid_block, release_profile),
            verification_valid=not verification.violations,
        )
        # Semantic non puo sanare hard-invalid; viene comunque eseguito per audit.
        semantic = verify_semantic(invalid_block)
        return BlockAnalysis(
            document=document,
            block=invalid_block,
            build=build,
            abstention=abstention,
            evaluations=(),
            compilation=compilation,
            verification=verification,
            release_profile=release_profile,
            rule_warnings=("Regole non eseguite: il verificatore hard ha rifiutato il grafo.",),
            semantic_verification=semantic,
        )
    # Il resolver e il rules engine leggono esclusivamente un grafo che ha gia
    # superato invarianti, riferimenti incrociati e provenance.
    assert_valid_experiment_block(candidate_block)
    assessments, resolver_questions = resolve_units(block_id, build)
    assessments = enforce_evidence_floor(assessments, document)
    rule_run = apply_rules(
        block_id,
        build,
        assessments,
        ruleset,
        lang=lang,
        evidence_by_id={item.id: item for item in candidate_block.evidence},
    )
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
    preliminary_compilation = compile_experiment_block(block)
    supported_profile = _supported_by_release_profile(block, release_profile)
    block = block.model_copy(
        update={
            "determinability": derive_determinability(
                block,
                preliminary_compilation,
                supported_profile=supported_profile,
            )
        }
    )
    block = apply_output_policy(block)
    verification = verify_block(block, additional_violations=build.violations)
    semantic = verify_semantic(block)
    compilation = finalize_experiment_block_compilation(
        block,
        supported_profile=supported_profile,
        verification_valid=not verification.violations,
    )
    return BlockAnalysis(
        document=document,
        block=block,
        build=build,
        abstention=abstention,
        evaluations=rule_run.evaluations,
        compilation=compilation,
        verification=verification,
        release_profile=release_profile,
        rule_warnings=rule_run.warnings,
        semantic_verification=semantic,
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


def _exclusion_records(build: BuildResult) -> tuple[ExclusionRecord, ...]:
    """Materializza esclusioni evidence-linked senza inventare lo scope mancante."""

    records: list[ExclusionRecord] = []
    for process in build.processes:
        if "exclusion" not in process.kind.casefold() or process.node_type is None:
            continue
        endpoint = next(
            (
                item
                for item in build.endpoints
                if process.endpoint_hint
                and item.name.casefold() == process.endpoint_hint.casefold()
            ),
            None,
        )
        unknown_reasons = {
            "phase": "not reported in source",
            "prespecified": "not reported in source",
            "author_role": "not reported in source",
        }
        if endpoint is None:
            unknown_reasons["endpoint_id"] = "not reported or not resolvable in source"
        if not process.group_hint:
            unknown_reasons["group"] = "not reported in source"
        if not process.evidence_ids:
            unknown_reasons["evidence_ids"] = "source evidence unavailable"
        records.append(
            ExclusionRecord(
                id=stable_id("exc", process.id, process.endpoint_hint, process.group_hint),
                unit_type=process.node_type,
                prespecified=TriState.UNKNOWN,
                endpoint_id=endpoint.id if endpoint else None,
                group=process.group_hint,
                reason=process.detail.strip() or "reason not reported",
                evidence_ids=process.evidence_ids,
                impact=(
                    f"excluded_count={process.value}"
                    if process.value is not None
                    else "excluded count not reported"
                ),
                unknown_reasons=unknown_reasons,
                provenance=process.provenance,
            )
        )
    return tuple(records)


def _supported_by_release_profile(
    block: ExperimentBlock,
    release_profile: ReleaseProfile,
) -> bool | None:
    """Adapter compatibile per il capability boundary scientifico versionato.

    ``release_profile`` governa soltanto i formati di input. Anche il profilo
    esteso deve attraversare lo stesso confine scientifico D0 finche non esiste
    un profilo scientifico successivo, esplicito e validato.
    """

    del release_profile
    return assess_core_profile_capability(block).supported


def _verification_summary(result: HardVerificationResult) -> VerificationSummary:
    return VerificationSummary(
        status=result.status.value,
        violation_codes=tuple(item.code for item in result.violations),
        warning_codes=tuple(item.code for item in result.warnings),
        checked_invariants=result.checked_invariants,
    )


def _all_graph_violations(
    analyses: tuple[BlockAnalysis, ...],
) -> tuple[GraphViolation, ...]:
    unique = {
        (item.code, item.message, item.node_ids, item.relation_ids, item.blocking): item
        for analysis in analyses
        for item in (
            *analysis.build.violations,
            *analysis.verification.violations,
            *analysis.verification.warnings,
        )
    }
    return tuple(unique.values())


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
    previous_dynamic_limits = {
        limit
        for analysis in result.block_analyses
        for limit in _attributed_analysis_limits(analysis)
    }
    stable_limits = tuple(
        limit for limit in result.report.limits if limit not in previous_dynamic_limits
    )
    recalculated_limits = tuple(
        limit for analysis in current for limit in _attributed_analysis_limits(analysis)
    )
    report_limits = tuple(dict.fromkeys((*stable_limits, *recalculated_limits)))
    report = result.report.model_copy(
        update={
            "status": _report_status(result.document, current),
            "blocks": tuple(analysis.block for analysis in current),
            "summaries": tuple(
                _summarize(analysis.block, analysis.abstention) for analysis in current
            ),
            "design_compilations": {
                analysis.block.id: analysis.compilation for analysis in current
            },
            "rule_evaluations": {
                analysis.block.id: apply_rule_evaluation_output_policy(
                    analysis.block,
                    analysis.evaluations,
                )
                for analysis in current
            },
            "verifier_results": {
                analysis.block.id: _verification_summary(analysis.verification)
                for analysis in current
            },
            "positive_outputs": {
                analysis.block.id: build_positive_output(
                    analysis.block,
                    language=result.report.language,
                    limits=(*stable_limits, *_analysis_limits(analysis)),
                    compilation=analysis.compilation,
                )
                for analysis in current
            },
            "graph_violations": _all_graph_violations(current),
            "limits": report_limits,
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


def _has_usable_parser_output(document: DocumentIR) -> bool:
    usable_file_ids = {
        source.id
        for source in document.files
        if source.status in {ParserStatus.OK, ParserStatus.DEGRADED}
    }
    return bool(
        any(document.texts.get(file_id, "").strip() for file_id in usable_file_ids)
        or any(table.file_id in usable_file_ids for table in document.tables)
        or any(item.file_id in usable_file_ids for item in document.statistical_code)
    )


def _report_status(
    document: DocumentIR,
    analyses: tuple[BlockAnalysis, ...],
) -> Literal["complete", "partial", "failed"]:
    from ntruth.verifier import VerificationStatus

    if analyses and all(
        analysis.verification.status is VerificationStatus.FAILED for analysis in analyses
    ):
        return "failed"
    parser_partial = any(
        source.status in {ParserStatus.DEGRADED, ParserStatus.FAILED, ParserStatus.IGNORED}
        for source in document.files
    )
    verifier_partial = any(
        analysis.verification.status is not VerificationStatus.COMPLETE for analysis in analyses
    )
    return "partial" if parser_partial or verifier_partial else "complete"


def _report_limits(
    analyses: tuple[BlockAnalysis, ...],
    segmentation_warnings: tuple[str, ...],
    *,
    domain_warning: str = "",
) -> tuple[str, ...]:
    limits = list(
        _global_report_limits(
            segmentation_warnings,
            domain_warning=domain_warning,
        )
    )
    for analysis in analyses:
        limits.extend(_attributed_analysis_limits(analysis))
    return tuple(dict.fromkeys(limits))


def _global_report_limits(
    segmentation_warnings: tuple[str, ...],
    *,
    domain_warning: str = "",
) -> tuple[str, ...]:
    """Limiti realmente condivisi da tutti i blocchi del documento."""

    limits = [*segmentation_warnings, NO_ML_LIMIT]
    if domain_warning:
        limits.append(domain_warning)
    return tuple(dict.fromkeys(limits))


def _attributed_analysis_limits(analysis: BlockAnalysis) -> tuple[str, ...]:
    """Limiti globali attribuiti, senza contaminarne la vista positiva altrui."""

    prefix = f"[ExperimentBlock {analysis.block.id}] "
    return tuple(prefix + limit for limit in _analysis_limits(analysis))


def _analysis_limits(analysis: BlockAnalysis) -> tuple[str, ...]:
    """Limiti derivati dal singolo blocco, da rigenerare dopo ogni correzione."""

    limits = [*analysis.build.warnings, *analysis.rule_warnings]
    if analysis.verification.violations:
        limits.append(
            "Verificatore hard: "
            + "; ".join(f"{item.code}: {item.message}" for item in analysis.verification.violations)
        )
    limits.extend(
        f"Verificatore hard (warning): {warning.code}: {warning.message}"
        for warning in analysis.verification.warnings
    )
    if analysis.abstention.abstained:
        limits.append(analysis.abstention.describe())
    if analysis.block.determinability is Determinability.OUT_OF_SCOPE:
        capability = assess_core_profile_capability(analysis.block)
        reason_codes = ", ".join(reason.value for reason in capability.reason_codes)
        reason_suffix = f" Motivi: {reason_codes}." if reason_codes else ""
        limits.append(
            f"ExperimentBlock fuori dal capability contract {CORE_PROFILE_REFERENCE}: "
            "nessuna unita sperimentale o n singolo viene pubblicato. Il profilo "
            "input esteso non amplia il perimetro scientifico." + reason_suffix
        )
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
