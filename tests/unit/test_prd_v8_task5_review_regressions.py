from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

import ntruth.training.mlx_runtime as runtime
from ntruth.governance.lineage import CorpusSplit
from ntruth.mvt_a.stage_schema import (
    MvtAStageOutput,
    StageCompletionStatus,
    StageCoverage,
    StageProvenance,
)
from ntruth.mvt_a.verifier import attach_verifier
from ntruth.parser_ai.adapter import run_parser_adapter
from ntruth.parser_ai.contract import (
    GoldParserTarget,
    ParserAIDocumentInput,
    ParserAIInput,
    ParserCandidateOutput,
)
from ntruth.schemas.core import content_checksum
from ntruth.training.manifest import build_manifest_records
from ntruth.training.records import (
    AnnotationStatus,
    PreparedRecord,
    SupervisedRecord,
    SupervisionProvenance,
)


def _candidate_payload(*, coverage: str = "COMPLETE") -> dict[str, Any]:
    missing = [] if coverage == "COMPLETE" else ["file-missing"]
    return {
        "contract_version": "8.0.0",
        "experiment_blocks": [
            {
                "block_id": "block-a",
                "title": "A",
                "evidence_ids": ["ev-a"],
                "confidence": 0.9,
            },
            {
                "block_id": "block-b",
                "title": "B",
                "evidence_ids": ["ev-b"],
                "confidence": 0.9,
            },
        ],
        "block_boundaries": [
            {
                "block_id": "block-a",
                "boundary_predicates": [
                    {
                        "criterion": "DISTINCT_EXPERIMENT_SOURCE_DOCUMENT",
                        "internal_query_representability": "NOT_REPRESENTABLE",
                    }
                ],
                "rationale": "The source explicitly separates block A.",
                "evidence_ids": ["ev-a"],
                "confidence": 0.9,
            },
            {
                "block_id": "block-b",
                "boundary_predicates": [
                    {
                        "criterion": "DISTINCT_EXPERIMENT_SOURCE_DOCUMENT",
                        "internal_query_representability": "NOT_REPRESENTABLE",
                    }
                ],
                "rationale": "The source explicitly separates block B.",
                "evidence_ids": ["ev-b"],
                "confidence": 0.9,
            },
        ],
        "evidence_spans": [
            {
                "evidence_id": "ev-a",
                "file_id": "file-a",
                "evidence_type": "AUTHOR_ASSERTION",
                "text": "a",
                "confidence": 0.9,
                "start": 0,
                "end": 1,
            },
            {
                "evidence_id": "ev-b",
                "file_id": "file-b",
                "evidence_type": "AUTHOR_ASSERTION",
                "text": "b",
                "confidence": 0.9,
                "start": 0,
                "end": 1,
            },
        ],
        "candidate_nodes": [
            {
                "node_id": "node-a",
                "block_id": "block-a",
                "node_type": {"value": "CellCulture"},
                "label": "culture a",
                "evidence_ids": ["ev-a"],
                "confidence": 0.9,
            },
            {
                "node_id": "node-b",
                "block_id": "block-b",
                "node_type": {"value": "CellCulture"},
                "label": "culture b",
                "evidence_ids": ["ev-b"],
                "confidence": 0.9,
            },
        ],
        "factors": [
            {
                "factor_id": "factor-a",
                "block_id": "block-a",
                "name": "factor a",
                "levels": ["control", "treated"],
                "allocation_level": None,
                "application_level": None,
                "evidence_ids": ["ev-a"],
                "confidence": 0.9,
            },
            {
                "factor_id": "factor-b",
                "block_id": "block-b",
                "name": "factor b",
                "levels": ["control", "treated"],
                "allocation_level": None,
                "application_level": None,
                "evidence_ids": ["ev-b"],
                "confidence": 0.9,
            },
        ],
        "endpoints": [
            {
                "endpoint_id": "endpoint-a",
                "block_id": "block-a",
                "name": "endpoint a",
                "evidence_ids": ["ev-a"],
                "confidence": 0.9,
            },
            {
                "endpoint_id": "endpoint-b",
                "block_id": "block-b",
                "name": "endpoint b",
                "evidence_ids": ["ev-b"],
                "confidence": 0.9,
            },
        ],
        "coverage": {
            "status": coverage,
            "covered_artifact_ids": ["file-a", "file-b"] if coverage == "COMPLETE" else [],
            "missing_artifact_ids": missing,
            "rationale": "Two-block parser fixture.",
        },
        "model_metadata": {
            "adapter_name": "fixture",
            "model_name": "fixture-model",
            "model_version": "1",
            "prompt_template_version": "candidate-v8",
        },
    }


