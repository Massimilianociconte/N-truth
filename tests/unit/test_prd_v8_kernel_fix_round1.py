"""Regression tests for Task 1 scientific-contract review findings."""

from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module

import pytest
from pydantic import JsonValue, ValidationError


def _knowledge() -> object:
    return import_module("ntruth.schemas.knowledge")


def _support() -> object:
    return import_module("ntruth.schemas.support")


def _claims() -> object:
    return import_module("ntruth.schemas.claims")


def _migration() -> object:
    return import_module("ntruth.migrations.v7_to_v8")


def _section_support_grade() -> object:
    support = _support()
    return support.SupportGrade(
        vocabulary_id=support.SUPPORT_GRADE_VOCABULARY_SECTION_0_4,
        token="DIRECT_SINGLE_SOURCE",
    )


def _human_support_descriptor() -> object:
    support = _support()
    return support.SupportDescriptor(
        source_class=support.SourceClassRef(
            registry_id=support.SOURCE_CLASS_REGISTRY_ID,
            token="clarification",
        ),
        authority_type=support.AuthorityType.AUTHOR_CLARIFICATION,
        evidence_basis=support.EvidenceBasis.SELF_REPORT,
        support_grade=support.SupportGrade(
            vocabulary_id=support.SUPPORT_GRADE_VOCABULARY_SECTION_0_4,
            token="AUTHOR_CLARIFIED",
        ),
    )


def _evidence_record(*, evidence_id: str, evidence_type: object) -> object:
    support = _support()
    return support.EvidenceRecord(
        evidence_id=evidence_id,
        source_id="SRC-001",
        evidence_type=evidence_type,
        locator=f"record:{evidence_id}",
        original_text="Treatment was assigned independently after splitting.",
    )


def _confirmation_event(
    *,
    event_id: str = "CONF-001",
    evidence_id: str = "EV-001",
    confirmed_value: JsonValue = True,
) -> object:
    knowledge = _knowledge()
    support = _support()
    return support.ConfirmationEvent(
        event_id=event_id,
        support=_human_support_descriptor(),
        evidence_refs=(evidence_id,),
        scope_id="PRED-ASSIGN-SEPARABLE",
        confirmed_value=knowledge.KnowledgeValue[JsonValue](
            knowledge_state=knowledge.KnowledgeState.PRESENT,
            value=confirmed_value,
            evidence_ids=(evidence_id,),
        ),
        actor_role="experiment_owner",
        review_independent=False,
        created_at=datetime(2026, 8, 8, 12, 0, tzinfo=UTC),
    )


def _rule_challenge(*, challenge_id: str = "CHAL-001", status: str = "OPEN") -> object:
    support = _support()
    return support.RuleChallenge(
        challenge_id=challenge_id,
        derived_claim_id="CLAIM-EU-001",
        frozen_claim_checksum="a" * 64,
        theory_version="derivation-theory-0.1.0",
        theory_clause_ids=("DT-EU-01",),
        ruleset_version="ntruth-core-0.3.0",
        rule_ids=("EU-ALLOC-001",),
        rationale="The assignment-separability premise is not supported.",
        actor_role="domain_expert",
        status=status,
        created_at=datetime(2026, 8, 8, 12, 0, tzinfo=UTC),
    )


def _rule_challenge_decision_payload(
    *,
    outcome: str = "ACCEPTED",
    theory_version: str = "derivation-theory-0.2.0",
    ruleset_version: str = "ntruth-core-0.4.0",
    created_at: datetime = datetime(2026, 8, 8, 13, 0, tzinfo=UTC),
) -> dict[str, object]:
    return {
        "decision_id": "RCD-001",
        "challenge_id": "CHAL-001",
        "outcome": outcome,
        "reviewer_role": "methodology_reviewer",
        "rationale": "The challenge received an append-only review decision.",
        "resulting_theory_version": theory_version,
        "resulting_ruleset_version": ruleset_version,
        "change_record_id": "CHANGE-001",
        "rederivation_record_id": "REDERIVE-001",
        "outcome_contract_review": {
            "issue_id": "SRR-V8-024",
            "rationale": "The accepted/rejected payload mapping remains under review.",
        },
        "created_at": created_at,
    }


