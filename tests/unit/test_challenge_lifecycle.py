"""PRD v9 AG.1 challenge lifecycle: fail-closed transitions and feedback gate."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from ntruth.governance.challenge_lifecycle import (
    ChallengeLifecycleError,
    ChallengeLifecycleState,
    ChallengeVersionRecord,
    activation_blockers,
    apply_transition,
    can_transition,
    item_level_feedback_permitted,
    reject_item_level_feedback_while_active,
    require_activation_ready,
    require_transition,
)
from ntruth.governance.contamination import (
    build_challenge_access_ledger_v8,
    build_contamination_attestation_v8,
)
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.training.custody import ArtifactReference

NOW = datetime(2026, 8, 25, 9, 0, tzinfo=UTC)
LATER = datetime(2026, 8, 26, 9, 0, tzinfo=UTC)
EVIDENCE = ("EVIDENCE-CHALLENGE-LIFECYCLE-001",)


def _record(**overrides: Any) -> ChallengeVersionRecord:
    fields: dict[str, Any] = {
        "challenge_id": "ECH-V9-001",
        "version": "v1",
        "custodian_actor_id": "external-custodian-001",
        "retirement_policy_id": "RETIRE-POLICY-001",
    }
    fields.update(overrides)
    return ChallengeVersionRecord.model_validate(fields)


def _present(value: Any) -> KnowledgeValue:
    return KnowledgeValue(
        knowledge_state=KnowledgeState.PRESENT,
        value=value,
        evidence_ids=EVIDENCE,
        claim_scope_id="EXTERNAL-CHALLENGE:ECH-V9-001",
    )


def _unknown(rationale: str) -> KnowledgeValue:
    return KnowledgeValue(
        knowledge_state=KnowledgeState.UNKNOWN,
        rationale=rationale,
        claim_scope_id="EXTERNAL-CHALLENGE:ECH-V9-001",
    )


def _attestation_for(item_id: str, risk: str) -> Any:
    from ntruth.governance.contamination import (
        ChallengeAccessEventV8,
        ChallengeAccessPurposeV8,
        ChallengeExposureRiskV8,
        ChallengeSourceClassV8,
    )

    ledger = build_challenge_access_ledger_v8(
        challenge_item_id=item_id,
        events=(
            ChallengeAccessEventV8(
                event_id=f"ACCESS-CUSTODY-{item_id}",
                actor_id="external-custodian-001",
                actor_role="EXTERNAL_CUSTODIAN",
                purpose=ChallengeAccessPurposeV8.CUSTODY,
                evidence_ref=EVIDENCE[0],
                occurred_at=NOW,
            ),
        ),
    )
    exposure = ChallengeExposureRiskV8(risk)
    return build_contamination_attestation_v8(
        challenge_item_id=item_id,
        source_class=ChallengeSourceClassV8.PROSPECTIVE_PRIVATE,
        publication_or_creation_date=_present("2026-09-01"),
        study_family_id="STUDY-FAMILY-9001",
        backbone_model_id="model-reviewed",
        backbone_revision="revision-reviewed",
        backbone_release_date=_unknown("No reviewed public release date."),
        documented_training_cutoff=_unknown("The backbone cutoff is undocumented."),
        known_web_availability=_present(False),
        text_exposure_risk=_present(exposure),
        exposure_assessment_evidence_refs=EVIDENCE,
        probes_run=_unknown("No probes were run."),
        residual_risk=_present(exposure),
        study_family_overlap=_present(False),
        permitted_claims=("pipeline_diagnostic",),
        forbidden_claims=("proof_of_no_pretraining_exposure",),
        custodian_actor_id="external-custodian-001",
        custodian_actor_role="EXTERNAL_CUSTODIAN",
        attester_actor_id="independent-attester-001",
        attester_actor_role="INDEPENDENT_CONTAMINATION_REVIEWER",
        access_ledger=ledger,
        family_evidence_references=(
            ArtifactReference(artifact_id=f"FAMILY-{item_id}", sha256="1" * 64),
        ),
        attester_attestation_ref="ATTESTATION-INDEPENDENT-001",
        created_at=NOW,
    )


def _active() -> ChallengeVersionRecord:
    frozen = apply_transition(_record(), ChallengeLifecycleState.FROZEN, occurred_at=NOW)
    return apply_transition(frozen, ChallengeLifecycleState.ACTIVE, occurred_at=LATER)


def _retired() -> ChallengeVersionRecord:
    return apply_transition(
        _active(), ChallengeLifecycleState.RETIRED_DIAGNOSTIC, occurred_at=LATER
    )


def test_full_happy_path_through_archive() -> None:
    record = _record()
    frozen = apply_transition(record, ChallengeLifecycleState.FROZEN, occurred_at=NOW)
    assert frozen.lifecycle_state is ChallengeLifecycleState.FROZEN
    assert frozen.frozen_at == NOW
    retired = _retired()
    archived = apply_transition(
        retired,
        ChallengeLifecycleState.PUBLIC_ARCHIVE,
        occurred_at=LATER,
        future_use_policy_updated=True,
    )
    assert archived.lifecycle_state is ChallengeLifecycleState.PUBLIC_ARCHIVE
    assert archived.frozen_at == NOW


def test_early_retirement_from_active_is_a_legal_edge() -> None:
    assert _retired().lifecycle_state is ChallengeLifecycleState.RETIRED_DIAGNOSTIC


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (ChallengeLifecycleState.DRAFT, ChallengeLifecycleState.ACTIVE),
        (ChallengeLifecycleState.DRAFT, ChallengeLifecycleState.RETIRED_DIAGNOSTIC),
        (ChallengeLifecycleState.DRAFT, ChallengeLifecycleState.PUBLIC_ARCHIVE),
        (ChallengeLifecycleState.FROZEN, ChallengeLifecycleState.DRAFT),
        (ChallengeLifecycleState.FROZEN, ChallengeLifecycleState.RETIRED_DIAGNOSTIC),
        (ChallengeLifecycleState.FROZEN, ChallengeLifecycleState.PUBLIC_ARCHIVE),
        (ChallengeLifecycleState.ACTIVE, ChallengeLifecycleState.FROZEN),
        (ChallengeLifecycleState.ACTIVE, ChallengeLifecycleState.PUBLIC_ARCHIVE),
        (ChallengeLifecycleState.ACTIVE, ChallengeLifecycleState.DRAFT),
        (ChallengeLifecycleState.RETIRED_DIAGNOSTIC, ChallengeLifecycleState.ACTIVE),
        (ChallengeLifecycleState.RETIRED_DIAGNOSTIC, ChallengeLifecycleState.FROZEN),
        (ChallengeLifecycleState.PUBLIC_ARCHIVE, ChallengeLifecycleState.ACTIVE),
        (ChallengeLifecycleState.PUBLIC_ARCHIVE, ChallengeLifecycleState.DRAFT),
    ],
)
def test_illegal_transitions_fail_closed(
    current: ChallengeLifecycleState, target: ChallengeLifecycleState
) -> None:
    assert can_transition(current, target) is False
    with pytest.raises(ChallengeLifecycleError):
        require_transition(current, target)


def test_public_archive_requires_future_use_policy_update() -> None:
    with pytest.raises(ChallengeLifecycleError, match="future-use"):
        apply_transition(_retired(), ChallengeLifecycleState.PUBLIC_ARCHIVE, occurred_at=LATER)


def test_naive_timestamps_are_rejected() -> None:
    from datetime import datetime as naive_datetime

    with pytest.raises(ValueError, match="timezone"):
        apply_transition(
            _record(),
            ChallengeLifecycleState.FROZEN,
            occurred_at=naive_datetime(2026, 1, 1, 12, 0),
        )


def test_post_draft_records_require_frozen_at() -> None:
    with pytest.raises(ValidationError, match="frozen_at"):
        ChallengeVersionRecord.model_validate(
            {
                "challenge_id": "ECH-V9-001",
                "version": "v1",
                "custodian_actor_id": "external-custodian-001",
                "retirement_policy_id": "RETIRE-POLICY-001",
                "lifecycle_state": ChallengeLifecycleState.ACTIVE,
            }
        )


def test_custodian_must_be_external_and_access_log_required() -> None:
    with pytest.raises(ValidationError):
        _record(custodian_external=False)
    with pytest.raises(ValidationError):
        _record(access_log_required=False)


def test_item_level_feedback_prohibited_while_active() -> None:
    active = _active()
    with pytest.raises(ChallengeLifecycleError, match="item-level feedback"):
        reject_item_level_feedback_while_active(active)
    assert item_level_feedback_permitted(active) is False


def test_item_level_feedback_permitted_only_in_public_archive() -> None:
    draft = _record()
    frozen = apply_transition(draft, ChallengeLifecycleState.FROZEN, occurred_at=NOW)
    assert item_level_feedback_permitted(draft) is False
    assert item_level_feedback_permitted(frozen) is False
    retired = _retired()
    assert item_level_feedback_permitted(retired) is False
    archived = apply_transition(
        retired,
        ChallengeLifecycleState.PUBLIC_ARCHIVE,
        occurred_at=LATER,
        future_use_policy_updated=True,
    )
    assert item_level_feedback_permitted(archived) is True
    reject_item_level_feedback_while_active(archived)


def test_activation_blocked_without_attestations() -> None:
    blockers = activation_blockers((), required_item_ids={"item-b", "item-a"})
    assert blockers == (
        "missing_contamination_attestation:item-a",
        "missing_contamination_attestation:item-b",
    )
    with pytest.raises(ChallengeLifecycleError, match="activation blocked"):
        require_activation_ready((), required_item_ids=["item-a"])


def test_activation_allowed_with_low_residual_risk() -> None:
    attestation = _attestation_for("ECH-V9-001-item-1", "LOW")
    assert activation_blockers((attestation,), required_item_ids={"ECH-V9-001-item-1"}) == ()
    require_activation_ready((attestation,), required_item_ids={"ECH-V9-001-item-1"})


def test_activation_blocked_with_high_or_unknown_residual_risk() -> None:
    high = _attestation_for("item-high", "HIGH")
    unknown = _attestation_for("item-unknown", "UNKNOWN")
    assert activation_blockers((high,), required_item_ids={"item-high"}) == (
        "residual_risk_high:item-high",
    )
    assert activation_blockers((unknown,), required_item_ids={"item-unknown"}) == (
        "residual_risk_unknown:item-unknown",
    )
    assert activation_blockers(
        (high, unknown), required_item_ids={"item-high", "item-unknown"}
    ) == (
        "residual_risk_high:item-high",
        "residual_risk_unknown:item-unknown",
    )


def test_retirement_policy_id_is_mandatory() -> None:
    with pytest.raises(ValidationError):
        ChallengeVersionRecord(challenge_id="ECH", version="v1")


def test_lifecycle_states_are_exactly_the_ag1_set() -> None:
    assert [state.value for state in ChallengeLifecycleState] == [
        "DRAFT",
        "FROZEN",
        "ACTIVE",
        "RETIRED_DIAGNOSTIC",
        "PUBLIC_ARCHIVE",
    ]
