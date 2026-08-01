"""Golden deterministico dell'export v3.

Il file atteso e uno snapshot di regressione del software, non un gold corpus
scientifico e non una valutazione expert-reviewed. Il checksum copre l'intero
report; la proiezione rende leggibili le differenze piu importanti.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ntruth.ingest.project import Project
from ntruth.pipeline import analyze_project
from ntruth.reporting import report_to_dict

METHODS = (
    "# Materials and Methods\n\n"
    "## Cell culture\n\nPrimary neurons were prepared from three independent preparations. "
    "Each preparation was plated into four wells.\n\n"
    "## Treatment\n\nCells were treated with NGF or vehicle at the level of the culture.\n\n"
    "## Quantitative microscopy\n\nIntensity per cell was quantified. "
    "Five fields were acquired per well.\n\n"
    "## Statistical analysis\n\nGroups were compared with an unpaired t-test; "
    "n = 120 cells.\n"
)

ProjectFactory = Callable[..., Project]
GOLDEN_PATH = Path(__file__).with_name("report_v3_software_snapshot.json")


def _projection(payload: dict[str, Any]) -> dict[str, Any]:
    block = payload["blocks"][0]
    assessment = block["unit_assessments"][0]
    positive = payload["positive_outputs"][block["id"]]
    n_row = positive["n_table"][0]
    factor = block["factors"][0]

    return {
        "report_id": payload["report_id"],
        "project_id": payload["project_id"],
        "versions": payload["versions"],
        "totals": payload["totals"],
        "summary": payload["summaries"][0],
        "block": {
            "id": block["id"],
            "title": block["title"],
            "determinability": block["determinability"],
            "node_types": [node["type"] for node in block["hierarchy"]["nodes"]],
            "relation_types": [relation["type"] for relation in block["hierarchy"]["relations"]],
            "factor": {
                "name": factor["name"],
                "levels": factor["levels"],
                "allocation_level": factor["allocation_level"],
                "application_level": factor["application_level"],
            },
            "assessment": {
                key: assessment[key]
                for key in (
                    "biological_unit",
                    "experimental_unit",
                    "observational_unit",
                    "analytical_unit",
                    "n_declared",
                    "n_allocated",
                    "n_analyzed",
                    "n_observational",
                    "n_independent",
                    "inferability",
                    "risk",
                )
            },
            "alerts": [
                {
                    "rule_id": alert["rule_id"],
                    "alert_class": alert["alert_class"],
                    "severity": alert["severity"],
                }
                for alert in block["alerts"]
            ],
            "questions": [
                {
                    "id": question["id"],
                    "priority": question["priority"],
                    "decisive": question["decisive"],
                    "impact": question["impact"],
                }
                for question in block["questions"]
            ],
        },
        "positive_output": {
            "path_status": positive["path_status"],
            "methods_status": positive["methods_statement"]["status"],
            "non_certifying": positive["non_certifying"],
            "n_row": {
                key: n_row[key]
                for key in (
                    "experimental_unit",
                    "observational_unit",
                    "analytical_unit",
                    "n_declared",
                    "n_allocated",
                    "n_analyzed",
                    "n_observational",
                    "n_independent",
                    "inferability",
                )
            },
            "driver_statuses": {
                item["item_id"]: item["status"] for item in positive["driver_checklist"]
            },
            "statement_layers": [item["layer"] for item in positive["statements"]],
            "candidate_analysis_strategies": positive["candidate_analysis_strategies"],
            "decisive_question_ids": positive["decisive_question_ids"],
        },
    }


def test_report_matches_reviewed_software_snapshot(make_project: ProjectFactory) -> None:
    project = make_project(
        {"methods.md": METHODS},
        name="report-golden-v3",
        project_name="golden-v3",
    )
    actual = report_to_dict(analyze_project(project).report)
    expected = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))

    assert expected["fixture_kind"] == "deterministic_software_snapshot_not_expert_gold"
    assert _projection(actual) == expected["projection"]
    assert actual["content_checksum"] == expected["content_checksum"]
