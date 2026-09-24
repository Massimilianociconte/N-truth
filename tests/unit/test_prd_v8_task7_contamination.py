"""External Challenge contamination/custody contracts remain claim-scoped and fail closed."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

import ntruth.governance.contamination as contamination
from ntruth.governance.contamination import (
    ChallengeAccessEventV8,
    ChallengeAccessLedgerV8,
    ChallengeAccessPurposeV8,
    ChallengeExposureRiskV8,
    ChallengeSourceClassV8,
    ChallengeUseDecisionV8,
    ChallengeUsePurposeV8,
    append_challenge_access_ledger_v8,
    build_challenge_access_ledger_v8,
    build_contamination_attestation_v8,
    build_external_challenge_use_request_v8,
    evaluate_external_challenge_use_v8,
)
from ntruth.schemas.core import content_checksum
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.training.custody import ArtifactReference, ExternalChallengeDependency

NOW = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
EVIDENCE = ("EVIDENCE-CONTAMINATION-001",)


def _present(value):
    return KnowledgeValue(
        knowledge_state=KnowledgeState.PRESENT,
        value=value,
        evidence_ids=EVIDENCE,
        claim_scope_id="EXTERNAL-CHALLENGE:ECH-001",
    )


def _unknown(rationale: str):
    return KnowledgeValue(
        knowledge_state=KnowledgeState.UNKNOWN,
        rationale=rationale,
        claim_scope_id="EXTERNAL-CHALLENGE:ECH-001",
    )


def _access(purpose: ChallengeAccessPurposeV8, *, actor: str = "custodian-001"):
    return ChallengeAccessEventV8(
        event_id=f"ACCESS-{purpose.value}-{actor}",
        actor_id=actor,
        actor_role="EXTERNAL_CUSTODIAN",
        purpose=purpose,
        evidence_ref="EVIDENCE-ACCESS-001",
        occurred_at=NOW,
    )


def _attestation(
    *,
    risk: ChallengeExposureRiskV8 = ChallengeExposureRiskV8.LOW,
    events: tuple[ChallengeAccessEventV8, ...] | None = None,
    probes=None,
):
    ledger = build_challenge_access_ledger_v8(
        challenge_item_id="ECH-001",
        events=events or (_access(ChallengeAccessPurposeV8.CUSTODY),),
    )
    probes_state = probes or KnowledgeValue(
        knowledge_state=KnowledgeState.ABSENT_EXPLICIT,
        evidence_ids=EVIDENCE,
        claim_scope_id="EXTERNAL-CHALLENGE:ECH-001:PROBES",
    )
    return build_contamination_attestation_v8(
        challenge_item_id="ECH-001",
        source_class=ChallengeSourceClassV8.PROSPECTIVE_PRIVATE,
        publication_or_creation_date=_present("2026-09-01"),
        study_family_id="STUDY-FAMILY-9001",
        backbone_model_id="model-reviewed",
        backbone_revision="revision-reviewed",
        backbone_release_date=_unknown("No reviewed public release date is available."),
        documented_training_cutoff=_unknown("The backbone cutoff is undocumented."),
        known_web_availability=_present(False),
        text_exposure_risk=_present(risk),
        exposure_assessment_evidence_refs=EVIDENCE,
        probes_run=probes_state,
        residual_risk=_present(risk),
        study_family_overlap=_present(False),
        permitted_claims=("pipeline_diagnostic", "pipeline_generalization"),
        forbidden_claims=("proof_of_no_pretraining_exposure",),
        custodian_actor_id="custodian-001",
        custodian_actor_role="EXTERNAL_CUSTODIAN",
        attester_actor_id="attester-independent-001",
        attester_actor_role="INDEPENDENT_CONTAMINATION_REVIEWER",
        access_ledger=ledger,
        family_evidence_references=(
            ArtifactReference(artifact_id="FAMILY-EVIDENCE-001", sha256="1" * 64),
        ),
        attester_attestation_ref="ATTESTATION-INDEPENDENT-001",
        created_at=NOW,
    )


def _request(
    purpose: ChallengeUsePurposeV8,
    *,
    revision: str = "revision-reviewed",
    requested_claims: tuple[str, ...] | None = None,
    requester_actor_id: str = "scorer-independent-001",
):
    return build_external_challenge_use_request_v8(
        challenge_item_id="ECH-001",
        snapshot_id="protected-evaluation-001",
        snapshot_sha256="2" * 64,
        source_manifest_id="source-manifest-001",
        source_manifest_sha256="3" * 64,
        record_ids_checksum="4" * 64,
        backbone_model_id="model-reviewed",
        backbone_revision=revision,
        purpose=purpose,
        requested_claims=requested_claims
        or (
            "pipeline_diagnostic"
            if purpose is ChallengeUsePurposeV8.DIAGNOSTIC
            else "pipeline_generalization",
        ),
        requester_actor_id=requester_actor_id,
        requester_role="INDEPENDENT_SCORER",
    )


def test_probes_are_open_world_and_raw_empty_list_is_rejected() -> None:
    payload = _attestation().model_dump(mode="python")
    payload["probes_run"] = []
    with pytest.raises((ValueError, ValidationError), match=r"probes|Knowledge|model"):
        type(_attestation()).model_validate(payload)


@pytest.mark.parametrize(
    "risk",
    (ChallengeExposureRiskV8.HIGH, ChallengeExposureRiskV8.UNKNOWN),
)
def test_high_or_unknown_exposure_is_diagnostic_only(risk) -> None:
    attestation = _attestation(risk=risk)
    diagnostic = evaluate_external_challenge_use_v8(
        attestation, _request(ChallengeUsePurposeV8.DIAGNOSTIC)
    )
    generalization = evaluate_external_challenge_use_v8(
        attestation, _request(ChallengeUsePurposeV8.GENERALIZATION)
    )
    assert diagnostic.decision is ChallengeUseDecisionV8.DIAGNOSTIC_ONLY
    assert generalization.decision is ChallengeUseDecisionV8.BLOCK


@pytest.mark.parametrize(
    "purpose",
    (
        ChallengeAccessPurposeV8.TRAINING,
        ChallengeAccessPurposeV8.MODEL_SELECTION,
        ChallengeAccessPurposeV8.PROMPT_DEVELOPMENT,
        ChallengeAccessPurposeV8.RULE_TUNING,
        ChallengeAccessPurposeV8.SCHEMA_TUNING,
        ChallengeAccessPurposeV8.THRESHOLD_TUNING,
    ),
)
def test_forbidden_access_invalidates_qualifying_use(purpose) -> None:
    attestation = _attestation(
        events=(
            _access(ChallengeAccessPurposeV8.CUSTODY),
            _access(purpose, actor="developer-001"),
        )
    )
    decision = evaluate_external_challenge_use_v8(
        attestation, _request(ChallengeUsePurposeV8.GENERALIZATION)
    )
    assert decision.decision is ChallengeUseDecisionV8.BLOCK
    assert any("access" in blocker.lower() for blocker in (decision.blockers.value or ()))


def test_backbone_revision_drift_and_forbidden_claim_are_blocked() -> None:
    attestation = _attestation()
    drift = evaluate_external_challenge_use_v8(
        attestation,
        _request(ChallengeUsePurposeV8.GENERALIZATION, revision="different-revision"),
    )
    assert drift.decision is ChallengeUseDecisionV8.BLOCK
    forbidden = _request(
        ChallengeUsePurposeV8.RELEASE,
        requested_claims=("proof_of_no_pretraining_exposure",),
    )
    decision = evaluate_external_challenge_use_v8(attestation, forbidden)
    assert decision.decision is ChallengeUseDecisionV8.BLOCK


def test_evaluation_is_addressed_never_authorizes_use_and_has_open_world_blockers() -> None:
    result = evaluate_external_challenge_use_v8(
        _attestation(), _request(ChallengeUsePurposeV8.GENERALIZATION)
    )
    assert result.evaluation_id.startswith("EXTERNAL-CHALLENGE-EVALUATION-")
    assert result.use_authorized is False
    assert result.decision is ChallengeUseDecisionV8.SCIENTIFIC_REVIEW_REQUIRED
    assert result.blockers.knowledge_state is KnowledgeState.PRESENT
    assert any("authority" in item.lower() for item in (result.blockers.value or ()))


def test_placeholder_date_unknown_family_overlap_and_requester_role_collision_fail_closed() -> None:
    payload = _attestation().model_dump(mode="python")
    payload["publication_or_creation_date"]["value"] = "2026-XX-XX"
    with pytest.raises((ValueError, ValidationError), match=r"date|month|format"):
        type(_attestation()).model_validate(payload)

    unknown_overlap = _attestation().model_copy(
        update={"study_family_overlap": _unknown("Family overlap review is incomplete.")}
    )
    overlap_decision = evaluate_external_challenge_use_v8(
        unknown_overlap, _request(ChallengeUsePurposeV8.GENERALIZATION)
    )
    assert overlap_decision.decision is ChallengeUseDecisionV8.BLOCK
    assert any("family overlap" in item.lower() for item in (overlap_decision.blockers.value or ()))

    collision = _request(
        ChallengeUsePurposeV8.GENERALIZATION,
        requester_actor_id="custodian-001",
    )
    collision_decision = evaluate_external_challenge_use_v8(_attestation(), collision)
    assert collision_decision.decision is ChallengeUseDecisionV8.BLOCK
    assert any("independent" in item.lower() for item in (collision_decision.blockers.value or ()))


def test_custodian_attester_collision_and_training_eligibility_are_impossible() -> None:
    payload = _attestation().model_dump(mode="python")
    payload["attester_actor_id"] = payload["custodian_actor_id"]
    with pytest.raises((ValueError, ValidationError), match=r"independent|custodian"):
        type(_attestation()).model_validate(payload)
    assert _attestation().training_eligible is False
    assert _attestation().model_selection_eligible is False


def test_access_ledger_append_is_content_addressed_and_preserves_history() -> None:
    initial = build_challenge_access_ledger_v8(
        challenge_item_id="ECH-001",
        events=(_access(ChallengeAccessPurposeV8.CUSTODY),),
    )
    appended = append_challenge_access_ledger_v8(
        initial,
        (_access(ChallengeAccessPurposeV8.INDEPENDENT_SCORING, actor="scorer-001"),),
    )
    assert appended.events[: len(initial.events)] == initial.events
    assert appended.parent_ledger.knowledge_state is KnowledgeState.PRESENT
    assert appended.parent_ledger.value == ArtifactReference(
        artifact_id=initial.ledger_id,
        sha256=initial.content_checksum,
    )
    with pytest.raises((ValueError, ValidationError), match=r"unique|duplicate|append"):
        append_challenge_access_ledger_v8(
            appended,
            (_access(ChallengeAccessPurposeV8.CUSTODY),),
        )


def _addressed_request(**updates):
    builder = getattr(contamination, "build_external_challenge_use_request_v8", None)
    assert callable(builder), "External Challenge requests must be content-addressed"
    fields = {
        "challenge_item_id": "ECH-001",
        "snapshot_id": "protected-evaluation-001",
        "snapshot_sha256": "2" * 64,
        "source_manifest_id": "source-manifest-001",
        "source_manifest_sha256": "3" * 64,
        "record_ids_checksum": "4" * 64,
        "backbone_model_id": "model-reviewed",
        "backbone_revision": "revision-reviewed",
        "purpose": ChallengeUsePurposeV8.GENERALIZATION,
        "requested_claims": ("pipeline_generalization",),
        "requester_actor_id": "scorer-independent-001",
        "requester_role": "INDEPENDENT_SCORER",
    }
    fields.update(updates)
    return builder(**fields)


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("snapshot_id", "protected-evaluation-stale"),
        ("snapshot_sha256", "a" * 64),
        ("source_manifest_id", "source-manifest-stale"),
        ("source_manifest_sha256", "b" * 64),
        ("record_ids_checksum", "c" * 64),
    ),
)
def test_external_request_dataset_pin_mutation_changes_identity_and_is_persisted(
    field: str, replacement: str
) -> None:
    baseline_request = _addressed_request()
    mutated_request = _addressed_request(**{field: replacement})
    assert mutated_request.request_id != baseline_request.request_id
    assert mutated_request.content_checksum != baseline_request.content_checksum

    baseline = evaluate_external_challenge_use_v8(_attestation(), baseline_request)
    mutated = evaluate_external_challenge_use_v8(_attestation(), mutated_request)
    assert mutated.evaluation_id != baseline.evaluation_id
    assert getattr(mutated, field) == replacement
    assert mutated.request_sha256 == mutated_request.content_checksum
    assert mutated.decision is ChallengeUseDecisionV8.SCIENTIFIC_REVIEW_REQUIRED
    assert mutated.blockers.knowledge_state is KnowledgeState.PRESENT


def _forged_descendant_without_parent_history(
    parent: ChallengeAccessLedgerV8,
) -> ChallengeAccessLedgerV8:
    fields = {
        "challenge_item_id": parent.challenge_item_id,
        "parent_ledger": KnowledgeValue[ArtifactReference](
            knowledge_state=KnowledgeState.PRESENT,
            value=ArtifactReference(
                artifact_id=parent.ledger_id,
                sha256=parent.content_checksum,
            ),
            evidence_ids=(parent.ledger_id,),
            claim_scope_id="EXTERNAL-CHALLENGE:ECH-001:ACCESS-LEDGER",
        ),
        "events": (_access(ChallengeAccessPurposeV8.CUSTODY),),
    }
    draft = ChallengeAccessLedgerV8.model_construct(
        ledger_id="CHALLENGE-ACCESS-LEDGER-PENDING",
        content_checksum="0" * 64,
        **fields,
    )
    checksum = content_checksum(
        draft.model_dump(mode="json", exclude={"ledger_id", "content_checksum"})
    )
    return ChallengeAccessLedgerV8(
        ledger_id=f"CHALLENGE-ACCESS-LEDGER-{checksum[:20]}",
        content_checksum=checksum,
        **fields,
    )


def _actor_assignments(*, collide_function: str | None = None):
    assignment_type = getattr(contamination, "ChallengeActorAssignmentV8", None)
    function_type = getattr(contamination, "ChallengeActorFunctionV8", None)
    assert assignment_type is not None and function_type is not None
    specs = (
        ("CUSTODIAN", "custodian-001", "EXTERNAL_CUSTODIAN"),
        ("ATTESTER", "attester-independent-001", "INDEPENDENT_CONTAMINATION_REVIEWER"),
        ("INDEPENDENT_SCORER", "scorer-independent-001", "INDEPENDENT_SCORER"),
        ("TRAINER", "trainer-independent-001", "TRAINER"),
        ("GENERATOR", "generator-independent-001", "GENERATOR"),
        ("MODEL_SELECTOR", "selector-independent-001", "MODEL_SELECTOR"),
        ("RELEASE_OWNER", "release-independent-001", "RELEASE_OWNER"),
    )
    return tuple(
        assignment_type(
            function=function_type[name],
            actor_id=("custodian-001" if name == collide_function else actor_id),
            actor_role=("EXTERNAL_CUSTODIAN" if name == collide_function else role),
        )
        for name, actor_id, role in specs
    )


@pytest.mark.parametrize(
    "collide_function",
    ("ATTESTER", "INDEPENDENT_SCORER", "TRAINER", "GENERATOR", "MODEL_SELECTOR", "RELEASE_OWNER"),
)
def test_external_actor_roster_rejects_id_and_role_collision(collide_function: str) -> None:
    roster_builder = getattr(contamination, "build_challenge_actor_roster_v8", None)
    assert callable(roster_builder), "a resolved actor-role roster is mandatory"
    with pytest.raises((ValueError, ValidationError), match=r"actor|role|separation|unique"):
        roster_builder(
            challenge_item_id="ECH-001",
            assignments=_actor_assignments(collide_function=collide_function),
        )


def test_ledger_resolution_rejects_descendant_that_deleted_forbidden_parent_event() -> None:
    roster_builder = getattr(contamination, "build_challenge_actor_roster_v8", None)
    resolution_builder = getattr(
        contamination, "build_external_challenge_authority_resolution_v8", None
    )
    assert callable(roster_builder) and callable(resolution_builder)
    parent = build_challenge_access_ledger_v8(
        challenge_item_id="ECH-001",
        events=(
            _access(ChallengeAccessPurposeV8.CUSTODY),
            _access(ChallengeAccessPurposeV8.TRAINING, actor="trainer-independent-001"),
        ),
    )
    forged = _forged_descendant_without_parent_history(parent)
    attestation = _attestation(events=forged.events)
    request = _addressed_request()
    roster = roster_builder(challenge_item_id="ECH-001", assignments=_actor_assignments())
    dependency = ExternalChallengeDependency(
        review_status="SCIENTIFIC_REVIEW_REQUIRED",
        task7_contamination_attestation_reference=ArtifactReference(
            artifact_id=attestation.attestation_id,
            sha256=attestation.content_checksum,
        ),
        custody_reference=ArtifactReference(
            artifact_id=forged.ledger_id,
            sha256=forged.content_checksum,
        ),
        family_evidence_references=attestation.family_evidence_references,
    )
    with pytest.raises((ValueError, ValidationError), match=r"history|prefix|parent|append"):
        resolution_builder(
            challenge_item_id="ECH-001",
            snapshot=ArtifactReference(
                artifact_id=request.snapshot_id, sha256=request.snapshot_sha256
            ),
            source_manifest=ArtifactReference(
                artifact_id=request.source_manifest_id,
                sha256=request.source_manifest_sha256,
            ),
            record_ids_checksum=request.record_ids_checksum,
            task5_dependency=dependency,
            access_ledger_head=ArtifactReference(
                artifact_id=forged.ledger_id,
                sha256=forged.content_checksum,
            ),
            access_ledgers=(parent, forged),
            actor_roster=roster,
        )


@pytest.mark.parametrize(
    ("publication", "cutoff"),
    ((date(2020, 1, 1), date(2025, 1, 1)), (date(2025, 1, 1), date(2025, 1, 1))),
)
def test_post_cutoff_public_requires_publication_strictly_after_cutoff(
    publication: date, cutoff: date
) -> None:
    attestation = _attestation().model_copy(
        update={
            "source_class": ChallengeSourceClassV8.POST_CUTOFF_PUBLIC,
            "publication_or_creation_date": _present(publication),
            "backbone_release_date": _present(date(2025, 1, 1)),
            "documented_training_cutoff": _present(cutoff),
            "known_web_availability": _present(True),
            "probes_run": _present(("PROBE-001",)),
        }
    )
    result = evaluate_external_challenge_use_v8(
        attestation, _request(ChallengeUsePurposeV8.GENERALIZATION)
    )
    assert result.decision is ChallengeUseDecisionV8.BLOCK
    assert any("cutoff" in item.lower() for item in (result.blockers.value or ()))


def _valid_resolution(attestation, request):
    roster = contamination.build_challenge_actor_roster_v8(
        challenge_item_id="ECH-001", assignments=_actor_assignments()
    )
    dependency = ExternalChallengeDependency(
        review_status="SCIENTIFIC_REVIEW_REQUIRED",
        task7_contamination_attestation_reference=ArtifactReference(
            artifact_id=attestation.attestation_id,
            sha256=attestation.content_checksum,
        ),
        custody_reference=ArtifactReference(
            artifact_id=attestation.access_ledger.ledger_id,
            sha256=attestation.access_ledger.content_checksum,
        ),
        family_evidence_references=attestation.family_evidence_references,
    )
    return contamination.build_external_challenge_authority_resolution_v8(
        challenge_item_id="ECH-001",
        snapshot=ArtifactReference(artifact_id=request.snapshot_id, sha256=request.snapshot_sha256),
        source_manifest=ArtifactReference(
            artifact_id=request.source_manifest_id,
            sha256=request.source_manifest_sha256,
        ),
        record_ids_checksum=request.record_ids_checksum,
        task5_dependency=dependency,
        access_ledger_head=dependency.custody_reference,
        access_ledgers=(attestation.access_ledger,),
        actor_roster=roster,
    )


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("snapshot_id", "protected-evaluation-stale"),
        ("snapshot_sha256", "a" * 64),
        ("source_manifest_id", "source-manifest-stale"),
        ("source_manifest_sha256", "b" * 64),
        ("record_ids_checksum", "c" * 64),
    ),
)
def test_resolved_dataset_pin_mismatch_is_blocked(field: str, replacement: str) -> None:
    attestation = _attestation()
    baseline = _addressed_request()
    resolution = _valid_resolution(attestation, baseline)
    mutated = _addressed_request(**{field: replacement})
    result = evaluate_external_challenge_use_v8(
        attestation, mutated, authority_resolution=resolution
    )
    assert result.decision is ChallengeUseDecisionV8.BLOCK
    assert any("dataset" in item.lower() for item in (result.blockers.value or ()))


@pytest.mark.parametrize(
    ("field", "blocker_phrase"),
    (
        ("documented_training_cutoff", "documented training cutoff"),
        ("known_web_availability", "known web availability"),
        ("probes_run", "detection probes"),
    ),
)
def test_public_source_cutoff_web_and_probes_are_fail_closed_when_unknown(
    field: str, blocker_phrase: str
) -> None:
    updates = {
        "source_class": ChallengeSourceClassV8.POST_CUTOFF_PUBLIC,
        "publication_or_creation_date": _present(date(2026, 1, 2)),
        "backbone_release_date": _present(date(2025, 1, 1)),
        "documented_training_cutoff": _present(date(2026, 1, 1)),
        "known_web_availability": _present(True),
        "probes_run": _present(("PROBE-001",)),
    }
    updates[field] = _unknown(f"{field} has not been independently resolved.")
    attestation = _attestation().model_copy(update=updates)
    result = evaluate_external_challenge_use_v8(
        attestation, _request(ChallengeUsePurposeV8.GENERALIZATION)
    )
    assert result.decision is ChallengeUseDecisionV8.BLOCK
    assert any(blocker_phrase in item.lower() for item in (result.blockers.value or ()))


def test_valid_post_cutoff_structure_stays_review_required_not_qualified() -> None:
    attestation = _attestation().model_copy(
        update={
            "source_class": ChallengeSourceClassV8.POST_CUTOFF_PUBLIC,
            "publication_or_creation_date": _present(date(2026, 1, 2)),
            "backbone_release_date": _present(date(2025, 1, 1)),
            "documented_training_cutoff": _present(date(2026, 1, 1)),
            "known_web_availability": _present(True),
            "probes_run": _present(("PROBE-001",)),
        }
    )
    request = _addressed_request()
    result = evaluate_external_challenge_use_v8(
        attestation,
        request,
        authority_resolution=_valid_resolution(attestation, request),
    )
    assert result.decision is ChallengeUseDecisionV8.SCIENTIFIC_REVIEW_REQUIRED
    assert result.use_authorized is False
    assert all("cutoff" not in item.lower() for item in (result.blockers.value or ()))
    assert any("authority" in item.lower() for item in (result.blockers.value or ()))


def test_custody_event_role_must_match_attested_custodian_role() -> None:
    ledger = build_challenge_access_ledger_v8(
        challenge_item_id="ECH-001",
        events=(
            ChallengeAccessEventV8(
                event_id="ACCESS-CUSTODY-WRONG-ROLE",
                actor_id="custodian-001",
                actor_role="UNRESOLVED_ROLE",
                purpose=ChallengeAccessPurposeV8.CUSTODY,
                evidence_ref="EVIDENCE-ACCESS-001",
                occurred_at=NOW,
            ),
        ),
    )
    with pytest.raises((ValueError, ValidationError), match=r"ID and role|custody"):
        build_contamination_attestation_v8(
            challenge_item_id="ECH-001",
            source_class=ChallengeSourceClassV8.PROSPECTIVE_PRIVATE,
            publication_or_creation_date=_present(date(2026, 9, 1)),
            study_family_id="STUDY-FAMILY-9001",
            backbone_model_id="model-reviewed",
            backbone_revision="revision-reviewed",
            backbone_release_date=_unknown("No reviewed public release date is available."),
            documented_training_cutoff=_unknown("The backbone cutoff is undocumented."),
            known_web_availability=_present(False),
            text_exposure_risk=_present(ChallengeExposureRiskV8.LOW),
            exposure_assessment_evidence_refs=EVIDENCE,
            probes_run=KnowledgeValue(
                knowledge_state=KnowledgeState.ABSENT_EXPLICIT,
                evidence_ids=EVIDENCE,
                claim_scope_id="EXTERNAL-CHALLENGE:ECH-001:PROBES",
            ),
            residual_risk=_present(ChallengeExposureRiskV8.LOW),
            study_family_overlap=_present(False),
            permitted_claims=("pipeline_generalization",),
            forbidden_claims=("proof_of_no_pretraining_exposure",),
            custodian_actor_id="custodian-001",
            custodian_actor_role="EXTERNAL_CUSTODIAN",
            attester_actor_id="attester-independent-001",
            attester_actor_role="INDEPENDENT_CONTAMINATION_REVIEWER",
            access_ledger=ledger,
            family_evidence_references=(
                ArtifactReference(artifact_id="FAMILY-EVIDENCE-001", sha256="1" * 64),
            ),
            attester_attestation_ref="ATTESTATION-INDEPENDENT-001",
            created_at=NOW,
        )


def test_false_use_authorization_always_has_an_explicit_blocker() -> None:
    for purpose in ChallengeUsePurposeV8:
        result = evaluate_external_challenge_use_v8(_attestation(), _request(purpose))
        assert result.use_authorized is False
        assert result.blockers.knowledge_state is KnowledgeState.PRESENT
        assert result.blockers.value


def test_false_use_authorization_schema_rejects_absent_explicit_blockers() -> None:
    result = evaluate_external_challenge_use_v8(
        _attestation(), _request(ChallengeUsePurposeV8.GENERALIZATION)
    )
    fields = result.model_dump(mode="python", exclude={"evaluation_id", "content_checksum"})
    fields["blockers"] = KnowledgeValue[tuple[str, ...]](
        knowledge_state=KnowledgeState.ABSENT_EXPLICIT,
        evidence_ids=(result.attestation_id,),
        claim_scope_id=f"EXTERNAL-CHALLENGE-USE:{result.request_id}",
    )
    checksum = content_checksum(fields)
    with pytest.raises((ValueError, ValidationError), match=r"blocker|authorization|HOLD"):
        type(result)(
            evaluation_id=f"EXTERNAL-CHALLENGE-EVALUATION-{checksum[:20]}",
            content_checksum=checksum,
            **fields,
        )


def test_resolved_access_event_actor_role_must_match_the_external_roster() -> None:
    initial = build_challenge_access_ledger_v8(
        challenge_item_id="ECH-001",
        events=(_access(ChallengeAccessPurposeV8.CUSTODY),),
    )
    head = append_challenge_access_ledger_v8(
        initial,
        (
            ChallengeAccessEventV8(
                event_id="ACCESS-INDEPENDENT-SCORING-WRONG-ROLE",
                actor_id="scorer-independent-001",
                actor_role="UNRESOLVED_SCORER_ROLE",
                purpose=ChallengeAccessPurposeV8.INDEPENDENT_SCORING,
                evidence_ref="EVIDENCE-ACCESS-SCORING-001",
                occurred_at=NOW,
            ),
        ),
    )
    attestation = build_contamination_attestation_v8(
        challenge_item_id="ECH-001",
        source_class=ChallengeSourceClassV8.PROSPECTIVE_PRIVATE,
        publication_or_creation_date=_present(date(2026, 9, 1)),
        study_family_id="STUDY-FAMILY-9001",
        backbone_model_id="model-reviewed",
        backbone_revision="revision-reviewed",
        backbone_release_date=_unknown("No reviewed public release date is available."),
        documented_training_cutoff=_unknown("The backbone cutoff is undocumented."),
        known_web_availability=_present(False),
        text_exposure_risk=_present(ChallengeExposureRiskV8.LOW),
        exposure_assessment_evidence_refs=EVIDENCE,
        probes_run=KnowledgeValue(
            knowledge_state=KnowledgeState.ABSENT_EXPLICIT,
            evidence_ids=EVIDENCE,
            claim_scope_id="EXTERNAL-CHALLENGE:ECH-001:PROBES",
        ),
        residual_risk=_present(ChallengeExposureRiskV8.LOW),
        study_family_overlap=_present(False),
        permitted_claims=("pipeline_generalization",),
        forbidden_claims=("proof_of_no_pretraining_exposure",),
        custodian_actor_id="custodian-001",
        custodian_actor_role="EXTERNAL_CUSTODIAN",
        attester_actor_id="attester-independent-001",
        attester_actor_role="INDEPENDENT_CONTAMINATION_REVIEWER",
        access_ledger=head,
        family_evidence_references=(
            ArtifactReference(artifact_id="FAMILY-EVIDENCE-001", sha256="1" * 64),
        ),
        attester_attestation_ref="ATTESTATION-INDEPENDENT-001",
        created_at=NOW,
    )
    request = _addressed_request()
    dependency = ExternalChallengeDependency(
        review_status="SCIENTIFIC_REVIEW_REQUIRED",
        task7_contamination_attestation_reference=ArtifactReference(
            artifact_id=attestation.attestation_id,
            sha256=attestation.content_checksum,
        ),
        custody_reference=ArtifactReference(
            artifact_id=head.ledger_id,
            sha256=head.content_checksum,
        ),
        family_evidence_references=attestation.family_evidence_references,
    )
    resolution = contamination.build_external_challenge_authority_resolution_v8(
        challenge_item_id="ECH-001",
        snapshot=ArtifactReference(artifact_id=request.snapshot_id, sha256=request.snapshot_sha256),
        source_manifest=ArtifactReference(
            artifact_id=request.source_manifest_id,
            sha256=request.source_manifest_sha256,
        ),
        record_ids_checksum=request.record_ids_checksum,
        task5_dependency=dependency,
        access_ledger_head=dependency.custody_reference,
        access_ledgers=(initial, head),
        actor_roster=contamination.build_challenge_actor_roster_v8(
            challenge_item_id="ECH-001", assignments=_actor_assignments()
        ),
    )
    result = evaluate_external_challenge_use_v8(
        attestation, request, authority_resolution=resolution
    )
    assert result.decision is ChallengeUseDecisionV8.BLOCK
    assert any("actor id or role" in item.lower() for item in (result.blockers.value or ()))
