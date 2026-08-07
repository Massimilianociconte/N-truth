"""Rendering del report: JSON come fonte di verita, HTML come vista (PRD 11.1)."""

import json
from collections.abc import Mapping
from pathlib import Path

from ntruth.capabilities import assess_core_profile_capability
from ntruth.design import (
    DesignSpecification,
    finalize_experiment_block_compilation,
    write_design_compilation,
    write_design_json_schema,
    write_design_specification,
)
from ntruth.parser_ai import parser_ai_json_schemas, parser_stage_json_schemas
from ntruth.reporting.html_report import render_html, write_html
from ntruth.reporting.json_report import (
    graph_to_dict,
    read_json,
    report_to_dict,
    write_graph,
    write_json,
    write_yaml,
)
from ntruth.reporting.positive import build_positive_output
from ntruth.reporting.privacy import (
    PrivacyAudit,
    ShareReadiness,
    write_privacy_audit,
    write_share_readiness,
)
from ntruth.reporting.ro_crate import ro_crate_to_dict, write_ro_crate
from ntruth.schemas.core import Determinability
from ntruth.schemas.experiment import GraphStatus
from ntruth.schemas.report import BlockSummary, Report, VerificationSummary
from ntruth.verifier import (
    apply_output_policy,
    apply_rule_evaluation_output_policy,
    verify_block,
)