def _claim_review_requirement(*, issue_id: str) -> object:
    claims = _claims()
    return claims.ScientificReviewRequirement(
        issue_id=issue_id,
        rationale="The PRD does not yet close this executable payload mapping.",
    )


def _profile_coverage_reference() -> object:
    claims = _claims()
    return claims.ProfileCoverageReference(
        statement_id="PCS-001",
        profile_id="simple_cell_culture",
        profile_version="0.1.0",
        predicate_closure_argument_id="PCA-SCC-001",
        contract_review=_claim_review_requirement(issue_id="SRR-V8-008"),
    )


def _proof_trace(*, resolved: bool) -> tuple[object, ...]:
    claims = _claims()
    knowledge = _knowledge()
    if resolved:
        predicate_value = knowledge.KnowledgeValue[bool](
            knowledge_state=knowledge.KnowledgeState.PRESENT,
            value=True,
            evidence_ids=("EV-PRED-001",),
        )
    else:
        predicate_value = knowledge.KnowledgeValue[bool](
            knowledge_state=knowledge.KnowledgeState.UNKNOWN,
            rationale="The decisive predicate remains unresolved.",
            claim_scope_id="CLAIM-EU-001",
        )
    return (
        claims.ProofTraceStep(
            step_id="PROOF-001",
            predicate_references=(
                claims.PredicateProofReference(
                    predicate_id="assignment_unit",
                    predicate_value=predicate_value,
                ),
            ),
            theory_clause_id="DT-EU-01",
            rule_id="EU-ALLOC-001",
        ),
    )


def _claim_for_state(
    *,
    state_name: str,
    value: object,
    include_review_blocker: bool = True,
    review_issue_id: str = "SRR-V8-023",
) -> object:
    claims = _claims()
    state = claims.DeterminabilityState(state_name)
    return claims.DerivedClaim(
        claim_id="CLAIM-EU-001",
        claim_type="EXPERIMENTAL_UNIT",
        inferential_query_id="IQ-001",
        value=value,
        determinability_state=state,
        support_grade=_section_support_grade(),
        required_predicates=("assignment_unit",),
        irrelevant_predicates=(
            claims.IrrelevantPredicate(
                id="biological_source_independence",
                rationale="Not required to identify the treatment EU.",
            ),
        ),
        assumptions=("record_complete_for_claim",),
        theory_version="derivation-theory-0.1.0",
        theory_clauses=("DT-EU-01",),
        ruleset_version="ntruth-core-0.3.0",
        rule_trace=("EU-ALLOC-001",),
        proof_trace=_proof_trace(resolved=state is claims.DeterminabilityState.DETERMINATE),
        profile_coverage=_profile_coverage_reference(),
        state_contract_review=(
            _claim_review_requirement(issue_id=review_issue_id)
            if include_review_blocker and state is not claims.DeterminabilityState.DETERMINATE
            else None
        ),
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"unit_type": None},
        {"unit_type": ""},
        {"items": []},
        {"nested": {"items": []}},
        [None],
        [""],
    ],
)
def test_present_rejects_recursively_ambiguous_scientific_payloads(payload: JsonValue) -> None:
    """Catches a bare null/blank/empty leaf hidden below a PRESENT wrapper."""
    knowledge = _knowledge()
    with pytest.raises(ValidationError, match="ambiguous scientific payload"):
        knowledge.KnowledgeValue[JsonValue](
            knowledge_state=knowledge.KnowledgeState.PRESENT,
            value=payload,
            evidence_ids=("EV-001",),
        )


