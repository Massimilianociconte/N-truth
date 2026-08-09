"""RED regressions for the guided Quick Design scientific review findings."""

from __future__ import annotations

import pickle
from datetime import UTC, datetime
from typing import Literal

import pytest
import test_prd_v8_quick_design_guided_builder as guided_fixture
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ntruth.api.app import create_app
from ntruth.mvt_a.stage_schema import FORBIDDEN_FINAL_FIELDS
from ntruth.quick_design import QuickDesignScientificReviewRequired
from ntruth.schemas.core import content_checksum
from ntruth.schemas.knowledge import KnowledgeState


class VerdictTuple(tuple):
    @property
    def design_adequacy(self) -> str:
        return "ADEQUATE"


class VerdictStr(str):
    @property
    def experimental_unit(self) -> str:
        return "well"


def _guided() -> object:
    return guided_fixture._guided()


def _draft_with_cohorts(
    status: Literal["PROVIDED", "NOT_AVAILABLE"] = "PROVIDED",
) -> object:
    module = _guided()
    base = guided_fixture._draft()
    groups: list[dict[str, object]] = []
    for group in base.planned_groups:
        payload = group.model_dump(mode="python")
        payload["cohort_id"] = (
            {"status": "PROVIDED", "value": f"cohort-{group.group_id}"}
            if status == "PROVIDED"
            else {
                "status": "NOT_AVAILABLE",
                "rationale": "The lifecycle cohort has not been declared.",
            }
        )
        groups.append(payload)
    return module.GuidedQuickDesignDraft.model_validate(
        {
            **base.model_dump(mode="python"),
            "planned_groups": groups,
        }
    )


def test_planned_count_uses_only_the_explicit_user_cohort() -> None:
    """Catches silently treating a treatment group as its lifecycle cohort."""

    draft = _draft_with_cohorts()
    preview = guided_fixture._preview(draft)
    confirmed = guided_fixture._confirm(preview, draft)
    submission = confirmed.submission_audit_snapshot.value
    assert submission is not None

    scopes = {
        count.scope.group_id.value: count.scope.cohort_id.value
        for count in submission.planned_unit_counts
    }
    assert scopes == {
        "vehicle": "cohort-vehicle",
        "drug": "cohort-drug",
    }
    assert all(group_id != cohort_id for group_id, cohort_id in scopes.items())


def test_missing_planned_cohort_previews_but_confirm_fails_with_srr_v8_011() -> None:
    """Catches a missing cohort being completed by a server-side proxy."""

    draft = _draft_with_cohorts("NOT_AVAILABLE")
    preview = guided_fixture._preview(draft)
    assert preview.state == "REVIEW_REQUIRED"

    with pytest.raises(QuickDesignScientificReviewRequired) as caught:
        guided_fixture._confirm(preview, draft)
    assert caught.value.review_requirement.issue_id == "SRR-V8-011"


def test_guided_confirm_executes_canonical_lane_without_a_resubmission_endpoint() -> None:
    """Catches returning a mutable submission as the guided execution capability."""

    preview = guided_fixture._preview()
    confirmed = guided_fixture._confirm(preview)

    assert confirmed.canonical_result.knowledge_state is KnowledgeState.PRESENT
    assert confirmed.canonical_result.value is not None
    assert confirmed.canonical_result.value.planned_design.count_records
    assert confirmed.submission_is_execution_capability is False
    assert not hasattr(confirmed, "next_endpoint")


def test_confirmation_event_identity_includes_actor_time_and_body() -> None:
    """Catches two materially different confirmations sharing one append-only event ID."""

    preview = guided_fixture._preview()
    first = guided_fixture._confirm(
        preview,
        actor_role="researcher",
        confirmed_at=datetime(2026, 8, 9, 8, 30, tzinfo=UTC),
    )
    second = guided_fixture._confirm(
        preview,
        actor_role="second_reviewer",
        confirmed_at=datetime(2026, 8, 10, 8, 30, tzinfo=UTC),
    )
    first_submission = first.submission_audit_snapshot.value
    second_submission = second.submission_audit_snapshot.value
    assert first_submission is not None and second_submission is not None

    first_ids = tuple(event.event_id for event in first_submission.input_ledger.confirmation_events)
    second_ids = tuple(
        event.event_id for event in second_submission.input_ledger.confirmation_events
    )
    assert first_ids != second_ids
    assert set(first_ids).isdisjoint(second_ids)
    assert first.confirmed_snapshot_checksum.value != second.confirmed_snapshot_checksum.value
    for event in first_submission.input_ledger.confirmation_events:
        body = {
            "support": event.support.model_dump(mode="json"),
            "evidence_refs": event.evidence_refs,
            "scope_id": event.scope_id,
            "confirmed_value": event.confirmed_value.model_dump(mode="json"),
            "actor_role": event.actor_role,
            "review_independent": event.review_independent,
            "sensitivity_record_ids": event.sensitivity_record_ids,
            "created_at": event.created_at.isoformat(),
        }
        assert event.event_id == f"CONF-QD-{content_checksum(body)[:20]}"


def test_confirmed_snapshot_rejects_post_execution_artifact_mutation() -> None:
    """Catches changing the atomic canonical result while retaining its freeze checksum."""

    module = _guided()
    confirmed = guided_fixture._confirm(guided_fixture._preview())
    result = confirmed.canonical_result.value
    assert result is not None
    forged_result = result.model_copy(update={"artifacts": tuple(reversed(result.artifacts))})
    forged_response = confirmed.model_copy(
        update={
            "canonical_result": confirmed.canonical_result.model_copy(
                update={"value": forged_result}
            )
        }
    )

    with pytest.raises(ValidationError, match="snapshot checksum"):
        module.GuidedQuickDesignBuildResponse.model_validate(
            forged_response.model_dump(mode="python")
        )


