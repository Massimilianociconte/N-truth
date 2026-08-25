"""PRD v8 External Challenge contamination and custody contracts.

The contracts are deliberately narrower than an authorization mechanism.  A
content-addressed attestation records what is known about exposure and access;
it cannot prove absence of pretraining exposure and it never makes an item
eligible for training or model selection.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import Field, model_validator

from ntruth.schemas.core import content_checksum
from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.training.custody import ArtifactReference, ExternalChallengeDependency

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class ChallengeSourceClassV8(StrEnum):
    PROSPECTIVE_PRIVATE = "PROSPECTIVE_PRIVATE"
    POST_CUTOFF_PUBLIC = "POST_CUTOFF_PUBLIC"
    LEGACY_PUBLIC = "LEGACY_PUBLIC"


class ChallengeExposureRiskV8(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


class ChallengeAccessPurposeV8(StrEnum):
    CUSTODY = "CUSTODY"
    INDEPENDENT_SCORING = "INDEPENDENT_SCORING"
    RELEASE_AUDIT = "RELEASE_AUDIT"
    TRAINING = "TRAINING"
    MODEL_SELECTION = "MODEL_SELECTION"
    PROMPT_DEVELOPMENT = "PROMPT_DEVELOPMENT"
    RULE_TUNING = "RULE_TUNING"
    SCHEMA_TUNING = "SCHEMA_TUNING"
    THRESHOLD_TUNING = "THRESHOLD_TUNING"
    GENERATOR_ACCESS = "GENERATOR_ACCESS"


FORBIDDEN_CHALLENGE_ACCESS_PURPOSES: frozenset[ChallengeAccessPurposeV8] = frozenset(
    {
        ChallengeAccessPurposeV8.TRAINING,
        ChallengeAccessPurposeV8.MODEL_SELECTION,
        ChallengeAccessPurposeV8.PROMPT_DEVELOPMENT,
        ChallengeAccessPurposeV8.RULE_TUNING,
        ChallengeAccessPurposeV8.SCHEMA_TUNING,
        ChallengeAccessPurposeV8.THRESHOLD_TUNING,
        ChallengeAccessPurposeV8.GENERATOR_ACCESS,
    }
)
FORBIDDEN_CHALLENGE_ACTOR_ROLES = frozenset(
    {
        "GENERATOR",
        "MODEL_SELECTOR",
        "PROMPT_DEVELOPER",
        "RULE_DEVELOPER",
        "SCHEMA_DEVELOPER",
        "THRESHOLD_TUNER",
        "TRAINER",
        "RELEASE_OWNER",
    }
)


class ChallengeAccessEventV8(KernelModel):
    event_id: NonBlankStr
    actor_id: NonBlankStr
    actor_role: NonBlankStr
    purpose: ChallengeAccessPurposeV8
    evidence_ref: NonBlankStr
    occurred_at: datetime

    @model_validator(mode="after")
    def _timezone_required(self) -> Self:
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("challenge access timestamp must include a timezone")
        return self


class ChallengeAccessLedgerV8(KernelModel):
    ledger_id: NonBlankStr
    content_checksum: Sha256
    challenge_item_id: NonBlankStr
    parent_ledger: KnowledgeValue[ArtifactReference]
    events: tuple[ChallengeAccessEventV8, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _closed_and_addressed(self) -> Self:
        event_ids = tuple(event.event_id for event in self.events)
        if len(set(event_ids)) != len(event_ids):
            raise ValueError("challenge access event IDs must be unique")
        if not any(event.purpose is ChallengeAccessPurposeV8.CUSTODY for event in self.events):
            raise ValueError("challenge access ledger requires a custody event")
        if (
            self.parent_ledger.knowledge_state is KnowledgeState.PRESENT
            and self.parent_ledger.value is not None
            and self.parent_ledger.value.artifact_id == self.ledger_id
        ):
            raise ValueError("challenge access ledger cannot reference itself as parent")
        expected = content_checksum(
            self.model_dump(mode="json", exclude={"ledger_id", "content_checksum"})
        )
        if self.content_checksum != expected:
            raise ValueError("challenge access ledger checksum mismatch")
        if self.ledger_id != f"CHALLENGE-ACCESS-LEDGER-{expected[:20]}":
            raise ValueError("challenge access ledger ID mismatch")
        return self


def build_challenge_access_ledger_v8(
    *, challenge_item_id: str, events: tuple[ChallengeAccessEventV8, ...]
) -> ChallengeAccessLedgerV8:
    fields: dict[str, Any] = {
        "challenge_item_id": challenge_item_id,
        "parent_ledger": KnowledgeValue[ArtifactReference](
            knowledge_state=KnowledgeState.NOT_APPLICABLE,
            rationale="This is the initial append-only challenge access ledger.",
            claim_scope_id=f"EXTERNAL-CHALLENGE:{challenge_item_id}:ACCESS-LEDGER",
        ),
        "events": events,
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


class ChallengeActorFunctionV8(StrEnum):
    CUSTODIAN = "CUSTODIAN"
    ATTESTER = "ATTESTER"
    INDEPENDENT_SCORER = "INDEPENDENT_SCORER"
    TRAINER = "TRAINER"
    GENERATOR = "GENERATOR"
    MODEL_SELECTOR = "MODEL_SELECTOR"
    RELEASE_OWNER = "RELEASE_OWNER"


class ChallengeActorAssignmentV8(KernelModel):
    function: ChallengeActorFunctionV8
    actor_id: NonBlankStr
    actor_role: NonBlankStr


class ChallengeActorRosterV8(KernelModel):
    roster_id: NonBlankStr
    content_checksum: Sha256
    challenge_item_id: NonBlankStr
    assignments: tuple[ChallengeActorAssignmentV8, ...] = Field(min_length=7, max_length=7)

    @model_validator(mode="after")
    def _complete_separated_and_addressed(self) -> Self:
        functions = tuple(item.function for item in self.assignments)
        if len(set(functions)) != len(functions) or set(functions) != set(ChallengeActorFunctionV8):
            raise ValueError("challenge actor roster must resolve every required function once")
        actor_ids = tuple(item.actor_id for item in self.assignments)
        roles = tuple(item.actor_role.upper() for item in self.assignments)
        if len(set(actor_ids)) != len(actor_ids):
            raise ValueError("challenge actor separation requires unique actor IDs")
        if len(set(roles)) != len(roles):
            raise ValueError("challenge actor separation requires unique actor roles")
        expected = content_checksum(
            self.model_dump(mode="json", exclude={"roster_id", "content_checksum"})
        )
        if self.content_checksum != expected:
            raise ValueError("challenge actor roster checksum mismatch")
        if self.roster_id != f"CHALLENGE-ACTOR-ROSTER-{expected[:20]}":
            raise ValueError("challenge actor roster ID mismatch")
        return self

    def assignment_for(self, function: ChallengeActorFunctionV8) -> ChallengeActorAssignmentV8:
        return next(item for item in self.assignments if item.function is function)


def build_challenge_actor_roster_v8(
    *, challenge_item_id: str, assignments: tuple[ChallengeActorAssignmentV8, ...]
) -> ChallengeActorRosterV8:
    fields: dict[str, Any] = {
        "challenge_item_id": challenge_item_id,
        "assignments": assignments,
    }
    draft = ChallengeActorRosterV8.model_construct(
        roster_id="CHALLENGE-ACTOR-ROSTER-PENDING",
        content_checksum="0" * 64,
        **fields,
    )
    checksum = content_checksum(
        draft.model_dump(mode="json", exclude={"roster_id", "content_checksum"})
    )
    return ChallengeActorRosterV8(
        roster_id=f"CHALLENGE-ACTOR-ROSTER-{checksum[:20]}",
        content_checksum=checksum,
        **fields,
    )


class ExternalChallengeAuthorityResolutionV8(KernelModel):
    """Self-contained structural resolution; never a use authorization."""

    resolution_id: NonBlankStr
    content_checksum: Sha256
    challenge_item_id: NonBlankStr
    snapshot: ArtifactReference
    source_manifest: ArtifactReference
    record_ids_checksum: Sha256
    task5_dependency: ExternalChallengeDependency
    access_ledger_head: ArtifactReference
    access_ledgers: tuple[ChallengeAccessLedgerV8, ...] = Field(min_length=1)
    actor_roster: ChallengeActorRosterV8
    use_authorized: Literal[False] = False

    @model_validator(mode="after")
    def _closed_chain_and_addressed(self) -> Self:
        if self.actor_roster.challenge_item_id != self.challenge_item_id:
            raise ValueError("challenge actor roster belongs to a different item")
        ledger_ids = tuple(item.ledger_id for item in self.access_ledgers)
        if len(set(ledger_ids)) != len(ledger_ids):
            raise ValueError("challenge access resolution contains duplicate ledger heads")
        if any(item.challenge_item_id != self.challenge_item_id for item in self.access_ledgers):
            raise ValueError("challenge access resolution crosses challenge items")
        first = self.access_ledgers[0]
        if first.parent_ledger.knowledge_state is not KnowledgeState.NOT_APPLICABLE:
            raise ValueError("initial challenge ledger parent must be NOT_APPLICABLE")
        for parent, child in zip(self.access_ledgers, self.access_ledgers[1:], strict=False):
            reference = child.parent_ledger.value
            if (
                child.parent_ledger.knowledge_state is not KnowledgeState.PRESENT
                or reference is None
                or reference.artifact_id != parent.ledger_id
                or reference.sha256 != parent.content_checksum
            ):
                raise ValueError("challenge ledger parent link is missing or stale")
            if len(child.events) <= len(parent.events) or child.events[: len(parent.events)] != (
                parent.events
            ):
                raise ValueError("challenge ledger append history is not an immutable prefix")
        head = self.access_ledgers[-1]
        if self.access_ledger_head != ArtifactReference(
            artifact_id=head.ledger_id, sha256=head.content_checksum
        ):
            raise ValueError("challenge access ledger head does not resolve the full chain")
        if self.task5_dependency.custody_reference != self.access_ledger_head:
            raise ValueError("Task 5 custody dependency does not pin the resolved ledger head")
        expected = content_checksum(
            self.model_dump(mode="json", exclude={"resolution_id", "content_checksum"})
        )
        if self.content_checksum != expected:
            raise ValueError("External Challenge resolution checksum mismatch")
        if self.resolution_id != f"EXTERNAL-CHALLENGE-RESOLUTION-{expected[:20]}":
            raise ValueError("External Challenge resolution ID mismatch")
        return self


def build_external_challenge_authority_resolution_v8(
    *,
    challenge_item_id: str,
    snapshot: ArtifactReference,
    source_manifest: ArtifactReference,
    record_ids_checksum: str,
    task5_dependency: ExternalChallengeDependency,
    access_ledger_head: ArtifactReference,
    access_ledgers: tuple[ChallengeAccessLedgerV8, ...],
    actor_roster: ChallengeActorRosterV8,
) -> ExternalChallengeAuthorityResolutionV8:
    fields: dict[str, Any] = {
        "challenge_item_id": challenge_item_id,
        "snapshot": snapshot,
        "source_manifest": source_manifest,
        "record_ids_checksum": record_ids_checksum,
        "task5_dependency": task5_dependency,
        "access_ledger_head": access_ledger_head,
        "access_ledgers": access_ledgers,
        "actor_roster": actor_roster,
        "use_authorized": False,
    }
    draft = ExternalChallengeAuthorityResolutionV8.model_construct(
        resolution_id="EXTERNAL-CHALLENGE-RESOLUTION-PENDING",
        content_checksum="0" * 64,
        **fields,
    )
    checksum = content_checksum(
        draft.model_dump(mode="json", exclude={"resolution_id", "content_checksum"})
    )
    return ExternalChallengeAuthorityResolutionV8(
        resolution_id=f"EXTERNAL-CHALLENGE-RESOLUTION-{checksum[:20]}",
        content_checksum=checksum,
        **fields,
    )


def append_challenge_access_ledger_v8(
    previous: ChallengeAccessLedgerV8,
    new_events: tuple[ChallengeAccessEventV8, ...],
) -> ChallengeAccessLedgerV8:
    if not new_events:
        raise ValueError("challenge access ledger append requires at least one event")
    fields: dict[str, Any] = {
        "challenge_item_id": previous.challenge_item_id,
        "parent_ledger": KnowledgeValue[ArtifactReference](
            knowledge_state=KnowledgeState.PRESENT,
            value=ArtifactReference(
                artifact_id=previous.ledger_id,
                sha256=previous.content_checksum,
            ),
            evidence_ids=(previous.ledger_id,),
            claim_scope_id=(f"EXTERNAL-CHALLENGE:{previous.challenge_item_id}:ACCESS-LEDGER"),
        ),
        "events": (*previous.events, *new_events),
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


class ContaminationAttestationV8(KernelModel):
    attestation_id: NonBlankStr
    content_checksum: Sha256
    challenge_item_id: NonBlankStr
    source_class: ChallengeSourceClassV8
    publication_or_creation_date: KnowledgeValue[date]
    study_family_id: NonBlankStr
    backbone_model_id: NonBlankStr
    backbone_revision: NonBlankStr
    backbone_release_date: KnowledgeValue[date]
    documented_training_cutoff: KnowledgeValue[date]
    known_web_availability: KnowledgeValue[bool]
    text_exposure_risk: KnowledgeValue[ChallengeExposureRiskV8]
    exposure_assessment_evidence_refs: tuple[NonBlankStr, ...] = Field(min_length=1)
    probes_run: KnowledgeValue[tuple[NonBlankStr, ...]]
    residual_risk: KnowledgeValue[ChallengeExposureRiskV8]
    study_family_overlap: KnowledgeValue[bool]
    permitted_claims: tuple[NonBlankStr, ...] = Field(min_length=1)
    forbidden_claims: tuple[NonBlankStr, ...] = Field(min_length=1)
    custodian_actor_id: NonBlankStr
    custodian_actor_role: NonBlankStr
    attester_actor_id: NonBlankStr
    attester_actor_role: NonBlankStr
    access_ledger: ChallengeAccessLedgerV8
    family_evidence_references: tuple[ArtifactReference, ...] = Field(min_length=1)
    attester_attestation_ref: NonBlankStr
    created_at: datetime
    training_eligible: Literal[False] = False
    model_selection_eligible: Literal[False] = False

    @model_validator(mode="after")
    def _independent_closed_and_addressed(self) -> Self:
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("contamination attestation timestamp must include a timezone")
        if self.custodian_actor_id == self.attester_actor_id:
            raise ValueError("contamination attester must be independent from the custodian")
        if self.custodian_actor_role.upper() == self.attester_actor_role.upper():
            raise ValueError("contamination attester and custodian roles must be separated")
        if self.custodian_actor_role.upper() in FORBIDDEN_CHALLENGE_ACTOR_ROLES:
            raise ValueError("challenge custodian role conflicts with a forbidden use role")
        if self.attester_actor_role.upper() in FORBIDDEN_CHALLENGE_ACTOR_ROLES:
            raise ValueError("contamination attester role conflicts with a forbidden use role")
        if self.access_ledger.challenge_item_id != self.challenge_item_id:
            raise ValueError("challenge access ledger belongs to a different item")
        if not any(
            event.actor_id == self.custodian_actor_id
            and event.actor_role.upper() == self.custodian_actor_role.upper()
            and event.purpose is ChallengeAccessPurposeV8.CUSTODY
            for event in self.access_ledger.events
        ):
            raise ValueError("custodian ID and role have no matching custody event")
        if len(set(self.permitted_claims)) != len(self.permitted_claims):
            raise ValueError("permitted challenge claims must be unique")
        if len(set(self.forbidden_claims)) != len(self.forbidden_claims):
            raise ValueError("forbidden challenge claims must be unique")
        if set(self.permitted_claims) & set(self.forbidden_claims):
            raise ValueError("a challenge claim cannot be both permitted and forbidden")
        if "proof_of_no_pretraining_exposure" not in self.forbidden_claims:
            raise ValueError(
                "absence of pretraining exposure cannot be an External Challenge claim"
            )
        known_exposure_evidence = set(self.exposure_assessment_evidence_refs)
        for label, value in (
            ("text exposure risk", self.text_exposure_risk),
            ("residual risk", self.residual_risk),
            ("detection probes", self.probes_run),
        ):
            if not set(value.evidence_ids).issubset(known_exposure_evidence):
                raise ValueError(f"{label} has evidence outside exposure assessment refs")
        family_ids = tuple(item.artifact_id for item in self.family_evidence_references)
        if len(set(family_ids)) != len(family_ids):
            raise ValueError("family evidence references must be unique")
        expected = content_checksum(
            self.model_dump(mode="json", exclude={"attestation_id", "content_checksum"})
        )
        if self.content_checksum != expected:
            raise ValueError("contamination attestation checksum mismatch")
        if self.attestation_id != f"CONTAMINATION-ATTESTATION-{expected[:20]}":
            raise ValueError("contamination attestation ID mismatch")
        return self


def build_contamination_attestation_v8(
    *,
    challenge_item_id: str,
    source_class: ChallengeSourceClassV8,
    publication_or_creation_date: KnowledgeValue[date],
    study_family_id: str,
    backbone_model_id: str,
    backbone_revision: str,
    backbone_release_date: KnowledgeValue[date],
    documented_training_cutoff: KnowledgeValue[date],
    known_web_availability: KnowledgeValue[bool],
    text_exposure_risk: KnowledgeValue[ChallengeExposureRiskV8],
    exposure_assessment_evidence_refs: tuple[str, ...],
    probes_run: KnowledgeValue[tuple[str, ...]],
    residual_risk: KnowledgeValue[ChallengeExposureRiskV8],
    study_family_overlap: KnowledgeValue[bool],
    permitted_claims: tuple[str, ...],
    forbidden_claims: tuple[str, ...],
    custodian_actor_id: str,
    custodian_actor_role: str,
    attester_actor_id: str,
    attester_actor_role: str,
    access_ledger: ChallengeAccessLedgerV8,
    family_evidence_references: tuple[ArtifactReference, ...],
    attester_attestation_ref: str,
    created_at: datetime,
) -> ContaminationAttestationV8:
    publication_or_creation_date = KnowledgeValue[date].model_validate(
        publication_or_creation_date.model_dump(mode="python")
    )
    backbone_release_date = KnowledgeValue[date].model_validate(
        backbone_release_date.model_dump(mode="python")
    )
    documented_training_cutoff = KnowledgeValue[date].model_validate(
        documented_training_cutoff.model_dump(mode="python")
    )
    fields: dict[str, Any] = {
        "challenge_item_id": challenge_item_id,
        "source_class": source_class,
        "publication_or_creation_date": publication_or_creation_date,
        "study_family_id": study_family_id,
        "backbone_model_id": backbone_model_id,
        "backbone_revision": backbone_revision,
        "backbone_release_date": backbone_release_date,
        "documented_training_cutoff": documented_training_cutoff,
        "known_web_availability": known_web_availability,
        "text_exposure_risk": text_exposure_risk,
        "exposure_assessment_evidence_refs": exposure_assessment_evidence_refs,
        "probes_run": probes_run,
        "residual_risk": residual_risk,
        "study_family_overlap": study_family_overlap,
        "permitted_claims": permitted_claims,
        "forbidden_claims": forbidden_claims,
        "custodian_actor_id": custodian_actor_id,
        "custodian_actor_role": custodian_actor_role,
        "attester_actor_id": attester_actor_id,
        "attester_actor_role": attester_actor_role,
        "access_ledger": access_ledger,
        "family_evidence_references": family_evidence_references,
        "attester_attestation_ref": attester_attestation_ref,
        "created_at": created_at,
        "training_eligible": False,
        "model_selection_eligible": False,
    }
    draft = ContaminationAttestationV8.model_construct(
        attestation_id="CONTAMINATION-ATTESTATION-PENDING",
        content_checksum="0" * 64,
        **fields,
    )
    checksum = content_checksum(
        draft.model_dump(mode="json", exclude={"attestation_id", "content_checksum"})
    )
    return ContaminationAttestationV8(
        attestation_id=f"CONTAMINATION-ATTESTATION-{checksum[:20]}",
        content_checksum=checksum,
        **fields,
    )


class ChallengeUsePurposeV8(StrEnum):
    DIAGNOSTIC = "DIAGNOSTIC"
    GENERALIZATION = "GENERALIZATION"
    RELEASE = "RELEASE"


class ChallengeUseDecisionV8(StrEnum):
    QUALIFIES_WITHIN_CLAIM_SCOPE = "QUALIFIES_WITHIN_CLAIM_SCOPE"
    DIAGNOSTIC_ONLY = "DIAGNOSTIC_ONLY"
    SCIENTIFIC_REVIEW_REQUIRED = "SCIENTIFIC_REVIEW_REQUIRED"
    BLOCK = "BLOCK"


class ExternalChallengeUseRequestV8(KernelModel):
    request_id: str = ""
    content_checksum: str = ""
    challenge_item_id: NonBlankStr
    snapshot_id: NonBlankStr
    snapshot_sha256: Sha256
    source_manifest_id: NonBlankStr
    source_manifest_sha256: Sha256
    record_ids_checksum: Sha256
    backbone_model_id: NonBlankStr
    backbone_revision: NonBlankStr
    purpose: ChallengeUsePurposeV8
    requested_claims: tuple[NonBlankStr, ...] = Field(min_length=1)
    requester_actor_id: NonBlankStr
    requester_role: NonBlankStr

    @model_validator(mode="after")
    def _closed_and_addressed_request(self) -> Self:
        if len(set(self.requested_claims)) != len(self.requested_claims):
            raise ValueError("requested External Challenge claims must be unique")
        expected = content_checksum(
            self.model_dump(mode="json", exclude={"request_id", "content_checksum"})
        )
        expected_id = f"EXTERNAL-CHALLENGE-REQUEST-{expected[:20]}"
        if self.content_checksum and self.content_checksum != expected:
            raise ValueError("External Challenge request checksum mismatch")
        if self.request_id and self.request_id != expected_id:
            raise ValueError("External Challenge request ID mismatch")
        object.__setattr__(self, "content_checksum", expected)
        object.__setattr__(self, "request_id", expected_id)
        return self


def build_external_challenge_use_request_v8(
    *,
    challenge_item_id: str,
    snapshot_id: str,
    snapshot_sha256: str,
    source_manifest_id: str,
    source_manifest_sha256: str,
    record_ids_checksum: str,
    backbone_model_id: str,
    backbone_revision: str,
    purpose: ChallengeUsePurposeV8,
    requested_claims: tuple[str, ...],
    requester_actor_id: str,
    requester_role: str,
) -> ExternalChallengeUseRequestV8:
    return ExternalChallengeUseRequestV8(
        challenge_item_id=challenge_item_id,
        snapshot_id=snapshot_id,
        snapshot_sha256=snapshot_sha256,
        source_manifest_id=source_manifest_id,
        source_manifest_sha256=source_manifest_sha256,
        record_ids_checksum=record_ids_checksum,
        backbone_model_id=backbone_model_id,
        backbone_revision=backbone_revision,
        purpose=purpose,
        requested_claims=requested_claims,
        requester_actor_id=requester_actor_id,
        requester_role=requester_role,
    )


class ExternalChallengeUseEvaluationV8(KernelModel):
    evaluation_id: NonBlankStr
    content_checksum: Sha256
    request_id: NonBlankStr
    request_sha256: Sha256
    challenge_item_id: NonBlankStr
    snapshot_id: NonBlankStr
    snapshot_sha256: Sha256
    source_manifest_id: NonBlankStr
    source_manifest_sha256: Sha256
    record_ids_checksum: Sha256
    attestation_id: NonBlankStr
    attestation_sha256: Sha256
    access_ledger_id: NonBlankStr
    access_ledger_sha256: Sha256
    authority_resolution: KnowledgeValue[ArtifactReference]
    decision: ChallengeUseDecisionV8
    blockers: KnowledgeValue[tuple[NonBlankStr, ...]]
    evaluated_claims: tuple[NonBlankStr, ...] = Field(min_length=1)
    use_authorized: Literal[False] = False
    training_eligible: Literal[False] = False
    model_selection_eligible: Literal[False] = False

    @model_validator(mode="after")
    def _addressed(self) -> Self:
        if self.blockers.knowledge_state is not KnowledgeState.PRESENT or not self.blockers.value:
            raise ValueError("a non-authorizing External Challenge HOLD requires blockers")
        expected = content_checksum(
            self.model_dump(mode="json", exclude={"evaluation_id", "content_checksum"})
        )
        if self.content_checksum != expected:
            raise ValueError("External Challenge evaluation checksum mismatch")
        if self.evaluation_id != f"EXTERNAL-CHALLENGE-EVALUATION-{expected[:20]}":
            raise ValueError("External Challenge evaluation ID mismatch")
        return self


def _present_risk(
    value: KnowledgeValue[ChallengeExposureRiskV8],
) -> ChallengeExposureRiskV8 | None:
    if value.knowledge_state is not KnowledgeState.PRESENT:
        return None
    return value.value


def _source_class_blockers(
    attestation: ContaminationAttestationV8,
    purpose: ChallengeUsePurposeV8,
) -> list[str]:
    blockers: list[str] = []

    def present(label: str, value: KnowledgeValue[Any]) -> Any | None:
        if value.knowledge_state is not KnowledgeState.PRESENT:
            blockers.append(f"{label} is not explicitly PRESENT")
            return None
        return value.value

    publication = present("publication or creation date", attestation.publication_or_creation_date)
    web = present("known web availability", attestation.known_web_availability)
    if attestation.source_class is ChallengeSourceClassV8.PROSPECTIVE_PRIVATE:
        if web is not False:
            blockers.append("PROSPECTIVE_PRIVATE requires explicitly absent web availability")
        return blockers

    cutoff = present("documented training cutoff", attestation.documented_training_cutoff)
    present("backbone release date", attestation.backbone_release_date)
    probes = present("detection probes", attestation.probes_run)
    if web is not True:
        blockers.append("public source classes require explicit web availability")
    if not isinstance(probes, tuple) or not probes:
        blockers.append("public source classes require at least one resolved detection probe")
    if isinstance(publication, date) and isinstance(cutoff, date):
        if attestation.source_class is ChallengeSourceClassV8.POST_CUTOFF_PUBLIC:
            if publication <= cutoff:
                blockers.append(
                    "POST_CUTOFF_PUBLIC publication must be strictly after the documented cutoff"
                )
        elif publication > cutoff:
            blockers.append("LEGACY_PUBLIC publication cannot be after the documented cutoff")
    if (
        attestation.source_class is ChallengeSourceClassV8.LEGACY_PUBLIC
        and purpose is not ChallengeUsePurposeV8.DIAGNOSTIC
    ):
        blockers.append("LEGACY_PUBLIC is diagnostic-only for generalization and release")
    return blockers


_EVENT_FUNCTIONS: dict[ChallengeAccessPurposeV8, ChallengeActorFunctionV8] = {
    ChallengeAccessPurposeV8.CUSTODY: ChallengeActorFunctionV8.CUSTODIAN,
    ChallengeAccessPurposeV8.INDEPENDENT_SCORING: ChallengeActorFunctionV8.INDEPENDENT_SCORER,
    ChallengeAccessPurposeV8.RELEASE_AUDIT: ChallengeActorFunctionV8.RELEASE_OWNER,
    ChallengeAccessPurposeV8.TRAINING: ChallengeActorFunctionV8.TRAINER,
    ChallengeAccessPurposeV8.MODEL_SELECTION: ChallengeActorFunctionV8.MODEL_SELECTOR,
    ChallengeAccessPurposeV8.GENERATOR_ACCESS: ChallengeActorFunctionV8.GENERATOR,
}


def _resolution_blockers(
    attestation: ContaminationAttestationV8,
    request: ExternalChallengeUseRequestV8,
    resolution: ExternalChallengeAuthorityResolutionV8,
) -> list[str]:
    blockers: list[str] = []
    if resolution.challenge_item_id != request.challenge_item_id:
        blockers.append("authority resolution belongs to a different challenge item")
    requested_pins = {
        "snapshot artifact ID": (request.snapshot_id, resolution.snapshot.artifact_id),
        "snapshot checksum": (request.snapshot_sha256, resolution.snapshot.sha256),
        "source manifest artifact ID": (
            request.source_manifest_id,
            resolution.source_manifest.artifact_id,
        ),
        "source manifest checksum": (
            request.source_manifest_sha256,
            resolution.source_manifest.sha256,
        ),
        "record IDs checksum": (request.record_ids_checksum, resolution.record_ids_checksum),
    }
    blockers.extend(
        f"{label} does not match the resolved custodial dataset"
        for label, (requested, resolved) in requested_pins.items()
        if requested != resolved
    )
    dependency = resolution.task5_dependency
    if dependency.task7_contamination_attestation_reference != ArtifactReference(
        artifact_id=attestation.attestation_id,
        sha256=attestation.content_checksum,
    ):
        blockers.append("Task 5 dependency does not pin the resolved contamination attestation")
    if dependency.custody_reference != ArtifactReference(
        artifact_id=attestation.access_ledger.ledger_id,
        sha256=attestation.access_ledger.content_checksum,
    ):
        blockers.append("Task 5 dependency does not pin the attested access ledger head")
    if tuple(dependency.family_evidence_references) != tuple(
        attestation.family_evidence_references
    ):
        blockers.append("Task 5 dependency family evidence does not match the attestation")
    if resolution.access_ledgers[-1] != attestation.access_ledger:
        blockers.append("attestation does not contain the resolved current ledger head")

    roster = resolution.actor_roster
    expected_assignments = (
        (
            ChallengeActorFunctionV8.CUSTODIAN,
            attestation.custodian_actor_id,
            attestation.custodian_actor_role,
        ),
        (
            ChallengeActorFunctionV8.ATTESTER,
            attestation.attester_actor_id,
            attestation.attester_actor_role,
        ),
        (
            ChallengeActorFunctionV8.INDEPENDENT_SCORER,
            request.requester_actor_id,
            request.requester_role,
        ),
    )
    for function, actor_id, role in expected_assignments:
        assignment = roster.assignment_for(function)
        if assignment.actor_id != actor_id or assignment.actor_role.upper() != role.upper():
            blockers.append(f"{function.value} identity or role is not resolved by the roster")
    for ledger in resolution.access_ledgers:
        for event in ledger.events:
            event_function = _EVENT_FUNCTIONS.get(event.purpose)
            if event_function is None:
                continue
            assignment = roster.assignment_for(event_function)
            if (
                assignment.actor_id != event.actor_id
                or assignment.actor_role.upper() != event.actor_role.upper()
            ):
                blockers.append(
                    f"access event {event.event_id} actor ID or role conflicts with the roster"
                )
    return blockers


def evaluate_external_challenge_use_v8(
    attestation: ContaminationAttestationV8,
    request: ExternalChallengeUseRequestV8,
    *,
    authority_resolution: ExternalChallengeAuthorityResolutionV8 | None = None,
) -> ExternalChallengeUseEvaluationV8:
    """Evaluate a claim-scoped use without granting access or release authority."""

    request = ExternalChallengeUseRequestV8.model_validate(request.model_dump(mode="python"))
    hard_blockers: list[str] = []
    review_blockers: list[str] = []
    if request.challenge_item_id != attestation.challenge_item_id:
        hard_blockers.append("request and attestation challenge item mismatch")
    if request.backbone_model_id != attestation.backbone_model_id:
        hard_blockers.append("backbone model does not match the contamination attestation")
    if request.backbone_revision != attestation.backbone_revision:
        hard_blockers.append("backbone revision does not match the contamination attestation")
    requested = set(request.requested_claims)
    forbidden = set(attestation.forbidden_claims)
    permitted = set(attestation.permitted_claims)
    if requested & forbidden:
        hard_blockers.append("request includes a forbidden External Challenge claim")
    if not requested.issubset(permitted):
        hard_blockers.append("request contains claims outside the attested permitted scope")
    if any(
        event.purpose in FORBIDDEN_CHALLENGE_ACCESS_PURPOSES
        for event in attestation.access_ledger.events
    ):
        hard_blockers.append("challenge access ledger records a forbidden access purpose")
    if (
        request.requester_actor_id
        in {attestation.custodian_actor_id, attestation.attester_actor_id}
        or request.requester_role != "INDEPENDENT_SCORER"
    ):
        hard_blockers.append("External Challenge requester must be an independent scorer")
    hard_blockers.extend(_source_class_blockers(attestation, request.purpose))
    if (
        attestation.study_family_overlap.knowledge_state is not KnowledgeState.PRESENT
        or attestation.study_family_overlap.value is not False
    ):
        hard_blockers.append("study family overlap is present, unknown or unresolved")

    resolved: ExternalChallengeAuthorityResolutionV8 | None = None
    if authority_resolution is None:
        review_blockers.append(
            "self-contained custodial dataset, ledger and actor-role resolution is absent"
        )
    else:
        resolved = ExternalChallengeAuthorityResolutionV8.model_validate(
            authority_resolution.model_dump(mode="python")
        )
        hard_blockers.extend(_resolution_blockers(attestation, request, resolved))

    exposure = _present_risk(attestation.text_exposure_risk)
    residual = _present_risk(attestation.residual_risk)
    uncertain_or_high = exposure in {
        None,
        ChallengeExposureRiskV8.HIGH,
        ChallengeExposureRiskV8.UNKNOWN,
    } or residual in {None, ChallengeExposureRiskV8.HIGH, ChallengeExposureRiskV8.UNKNOWN}
    if request.purpose is not ChallengeUsePurposeV8.DIAGNOSTIC and uncertain_or_high:
        hard_blockers.append("HIGH or UNKNOWN exposure risk is diagnostic-only")

    review_blockers.append(
        "external custodial use authority and independent trust verifier are not configured"
    )
    if hard_blockers:
        decision = ChallengeUseDecisionV8.BLOCK
    elif request.purpose is ChallengeUsePurposeV8.DIAGNOSTIC:
        decision = ChallengeUseDecisionV8.DIAGNOSTIC_ONLY
    else:
        decision = ChallengeUseDecisionV8.SCIENTIFIC_REVIEW_REQUIRED

    blocker_evidence = [
        request.request_id,
        attestation.attestation_id,
        attestation.access_ledger.ledger_id,
    ]
    if resolved is None:
        resolution_state = KnowledgeValue[ArtifactReference](
            knowledge_state=KnowledgeState.UNKNOWN,
            rationale="No external custodial authority resolution was supplied.",
            claim_scope_id=f"EXTERNAL-CHALLENGE-USE:{request.request_id}",
        )
    else:
        blocker_evidence.append(resolved.resolution_id)
        resolution_state = KnowledgeValue[ArtifactReference](
            knowledge_state=KnowledgeState.PRESENT,
            value=ArtifactReference(
                artifact_id=resolved.resolution_id,
                sha256=resolved.content_checksum,
            ),
            evidence_ids=(resolved.resolution_id,),
            claim_scope_id=f"EXTERNAL-CHALLENGE-USE:{request.request_id}",
        )
    blocker_state = KnowledgeValue[tuple[str, ...]](
        knowledge_state=KnowledgeState.PRESENT,
        value=tuple(dict.fromkeys((*hard_blockers, *review_blockers))),
        evidence_ids=tuple(blocker_evidence),
        claim_scope_id=f"EXTERNAL-CHALLENGE-USE:{request.request_id}",
    )
    fields: dict[str, Any] = {
        "request_id": request.request_id,
        "request_sha256": request.content_checksum,
        "challenge_item_id": request.challenge_item_id,
        "snapshot_id": request.snapshot_id,
        "snapshot_sha256": request.snapshot_sha256,
        "source_manifest_id": request.source_manifest_id,
        "source_manifest_sha256": request.source_manifest_sha256,
        "record_ids_checksum": request.record_ids_checksum,
        "attestation_id": attestation.attestation_id,
        "attestation_sha256": attestation.content_checksum,
        "access_ledger_id": attestation.access_ledger.ledger_id,
        "access_ledger_sha256": attestation.access_ledger.content_checksum,
        "authority_resolution": resolution_state,
        "decision": decision,
        "blockers": blocker_state,
        "evaluated_claims": request.requested_claims,
        "use_authorized": False,
        "training_eligible": False,
        "model_selection_eligible": False,
    }
    draft = ExternalChallengeUseEvaluationV8.model_construct(
        evaluation_id="EXTERNAL-CHALLENGE-EVALUATION-PENDING",
        content_checksum="0" * 64,
        **fields,
    )
    checksum = content_checksum(
        draft.model_dump(mode="json", exclude={"evaluation_id", "content_checksum"})
    )
    return ExternalChallengeUseEvaluationV8(
        evaluation_id=f"EXTERNAL-CHALLENGE-EVALUATION-{checksum[:20]}",
        content_checksum=checksum,
        **fields,
    )


__all__ = [
    "FORBIDDEN_CHALLENGE_ACCESS_PURPOSES",
    "FORBIDDEN_CHALLENGE_ACTOR_ROLES",
    "ChallengeAccessEventV8",
    "ChallengeAccessLedgerV8",
    "ChallengeAccessPurposeV8",
    "ChallengeActorAssignmentV8",
    "ChallengeActorFunctionV8",
    "ChallengeActorRosterV8",
    "ChallengeExposureRiskV8",
    "ChallengeSourceClassV8",
    "ChallengeUseDecisionV8",
    "ChallengeUsePurposeV8",
    "ContaminationAttestationV8",
    "ExternalChallengeAuthorityResolutionV8",
    "ExternalChallengeUseEvaluationV8",
    "ExternalChallengeUseRequestV8",
    "append_challenge_access_ledger_v8",
    "build_challenge_access_ledger_v8",
    "build_challenge_actor_roster_v8",
    "build_contamination_attestation_v8",
    "build_external_challenge_authority_resolution_v8",
    "build_external_challenge_use_request_v8",
    "evaluate_external_challenge_use_v8",
]
