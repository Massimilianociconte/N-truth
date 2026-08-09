"""RED regressions for the guided-confirmation atomic closure boundary."""

from __future__ import annotations

import pickle
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Literal

import pytest
import test_prd_v8_quick_design_guided_builder as guided_fixture
from pydantic import ValidationError

from ntruth.schemas.core import content_checksum


class VerdictDatetime(datetime):
    """A pickle-visible datetime whose methods and public state are attacker-controlled."""

    method_calls = 0

    @property
    def design_adequacy(self) -> str:
        return "ADEQUATE"

    def utcoffset(self) -> timedelta | None:
        type(self).method_calls += 1
        return super().utcoffset()

    def isoformat(self, sep: str = "T", timespec: str = "auto") -> str:
        type(self).method_calls += 1
        return super().isoformat(sep=sep, timespec=timespec)


class VerdictTimezone(tzinfo):
    """A pickle-visible timezone with final scientific state and overridable methods."""

    method_calls = 0

    @property
    def experimental_unit(self) -> str:
        return "well"

    def utcoffset(self, value: datetime | None) -> timedelta:
        type(self).method_calls += 1
        return timedelta(0)

    def dst(self, value: datetime | None) -> timedelta:
        type(self).method_calls += 1
        return timedelta(0)

    def tzname(self, value: datetime | None) -> str:
        type(self).method_calls += 1
        return "FORGED"


def _guided() -> object:
    return guided_fixture._guided()


def _forged_confirmation_request(
    confirmed_at: datetime,
    construction: Literal["model_copy", "model_construct"],
) -> object:
    module = _guided()
    preview = guided_fixture._preview()
    valid_confirmation = module.GuidedQuickDesignConfirmation(
        preview_checksum=preview.preview_checksum,
        review_focus_predicate_id=preview.visible_questions[0].predicate_id,
        actor_role="researcher",
        confirmed_at=datetime(2026, 8, 9, 8, 30, tzinfo=UTC),
    )
    valid_request = module.GuidedQuickDesignBuildRequest(
        action="CONFIRM",
        draft=guided_fixture._draft(),
        confirmation=valid_confirmation,
    )
    if construction == "model_copy":
        forged_confirmation = valid_confirmation.model_copy(update={"confirmed_at": confirmed_at})
        forged_request = valid_request.model_copy(update={"confirmation": forged_confirmation})
    else:
        confirmation_state = dict(valid_confirmation.__dict__)
        confirmation_state["confirmed_at"] = confirmed_at
        forged_confirmation = type(valid_confirmation).model_construct(**confirmation_state)
        request_state = dict(valid_request.__dict__)
        request_state["confirmation"] = forged_confirmation
        forged_request = type(valid_request).model_construct(**request_state)
    return pickle.loads(pickle.dumps(forged_request))


@pytest.mark.parametrize("temporal_kind", ("datetime_subclass", "timezone_subclass"))
def test_confirmation_constructor_rejects_temporal_subclasses_before_methods(
    temporal_kind: Literal["datetime_subclass", "timezone_subclass"],
) -> None:
    """Catches the validated constructor invoking an attacker-controlled time method."""

    module = _guided()
    preview = guided_fixture._preview()
    if temporal_kind == "datetime_subclass":
        confirmed_at = VerdictDatetime(2026, 8, 9, 8, 30, tzinfo=UTC)
        counter_owner = VerdictDatetime
    else:
        confirmed_at = datetime(2026, 8, 9, 8, 30, tzinfo=VerdictTimezone())
        counter_owner = VerdictTimezone
    counter_owner.method_calls = 0

    with pytest.raises(ValidationError, match=r"canonical|datetime|timezone|temporal"):
        module.GuidedQuickDesignConfirmation(
            preview_checksum=preview.preview_checksum,
            review_focus_predicate_id=preview.visible_questions[0].predicate_id,
            actor_role="researcher",
            confirmed_at=confirmed_at,
        )
    assert counter_owner.method_calls == 0


@pytest.mark.parametrize("construction", ("model_copy", "model_construct"))
@pytest.mark.parametrize("temporal_kind", ("datetime_subclass", "timezone_subclass"))
def test_guided_builder_rejects_pickle_visible_temporal_subclasses_before_methods(
    construction: Literal["model_copy", "model_construct"],
    temporal_kind: Literal["datetime_subclass", "timezone_subclass"],
) -> None:
    """Catches overridable temporal methods influencing confirmation-event identity."""

    module = _guided()
    if temporal_kind == "datetime_subclass":
        confirmed_at = VerdictDatetime(2026, 8, 9, 8, 30, tzinfo=UTC)
        counter_owner = VerdictDatetime
    else:
        confirmed_at = datetime(2026, 8, 9, 8, 30, tzinfo=VerdictTimezone())
        counter_owner = VerdictTimezone
    forged_request = _forged_confirmation_request(confirmed_at, construction)
    counter_owner.method_calls = 0

    with pytest.raises(ValueError, match=r"canonical|datetime|timezone|temporal"):
        module.build_guided_quick_design(forged_request)
    assert counter_owner.method_calls == 0


