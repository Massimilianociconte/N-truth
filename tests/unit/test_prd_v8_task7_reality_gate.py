"""PRD v8 Reality Gate contracts: complete, open-world and non-self-authorizing."""

from __future__ import annotations

from datetime import UTC, datetime
from inspect import signature

import pytest
from pydantic import ValidationError

from ntruth.reality_gate.v8 import (
    SUBSTANTIVE_TRAINING_PREDICATES,
    GateDecisionV8,
    GateEvidenceArtifactKindV8,
    ReadinessDimensionV8,
    ReadinessStatusV8,
    RealityGatePredicateAssessmentV8,
    RealityGatePredicateNameV8,
    build_gate_blocker_registry_v8,
    build_gate_evidence_artifact_v8,
    build_reality_gate_assessment_v8,
    build_reality_gate_evidence_ledger_v8,
    build_reality_gate_training_target_v8,
    build_stage_gate_decision_v8,
)
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.support import ScientificReviewRequirement
from ntruth.training.custody import ArtifactReference

EXPECTED: dict[RealityGatePredicateNameV8, bool | int] = {
    name: (0 if name is RealityGatePredicateNameV8.BLOCKING_SCHEMA_GAPS else True)
    for name in SUBSTANTIVE_TRAINING_PREDICATES
}


def _evidence(name: str):
    return build_gate_evidence_artifact_v8(
        kind=GateEvidenceArtifactKindV8.REVIEW_RECORD,
        issuer_role="INDEPENDENT_SCIENTIFIC_REVIEWER",
        reviewer_ids=("reviewer-independent-001",),
        payload={"assertion": name, "result": "reviewed"},
    )


def _predicate(name: RealityGatePredicateNameV8, value: bool | int | None = None):
    evidence = _evidence(name.value)
    actual = EXPECTED[name] if value is None else value
    return (
        RealityGatePredicateAssessmentV8(
            name=name,
            value=KnowledgeValue[bool | int](
                knowledge_state=KnowledgeState.PRESENT,
                value=actual,
                evidence_ids=(evidence.artifact_id,),
                claim_scope_id=f"REALITY-GATE:{name.value}",
            ),
            expected_value=EXPECTED[name],
            reviewer_decision_refs=(evidence.artifact_id,),
        ),
        evidence,
    )


def _complete_ledger():
    pairs = tuple(_predicate(name) for name in SUBSTANTIVE_TRAINING_PREDICATES)
    return build_reality_gate_evidence_ledger_v8(
        predicate_assessments=tuple(pair[0] for pair in pairs),
        evidence_artifacts=tuple(pair[1] for pair in pairs),
    )


def _assessment_dependencies():
    base = _complete_ledger()
    snapshot_subject = ArtifactReference(artifact_id="snapshot-001", sha256="1" * 64)
    design_subject = ArtifactReference(artifact_id="design-001", sha256="2" * 64)
    snapshot = build_gate_evidence_artifact_v8(
        kind=GateEvidenceArtifactKindV8.SNAPSHOT_MANIFEST,
        issuer_role="DATA_CUSTODIAN",
        reviewer_ids=("snapshot-reviewer-001",),
        payload={
            "assertion": "snapshot",
            "result": "reviewed",
            "subject_artifact_id": snapshot_subject.artifact_id,
            "subject_sha256": snapshot_subject.sha256,
        },
    )
    design = build_gate_evidence_artifact_v8(
        kind=GateEvidenceArtifactKindV8.DESIGN_LINEAGE,
        issuer_role="DESIGN_REVIEWER",
        reviewer_ids=("design-reviewer-001",),
        payload={
            "assertion": "design-lineage",
            "result": "reviewed",
            "subject_artifact_id": design_subject.artifact_id,
            "subject_sha256": design_subject.sha256,
        },
    )
    privacy = build_gate_evidence_artifact_v8(
        kind=GateEvidenceArtifactKindV8.PRIVACY_ATTESTATION,
        issuer_role="INDEPENDENT_PRIVACY_REVIEWER",
        reviewer_ids=("privacy-reviewer-001",),
        payload={"assertion": "privacy", "result": "reviewed"},
    )
    no_corpus = build_gate_evidence_artifact_v8(
        kind=GateEvidenceArtifactKindV8.NO_CORPUS_ATTESTATION,
        issuer_role="INDEPENDENT_REPOSITORY_REVIEWER",
        reviewer_ids=("repository-reviewer-001",),
        payload={"assertion": "no-corpus", "result": "reviewed"},
    )
    policy = build_gate_evidence_artifact_v8(
        kind=GateEvidenceArtifactKindV8.POLICY_RECORD,
        issuer_role="GOVERNANCE_REVIEWER",
        reviewer_ids=("governance-reviewer-001",),
        payload={"assertion": "train-policy", "result": "reviewed"},
    )
    ledger = build_reality_gate_evidence_ledger_v8(
        predicate_assessments=base.predicate_assessments,
        evidence_artifacts=(
            *base.evidence_artifacts,
            snapshot,
            design,
            privacy,
            no_corpus,
            policy,
        ),
    )
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
    blockers = build_gate_blocker_registry_v8(
        policy=target.policy,
        unresolved_blockers=KnowledgeValue[tuple[ScientificReviewRequirement, ...]](
            knowledge_state=KnowledgeState.ABSENT_EXPLICIT,
            evidence_ids=(policy.artifact_id,),
            claim_scope_id="REALITY-GATE:BLOCKERS",
        ),
    )
    return target, ledger, blockers


