from __future__ import annotations

import inspect

import pytest

from ntruth.governance.lineage import CorpusSplit
from ntruth.mvt_a.stage_schema import assert_no_final_scientific_fields
from ntruth.parser_ai.contract import GoldParserTarget, ParserCandidateOutput
from ntruth.training.mlx_runtime import run_training
from ntruth.training.records import (
    AnnotationStatus,
    SupervisedRecord,
    SupervisionProvenance,
)


@pytest.mark.parametrize(
    "forbidden",
    (
        "n",
        "independent_n",
        "experimental_unit",
        "experimental_unit_count",
        "final_count",
        "determinability",
        "determinability_state",
        "adequacy",
        "design_adequacy",
        "design_verdict",
        "pseudoreplication",
        "pseudoreplication_verdict",
        "rule_result",
        "RuleResult",
    ),
)
def test_candidate_boundary_rejects_final_fields_recursively(forbidden: str) -> None:
    payload = {"candidate": {"nested": [{forbidden: "forbidden-final"}]}}

    with pytest.raises(ValueError, match="final field"):
        assert_no_final_scientific_fields(payload)


def test_supervised_record_rejects_training_eligible_test_split() -> None:
    provenance = SupervisionProvenance(
        source_id="source-1",
        source_asset_id="asset-1",
        source_sha256="a" * 64,
        governance_hash="b" * 64,
        license_or_authorization_id="license-1",
        guideline_version="8.0.0",
        reviewer_count=2,
        reviewer_ids=("reviewer-a", "reviewer-b"),
        reviewer_roles=("wet-lab", "statistical-methods"),
        adjudication_id="adjudication-1",
    )

    with pytest.raises(ValueError, match=r"TEST.*training"):
        SupervisedRecord(
            record_id="record-test",
            task="parser_candidate_v8",
            language="en",
            input_text="protected sentinel that training must not read",
            target=GoldParserTarget(
                candidate_target=ParserCandidateOutput.model_validate(
                    {
                        "coverage": {
                            "status": "PARTIAL",
                            "missing_artifact_ids": ["source"],
                            "rationale": "Fixture.",
                        },
                        "model_metadata": {
                            "adapter_name": "fixture",
                            "model_name": "fixture",
                            "model_version": "1",
                            "prompt_template_version": "candidate-v8",
                        },
                    }
                ),
                adjudication_id="adjudication-1",
                reviewer_ids=("reviewer-a", "reviewer-b"),
                adjudication_rationale="Fixture adjudication.",
                submission_references=(
                    {
                        "submission_id": "submission-a",
                        "submission_sha256": "c" * 64,
                        "reviewer_id": "reviewer-a",
                        "reviewer_role": "wet-lab",
                    },
                    {
                        "submission_id": "submission-b",
                        "submission_sha256": "d" * 64,
                        "reviewer_id": "reviewer-b",
                        "reviewer_role": "statistical-methods",
                    },
                ),
                comparison_status="AGREED",
                material_differences=(),
            ),
            provenance=provenance,
            annotation_status=AnnotationStatus.ADJUDICATED,
            training_eligible=True,
            split=CorpusSplit.TEST,
        )


def test_run_training_requires_reality_gate_v8_boundary_without_default() -> None:
    parameter = inspect.signature(run_training).parameters.get("reality_gate")

    assert parameter is not None
    assert parameter.default is inspect.Parameter.empty