def _variant_draft() -> object:
    module = _guided()
    base = guided_fixture._draft()
    groups = [group.model_dump(mode="python") for group in base.planned_groups]
    groups[0]["planned_count"] = 3
    return module.GuidedQuickDesignDraft.model_validate(
        {
            **base.model_dump(mode="python"),
            "block_title": "Independent dose response block",
            "endpoint_id": "membrane_integrity",
            "planned_groups": groups,
        }
    )


def _confirmed_pair() -> tuple[object, object]:
    first_preview = guided_fixture._preview()
    first = guided_fixture._confirm(first_preview)
    second_draft = _variant_draft()
    second_preview = guided_fixture._preview(second_draft)
    second = guided_fixture._confirm(
        second_preview,
        second_draft,
        actor_role="second_reviewer",
        confirmed_at=datetime(2026, 8, 10, 9, 45, tzinfo=UTC),
    )
    return first, second


def _recalculated_freeze(
    *,
    preview_checksum: str,
    submission: object,
    result: object,
) -> str:
    """Reproduce the public checksum calculation used by the pre-fix envelope."""

    return content_checksum(
        {
            "preview_checksum": preview_checksum,
            "submission_audit_snapshot": submission.model_dump(mode="json"),
            "canonical_result": result.model_dump(mode="json"),
        }
    )


def _mixed_submission_result_response() -> object:
    first, second = _confirmed_pair()
    first_submission = first.submission_audit_snapshot.value
    second_submission = second.submission_audit_snapshot.value
    second_result = second.canonical_result.value
    assert first_submission is not None
    assert second_submission is not None
    assert second_result is not None

    # The two individually valid envelopes differ across every closure axis named
    # by the guided contract; mixing them must not become valid by rehashing.
    assert first_submission.pipeline_request.query != second_submission.pipeline_request.query
    assert first_submission.planned_unit_counts != second_submission.planned_unit_counts
    assert first_submission.planned_event_registry != second_submission.planned_event_registry
    assert (
        first_submission.input_ledger.confirmation_events
        != second_submission.input_ledger.confirmation_events
    )
    assert first_submission.input_ledger.artifacts != second_submission.input_ledger.artifacts

    freeze = _recalculated_freeze(
        preview_checksum=first.preview_checksum,
        submission=first_submission,
        result=second_result,
    )
    return first.model_copy(
        update={
            "canonical_result": first.canonical_result.model_copy(update={"value": second_result}),
            "confirmed_snapshot_checksum": first.confirmed_snapshot_checksum.model_copy(
                update={"value": freeze}
            ),
        }
    )


def test_confirmed_envelope_rejects_submission_a_result_b_after_public_rehash() -> None:
    """Catches treating a caller-recomputed checksum as semantic authority."""

    module = _guided()
    mixed = _mixed_submission_result_response()

    with pytest.raises(ValidationError, match=r"closure|submission|result|re-execution"):
        module.GuidedQuickDesignBuildResponse.model_validate(mixed.model_dump(mode="python"))


def test_confirmed_result_accessor_rejects_mixed_valid_envelopes_after_public_rehash() -> None:
    """Catches the convenience accessor bypassing atomic submission/result closure."""

    module = _guided()
    mixed = _mixed_submission_result_response()

    with pytest.raises(ValueError, match=r"closure|submission|result|re-execution"):
        module.run_confirmed_guided_quick_design(mixed)


@pytest.mark.parametrize(
    "outer_field",
    ("preview_checksum", "summary", "questions", "artifacts"),
)
def test_confirmed_envelope_rejects_outer_projection_from_another_valid_draft(
    outer_field: Literal["preview_checksum", "summary", "questions", "artifacts"],
) -> None:
    """Catches detached preview, summary, question, or artifact projections."""

    module = _guided()
    first, second = _confirmed_pair()
    first_submission = first.submission_audit_snapshot.value
    first_result = first.canonical_result.value
    assert first_submission is not None and first_result is not None

    updates: dict[str, object]
    if outer_field == "preview_checksum":
        updates = {"preview_checksum": second.preview_checksum}
    elif outer_field == "summary":
        updates = {"summary": second.summary}
    elif outer_field == "questions":
        updates = {
            "visible_questions": second.visible_questions,
            "question_queue": second.question_queue,
        }
    else:
        updates = {"artifact_previews": second.artifact_previews}
    preview_checksum = str(updates.get("preview_checksum", first.preview_checksum))
    updates["confirmed_snapshot_checksum"] = first.confirmed_snapshot_checksum.model_copy(
        update={
            "value": _recalculated_freeze(
                preview_checksum=preview_checksum,
                submission=first_submission,
                result=first_result,
            )
        }
    )
    forged = first.model_copy(update=updates)

    with pytest.raises(ValidationError, match=r"closure|preview|summary|question|artifact"):
        module.GuidedQuickDesignBuildResponse.model_validate(forged.model_dump(mode="python"))