@pytest.mark.parametrize(
    ("field_name", "ambiguous_value"),
    [
        ("current_value", {"predicate": None}),
        ("counterfactual_value", {"predicate": ""}),
        ("current_output", {"experimental_unit_count": {"items": []}}),
        ("counterfactual_output", {"experimental_unit_count": [None]}),
    ],
)
def test_sensitivity_rejects_recursively_ambiguous_scientific_payloads(
    field_name: str,
    ambiguous_value: JsonValue,
) -> None:
    """Catches nested ambiguous leaves in sensitivity values or outputs."""
    support = _support()
    payload: dict[str, object] = {
        "sensitivity_id": "SENS-001",
        "derived_claim_id": "CLAIM-N-001",
        "decisive_predicate_id": "PRED-INDEP-001",
        "current_support_grade": _section_support_grade(),
        "current_value": True,
        "counterfactual_value": False,
        "current_output": {"experimental_unit_count": 4},
        "counterfactual_output": {"experimental_unit_count": 1},
        "interpretation": "The count changes under the counterfactual.",
    }
    payload[field_name] = ambiguous_value
    with pytest.raises(ValidationError, match="ambiguous scientific payload"):
        support.SensitivityRecord.model_validate(payload)


def test_not_reported_requires_nonempty_source_scope() -> None:
    """Catches an unsupported claim that inspected sources were silent."""
    knowledge = _knowledge()
    with pytest.raises(ValidationError, match="source_scope_ids"):
        knowledge.KnowledgeValue[str](
            knowledge_state=knowledge.KnowledgeState.NOT_REPORTED,
        )

    value = knowledge.KnowledgeValue[list[str]](
        knowledge_state=knowledge.KnowledgeState.NOT_REPORTED,
        value=[],
        source_scope_ids=("SRC-METHODS", "SRC-SAMPLE-SHEET"),
    )
    assert value.source_scope_ids == ("SRC-METHODS", "SRC-SAMPLE-SHEET")


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"rationale": "The available records do not resolve the assignment unit."},
        {"claim_scope_id": "CLAIM-EU-001"},
    ],
)
def test_unknown_requires_rationale_and_claim_or_query_scope(payload: dict[str, str]) -> None:
    """Catches UNKNOWN collapsing into an unscoped generic missing value."""
    knowledge = _knowledge()
    with pytest.raises(ValidationError, match="UNKNOWN requires"):
        knowledge.KnowledgeValue[str](
            knowledge_state=knowledge.KnowledgeState.UNKNOWN,
            **payload,
        )

    value = knowledge.KnowledgeValue[str](
        knowledge_state=knowledge.KnowledgeState.UNKNOWN,
        rationale="The available records do not resolve the assignment unit.",
        query_scope_id="IQ-001",
    )
    assert value.query_scope_id == "IQ-001"


def test_knowledge_state_obligation_matrix_has_one_valid_example_per_state() -> None:
    """Catches one state inheriting another state's evidence/scope obligations."""
    knowledge = _knowledge()
    values = (
        knowledge.KnowledgeValue[str](
            knowledge_state=knowledge.KnowledgeState.PRESENT,
            value="well",
            evidence_ids=("EV-PRESENT",),
        ),
        knowledge.KnowledgeValue[str](
            knowledge_state=knowledge.KnowledgeState.ABSENT_EXPLICIT,
            evidence_ids=("EV-ABSENCE",),
        ),
        knowledge.KnowledgeValue[str](
            knowledge_state=knowledge.KnowledgeState.NOT_REPORTED,
            source_scope_ids=("SRC-METHODS",),
        ),
        knowledge.KnowledgeValue[str](
            knowledge_state=knowledge.KnowledgeState.UNKNOWN,
            rationale="The source set does not resolve this claim.",
            claim_scope_id="CLAIM-EU-001",
        ),
        knowledge.KnowledgeValue[str](
            knowledge_state=knowledge.KnowledgeState.NOT_APPLICABLE,
            rationale="This predicate is irrelevant to this claim.",
            claim_scope_id="CLAIM-EU-001",
        ),
        knowledge.KnowledgeValue[str](
            knowledge_state=knowledge.KnowledgeState.CONFLICTING,
            conflicting_values=("well", "plate"),
            evidence_ids=("EV-CONFLICT-1", "EV-CONFLICT-2"),
        ),
    )
    assert tuple(value.knowledge_state for value in values) == tuple(knowledge.KnowledgeState)


