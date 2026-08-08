"""Orthogonal source, authority, evidence and support contracts for PRD v8."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, JsonValue, field_validator, model_validator

from ntruth.schemas.authority import AuthorityType
from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.knowledge import KnowledgeValue, ensure_unambiguous_scientific_payload

SUPPORT_GRADE_VOCABULARY_SECTION_0_4 = "ntruth-prd-v8.0-section-0.4"
SUPPORT_GRADE_VOCABULARY_APPENDIX_R_1 = "ntruth-prd-v8.0-appendix-r.1"
SOURCE_CLASS_REGISTRY_ID = "ntruth-source-class-v8.0"
RULE_CHALLENGE_OUTCOME_REVIEW_ISSUE_ID = "SRR-V8-024"
SOURCE_CLASS_TOKENS = frozenset(
    {
        "document",
        "sample_sheet",
        "instrument_log",
        "metadata",
        "clarification",
        "model_output",
        "UNKNOWN_WITH_REASON",
    }
)

SUPPORT_GRADE_TOKENS: dict[str, frozenset[str]] = {
    SUPPORT_GRADE_VOCABULARY_SECTION_0_4: frozenset(
        {
            "ADJUDICATED",
            "CORROBORATED_DIRECT",
            "DIRECT_SINGLE_SOURCE",
            "AUTHOR_CLARIFIED",
            "SELF_REPORT_ONLY",
            "ASSERTION_ONLY",
            "MODEL_CANDIDATE",
            "CONFLICTED",
        }
    ),
    SUPPORT_GRADE_VOCABULARY_APPENDIX_R_1: frozenset(
        {
            "ADJUDICATED_REFERENCE",
            "CORROBORATED_EXECUTION_RECORD",
            "AUTHOR_CLARIFIED",
            "DOMAIN_EXPERT_INTERPRETATION",
            "SELF_REPORT_ONLY",
            "DOCUMENT_ASSERTION_ONLY",
            "MODEL_CANDIDATE_ONLY",
            "MIXED_UNRESOLVED",
        }
    ),
}


class EvidenceBasis(StrEnum):
    DIRECT_RECORD = "DIRECT_RECORD"
    STRUCTURED_DIRECT = "STRUCTURED_DIRECT"
    AUTHOR_ASSERTED = "AUTHOR_ASSERTED"
    SELF_REPORT = "SELF_REPORT"
    CORROBORATED_CONFIRMATION = "CORROBORATED_CONFIRMATION"
    INFERRED_CANDIDATE = "INFERRED_CANDIDATE"
    ADJUDICATED_REFERENCE = "ADJUDICATED_REFERENCE"


class EvidenceTypeV8(StrEnum):
    STRUCTURAL_FACT = "STRUCTURAL_FACT"
    PROCEDURAL_EVENT = "PROCEDURAL_EVENT"
    AUTHOR_ASSERTION = "AUTHOR_ASSERTION"
    SAMPLE_METADATA_PLANNED = "SAMPLE_METADATA_PLANNED"
    SAMPLE_METADATA_EXECUTED = "SAMPLE_METADATA_EXECUTED"
    INSTRUMENT_OR_EXECUTION_LOG = "INSTRUMENT_OR_EXECUTION_LOG"
    IMAGE_METADATA = "IMAGE_METADATA"
    STATISTICAL_CODE = "STATISTICAL_CODE"
    AUTHOR_CLARIFICATION = "AUTHOR_CLARIFICATION"
    USER_CONFIRMATION = "USER_CONFIRMATION"
    EXPERT_ADJUDICATION = "EXPERT_ADJUDICATION"
    MODEL_INFERENCE = "MODEL_INFERENCE"
    RULE_DERIVATION = "RULE_DERIVATION"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"


class SourceContext(StrEnum):
    PLANNED = "planned"
    EXECUTED = "executed"
    RECONCILED = "reconciled"
    UNVERIFIED_RETROSPECTIVE_STATEMENT = "unverified_retrospective_statement"


class ScientificReviewStatus(StrEnum):
    SCIENTIFIC_REVIEW_REQUIRED = "SCIENTIFIC_REVIEW_REQUIRED"


class ScientificReviewRequirement(KernelModel):
    status: ScientificReviewStatus = ScientificReviewStatus.SCIENTIFIC_REVIEW_REQUIRED
    issue_id: NonBlankStr
    rationale: NonBlankStr


class RuleChallengeStatus(StrEnum):
    OPEN = "OPEN"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class RuleChallengeDecisionOutcome(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class SourceClassRef(KernelModel):
    """Registry-pinned source-class token; the PRD vocabulary is not yet closed."""

    registry_id: NonBlankStr
    token: NonBlankStr
    unknown_reason: NonBlankStr | None = None

    @model_validator(mode="after")
    def _unknown_requires_reason(self) -> SourceClassRef:
        if self.registry_id != SOURCE_CLASS_REGISTRY_ID:
            raise ValueError(f"unknown source-class registry: {self.registry_id}")
        if self.token not in SOURCE_CLASS_TOKENS:
            raise ValueError("unreviewed source class must use UNKNOWN_WITH_REASON with a reason")
        if self.token == "UNKNOWN_WITH_REASON" and self.unknown_reason is None:
            raise ValueError("UNKNOWN_WITH_REASON requires unknown_reason")
        return self


class SupportGrade(KernelModel):
    """An exact token pinned to one conflicting PRD v8 vocabulary."""

    vocabulary_id: NonBlankStr
    token: NonBlankStr

    @model_validator(mode="after")
    def _known_vocabulary_and_token(self) -> SupportGrade:
        allowed = SUPPORT_GRADE_TOKENS.get(self.vocabulary_id)
        if allowed is None:
            raise ValueError(f"unknown SupportGrade vocabulary: {self.vocabulary_id}")
        if self.token not in allowed:
            raise ValueError(
                f"SupportGrade token {self.token!r} is not defined by {self.vocabulary_id}"
            )
        return self


class SupportDescriptor(KernelModel):
    """Four orthogonal dimensions; no precedence or probability is implied."""

    source_class: SourceClassRef
    authority_type: AuthorityType
    evidence_basis: EvidenceBasis
    support_grade: SupportGrade


class SourceRecord(KernelModel):
    source_id: NonBlankStr
    source_class: SourceClassRef
    source_context: SourceContext
    source_version: NonBlankStr


class EvidenceRecord(KernelModel):
    evidence_id: NonBlankStr
    source_id: NonBlankStr
    evidence_type: EvidenceTypeV8
    locator: NonBlankStr
    original_text: NonBlankStr


def _require_timezone(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return value


class ConfirmationEvent(KernelModel):
    event_id: NonBlankStr
    support: SupportDescriptor
    evidence_refs: tuple[NonBlankStr, ...] = Field(min_length=1)
    scope_id: NonBlankStr
    confirmed_value: KnowledgeValue[JsonValue]
    actor_role: NonBlankStr
    review_independent: bool
    sensitivity_record_ids: tuple[NonBlankStr, ...] = ()
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def _timezone_aware(cls, value: datetime) -> datetime:
        return _require_timezone(value)

    @model_validator(mode="after")
    def _factual_confirmation_authority(self) -> ConfirmationEvent:
        if self.support.authority_type in {
            AuthorityType.SYSTEM_INFERENCE,
            AuthorityType.RULE_DERIVATION,
        }:
            raise ValueError(
                f"{self.support.authority_type.value} cannot be factual confirmation authority"
            )
        if not set(self.confirmed_value.evidence_ids).issubset(self.evidence_refs):
            raise ValueError("confirmed_value evidence must be declared in evidence_refs")
        return self


class SensitivityRecord(KernelModel):
    sensitivity_id: NonBlankStr
    derived_claim_id: NonBlankStr
    decisive_predicate_id: NonBlankStr
    current_support_grade: SupportGrade
    current_value: JsonValue
    counterfactual_value: JsonValue
    current_output: dict[str, JsonValue]
    counterfactual_output: dict[str, JsonValue]
    interpretation: NonBlankStr

    @model_validator(mode="after")
    def _material_counterfactual(self) -> SensitivityRecord:
        ensure_unambiguous_scientific_payload(self.current_value)
        ensure_unambiguous_scientific_payload(self.counterfactual_value)
        ensure_unambiguous_scientific_payload(self.current_output)
        ensure_unambiguous_scientific_payload(self.counterfactual_output)
        if self.current_value == self.counterfactual_value:
            raise ValueError("sensitivity requires a distinct counterfactual value")
        return self


class RuleChallenge(KernelModel):
    challenge_id: NonBlankStr
    derived_claim_id: NonBlankStr
    frozen_claim_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    theory_version: NonBlankStr
    theory_clause_ids: tuple[NonBlankStr, ...] = ()
    ruleset_version: NonBlankStr
    rule_ids: tuple[NonBlankStr, ...] = ()
    rationale: NonBlankStr
    actor_role: NonBlankStr
    status: RuleChallengeStatus = RuleChallengeStatus.OPEN
    review_status: ScientificReviewStatus = ScientificReviewStatus.SCIENTIFIC_REVIEW_REQUIRED
    created_at: datetime

    @field_validator("status", mode="before")
    @classmethod
    def _born_open(cls, value: object) -> object:
        if value not in {RuleChallengeStatus.OPEN, RuleChallengeStatus.OPEN.value}:
            raise ValueError("RuleChallenge must be born OPEN")
        return value

    @field_validator("created_at")
    @classmethod
    def _timezone_aware(cls, value: datetime) -> datetime:
        return _require_timezone(value)

    @model_validator(mode="after")
    def _names_challenged_contract(self) -> RuleChallenge:
        if not self.theory_clause_ids and not self.rule_ids:
            raise ValueError("RuleChallenge requires a theory clause or rule ID")
        return self


class RuleChallengeDecision(KernelModel):
    decision_id: NonBlankStr
    challenge_id: NonBlankStr
    outcome: RuleChallengeDecisionOutcome
    reviewer_role: NonBlankStr
    rationale: NonBlankStr
    resulting_theory_version: NonBlankStr
    resulting_ruleset_version: NonBlankStr
    change_record_id: NonBlankStr
    rederivation_record_id: NonBlankStr
    outcome_contract_review: ScientificReviewRequirement
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def _timezone_aware(cls, value: datetime) -> datetime:
        return _require_timezone(value)

    @model_validator(mode="after")
    def _registered_outcome_contract_gap(self) -> RuleChallengeDecision:
        if self.outcome_contract_review.issue_id != RULE_CHALLENGE_OUTCOME_REVIEW_ISSUE_ID:
            raise ValueError(
                "outcome_contract_review must reference registered scientific-review issue "
                f"{RULE_CHALLENGE_OUTCOME_REVIEW_ISSUE_ID}"
            )
        return self


class EpistemicEventLedger(KernelModel):
    """Immutable event collection; append operations return a new ledger."""

    ledger_id: NonBlankStr
    evidence_records: tuple[EvidenceRecord, ...] = ()
    confirmation_events: tuple[ConfirmationEvent, ...] = ()
    sensitivity_records: tuple[SensitivityRecord, ...] = ()
    rule_challenges: tuple[RuleChallenge, ...] = ()
    rule_challenge_decisions: tuple[RuleChallengeDecision, ...] = ()

    @model_validator(mode="after")
    def _persisted_ledger_invariants(self) -> EpistemicEventLedger:
        identifiers = [
            *(record.evidence_id for record in self.evidence_records),
            *(event.event_id for event in self.confirmation_events),
            *(record.sensitivity_id for record in self.sensitivity_records),
            *(challenge.challenge_id for challenge in self.rule_challenges),
            *(decision.decision_id for decision in self.rule_challenge_decisions),
        ]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("ledger object IDs must be globally unique")

        evidence_by_id = {record.evidence_id: record for record in self.evidence_records}
        sensitivity_ids = {record.sensitivity_id for record in self.sensitivity_records}
        forbidden = {EvidenceTypeV8.MODEL_INFERENCE, EvidenceTypeV8.RULE_DERIVATION}
        for event in self.confirmation_events:
            missing = set(event.evidence_refs) - evidence_by_id.keys()
            if missing:
                raise ValueError(f"confirmation references unknown evidence IDs: {sorted(missing)}")
            prohibited = [
                evidence_by_id[evidence_id].evidence_type
                for evidence_id in event.evidence_refs
                if evidence_by_id[evidence_id].evidence_type in forbidden
            ]
            if prohibited:
                raise ValueError(f"{prohibited[0].value} cannot be factual confirmation evidence")
            missing_sensitivity = set(event.sensitivity_record_ids) - sensitivity_ids
            if missing_sensitivity:
                raise ValueError(
                    "confirmation references unknown sensitivity record IDs: "
                    f"{sorted(missing_sensitivity)}"
                )

        challenges_by_id = {challenge.challenge_id: challenge for challenge in self.rule_challenges}
        decided_challenges: set[str] = set()
        for decision in self.rule_challenge_decisions:
            challenge = challenges_by_id.get(decision.challenge_id)
            if challenge is None:
                raise ValueError(
                    f"decision {decision.decision_id} references unknown RuleChallenge "
                    f"{decision.challenge_id}"
                )
            if decision.challenge_id in decided_challenges:
                raise ValueError(f"RuleChallenge {decision.challenge_id} already has a decision")
            if decision.created_at < challenge.created_at:
                raise ValueError(
                    f"decision {decision.decision_id} precedes RuleChallenge "
                    f"{decision.challenge_id}"
                )
            if decision.outcome is RuleChallengeDecisionOutcome.ACCEPTED and (
                decision.resulting_theory_version == challenge.theory_version
                or decision.resulting_ruleset_version == challenge.ruleset_version
            ):
                raise ValueError(
                    "ACCEPTED decision requires distinct successor versions from the frozen "
                    "RuleChallenge contracts"
                )
            decided_challenges.add(decision.challenge_id)
        return self

    def append_evidence(self, record: EvidenceRecord) -> EpistemicEventLedger:
        self._reject_duplicate(record.evidence_id)
        return self._copy_with(evidence_records=(*self.evidence_records, record))

    def append_confirmation(self, event: ConfirmationEvent) -> EpistemicEventLedger:
        self._reject_duplicate(event.event_id)
        return self._copy_with(confirmation_events=(*self.confirmation_events, event))

    def append_sensitivity(self, record: SensitivityRecord) -> EpistemicEventLedger:
        self._reject_duplicate(record.sensitivity_id)
        return self._copy_with(sensitivity_records=(*self.sensitivity_records, record))

    def append_rule_challenge(self, challenge: RuleChallenge) -> EpistemicEventLedger:
        self._reject_duplicate(challenge.challenge_id)
        return self._copy_with(rule_challenges=(*self.rule_challenges, challenge))

    def append_rule_challenge_decision(
        self, decision: RuleChallengeDecision
    ) -> EpistemicEventLedger:
        self._reject_duplicate(decision.decision_id)
        if any(
            existing.challenge_id == decision.challenge_id
            for existing in self.rule_challenge_decisions
        ):
            raise ValueError(f"RuleChallenge {decision.challenge_id} already has a decision")
        return self._copy_with(rule_challenge_decisions=(*self.rule_challenge_decisions, decision))

    def _copy_with(self, **updates: object) -> EpistemicEventLedger:
        values = {
            "ledger_id": self.ledger_id,
            "evidence_records": self.evidence_records,
            "confirmation_events": self.confirmation_events,
            "sensitivity_records": self.sensitivity_records,
            "rule_challenges": self.rule_challenges,
            "rule_challenge_decisions": self.rule_challenge_decisions,
            **updates,
        }
        return EpistemicEventLedger.model_validate(values)

    def _reject_duplicate(self, identifier: str) -> None:
        identifiers = {
            *(record.evidence_id for record in self.evidence_records),
            *(event.event_id for event in self.confirmation_events),
            *(record.sensitivity_id for record in self.sensitivity_records),
            *(challenge.challenge_id for challenge in self.rule_challenges),
            *(decision.decision_id for decision in self.rule_challenge_decisions),
        }
        if identifier in identifiers:
            raise ValueError(f"event {identifier} already exists: append-only")


__all__ = [
    "RULE_CHALLENGE_OUTCOME_REVIEW_ISSUE_ID",
    "SOURCE_CLASS_REGISTRY_ID",
    "SOURCE_CLASS_TOKENS",
    "SUPPORT_GRADE_TOKENS",
    "SUPPORT_GRADE_VOCABULARY_APPENDIX_R_1",
    "SUPPORT_GRADE_VOCABULARY_SECTION_0_4",
    "AuthorityType",
    "ConfirmationEvent",
    "EpistemicEventLedger",
    "EvidenceBasis",
    "EvidenceRecord",
    "EvidenceTypeV8",
    "RuleChallenge",
    "RuleChallengeDecision",
    "RuleChallengeDecisionOutcome",
    "RuleChallengeStatus",
    "ScientificReviewRequirement",
    "ScientificReviewStatus",
    "SensitivityRecord",
    "SourceClassRef",
    "SourceContext",
    "SourceRecord",
    "SupportDescriptor",
    "SupportGrade",
]
