"""Matrice di conformita eseguibile: meccanismi SRR-V8 meccanizzabili in codice.

Ogni test sigilla un meccanismo fail-closed richiesto dal registro
``docs/audits/prd-v8-full-migration/SCIENTIFIC_REVIEW_REGISTER.md``. La chiusura
scientifiche dei blocker resta esterna: qui si verifica che il CODICE applichi
esattamente la meccanica prescritta (rifiuti, blocchi, evidenze di migrazione).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ntruth.schemas.claims import (
    CLAIM_STATE_OUTPUT_REVIEW_ISSUE_ID,
    DerivedClaim,
    DerivedClaimSet,
    DeterminabilityState,
    IrrelevantPredicate,
    ProfileCoverageReference,
    ProofTraceStep,
)
from ntruth.schemas.count_registry import CanonicalCountKind
from ntruth.schemas.kernel import KernelModel
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.report_resolution import ReportResolutionState
from ntruth.schemas.support import (
    SUPPORT_GRADE_TOKENS,
    SUPPORT_GRADE_VOCABULARY_APPENDIX_R_1,
    SUPPORT_GRADE_VOCABULARY_SECTION_0_4,
    ScientificReviewRequirement,
    SourceClassRef,
    SupportGrade,
)


def _review(issue_id: str = "SRR-V8-008") -> ScientificReviewRequirement:
    return ScientificReviewRequirement(issue_id=issue_id, rationale="conformance fixture")


def _coverage() -> ProfileCoverageReference:
    return ProfileCoverageReference(
        statement_id="st-1",
        profile_id="simple_cell_culture",
        profile_version="1.0.0",
        predicate_closure_argument_id="arg-1",
        contract_review=_review("SRR-V8-008"),
    )


def _proof(predicate_id: str = "pred-count") -> tuple[ProofTraceStep, ...]:
    return (
        ProofTraceStep(
            step_id="step-1",
            predicate_references=(
                {
                    "predicate_id": predicate_id,
                    "predicate_value": {
                        "schema_version": "8.0.0",
                        "knowledge_state": "PRESENT",
                        "value": 12,
                        "evidence_ids": ("ev-1",),
                    },
                },
            ),
            theory_clause_id="clause-A",
            rule_id="rule-A",
        ),
    )


def _claim(**overrides: object) -> DerivedClaim:
    base: dict[str, object] = {
        "claim_id": "claim-1",
        "claim_type": "experimental_unit_count",
        "inferential_query_id": "query-1",
        "value": {
            "schema_version": "8.0.0",
            "knowledge_state": "PRESENT",
            "value": 12,
            "evidence_ids": ("ev-1",),
        },
        "determinability_state": DeterminabilityState.DETERMINATE,
        "support_grade": {
            "schema_version": "8.0.0",
            "vocabulary_id": SUPPORT_GRADE_VOCABULARY_SECTION_0_4,
            "token": "ADJUDICATED",
        },
        "required_predicates": ("pred-count",),
        "irrelevant_predicates": (),
        "theory_version": "8.0.0",
        "theory_clauses": ("clause-A",),
        "ruleset_version": "ntruth-v8-core@0.1.0",
        "rule_trace": ("rule-A",),
        "proof_trace": _proof(),
        "profile_coverage": _coverage(),
    }
    base.update(overrides)
    return DerivedClaim.model_validate(base)


# ---------------------------------------------------------------------- SRR-001


def test_srr_001_support_grade_vocabularies_are_pinned_and_isolated() -> None:
    assert set(SUPPORT_GRADE_TOKENS) == {
        SUPPORT_GRADE_VOCABULARY_SECTION_0_4,
        SUPPORT_GRADE_VOCABULARY_APPENDIX_R_1,
    }
    # Token dell'appendice R.1 rifiutato nel vocabolario §0.4 e viceversa.
    with pytest.raises(ValidationError):
        SupportGrade.model_validate(
            {
                "schema_version": "8.0.0",
                "vocabulary_id": SUPPORT_GRADE_VOCABULARY_SECTION_0_4,
                "token": "DOMAIN_EXPERT_INTERPRETATION",
            }
        )
    with pytest.raises(ValidationError):
        SupportGrade.model_validate(
            {
                "schema_version": "8.0.0",
                "vocabulary_id": SUPPORT_GRADE_VOCABULARY_APPENDIX_R_1,
                "token": "ADJUDICATED",
            }
        )


def test_srr_002_query_id_legacy_key_is_rejected_not_aliased() -> None:
    payload = _claim().model_dump(mode="json")
    payload["query_id"] = payload["inferential_query_id"]
    with pytest.raises(ValidationError):
        DerivedClaim.model_validate(payload)


# ---------------------------------------------------------------------- SRR-003


def test_srr_003_required_predicates_and_rationale_are_mandatory() -> None:
    with pytest.raises(ValidationError):
        _claim(required_predicates=())
    with pytest.raises(ValidationError):
        IrrelevantPredicate(id="p", rationale="")


# ---------------------------------------------------------------------- SRR-004


def test_srr_004_determinability_field_is_the_canonical_name() -> None:
    payload = _claim().model_dump(mode="json")
    assert "determinability_state" in payload
    payload["determinability"] = payload.pop("determinability_state")
    with pytest.raises(ValidationError):
        DerivedClaim.model_validate(payload)


# ---------------------------------------------------------------------- SRR-005


def test_srr_005_report_level_state_uses_multi_scenario_token() -> None:
    tokens = {item.value for item in ReportResolutionState}
    assert "MULTI_SCENARIO" in tokens
    assert "MULTIPLE_PLAUSIBLE_GRAPHS" not in tokens


# ---------------------------------------------------------------------- SRR-007/008


def test_srr_008_profile_coverage_reference_keeps_blocker_pinned() -> None:
    with pytest.raises(ValidationError):
        ProfileCoverageReference(
            statement_id="st-1",
            profile_id="p",
            profile_version="1",
            predicate_closure_argument_id="a",
            contract_review=_review("SRR-V8-999"),
        )


# ---------------------------------------------------------------------- SRR-010


def test_srr_010_unresolved_conflict_carries_no_resolution_event() -> None:
    from ntruth.schemas.report_bundle import ConflictRecord

    field_names = set(ConflictRecord.model_fields)
    assert not any("resolution" in name for name in field_names), sorted(field_names)


# ---------------------------------------------------------------------- SRR-011


def test_srr_011_count_registry_rejects_unknown_labels() -> None:
    assert issubclass(CanonicalCountKind, str)
    with pytest.raises(ValueError):
        CanonicalCountKind("made_up_count_kind")


# ---------------------------------------------------------------------- SRR-012


def test_srr_012_partial_graph_score_stays_behind_scientific_review() -> None:
    from ntruth.graph.equality_v8 import partial_graph_score

    requirement = partial_graph_score()
    assert requirement.issue_id == "SRR-V8-012"


# ---------------------------------------------------------------------- SRR-015


def test_srr_015_source_class_unknown_requires_reason_and_registry() -> None:
    ref = SourceClassRef(
        registry_id="ntruth-source-class-v8.0",
        token="UNKNOWN_WITH_REASON",
        unknown_reason="token fuori registro in attesa di review",
    )
    assert ref.token == "UNKNOWN_WITH_REASON"
    with pytest.raises(ValidationError):
        SourceClassRef(registry_id="other-registry", token="document")
    with pytest.raises(ValidationError):
        SourceClassRef(
            registry_id="ntruth-source-class-v8.0",
            token="UNKNOWN_WITH_REASON",
        )
    with pytest.raises(ValidationError):
        SourceClassRef(registry_id="ntruth-source-class-v8.0", token="made_up_class")


# ---------------------------------------------------------------------- SRR-019


def test_srr_019_absent_explicit_requires_evidence() -> None:
    with pytest.raises(ValidationError):
        KnowledgeValue[dict](
            schema_version="8.0.0",
            knowledge_state=KnowledgeState.ABSENT_EXPLICIT,
            value=None,
        )


# ---------------------------------------------------------------------- SRR-023


@pytest.mark.parametrize(
    "state",
    [
        DeterminabilityState.CONDITIONALLY_DETERMINATE,
        DeterminabilityState.MULTIPLE_PLAUSIBLE_GRAPHS,
        DeterminabilityState.INSUFFICIENT_INFORMATION,
    ],
)
def test_srr_023_non_determinate_states_block_plain_present_payloads(state: object) -> None:
    with pytest.raises(ValidationError):
        _claim(determinability_state=state)


def test_srr_023_review_blocker_may_authorize_conditional_payload() -> None:
    claim = _claim(
        determinability_state=DeterminabilityState.INSUFFICIENT_INFORMATION,
        value={
            "schema_version": "8.0.0",
            "knowledge_state": "UNKNOWN",
            "value": None,
            "rationale": "mechanism of independence not declared",
            "evidence_ids": ("ev-1",),
            "query_scope_id": "query-1",
        },
        state_contract_review={
            "schema_version": "8.0.0",
            "status": "SCIENTIFIC_REVIEW_REQUIRED",
            "issue_id": CLAIM_STATE_OUTPUT_REVIEW_ISSUE_ID,
            "rationale": "payload contracto aperto fino a Task 4",
        },
    )
    assert claim.state_contract_review is not None


# ---------------------------------------------------------------------- integrita


def test_kernel_models_are_strict_and_frozen() -> None:
    assert KernelModel.model_config.get("extra") == "forbid"
    assert KernelModel.model_config.get("frozen") is True


def test_claim_set_enforces_single_query_scope() -> None:
    other = _claim(claim_id="claim-2", inferential_query_id="query-2")
    with pytest.raises(ValidationError):
        DerivedClaimSet(
            claim_set_id="set-1",
            inferential_query_id="query-1",
            claims=(_claim(), other),
        )