@pytest.mark.parametrize("omitted", SUBSTANTIVE_TRAINING_PREDICATES)
def test_each_missing_substantive_training_predicate_fails_closed(omitted) -> None:
    pairs = tuple(
        _predicate(name) for name in SUBSTANTIVE_TRAINING_PREDICATES if name is not omitted
    )
    with pytest.raises((ValueError, ValidationError), match=r"predicate|complete|missing"):
        build_reality_gate_evidence_ledger_v8(
            predicate_assessments=tuple(pair[0] for pair in pairs),
            evidence_artifacts=tuple(pair[1] for pair in pairs),
        )


def test_blocking_schema_gaps_requires_integer_zero_not_boolean_or_one() -> None:
    expected = RealityGatePredicateNameV8.BLOCKING_SCHEMA_GAPS
    assert _predicate(expected, 0)[0].satisfied is True
    assert _predicate(expected, 1)[0].satisfied is False
    assert _predicate(expected, False)[0].satisfied is False


@pytest.mark.parametrize("name", SUBSTANTIVE_TRAINING_PREDICATES)
def test_each_unexpected_substantive_training_value_fails_closed(name) -> None:
    unexpected = 1 if name is RealityGatePredicateNameV8.BLOCKING_SCHEMA_GAPS else False
    assert _predicate(name, unexpected)[0].satisfied is False


def test_unknown_or_conflicting_predicate_is_retained_but_never_satisfied() -> None:
    evidence = _evidence("unknown-anchor")
    unknown = RealityGatePredicateAssessmentV8(
        name=RealityGatePredicateNameV8.REAL_ANCHOR_AVAILABLE,
        value=KnowledgeValue[bool | int](
            knowledge_state=KnowledgeState.UNKNOWN,
            rationale="No authorized real anchor has been registered.",
            claim_scope_id="REALITY-GATE:real_anchor_available",
        ),
        expected_value=True,
        reviewer_decision_refs=("REVIEW-real-anchor-open",),
    )
    assert unknown.satisfied is False
    assert evidence.artifact_id not in unknown.value.evidence_ids
    conflicting = unknown.model_copy(
        update={
            "value": KnowledgeValue[bool | int](
                knowledge_state=KnowledgeState.CONFLICTING,
                conflicting_values=(True, False),
                evidence_ids=(evidence.artifact_id,),
                claim_scope_id="REALITY-GATE:real_anchor_available",
            ),
            "reviewer_decision_refs": (evidence.artifact_id,),
        }
    )
    assert conflicting.satisfied is False


@pytest.mark.parametrize("payload", ({}, {"claim": None}, {"items": []}))
def test_gate_evidence_rejects_bare_empty_or_null_scientific_payloads(payload) -> None:
    with pytest.raises((ValueError, ValidationError), match=r"ambiguous|payload"):
        build_gate_evidence_artifact_v8(
            kind=GateEvidenceArtifactKindV8.REVIEW_RECORD,
            issuer_role="INDEPENDENT_SCIENTIFIC_REVIEWER",
            reviewer_ids=("reviewer-independent-001",),
            payload=payload,
        )


