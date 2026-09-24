"""HTTP contract regressions for the guided PRD v8 Quick Design builder."""

from __future__ import annotations

from datetime import UTC, datetime

import test_prd_v8_quick_design_guided_builder as guided_fixture
from fastapi.testclient import TestClient

from ntruth.api.app import create_app


def test_guided_confirm_atomically_returns_the_canonical_result() -> None:
    """Catches a UI/backend adapter requiring mutable post-confirm resubmission."""

    client = TestClient(create_app(), base_url="http://127.0.0.1")
    draft = guided_fixture._draft().model_dump(mode="json")

    preview_response = client.post(
        "/v8/quick-design/build-submission",
        json={"action": "PREVIEW", "draft": draft},
    )
    assert preview_response.status_code == 200, preview_response.text
    preview = preview_response.json()
    assert preview["state"] == "REVIEW_REQUIRED"
    assert preview["submission_audit_snapshot"]["knowledge_state"] == "UNKNOWN"
    assert preview["canonical_result"]["knowledge_state"] == "UNKNOWN"
    assert len(preview["visible_questions"]) == 3
    assert len(preview["question_queue"]) > 3

    confirm_response = client.post(
        "/v8/quick-design/build-submission",
        json={
            "action": "CONFIRM",
            "draft": draft,
            "confirmation": {
                "preview_checksum": preview["preview_checksum"],
                "review_focus_predicate_id": preview["visible_questions"][0]["predicate_id"],
                "actor_role": "researcher",
                "confirmed_at": datetime(2026, 8, 9, 10, 15, tzinfo=UTC).isoformat(),
            },
        },
    )
    assert confirm_response.status_code == 200, confirm_response.text
    confirmed = confirm_response.json()
    assert confirmed["state"] == "BUILT"
    assert confirmed["submission_is_execution_capability"] is False
    assert "next_endpoint" not in confirmed
    canonical = confirmed["canonical_result"]["value"]
    assert canonical["planned_design"]["count_records"]
    assert canonical["report_bundle"]["strategy_module_status"] == "HANDOFF_ONLY"
    assert canonical["artifacts"] == confirmed["artifact_previews"]
    assert canonical["report_bundle"]["query_sections"]


def test_guided_build_endpoint_recomputes_preview_and_preserves_typed_blockers() -> None:
    client = TestClient(create_app(), base_url="http://127.0.0.1")
    draft_model = guided_fixture._draft()
    draft = draft_model.model_dump(mode="json")
    preview = client.post(
        "/v8/quick-design/build-submission",
        json={"action": "PREVIEW", "draft": draft},
    ).json()

    stale = client.post(
        "/v8/quick-design/build-submission",
        json={
            "action": "CONFIRM",
            "draft": draft,
            "confirmation": {
                "preview_checksum": "0" * 64,
                "review_focus_predicate_id": preview["visible_questions"][0]["predicate_id"],
                "actor_role": "researcher",
                "confirmed_at": datetime(2026, 8, 9, 10, 15, tzinfo=UTC).isoformat(),
            },
        },
    )
    assert stale.status_code == 422

    unresolved_scope = {
        **draft,
        "planned_unit_type": {
            "status": "NOT_AVAILABLE",
            "rationale": "The planned unit type remains unavailable.",
        },
    }
    unresolved_preview = client.post(
        "/v8/quick-design/build-submission",
        json={"action": "PREVIEW", "draft": unresolved_scope},
    ).json()
    blocked = client.post(
        "/v8/quick-design/build-submission",
        json={
            "action": "CONFIRM",
            "draft": unresolved_scope,
            "confirmation": {
                "preview_checksum": unresolved_preview["preview_checksum"],
                "review_focus_predicate_id": unresolved_preview["visible_questions"][0][
                    "predicate_id"
                ],
                "actor_role": "researcher",
                "confirmed_at": datetime(2026, 8, 9, 10, 15, tzinfo=UTC).isoformat(),
            },
        },
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "SCIENTIFIC_REVIEW_REQUIRED"

    unresolved_cohort = {
        **draft,
        "planned_groups": [
            {
                **group,
                "cohort_id": {
                    "status": "NOT_AVAILABLE",
                    "rationale": "The lifecycle cohort has not been declared.",
                },
            }
            if index == 0
            else group
            for index, group in enumerate(draft["planned_groups"])
        ],
    }
    cohort_preview = client.post(
        "/v8/quick-design/build-submission",
        json={"action": "PREVIEW", "draft": unresolved_cohort},
    ).json()
    cohort_blocked = client.post(
        "/v8/quick-design/build-submission",
        json={
            "action": "CONFIRM",
            "draft": unresolved_cohort,
            "confirmation": {
                "preview_checksum": cohort_preview["preview_checksum"],
                "review_focus_predicate_id": cohort_preview["visible_questions"][0]["predicate_id"],
                "actor_role": "researcher",
                "confirmed_at": datetime(2026, 8, 9, 10, 15, tzinfo=UTC).isoformat(),
            },
        },
    )
    assert cohort_blocked.status_code == 409
    assert cohort_blocked.json()["detail"]["issue_id"] == "SRR-V8-011"
