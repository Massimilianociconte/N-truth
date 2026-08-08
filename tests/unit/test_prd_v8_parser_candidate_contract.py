from __future__ import annotations

from importlib import import_module

import pytest

from ntruth.mvt_a.stage_schema import FORBIDDEN_FINAL_FIELDS


def _recursive_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str):
                keys.add(key.casefold())
            keys.update(_recursive_keys(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            keys.update(_recursive_keys(item))
    return keys


def _contract_api() -> tuple[object, object, object]:
    contract = import_module("ntruth.parser_ai.contract")
    parser_output = getattr(contract, "ParserCandidateOutput", None)
    gold_target = getattr(contract, "GoldParserTarget", None)
    legacy_output = getattr(contract, "ParserAIOutputV3", None)
    assert parser_output is not None
    assert gold_target is not None
    assert legacy_output is not None
    return parser_output, gold_target, legacy_output


def _candidate_payload() -> dict[str, object]:
    return {
        "contract_version": "8.0.0",
        "experiment_blocks": [
            {
                "block_id": "block-1",
                "title": "Block one",
                "evidence_ids": ["ev-1"],
                "confidence": 0.8,
            }
        ],
        "evidence_spans": [
            {
                "evidence_id": "ev-1",
                "file_id": "file-1",
                "evidence_type": "AUTHOR_ASSERTION",
                "text": "x",
                "confidence": 0.8,
                "start": 0,
                "end": 1,
            }
        ],
        "coverage": {
            "status": "PARTIAL",
            "covered_artifact_ids": [],
            "missing_artifact_ids": ["methods-rest"],
            "rationale": "Only the supplied excerpt was parsed.",
        },
        "missing_predicates": [
            {
                "predicate_name": "assignment_event_observed",
                "block_id": "block-1",
                "rationale": "No allocation statement in the excerpt.",
            }
        ],
        "model_metadata": {
            "adapter_name": "fixture",
            "model_name": "fixture",
            "model_version": "1",
            "prompt_template_version": "candidate-v8",
            "contract_version": "8.0.0",
            "local_execution": True,
        },
    }


def test_active_parser_and_gold_are_distinct_candidate_only_types() -> None:
    parser_output, gold_target, _legacy_output = _contract_api()
    candidate = parser_output.model_validate(_candidate_payload())
    gold = gold_target.model_validate(
        {
            "schema_version": "8.0.0",
            "candidate_target": candidate.model_dump(mode="json"),
            "adjudication_id": "adj-1",
            "reviewer_ids": ["reviewer-a", "reviewer-b"],
            "adjudication_rationale": "Two submissions were reconciled.",
            "submission_references": [
                {
                    "submission_id": "submission-a",
                    "submission_sha256": "a" * 64,
                    "reviewer_id": "reviewer-a",
                    "reviewer_role": "wet-lab",
                },
                {
                    "submission_id": "submission-b",
                    "submission_sha256": "b" * 64,
                    "reviewer_id": "reviewer-b",
                    "reviewer_role": "statistical-methods",
                },
            ],
            "comparison_status": "AGREED",
            "material_differences": [],
        }
    )

    assert type(gold) is not type(candidate)
    dumped = gold.model_dump(mode="json")
    assert _recursive_keys(dumped).isdisjoint(FORBIDDEN_FINAL_FIELDS)


def test_parser_candidate_output_rejects_nested_final_aliases() -> None:
    parser_output, _gold_target, _legacy_output = _contract_api()
    payload = _candidate_payload()
    payload["alternatives"] = [
        {
            "alternative_id": "alt-1",
            "block_id": "block-1",
            "description": "candidate",
            "evidence_ids": ["ev-1"],
            "confidence": 0.4,
            "metadata": {"design_verdict": "adequate"},
        }
    ]

    with pytest.raises(ValueError, match="final field"):
        parser_output.model_validate(payload)


def test_legacy_v3_output_can_never_be_silently_promoted_to_gold() -> None:
    contract = import_module("ntruth.parser_ai.contract")
    migrate = getattr(contract, "migrate_parser_ai_output_v3_to_gold", None)
    review_error = getattr(contract, "ParserV3MigrationReviewRequired", None)
    assert migrate is not None
    assert review_error is not None

    with pytest.raises(review_error, match="SCIENTIFIC_REVIEW_REQUIRED"):
        migrate({"contract_version": "2.0.0", "determinability": {"status": "DETERMINATE"}})


def test_stage_envelope_uses_complete_partial_failed_and_exact_error_taxonomy() -> None:
    stage = import_module("ntruth.mvt_a.stage_schema")
    status = getattr(stage, "StageCompletionStatus", None)
    error_code = getattr(stage, "StageErrorCode", None)
    assert status is not None
    assert error_code is not None
    assert {item.value for item in status} == {"COMPLETE", "PARTIAL", "FAILED"}
    assert {item.value for item in error_code} == {
        "UNSUPPORTED_FORMAT",
        "CHUNK_COVERAGE_INCOMPLETE",
        "MISSING_REQUIRED_EVIDENCE",
        "AMBIGUOUS_COREFERENCE",
        "CONFLICTING_SOURCES",
        "INVALID_COUNT_INVARIANT",
        "AMBIGUOUS_NULL_SEMANTICS",
        "NON_EXHAUSTIVE_SCENARIO_SET",
        "UNSUPPORTED_DESIGN_PROFILE",
        "VERIFIER_DISAGREEMENT",
        "AUTHORITY_CONFLICT",
        "INTERFERENCE_STATUS_UNKNOWN",
        "RULE_THEORY_MISMATCH",
        "PROFILE_COVERAGE_GAP",
        "REALITY_GATE_BLOCKED",
    }


def test_syntax_normalizer_preserves_null_and_never_maps_keywords_to_facts() -> None:
    stage = import_module("ntruth.mvt_a.stage_schema")
    normalize = getattr(stage, "normalize_candidate_syntax", None)
    assert normalize is not None
    source = {
        "free_text": "independent",
        "well_id": "A-01",
        "random_intercept_code": "(1|batch)",
        "reported_value": None,
    }

    normalized = normalize(source)

    assert set(normalized) == set(source)
    assert normalized["reported_value"] is None
    assert normalized["free_text"] == "independent"
    assert "experimental_unit" not in normalized
    assert "allocation" not in normalized
    assert "absence" not in normalized


def test_prompt_and_candidate_metrics_have_no_final_scientific_target() -> None:
    dataset = import_module("ntruth.training.mlx_dataset")
    prompt = str(dataset.SYSTEM_PROMPT)
    for forbidden in (
        "independent_n",
        "experimental_unit_count",
        "determinability",
        "design_adequacy",
        "pseudoreplication",
        "RuleResult",
    ):
        assert forbidden not in prompt

    parser_output, _gold_target, _legacy_output = _contract_api()
    metrics = import_module("ntruth.training.metrics")
    candidate = parser_output.model_validate(_candidate_payload())
    score = metrics.score_output(candidate, candidate)
    assert not any("determinability" in key for key in score)
    aggregated = metrics.aggregate_scores((score,))
    assert not any("determinability" in key for key in aggregated)
