"""Unit test scorer semantico stage-level B4."""

from __future__ import annotations

import json

from ntruth.training.semantic_stage_scorer import (
    aggregate_stage_scores,
    bootstrap_ci,
    decide_lora_gate,
    match_counts,
    match_entities,
    match_relations,
    match_spans_exact,
    match_spans_overlap,
    score_case_stage,
)


def _case_with_gold() -> dict:
    text = "Five donors provided cells treated with LPS."
    # coordinates for "Five donors"
    start = text.index("Five donors")
    end = start + len("Five donors")
    return {
        "case_id": "unit-01",
        "kind": "entity_count",
        "gold": {
            "evidence_spans": [
                {
                    "evidence_id": "e1",
                    "file_id": "file-unit-01",
                    "text": "Five donors",
                    "start": start,
                    "end": end,
                    "evidence_type": "AUTHOR_ASSERTION",
                }
            ],
            "candidate_nodes": [
                {
                    "node_id": "n1",
                    "label": "donors",
                    "node_type": {"value": "HumanDonor"},
                    "evidence_ids": ["e1"],
                }
            ],
            "counts": [
                {
                    "count_id": "c1",
                    "quantifier": "EXACT",
                    "value": 5,
                    "unit_type": {"value": "HumanDonor"},
                    "population_scope": "donors",
                    "evidence_ids": ["e1"],
                }
            ],
            "candidate_edges": [
                {
                    "edge_id": "ed1",
                    "source_id": "n1",
                    "target_id": "n1",
                    "relation_type": {"value": "nested_in"},
                    "evidence_ids": ["e1"],
                }
            ],
        },
        "source_text": text,
    }


def test_perfect_evidence_match() -> None:
    case = _case_with_gold()
    g = case["gold"]["evidence_spans"][0]
    pred = {
        "evidence_spans": [
            {
                "evidence_id": "p1",
                "file_id": g["file_id"],
                "text": g["text"],
                "start": g["start"],
                "end": g["end"],
            }
        ]
    }
    raw = json.dumps(pred)
    scored = score_case_stage(
        stage="evidence_extraction",
        case=case,
        raw_text=raw,
        schema_valid=True,
        truncated=False,
    )
    assert scored["exact_span"]["f1"] == 1.0
    assert scored["complete"] is True


def test_partial_overlap_not_exact() -> None:
    gold = [{"file_id": "f", "text": "five donors", "start": 0, "end": 11}]
    pred = [{"file_id": "f", "text": "five", "start": 0, "end": 4}]
    exact = match_spans_exact(pred, gold)
    overlap = match_spans_overlap(pred, gold, min_iou=0.1)
    assert exact["f1"] == 0.0
    assert overlap["true_positive"] >= 1


def test_wrong_count_value_not_fully_correct() -> None:
    gold = [{"quantifier": "EXACT", "value": 5, "unit_label": "HumanDonor", "scope": "donors"}]
    pred = [{"quantifier": "EXACT", "value": 5, "unit_label": "Cell", "scope": "cells"}]
    m = match_counts(pred, gold)
    assert m["value_exact_accuracy"] == 1.0
    assert m["fully_correct_rate"] == 0.0  # wrong unit


def test_entity_relaxed_vs_exact() -> None:
    gold = [{"label": "Human donors", "node_type": "HumanDonor"}]
    pred = [{"label": "donors", "node_type": "Animal"}]
    m = match_entities(pred, gold)
    assert m["exact"]["f1"] == 0.0
    assert m["relaxed"]["true_positive"] >= 1


def test_relation_direction() -> None:
    gold = [
        {
            "source_label": "cells",
            "target_label": "wells",
            "relation_type": "nested_in",
        }
    ]
    pred = [
        {
            "source_label": "wells",
            "target_label": "cells",
            "relation_type": "nested_in",
        }
    ]
    m = match_relations(pred, gold)
    assert m["direction_error_count"] >= 1
    assert m["directed_edge"]["f1"] == 0.0


def test_incomplete_gets_zero_all_case() -> None:
    case = _case_with_gold()
    scored = score_case_stage(
        stage="entity_count",
        case=case,
        raw_text="{}",
        schema_valid=False,
        truncated=True,
    )
    assert scored["primary_f1_all_case"] == 0.0
    assert scored["complete"] is False


def test_bootstrap_ci_bounds() -> None:
    ci = bootstrap_ci([0.0, 0.5, 1.0], n_boot=500, seed=1)
    assert ci["n"] == 3
    assert ci["low"] is not None and ci["high"] is not None
    assert ci["low"] <= ci["mean"] <= ci["high"]


def test_aggregate_and_decision_smoke() -> None:
    case = _case_with_gold()
    rows = [
        score_case_stage(
            stage="evidence_extraction",
            case=case,
            raw_text=json.dumps(
                {
                    "evidence_spans": [
                        {
                            "file_id": "file-unit-01",
                            "text": "Five donors",
                            "start": 0,
                            "end": 11,
                        }
                    ]
                }
            ),
            schema_valid=True,
            truncated=False,
        )
    ]
    agg = aggregate_stage_scores(rows)
    assert agg["n_all"] == 1
    report = {
        "stages": {
            "evidence_extraction": {"aggregate": agg},
            "entity_count": {
                "aggregate": aggregate_stage_scores(
                    [
                        score_case_stage(
                            stage="entity_count",
                            case=case,
                            raw_text=json.dumps({"entities": [], "counts": []}),
                            schema_valid=True,
                            truncated=False,
                        )
                    ]
                )
            },
            "candidate_relations": {
                "aggregate": aggregate_stage_scores(
                    [
                        score_case_stage(
                            stage="candidate_relations",
                            case=case,
                            raw_text=json.dumps({"relations": []}),
                            schema_valid=True,
                            truncated=False,
                        )
                    ]
                )
            },
            "candidate_graph_minimal": {
                "aggregate": aggregate_stage_scores(
                    [
                        score_case_stage(
                            stage="candidate_graph_minimal",
                            case=case,
                            raw_text=json.dumps(
                                {
                                    "entities": [],
                                    "relations": [],
                                    "evidence_spans": [],
                                    "counts": [],
                                    "factors": [],
                                    "endpoints": [],
                                    "missing_fact_predicates": [],
                                    "result_id": "x",
                                    "graph_set_id": "g",
                                    "provenance": {
                                        "stage": "candidate_graph_set",
                                        "authority": "model",
                                    },
                                }
                            ),
                            schema_valid=True,
                            truncated=False,
                        )
                    ]
                )
            },
        }
    }
    decision = decide_lora_gate(report)
    assert decision["decision"] in {
        "GO_LORA_P0",
        "REVISE_PROMPT_OR_SCHEMA",
        "EXPAND_DEV_SET",
        "STOP_OR_CHANGE_MODEL",
    }