def _gold_payload(candidate: ParserCandidateOutput | None = None) -> dict[str, Any]:
    target = candidate or ParserCandidateOutput.model_validate(_candidate_payload())
    return {
        "schema_version": "8.0.0",
        "candidate_target": target.model_dump(mode="json"),
        "adjudication_id": "adj-1",
        "reviewer_ids": ["reviewer-a", "reviewer-b"],
        "adjudication_rationale": "Two independent submissions were reconciled.",
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


def _provenance(**updates: Any) -> SupervisionProvenance:
    payload: dict[str, Any] = {
        "source_id": "source-1",
        "source_asset_id": "asset-1",
        "source_sha256": "c" * 64,
        "governance_hash": "d" * 64,
        "study_family_id": "study-1",
        "document_lineage_id": "document-1",
        "license_or_authorization_id": "license-1",
        "guideline_version": "8.0.0",
        "reviewer_count": 2,
        "reviewer_ids": ["reviewer-a", "reviewer-b"],
        "reviewer_roles": ["wet-lab", "statistical-methods"],
        "adjudication_id": "adj-1",
    }
    payload.update(updates)
    return SupervisionProvenance.model_validate(payload)


def _record(
    *, target: GoldParserTarget | None = None, provenance: SupervisionProvenance | None = None
) -> SupervisedRecord:
    return SupervisedRecord(
        record_id="record-1",
        task="parser_candidate_v8",
        language="en",
        input_text=ParserAIInput(metadata={"record": "record-1"}).model_dump_json(),
        target=target or GoldParserTarget.model_validate(_gold_payload()),
        provenance=provenance or _provenance(),
        annotation_status=AnnotationStatus.ADJUDICATED,
        training_eligible=True,
        split=CorpusSplit.TRAIN,
    )


def test_01_self_issued_file_reality_gate_is_never_authoritative(tmp_path: Path) -> None:
    artifact = runtime.build_training_reality_gate_v8_artifact(
        snapshot_id="snapshot-current",
        snapshot_sha256="a" * 64,
        privacy_attestation_sha256="b" * 64,
        no_corpus_attestation_sha256="c" * 64,
        authorized=True,
        issued_by="caller-controlled",
    )
    path = tmp_path / "self-issued.json"
    path.write_text(json.dumps(artifact.model_dump(mode="json")), encoding="utf-8")

    with pytest.raises(runtime.MLXPipelineError, match=r"Task 7|authoritative|review"):
        runtime.verify_training_reality_gate_v8(
            runtime.FileRealityGateV8Protocol(path),
            runtime.TrainingRealityGateV8Request(
                snapshot_id="snapshot-current",
                snapshot_sha256="a" * 64,
            ),
        )


@dataclass
class _Adapter:
    response: Any
    name: str = "fixture-adapter"
    version: str = "1"

    def parse(self, _request: ParserAIInput) -> Any:
        return self.response


def test_02_public_parser_flows_losslessly_through_versioned_stage_and_verifier() -> None:
    request = ParserAIInput(
        documents=(
            ParserAIDocumentInput(file_id="file-a", filename="a.txt", sha256="a" * 64, text="a"),
            ParserAIDocumentInput(file_id="file-b", filename="b.txt", sha256="b" * 64, text="b"),
        )
    )
    candidate = ParserCandidateOutput.model_validate(_candidate_payload())

    stage = run_parser_adapter(_Adapter(candidate), request)

    assert isinstance(stage, MvtAStageOutput)
    assert stage.verifier_passed is True
    assert stage.candidates == candidate
    assert MvtAStageOutput.model_validate_json(stage.model_dump_json()) == stage
    assert stage.provenance.input_checksum == content_checksum(request.model_dump(mode="json"))


@pytest.mark.parametrize(
    "field_payload",
    (
        {
            "contrasts": [
                {
                    "contrast_id": "contrast-a",
                    "block_id": "block-a",
                    "factor_ids": ["factor-b"],
                    "compared_levels": ["control", "treated"],
                    "endpoint_ids": ["endpoint-a"],
                    "evidence_ids": ["ev-a"],
                    "confidence": 0.8,
                }
            ]
        },
        {
            "candidate_estimands": [
                {
                    "estimand_id": "estimand-a",
                    "block_id": "block-a",
                    "factor_ids": ["factor-b"],
                    "endpoint_id": "endpoint-a",
                    "effect_measure": "difference",
                    "target_population_or_unit": "culture",
                    "generalization_level": "culture",
                    "evidence_ids": ["ev-a"],
                    "confidence": 0.8,
                }
            ]
        },
        {
            "candidate_events": [
                {
                    "event_id": "event-a",
                    "block_id": "block-a",
                    "event_type": "candidate-event",
                    "participant_candidate_ids": ["factor-a"],
                    "evidence_ids": ["ev-a"],
                    "confidence": 0.8,
                }
            ]
        },
        {
            "candidate_graphs": [
                {
                    "graph_id": "graph-a",
                    "block_id": "block-a",
                    "candidate_node_ids": ["node-b"],
                    "evidence_ids": ["ev-a"],
                    "confidence": 0.8,
                }
            ]
        },
        {
            "alternatives": [
                {
                    "alternative_id": "alternative-a",
                    "block_id": "block-a",
                    "description": "cross-block alternative",
                    "candidate_node_ids": ["node-b"],
                    "evidence_ids": ["ev-a"],
                    "confidence": 0.8,
                }
            ]
        },
        {
            "clarification_questions": [
                {
                    "question_id": "question-a",
                    "block_id": "block-a",
                    "question": "Which candidate?",
                    "resolves_candidate_ids": ["node-b"],
                    "rationale": "Resolve cross-block ambiguity.",
                }
            ]
        },
    ),
)
def test_03_active_parser_rejects_wrong_type_or_cross_block_references(
    field_payload: dict[str, Any],
) -> None:
    payload = _candidate_payload()
    payload.update(field_payload)

    with pytest.raises(ValueError, match=r"block|type"):
        ParserCandidateOutput.model_validate(payload)


def test_04_complete_stage_cannot_preserve_failed_verifier_state() -> None:
    stage = MvtAStageOutput(
        stage_id="stage-1",
        status=StageCompletionStatus.COMPLETE,
        candidates=ParserCandidateOutput.model_validate(_candidate_payload()),
        coverage=StageCoverage(
            status=StageCompletionStatus.COMPLETE,
            covered_artifact_ids=("file-a",),
            rationale="Complete fixture.",
        ),
        provenance=StageProvenance(
            producer_id="fixture",
            producer_version="1",
            input_artifact_ids=("file-a",),
            input_checksum="a" * 64,
        ),
    )
    failed = stage.model_copy(update={"verifier_passed": False})

    with pytest.raises(ValueError, match="verifier"):
        MvtAStageOutput.model_validate(failed.model_dump(mode="json"))

    empty_payload = _candidate_payload()
    empty_payload.update(
        {
            "experiment_blocks": [],
            "block_boundaries": [],
            "evidence_spans": [],
            "candidate_nodes": [],
            "factors": [],
            "endpoints": [],
        }
    )
    attached = attach_verifier(
        stage.model_copy(update={"candidates": ParserCandidateOutput.model_validate(empty_payload)})
    )
    assert attached.status is StageCompletionStatus.FAILED
    assert attached.verifier_passed is False
    assert attached.candidates is not None
    assert attached.provenance == stage.provenance


def test_05_gold_requires_two_submission_pins_and_exact_record_provenance() -> None:
    missing = _gold_payload()
    missing.pop("submission_references")
    with pytest.raises(ValueError, match="submission"):
        GoldParserTarget.model_validate(missing)

    one = _gold_payload()
    one["submission_references"] = one["submission_references"][:1]
    with pytest.raises(ValueError, match=r"two|2|submission"):
        GoldParserTarget.model_validate(one)

    target = GoldParserTarget.model_validate(_gold_payload())
    with pytest.raises(ValueError, match="adjudication"):
        _record(target=target, provenance=_provenance(adjudication_id="adj-other"))
    with pytest.raises(ValueError, match="reviewer"):
        _record(target=target, provenance=_provenance(reviewer_ids=["reviewer-a", "reviewer-c"]))

    record = _record(target=target)
    prepared = PreparedRecord(
        record=record,
        normalized_input="fixture",
        canonical_target=target.model_dump_json(),
        exact_fingerprint="e" * 64,
        near_fingerprint="f" * 64,
        leakage_group_id="leakage-1",
        split=CorpusSplit.TRAIN,
    )
    manifest_record = build_manifest_records((prepared,))[0]
    assert manifest_record.target_adjudication_id == target.adjudication_id
    assert manifest_record.submission_ids == ("submission-a", "submission-b")
    assert manifest_record.submission_checksums == ("a" * 64, "b" * 64)
    assert manifest_record.comparison_status == "AGREED"
    assert manifest_record.reviewer_ids == target.reviewer_ids


@pytest.mark.parametrize(
    "kind",
    (
        "determinability_candidate",
        "pseudoreplication_candidate",
        "experimental_unit_count_candidate",
        "unknown_unreviewed_candidate",
    ),
)
def test_06_count_kind_discriminator_is_closed_at_parser_and_stage(kind: str) -> None:
    payload = _candidate_payload()
    payload["candidate_counts"] = [
        {
            "count_id": "count-a",
            "block_id": "block-a",
            "kind": kind,
            "candidate_value": 4,
            "raw_text": "four samples",
            "evidence_ids": ["ev-a"],
            "confidence": 0.8,
        }
    ]
    with pytest.raises(ValueError, match="candidate count kind"):
        ParserCandidateOutput.model_validate(payload)