def test_v8_ledger_has_exact_fifteen_unique_predicates_and_closed_evidence() -> None:
    ledger = _complete_ledger()
    assert len(SUBSTANTIVE_TRAINING_PREDICATES) == 15
    assert {item.name for item in ledger.predicate_assessments} == set(
        SUBSTANTIVE_TRAINING_PREDICATES
    )
    assert ledger.all_predicates_satisfied is True
    tampered = ledger.model_dump(mode="python")
    tampered["predicate_assessments"][0]["value"]["evidence_ids"] = ("missing",)
    with pytest.raises((ValueError, ValidationError), match=r"evidence|dangling"):
        type(ledger).model_validate(tampered)
    forged_assessment = ledger.predicate_assessments[0].model_copy(
        update={"reviewer_decision_refs": ("missing-review-record",)}
    )
    with pytest.raises((ValueError, ValidationError), match=r"review|dangling"):
        build_reality_gate_evidence_ledger_v8(
            predicate_assessments=(forged_assessment, *ledger.predicate_assessments[1:]),
            evidence_artifacts=ledger.evidence_artifacts,
        )


def test_assessment_requires_all_six_dimensions_and_no_bare_blocker_list() -> None:
    target, ledger, blockers = _assessment_dependencies()
    parameters = signature(build_reality_gate_assessment_v8).parameters
    assert {"target", "evidence_ledger", "blocker_registry", "dimensions"} <= parameters.keys()
    dimensions = tuple(
        (
            dimension,
            KnowledgeValue[ReadinessStatusV8](
                knowledge_state=KnowledgeState.PRESENT,
                value=ReadinessStatusV8.READY,
                evidence_ids=(ledger.evidence_artifacts[0].artifact_id,),
                claim_scope_id=f"READINESS:{dimension.value}",
            ),
        )
        for dimension in ReadinessDimensionV8
    )
    with pytest.raises((ValueError, ValidationError), match=r"dimension|six|complete"):
        build_reality_gate_assessment_v8(
            target=target,
            evidence_ledger=ledger,
            blocker_registry=blockers,
            dimensions=dimensions[:-1],
        )
    with pytest.raises((ValueError, ValidationError), match=r"dimension|once|duplicat"):
        build_reality_gate_assessment_v8(
            target=target,
            evidence_ledger=ledger,
            blocker_registry=blockers,
            dimensions=(*dimensions[:-1], dimensions[0]),
        )


@pytest.mark.parametrize(
    "decision",
    (GateDecisionV8.REVISE, GateDecisionV8.LIMIT, GateDecisionV8.STOP),
)
def test_non_go_decisions_never_authorize_substantive_training(decision) -> None:
    target, ledger, blockers = _assessment_dependencies()
    dimensions = tuple(
        (
            dimension,
            KnowledgeValue[ReadinessStatusV8](
                knowledge_state=KnowledgeState.PRESENT,
                value=ReadinessStatusV8.READY,
                evidence_ids=(ledger.evidence_artifacts[0].artifact_id,),
                claim_scope_id=f"READINESS:{dimension.value}",
            ),
        )
        for dimension in ReadinessDimensionV8
    )
    assessment = build_reality_gate_assessment_v8(
        target=target,
        evidence_ledger=ledger,
        blocker_registry=blockers,
        dimensions=dimensions,
    )
    record = build_stage_gate_decision_v8(
        target=target,
        assessment=assessment,
        blocker_registry=blockers,
        decision=decision,
        scope="SUBSTANTIVE_TRAINING",
        conditions=KnowledgeValue(
            knowledge_state=KnowledgeState.NOT_APPLICABLE,
            rationale="No authorizing conditions exist for a non-GO decision.",
            claim_scope_id="REALITY-GATE:DECISION",
        ),
        rationale="The gate is not authorized to open.",
        decision_maker_attestation_ref="ATTESTATION-DECISION-001",
        independent_stop_attestation_ref=(
            "ATTESTATION-STOP-001" if decision is GateDecisionV8.STOP else None
        ),
        decided_at=datetime(2026, 8, 8, 12, 0, tzinfo=UTC),
    )
    assert record.authorizes_substantive_training is False


def test_gate_inputs_never_accept_a_caller_supplied_authorized_boolean() -> None:
    module = __import__("ntruth.reality_gate.v8", fromlist=["RealityGateAssessmentV8"])
    for model_name in (
        "RealityGateEvidenceLedgerV8",
        "RealityGateAssessmentV8",
        "StageGateDecisionRecordV8",
    ):
        assert "authorized" not in getattr(module, model_name).model_fields
