"""Foundational PRD v8 Core Semantic Kernel contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module

import pytest
from pydantic import ValidationError


def _knowledge() -> object:
    return import_module("ntruth.schemas.knowledge")


def _support() -> object:
    return import_module("ntruth.schemas.support")


def _claims() -> object:
    return import_module("ntruth.schemas.claims")


def _kernel() -> object:
    return import_module("ntruth.schemas.kernel")


def _section_support() -> object:
    support = _support()
    return support.SupportGrade(
        vocabulary_id=support.SUPPORT_GRADE_VOCABULARY_SECTION_0_4,
        token="DIRECT_SINGLE_SOURCE",
    )


def _support_descriptor() -> object:
    support = _support()
    return support.SupportDescriptor(
        source_class=support.SourceClassRef(
            registry_id="ntruth-source-class-v8.0",
            token="document",
        ),
        authority_type=support.AuthorityType.SYSTEM_INFERENCE,
        evidence_basis=support.EvidenceBasis.DIRECT_RECORD,
        support_grade=_section_support(),
    )


def _present_value() -> object:
    knowledge = _knowledge()
    return knowledge.KnowledgeValue[dict[str, object]](
        knowledge_state=knowledge.KnowledgeState.PRESENT,
        value={"unit_type": "well"},
        evidence_ids=("EV-001",),
    )


def _derived_claim(*, claim_id: str = "CLAIM-EU-001", query_id: str = "IQ-001") -> object:
    claims = _claims()
    return claims.DerivedClaim(
        claim_id=claim_id,
        claim_type="EXPERIMENTAL_UNIT",
        inferential_query_id=query_id,
        value=_present_value(),
        determinability_state=claims.DeterminabilityState.DETERMINATE,
        support_grade=_section_support(),
        required_predicates=("assignment_unit", "assignment_separability"),
        irrelevant_predicates=(
            claims.IrrelevantPredicate(
                id="biological_source_independence",
                rationale="Not required to identify the treatment EU; used for inference scope.",
            ),
        ),
        assumptions=("record_complete_for_claim",),
        sensitivity_records=("SENS-001",),
        theory_version="derivation-theory-0.1.0",
        theory_clauses=("DT-EU-01",),
        ruleset_version="ntruth-core-0.3.0",
        rule_trace=("EU-ALLOC-001",),
        proof_trace=(
            claims.ProofTraceStep(
                step_id="PROOF-001",
                predicate_references=(
                    claims.PredicateProofReference(
                        predicate_id="assignment_unit",
                        predicate_value=_knowledge().KnowledgeValue[bool](
                            knowledge_state=_knowledge().KnowledgeState.PRESENT,
                            value=True,
                            evidence_ids=("EV-PRED-001",),
                        ),
                    ),
                    claims.PredicateProofReference(
                        predicate_id="assignment_separability",
                        predicate_value=_knowledge().KnowledgeValue[bool](
                            knowledge_state=_knowledge().KnowledgeState.PRESENT,
                            value=True,
                            evidence_ids=("EV-PRED-002",),
                        ),
                    ),
                ),
                theory_clause_id="DT-EU-01",
                rule_id="EU-ALLOC-001",
            ),
        ),
        profile_coverage=claims.ProfileCoverageReference(
            statement_id="PCS-001",
            profile_id="simple_cell_culture",
            profile_version="0.1.0",
            predicate_closure_argument_id="PCA-SCC-001",
            contract_review=claims.ScientificReviewRequirement(
                issue_id="SRR-V8-008",
                rationale="ProfileCoverageStatement shape requires Task 4 review.",
            ),
        ),
    )


def test_knowledge_state_vocabulary_is_exact_and_versioned() -> None:
    """Catches adding, removing or renaming one of the six normative states."""
    knowledge = _knowledge()
    assert {state.value for state in knowledge.KnowledgeState} == {
        "PRESENT",
        "ABSENT_EXPLICIT",
        "NOT_REPORTED",
        "UNKNOWN",
        "NOT_APPLICABLE",
        "CONFLICTING",
    }

    value = knowledge.KnowledgeValue[str](
        knowledge_state=knowledge.KnowledgeState.PRESENT,
        value="well",
        evidence_ids=("EV-001",),
    )
    assert value.schema_version == "8.0.0"
    with pytest.raises(ValidationError):
        value.value = "plate"


@pytest.mark.parametrize("scientific_value", [None, "", "   ", (), [], {}])
def test_present_rejects_null_blank_and_empty_scientific_values(
    scientific_value: object,
) -> None:
    """Catches reintroducing bare null/blank/empty as PRESENT science."""
    knowledge = _knowledge()
    with pytest.raises(ValidationError):
        knowledge.KnowledgeValue[object](
            knowledge_state=knowledge.KnowledgeState.PRESENT,
            value=scientific_value,
            evidence_ids=("EV-001",),
        )


def test_present_and_absent_explicit_require_evidence() -> None:
    """Catches unsupported presence and inferred absence from source silence."""
    knowledge = _knowledge()
    with pytest.raises(ValidationError):
        knowledge.KnowledgeValue[str](
            knowledge_state=knowledge.KnowledgeState.PRESENT,
            value="well",
        )
    with pytest.raises(ValidationError):
        knowledge.KnowledgeValue[str](
            knowledge_state=knowledge.KnowledgeState.ABSENT_EXPLICIT,
        )


def test_empty_collection_is_valid_only_with_explicit_non_present_state() -> None:
    """Catches rejecting the PRD open-world empty-list wrapper or losing its state."""
    knowledge = _knowledge()
    value = knowledge.KnowledgeValue[list[str]](
        knowledge_state=knowledge.KnowledgeState.NOT_REPORTED,
        value=[],
        source_scope_ids=("SRC-001",),
    )
    assert value.value == []
    assert value.knowledge_state is knowledge.KnowledgeState.NOT_REPORTED


def test_not_applicable_requires_rationale_and_claim_or_query_scope() -> None:
    """Catches using N/A as an unqualified synonym for missing."""
    knowledge = _knowledge()
    with pytest.raises(ValidationError):
        knowledge.KnowledgeValue[str](
            knowledge_state=knowledge.KnowledgeState.NOT_APPLICABLE,
            rationale="Not used for this derivation.",
        )
    with pytest.raises(ValidationError):
        knowledge.KnowledgeValue[str](
            knowledge_state=knowledge.KnowledgeState.NOT_APPLICABLE,
            claim_scope_id="CLAIM-EU-001",
        )

    value = knowledge.KnowledgeValue[str](
        knowledge_state=knowledge.KnowledgeState.NOT_APPLICABLE,
        rationale="Not used for this derivation.",
        claim_scope_id="CLAIM-EU-001",
    )
    assert value.value is None


def test_conflicting_requires_retained_distinct_values_and_evidence() -> None:
    """Catches conflict collapse into one preferred value."""
    knowledge = _knowledge()
    with pytest.raises(ValidationError):
        knowledge.KnowledgeValue[str](
            knowledge_state=knowledge.KnowledgeState.CONFLICTING,
            conflicting_values=("well",),
            evidence_ids=("EV-001",),
        )

    value = knowledge.KnowledgeValue[str](
        knowledge_state=knowledge.KnowledgeState.CONFLICTING,
        conflicting_values=("well", "plate"),
        evidence_ids=("EV-001", "EV-002"),
    )
    assert value.conflicting_values == ("well", "plate")


def test_support_dimensions_are_orthogonal_and_vocabularies_are_not_collapsed() -> None:
    """Catches linear ranking or cross-vocabulary SupportGrade aliases."""
    support = _support()
    descriptor = _support_descriptor()
    assert descriptor.source_class.token == "document"
    assert descriptor.authority_type.value == "SYSTEM_INFERENCE"
    assert descriptor.evidence_basis.value == "DIRECT_RECORD"
    assert descriptor.support_grade.token == "DIRECT_SINGLE_SOURCE"

    appendix_grade = support.SupportGrade(
        vocabulary_id=support.SUPPORT_GRADE_VOCABULARY_APPENDIX_R_1,
        token="ADJUDICATED_REFERENCE",
    )
    assert appendix_grade.vocabulary_id != descriptor.support_grade.vocabulary_id
    with pytest.raises(ValidationError):
        support.SupportGrade(
            vocabulary_id=support.SUPPORT_GRADE_VOCABULARY_SECTION_0_4,
            token="ADJUDICATED_REFERENCE",
        )


def test_unknown_source_class_requires_reason() -> None:
    """Catches silently ranking or normalizing an unreviewed source class."""
    support = _support()
    with pytest.raises(ValidationError):
        support.SourceClassRef(
            registry_id="ntruth-source-class-v8.0",
            token="UNKNOWN_WITH_REASON",
        )
    source_class = support.SourceClassRef(
        registry_id="ntruth-source-class-v8.0",
        token="UNKNOWN_WITH_REASON",
        unknown_reason="Source token is not yet in the reviewed registry.",
    )
    assert source_class.unknown_reason

    with pytest.raises(ValidationError):
        support.SourceClassRef(
            registry_id="ntruth-source-class-v8.0",
            token="unreviewed_device_record",
        )


def test_source_evidence_and_confirmation_preserve_source_to_reality_context() -> None:
    """Catches planned evidence being serialized as executed evidence."""
    support = _support()
    source = support.SourceRecord(
        source_id="SRC-001",
        source_class=support.SourceClassRef(
            registry_id="ntruth-source-class-v8.0",
            token="sample_sheet",
        ),
        source_context=support.SourceContext.PLANNED,
        source_version="plan-v1",
    )
    evidence = support.EvidenceRecord(
        evidence_id="EV-001",
        source_id=source.source_id,
        evidence_type=support.EvidenceTypeV8.SAMPLE_METADATA_PLANNED,
        locator="samples.csv!rows:2-5",
        original_text="planned wells W1-W4",
    )
    confirmation = support.ConfirmationEvent(
        event_id="CONF-001",
        support=_support_descriptor().model_copy(
            update={"authority_type": support.AuthorityType.AUTHOR_CLARIFICATION}
        ),
        evidence_refs=(evidence.evidence_id,),
        scope_id="PRED-ASSIGN-SEPARABLE",
        confirmed_value=_knowledge().KnowledgeValue[bool](
            knowledge_state=_knowledge().KnowledgeState.PRESENT,
            value=True,
            evidence_ids=(evidence.evidence_id,),
        ),
        actor_role="experiment_owner",
        review_independent=False,
        sensitivity_record_ids=("SENS-001",),
        created_at=datetime(2026, 8, 8, 12, 0, tzinfo=UTC),
    )
    assert source.source_context is support.SourceContext.PLANNED
    assert confirmation.support.support_grade.token == "DIRECT_SINGLE_SOURCE"


def test_confirmation_cannot_treat_rule_derivation_as_factual_authority() -> None:
    """Catches a Rulebook output being recorded as a human/factual confirmation."""
    support = _support()
    descriptor = _support_descriptor().model_copy(
        update={"authority_type": support.AuthorityType.RULE_DERIVATION}
    )
    with pytest.raises(ValidationError, match="RULE_DERIVATION"):
        support.ConfirmationEvent(
            event_id="CONF-RULE-001",
            support=descriptor,
            evidence_refs=("EV-RULE-001",),
            scope_id="PRED-ASSIGN-SEPARABLE",
            confirmed_value=_knowledge().KnowledgeValue[bool](
                knowledge_state=_knowledge().KnowledgeState.PRESENT,
                value=True,
                evidence_ids=("EV-RULE-001",),
            ),
            actor_role="rule_engine",
            review_independent=False,
            created_at=datetime(2026, 8, 8, 12, 0, tzinfo=UTC),
        )


def test_sensitivity_rule_challenge_and_ledger_are_append_only() -> None:
    """Catches direct overwrite or loss of epistemic event history."""
    support = _support()
    sensitivity = support.SensitivityRecord(
        sensitivity_id="SENS-001",
        derived_claim_id="CLAIM-N-001",
        decisive_predicate_id="PRED-INDEP-001",
        current_support_grade=_section_support(),
        current_value=True,
        counterfactual_value=False,
        current_output={"experimental_unit_count": 4},
        counterfactual_output={"experimental_unit_count": 1},
        interpretation="The count depends entirely on this confirmation.",
    )
    challenge = support.RuleChallenge(
        challenge_id="CHAL-001",
        derived_claim_id="CLAIM-N-001",
        frozen_claim_checksum="a" * 64,
        theory_version="derivation-theory-0.1.0",
        theory_clause_ids=("DT-EU-01",),
        ruleset_version="ntruth-core-0.3.0",
        rule_ids=("EU-ALLOC-001",),
        rationale="The assignment-separability premise is not supported.",
        actor_role="domain_expert",
        created_at=datetime(2026, 8, 8, 12, 0, tzinfo=UTC),
    )
    assert challenge.review_status.value == "SCIENTIFIC_REVIEW_REQUIRED"
    assert challenge.status.value == "OPEN"

    ledger = support.EpistemicEventLedger(ledger_id="LEDGER-001")
    updated = ledger.append_sensitivity(sensitivity).append_rule_challenge(challenge)
    assert ledger.sensitivity_records == ()
    assert updated.sensitivity_records == (sensitivity,)
    with pytest.raises(ValueError, match="append-only"):
        updated.append_rule_challenge(challenge)


def test_sensitivity_rejects_blank_or_empty_scientific_values() -> None:
    """Catches reintroducing blank scientific values outside KnowledgeValue."""
    support = _support()
    with pytest.raises(ValidationError):
        support.SensitivityRecord(
            sensitivity_id="SENS-EMPTY",
            derived_claim_id="CLAIM-N-001",
            decisive_predicate_id="PRED-INDEP-001",
            current_support_grade=_section_support(),
            current_value="",
            counterfactual_value=False,
            current_output={"experimental_unit_count": 4},
            counterfactual_output={"experimental_unit_count": 1},
            interpretation="Invalid blank current value.",
        )


def test_derived_claim_is_query_scoped_strict_and_round_trips() -> None:
    """Catches legacy query aliases, missing predicate rationale or mutable claims."""
    claims = _claims()
    claim = _derived_claim()
    restored = claims.DerivedClaim.model_validate_json(claim.model_dump_json())
    assert restored == claim
    with pytest.raises(ValidationError):
        claim.claim_type = "EXPERIMENTAL_UNIT_COUNT"

    payload = claim.model_dump(mode="json")
    payload["query_id"] = payload.pop("inferential_query_id")
    with pytest.raises(ValidationError):
        claims.DerivedClaim.model_validate(payload)


def test_derived_claim_uses_normative_sensitivity_and_irrelevant_predicate_keys() -> None:
    """Catches drift from the canonical §10.2 field names."""
    payload = _derived_claim().model_dump(mode="json")
    assert "sensitivity_records" in payload
    assert "sensitivity_record_ids" not in payload
    assert payload["irrelevant_predicates"][0]["id"] == "biological_source_independence"
    assert "predicate_id" not in payload["irrelevant_predicates"][0]


def test_derived_claim_set_rejects_cross_query_claims() -> None:
    """Catches aggregation of claims from different inferential questions."""
    claims = _claims()
    with pytest.raises(ValidationError, match="inferential_query_id"):
        claims.DerivedClaimSet(
            claim_set_id="CLAIMSET-001",
            inferential_query_id="IQ-001",
            claims=(
                _derived_claim(claim_id="CLAIM-001", query_id="IQ-001"),
                _derived_claim(claim_id="CLAIM-002", query_id="IQ-002"),
            ),
        )


def test_kernel_json_schemas_are_strict_and_exportable(tmp_path: object) -> None:
    """Catches permissive schemas or an export that drifts from runtime models."""
    from pathlib import Path

    kernel = _kernel()
    schemas = kernel.kernel_json_schemas()
    assert {
        "knowledge_value",
        "source_record",
        "evidence_record",
        "confirmation_event",
        "sensitivity_record",
        "rule_challenge",
        "derived_claim",
        "derived_claim_set",
    } <= set(schemas)
    assert all(schema["additionalProperties"] is False for schema in schemas.values())

    written = kernel.write_kernel_json_schemas(Path(str(tmp_path)))
    assert set(written) == set(schemas)
    assert all(path.is_file() for path in written.values())


def test_kernel_contracts_are_public_schema_exports() -> None:
    """Catches a runtime contract that cannot be imported through ntruth.schemas."""
    schemas = import_module("ntruth.schemas")
    for name in (
        "KnowledgeState",
        "KnowledgeValue",
        "SourceClassRef",
        "EvidenceBasis",
        "SupportGrade",
        "ConfirmationEvent",
        "SensitivityRecord",
        "RuleChallenge",
        "DerivedClaim",
        "DerivedClaimSet",
        "kernel_json_schemas",
        "write_kernel_json_schemas",
    ):
        assert hasattr(schemas, name), name
