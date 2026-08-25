"""PRD v9 §0.8 Reality Gate: complete flag set, HOLD by default, composed over v8."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from ntruth.reality_gate.v8 import (
    SUBSTANTIVE_TRAINING_PREDICATES,
    GateEvidenceArtifactKindV8,
    GateEvidenceArtifactV8,
    ReadinessDimensionV8,
    ReadinessStatusV8,
    RealityGatePredicateAssessmentV8,
    RealityGatePredicateNameV8,
    build_gate_blocker_registry_v8,
    build_gate_evidence_artifact_v8,
    build_reality_gate_assessment_v8,
    build_reality_gate_evidence_ledger_v8,
    build_reality_gate_training_target_v8,
)
from ntruth.reality_gate.v9 import (
    SHARED_PREDICATE_NAMES_V9,
    SUBSTANTIVE_TRAINING_PREDICATES_V9,
    GateStateV9,
    RealityGateEvidenceLedgerV9,
    RealityGatePredicateAssessmentV9,
    RealityGatePredicateNameV9,
    build_default_evidence_ledger_v9,
    build_reality_gate_evidence_ledger_v9,
    compose_reality_gate_v9,
    resolve_ledger_predicates_v9,
)
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.support import ScientificReviewRequirement
from ntruth.training.custody import ArtifactReference

# Verbatim PRD v9 §0.8 flag list; the ledger must never drift from the PRD.
PRD_V9_SECTION_0_8_FLAGS: tuple[str, ...] = (
    "canonical_schema_registry_frozen",
    "all_normative_examples_schema_valid",
    "factor_role_and_contrast_type_reviewed",
    "assignment_anchored_derivation_theory_reviewed",
    "material_lineage_clauses_reviewed",
    "contrast_support_contract_reviewed",
    "support_profile_policy_reviewed",
    "profile_assumption_set_reviewed",
    "human_second_review_completed",
    "blocking_schema_or_theory_gaps",
    "real_anchor_available",
    "license_and_data_use_scope_verified",
    "train_dev_test_lineage_frozen",
    "reference_stability_report_available",
    "human_only_baseline_executed",
    "human_ai_team_protocol_frozen",
    "real_baseline_executed",
    "synthetic_factory_human_calibrated",
    "critical_error_and_calibration_contract_frozen",
    "end_to_end_metric_contract_frozen",
    "external_challenge_custody_and_lifecycle_ready",
    "ingestion_threat_model_and_adversarial_tests_passed",
    "requirements_traceability_complete_for_release_scope",
)


def _expected_value(name: RealityGatePredicateNameV9) -> bool | int:
    return 0 if name is RealityGatePredicateNameV9.BLOCKING_SCHEMA_OR_THEORY_GAPS else True


def _v9_evidence(name: str) -> GateEvidenceArtifactV8:
    return build_gate_evidence_artifact_v8(
        kind=GateEvidenceArtifactKindV8.REVIEW_RECORD,
        issuer_role="INDEPENDENT_SCIENTIFIC_REVIEWER",
        reviewer_ids=(f"reviewer-{name}",),
        payload={"assertion": name, "result": "reviewed"},
    )


def _resolved_v9_ledger() -> RealityGateEvidenceLedgerV9:
    resolutions = tuple(
        (name, _expected_value(name), _v9_evidence(name.value))
        for name in SUBSTANTIVE_TRAINING_PREDICATES_V9
    )
    return resolve_ledger_predicates_v9(build_default_evidence_ledger_v9(), resolutions)


def _assessment_dependencies() -> tuple[Any, Any, Any]:
    """Build a GO-ready pinned v8 target/ledger/blocker triple (see v8 gate tests)."""

    def v8_predicate(name: RealityGatePredicateNameV8):
        expected = 0 if name is RealityGatePredicateNameV8.BLOCKING_SCHEMA_GAPS else True
        evidence = build_gate_evidence_artifact_v8(
            kind=GateEvidenceArtifactKindV8.REVIEW_RECORD,
            issuer_role="INDEPENDENT_SCIENTIFIC_REVIEWER",
            reviewer_ids=(f"v8-reviewer-{name.value}",),
            payload={"assertion": name.value, "result": "reviewed"},
        )
        return (
            RealityGatePredicateAssessmentV8(
                name=name,
                value=KnowledgeValue[bool | int](
                    knowledge_state=KnowledgeState.PRESENT,
                    value=expected,
                    evidence_ids=(evidence.artifact_id,),
                    claim_scope_id=f"REALITY-GATE:{name.value}",
                ),
                expected_value=expected,
                reviewer_decision_refs=(evidence.artifact_id,),
            ),
            evidence,
        )

    pairs = tuple(v8_predicate(name) for name in SUBSTANTIVE_TRAINING_PREDICATES)
    ledger = build_reality_gate_evidence_ledger_v8(
        predicate_assessments=tuple(pair[0] for pair in pairs),
        evidence_artifacts=tuple(pair[1] for pair in pairs),
    )
    snapshot_subject = ArtifactReference(artifact_id="snapshot-001", sha256="1" * 64)
    design_subject = ArtifactReference(artifact_id="design-001", sha256="2" * 64)

    def reviewed_subject_artifact(kind: GateEvidenceArtifactKindV8, subject: ArtifactReference):
        return build_gate_evidence_artifact_v8(
            kind=kind,
            issuer_role=(
                "DATA_CUSTODIAN"
                if kind is GateEvidenceArtifactKindV8.SNAPSHOT_MANIFEST
                else "DESIGN_REVIEWER"
            ),
            reviewer_ids=(f"{kind.value.lower()}-reviewer-001",),
            payload={
                "assertion": kind.value,
                "result": "reviewed",
                "subject_artifact_id": subject.artifact_id,
                "subject_sha256": subject.sha256,
            },
        )

    snapshot = reviewed_subject_artifact(
        GateEvidenceArtifactKindV8.SNAPSHOT_MANIFEST, snapshot_subject
    )
    design = reviewed_subject_artifact(GateEvidenceArtifactKindV8.DESIGN_LINEAGE, design_subject)

    def simple_attestation(kind: GateEvidenceArtifactKindV8, reviewer: str):
        return build_gate_evidence_artifact_v8(
            kind=kind,
            issuer_role="GOVERNANCE_REVIEWER",
            reviewer_ids=(reviewer,),
            payload={"assertion": kind.value, "result": "attested"},
        )

    privacy = simple_attestation(
        GateEvidenceArtifactKindV8.PRIVACY_ATTESTATION, "privacy-reviewer-001"
    )
    no_corpus = simple_attestation(
        GateEvidenceArtifactKindV8.NO_CORPUS_ATTESTATION, "repository-reviewer-001"
    )
    policy = simple_attestation(GateEvidenceArtifactKindV8.POLICY_RECORD, "governance-reviewer-001")
    ledger = build_reality_gate_evidence_ledger_v8(
        predicate_assessments=ledger.predicate_assessments,
        evidence_artifacts=(
            *ledger.evidence_artifacts,
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


def _v8_assessment(product_value_status: ReadinessStatusV8 = ReadinessStatusV8.READY):
    target, ledger, blockers = _assessment_dependencies()
    dimensions = tuple(
        (
            dimension,
            KnowledgeValue[ReadinessStatusV8](
                knowledge_state=KnowledgeState.PRESENT,
                value=(
                    product_value_status
                    if dimension is ReadinessDimensionV8.PRODUCT_VALUE
                    else ReadinessStatusV8.READY
                ),
                evidence_ids=(ledger.evidence_artifacts[0].artifact_id,),
                claim_scope_id=f"READINESS:{dimension.value}",
            ),
        )
        for dimension in ReadinessDimensionV8
    )
    return build_reality_gate_assessment_v8(
        target=target,
        evidence_ledger=ledger,
        blocker_registry=blockers,
        dimensions=dimensions,
    )


def test_v9_flag_set_matches_prd_section_0_8_verbatim() -> None:
    assert len(SUBSTANTIVE_TRAINING_PREDICATES_V9) == len(PRD_V9_SECTION_0_8_FLAGS) == 23
    assert (
        tuple(name.value for name in SUBSTANTIVE_TRAINING_PREDICATES_V9) == PRD_V9_SECTION_0_8_FLAGS
    )


def test_shared_predicates_are_exactly_the_verbatim_v8_overlap() -> None:
    assert len(SUBSTANTIVE_TRAINING_PREDICATES) == 15
    assert {name.value for name in SHARED_PREDICATE_NAMES_V9} == {
        "human_second_review_completed",
        "real_anchor_available",
        "reference_stability_report_available",
        "real_baseline_executed",
        "synthetic_factory_human_calibrated",
        "end_to_end_metric_contract_frozen",
    }


@pytest.mark.parametrize("omitted", SUBSTANTIVE_TRAINING_PREDICATES_V9)
def test_each_missing_v9_flag_fails_closed(omitted: RealityGatePredicateNameV9) -> None:
    default = build_default_evidence_ledger_v9()
    partial = tuple(item for item in default.predicate_assessments if item.name is not omitted)
    assert len(partial) == 22
    with pytest.raises((ValueError, ValidationError), match=r"23"):
        build_reality_gate_evidence_ledger_v9(
            predicate_assessments=partial,
            evidence_artifacts=(),
        )


def test_default_ledger_holds_every_flag_and_registers_no_evidence() -> None:
    ledger = build_default_evidence_ledger_v9()
    assert ledger.evidence_artifacts == ()
    assert ledger.all_predicates_satisfied is False
    assert ledger.unsatisfied_predicate_names() == SUBSTANTIVE_TRAINING_PREDICATES_V9


@pytest.mark.parametrize("name", SUBSTANTIVE_TRAINING_PREDICATES_V9)
def test_each_flag_satisfies_only_with_strict_expected_value(
    name: RealityGatePredicateNameV9,
) -> None:
    expected = _expected_value(name)
    wrong = 1 if expected == 0 else False
    good = resolve_ledger_predicates_v9(
        build_default_evidence_ledger_v9(), ((name, expected, _v9_evidence(f"good-{name.value}")),)
    )
    bad = resolve_ledger_predicates_v9(
        build_default_evidence_ledger_v9(), ((name, wrong, _v9_evidence(f"bad-{name.value}")),)
    )
    good_item = next(item for item in good.predicate_assessments if item.name is name)
    bad_item = next(item for item in bad.predicate_assessments if item.name is name)
    assert good_item.satisfied is True
    assert bad_item.satisfied is False
    assert good.all_predicates_satisfied is False
    assert bad.all_predicates_satisfied is False


def test_blocking_gap_flag_never_satisfied_by_boolean_false_or_integer_one() -> None:
    name = RealityGatePredicateNameV9.BLOCKING_SCHEMA_OR_THEORY_GAPS
    for wrong in (False, 1):
        ledger = resolve_ledger_predicates_v9(
            build_default_evidence_ledger_v9(), ((name, wrong, _v9_evidence(f"gap-{wrong}")),)
        )
        item = next(a for a in ledger.predicate_assessments if a.name is name)
        assert item.satisfied is False
        assert ledger.all_predicates_satisfied is False


def test_present_state_requires_registered_evidence_and_unique_reviewers() -> None:
    name = RealityGatePredicateNameV9.REAL_ANCHOR_AVAILABLE
    evidence = _v9_evidence(name.value)
    with pytest.raises(
        (ValueError, ValidationError), match=r"PRESENT.*registered|registered.*evidence"
    ):
        RealityGatePredicateAssessmentV9(
            name=name,
            expected_value=True,
            value=KnowledgeValue[bool | int](
                knowledge_state=KnowledgeState.PRESENT,
                value=True,
                evidence_ids=(evidence.artifact_id,),
            ),
            reviewer_decision_refs=(),
        )
    with pytest.raises((ValueError, ValidationError), match=r"PRESENT"):
        RealityGatePredicateAssessmentV9(
            name=name,
            expected_value=True,
            value=KnowledgeValue[bool | int](
                knowledge_state=KnowledgeState.PRESENT,
                value=True,
                evidence_ids=(),
            ),
            reviewer_decision_refs=(evidence.artifact_id,),
        )
    with pytest.raises((ValueError, ValidationError), match=r"unique"):
        RealityGatePredicateAssessmentV9(
            name=name,
            expected_value=True,
            value=KnowledgeValue[bool | int](
                knowledge_state=KnowledgeState.PRESENT,
                value=True,
                evidence_ids=(evidence.artifact_id,),
            ),
            reviewer_decision_refs=(evidence.artifact_id, evidence.artifact_id),
        )


def test_state_transition_happens_only_through_content_addressed_evidence() -> None:
    default = build_default_evidence_ledger_v9()
    name = RealityGatePredicateNameV9.HUMAN_AI_TEAM_PROTOCOL_FROZEN
    evidence = _v9_evidence(name.value)
    forged = RealityGatePredicateAssessmentV9(
        name=name,
        expected_value=True,
        value=KnowledgeValue[bool | int](
            knowledge_state=KnowledgeState.PRESENT,
            value=True,
            evidence_ids=("GATE-EVIDENCE-FORGED",),
        ),
        reviewer_decision_refs=("GATE-EVIDENCE-FORGED",),
    )
    with pytest.raises((ValueError, ValidationError), match=r"dangling"):
        build_reality_gate_evidence_ledger_v9(
            predicate_assessments=tuple(
                forged if item.name is name else item for item in default.predicate_assessments
            ),
            evidence_artifacts=(),
        )
    resolved = resolve_ledger_predicates_v9(default, ((name, True, evidence),))
    assert resolved.unsatisfied_predicate_names() == tuple(
        n for n in SUBSTANTIVE_TRAINING_PREDICATES_V9 if n is not name
    )
    assert default.all_predicates_satisfied is False
    assert resolved.ledger_id != default.ledger_id
    tampered = resolved.model_dump(mode="python")
    tampered["predicate_assessments"][0]["value"]["evidence_ids"] = ("missing",)
    with pytest.raises((ValueError, ValidationError), match=r"dangling|mismatch"):
        RealityGateEvidenceLedgerV9.model_validate(tampered)


def test_composition_with_default_ledger_stays_hold_even_on_go_ready_v8_baseline() -> None:
    composition = compose_reality_gate_v9(
        v8_assessment=_v8_assessment(),
        v9_evidence_ledger=build_default_evidence_ledger_v9(),
    )
    assert composition.effective_state is GateStateV9.HOLD
    assert composition.predicates_satisfied is False
    assert composition.authorizes_substantive_training is False


def test_full_evidence_composition_is_ready_for_review_but_never_authorizes_training() -> None:
    composition = compose_reality_gate_v9(
        v8_assessment=_v8_assessment(),
        v9_evidence_ledger=_resolved_v9_ledger(),
    )
    assert composition.effective_state is GateStateV9.READY_FOR_SCIENTIFIC_REVIEW
    assert composition.predicates_satisfied is True
    assert composition.authorizes_substantive_training is False


def test_composition_stays_hold_when_only_the_v9_side_is_resolved() -> None:
    composition = compose_reality_gate_v9(
        v8_assessment=_v8_assessment(ReadinessStatusV8.BLOCKED),
        v9_evidence_ledger=_resolved_v9_ledger(),
    )
    assert composition.v8_assessment.ready_for_go is False
    assert composition.effective_state is GateStateV9.HOLD
    assert composition.authorizes_substantive_training is False


def test_composition_rejects_contradicted_shared_predicate() -> None:
    shared = RealityGatePredicateNameV9.HUMAN_SECOND_REVIEW_COMPLETED
    contradicted = resolve_ledger_predicates_v9(
        build_default_evidence_ledger_v9(),
        ((shared, False, _v9_evidence("contradiction")),),
    )
    with pytest.raises((ValueError, ValidationError), match=r"conflicts"):
        compose_reality_gate_v9(v8_assessment=_v8_assessment(), v9_evidence_ledger=contradicted)


def test_composition_is_content_addressed_and_tamper_evident() -> None:
    composition = compose_reality_gate_v9(
        v8_assessment=_v8_assessment(),
        v9_evidence_ledger=build_default_evidence_ledger_v9(),
    )
    assert composition.authorizes_substantive_training is False
    tampered = composition.model_dump(mode="python")
    tampered["v9_evidence_ledger"]["ledger_id"] = "REALITY-GATE-V9-LEDGER-TAMPERED"
    with pytest.raises((ValueError, ValidationError), match=r"mismatch|checksum"):
        type(composition).model_validate(tampered)
