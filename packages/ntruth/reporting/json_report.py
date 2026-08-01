"""Export JSON e graph.json (PRD FR-015, FR-027).

Il JSON e la fonte di verita del report: l'HTML e una vista e non puo
introdurre fatti che qui non esistono (PRD 11.3).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ntruth import DISCLAIMER
from ntruth.schemas.experiment import ExperimentBlock
from ntruth.schemas.report import Report


def report_to_dict(report: Report) -> dict[str, Any]:
    payload = report.model_dump(mode="json")
    payload["content_checksum"] = report.content_checksum()
    payload["totals"] = report.totals()
    payload["disclaimer"] = DISCLAIMER
    return payload


def write_json(report: Report, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report_to_dict(report), indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return path


def write_yaml(report: Report, path: Path) -> Path:
    """Scrive un documento YAML 1.2 deterministico senza una nuova dipendenza.

    YAML 1.2 e un superset di JSON: la serializzazione canonica JSON e quindi
    leggibile da parser YAML conformi e mantiene identico il contenuto logico
    dei due export.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report_to_dict(report), indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def read_json(path: Path) -> Report:
    """Riapre un report esportato e ne verifica il checksum dichiarato."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    expected_checksum = payload.pop("content_checksum", None)
    payload.pop("totals", None)
    report = Report.model_validate(payload)
    if expected_checksum is not None and expected_checksum != report.content_checksum():
        raise ValueError("checksum del report non corrispondente al contenuto")
    return report


def graph_to_dict(block: ExperimentBlock) -> dict[str, Any]:
    """Grafo in forma node-link, con le versioni necessarie a ricostruirlo."""
    return {
        "block_id": block.id,
        "schema_version": block.versions.schema_version,
        "graph_version": block.versions.graph_version,
        "nodes": [
            {
                "id": node.id,
                "type": str(node.type),
                "label": node.label,
                "count": node.count,
                "attributes": node.attributes,
                "confidence": node.confidence,
                "evidence_ids": list(node.evidence_ids),
                "provenance": node.provenance.model_dump(mode="json"),
            }
            for node in block.hierarchy.nodes
        ],
        "relations": [
            {
                "id": relation.id,
                "type": str(relation.type),
                "source": relation.source,
                "target": relation.target,
                "attributes": relation.attributes,
                "confidence": relation.confidence,
                "evidence_ids": list(relation.evidence_ids),
                "provenance": relation.provenance.model_dump(mode="json"),
            }
            for relation in block.hierarchy.relations
        ],
    }


def write_graph(block: ExperimentBlock, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(graph_to_dict(block), indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return path
