"""PRD v9 §0.8 Reality Gate composed over the pinned PRD v8 gate.

The v9 gate never relaxes the v8 contracts: it adds the complete 23-predicate
flag set of PRD v9 §0.8 as a second, independent fail-closed ledger and
composes it with a fully validated ``RealityGateAssessmentV8``.  Every flag is
false (HOLD) until content-addressed evidence with unique reviewers is
registered; even a fully ready composition remains an inspectable record and
never an authorization capability.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Self

from pydantic import Field, field_validator, model_validator

from ntruth.reality_gate.v8 import (
    SUBSTANTIVE_TRAINING_PREDICATES,
    GateEvidenceArtifactKindV8,
    GateEvidenceArtifactV8,
    PredicateScalar,
    ReadinessDimensionV8,
    ReadinessStatusV8,
    RealityGateAssessmentV8,
    RealityGatePredicateAssessmentV8,
    RealityGatePredicateNameV8,
    Sha256,
    build_gate_blocker_registry_v8,
    build_gate_evidence_artifact_v8,
    build_reality_gate_assessment_v8,
    build_reality_gate_evidence_ledger_v8,
    build_reality_gate_training_target_v8,
)
from ntruth.schemas.core import content_checksum
from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.support import ScientificReviewRequirement
from ntruth.training.custody import ArtifactReference

LEDGER_PREDICATE_COUNT_V9 = 23


class RealityGatePredicateNameV9(StrEnum):
    CANONICAL_SCHEMA_REGISTRY_FROZEN = "canonical_schema_registry_frozen"
    ALL_NORMATIVE_EXAMPLES_SCHEMA_VALID = "all_normative_examples_schema_valid"
    FACTOR_ROLE_AND_CONTRAST_TYPE_REVIEWED = "factor_role_and_contrast_type_reviewed"
    ASSIGNMENT_ANCHORED_DERIVATION_THEORY_REVIEWED = (
        "assignment_anchored_derivation_theory_reviewed"
    )
    MATERIAL_LINEAGE_CLAUSES_REVIEWED = "material_lineage_clauses_reviewed"
    CONTRAST_SUPPORT_CONTRACT_REVIEWED = "contrast_support_contract_reviewed"
    SUPPORT_PROFILE_POLICY_REVIEWED = "support_profile_policy_reviewed"
    PROFILE_ASSUMPTION_SET_REVIEWED = "profile_assumption_set_reviewed"
    HUMAN_SECOND_REVIEW_COMPLETED = "human_second_review_completed"
    BLOCKING_SCHEMA_OR_THEORY_GAPS = "blocking_schema_or_theory_gaps"
    REAL_ANCHOR_AVAILABLE = "real_anchor_available"
    LICENSE_AND_DATA_USE_SCOPE_VERIFIED = "license_and_data_use_scope_verified"
    TRAIN_DEV_TEST_LINEAGE_FROZEN = "train_dev_test_lineage_frozen"
    REFERENCE_STABILITY_REPORT_AVAILABLE = "reference_stability_report_available"
    HUMAN_ONLY_BASELINE_EXECUTED = "human_only_baseline_executed"
    HUMAN_AI_TEAM_PROTOCOL_FROZEN = "human_ai_team_protocol_frozen"
    REAL_BASELINE_EXECUTED = "real_baseline_executed"
    SYNTHETIC_FACTORY_HUMAN_CALIBRATED = "synthetic_factory_human_calibrated"
    CRITICAL_ERROR_AND_CALIBRATION_CONTRACT_FROZEN = (
        "critical_error_and_calibration_contract_frozen"
    )
    END_TO_END_METRIC_CONTRACT_FROZEN = "end_to_end_metric_contract_frozen"
    EXTERNAL_CHALLENGE_CUSTODY_AND_LIFECYCLE_READY = (
        "external_challenge_custody_and_lifecycle_ready"
    )
    INGESTION_THREAT_MODEL_AND_ADVERSARIAL_TESTS_PASSED = (
        "ingestion_threat_model_and_adversarial_tests_passed"
    )
    REQUIREMENTS_TRACEABILITY_COMPLETE_FOR_RELEASE_SCOPE = (
        "requirements_traceability_complete_for_release_scope"
    )


SUBSTANTIVE_TRAINING_PREDICATES_V9: tuple[RealityGatePredicateNameV9, ...] = tuple(
    RealityGatePredicateNameV9
)

_EXPECTED_VALUES_V9: dict[RealityGatePredicateNameV9, bool | int] = {
    name: (0 if name is RealityGatePredicateNameV9.BLOCKING_SCHEMA_OR_THEORY_GAPS else True)
    for name in SUBSTANTIVE_TRAINING_PREDICATES_V9
}

_V8_NAMES_BY_VALUE: dict[str, RealityGatePredicateNameV8] = {
    member.value: member for member in RealityGatePredicateNameV8
}

SHARED_PREDICATE_NAMES_V9: tuple[RealityGatePredicateNameV9, ...] = tuple(
    name for name in SUBSTANTIVE_TRAINING_PREDICATES_V9 if name.value in _V8_NAMES_BY_VALUE
)


class RealityGatePredicateAssessmentV9(KernelModel):
    """One §0.8 flag; PRESENT is admissible only with registered evidence."""

    name: RealityGatePredicateNameV9
    value: KnowledgeValue[PredicateScalar]
    expected_value: PredicateScalar
    reviewer_decision_refs: tuple[NonBlankStr, ...] = ()

    @field_validator("expected_value", mode="before")
    @classmethod
    def _strict_expected(cls, value: object) -> object:
        if type(value) not in {bool, int}:
            raise ValueError("Reality Gate expected value must be a strict bool or integer")
        return value

    @model_validator(mode="after")
    def _canonical_expectation_and_evidence_gated_presence(self) -> Self:
        canonical = _EXPECTED_VALUES_V9[self.name]
        if type(self.expected_value) is not type(canonical) or self.expected_value != canonical:
            raise ValueError(f"unexpected canonical value for {self.name.value}")
        refs = self.reviewer_decision_refs
        if len(set(refs)) != len(refs):
            raise ValueError("predicate reviewer decision refs must be unique")
        if self.value.knowledge_state is KnowledgeState.PRESENT and (
            not refs or not self.value.evidence_ids
        ):
            raise ValueError(
                f"predicate {self.name.value} may be PRESENT only with registered "
                "evidence artifacts and reviewer decisions"
            )
        return self

    @property
    def satisfied(self) -> bool:
        actual = self.value.value
        expected = self.expected_value
        return (
            self.value.knowledge_state is KnowledgeState.PRESENT
            and type(actual) is type(expected)
            and actual == expected
        )


class RealityGateEvidenceLedgerV9(KernelModel):
    """Complete, closed and content-addressed PRD v9 §0.8 evidence ledger."""

    ledger_id: NonBlankStr
    content_checksum: Sha256
    predicate_assessments: tuple[RealityGatePredicateAssessmentV9, ...] = Field(
        min_length=LEDGER_PREDICATE_COUNT_V9, max_length=LEDGER_PREDICATE_COUNT_V9
    )
    evidence_artifacts: tuple[GateEvidenceArtifactV8, ...] = ()

    @property
    def all_predicates_satisfied(self) -> bool:
        return all(item.satisfied for item in self.predicate_assessments)

    def unsatisfied_predicate_names(self) -> tuple[RealityGatePredicateNameV9, ...]:
        return tuple(item.name for item in self.predicate_assessments if not item.satisfied)

    @model_validator(mode="after")
    def _complete_closed_and_addressed(self) -> Self:
        names = tuple(item.name for item in self.predicate_assessments)
        if len(set(names)) != len(names) or set(names) != set(SUBSTANTIVE_TRAINING_PREDICATES_V9):
            raise ValueError("Reality Gate predicate set is incomplete or duplicated")
        artifact_ids = tuple(item.artifact_id for item in self.evidence_artifacts)
        if len(set(artifact_ids)) != len(artifact_ids):
            raise ValueError("Reality Gate evidence artifact IDs must be unique")
        known = set(artifact_ids)
        for assessment in self.predicate_assessments:
            if not set(assessment.value.evidence_ids).issubset(known):
                raise ValueError(
                    f"Reality Gate predicate {assessment.name.value} has dangling evidence"
                )
            if not set(assessment.reviewer_decision_refs).issubset(known):
                raise ValueError(
                    f"Reality Gate predicate {assessment.name.value} has dangling review refs"
                )
        expected = content_checksum(
            self.model_dump(mode="json", exclude={"ledger_id", "content_checksum"})
        )
        if self.content_checksum != expected:
            raise ValueError("Reality Gate evidence ledger checksum mismatch")
        if self.ledger_id != f"REALITY-GATE-V9-LEDGER-{expected[:20]}":
            raise ValueError("Reality Gate evidence ledger ID mismatch")
        return self


def build_reality_gate_evidence_ledger_v9(
    *,
    predicate_assessments: tuple[RealityGatePredicateAssessmentV9, ...],
    evidence_artifacts: tuple[GateEvidenceArtifactV8, ...],
) -> RealityGateEvidenceLedgerV9:
    fields: dict[str, Any] = {
        "predicate_assessments": predicate_assessments,
        "evidence_artifacts": evidence_artifacts,
    }
    draft = RealityGateEvidenceLedgerV9.model_construct(
        ledger_id="REALITY-GATE-V9-LEDGER-PENDING",
        content_checksum="0" * 64,
        **fields,
    )
    checksum = content_checksum(
        draft.model_dump(mode="json", exclude={"ledger_id", "content_checksum"})
    )
    return RealityGateEvidenceLedgerV9(
        ledger_id=f"REALITY-GATE-V9-LEDGER-{checksum[:20]}",
        content_checksum=checksum,
        **fields,
    )


def build_default_evidence_ledger_v9() -> RealityGateEvidenceLedgerV9:
    """Return the deterministic fail-closed ledger where every flag is unresolved."""

    assessments = tuple(
        RealityGatePredicateAssessmentV9(
            name=name,
            value=KnowledgeValue[PredicateScalar](
                knowledge_state=KnowledgeState.UNKNOWN,
                rationale="awaiting registered evidence (PRD v9 section 0.8)",
                claim_scope_id=f"REALITY-GATE-V9:{name.value}",
            ),
            expected_value=_EXPECTED_VALUES_V9[name],
            reviewer_decision_refs=(),
        )
        for name in SUBSTANTIVE_TRAINING_PREDICATES_V9
    )
    return build_reality_gate_evidence_ledger_v9(
        predicate_assessments=assessments,
        evidence_artifacts=(),
    )


def resolve_ledger_predicates_v9(
    ledger: RealityGateEvidenceLedgerV9,
    resolutions: tuple[tuple[RealityGatePredicateNameV9, bool | int, GateEvidenceArtifactV8], ...],
) -> RealityGateEvidenceLedgerV9:
    """Return a new immutable ledger with the given predicates resolved by evidence.

    The input ledger is never mutated.  A resolution records what the evidence
    asserts even when it contradicts the expected value; an asserted-false flag
    simply keeps the gate closed.
    """

    replacements: dict[RealityGatePredicateNameV9, RealityGatePredicateAssessmentV9] = {}
    artifacts: dict[str, GateEvidenceArtifactV8] = {
        item.artifact_id: item for item in ledger.evidence_artifacts
    }
    for name, value, evidence in resolutions:
        artifacts.setdefault(evidence.artifact_id, evidence)
        replacements[name] = RealityGatePredicateAssessmentV9(
            name=name,
            value=KnowledgeValue[PredicateScalar](
                knowledge_state=KnowledgeState.PRESENT,
                value=value,
                evidence_ids=(evidence.artifact_id,),
                claim_scope_id=f"REALITY-GATE-V9:{name.value}",
            ),
            expected_value=_EXPECTED_VALUES_V9[name],
            reviewer_decision_refs=(evidence.artifact_id,),
        )
    updated = tuple(replacements.get(item.name, item) for item in ledger.predicate_assessments)
    return build_reality_gate_evidence_ledger_v9(
        predicate_assessments=updated,
        evidence_artifacts=tuple(artifacts.values()),
    )


class GateStateV9(StrEnum):
    HOLD = "HOLD"
    READY_FOR_SCIENTIFIC_REVIEW = "READY_FOR_SCIENTIFIC_REVIEW"


class RealityGateCompositionV9(KernelModel):
    """v9 gate state composed from a pinned v8 assessment plus the v9 ledger.

    The composition embeds both components so every integrity validator of the
    pinned contracts re-runs on any serialization boundary.  Readiness here is
    still only evidence: production authorization additionally requires an
    independently configured trust verifier which this repository does not
    possess.
    """

    composition_id: NonBlankStr
    content_checksum: Sha256
    v8_assessment: RealityGateAssessmentV8
    v9_evidence_ledger: RealityGateEvidenceLedgerV9

    @property
    def predicates_satisfied(self) -> bool:
        return (
            self.v8_assessment.predicates_satisfied
            and self.v9_evidence_ledger.all_predicates_satisfied
        )

    @property
    def effective_state(self) -> GateStateV9:
        if self.v8_assessment.ready_for_go and self.v9_evidence_ledger.all_predicates_satisfied:
            return GateStateV9.READY_FOR_SCIENTIFIC_REVIEW
        return GateStateV9.HOLD

    @property
    def authorizes_substantive_training(self) -> bool:
        """A serialized composition is evidence, never an authorization capability."""

        return False

    @model_validator(mode="after")
    def _shared_predicates_consistent_and_addressed(self) -> Self:
        v8_by_name = {
            item.name.value: item
            for item in self.v8_assessment.evidence_ledger.predicate_assessments
        }
        v9_by_name = {
            item.name.value: item for item in self.v9_evidence_ledger.predicate_assessments
        }
        for shared in SHARED_PREDICATE_NAMES_V9:
            v8_item = v8_by_name[shared.value]
            v9_item = v9_by_name[shared.value]
            both_present = (
                v8_item.value.knowledge_state is KnowledgeState.PRESENT
                and v9_item.value.knowledge_state is KnowledgeState.PRESENT
            )
            if both_present and (
                type(v8_item.value.value) is not type(v9_item.value.value)
                or v8_item.value.value != v9_item.value.value
            ):
                raise ValueError(
                    f"shared Reality Gate predicate {shared.value} conflicts between "
                    "the pinned v8 assessment and the v9 ledger"
                )
        expected = content_checksum(
            self.model_dump(mode="json", exclude={"composition_id", "content_checksum"})
        )
        if self.content_checksum != expected:
            raise ValueError("Reality Gate v9 composition checksum mismatch")
        if self.composition_id != f"REALITY-GATE-V9-COMPOSITION-{expected[:20]}":
            raise ValueError("Reality Gate v9 composition ID mismatch")
        return self


def compose_reality_gate_v9(
    *,
    v8_assessment: RealityGateAssessmentV8,
    v9_evidence_ledger: RealityGateEvidenceLedgerV9,
) -> RealityGateCompositionV9:
    fields: dict[str, Any] = {
        "v8_assessment": v8_assessment,
        "v9_evidence_ledger": v9_evidence_ledger,
    }
    draft = RealityGateCompositionV9.model_construct(
        composition_id="REALITY-GATE-V9-COMPOSITION-PENDING",
        content_checksum="0" * 64,
        **fields,
    )
    checksum = content_checksum(
        draft.model_dump(mode="json", exclude={"composition_id", "content_checksum"})
    )
    return RealityGateCompositionV9(
        composition_id=f"REALITY-GATE-V9-COMPOSITION-{checksum[:20]}",
        content_checksum=checksum,
        **fields,
    )


def _pending_artifact(
    kind: GateEvidenceArtifactKindV8,
    issuer_role: str,
    payload_extra: dict[str, Any] | None = None,
) -> GateEvidenceArtifactV8:
    return build_gate_evidence_artifact_v8(
        kind=kind,
        issuer_role=issuer_role,
        reviewer_ids=("pending-canonical-custodian",),
        payload={"assertion": kind.value, "result": "pending", **(payload_extra or {})},
    )


def build_default_hold_assessment_v8() -> RealityGateAssessmentV8:
    """Assessment v8 pinnato e deterministico con ogni readiness non risolta.

    Il target referenzia artifact segnaposto auto-consistenti (i checksum
    combaciano con il ledger per costruzione): sono identita di contratto che
    dimostrano la forma del gate, non evidenze reali. La decisione resta HOLD
    finche il flusso di governance non registra evidenze autentiche.
    """

    snapshot = ArtifactReference(artifact_id="pending-snapshot-manifest", sha256="0" * 64)
    design_lineage = ArtifactReference(artifact_id="pending-design-lineage", sha256="0" * 64)
    snapshot_review = _pending_artifact(
        GateEvidenceArtifactKindV8.SNAPSHOT_MANIFEST,
        "DATA_CUSTODIAN",
        {"subject_artifact_id": snapshot.artifact_id, "subject_sha256": snapshot.sha256},
    )
    design_review = _pending_artifact(
        GateEvidenceArtifactKindV8.DESIGN_LINEAGE,
        "DESIGN_REVIEWER",
        {
            "subject_artifact_id": design_lineage.artifact_id,
            "subject_sha256": design_lineage.sha256,
        },
    )
    privacy = _pending_artifact(GateEvidenceArtifactKindV8.PRIVACY_ATTESTATION, "DATA_CUSTODIAN")
    no_corpus = _pending_artifact(
        GateEvidenceArtifactKindV8.NO_CORPUS_ATTESTATION, "DATA_CUSTODIAN"
    )
    policy = _pending_artifact(GateEvidenceArtifactKindV8.POLICY_RECORD, "GOVERNANCE_REVIEWER")

    def reference(artifact: GateEvidenceArtifactV8) -> ArtifactReference:
        return ArtifactReference(artifact_id=artifact.artifact_id, sha256=artifact.content_checksum)

    target = build_reality_gate_training_target_v8(
        snapshot=snapshot,
        snapshot_review=reference(snapshot_review),
        design_lineage=design_lineage,
        design_lineage_review=reference(design_review),
        privacy_attestation=reference(privacy),
        no_corpus_attestation=reference(no_corpus),
        policy=reference(policy),
    )
    assessments = tuple(
        RealityGatePredicateAssessmentV8(
            name=name,
            value=KnowledgeValue[bool | int](
                knowledge_state=KnowledgeState.UNKNOWN,
                rationale="awaiting registered evidence",
                claim_scope_id=f"REALITY-GATE:{name.value}",
            ),
            expected_value=0 if name is RealityGatePredicateNameV8.BLOCKING_SCHEMA_GAPS else True,
            # Il ref punta al policy record pending: e la decisione di
            # governance registrata che mantiene il predicato non risolto.
            reviewer_decision_refs=(policy.artifact_id,),
        )
        for name in SUBSTANTIVE_TRAINING_PREDICATES
    )
    ledger = build_reality_gate_evidence_ledger_v8(
        predicate_assessments=assessments,
        evidence_artifacts=(snapshot_review, design_review, privacy, no_corpus, policy),
    )
    blockers = build_gate_blocker_registry_v8(
        policy=reference(policy),
        unresolved_blockers=KnowledgeValue[tuple[ScientificReviewRequirement, ...]](
            knowledge_state=KnowledgeState.UNKNOWN,
            rationale="scientific review register contains open blockers",
            claim_scope_id="REALITY-GATE:unresolved-blockers",
        ),
    )
    dimensions = tuple(
        (
            dimension,
            KnowledgeValue[ReadinessStatusV8](
                knowledge_state=KnowledgeState.UNKNOWN,
                rationale="awaiting registered evidence",
                claim_scope_id=f"REALITY-GATE:{dimension.value}",
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


def compose_default_hold_gate_v9() -> RealityGateCompositionV9:
    """Composizione HOLD canonica: assessment v8 deterministico + ledger v9 di default.

    Esposta a CLI/API come stato ispezionabile e content-addressed; non e una
    autorizzazione e non modifica alcun gate esistente.
    """

    return compose_reality_gate_v9(
        v8_assessment=build_default_hold_assessment_v8(),
        v9_evidence_ledger=build_default_evidence_ledger_v9(),
    )


__all__ = [
    "LEDGER_PREDICATE_COUNT_V9",
    "SHARED_PREDICATE_NAMES_V9",
    "SUBSTANTIVE_TRAINING_PREDICATES_V9",
    "GateStateV9",
    "RealityGateCompositionV9",
    "RealityGateEvidenceLedgerV9",
    "RealityGatePredicateAssessmentV9",
    "RealityGatePredicateNameV9",
    "build_default_evidence_ledger_v9",
    "build_default_hold_assessment_v8",
    "build_reality_gate_evidence_ledger_v9",
    "compose_default_hold_gate_v9",
    "compose_reality_gate_v9",
    "resolve_ledger_predicates_v9",
]
