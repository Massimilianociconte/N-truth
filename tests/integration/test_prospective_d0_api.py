"""API locale del compiler prospettico D0 e download esplicito."""

from __future__ import annotations

from datetime import datetime

import pytest

from ntruth.prospective import MAX_PROSPECTIVE_D0_BODY_BYTES


def _api_payload() -> dict[str, object]:
    return {
        "draft": {
            "experimentBlockId": "EB-D0-API-001",
            "question": "Does treatment change viability?",
            "inferenceTarget": "wells under the declared culture conditions",
            "factorName": "Treatment",
            "factorKind": "treatment",
            "levelA": "vehicle",
            "levelB": "drug",
            "endpointName": "viability",
            "endpointId": "EP-V",
            "measuredOn": "Well",
            "allocationLevel": "Well",
            "applicationLevel": "Well",
            "independentlyAssigned": "TRUE",
            "independenceMechanism": "Recorded independent allocation for each well.",
            "targetBiologicalUnit": "Well",
            "estimand": {
                "effectMeasure": "difference in means",
                "targetPopulationOrUnit": "declared wells",
                "generalizationLevel": "declared culture conditions",
            },
        },
        "rows": [
            {
                "sampleId": "S1",
                "sourceId": "SRC1",
                "preparationId": "P1",
                "cultureId": "C1",
                "plateId": "PL1",
                "wellId": "A01",
                "factorLevel": "vehicle",
                "timepoint": "24 h",
                "endpointId": "EP-V",
                "lifecycleStatus": "planned",
            },
            {
                "sampleId": "S2",
                "sourceId": "SRC1",
                "preparationId": "P1",
                "cultureId": "C1",
                "plateId": "PL1",
                "wellId": "A02",
                "factorLevel": "drug",
                "timepoint": "24 h",
                "endpointId": "EP-V",
                "lifecycleStatus": "planned",
            },
        ],
    }


def test_compile_session_and_export_are_local_and_serializable() -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx2")
    from fastapi.testclient import TestClient

    from ntruth.api.app import create_app

    client = TestClient(create_app())
    response = client.post("/v1/prospective/d0/compile", json=_api_payload())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["session_persistence"] == "ephemeral_process_memory"
    assert body["determinability"] == "DETERMINATE"
    assert body["ready_for_handoff"] is True
    assert body["scientific_validation_status"] == "not_performed"
    assert body["verification"]["status"] == "complete"
    assert body["block"]["count_records"]
    assert body["block"]["exclusion_records"] == []
    assert len(body["ruleset_checksum"]) == 64
    assert body["compiler_version"] == "1.0.0"
    assert len(body["audit_trail"]) == 1
    audit = body["audit_trail"][0]
    assert datetime.fromisoformat(audit["recorded_at"]).utcoffset() is not None
    assert len(audit["input_checksum"]) == 64
    assert len(audit["output_checksum"]) == 64

    reopened = client.get(f"/v1/prospective/d0/sessions/{body['session_id']}")
    assert reopened.status_code == 200
    assert reopened.json()["compilation_id"] == body["compilation_id"]

    exported = client.get(f"/v1/prospective/d0/sessions/{body['session_id']}/export")
    assert exported.status_code == 200
    assert exported.headers["content-disposition"].startswith("attachment;")
    assert exported.json()["compilation_id"] == body["compilation_id"]
    assert exported.json()["audit_trail"] == body["audit_trail"]
    assert "session_id" not in exported.json()

    repeated = client.post("/v1/prospective/d0/compile", json=_api_payload()).json()
    assert repeated["compilation_id"] == body["compilation_id"]
    assert repeated["audit_trail"][0]["input_checksum"] == audit["input_checksum"]
    assert repeated["audit_trail"][0]["output_checksum"] == audit["output_checksum"]
    assert repeated["audit_trail"][0]["id"] != audit["id"]


def test_invalid_cross_row_payload_returns_structured_422_and_no_session() -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx2")
    from fastapi.testclient import TestClient

    from ntruth.api.app import create_app

    payload = _api_payload()
    rows = list(payload["rows"])  # type: ignore[arg-type]
    rows[1] = {**rows[1], "wellId": "A01", "factorLevel": "drug"}
    payload["rows"] = rows
    client = TestClient(create_app())

    response = client.post("/v1/prospective/d0/compile", json=payload)

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "prospective_d0_invalid"
    assert {item["code"] for item in detail["issues"]} >= {
        "duplicate_well_allocation_unit",
        "allocation_unit_assigned_to_multiple_levels",
    }
    assert "session_id" not in response.json()


def test_missing_or_evicted_prospective_session_is_404() -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx2")
    from fastapi.testclient import TestClient

    from ntruth.api.app import create_app

    client = TestClient(create_app())
    response = client.get("/v1/prospective/d0/sessions/not-present")
    export = client.get("/v1/prospective/d0/sessions/not-present/export")

    assert response.status_code == 404
    assert export.status_code == 404


def test_export_blocks_identifiers_without_echoing_sensitive_values() -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx2")
    from fastapi.testclient import TestClient

    from ntruth.api.app import create_app

    payload = _api_payload()
    rows = list(payload["rows"])  # type: ignore[arg-type]
    rows[0] = {
        **rows[0],
        "sampleId": "alice@example.com",
        "fileRef": "/Users/alice/private.csv",
    }
    payload["rows"] = rows
    client = TestClient(create_app())

    compiled = client.post("/v1/prospective/d0/compile", json=payload)
    assert compiled.status_code == 200, compiled.text
    exported = client.get(f"/v1/prospective/d0/sessions/{compiled.json()['session_id']}/export")

    assert exported.status_code == 409
    assert exported.json()["detail"]["code"] == "privacy_export_blocked"
    assert exported.json()["detail"]["finding_count"] >= 2
    assert "alice@example.com" not in exported.text
    assert "/Users/alice/private.csv" not in exported.text


@pytest.mark.parametrize(
    ("ruleset_id", "ruleset_version"),
    [("../secret", "0.2.0"), ("ntruth-core", "0.1.0")],
)
def test_noncanonical_ruleset_is_rejected_without_path_disclosure(
    ruleset_id: str, ruleset_version: str
) -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx2")
    from fastapi.testclient import TestClient

    from ntruth.api.app import create_app

    payload = _api_payload()
    payload["rulesetId"] = ruleset_id
    payload["rulesetVersion"] = ruleset_version
    response = TestClient(create_app()).post("/v1/prospective/d0/compile", json=payload)

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "prospective_ruleset_not_allowed"
    assert detail["allowed_ruleset"] == "ntruth-core@0.2.0"
    assert "/Users/" not in response.text
    assert "../secret" not in response.text


def test_oversized_prospective_body_is_rejected_before_json_parsing() -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx2")
    from fastapi.testclient import TestClient

    from ntruth.api.app import create_app

    response = TestClient(create_app()).post(
        "/v1/prospective/d0/compile",
        content=b"{" + b"x" * MAX_PROSPECTIVE_D0_BODY_BYTES + b"}",
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "prospective_payload_too_large"

    chunked = TestClient(create_app()).post(
        "/v1/prospective/d0/compile",
        content=iter([b"{", b" " * (MAX_PROSPECTIVE_D0_BODY_BYTES + 1024), b"}"]),
        headers={"content-type": "application/json"},
    )
    assert chunked.status_code == 413
    assert chunked.json()["detail"]["code"] == "prospective_payload_too_large"
