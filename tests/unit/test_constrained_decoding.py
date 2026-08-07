"""Test constrained decoding adapter e schemi stage (senza caricare pesi)."""

from __future__ import annotations

import json

from ntruth.model_backends.constrained import (
    ConstrainedStatus,
    compile_schema_probe,
    probe_outlines_mlx,
)
from ntruth.model_backends.stage_schemas import (
    STAGE_SCHEMA_REGISTRY,
    EvidenceExtractionStage,
    stage_schema,
)
from ntruth.training.candidate_conformance import extract_json_object


def test_probe_reports_status() -> None:
    cap = probe_outlines_mlx()
    assert cap.status in {
        ConstrainedStatus.CONSTRAINED_SUPPORTED,
        ConstrainedStatus.CONSTRAINED_UNAVAILABLE,
    }
    assert cap.backend


def test_stage_schemas_compile_and_forbid_extra() -> None:
    for cls in STAGE_SCHEMA_REGISTRY.values():
        probe = compile_schema_probe(cls)
        assert probe["schema_bytes"] > 50
        assert probe["status"] == ConstrainedStatus.CONSTRAINED_SUPPORTED.value
        schema = cls.model_json_schema()
        # Pydantic v2 extra=forbid → additionalProperties false on root
        assert schema.get("additionalProperties") is False or "additionalProperties" in json.dumps(
            schema
        )


def test_evidence_stage_empty_arrays_valid() -> None:
    payload = {
        "schema_version": "1.0.0",
        "stage": "evidence_extraction",
        "result_id": "r1",
        "status": "complete",
        "provenance": {
            "stage_run_id": "s1",
            "stage": "evidence_extraction",
            "authority": "model",
            "producer": "t",
            "producer_version": "1",
        },
        "evidence_spans": [],
    }
    model = EvidenceExtractionStage.model_validate(payload)
    assert model.evidence_spans == []


def test_evidence_stage_rejects_verdict_field() -> None:
    payload = {
        "schema_version": "1.0.0",
        "stage": "evidence_extraction",
        "result_id": "r1",
        "status": "complete",
        "provenance": {
            "stage_run_id": "s1",
            "stage": "evidence_extraction",
            "authority": "model",
            "producer": "t",
            "producer_version": "1",
        },
        "evidence_spans": [],
        "verdict": "PASS",
    }
    try:
        EvidenceExtractionStage.model_validate(payload)
        raised = False
    except Exception:
        raised = True
    assert raised


def test_stage_registry_lookup() -> None:
    assert stage_schema("entity_count").__name__ == "EntityCountStage"


def test_extract_json_still_works() -> None:
    obj, err = extract_json_object('{"a": 1}')
    assert err is None
    assert obj == {"a": 1}