def test_migration_result_is_success_xor_scientific_review_required() -> None:
    """Catches consumers receiving both a usable value and a blocking diagnostic, or neither."""
    migration = _migration()
    diagnostic = migration.MigrationDiagnostic(
        code=migration.MigrationDiagnosticCode.SCIENTIFIC_REVIEW_REQUIRED,
        issue_id="SRR-V8-002",
        message="Ambiguous query identifier.",
    )
    with pytest.raises(ValidationError, match="exactly one"):
        migration.MigrationResult[str](value="IQ-001", diagnostics=(diagnostic,))
    with pytest.raises(ValidationError, match="exactly one"):
        migration.MigrationResult[str]()

    success = migration.MigrationResult[str](value="IQ-001")
    blocked = migration.MigrationResult[str](diagnostics=(diagnostic,))
    assert not success.requires_scientific_review
    assert blocked.requires_scientific_review


@pytest.mark.parametrize("invalid_query_id", [None, "", "   ", 7])
def test_query_alias_null_blank_or_wrong_type_fails_closed(invalid_query_id: object) -> None:
    """Catches a syntactically invalid legacy query ID being reported as migrated."""
    migration = _migration()
    result = migration.migrate_v7_claim_field_names(
        {"query_id": invalid_query_id},
        source_contract="ntruth-prd-v7-derived-claim",
    )
    assert result.value is None
    assert result.requires_scientific_review
    assert result.diagnostics[0].issue_id == "SRR-V8-002"


@pytest.mark.parametrize("invalid_state", [None, "", "   ", 7, "INDETERMINATE"])
def test_determinability_alias_invalid_token_or_type_fails_closed(invalid_state: object) -> None:
    """Catches an invalid legacy state being reported as a canonical v8 state."""
    migration = _migration()
    result = migration.migrate_v7_claim_field_names(
        {"determinability": invalid_state},
        source_contract="ntruth-prd-v7-derived-claim",
    )
    assert result.value is None
    assert result.requires_scientific_review
    assert result.diagnostics[0].issue_id == "SRR-V8-004"


@pytest.mark.parametrize(
    ("legacy_name", "canonical_name", "invalid_value", "issue_id"),
    [
        ("query_id", "inferential_query_id", None, "SRR-V8-002"),
        ("query_id", "inferential_query_id", "", "SRR-V8-002"),
        ("determinability", "determinability_state", None, "SRR-V8-004"),
        ("determinability", "determinability_state", "", "SRR-V8-004"),
    ],
)
def test_equal_invalid_legacy_and_canonical_aliases_still_fail_closed(
    legacy_name: str,
    canonical_name: str,
    invalid_value: object,
    issue_id: str,
) -> None:
    """Catches equality short-circuiting validation of two equally invalid aliases."""
    migration = _migration()
    result = migration.migrate_v7_claim_field_names(
        {legacy_name: invalid_value, canonical_name: invalid_value},
        source_contract="ntruth-prd-v7-derived-claim",
    )
    assert result.value is None
    assert result.requires_scientific_review
    assert result.diagnostics[0].issue_id == issue_id


