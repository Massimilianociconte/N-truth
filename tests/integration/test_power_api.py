"""Endpoint POST /v1/power/plan: candidate-only, HANDOFF_ONLY, fail-closed."""

from __future__ import annotations

import pytest


@pytest.fixture()
def client():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx2")
    from fastapi.testclient import TestClient

    from ntruth.api.app import create_app

    return TestClient(create_app(), base_url="http://127.0.0.1")


POWER_PAYLOAD = {
    "query_id": "IQ-1",
    "factor_id": "treatment",
    "contrast_id": "control_vs_treated",
    "endpoint_id": "viability",
    "endpoint_type": "CONTINUOUS",
    "family": "T_TWO_SAMPLE",
    "tail": "TWO_SIDED",
    "alpha": 0.05,
    "target_power": 0.8,
    "factor_role": "ASSIGNED_INTERVENTION",
    "contrast_type": "ASSIGNED_INTERVENTION_EFFECT",
    "assignment_event_id": "ASSIGN-1",
    "experimental_unit_type": "independent culture",
    "sesoi": {
        "source": "DECLARED_SESOI",
        "value": 0.5,
        "effect_scale": "d",
        "endpoint_id": "viability",
        "contrast_id": "control_vs_treated",
        "rationale": "SESOI dichiarata dal team su prior documentato.",
    },
    "cohen_d": 0.5,
}


def test_power_plan_returns_candidate_and_handoff_only(client) -> None:
    response = client.post("/v1/power/plan", json=POWER_PAYLOAD)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["strategy"] == "HANDOFF_ONLY"
    assert body["input_mode"] == "HUMAN_DECLARED"
    candidate = body["power_plan_candidate"]
    assert candidate["required_total_eu"] == 128
    assert candidate["required_per_group"] == [64, 64]
    assert candidate["achieved_power"] >= 0.8
    assert candidate["scientific_validation_status"] == "not_performed"
    assert len(candidate["sensitivity"]) == 3


def test_power_plan_eu_gate_denied_is_409(client) -> None:
    payload = dict(
        POWER_PAYLOAD,
        factor_role="OBSERVATIONAL_EXPOSURE",
        contrast_type="OBSERVATIONAL_ASSOCIATION",
    )
    response = client.post("/v1/power/plan", json=payload)
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "eu_gate_denied"


def test_power_plan_invalid_is_422(client) -> None:
    payload = dict(POWER_PAYLOAD, alpha=1.5)
    response = client.post("/v1/power/plan", json=payload)
    assert response.status_code == 422, response.text


SIMULATED_PAYLOAD = {
    "plan": dict(
        POWER_PAYLOAD,
        cohen_d=1.5,
        repeated_measures=True,
        sesoi=dict(
            POWER_PAYLOAD["sesoi"],
            value=1.5,
        ),
    ),
    "simulation": {
        "generative": {
            "levels": [
                {"level_name": "culture", "counts_per_parent": [1]},
                {"level_name": "well", "counts_per_parent": [2]},
                {"level_name": "cell", "counts_per_parent": [5]},
            ],
            "variance_mode": "VARIANCE_COMPONENTS",
            "sigma2_by_level": [0.1, 0.1, 0.1],
            "sigma2_residual": 0.7,
            "intercept": 0.0,
            "treatment_effect": 1.5,
            "assignment_level": "culture",
            "endpoint_type": "CONTINUOUS",
        },
        "decision_rule": "EU_MEAN_STUDENT_T",
        "n_sim": 1000,
        "mcse_target": 0.02,
        "seed_root": "api-sim-test-01",
    },
}


def test_power_plan_simulated_returns_monte_carlo_candidate(client) -> None:
    response = client.post("/v1/power/plan-simulated", json=SIMULATED_PAYLOAD)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["strategy"] == "HANDOFF_ONLY"
    candidate = body["power_plan_candidate"]
    assert candidate["method"] == "MONTE_CARLO_HIERARCHICAL"
    assert candidate["simulation_n"] == 1000
    assert candidate["simulation_seed_root"] == "api-sim-test-01"
    assert candidate["required_total_eu"] > 0
    assert candidate["scientific_validation_status"] == "not_performed"


def test_power_plan_simulated_rejects_closed_form_case(client) -> None:
    response = client.post(
        "/v1/power/plan-simulated",
        json={"plan": POWER_PAYLOAD, "simulation": SIMULATED_PAYLOAD["simulation"]},
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "simulation_not_required"


def test_pseudoreplication_risk_reports_exact_naive_alpha(client) -> None:
    response = client.post(
        "/v1/power/pseudoreplication-risk",
        json={"total_units": 6, "mean_obs_per_unit": 50, "icc": 0.05},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["strategy"] == "HANDOFF_ONLY"
    risk = body["pseudoreplication_risk"]
    assert risk["declared"]["alpha_actual"] == pytest.approx(0.2942888837, abs=1e-8)
    assert risk["method"] == "EXACT_BALANCED_RANDOM_INTERCEPT"
    assert [row["icc"] for row in risk["sensitivity"]] == [0.01, 0.05, 0.1, 0.2, 0.5]


def test_pseudoreplication_risk_without_icc_never_assumes_zero(client) -> None:
    response = client.post(
        "/v1/power/pseudoreplication-risk",
        json={"total_units": 6, "mean_obs_per_unit": 50},
    )
    assert response.status_code == 200
    risk = response.json()["pseudoreplication_risk"]
    assert risk["declared"] is None
    assert all(row["icc"] > 0 for row in risk["sensitivity"])
    assert any("mai ICC = 0" in caveat for caveat in risk["caveats"])


@pytest.mark.parametrize(
    "payload",
    [
        {"total_units": 1, "mean_obs_per_unit": 10},
        {"total_units": 3, "mean_obs_per_unit": 10, "groups": 4},
        {"total_units": 6, "mean_obs_per_unit": 10, "groups": 3, "tail": "ONE_SIDED"},
        {"total_units": 6, "mean_obs_per_unit": 10, "icc_grid": [0.1, 1.5]},
    ],
)
def test_pseudoreplication_risk_rejects_incoherent_structure(client, payload) -> None:
    response = client.post("/v1/power/pseudoreplication-risk", json=payload)
    assert response.status_code == 422
