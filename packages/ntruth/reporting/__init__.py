"""Rendering del report: JSON come fonte di verita, HTML come vista (PRD 11.1)."""

import json
from collections.abc import Mapping
from pathlib import Path

from ntruth.design import (
    DesignSpecification,
    compile_experiment_block,
    write_design_compilation,
    write_design_json_schema,
    write_design_specification,
)
from ntruth.parser_ai import parser_ai_json_schemas
from ntruth.reporting.html_report import render_html, write_html
from ntruth.reporting.json_report import (
    graph_to_dict,
    read_json,
    report_to_dict,
    write_graph,
    write_json,
    write_yaml,
)
from ntruth.reporting.privacy import (
    PrivacyAudit,
    ShareReadiness,
    write_privacy_audit,
    write_share_readiness,
)
from ntruth.reporting.ro_crate import ro_crate_to_dict, write_ro_crate
from ntruth.schemas.report import Report


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
        compilation = report.design_compilations.get(block.id) or compile_experiment_block(block)
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
    parser_schemas = parser_ai_json_schemas()
    written["parser_ai_input_schema"] = _write_json_schema(
        parser_schemas["input"], out_dir / "parser-ai-input.schema.json"
    )
    written["parser_ai_output_schema"] = _write_json_schema(
        parser_schemas["output"], out_dir / "parser-ai-output.schema.json"
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