@pytest.mark.parametrize(
    "null_semantics",
    ["UNKNOWN", "NOT_REPORTED"],
)
def test_v7_null_mapping_without_new_state_obligations_fails_closed(
    null_semantics: str,
) -> None:
    """Catches an audited null rule producing an unscoped UNKNOWN/NOT_REPORTED value."""
    knowledge = _knowledge()
    migration = _migration()
    result = migration.migrate_v7_scientific_field(
        field_name="experimental_unit",
        value=None,
        source_contract="ntruth-v7-unit-assessment",
        null_semantics=knowledge.KnowledgeState(null_semantics),
        migration_rule_id="MIG-V7-EU-NULL",
    )
    assert result.value is None
    assert result.requires_scientific_review


def test_confirmation_records_the_typed_value_that_was_confirmed() -> None:
    """Catches opposite confirmations being structurally indistinguishable."""
    positive = _confirmation_event(event_id="CONF-TRUE", confirmed_value=True)
    negative = _confirmation_event(event_id="CONF-FALSE", confirmed_value=False)
    assert positive.confirmed_value.value is True
    assert negative.confirmed_value.value is False
    assert positive.model_dump(mode="json") != negative.model_dump(mode="json")


def test_confirmation_value_evidence_must_be_declared_by_the_event() -> None:
    """Catches a confirmed value depending on evidence hidden from event provenance."""
    knowledge = _knowledge()
    support = _support()
    with pytest.raises(ValidationError, match="confirmed_value evidence"):
        support.ConfirmationEvent(
            event_id="CONF-MISMATCH",
            support=_human_support_descriptor(),
            evidence_refs=("EV-DECLARED",),
            scope_id="PRED-ASSIGN-SEPARABLE",
            confirmed_value=knowledge.KnowledgeValue[JsonValue](
                knowledge_state=knowledge.KnowledgeState.PRESENT,
                value=True,
                evidence_ids=("EV-HIDDEN",),
            ),
            actor_role="experiment_owner",
            review_independent=False,
            created_at=datetime(2026, 8, 8, 12, 0, tzinfo=UTC),
        )


@pytest.mark.parametrize("forbidden_type", ["RULE_DERIVATION", "MODEL_INFERENCE"])
def test_ledger_rejects_nonfactual_evidence_for_human_confirmation(
    forbidden_type: str,
) -> None:
    """Catches rule/model output entering through the evidence axis of a human event."""
    support = _support()
    evidence = _evidence_record(
        evidence_id="EV-001",
        evidence_type=support.EvidenceTypeV8(forbidden_type),
    )
    event = _confirmation_event()
    with pytest.raises(ValidationError, match="cannot be factual confirmation evidence"):
        support.EpistemicEventLedger(
            ledger_id="LEDGER-001",
            evidence_records=(evidence,),
            confirmation_events=(event,),
        )


def test_ledger_accepts_declared_factual_confirmation_evidence() -> None:
    """Catches an over-broad ban that would reject a direct human clarification."""
    support = _support()
    evidence = _evidence_record(
        evidence_id="EV-001",
        evidence_type=support.EvidenceTypeV8.AUTHOR_CLARIFICATION,
    )
    ledger = support.EpistemicEventLedger(
        ledger_id="LEDGER-001",
        evidence_records=(evidence,),
        confirmation_events=(_confirmation_event(),),
    )
    assert ledger.confirmation_events[0].confirmed_value.value is True


def test_ledger_deserialization_rejects_dangling_confirmation_sensitivity_reference() -> None:
    """Catches a persisted confirmation pointing outside the ledger sensitivity bundle."""
    support = _support()
    evidence = _evidence_record(
        evidence_id="EV-001",
        evidence_type=support.EvidenceTypeV8.AUTHOR_CLARIFICATION,
    )
    event = _confirmation_event().model_copy(update={"sensitivity_record_ids": ("SENS-MISSING",)})
    payload = {
        "ledger_id": "LEDGER-001",
        "evidence_records": [evidence.model_dump(mode="json")],
        "confirmation_events": [event.model_dump(mode="json")],
    }
    with pytest.raises(ValidationError, match="unknown sensitivity"):
        support.EpistemicEventLedger.model_validate(payload)


