"""Superficie v9: reality gate composto e preflight design (PRD v9 §0.8, §6.1, §11.2)."""

from __future__ import annotations

import pytest


@pytest.fixture()
def client():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx2")
    from fastapi.testclient import TestClient

    from ntruth.api.app import create_app

    return TestClient(create_app(), base_url="http://127.0.0.1")


def test_reality_gate_v9_is_hold_and_content_addressed(client) -> None:
    response = client.get("/v9/reality-gate")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["effective_state"] == "HOLD"
    assert body["authorizes_substantive_training"] is False
    assert len(body["v9_evidence_ledger"]["predicate_assessments"]) == 23
    assert len(body["v8_assessment"]["dimensions"]) == 6
    assert body["composition_id"].startswith("REALITY-GATE-V9-COMPOSITION-")
    assert len(body["content_checksum"]) == 64


ALIASED_PAYLOAD = {
    "assignments": {
        "u1": {"treatment": "control", "batch": "b1"},
        "u2": {"treatment": "control", "batch": "b1"},
        "u3": {"treatment": "drug", "batch": "b2"},
        "u4": {"treatment": "drug", "batch": "b2"},
    },
    "declared_levels": {"treatment": ["control", "drug"], "batch": ["b1", "b2"]},
    "blocks": {"u1": "w1", "u2": "w2", "u3": "w3", "u4": "w4"},
    "factor_id": "treatment",
    "query_id": "IQ-1",
    "unit_type": "culture",
    "factor_role": "ASSIGNED_INTERVENTION",
    "contrast_type": "ASSIGNED_INTERVENTION_EFFECT",
    "assignment_event_id": "ASSIGN-1",
    "information_sufficient": True,
}


def test_design_preflight_detects_aliasing_and_gates_eu(client) -> None:
    response = client.post("/v9/design/preflight", json=ALIASED_PAYLOAD)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["design_matrix"]["fully_aliased"] is True
    assert body["design_matrix"]["aliased_factor_pairs"] == [["batch", "treatment"]]
    assert body["decision"]["contrast_status"] == "STRUCTURALLY_ALIASED"
    assert body["decision"]["eu_emitted"] is True
    assert body["decision"]["eu_claim"]["assignment_event_id"] == "ASSIGN-1"
    assert body["strategy"] == "HANDOFF_ONLY"


def test_design_preflight_partial_support_on_clean_randomized_design(client) -> None:
    payload = {
        **ALIASED_PAYLOAD,
        "assignments": {
            "u1": {"treatment": "control", "batch": "b1"},
            "u2": {"treatment": "drug", "batch": "b1"},
            "u3": {"treatment": "control", "batch": "b2"},
            "u4": {"treatment": "drug", "batch": "b2"},
        },
        # Blocchi con livelli misti: la variazione intra-blocco e rilevabile.
        "blocks": {"u1": "w1", "u2": "w1", "u3": "w2", "u4": "w2"},
        # Esposizione separabile dichiarata dal chiamante: senza questo fatto
        # il contratto emette PARTIALLY_SUPPORTED, mai un supporto pieno.
        "exposure_separable": True,
    }
    response = client.post("/v9/design/preflight", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["design_matrix"]["fully_aliased"] is False
    assert body["design_matrix"]["within_block_variation"]["treatment"] is True
    assert body["gate_inputs"]["within_block_variation"] is True
    assert body["decision"]["contrast_status"] == "SUPPORTED_WITHIN_RECORDED_DESIGN"


def test_design_preflight_rejects_unknown_role_token(client) -> None:
    response = client.post(
        "/v9/design/preflight", json={**ALIASED_PAYLOAD, "factor_role": "NOT_A_ROLE"}
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "unknown_factor_role"


def test_design_preflight_rejects_undeclared_assigned_level(client) -> None:
    payload = {
        **ALIASED_PAYLOAD,
        "assignments": {"u1": {"treatment": "high"}, "u2": {"treatment": "control"}},
    }
    response = client.post("/v9/design/preflight", json=payload)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_design"
    assert "undeclared level" in response.json()["detail"]["message"]


def test_design_preflight_denies_eu_minted_from_exposure_only(client) -> None:
    payload = {
        **ALIASED_PAYLOAD,
        "assignment_event_id": None,
        "exposure_cluster": "cage-7",
    }
    response = client.post("/v9/design/preflight", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["decision"]["eu_emitted"] is False
    assert body["decision"]["denial_reason"] is not None
    assert "assignment_event_id" in body["decision"]["denial_reason"]
