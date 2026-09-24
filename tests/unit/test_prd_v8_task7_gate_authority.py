"""Reality Gate v8 target, blocker, trust and production-HOLD boundary."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import ntruth.training.mlx_runtime as runtime
from ntruth.reality_gate.v8 import (
    SUBSTANTIVE_TRAINING_PREDICATES,
    DetachedGateSignatureV8,
    GateDecisionV8,
    GateEvidenceArtifactKindV8,
    GateTrustUsageV8,
    ReadinessDimensionV8,
    ReadinessStatusV8,
    RealityGatePredicateAssessmentV8,
    RealityGatePredicateNameV8,
    RealityGateTrainingPinTupleV8,
    TrustedGateSignerV8,
    build_gate_blocker_registry_v8,
    build_gate_evidence_artifact_v8,
    build_gate_trust_registry_v8,
    build_reality_gate_assessment_v8,
    build_reality_gate_evidence_ledger_v8,
    build_reality_gate_training_target_v8,
    build_stage_gate_decision_v8,
    evaluate_training_authorization_v8,
    reconcile_training_authorization_pins_v8,
)
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.support import ScientificReviewRequirement
from ntruth.training.custody import ArtifactReference

NOW = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)


def _artifact(
    kind: GateEvidenceArtifactKindV8,
    label: str,
    *,
    subject: ArtifactReference | None = None,
):
    payload = {"assertion": label, "outcome": "reviewed"}
    if subject is not None:
        payload.update(
            {
                "subject_artifact_id": subject.artifact_id,
                "subject_sha256": subject.sha256,
            }
        )
    return build_gate_evidence_artifact_v8(
        kind=kind,
        issuer_role="INDEPENDENT_REVIEWER",
        reviewer_ids=("reviewer-independent-001",),
        payload=payload,
    )


def _target_and_artifacts():
    snapshot_subject = ArtifactReference(artifact_id="snapshot-001", sha256="1" * 64)
    design_subject = ArtifactReference(artifact_id="design-lineage-001", sha256="2" * 64)
    snapshot = _artifact(
        GateEvidenceArtifactKindV8.SNAPSHOT_MANIFEST,
        "snapshot",
        subject=snapshot_subject,
    )
    design = _artifact(
        GateEvidenceArtifactKindV8.DESIGN_LINEAGE,
        "design-lineage",
        subject=design_subject,
    )
    privacy = _artifact(GateEvidenceArtifactKindV8.PRIVACY_ATTESTATION, "privacy")
    no_corpus = _artifact(GateEvidenceArtifactKindV8.NO_CORPUS_ATTESTATION, "no-corpus")
    policy = _artifact(GateEvidenceArtifactKindV8.POLICY_RECORD, "train-policy")
    target = build_reality_gate_training_target_v8(
        snapshot=snapshot_subject,
        snapshot_review=ArtifactReference(
            artifact_id=snapshot.artifact_id, sha256=snapshot.content_checksum
        ),
        design_lineage=design_subject,
        design_lineage_review=ArtifactReference(
            artifact_id=design.artifact_id, sha256=design.content_checksum
        ),
        privacy_attestation=ArtifactReference(
            artifact_id=privacy.artifact_id, sha256=privacy.content_checksum
        ),
        no_corpus_attestation=ArtifactReference(
            artifact_id=no_corpus.artifact_id, sha256=no_corpus.content_checksum
        ),
        policy=ArtifactReference(artifact_id=policy.artifact_id, sha256=policy.content_checksum),
    )
    return target, (snapshot, design, privacy, no_corpus, policy)


def _complete_components():
    target, fixed_artifacts = _target_and_artifacts()
    predicate_artifacts = tuple(
        _artifact(GateEvidenceArtifactKindV8.REVIEW_RECORD, name.value)
        for name in SUBSTANTIVE_TRAINING_PREDICATES
    )
    predicates = tuple(
        RealityGatePredicateAssessmentV8(
            name=name,
            value=KnowledgeValue[bool | int](
                knowledge_state=KnowledgeState.PRESENT,
                value=(0 if name is RealityGatePredicateNameV8.BLOCKING_SCHEMA_GAPS else True),
                evidence_ids=(predicate_artifacts[index].artifact_id,),
                claim_scope_id=f"REALITY-GATE:{name.value}",
            ),
            expected_value=(0 if name is RealityGatePredicateNameV8.BLOCKING_SCHEMA_GAPS else True),
            reviewer_decision_refs=(predicate_artifacts[index].artifact_id,),
        )
        for index, name in enumerate(SUBSTANTIVE_TRAINING_PREDICATES)
    )
    ledger = build_reality_gate_evidence_ledger_v8(
        predicate_assessments=predicates,
        evidence_artifacts=(*predicate_artifacts, *fixed_artifacts),
    )
    blocker_registry = build_gate_blocker_registry_v8(
        policy=target.policy,
        unresolved_blockers=KnowledgeValue[tuple[ScientificReviewRequirement, ...]](
            knowledge_state=KnowledgeState.ABSENT_EXPLICIT,
            evidence_ids=(fixed_artifacts[-1].artifact_id,),
            claim_scope_id="REALITY-GATE:BLOCKERS",
        ),
    )
    dimensions = tuple(
        (
            dimension,
            KnowledgeValue[ReadinessStatusV8](
                knowledge_state=KnowledgeState.PRESENT,
                value=ReadinessStatusV8.READY,
                evidence_ids=(predicate_artifacts[0].artifact_id,),
                claim_scope_id=f"READINESS:{dimension.value}",
            ),
        )
        for dimension in ReadinessDimensionV8
    )
    assessment = build_reality_gate_assessment_v8(
        target=target,
        evidence_ledger=ledger,
        blocker_registry=blocker_registry,
        dimensions=dimensions,
    )
    decision = build_stage_gate_decision_v8(
        target=target,
        assessment=assessment,
        blocker_registry=blocker_registry,
        decision=GateDecisionV8.GO,
        scope="TRAIN",
        conditions=KnowledgeValue[tuple[str, ...]](
            knowledge_state=KnowledgeState.ABSENT_EXPLICIT,
            evidence_ids=(fixed_artifacts[-1].artifact_id,),
            claim_scope_id="REALITY-GATE:DECISION-CONDITIONS",
        ),
        rationale="All contract predicates are structurally satisfied.",
        decision_maker_attestation_ref="DECISION-MAKER-ATTESTATION-001",
        independent_stop_attestation_ref=None,
        decided_at=NOW,
    )
    return target, ledger, blocker_registry, assessment, decision


def test_target_requires_addressed_privacy_no_corpus_design_snapshot_and_policy() -> None:
    target, _ = _target_and_artifacts()
    assert target.purpose == "TRAIN"
    assert target.snapshot.artifact_id == "snapshot-001"
    assert target.design_lineage.artifact_id == "design-lineage-001"
    assert target.privacy_attestation.artifact_id.startswith("GATE-EVIDENCE-")
    payload = target.model_dump(mode="python")
    payload["privacy_attestation"]["sha256"] = "f" * 64
    with pytest.raises((ValueError, ValidationError), match=r"checksum|target"):
        type(target).model_validate(payload)


def test_assessment_closes_target_evidence_policy_blockers_and_dimensions() -> None:
    target, ledger, blocker_registry, assessment, _ = _complete_components()
    assert assessment.target == target
    assert assessment.evidence_ledger == ledger
    assert assessment.blocker_registry == blocker_registry
    assert assessment.ready_for_go is True
    payload = assessment.model_dump(mode="python")
    payload["blocker_registry"]["unresolved_blockers"] = {
        "knowledge_state": "PRESENT",
        "value": [
            {
                "issue_id": "SRR-TEST",
                "rationale": "A scientific blocker remains unresolved.",
            }
        ],
        "evidence_ids": [ledger.evidence_artifacts[0].artifact_id],
        "claim_scope_id": "REALITY-GATE:BLOCKERS",
    }
    with pytest.raises((ValueError, ValidationError), match=r"checksum|blocker"):
        type(assessment).model_validate(payload)


@pytest.mark.parametrize("reference_name", ("snapshot", "design_lineage"))
def test_assessment_rejects_unresolved_snapshot_or_design_artifact(reference_name) -> None:
    target, ledger, blocker_registry, assessment, _ = _complete_components()
    reference = getattr(target, f"{reference_name}_review")
    missing_ledger = build_reality_gate_evidence_ledger_v8(
        predicate_assessments=ledger.predicate_assessments,
        evidence_artifacts=tuple(
            artifact
            for artifact in ledger.evidence_artifacts
            if artifact.artifact_id != reference.artifact_id
        ),
    )
    dimensions = tuple((item.dimension, item.status) for item in assessment.dimensions)
    with pytest.raises((ValueError, ValidationError), match=r"target|resolved|ledger"):
        build_reality_gate_assessment_v8(
            target=target,
            evidence_ledger=missing_ledger,
            blocker_registry=blocker_registry,
            dimensions=dimensions,
        )


def test_go_decision_is_pinned_to_exact_target_assessment_registry_and_policy() -> None:
    target, _, blocker_registry, assessment, decision = _complete_components()
    assert decision.target_ref == target.target_id
    assert decision.assessment_ref == assessment.assessment_id
    assert decision.blocker_registry_ref == blocker_registry.registry_id
    payload = decision.model_dump(mode="python")
    payload["assessment_sha256"] = "e" * 64
    with pytest.raises((ValueError, ValidationError), match=r"checksum|decision"):
        type(decision).model_validate(payload)


@pytest.mark.parametrize(
    "decision_value",
    (GateDecisionV8.REVISE, GateDecisionV8.LIMIT, GateDecisionV8.STOP),
)
def test_non_go_never_becomes_training_authorization(decision_value) -> None:
    target, _, blocker_registry, assessment, _ = _complete_components()
    decision = build_stage_gate_decision_v8(
        target=target,
        assessment=assessment,
        blocker_registry=blocker_registry,
        decision=decision_value,
        scope="TRAIN",
        conditions=KnowledgeValue[tuple[str, ...]](
            knowledge_state=KnowledgeState.NOT_APPLICABLE,
            rationale="A non-GO decision cannot carry authorizing conditions.",
            claim_scope_id="REALITY-GATE:DECISION-CONDITIONS",
        ),
        rationale="The gate remains closed.",
        decision_maker_attestation_ref="DECISION-MAKER-ATTESTATION-001",
        independent_stop_attestation_ref=(
            "INDEPENDENT-STOP-ATTESTATION-001" if decision_value is GateDecisionV8.STOP else None
        ),
        decided_at=NOW,
    )
    assert decision.authorizes_substantive_training is False


def test_detached_signature_and_registry_are_external_but_conformance_never_authorizes() -> None:
    target, ledger, blocker_registry, assessment, decision = _complete_components()
    signer = TrustedGateSignerV8(
        signer_id="conformance-signer-001",
        key_id="conformance-key-001",
        public_key_sha256="5" * 64,
        usage=GateTrustUsageV8.CONFORMANCE_ONLY,
    )
    registry = build_gate_trust_registry_v8(
        policy=target.policy,
        signers=(signer,),
        registry_issuer_attestation_ref="TRUST-REGISTRY-ATTESTATION-001",
    )
    signature = DetachedGateSignatureV8(
        signer_id=signer.signer_id,
        key_id=signer.key_id,
        algorithm="CONFORMANCE_DIGEST_ONLY",
        signed_decision_id=decision.decision_id,
        signed_payload_sha256=decision.content_checksum,
        signature="conformance-not-a-production-signature",
    )
    result = evaluate_training_authorization_v8(
        target=target,
        evidence_ledger=ledger,
        blocker_registry=blocker_registry,
        assessment=assessment,
        decision=decision,
        trust_registry=registry,
        detached_signature=signature,
    )
    assert result.authorized_for_training is False
    assert result.status == "SCIENTIFIC_REVIEW_REQUIRED"
    assert result.evidence_ledger_ref == ledger.ledger_id
    assert result.blocker_registry_ref == blocker_registry.registry_id
    assert result.policy_ref == target.policy.artifact_id
    assert any("production trust" in item.lower() for item in result.blockers)


def test_self_authored_production_signer_untrusted_signer_and_stale_target_all_hold() -> None:
    target, ledger, blocker_registry, assessment, decision = _complete_components()
    production_signer = TrustedGateSignerV8(
        signer_id="caller-authored-production-signer",
        key_id="caller-authored-key",
        public_key_sha256="6" * 64,
        usage=GateTrustUsageV8.PRODUCTION,
    )
    registry = build_gate_trust_registry_v8(
        policy=target.policy,
        signers=(production_signer,),
        registry_issuer_attestation_ref="CALLER-SELF-ATTESTATION",
    )
    base_signature = DetachedGateSignatureV8(
        signer_id=production_signer.signer_id,
        key_id=production_signer.key_id,
        algorithm="CALLER_ASSERTED",
        signed_decision_id=decision.decision_id,
        signed_payload_sha256=decision.content_checksum,
        signature="caller-authored-signature-without-external-verification",
    )
    self_authored = evaluate_training_authorization_v8(
        target=target,
        evidence_ledger=ledger,
        blocker_registry=blocker_registry,
        assessment=assessment,
        decision=decision,
        trust_registry=registry,
        detached_signature=base_signature,
    )
    assert self_authored.authorized_for_training is False
    assert any("not configured" in item for item in self_authored.blockers)

    untrusted = evaluate_training_authorization_v8(
        target=target,
        evidence_ledger=ledger,
        blocker_registry=blocker_registry,
        assessment=assessment,
        decision=decision,
        trust_registry=registry,
        detached_signature=base_signature.model_copy(
            update={"signer_id": "not-in-registry", "key_id": "unknown-key"}
        ),
    )
    assert untrusted.authorized_for_training is False
    assert any("not in the pinned trust registry" in item for item in untrusted.blockers)

    stale_target = build_reality_gate_training_target_v8(
        snapshot=ArtifactReference(artifact_id="snapshot-stale", sha256="7" * 64),
        snapshot_review=target.snapshot_review,
        design_lineage=target.design_lineage,
        design_lineage_review=target.design_lineage_review,
        privacy_attestation=target.privacy_attestation,
        no_corpus_attestation=target.no_corpus_attestation,
        policy=target.policy,
    )
    stale = evaluate_training_authorization_v8(
        target=stale_target,
        evidence_ledger=ledger,
        blocker_registry=blocker_registry,
        assessment=assessment,
        decision=decision,
        trust_registry=registry,
        detached_signature=base_signature,
    )
    assert stale.authorized_for_training is False
    assert any("target" in item for item in stale.blockers)


def test_complete_authorization_pin_tuple_rejects_every_resume_mutation() -> None:
    target, ledger, blocker_registry, assessment, decision = _complete_components()
    signer = TrustedGateSignerV8(
        signer_id="conformance-signer-001",
        key_id="conformance-key-001",
        public_key_sha256="5" * 64,
        usage=GateTrustUsageV8.CONFORMANCE_ONLY,
    )
    trust = build_gate_trust_registry_v8(
        policy=target.policy,
        signers=(signer,),
        registry_issuer_attestation_ref="TRUST-REGISTRY-ATTESTATION-001",
    )
    signature = DetachedGateSignatureV8(
        signer_id=signer.signer_id,
        key_id=signer.key_id,
        algorithm="CONFORMANCE_DIGEST_ONLY",
        signed_decision_id=decision.decision_id,
        signed_payload_sha256=decision.content_checksum,
        signature="conformance-not-a-production-signature",
    )
    authorization = evaluate_training_authorization_v8(
        target=target,
        evidence_ledger=ledger,
        blocker_registry=blocker_registry,
        assessment=assessment,
        decision=decision,
        trust_registry=trust,
        detached_signature=signature,
    )
    pins = RealityGateTrainingPinTupleV8.from_components(
        authorization=authorization,
        target=target,
        evidence_ledger=ledger,
        blocker_registry=blocker_registry,
        assessment=assessment,
        decision=decision,
        trust_registry=trust,
        detached_signature=signature,
    )
    state = pins.state_payload()
    reconcile_training_authorization_pins_v8(state, pins)
    for key in tuple(state):
        changed = dict(state)
        changed[key] = "f" * 64 if key.endswith("sha256") else f"mutated-{key}"
        with pytest.raises(ValueError, match=r"changed|pin"):
            reconcile_training_authorization_pins_v8(changed, pins)


def test_v7_true_values_cannot_be_parsed_as_a_v8_authoritative_target_or_assessment() -> None:
    legacy = {
        "schema_stable_on_real_cases": True,
        "no_blocking_schema_gaps": True,
        "real_anchor_available": True,
        "licence_scope_verified": True,
        "protected_split_frozen": True,
        "human_second_review_completed": True,
        "decisive_fields_reviewed": True,
        "real_baseline_executed": True,
        "synthetic_factory_human_calibrated": True,
    }
    with pytest.raises((TypeError, ValueError, ValidationError)):
        build_reality_gate_training_target_v8(**legacy)


@dataclass(frozen=True)
class _CanonicalGate:
    resolution: object

    def resolve_training_authorization(self, _request: object) -> object:
        return self.resolution


def _canonical_runtime_resolution(*, usage: GateTrustUsageV8 = GateTrustUsageV8.CONFORMANCE_ONLY):
    target, ledger, blockers, assessment, decision = _complete_components()
    signer = TrustedGateSignerV8(
        signer_id="runtime-signer-001",
        key_id="runtime-key-001",
        public_key_sha256="5" * 64,
        usage=usage,
    )
    trust = build_gate_trust_registry_v8(
        policy=target.policy,
        signers=(signer,),
        registry_issuer_attestation_ref="RUNTIME-TRUST-REGISTRY-ATTESTATION-001",
    )
    signature = DetachedGateSignatureV8(
        signer_id=signer.signer_id,
        key_id=signer.key_id,
        algorithm="UNVERIFIED_TEST_SIGNATURE",
        signed_decision_id=decision.decision_id,
        signed_payload_sha256=decision.content_checksum,
        signature="not-a-production-signature",
    )
    authorization = evaluate_training_authorization_v8(
        target=target,
        evidence_ledger=ledger,
        blocker_registry=blockers,
        assessment=assessment,
        decision=decision,
        trust_registry=trust,
        detached_signature=signature,
    )
    pins = RealityGateTrainingPinTupleV8.from_components(
        authorization=authorization,
        target=target,
        evidence_ledger=ledger,
        blocker_registry=blockers,
        assessment=assessment,
        decision=decision,
        trust_registry=trust,
        detached_signature=signature,
    )
    resolution_type = getattr(runtime, "CanonicalRealityGateAuthorizationResolutionV8", None)
    assert resolution_type is not None, "runtime must consume canonical Task 7 components"
    return target, resolution_type(
        target=target,
        evidence_ledger=ledger,
        blocker_registry=blockers,
        assessment=assessment,
        decision=decision,
        trust_registry=trust,
        detached_signature=signature,
        declared_pins=pins,
    )


@pytest.mark.parametrize("pin_field", tuple(RealityGateTrainingPinTupleV8.model_fields))
def test_runtime_rejects_every_mutated_canonical_gate_pin_before_payload_model_or_subprocess(
    pin_field: str, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    target, resolution = _canonical_runtime_resolution()
    pins = resolution.declared_pins
    value = "f" * 64 if pin_field.endswith("sha256") else f"mutated-{pin_field}"
    mutated_pins = pins.model_copy(update={pin_field: value})
    resolution = replace(resolution, declared_pins=mutated_pins)
    calls = {"payload": 0, "model": 0, "subprocess": 0}
    monkeypatch.setattr(
        runtime,
        "resolve_training_lineage_inputs",
        lambda **_kwargs: SimpleNamespace(state_payload=lambda: {}),
    )
    monkeypatch.setattr(
        runtime,
        "read_training_snapshot_envelope",
        lambda *_a, **_k: {
            "snapshot_id": target.snapshot.artifact_id,
            "snapshot_sha256": target.snapshot.sha256,
            "manifest_sha256": "9" * 64,
        },
    )
    monkeypatch.setattr(
        runtime,
        "validate_mlx_dataset",
        lambda *_a, **_k: calls.__setitem__("payload", calls["payload"] + 1),
    )
    monkeypatch.setattr(
        runtime,
        "_model_path",
        lambda *_a, **_k: calls.__setitem__("model", calls["model"] + 1),
    )
    monkeypatch.setattr(
        runtime,
        "_stream_command",
        lambda *_a, **_k: calls.__setitem__("subprocess", calls["subprocess"] + 1),
    )

    with pytest.raises(runtime.MLXPipelineError, match=r"pin|canonical|mismatch|changed"):
        runtime.run_training(
            tmp_path / "profile.json",
            tmp_path,
            tmp_path / "data",
            tmp_path / "run",
            seed=13,
            reality_gate=_CanonicalGate(resolution),  # type: ignore[arg-type]
            design_lineage_pins=None,  # type: ignore[arg-type]
            design_lineage_artifact_path=None,  # type: ignore[arg-type]
            protected_source_manifest_path=None,  # type: ignore[arg-type]
        )
    assert calls == {"payload": 0, "model": 0, "subprocess": 0}


@pytest.mark.parametrize(
    "case",
    ("conformance", "self_authored_production", "unsigned", "stale_target"),
)
def test_canonical_runtime_has_no_repository_local_positive_authority(case: str) -> None:
    usage = (
        GateTrustUsageV8.PRODUCTION
        if case == "self_authored_production"
        else GateTrustUsageV8.CONFORMANCE_ONLY
    )
    target, resolution = _canonical_runtime_resolution(usage=usage)
    if case == "unsigned":
        resolution = replace(resolution, detached_signature=None)
    request = runtime.TrainingRealityGateV8Request(
        snapshot_id=("stale-snapshot" if case == "stale_target" else target.snapshot.artifact_id),
        snapshot_sha256=target.snapshot.sha256,
    )
    with pytest.raises(
        runtime.MLXPipelineError,
        match=r"HOLD|SCIENTIFIC_REVIEW_REQUIRED|canonical|stale|signature",
    ):
        runtime.verify_training_reality_gate_v8(
            _CanonicalGate(resolution),  # type: ignore[arg-type]
            request,
        )