@pytest.mark.parametrize("field_name", sorted(FORBIDDEN_FINAL_FIELDS))
@pytest.mark.parametrize("location", ("root", "nested"))
@pytest.mark.parametrize("construction", ("model_copy", "model_construct"))
def test_python_builder_rejects_pickle_visible_raw_final_fields(
    field_name: str,
    location: Literal["root", "nested"],
    construction: Literal["model_copy", "model_construct"],
) -> None:
    """Catches Python callers smuggling final verdicts past HTTP validation."""

    module = _guided()
    draft = guided_fixture._draft()
    if location == "nested":
        target = draft.assignment_unit_type
        if construction == "model_copy":
            forged_target = target.model_copy(update={field_name: "FORGED"})
        else:
            forged_target = type(target).model_construct(**target.__dict__)
            forged_target.__dict__[field_name] = "FORGED"
        forged_draft = draft.model_copy(update={"assignment_unit_type": forged_target})
    elif construction == "model_copy":
        forged_draft = draft.model_copy(update={field_name: "FORGED"})
    else:
        forged_draft = type(draft).model_construct(**draft.__dict__)
        forged_draft.__dict__[field_name] = "FORGED"

    request = module.GuidedQuickDesignBuildRequest(
        action="PREVIEW",
        draft=draft,
    ).model_copy(update={"draft": forged_draft})
    restored = pickle.loads(pickle.dumps(request))

    with pytest.raises(ValueError, match=r"final|raw|canonical|runtime"):
        module.build_guided_quick_design(restored)


def test_python_builder_rejects_public_container_and_scalar_subclasses() -> None:
    """Catches public verdict properties hidden on declared container/scalar values."""

    module = _guided()
    draft = guided_fixture._draft()

    for forged_draft in (
        draft.model_copy(update={"planned_groups": VerdictTuple(draft.planned_groups)}),
        draft.model_copy(update={"factor_id": VerdictStr(draft.factor_id)}),
    ):
        request = module.GuidedQuickDesignBuildRequest(
            action="PREVIEW",
            draft=draft,
        ).model_copy(update={"draft": forged_draft})
        with pytest.raises(ValueError, match=r"canonical|runtime|container|scalar"):
            module.build_guided_quick_design(pickle.loads(pickle.dumps(request)))


def test_python_builder_allows_private_non_output_cache() -> None:
    module = _guided()
    request = module.GuidedQuickDesignBuildRequest(
        action="PREVIEW",
        draft=guided_fixture._draft(),
    )
    request.__dict__["_cache"] = {"design_adequacy": "ADEQUATE"}

    assert module.build_guided_quick_design(request).state == "REVIEW_REQUIRED"


def test_question_priority_and_evidence_request_remain_typed_review_gaps() -> None:
    """Catches alphabetical rationale text being presented as reviewed Theory priority."""

    preview = guided_fixture._preview()
    assert preview.visible_questions == preview.question_queue[:3]
    assert len(preview.question_queue) > 3
    for question in preview.question_queue:
        assert question.priority_state == "UNREVIEWED"
        assert question.priority_review.status == "SCIENTIFIC_REVIEW_REQUIRED"
        assert question.priority_review.issue_id == "SRR-V8-025"
        assert question.evidence_required.knowledge_state is KnowledgeState.UNKNOWN
        assert question.evidence_required.value is None


def test_profile_asset_known_gaps_are_visible_in_preview_and_report_limits() -> None:
    """Catches reducing concrete profile limitations to a generic SRR identifier."""

    preview = guided_fixture._preview()
    expected = {
        "ProfileCoverageStatement shape is not consistently instantiated in PRD v8.",
        "Predicate closure has not received independent scientific review.",
    }
    assert expected <= set(preview.summary.known_profile_gaps)

    confirmed = guided_fixture._confirm(preview)
    result = confirmed.canonical_result.value
    assert result is not None
    assert any(
        "user-selected review focus" in limit and "not a Theory-reviewed question priority" in limit
        for limit in result.report_bundle.inference_limits
    )
    assert all(
        any(gap in limit for limit in result.report_bundle.inference_limits) for gap in expected
    )


def test_sample_sheet_row_limit_is_explicitly_operational_not_scientific() -> None:
    """Catches unbounded row materialization from one guided API request."""

    module = _guided()
    base = guided_fixture._draft()
    groups = [group.model_dump(mode="python") for group in base.planned_groups]
    groups[0]["planned_count"] = 100_001

    with pytest.raises(ValidationError, match=r"operational|safety"):
        module.GuidedQuickDesignDraft.model_validate(
            {
                **base.model_dump(mode="python"),
                "planned_groups": groups,
            }
        )

    groups = [group.model_dump(mode="python") for group in base.planned_groups]
    groups[0]["planned_count"] = 50_001
    groups[1]["planned_count"] = 50_000
    with pytest.raises(ValidationError, match=r"operational|safety"):
        module.GuidedQuickDesignDraft.model_validate(
            {
                **base.model_dump(mode="python"),
                "planned_groups": groups,
            }
        )


def test_raw_canonical_route_cannot_claim_guided_confirmation() -> None:
    """Catches the raw AUTHOR_ASSERTED lane being displayed as guided-confirmed."""

    preview = guided_fixture._preview()
    confirmed = guided_fixture._confirm(preview)
    submission = confirmed.submission_audit_snapshot.value
    assert submission is not None

    response = TestClient(create_app()).post(
        "/v8/quick-design",
        json=submission.model_dump(mode="json"),
    )
    assert response.status_code == 200, response.text
    contract = response.json()["contract"]
    assert contract["input_mode"] == "RAW_AUTHOR_ASSERTED"
    assert contract["guided_confirmation"] is False