def test_ledger_rejects_duplicate_ids_when_deserializing() -> None:
    """Catches persisted duplicate events bypassing append helper validation."""
    support = _support()
    event = _confirmation_event()
    payload = {
        "ledger_id": "LEDGER-001",
        "evidence_records": [
            _evidence_record(
                evidence_id="EV-001",
                evidence_type=support.EvidenceTypeV8.AUTHOR_CLARIFICATION,
            ).model_dump(mode="json")
        ],
        "confirmation_events": [
            event.model_dump(mode="json"),
            event.model_dump(mode="json"),
        ],
    }
    with pytest.raises(ValidationError, match="globally unique"):
        support.EpistemicEventLedger.model_validate(payload)


def test_ledger_ids_are_unique_across_record_kinds() -> None:
    """Catches an evidence ID and an event ID addressing two different objects."""
    support = _support()
    evidence = _evidence_record(
        evidence_id="GLOBAL-001",
        evidence_type=support.EvidenceTypeV8.AUTHOR_CLARIFICATION,
    )
    event = _confirmation_event(event_id="GLOBAL-001", evidence_id="GLOBAL-001")
    with pytest.raises(ValidationError, match="globally unique"):
        support.EpistemicEventLedger(
            ledger_id="LEDGER-001",
            evidence_records=(evidence,),
            confirmation_events=(event,),
        )


@pytest.mark.parametrize("non_open_status", ["ACCEPTED", "REJECTED"])
def test_rule_challenge_can_only_be_created_open(non_open_status: str) -> None:
    """Catches a challenge materializing as decided without a decision event."""
    with pytest.raises(ValidationError, match="born OPEN"):
        _rule_challenge(status=non_open_status)


def test_rule_challenge_decision_is_separate_append_only_history() -> None:
    """Catches mutating a challenge status instead of recording review and re-derivation."""
    support = _support()
    challenge = _rule_challenge()
    decision = support.RuleChallengeDecision.model_validate(_rule_challenge_decision_payload())
    ledger = support.EpistemicEventLedger(
        ledger_id="LEDGER-001",
        rule_challenges=(challenge,),
    )
    updated = ledger.append_rule_challenge_decision(decision)
    assert ledger.rule_challenge_decisions == ()
    assert updated.rule_challenge_decisions == (decision,)
    assert updated.rule_challenges[0].status.value == "OPEN"

    second_decision = decision.model_copy(update={"decision_id": "RCD-002"})
    with pytest.raises(ValueError, match="already has a decision"):
        updated.append_rule_challenge_decision(second_decision)


def test_rule_challenge_decision_requires_existing_challenge() -> None:
    """Catches an orphan decision entering through direct deserialization."""
    support = _support()
    payload = _rule_challenge_decision_payload(outcome="REJECTED")
    payload.update(
        decision_id="RCD-ORPHAN",
        challenge_id="CHAL-MISSING",
        resulting_theory_version="derivation-theory-0.1.0",
        resulting_ruleset_version="ntruth-core-0.3.0",
        rederivation_record_id="REDERIVE-UNCHANGED-001",
    )
    decision = support.RuleChallengeDecision.model_validate(payload)
    with pytest.raises(ValidationError, match="unknown RuleChallenge"):
        support.EpistemicEventLedger(
            ledger_id="LEDGER-001",
            rule_challenge_decisions=(decision,),
        )


def test_rule_challenge_decision_cannot_precede_challenge() -> None:
    """Catches persisted review history whose decision predates the challenged snapshot."""
    support = _support()
    challenge = _rule_challenge()
    decision = support.RuleChallengeDecision.model_validate(
        _rule_challenge_decision_payload(created_at=datetime(2026, 8, 8, 11, 59, tzinfo=UTC))
    )
    with pytest.raises(ValidationError, match="precedes RuleChallenge"):
        support.EpistemicEventLedger.model_validate(
            {
                "ledger_id": "LEDGER-001",
                "rule_challenges": [challenge.model_dump(mode="json")],
                "rule_challenge_decisions": [decision.model_dump(mode="json")],
            }
        )


