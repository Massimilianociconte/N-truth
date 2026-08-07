"""Guardia fail-loud sull'immutabilita dello snapshot golden v3 (PRD AE.1).

Lo snapshot v3 e un artefatto storico congelato: gli stable_id e il
content_checksum dei payload v7-era non devono mai cambiare durante la
migrazione v8. Qualsiasi modifica del fixture o deriva di hashing rompe
questo test prima ancora del confronto di contenuto.
"""

from __future__ import annotations

import json
from pathlib import Path

from test_report_golden_v3 import GOLDEN_PATH, METHODS, _projection

from ntruth.pipeline import analyze_project
from ntruth.reporting import report_to_dict

FROZEN_CONTENT_CHECKSUM = "1959afb5391e169af44e458676d43db2bdb53f19221405a726bae013de15aabe"
FROZEN_REPORT_ID = "rep-d3f5de02ebfa"
FROZEN_DECISIVE_QUESTION_IDS = (
    "qst-0d3705fef718",
    "qst-138783efd348",
    "qst-845edcdd8b10",
    "qst-9980f88520bf",
    "qst-7c84ad5fac45",
    "qst-cebebdc1f595",
    "qst-7459fe6625b5",
)


def test_v3_snapshot_file_is_frozen() -> None:
    """Il fixture storico non si tocca: checksum e stable_id sono costanti."""
    assert isinstance(GOLDEN_PATH, Path) and GOLDEN_PATH.is_file()
    snapshot = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    assert snapshot["fixture_kind"] == "deterministic_software_snapshot_not_expert_gold"
    assert snapshot["content_checksum"] == FROZEN_CONTENT_CHECKSUM
    assert snapshot["projection"]["report_id"] == FROZEN_REPORT_ID
    assert (
        tuple(snapshot["projection"]["positive_output"]["decisive_question_ids"])
        == FROZEN_DECISIVE_QUESTION_IDS
    )


def test_v3_stable_ids_remain_frozen_across_migration(make_project) -> None:
    """AE.1: la pipeline v8 rigenera gli stessi stable_id/checksum v7-era."""
    project = make_project(
        {"methods.md": METHODS},
        name="report-golden-v3",
        project_name="golden-v3",
    )
    actual = report_to_dict(analyze_project(project).report)
    assert actual["report_id"] == FROZEN_REPORT_ID
    assert actual["content_checksum"] == FROZEN_CONTENT_CHECKSUM
    block_id = actual["blocks"][0]["id"]
    decisive = tuple(actual["positive_outputs"][block_id]["decisive_question_ids"])
    assert decisive == FROZEN_DECISIVE_QUESTION_IDS
    # La proiezione storica resta identica, chiavi v8 comprese le assenze.
    expected = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    assert _projection(actual) == expected["projection"]
