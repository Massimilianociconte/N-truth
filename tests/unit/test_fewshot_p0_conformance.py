"""Test harness few-shot P0: fixture validity e normalizzazione strutturale sicura."""

from __future__ import annotations

from ntruth.parser_ai import ParserAIInput
from ntruth.parser_ai.stages import CandidateGraphSet, validate_candidate_graph_pair
from ntruth.training.candidate_conformance import (
    assess_prediction,
    safe_structural_normalize,
)
from ntruth.training.fewshot_p0_fixtures import build_all_cases


def test_all_fixtures_validate() -> None:
    cases = build_all_cases()
    assert len(cases) >= 40
    demos = [c for c in cases if c["split"] == "demo"]
    evals = [c for c in cases if c["split"] == "eval"]
    assert len(demos) >= 5
    assert len(evals) >= 20
    for case in cases:
        parser_input = ParserAIInput.model_validate(case["parser_input"])
        gold = CandidateGraphSet.model_validate(case["gold"])
        validate_candidate_graph_pair(parser_input, gold)
        assert "determinability" not in case["gold"]
        assert "verdict" not in case["gold"]


def test_safe_normalize_fills_missing_lists_only() -> None:
    payload = {
        "schema_version": "1.0.0",
        "result_id": "r",
        "stage": "candidate_graph_set",
        "status": "complete",
        "provenance": {
            "stage_run_id": "s",
            "stage": "candidate_graph_set",
            "authority": "model",
            "producer": "t",
            "producer_version": "1",
        },
        "graph_set_id": "g",
        # missing_facts intentionally omitted → may become []
    }
    normalized, notes = safe_structural_normalize(payload)
    assert normalized["missing_facts"] == []
    assert any(n.startswith("filled_missing_list:missing_facts") for n in notes)
    # wrong type must not be "fixed" into invented facts
    bad = {**payload, "missing_facts": "no evidence"}
    fixed, notes2 = safe_structural_normalize(bad)
    assert fixed["missing_facts"] == "no evidence"
    assert not any("missing_facts" in n and "filled" in n for n in notes2)


def test_assess_rejects_forbidden_keys() -> None:
    text = (
        '{"schema_version":"1.0.0","result_id":"r","stage":"candidate_graph_set",'
        '"status":"complete","provenance":{"stage_run_id":"s","stage":"candidate_graph_set",'
        '"authority":"model","producer":"t","producer_version":"1"},'
        '"graph_set_id":"g","determinability":"DETERMINABLE","verdict":"PASS"}'
    )
    result = assess_prediction(text, apply_safe_normalize=True)
    assert result["json_extractable"] is True
    assert result["candidate_only_ok"] is False
    assert "determinability" in result["forbidden_keys"] or "verdict" in result["forbidden_keys"]