@pytest.mark.parametrize(
    ("theory_version", "ruleset_version"),
    [
        ("derivation-theory-0.1.0", "ntruth-core-0.4.0"),
        ("derivation-theory-0.2.0", "ntruth-core-0.3.0"),
    ],
)
def test_accepted_rule_challenge_requires_distinct_successor_versions(
    theory_version: str,
    ruleset_version: str,
) -> None:
    """Catches ACCEPTED history that silently reuses either frozen contract version."""
    support = _support()
    challenge = _rule_challenge()
    decision = support.RuleChallengeDecision.model_validate(
        _rule_challenge_decision_payload(
            theory_version=theory_version,
            ruleset_version=ruleset_version,
        )
    )
    with pytest.raises(ValidationError, match="distinct successor versions"):
        support.EpistemicEventLedger.model_validate(
            {
                "ledger_id": "LEDGER-001",
                "rule_challenges": [challenge.model_dump(mode="json")],
                "rule_challenge_decisions": [decision.model_dump(mode="json")],
            }
        )


def test_rule_challenge_decision_requires_change_record_reference() -> None:
    """Catches a decision that cannot be joined to its change or migration record."""
    support = _support()
    payload = _rule_challenge_decision_payload()
    payload.pop("change_record_id")
    with pytest.raises(ValidationError, match="change_record_id"):
        support.RuleChallengeDecision.model_validate(payload)


def test_rule_challenge_decision_requires_typed_registered_outcome_blocker() -> None:
    """Catches an outcome mapping being treated as scientifically closed by omission."""
    support = _support()
    payload = _rule_challenge_decision_payload()
    payload.pop("outcome_contract_review")
    with pytest.raises(ValidationError, match="outcome_contract_review"):
        support.RuleChallengeDecision.model_validate(payload)


def test_rule_challenge_outcome_blocker_rejects_unregistered_issue_id() -> None:
    """Catches a local outcome-review label bypassing the scientific review register."""
    support = _support()
    payload = _rule_challenge_decision_payload()
    payload["outcome_contract_review"] = {
        "issue_id": "LOCAL-OUTCOME-MAPPING",
        "rationale": "The accepted/rejected payload mapping remains under review.",
    }
    with pytest.raises(ValidationError, match="registered scientific-review issue"):
        support.RuleChallengeDecision.model_validate(payload)


def test_derived_claim_requires_pinned_profile_coverage_and_explicit_proof_dependencies() -> None:
    """Catches scalar coverage or string-only traces closing a DerivedClaim."""
    knowledge = _knowledge()
    claim = _claim_for_state(
        state_name="DETERMINATE",
        value=knowledge.KnowledgeValue[str](
            knowledge_state=knowledge.KnowledgeState.PRESENT,
            value="well",
            evidence_ids=("EV-CLAIM-001",),
        ),
    )
    assert claim.profile_coverage.statement_id == "PCS-001"
    assert claim.profile_coverage.contract_review.status.value == "SCIENTIFIC_REVIEW_REQUIRED"
    assert claim.profile_coverage.contract_review.issue_id == "SRR-V8-008"
    assert claim.proof_trace[0].predicate_references[0].predicate_id == "assignment_unit"

    payload = claim.model_dump(mode="json")
    payload.pop("proof_trace")
    with pytest.raises(ValidationError):
        _claims().DerivedClaim.model_validate(payload)

    payload = claim.model_dump(mode="json")
    payload["profile_coverage"] = "COVERED_WITH_KNOWN_GAPS"
    with pytest.raises(ValidationError):
        _claims().DerivedClaim.model_validate(payload)


