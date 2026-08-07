"""Golden deterministico della forma v8 (FASE 5 del piano di migrazione).

Lo snapshot v3 resta intatto come fixture di migrazione (PRD AE.1); questo
snapshot separato fotografa la FORMA v8 degli stessi count: wire contract
``V8CountRecord`` con KnowledgeState esplicito e naming canonico §7.9.
Gli stable_id sono identici al v3: cambia solo la forma espositiva.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from test_report_golden_v3 import METHODS

from ntruth.pipeline import analyze_project
from ntruth.schemas.experiment import COUNT_KIND_V8_WIRE, CountRecord
from ntruth.schemas.kernel import KnowledgeState, V8CountRecord

V8_GOLDEN_PATH = Path(__file__).with_name("report_v8_software_snapshot.json")

#: Lineage v7-era congelato: deve coincidere con lo snapshot v3 (AE.1).
FROZEN_V7_CONTENT_CHECKSUM = "1959afb5391e169af44e458676d43db2bdb53f19221405a726bae013de15aabe"
FROZEN_V7_REPORT_ID = "rep-d3f5de02ebfa"
FROZEN_V7_DECISIVE_QUESTION_IDS = (
    "qst-0d3705fef718",
    "qst-138783efd348",
    "qst-845edcdd8b10",
    "qst-9980f88520bf",
    "qst-7c84ad5fac45",
    "qst-cebebdc1f595",
    "qst-7459fe6625b5",
)


def project_count_to_v8(record: CountRecord) -> dict[str, Any]:
    """Proiezione deterministica v6->v8 di un count (contratti FASE 1).

    Fail-closed: un count senza valore numerico diventa NOT_REPORTED, mai un
    bare null (§15.10, Appendice AC). Il naming §7.9 esce dal serializer di
    ``V8CountRecord``; il valore v6 congelato non appare mai nel wire v8.
    """
    scope = record.scope
    state = KnowledgeState.PRESENT if record.value is not None else KnowledgeState.NOT_REPORTED
    v8 = V8CountRecord(
        count_id=record.count_id,
        kind=record.kind,
        knowledge_state=state,
        value=record.value,
        quantifier=record.quantifier,
        unit_type=scope.unit_type.value if scope.unit_type is not None else None,
        query_id=record.query_id,
        group_id=scope.group_or_level,
        cohort_id=record.cohort_id or scope.cohort_id,
        factor_id=scope.factor_id,
        contrast_id=scope.contrast_id,
        endpoint_id=scope.endpoint_id,
        timepoint=scope.timepoint,
        population_scope=scope.population,
        condition=scope.condition,
        source_evidence=record.evidence_ids,
        rule_trace=record.rule_trace_ids,
        diagnostic_only=record.diagnostic_only,
    )
    return v8.model_dump(mode="json", exclude_none=True)


def build_v8_snapshot(make_project_callable: Any) -> dict[str, Any]:
    """Costruisce lo snapshot v8 a partire dallo stesso input del golden v3."""
    project = make_project_callable(
        {"methods.md": METHODS},
        name="report-golden-v3",
        project_name="golden-v3",
    )
    report = analyze_project(project).report
    block = report.blocks[0]
    positive = report.positive_outputs[block.id]
    return {
        "fixture_kind": "deterministic_software_snapshot_v8_form",
        "lineage": {
            "v3_snapshot": "report_v3_software_snapshot.json",
            "v7_report_id": report.report_id,
            "v7_content_checksum": report.content_checksum(),
            "v7_decisive_question_ids": list(positive.decisive_question_ids),
        },
        "projection": {
            "block_id": block.id,
            "determinability": block.determinability.value,
            "published_counts": [project_count_to_v8(item) for item in positive.count_records],
            "diagnostic_counts": [
                project_count_to_v8(item) for item in positive.diagnostic_count_records
            ],
        },
    }


def test_v8_snapshot_matches_reviewed_software_snapshot(make_project) -> None:
    actual = build_v8_snapshot(make_project)
    expected = json.loads(V8_GOLDEN_PATH.read_text(encoding="utf-8"))
    assert actual == expected


def test_v8_snapshot_lineage_keeps_v7_stable_ids_frozen(make_project) -> None:
    """AE.1: la forma v8 riusa gli stable_id v7-era senza alterarli."""
    actual = build_v8_snapshot(make_project)
    lineage = actual["lineage"]
    assert lineage["v7_report_id"] == FROZEN_V7_REPORT_ID
    assert lineage["v7_content_checksum"] == FROZEN_V7_CONTENT_CHECKSUM
    assert tuple(lineage["v7_decisive_question_ids"]) == FROZEN_V7_DECISIVE_QUESTION_IDS
    kinds = {item["kind"] for item in actual["projection"]["published_counts"]} | {
        item["kind"] for item in actual["projection"]["diagnostic_counts"]
    }
    # Il wire v8 espone solo la denominazione canonica §7.9, mai i valori v6.
    assert kinds <= set(COUNT_KIND_V8_WIRE.values())
    frozen_v6_only = {"planned_n", "independent_n", "effective_n", "analysed_n"}
    assert not (kinds & frozen_v6_only)