def write_all(
    report: Report,
    out_dir: Path,
    *,
    additional_artifacts: Mapping[str, Path] | None = None,
    privacy_audit: PrivacyAudit | None = None,
    share_readiness: ShareReadiness | None = None,
) -> dict[str, Path]:
    """Scrive tutti gli export e genera la RO-Crate rigorosamente per ultima.

    Gli artefatti aggiuntivi devono essere gia presenti nella directory di
    export. Questo consente alle revisioni di includere candidate annotations e
    audit nel checksum della crate senza una seconda scrittura del metadata.
    """

    out_dir = Path(out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    public_blocks = []
    reconciled_compilations = {}
    reconciled_evaluations = {}
    reconciled_positive_outputs = {}
    reconciled_summaries = []
    reconciled_verifier_results = {}
    live_graph_findings = list(report.graph_violations)
    live_verification_limits = []
    for source_block in report.blocks:
        cached_verification = report.verifier_results.get(source_block.id)
        cached_violation_codes = set(
            cached_verification.violation_codes if cached_verification is not None else ()
        )
        cached_warning_codes = set(
            cached_verification.warning_codes if cached_verification is not None else ()
        )
        # ``graph_violations`` e globale e non porta un block_id: non deve
        # essere reidratato dentro una verifica per solo code, perche in un
        # report multi-blocco attribuirebbe potenzialmente il finding del blocco
        # B al blocco A. La cache resta un gate fail-closed nel summary; i
        # finding strutturati gia presenti restano nel registro globale.
        source_verification = verify_block(source_block, check_output_policy=False)
        public_candidate = source_block
        if source_verification.violations:
            public_candidate = source_block.model_copy(
                update={
                    "graph_status": GraphStatus.INVALID,
                    "determinability": Determinability.INVALID_GRAPH,
                    "plausible_graph_set": None,
                }
            )
        block = apply_output_policy(public_candidate)
        public_blocks.append(block)
        public_verification = verify_block(
            block,
            additional_violations=(
                *source_verification.violations,
                *source_verification.warnings,
            ),
        )
        source_warnings = tuple(
            item
            for item in source_verification.warnings
            if not (cached_violation_codes and item.code == "invalid_state_without_hard_violation")
        )
        public_warnings = tuple(
            item
            for item in public_verification.warnings
            if not (cached_violation_codes and item.code == "invalid_state_without_hard_violation")
        )
        live_graph_findings.extend(
            (
                *source_verification.violations,
                *source_warnings,
                *public_verification.violations,
                *public_warnings,
            )
        )
        violation_codes = tuple(
            dict.fromkeys(
                (
                    *(item.code for item in source_verification.violations),
                    *(item.code for item in public_verification.violations),
                    *(
                        cached_verification.violation_codes
                        if cached_verification is not None
                        else ()
                    ),
                )
            )
        )
        warning_codes = tuple(
            dict.fromkeys(
                (
                    *(item.code for item in source_warnings),
                    *(item.code for item in public_warnings),
                    *(cached_verification.warning_codes if cached_verification is not None else ()),
                )
            )
        )
        checked_invariants = tuple(
            dict.fromkeys(
                (
                    *source_verification.checked_invariants,
                    *public_verification.checked_invariants,
                    *(
                        cached_verification.checked_invariants
                        if cached_verification is not None
                        else ()
                    ),
                )
            )
        )
        verification_status = (
            "failed" if violation_codes else ("partial" if warning_codes else "complete")
        )
        reconciled_verifier_results[block.id] = VerificationSummary(
            status=verification_status,
            violation_codes=violation_codes,
            warning_codes=warning_codes,
            checked_invariants=checked_invariants,
        )
        live_violation_codes = {
            *(item.code for item in source_verification.violations),
            *(item.code for item in public_verification.violations),
        }
        live_warning_codes = {
            *(item.code for item in source_warnings),
            *(item.code for item in public_warnings),
        }
        new_live_violations = sorted(live_violation_codes - cached_violation_codes)
        new_live_warnings = sorted(
            live_warning_codes - cached_warning_codes - cached_violation_codes
        )
        if new_live_violations:
            live_verification_limits.append(
                f"[ExperimentBlock {block.id}] Verificatore hard live fallito: "
                + ", ".join(new_live_violations)
            )
        elif new_live_warnings:
            live_verification_limits.append(
                f"[ExperimentBlock {block.id}] Verificatore hard live parziale: "
                + ", ".join(new_live_warnings)
            )
        verification_valid = not violation_codes
        capability = assess_core_profile_capability(block)
        compilation = finalize_experiment_block_compilation(
            block,
            supported_profile=capability.supported,
            verification_valid=verification_valid,
        )
        reconciled_compilations[block.id] = compilation
        reconciled_evaluations[block.id] = apply_rule_evaluation_output_policy(
            block,
            report.rule_evaluations.get(block.id, ()),
        )
        reconciled_positive_outputs[block.id] = build_positive_output(
            block,
            language=report.language,
            limits=_public_limits_for_block(report, block.id),
            compilation=compilation,
        )
        reconciled_summaries.append(
            BlockSummary(
                block_id=block.id,
                title=block.title,
                max_severity=block.max_severity(),
                n_alerts=len(block.alerts),
                n_questions=len(block.questions),
                n_unresolved_conflicts=sum(
                    1 for item in block.contradictions if item.status == "unresolved"
                ),
                assessments_with_independent_n=sum(
                    1 for item in block.unit_assessments if item.n_independent is not None
                ),
                assessments_total=len(block.unit_assessments),
                abstained=compilation.abstained,
            )
        )
    verification_statuses = tuple(item.status for item in reconciled_verifier_results.values())
    live_status = (
        "failed"
        if verification_statuses and all(item == "failed" for item in verification_statuses)
        else (
            "partial" if any(item != "complete" for item in verification_statuses) else "complete"
        )
    )
    status_rank = {"complete": 0, "partial": 1, "failed": 2}
    report_status = max((report.status, live_status), key=status_rank.__getitem__)
    unique_graph_findings = {
        (
            item.code,
            item.message,
            item.node_ids,
            item.relation_ids,
            item.blocking,
        ): item
        for item in live_graph_findings
    }
    report = report.model_copy(
        update={
            "status": report_status,
            "blocks": tuple(public_blocks),
            "summaries": tuple(reconciled_summaries),
            "design_compilations": reconciled_compilations,
            "rule_evaluations": reconciled_evaluations,
            "positive_outputs": reconciled_positive_outputs,
            "verifier_results": reconciled_verifier_results,
            "graph_violations": tuple(unique_graph_findings.values()),
            "limits": tuple(dict.fromkeys((*report.limits, *live_verification_limits))),
        }
    )
    # Il boundary di scrittura non puo affidarsi a ``model_copy``: il payload
    # pubblico finale deve poter essere riaperto con la validazione completa.
    report = Report.model_validate(report.model_dump(mode="json"))
    written: dict[str, Path] = {}
    for label, raw_path in (additional_artifacts or {}).items():
        if label == "ro_crate":
            raise ValueError("'ro_crate' e riservato al metadata generato per ultimo")
        path = raw_path.expanduser().resolve()
        try:
            path.relative_to(out_dir)
        except ValueError as exc:
            raise ValueError(
                f"artefatto aggiuntivo fuori dalla directory di export: {path}"
            ) from exc
        if not path.is_file():
            raise FileNotFoundError(f"artefatto aggiuntivo non trovato: {path}")
        written[label] = path

    written.update(
        {
            "json": write_json(report, out_dir / "report.json"),
            "yaml": write_yaml(report, out_dir / "report.yaml"),
            "html": write_html(report, out_dir / "report.html"),
        }
    )
    for index, block in enumerate(report.blocks):
        name = "graph.json" if index == 0 else f"graph-{index}.json"
        written[f"graph_{index}"] = write_graph(block, out_dir / name)
        specification = DesignSpecification.from_experiment_block(block)
        compilation = report.design_compilations[block.id]
        design_name = (
            "design-specification.json" if index == 0 else f"design-specification-{index}.json"
        )
        compilation_name = (
            "design-compilation.json" if index == 0 else f"design-compilation-{index}.json"
        )
        written[f"design_{index}"] = write_design_specification(
            specification, out_dir / design_name
        )
        written[f"compilation_{index}"] = write_design_compilation(
            compilation, out_dir / compilation_name
        )
    written["design_schema"] = write_design_json_schema(
        out_dir / "design-specification.schema.json"
    )
    legacy_parser_schemas = parser_ai_json_schemas()
    written["parser_ai_input_schema"] = _write_json_schema(
        legacy_parser_schemas["input"], out_dir / "parser-ai-input.schema.json"
    )
    written["parser_ai_output_legacy_schema"] = _write_json_schema(
        legacy_parser_schemas["output"],
        out_dir / "parser-ai-output-legacy-v2.schema.json",
    )
    for stage_name, schema in parser_stage_json_schemas().items():
        filename = f"{stage_name.replace('_', '-')}.schema.json"
        written[f"parser_stage_{stage_name}_schema"] = _write_json_schema(
            schema,
            out_dir / filename,
        )
    if privacy_audit is not None:
        written["privacy_scan"] = write_privacy_audit(privacy_audit, out_dir / "privacy-scan.json")
    if share_readiness is not None:
        written["share_readiness"] = write_share_readiness(
            share_readiness, out_dir / "share-readiness.json"
        )
    # Invariante: nessun artefatto della revisione viene scritto dopo la crate.
    written["ro_crate"] = write_ro_crate(report, out_dir, written)
    return written


def _public_limits_for_block(report: Report, block_id: str) -> tuple[str, ...]:
    """Ricostruisce i limiti globali e quelli attribuiti al singolo blocco."""

    generic_prefix = "[ExperimentBlock "
    block_prefix = f"[ExperimentBlock {block_id}] "
    global_limits = tuple(item for item in report.limits if not item.startswith(generic_prefix))
    block_limits = tuple(
        item.removeprefix(block_prefix) for item in report.limits if item.startswith(block_prefix)
    )
    return tuple(dict.fromkeys((*global_limits, *block_limits)))


def _write_json_schema(schema: dict[str, object], path: Path) -> Path:
    path.write_text(
        json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return path


__all__ = [
    "PrivacyAudit",
    "ShareReadiness",
    "graph_to_dict",
    "read_json",
    "render_html",
    "report_to_dict",
    "ro_crate_to_dict",
    "write_all",
    "write_graph",
    "write_html",
    "write_json",
    "write_ro_crate",
    "write_yaml",
]
