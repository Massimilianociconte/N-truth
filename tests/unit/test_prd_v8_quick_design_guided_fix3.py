"""RED regressions for complete guided PREVIEW and CONFIRM envelope closure."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

import pytest
import test_prd_v8_quick_design_guided_builder as guided_fixture
from pydantic import ValidationError

from ntruth.derivation_theory.runtime import load_runtime_bundle
from ntruth.schemas.core import content_checksum
from ntruth.schemas.knowledge import KnowledgeState

Construction = Literal["model_copy", "model_construct"]
EntryPoint = Literal["response", "accessor"]


def _guided() -> object:
    return guided_fixture._guided()


def _construct(model: object, updates: dict[str, object], construction: Construction) -> object:
    if construction == "model_copy":
        return model.model_copy(update=updates)
    state = dict(model.__dict__)
    state.update(updates)
    return type(model).model_construct(**state)


def _variant_draft() -> object:
    module = _guided()
    base = guided_fixture._draft()
    groups = [group.model_dump(mode="python") for group in base.planned_groups]
    groups[0]["planned_count"] = 3
    return module.GuidedQuickDesignDraft.model_validate(
        {
            **base.model_dump(mode="python"),
            "block_title": "Independent membrane-integrity block",
            "endpoint_id": "membrane_integrity",
            "planned_groups": groups,
        }
    )


@pytest.fixture(scope="module")
def preview_pair() -> tuple[object, object]:
    first = guided_fixture._preview()
    second = guided_fixture._preview(_variant_draft())
    return first, second


@pytest.fixture(scope="module")
def confirmed_pair(preview_pair: tuple[object, object]) -> tuple[object, object]:
    first_preview, second_preview = preview_pair
    first = guided_fixture._confirm(first_preview)
    second_draft = _variant_draft()
    second = guided_fixture._confirm(
        second_preview,
        second_draft,
        actor_role="second_reviewer",
        confirmed_at=datetime(2026, 8, 10, 9, 45, tzinfo=UTC),
    )
    return first, second


def test_preview_embeds_typed_review_only_draft_and_bundle_snapshot(
    preview_pair: tuple[object, object],
) -> None:
    """Catches a preview that cannot be independently and exactly re-derived."""

    module = _guided()
    preview, _ = preview_pair
    snapshot_type = getattr(module, "GuidedQuickDesignReviewSnapshot", None)
    snapshot = getattr(preview, "review_snapshot", None)

    assert snapshot_type is not None
    assert isinstance(snapshot, snapshot_type)
    assert snapshot.draft == guided_fixture._draft()
    assert snapshot.conformance_bundle == load_runtime_bundle()
    assert snapshot.is_execution_capability is False
    assert preview.submission_is_execution_capability is False
    assert preview.submission_audit_snapshot.knowledge_state is KnowledgeState.UNKNOWN
    assert preview.canonical_result.knowledge_state is KnowledgeState.UNKNOWN
    with pytest.raises(ValueError, match=r"confirmed|CONFIRM|canonical result"):
        module.run_confirmed_guided_quick_design(preview)


@pytest.mark.parametrize("construction", ("model_copy", "model_construct"))
def test_preview_rejects_all_outer_projections_mixed_from_another_valid_draft(
    construction: Construction,
    preview_pair: tuple[object, object],
) -> None:
    """Catches checksum/summary/questions/artifacts floating free of reviewed draft bytes."""

    module = _guided()
    first, second = preview_pair
    forged = _construct(
        first,
        {
            "preview_checksum": second.preview_checksum,
            "summary": second.summary,
            "visible_questions": second.visible_questions,
            "question_queue": second.question_queue,
            "artifact_previews": second.artifact_previews,
        },
        construction,
    )

    with pytest.raises(ValidationError, match=r"closure|preview|summary|question|artifact"):
        module.GuidedQuickDesignBuildResponse.model_validate(forged.model_dump(mode="python"))


def test_preview_rejects_a_tampered_embedded_profile_bundle(
    preview_pair: tuple[object, object],
) -> None:
    """Catches a snapshot self-certifying a changed profile with response-local metadata."""

    module = _guided()
    preview, _ = preview_pair
    snapshot = getattr(preview, "review_snapshot", None)
    assert snapshot is not None
    bundle = snapshot.conformance_bundle
    forged_profile = bundle.profile_closure.model_copy(
        update={"known_gaps": (*bundle.profile_closure.known_gaps, "FORGED PROFILE GAP")}
    )
    forged_bundle = bundle.model_copy(update={"profile_closure": forged_profile})
    forged_snapshot = snapshot.model_copy(
        update={
            "conformance_bundle_payload": forged_bundle.model_dump(
                mode="json",
                exclude_unset=True,
            )
        }
    )
    forged = preview.model_copy(update={"review_snapshot": forged_snapshot})

    with pytest.raises(ValidationError, match=r"bundle|profile|conformance|closure"):
        module.GuidedQuickDesignBuildResponse.model_validate(forged.model_dump(mode="python"))


def _metadata_forgery(
    response: object,
    envelope_field: str,
    construction: Construction,
) -> object:
    envelope = getattr(response, envelope_field)
    forged_envelope = _construct(
        envelope,
        {
            "evidence_ids": ("EV-FORGED-METADATA",),
            "source_scope_ids": ("SOURCE-FORGED-METADATA",),
            "rationale": "Caller-supplied envelope provenance.",
            "claim_scope_id": "CLAIM-FORGED-METADATA",
            "query_scope_id": "IQ-FORGED-METADATA",
        },
        construction,
    )
    return _construct(response, {envelope_field: forged_envelope}, construction)


@pytest.mark.parametrize(
    "envelope_field",
    (
        "submission_audit_snapshot",
        "canonical_result",
        "confirmed_snapshot_checksum",
    ),
)
@pytest.mark.parametrize("construction", ("model_copy", "model_construct"))
@pytest.mark.parametrize("entrypoint", ("response", "accessor"))
def test_confirm_rejects_metadata_forgery_on_each_complete_knowledge_envelope(
    envelope_field: str,
    construction: Construction,
    entrypoint: EntryPoint,
    confirmed_pair: tuple[object, object],
) -> None:
    """Catches comparing only PRESENT values while accepting forged epistemic metadata."""

    module = _guided()
    confirmed, _ = confirmed_pair
    forged = _metadata_forgery(confirmed, envelope_field, construction)

    if entrypoint == "response":
        with pytest.raises(ValidationError, match=r"closure|envelope|metadata|snapshot"):
            module.GuidedQuickDesignBuildResponse.model_validate(forged.model_dump(mode="python"))
    else:
        with pytest.raises(ValueError, match=r"closure|envelope|metadata|snapshot"):
            module.run_confirmed_guided_quick_design(forged)


def _mixed_confirmed_response(
    first: object,
    second: object,
    construction: Construction,
) -> object:
    first_submission = first.submission_audit_snapshot.value
    second_result = second.canonical_result.value
    assert first_submission is not None and second_result is not None
    freeze = content_checksum(
        {
            "preview_checksum": first.preview_checksum,
            "submission_audit_snapshot": first_submission.model_dump(mode="json"),
            "canonical_result": second_result.model_dump(mode="json"),
        }
    )
    forged_result = _construct(
        first.canonical_result,
        {"value": second_result},
        construction,
    )
    forged_freeze = _construct(
        first.confirmed_snapshot_checksum,
        {"value": freeze},
        construction,
    )
    return _construct(
        first,
        {
            "canonical_result": forged_result,
            "confirmed_snapshot_checksum": forged_freeze,
        },
        construction,
    )


@pytest.mark.parametrize("construction", ("model_copy", "model_construct"))
@pytest.mark.parametrize("entrypoint", ("response", "accessor"))
def test_confirm_keeps_submission_result_closure_under_both_python_constructions(
    construction: Construction,
    entrypoint: EntryPoint,
    confirmed_pair: tuple[object, object],
) -> None:
    """Keeps the A/B rehash regression closed for copy and construct call paths."""

    module = _guided()
    forged = _mixed_confirmed_response(*confirmed_pair, construction)
    if entrypoint == "response":
        with pytest.raises(ValidationError, match=r"closure|submission|result|re-execution"):
            module.GuidedQuickDesignBuildResponse.model_validate(forged.model_dump(mode="python"))
    else:
        with pytest.raises(ValueError, match=r"closure|submission|result|re-execution"):
            module.run_confirmed_guided_quick_design(forged)


def test_preview_and_confirm_roundtrip_without_creating_a_second_execution_path(
    preview_pair: tuple[object, object],
    confirmed_pair: tuple[object, object],
) -> None:
    """Protects positive JSON persistence and same-call canonical-result access."""

    module = _guided()
    preview, _ = preview_pair
    confirmed, _ = confirmed_pair

    preview_roundtrip = module.GuidedQuickDesignBuildResponse.model_validate(
        preview.model_dump(mode="json")
    )
    confirmed_roundtrip = module.GuidedQuickDesignBuildResponse.model_validate(
        confirmed.model_dump(mode="json")
    )
    assert preview_roundtrip == preview
    assert confirmed_roundtrip == confirmed
    assert (
        module.run_confirmed_guided_quick_design(confirmed_roundtrip)
        == confirmed.canonical_result.value
    )
    assert not hasattr(confirmed_roundtrip, "next_endpoint")