def test_proof_trace_must_cover_every_required_predicate() -> None:
    """Catches a claim whose proof omits one of its declared prerequisites."""
    knowledge = _knowledge()
    claim = _claim_for_state(
        state_name="DETERMINATE",
        value=knowledge.KnowledgeValue[str](
            knowledge_state=knowledge.KnowledgeState.PRESENT,
            value="well",
            evidence_ids=("EV-CLAIM-001",),
        ),
    )
    payload = claim.model_dump(mode="json")
    payload["required_predicates"].append("realized_exposure_separability")
    with pytest.raises(ValidationError, match="proof_trace does not cover"):
        _claims().DerivedClaim.model_validate(payload)


@pytest.mark.parametrize(
    ("state_name", "knowledge_state"),
    [
        ("DETERMINATE", "UNKNOWN"),
        ("CONDITIONALLY_DETERMINATE", "PRESENT"),
        ("MULTIPLE_PLAUSIBLE_GRAPHS", "PRESENT"),
        ("INSUFFICIENT_INFORMATION", "PRESENT"),
        ("OUT_OF_SCOPE", "PRESENT"),
        ("INVALID_GRAPH", "PRESENT"),
        ("CONFLICTING_INFORMATION", "PRESENT"),
    ],
)
def test_explicitly_forbidden_determinability_value_combinations_are_rejected(
    state_name: str,
    knowledge_state: str,
) -> None:
    """Catches false certainty or a scientific verdict in a prohibited output state."""
    knowledge = _knowledge()
    if knowledge_state == "PRESENT":
        value = knowledge.KnowledgeValue[str](
            knowledge_state=knowledge.KnowledgeState.PRESENT,
            value="well",
            evidence_ids=("EV-CLAIM-001",),
        )
    else:
        value = knowledge.KnowledgeValue[str](
            knowledge_state=knowledge.KnowledgeState.UNKNOWN,
            rationale="The claim value is unresolved.",
            claim_scope_id="CLAIM-EU-001",
        )
    with pytest.raises(ValidationError, match="forbids this scientific value"):
        _claim_for_state(state_name=state_name, value=value)


@pytest.mark.parametrize(
    "state_name",
    [
        "CONDITIONALLY_DETERMINATE",
        "MULTIPLE_PLAUSIBLE_GRAPHS",
        "INSUFFICIENT_INFORMATION",
        "CONFLICTING_INFORMATION",
        "INVALID_GRAPH",
        "OUT_OF_SCOPE",
    ],
)
def test_unclosed_state_output_mappings_require_typed_scientific_review_blocker(
    state_name: str,
) -> None:
    """Catches Task 1 inventing a final payload mapping reserved for Task 4 review."""
    knowledge = _knowledge()
    unknown = knowledge.KnowledgeValue[str](
        knowledge_state=knowledge.KnowledgeState.UNKNOWN,
        rationale="The claim-specific output mapping remains under review.",
        claim_scope_id="CLAIM-EU-001",
    )
    with pytest.raises(ValidationError, match="SCIENTIFIC_REVIEW_REQUIRED"):
        _claim_for_state(
            state_name=state_name,
            value=unknown,
            include_review_blocker=False,
        )

    blocked = _claim_for_state(state_name=state_name, value=unknown)
    assert blocked.state_contract_review.status.value == "SCIENTIFIC_REVIEW_REQUIRED"


def test_unclosed_state_output_blocker_requires_registered_issue_id() -> None:
    """Catches an arbitrary local label masquerading as a governed review-register entry."""
    knowledge = _knowledge()
    unknown = knowledge.KnowledgeValue[str](
        knowledge_state=knowledge.KnowledgeState.UNKNOWN,
        rationale="The claim-specific output mapping remains under review.",
        claim_scope_id="CLAIM-EU-001",
    )
    with pytest.raises(ValidationError, match="registered scientific-review issue"):
        _claim_for_state(
            state_name="INSUFFICIENT_INFORMATION",
            value=unknown,
            review_issue_id="TASK4-CLAIM-STATE-OUTPUT-CONTRACT",
        )
