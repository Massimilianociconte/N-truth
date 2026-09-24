"""Authoritative PRD v8 Reality Gate data contracts.

These models make readiness evidence and decisions inspectable and
content-addressed.  A decision record is deliberately not an authorization
capability: production authorization additionally requires an independently
configured trust verifier, which this repository does not currently possess.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import Field, JsonValue, StrictBool, StrictInt, field_validator, model_validator

from ntruth.schemas.core import content_checksum
from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.knowledge import (
    KnowledgeState,
    KnowledgeValue,
    ensure_unambiguous_scientific_payload,
)
from ntruth.schemas.support import ScientificReviewRequirement
from ntruth.training.custody import ArtifactReference

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
PredicateScalar = StrictBool | StrictInt


class RealityGatePredicateNameV8(StrEnum):
    SCHEMA_STABLE_ON_REAL_CASES = "schema_stable_on_real_cases"
    CORE_SEMANTIC_KERNEL_REVIEWED = "core_semantic_kernel_reviewed"
    DERIVATION_THEORY_REVIEWED = "derivation_theory_reviewed"
    PROFILE_PREDICATE_CLOSURE_REVIEWED = "profile_predicate_closure_reviewed"
    HUMAN_SECOND_REVIEW_COMPLETED = "human_second_review_completed"
    BLOCKING_SCHEMA_GAPS = "blocking_schema_gaps"
    REAL_ANCHOR_AVAILABLE = "real_anchor_available"
    LICENSE_SCOPE_VERIFIED = "license_scope_verified"
    TRAIN_DEV_TEST_SPLIT_FROZEN = "train_dev_test_split_frozen"
    DECISIVE_PREDICATES_REVIEWED = "decisive_predicates_reviewed"
    REFERENCE_STABILITY_REPORT_AVAILABLE = "reference_stability_report_available"
    REAL_BASELINE_EXECUTED = "real_baseline_executed"
    SYNTHETIC_FACTORY_HUMAN_CALIBRATED = "synthetic_factory_human_calibrated"
    END_TO_END_METRIC_CONTRACT_FROZEN = "end_to_end_metric_contract_frozen"
    EXTERNAL_CHALLENGE_CONTAMINATION_PROTOCOL_READY = (
        "external_challenge_contamination_protocol_ready"
    )


SUBSTANTIVE_TRAINING_PREDICATES: tuple[RealityGatePredicateNameV8, ...] = tuple(
    RealityGatePredicateNameV8
)
_EXPECTED_VALUES: dict[RealityGatePredicateNameV8, bool | int] = {
    name: (0 if name is RealityGatePredicateNameV8.BLOCKING_SCHEMA_GAPS else True)
    for name in SUBSTANTIVE_TRAINING_PREDICATES
}


class GateEvidenceArtifactKindV8(StrEnum):
    REVIEW_RECORD = "REVIEW_RECORD"
    ATTESTATION = "ATTESTATION"
    SNAPSHOT_MANIFEST = "SNAPSHOT_MANIFEST"
    DESIGN_LINEAGE = "DESIGN_LINEAGE"
    POLICY_RECORD = "POLICY_RECORD"
    PRIVACY_ATTESTATION = "PRIVACY_ATTESTATION"
    NO_CORPUS_ATTESTATION = "NO_CORPUS_ATTESTATION"


class GateEvidenceArtifactV8(KernelModel):
    artifact_id: NonBlankStr
    content_checksum: Sha256
    kind: GateEvidenceArtifactKindV8
    issuer_role: NonBlankStr
    reviewer_ids: tuple[NonBlankStr, ...] = Field(min_length=1)
    payload: dict[NonBlankStr, JsonValue]

    @model_validator(mode="after")
    def _addressed(self) -> Self:
        if len(set(self.reviewer_ids)) != len(self.reviewer_ids):
            raise ValueError("gate evidence reviewer IDs must be unique")
        ensure_unambiguous_scientific_payload(self.payload)
        expected = content_checksum(
            self.model_dump(mode="json", exclude={"artifact_id", "content_checksum"})
        )
        if self.content_checksum != expected:
            raise ValueError("gate evidence artifact checksum mismatch")
        if self.artifact_id != f"GATE-EVIDENCE-{expected[:20]}":
            raise ValueError("gate evidence artifact ID mismatch")
        return self


def build_gate_evidence_artifact_v8(
    *,
    kind: GateEvidenceArtifactKindV8,
    issuer_role: str,
    reviewer_ids: tuple[str, ...],
    payload: dict[str, JsonValue],
) -> GateEvidenceArtifactV8:
    fields: dict[str, Any] = {
        "kind": kind,
        "issuer_role": issuer_role,
        "reviewer_ids": reviewer_ids,
        "payload": payload,
    }
    draft = GateEvidenceArtifactV8.model_construct(
        artifact_id="GATE-EVIDENCE-PENDING",
        content_checksum="0" * 64,
        **fields,
    )
    checksum = content_checksum(
        draft.model_dump(mode="json", exclude={"artifact_id", "content_checksum"})
    )
    return GateEvidenceArtifactV8(
        artifact_id=f"GATE-EVIDENCE-{checksum[:20]}",
        content_checksum=checksum,
        **fields,
    )


class RealityGateTrainingTargetV8(KernelModel):
    """Exact TRAIN target; raw hashes are references, never predicate truth."""

    target_id: NonBlankStr
    content_checksum: Sha256
    purpose: Literal["TRAIN"] = "TRAIN"
    snapshot: ArtifactReference
    snapshot_review: ArtifactReference
    design_lineage: ArtifactReference
    design_lineage_review: ArtifactReference
    privacy_attestation: ArtifactReference
    no_corpus_attestation: ArtifactReference
    policy: ArtifactReference

    @model_validator(mode="after")
    def _addressed(self) -> Self:
        references = (
            self.snapshot,
            self.snapshot_review,
            self.design_lineage,
            self.design_lineage_review,
            self.privacy_attestation,
            self.no_corpus_attestation,
            self.policy,
        )
        identifiers = tuple(item.artifact_id for item in references)
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("Reality Gate target references must have distinct artifact IDs")
        expected = content_checksum(
            self.model_dump(mode="json", exclude={"target_id", "content_checksum"})
        )
        if self.content_checksum != expected:
            raise ValueError("Reality Gate training target checksum mismatch")
        if self.target_id != f"REALITY-GATE-TARGET-{expected[:20]}":
            raise ValueError("Reality Gate training target ID mismatch")
        return self


def build_reality_gate_training_target_v8(
    *,
    snapshot: ArtifactReference,
    snapshot_review: ArtifactReference,
    design_lineage: ArtifactReference,
    design_lineage_review: ArtifactReference,
    privacy_attestation: ArtifactReference,
    no_corpus_attestation: ArtifactReference,
    policy: ArtifactReference,
) -> RealityGateTrainingTargetV8:
    fields: dict[str, Any] = {
        "purpose": "TRAIN",
        "snapshot": snapshot,
        "snapshot_review": snapshot_review,
        "design_lineage": design_lineage,
        "design_lineage_review": design_lineage_review,
        "privacy_attestation": privacy_attestation,
        "no_corpus_attestation": no_corpus_attestation,
        "policy": policy,
    }
    draft = RealityGateTrainingTargetV8.model_construct(
        target_id="REALITY-GATE-TARGET-PENDING",
        content_checksum="0" * 64,
        **fields,
    )
    checksum = content_checksum(
        draft.model_dump(mode="json", exclude={"target_id", "content_checksum"})
    )
    return RealityGateTrainingTargetV8(
        target_id=f"REALITY-GATE-TARGET-{checksum[:20]}",
        content_checksum=checksum,
        **fields,
    )


class GateBlockerRegistryV8(KernelModel):
    registry_id: NonBlankStr
    content_checksum: Sha256
    policy: ArtifactReference
    unresolved_blockers: KnowledgeValue[tuple[ScientificReviewRequirement, ...]]

    @property
    def has_open_blockers(self) -> bool:
        return self.unresolved_blockers.knowledge_state is not KnowledgeState.ABSENT_EXPLICIT

    @model_validator(mode="after")
    def _addressed(self) -> Self:
        expected = content_checksum(
            self.model_dump(mode="json", exclude={"registry_id", "content_checksum"})
        )
        if self.content_checksum != expected:
            raise ValueError("Reality Gate blocker registry checksum mismatch")
        if self.registry_id != f"REALITY-GATE-BLOCKERS-{expected[:20]}":
            raise ValueError("Reality Gate blocker registry ID mismatch")
        return self


def build_gate_blocker_registry_v8(
    *,
    policy: ArtifactReference,
    unresolved_blockers: KnowledgeValue[tuple[ScientificReviewRequirement, ...]],
) -> GateBlockerRegistryV8:
    fields: dict[str, Any] = {
        "policy": policy,
        "unresolved_blockers": unresolved_blockers,
    }
    draft = GateBlockerRegistryV8.model_construct(
        registry_id="REALITY-GATE-BLOCKERS-PENDING",
        content_checksum="0" * 64,
        **fields,
    )
    checksum = content_checksum(
        draft.model_dump(mode="json", exclude={"registry_id", "content_checksum"})
    )
    return GateBlockerRegistryV8(
        registry_id=f"REALITY-GATE-BLOCKERS-{checksum[:20]}",
        content_checksum=checksum,
        **fields,
    )


class RealityGatePredicateAssessmentV8(KernelModel):
    name: RealityGatePredicateNameV8
    value: KnowledgeValue[PredicateScalar]
    expected_value: PredicateScalar
    reviewer_decision_refs: tuple[NonBlankStr, ...] = Field(min_length=1)

    @field_validator("expected_value", mode="before")
    @classmethod
    def _strict_expected(cls, value: object) -> object:
        if type(value) not in {bool, int}:
            raise ValueError("Reality Gate expected value must be a strict bool or integer")
        return value

    @model_validator(mode="after")
    def _canonical_expectation(self) -> Self:
        canonical = _EXPECTED_VALUES[self.name]
        if type(self.expected_value) is not type(canonical) or self.expected_value != canonical:
            raise ValueError(f"unexpected canonical value for {self.name.value}")
        if len(set(self.reviewer_decision_refs)) != len(self.reviewer_decision_refs):
            raise ValueError("predicate reviewer decision refs must be unique")
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


class RealityGateEvidenceLedgerV8(KernelModel):
    ledger_id: NonBlankStr
    content_checksum: Sha256
    predicate_assessments: tuple[RealityGatePredicateAssessmentV8, ...] = Field(
        min_length=15, max_length=15
    )
    evidence_artifacts: tuple[GateEvidenceArtifactV8, ...] = Field(min_length=1)

    @property
    def all_predicates_satisfied(self) -> bool:
        return all(item.satisfied for item in self.predicate_assessments)

    @model_validator(mode="after")
    def _complete_closed_and_addressed(self) -> Self:
        names = tuple(item.name for item in self.predicate_assessments)
        if len(set(names)) != len(names) or set(names) != set(SUBSTANTIVE_TRAINING_PREDICATES):
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
        if self.ledger_id != f"REALITY-GATE-LEDGER-{expected[:20]}":
            raise ValueError("Reality Gate evidence ledger ID mismatch")
        return self


def build_reality_gate_evidence_ledger_v8(
    *,
    predicate_assessments: tuple[RealityGatePredicateAssessmentV8, ...],
    evidence_artifacts: tuple[GateEvidenceArtifactV8, ...],
) -> RealityGateEvidenceLedgerV8:
    fields: dict[str, Any] = {
        "predicate_assessments": predicate_assessments,
        "evidence_artifacts": evidence_artifacts,
    }
    draft = RealityGateEvidenceLedgerV8.model_construct(
        ledger_id="REALITY-GATE-LEDGER-PENDING",
        content_checksum="0" * 64,
        **fields,
    )
    checksum = content_checksum(
        draft.model_dump(mode="json", exclude={"ledger_id", "content_checksum"})
    )
    return RealityGateEvidenceLedgerV8(
        ledger_id=f"REALITY-GATE-LEDGER-{checksum[:20]}",
        content_checksum=checksum,
        **fields,
    )


class ReadinessDimensionV8(StrEnum):
    ENGINEERING = "ENGINEERING"
    SEMANTIC_THEORY = "SEMANTIC_THEORY"
    DATA = "DATA"
    REFERENCE_STABILITY = "REFERENCE_STABILITY"
    PRODUCT_VALUE = "PRODUCT_VALUE"
    SCIENTIFIC_VALIDATION = "SCIENTIFIC_VALIDATION"


class ReadinessStatusV8(StrEnum):
    READY = "READY"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"
    NOT_STARTED = "NOT_STARTED"
    SCIENTIFIC_REVIEW_REQUIRED = "SCIENTIFIC_REVIEW_REQUIRED"


class ReadinessDimensionAssessmentV8(KernelModel):
    dimension: ReadinessDimensionV8
    status: KnowledgeValue[ReadinessStatusV8]


class RealityGateAssessmentV8(KernelModel):
    assessment_id: NonBlankStr
    content_checksum: Sha256
    target: RealityGateTrainingTargetV8
    evidence_ledger: RealityGateEvidenceLedgerV8
    blocker_registry: GateBlockerRegistryV8
    dimensions: tuple[ReadinessDimensionAssessmentV8, ...] = Field(min_length=6, max_length=6)

    @property
    def predicates_satisfied(self) -> bool:
        return self.evidence_ledger.all_predicates_satisfied

    @property
    def ready_for_go(self) -> bool:
        return (
            self.predicates_satisfied
            and not self.blocker_registry.has_open_blockers
            and all(
                item.status.knowledge_state is KnowledgeState.PRESENT
                and item.status.value is ReadinessStatusV8.READY
                for item in self.dimensions
            )
        )

    @model_validator(mode="after")
    def _complete_and_addressed(self) -> Self:
        dimensions = tuple(item.dimension for item in self.dimensions)
        if len(set(dimensions)) != len(dimensions) or set(dimensions) != set(ReadinessDimensionV8):
            raise ValueError("Reality Gate requires all six readiness dimensions exactly once")
        known_evidence = {item.artifact_id for item in self.evidence_ledger.evidence_artifacts}
        artifacts = {item.artifact_id: item for item in self.evidence_ledger.evidence_artifacts}
        required_target_artifacts = (
            (
                self.target.snapshot_review,
                GateEvidenceArtifactKindV8.SNAPSHOT_MANIFEST,
                self.target.snapshot,
            ),
            (
                self.target.design_lineage_review,
                GateEvidenceArtifactKindV8.DESIGN_LINEAGE,
                self.target.design_lineage,
            ),
            (
                self.target.privacy_attestation,
                GateEvidenceArtifactKindV8.PRIVACY_ATTESTATION,
                None,
            ),
            (
                self.target.no_corpus_attestation,
                GateEvidenceArtifactKindV8.NO_CORPUS_ATTESTATION,
                None,
            ),
            (self.target.policy, GateEvidenceArtifactKindV8.POLICY_RECORD, None),
        )
        for reference, expected_kind, subject in required_target_artifacts:
            artifact = artifacts.get(reference.artifact_id)
            if (
                artifact is None
                or artifact.content_checksum != reference.sha256
                or artifact.kind is not expected_kind
            ):
                raise ValueError(
                    f"Reality Gate target {expected_kind.value} is not resolved by the ledger"
                )
            if subject is not None and (
                artifact.payload.get("subject_artifact_id") != subject.artifact_id
                or artifact.payload.get("subject_sha256") != subject.sha256
            ):
                raise ValueError(
                    f"Reality Gate target {expected_kind.value} review has a different subject"
                )
        if self.blocker_registry.policy != self.target.policy:
            raise ValueError("Reality Gate blocker registry uses a different policy")
        if not set(self.blocker_registry.unresolved_blockers.evidence_ids).issubset(known_evidence):
            raise ValueError("Reality Gate blocker registry has dangling evidence")
        for item in self.dimensions:
            if not set(item.status.evidence_ids).issubset(known_evidence):
                raise ValueError(
                    f"readiness dimension {item.dimension.value} has dangling evidence"
                )
        expected = content_checksum(
            self.model_dump(mode="json", exclude={"assessment_id", "content_checksum"})
        )
        if self.content_checksum != expected:
            raise ValueError("Reality Gate assessment checksum mismatch")
        if self.assessment_id != f"REALITY-GATE-ASSESSMENT-{expected[:20]}":
            raise ValueError("Reality Gate assessment ID mismatch")
        return self


def build_reality_gate_assessment_v8(
    *,
    target: RealityGateTrainingTargetV8,
    evidence_ledger: RealityGateEvidenceLedgerV8,
    blocker_registry: GateBlockerRegistryV8,
    dimensions: tuple[tuple[ReadinessDimensionV8, KnowledgeValue[ReadinessStatusV8]], ...],
) -> RealityGateAssessmentV8:
    fields: dict[str, Any] = {
        "target": target,
        "evidence_ledger": evidence_ledger,
        "blocker_registry": blocker_registry,
        "dimensions": tuple(
            ReadinessDimensionAssessmentV8(dimension=dimension, status=status)
            for dimension, status in dimensions
        ),
    }
    draft = RealityGateAssessmentV8.model_construct(
        assessment_id="REALITY-GATE-ASSESSMENT-PENDING",
        content_checksum="0" * 64,
        **fields,
    )
    checksum = content_checksum(
        draft.model_dump(mode="json", exclude={"assessment_id", "content_checksum"})
    )
    return RealityGateAssessmentV8(
        assessment_id=f"REALITY-GATE-ASSESSMENT-{checksum[:20]}",
        content_checksum=checksum,
        **fields,
    )


class GateDecisionV8(StrEnum):
    GO = "GO"
    REVISE = "REVISE"
    LIMIT = "LIMIT"
    STOP = "STOP"


class StageGateDecisionRecordV8(KernelModel):
    decision_id: NonBlankStr
    content_checksum: Sha256
    target_ref: NonBlankStr
    target_sha256: Sha256
    assessment_ref: NonBlankStr
    assessment_sha256: Sha256
    blocker_registry_ref: NonBlankStr
    blocker_registry_sha256: Sha256
    policy_ref: NonBlankStr
    policy_sha256: Sha256
    decision: GateDecisionV8
    scope: NonBlankStr
    conditions: KnowledgeValue[tuple[NonBlankStr, ...]]
    rationale: NonBlankStr
    decision_maker_attestation_ref: NonBlankStr
    independent_stop_attestation_ref: NonBlankStr | None = None
    decided_at: datetime

    @property
    def authorizes_substantive_training(self) -> bool:
        """A serialized decision is evidence, never an authorization capability."""

        return False

    @model_validator(mode="after")
    def _decision_integrity(self) -> Self:
        if self.decided_at.tzinfo is None or self.decided_at.utcoffset() is None:
            raise ValueError("Reality Gate decision timestamp must include a timezone")
        if self.decision is GateDecisionV8.STOP:
            if self.independent_stop_attestation_ref is None:
                raise ValueError("STOP requires an independent STOP attestation")
            if self.independent_stop_attestation_ref == self.decision_maker_attestation_ref:
                raise ValueError("STOP authority must be independent from the decision maker")
        elif self.independent_stop_attestation_ref is not None:
            raise ValueError("only STOP may carry an independent STOP attestation")
        expected = content_checksum(
            self.model_dump(mode="json", exclude={"decision_id", "content_checksum"})
        )
        if self.content_checksum != expected:
            raise ValueError("Reality Gate decision checksum mismatch")
        if self.decision_id != f"REALITY-GATE-DECISION-{expected[:20]}":
            raise ValueError("Reality Gate decision ID mismatch")
        return self


def build_stage_gate_decision_v8(
    *,
    target: RealityGateTrainingTargetV8,
    assessment: RealityGateAssessmentV8,
    blocker_registry: GateBlockerRegistryV8,
    decision: GateDecisionV8,
    scope: str,
    conditions: KnowledgeValue[tuple[str, ...]],
    rationale: str,
    decision_maker_attestation_ref: str,
    independent_stop_attestation_ref: str | None,
    decided_at: datetime,
) -> StageGateDecisionRecordV8:
    if assessment.target != target:
        raise ValueError("Reality Gate decision assessment belongs to a different target")
    if assessment.blocker_registry != blocker_registry:
        raise ValueError("Reality Gate decision assessment uses a different blocker registry")
    if not set(conditions.evidence_ids).issubset(
        {item.artifact_id for item in assessment.evidence_ledger.evidence_artifacts}
    ):
        raise ValueError("Reality Gate decision conditions have dangling evidence")
    if decision is GateDecisionV8.GO and not assessment.ready_for_go:
        raise ValueError("GO requires a complete ready assessment with no open blockers")
    fields: dict[str, Any] = {
        "target_ref": target.target_id,
        "target_sha256": target.content_checksum,
        "assessment_ref": assessment.assessment_id,
        "assessment_sha256": assessment.content_checksum,
        "blocker_registry_ref": blocker_registry.registry_id,
        "blocker_registry_sha256": blocker_registry.content_checksum,
        "policy_ref": target.policy.artifact_id,
        "policy_sha256": target.policy.sha256,
        "decision": decision,
        "scope": scope,
        "conditions": conditions,
        "rationale": rationale,
        "decision_maker_attestation_ref": decision_maker_attestation_ref,
        "independent_stop_attestation_ref": independent_stop_attestation_ref,
        "decided_at": decided_at,
    }
    draft = StageGateDecisionRecordV8.model_construct(
        decision_id="REALITY-GATE-DECISION-PENDING",
        content_checksum="0" * 64,
        **fields,
    )
    checksum = content_checksum(
        draft.model_dump(mode="json", exclude={"decision_id", "content_checksum"})
    )
    return StageGateDecisionRecordV8(
        decision_id=f"REALITY-GATE-DECISION-{checksum[:20]}",
        content_checksum=checksum,
        **fields,
    )


class GateTrustUsageV8(StrEnum):
    CONFORMANCE_ONLY = "CONFORMANCE_ONLY"
    PRODUCTION = "PRODUCTION"


class TrustedGateSignerV8(KernelModel):
    signer_id: NonBlankStr
    key_id: NonBlankStr
    public_key_sha256: Sha256
    usage: GateTrustUsageV8


class GateTrustRegistryV8(KernelModel):
    registry_id: NonBlankStr
    content_checksum: Sha256
    policy: ArtifactReference
    signers: tuple[TrustedGateSignerV8, ...] = Field(min_length=1)
    registry_issuer_attestation_ref: NonBlankStr

    @model_validator(mode="after")
    def _closed_and_addressed(self) -> Self:
        signer_ids = tuple(item.signer_id for item in self.signers)
        key_ids = tuple(item.key_id for item in self.signers)
        if len(set(signer_ids)) != len(signer_ids):
            raise ValueError("Reality Gate trust signer IDs must be unique")
        if len(set(key_ids)) != len(key_ids):
            raise ValueError("Reality Gate trust key IDs must be unique")
        expected = content_checksum(
            self.model_dump(mode="json", exclude={"registry_id", "content_checksum"})
        )
        if self.content_checksum != expected:
            raise ValueError("Reality Gate trust registry checksum mismatch")
        if self.registry_id != f"REALITY-GATE-TRUST-{expected[:20]}":
            raise ValueError("Reality Gate trust registry ID mismatch")
        return self


def build_gate_trust_registry_v8(
    *,
    policy: ArtifactReference,
    signers: tuple[TrustedGateSignerV8, ...],
    registry_issuer_attestation_ref: str,
) -> GateTrustRegistryV8:
    fields: dict[str, Any] = {
        "policy": policy,
        "signers": signers,
        "registry_issuer_attestation_ref": registry_issuer_attestation_ref,
    }
    draft = GateTrustRegistryV8.model_construct(
        registry_id="REALITY-GATE-TRUST-PENDING",
        content_checksum="0" * 64,
        **fields,
    )
    checksum = content_checksum(
        draft.model_dump(mode="json", exclude={"registry_id", "content_checksum"})
    )
    return GateTrustRegistryV8(
        registry_id=f"REALITY-GATE-TRUST-{checksum[:20]}",
        content_checksum=checksum,
        **fields,
    )


class DetachedGateSignatureV8(KernelModel):
    """Detached-signature envelope; cryptographic verification is external."""

    signer_id: NonBlankStr
    key_id: NonBlankStr
    algorithm: NonBlankStr
    signed_decision_id: NonBlankStr
    signed_payload_sha256: Sha256
    signature: NonBlankStr


class TrainingAuthorizationEvaluationV8(KernelModel):
    authorization_id: NonBlankStr
    content_checksum: Sha256
    status: Literal["SCIENTIFIC_REVIEW_REQUIRED"] = "SCIENTIFIC_REVIEW_REQUIRED"
    authorized_for_training: Literal[False] = False
    target_ref: NonBlankStr
    target_sha256: Sha256
    assessment_ref: NonBlankStr
    assessment_sha256: Sha256
    evidence_ledger_ref: NonBlankStr
    evidence_ledger_sha256: Sha256
    blocker_registry_ref: NonBlankStr
    blocker_registry_sha256: Sha256
    decision_ref: NonBlankStr
    decision_sha256: Sha256
    policy_ref: NonBlankStr
    policy_sha256: Sha256
    trust_registry_ref: NonBlankStr
    trust_registry_sha256: Sha256
    detached_signature_sha256: Sha256
    blockers: tuple[NonBlankStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _addressed(self) -> Self:
        expected = content_checksum(
            self.model_dump(mode="json", exclude={"authorization_id", "content_checksum"})
        )
        if self.content_checksum != expected:
            raise ValueError("Reality Gate authorization evaluation checksum mismatch")
        if self.authorization_id != f"REALITY-GATE-AUTHORIZATION-{expected[:20]}":
            raise ValueError("Reality Gate authorization evaluation ID mismatch")
        return self


def evaluate_training_authorization_v8(
    *,
    target: RealityGateTrainingTargetV8,
    evidence_ledger: RealityGateEvidenceLedgerV8,
    blocker_registry: GateBlockerRegistryV8,
    assessment: RealityGateAssessmentV8,
    decision: StageGateDecisionRecordV8,
    trust_registry: GateTrustRegistryV8,
    detached_signature: DetachedGateSignatureV8,
) -> TrainingAuthorizationEvaluationV8:
    """Resolve the full chain but keep production authorization unavailable.

    The repository intentionally has no production trust root or detached
    signature verifier.  Conformance records are inspectable but can never open
    the training gate.
    """

    blockers: list[str] = []
    if assessment.target != target:
        blockers.append("assessment target does not match the requested target")
    if assessment.evidence_ledger != evidence_ledger:
        blockers.append("assessment evidence ledger mismatch")
    if assessment.blocker_registry != blocker_registry:
        blockers.append("assessment blocker registry mismatch")
    if blocker_registry.policy != target.policy or trust_registry.policy != target.policy:
        blockers.append("target, blocker and trust policies do not match")
    expected_decision_pins = {
        "target_ref": target.target_id,
        "target_sha256": target.content_checksum,
        "assessment_ref": assessment.assessment_id,
        "assessment_sha256": assessment.content_checksum,
        "blocker_registry_ref": blocker_registry.registry_id,
        "blocker_registry_sha256": blocker_registry.content_checksum,
        "policy_ref": target.policy.artifact_id,
        "policy_sha256": target.policy.sha256,
    }
    for field_name, expected in expected_decision_pins.items():
        if getattr(decision, field_name) != expected:
            blockers.append(f"decision {field_name} does not match its resolved component")
    if decision.decision is not GateDecisionV8.GO or decision.scope != "TRAIN":
        blockers.append("only a TRAIN-scoped GO decision can be considered")
    if not assessment.ready_for_go:
        blockers.append("Reality Gate assessment is not ready for GO")
    if detached_signature.signed_decision_id != decision.decision_id:
        blockers.append("detached signature refers to a different decision")
    if detached_signature.signed_payload_sha256 != decision.content_checksum:
        blockers.append("detached signature payload checksum mismatch")
    matching_signers = tuple(
        signer
        for signer in trust_registry.signers
        if signer.signer_id == detached_signature.signer_id
        and signer.key_id == detached_signature.key_id
    )
    if len(matching_signers) != 1:
        blockers.append("detached signature signer is not in the pinned trust registry")
    elif matching_signers[0].usage is GateTrustUsageV8.CONFORMANCE_ONLY:
        blockers.append("conformance-only signer is not a production trust root")
    else:
        blockers.append(
            "production trust root and detached cryptographic verifier are not configured"
        )
    if not blockers:
        blockers.append("production trust boundary is unavailable")

    signature_sha256 = content_checksum(detached_signature.model_dump(mode="json"))
    fields: dict[str, Any] = {
        "status": "SCIENTIFIC_REVIEW_REQUIRED",
        "authorized_for_training": False,
        "target_ref": target.target_id,
        "target_sha256": target.content_checksum,
        "assessment_ref": assessment.assessment_id,
        "assessment_sha256": assessment.content_checksum,
        "evidence_ledger_ref": evidence_ledger.ledger_id,
        "evidence_ledger_sha256": evidence_ledger.content_checksum,
        "blocker_registry_ref": blocker_registry.registry_id,
        "blocker_registry_sha256": blocker_registry.content_checksum,
        "decision_ref": decision.decision_id,
        "decision_sha256": decision.content_checksum,
        "policy_ref": target.policy.artifact_id,
        "policy_sha256": target.policy.sha256,
        "trust_registry_ref": trust_registry.registry_id,
        "trust_registry_sha256": trust_registry.content_checksum,
        "detached_signature_sha256": signature_sha256,
        "blockers": tuple(dict.fromkeys(blockers)),
    }
    draft = TrainingAuthorizationEvaluationV8.model_construct(
        authorization_id="REALITY-GATE-AUTHORIZATION-PENDING",
        content_checksum="0" * 64,
        **fields,
    )
    checksum = content_checksum(
        draft.model_dump(mode="json", exclude={"authorization_id", "content_checksum"})
    )
    return TrainingAuthorizationEvaluationV8(
        authorization_id=f"REALITY-GATE-AUTHORIZATION-{checksum[:20]}",
        content_checksum=checksum,
        **fields,
    )


class RealityGateTrainingPinTupleV8(KernelModel):
    authorization_id: NonBlankStr
    authorization_sha256: Sha256
    target_id: NonBlankStr
    target_sha256: Sha256
    snapshot_id: NonBlankStr
    snapshot_sha256: Sha256
    design_lineage_id: NonBlankStr
    design_lineage_sha256: Sha256
    privacy_attestation_id: NonBlankStr
    privacy_attestation_sha256: Sha256
    no_corpus_attestation_id: NonBlankStr
    no_corpus_attestation_sha256: Sha256
    policy_id: NonBlankStr
    policy_sha256: Sha256
    evidence_ledger_id: NonBlankStr
    evidence_ledger_sha256: Sha256
    blocker_registry_id: NonBlankStr
    blocker_registry_sha256: Sha256
    assessment_id: NonBlankStr
    assessment_sha256: Sha256
    decision_id: NonBlankStr
    decision_sha256: Sha256
    trust_registry_id: NonBlankStr
    trust_registry_sha256: Sha256
    detached_signature_sha256: Sha256

    @classmethod
    def from_components(
        cls,
        *,
        authorization: TrainingAuthorizationEvaluationV8,
        target: RealityGateTrainingTargetV8,
        evidence_ledger: RealityGateEvidenceLedgerV8,
        blocker_registry: GateBlockerRegistryV8,
        assessment: RealityGateAssessmentV8,
        decision: StageGateDecisionRecordV8,
        trust_registry: GateTrustRegistryV8,
        detached_signature: DetachedGateSignatureV8,
    ) -> RealityGateTrainingPinTupleV8:
        if assessment.target != target:
            raise ValueError("authorization pin assessment target mismatch")
        if assessment.evidence_ledger != evidence_ledger:
            raise ValueError("authorization pin evidence ledger mismatch")
        if assessment.blocker_registry != blocker_registry:
            raise ValueError("authorization pin blocker registry mismatch")
        if trust_registry.policy != target.policy:
            raise ValueError("authorization pin trust policy mismatch")
        if (
            detached_signature.signed_decision_id != decision.decision_id
            or detached_signature.signed_payload_sha256 != decision.content_checksum
        ):
            raise ValueError("authorization pin detached signature mismatch")
        signature_sha256 = content_checksum(detached_signature.model_dump(mode="json"))
        expected_authorization = {
            "target_ref": target.target_id,
            "target_sha256": target.content_checksum,
            "assessment_ref": assessment.assessment_id,
            "assessment_sha256": assessment.content_checksum,
            "evidence_ledger_ref": evidence_ledger.ledger_id,
            "evidence_ledger_sha256": evidence_ledger.content_checksum,
            "blocker_registry_ref": blocker_registry.registry_id,
            "blocker_registry_sha256": blocker_registry.content_checksum,
            "decision_ref": decision.decision_id,
            "decision_sha256": decision.content_checksum,
            "policy_ref": target.policy.artifact_id,
            "policy_sha256": target.policy.sha256,
            "trust_registry_ref": trust_registry.registry_id,
            "trust_registry_sha256": trust_registry.content_checksum,
            "detached_signature_sha256": signature_sha256,
        }
        for field_name, expected in expected_authorization.items():
            if getattr(authorization, field_name) != expected:
                raise ValueError(f"authorization {field_name} pin mismatch")
        return cls(
            authorization_id=authorization.authorization_id,
            authorization_sha256=authorization.content_checksum,
            target_id=target.target_id,
            target_sha256=target.content_checksum,
            snapshot_id=target.snapshot.artifact_id,
            snapshot_sha256=target.snapshot.sha256,
            design_lineage_id=target.design_lineage.artifact_id,
            design_lineage_sha256=target.design_lineage.sha256,
            privacy_attestation_id=target.privacy_attestation.artifact_id,
            privacy_attestation_sha256=target.privacy_attestation.sha256,
            no_corpus_attestation_id=target.no_corpus_attestation.artifact_id,
            no_corpus_attestation_sha256=target.no_corpus_attestation.sha256,
            policy_id=target.policy.artifact_id,
            policy_sha256=target.policy.sha256,
            evidence_ledger_id=evidence_ledger.ledger_id,
            evidence_ledger_sha256=evidence_ledger.content_checksum,
            blocker_registry_id=blocker_registry.registry_id,
            blocker_registry_sha256=blocker_registry.content_checksum,
            assessment_id=assessment.assessment_id,
            assessment_sha256=assessment.content_checksum,
            decision_id=decision.decision_id,
            decision_sha256=decision.content_checksum,
            trust_registry_id=trust_registry.registry_id,
            trust_registry_sha256=trust_registry.content_checksum,
            detached_signature_sha256=signature_sha256,
        )

    def state_payload(self) -> dict[str, str]:
        return {
            f"reality_gate_{field_name}": str(value)
            for field_name, value in self.model_dump(
                mode="python", exclude={"schema_version"}
            ).items()
        }


def reconcile_training_authorization_pins_v8(
    recorded: dict[str, object], expected: RealityGateTrainingPinTupleV8
) -> None:
    expected_state = expected.state_payload()
    pin_aliases = {field_name.removeprefix("reality_gate_") for field_name in expected_state}
    aliases = pin_aliases & set(recorded)
    if aliases:
        raise ValueError(
            f"non-canonical Reality Gate authorization pins present: {sorted(aliases)}"
        )
    missing = set(expected_state) - set(recorded)
    if missing:
        raise ValueError(f"Reality Gate authorization pins missing: {sorted(missing)}")
    for field_name, expected_value in expected_state.items():
        if recorded[field_name] != expected_value:
            raise ValueError(f"Reality Gate authorization pin {field_name} changed")


__all__ = [
    "SUBSTANTIVE_TRAINING_PREDICATES",
    "DetachedGateSignatureV8",
    "GateBlockerRegistryV8",
    "GateDecisionV8",
    "GateEvidenceArtifactKindV8",
    "GateEvidenceArtifactV8",
    "GateTrustRegistryV8",
    "GateTrustUsageV8",
    "ReadinessDimensionAssessmentV8",
    "ReadinessDimensionV8",
    "ReadinessStatusV8",
    "RealityGateAssessmentV8",
    "RealityGateEvidenceLedgerV8",
    "RealityGatePredicateAssessmentV8",
    "RealityGatePredicateNameV8",
    "RealityGateTrainingPinTupleV8",
    "RealityGateTrainingTargetV8",
    "StageGateDecisionRecordV8",
    "TrainingAuthorizationEvaluationV8",
    "TrustedGateSignerV8",
    "build_gate_blocker_registry_v8",
    "build_gate_evidence_artifact_v8",
    "build_gate_trust_registry_v8",
    "build_reality_gate_assessment_v8",
    "build_reality_gate_evidence_ledger_v8",
    "build_reality_gate_training_target_v8",
    "build_stage_gate_decision_v8",
    "evaluate_training_authorization_v8",
    "reconcile_training_authorization_pins_v8",
]
