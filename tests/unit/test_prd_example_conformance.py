"""Conformance dei esempi normativi del PRD v8.0 (PRD §26.9).

Ogni esempio YAML/JSON del PRD e' estratto verbatim in
``tests/fixtures/prd_v8_examples/`` e validato contro gli schema v8
(``ntruth.schemas.kernel``, ``ntruth.schemas.claims``, count registry v8).

Regole di conformance:
- gli esempi NON vengono indeboliti per adattarli al codice;
- i token ``A|B|C`` negli esempi sono alternative normative: ogni token deve
  appartenere all'enum corrispondente e la validazione usa il primo token;
- le discrepanze interne al PRD sono finding documentati (registro SRR e
  report di migrazione), mai risolte inventando contenuto scientifico.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from ntruth.schemas.claims import (
    ClaimType,
    ConditionalClaimOutput,
    DerivedClaim,
    DerivedClaimSet,
    DesignAdequacyFinding,
    ReportResolutionState,
    aggregate_report_resolution,
)
from ntruth.schemas.core import Determinability
from ntruth.schemas.experiment import COUNT_KIND_V8_WIRE, CountKind, CountQuantifier
from ntruth.schemas.kernel import (
    AuthorityType,
    BlockBoundaryRecord,
    BlockBoundaryStatus,
    ChallengeSourceClass,
    ConditionRecord,
    ConfirmationEvent,
    ConflictRecord,
    ConflictStatus,
    ContaminationAttestation,
    EventTiming,
    EvidenceBasis,
    InferentialQuery,
    KnowledgeState,
    KnowledgeValue,
    ProfileCoverageStatus,
    RuleChallenge,
    RuleChallengeStatus,
    ScenarioCoverage,
    ScenarioCoverageStatus,
    SensitivityRecord,
    SourceClass,
    SupportGrade,
    TextExposureRisk,
    TimingRelation,
    V8CountRecord,
)

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "prd_v8_examples"

#: Inventario completo degli esempi normativi estratti (nome file -> provenienza PRD).
PRD_EXAMPLE_FILES: dict[str, str] = {
    "section_0_7_reality_gate.yaml": "PRD §0.7 Reality Gate v8",
    "section_2_4_contexts.yaml": "PRD §2.4 causal/exposure/measurement context",
    "section_7_7_relative_timing.yaml": "PRD §7.7 eventi e timing referenziato",
    "section_7_8_inferential_query.yaml": "PRD §7.8 InferentialQuery",
    "section_8_6_block_boundary.yaml": "PRD §8.6 block boundary record",
    "section_8_7_confirmation_event.yaml": "PRD §8.7 confirmation event",
    "section_8_7_conflict_record.yaml": "PRD §8.7 conflict record",
    "section_8_7_rule_challenge.yaml": "PRD §8.7 rule challenge",
    "section_9_5_confounded_with.yaml": "PRD §9.5 KnowledgeState example",
    "section_9_7_sensitivity_record.yaml": "PRD §9.7 SensitivityRecord",
    "section_10_2_derived_claim.yaml": "PRD §10.2 DerivedClaim",
    "section_10_6_conditional_output.json": "PRD §10.6 output condizionale",
    "section_10_7_scenario_coverage.yaml": "PRD §10.7 ScenarioCoverage",
    "section_10_12_condition_record.yaml": "PRD §10.12 ConditionRecord",
    "section_15_10_count_record.yaml": "PRD §15.10 count scope-aware",
    "appendix_a_experiment_bundle.yaml": "PRD Appendice A bundle completo",
    "appendix_af_derived_claim.yaml": "PRD Appendice AF DerivedClaim/ReportBundle",
    "appendix_ag_contamination_attestation.yaml": "PRD Appendice AG attestation",
    "appendix_p_4_event_timing.yaml": "PRD Appendice P.4 event timing",
}


def load_fixture(name: str) -> Any:
    """Carica un esempio normativo preservando il contenuto verbatim."""
    raw = (FIXTURE_DIR / name).read_text(encoding="utf-8")
    if name.endswith(".json"):
        stripped = [line for line in raw.splitlines() if not line.lstrip().startswith("//")]
        return json.loads("\n".join(stripped))
    return yaml.safe_load(raw)


def resolve_alternatives(payload: Any) -> Any:
    """Risolve i token alternativa ``A|B|C`` selezionando il primo token.

    Gli esempi PRD usano ``|`` per elencare le alternative normative di un
    campo; la validazione dello schema richiede un valore singolo.
    """
    if isinstance(payload, str) and "|" in payload:
        return payload.split("|", 1)[0]
    if isinstance(payload, list):
        return [resolve_alternatives(item) for item in payload]
    if isinstance(payload, dict):
        return {key: resolve_alternatives(value) for key, value in payload.items()}
    return payload


def alternative_tokens(payload: Any) -> list[tuple[str, tuple[str, ...]]]:
    """Raccoglie i campi con alternative ``A|B|C`` come (path, token)."""
    found: list[tuple[str, tuple[str, ...]]] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, str) and "|" in node:
            found.append((path, tuple(node.split("|"))))
        elif isinstance(node, list):
            for index, item in enumerate(node):
                walk(item, f"{path}[{index}]")
        elif isinstance(node, dict):
            for key, value in node.items():
                walk(value, f"{path}.{key}" if path else str(key))

    walk(payload, "")
    return found


# ---------------------------------------------------------------------------
# Inventario e parsing
# ---------------------------------------------------------------------------


def test_fixture_inventory_matches_disk() -> None:
    on_disk = {path.name for path in FIXTURE_DIR.glob("*") if not path.name.startswith(".")}
    assert on_disk == set(PRD_EXAMPLE_FILES)


@pytest.mark.parametrize("name", sorted(PRD_EXAMPLE_FILES))
def test_fixture_parses(name: str) -> None:
    payload = load_fixture(name)
    assert isinstance(payload, dict) and payload


# ---------------------------------------------------------------------------
# §0.7 Reality Gate (strutturale: il contratto operativo arriva in FASE 6)
# ---------------------------------------------------------------------------


def test_reality_gate_structure() -> None:
    payload = load_fixture("section_0_7_reality_gate.yaml")
    assert len(payload) == 15
    assert payload["blocking_schema_gaps"] == 0
    for key, value in payload.items():
        if key != "blocking_schema_gaps":
            assert value is True, key


# ---------------------------------------------------------------------------
# §2.4 context (token normativi, nessun modello kernel in FASE 1)
# ---------------------------------------------------------------------------


def test_section_2_4_context_tokens() -> None:
    payload = load_fixture("section_2_4_contexts.yaml")
    assignment = payload["assignment_context"]
    mechanism_tokens = assignment["mechanism"].split("|")
    assert mechanism_tokens == [
        "random",
        "blocked_random",
        "matched",
        "manual",
        "convenience",
        "unknown",
    ]
    for token in assignment["separability_state"].split("|"):
        assert KnowledgeState(token)
    exposure = payload["exposure_context"]
    assert exposure["interference_status"].split("|") == [
        "no_known_path",
        "possible",
        "documented",
        "unknown",
    ]
    relative = payload["application_context"]["relative_to_event"]
    assert TimingRelation(relative["relation"]) is TimingRelation.AFTER


# ---------------------------------------------------------------------------
# Timing eventi (§7.7, Appendice P.4, Appendice A)
# ---------------------------------------------------------------------------


def test_section_7_7_relative_timing() -> None:
    payload = resolve_alternatives(load_fixture("section_7_7_relative_timing.yaml"))
    timing = EventTiming.model_validate(payload["relative_timing"])
    assert timing.subject_event_id == "EVT-APPLY-01"
    assert timing.relation is TimingRelation.BEFORE


def test_appendix_p_4_event_timing() -> None:
    payload = resolve_alternatives(load_fixture("appendix_p_4_event_timing.yaml"))
    timing = EventTiming.model_validate(payload["timing"])
    assert timing.reference_event_id == "SPLIT-02"
    assert timing.subject_event_id is None


# ---------------------------------------------------------------------------
# InferentialQuery (§7.8 e Appendice A)
# ---------------------------------------------------------------------------


def test_section_7_8_inferential_query() -> None:
    payload = resolve_alternatives(load_fixture("section_7_8_inferential_query.yaml"))
    query = InferentialQuery.model_validate(payload["inferential_query"])
    assert query.id == "IQ-001"
    assert query.profile_id == "simple_cell_culture"
    assert query.compared_levels == ("vehicle", "drug_x")
    assert query.estimand == "mean_difference"


def test_appendix_a_inferential_query_knowledge_wrapped() -> None:
    bundle = load_fixture("appendix_a_experiment_bundle.yaml")
    query = InferentialQuery.model_validate(bundle["inferential_query"])
    assert query.id == "IQ-001"
    assert isinstance(query.estimand, KnowledgeValue)
    assert query.estimand.knowledge_state is KnowledgeState.PRESENT
    assert query.estimand.value == "mean_difference"
    assert query.timepoint == "48h"


# ---------------------------------------------------------------------------
# Block boundary, confirmation, conflict, rule challenge (§8.6, §8.7)
# ---------------------------------------------------------------------------


def test_section_8_6_block_boundary() -> None:
    raw = load_fixture("section_8_6_block_boundary.yaml")["block_boundary"]
    for token in raw["status"].split("|"):
        assert BlockBoundaryStatus(token)
    record = BlockBoundaryRecord.model_validate(resolve_alternatives(raw))
    assert record.block_id == "EB-01"
    assert record.boundary_basis == (
        "distinct_assignment_history",
        "distinct_source_population",
    )


def test_section_8_7_confirmation_event() -> None:
    raw = load_fixture("section_8_7_confirmation_event.yaml")["confirmation_event"]
    event = ConfirmationEvent.model_validate(raw)
    assert event.authority_type is AuthorityType.AUTHOR_CLARIFICATION
    assert event.evidence_basis is EvidenceBasis.SELF_REPORT
    assert event.support_grade is SupportGrade.AUTHOR_CLARIFIED


def test_section_8_7_conflict_record() -> None:
    raw = load_fixture("section_8_7_conflict_record.yaml")["conflict_record"]
    for token in raw["status"].split("|"):
        assert ConflictStatus(token)
    record = ConflictRecord.model_validate(resolve_alternatives(raw))
    assert record.status is ConflictStatus.UNRESOLVED
    assert record.resolution_event is not None
    assert record.resolution_event.knowledge_state is KnowledgeState.NOT_APPLICABLE
    assert record.resolution_event.rationale


def test_section_8_7_rule_challenge() -> None:
    raw = load_fixture("section_8_7_rule_challenge.yaml")["rule_challenge"]
    for token in raw["status"].split("|"):
        assert RuleChallengeStatus(token)
    challenge = RuleChallenge.model_validate(resolve_alternatives(raw))
    assert challenge.challenger_role is AuthorityType.DOMAIN_EXPERT_REVIEW
    assert challenge.challenged_clause == "DT-EU-04"


# ---------------------------------------------------------------------------
# KnowledgeState / KnowledgeValue (§9.5, Appendice AC)
# ---------------------------------------------------------------------------


def test_section_9_5_confounded_with() -> None:
    payload = load_fixture("section_9_5_confounded_with.yaml")["confounded_with"]
    wrapped = KnowledgeValue[Any].model_validate(payload)
    assert wrapped.knowledge_state is KnowledgeState.NOT_REPORTED
    assert wrapped.items == ()
    assert wrapped.source_scope == ("methods_01", "sample_sheet_01")


def test_knowledge_value_states_match_prd_table() -> None:
    assert {state.value for state in KnowledgeState} == {
        "PRESENT",
        "ABSENT_EXPLICIT",
        "NOT_REPORTED",
        "UNKNOWN",
        "NOT_APPLICABLE",
        "CONFLICTING",
    }


def test_knowledge_value_forbids_bare_null_and_empty_semantics() -> None:
    with pytest.raises(ValidationError):
        KnowledgeValue[Any].model_validate(None)
    with pytest.raises(ValidationError):
        KnowledgeValue[Any].model_validate({"knowledge_state": "PRESENT", "value": ""})
    with pytest.raises(ValidationError):
        KnowledgeValue[Any].model_validate({"knowledge_state": "PRESENT"})


def test_knowledge_value_state_specific_requirements() -> None:
    # Appendice AC: NOT_APPLICABLE richiede rationale.
    with pytest.raises(ValidationError):
        KnowledgeValue[Any].model_validate({"knowledge_state": "NOT_APPLICABLE"})
    # Appendice AC: ABSENT_EXPLICIT richiede evidence.
    with pytest.raises(ValidationError):
        KnowledgeValue[Any].model_validate({"knowledge_state": "ABSENT_EXPLICIT", "items": []})
    # CONFLICTING richiede la lista dei valori incompatibili.
    with pytest.raises(ValidationError):
        KnowledgeValue[Any].model_validate({"knowledge_state": "CONFLICTING"})
    valid = KnowledgeValue[Any].model_validate(
        {
            "knowledge_state": "CONFLICTING",
            "items": [4, 6],
            "source_scope": ["methods_01", "sheet_01"],
        }
    )
    assert valid.items == (4, 6)


def test_knowledge_value_legacy_migration_rules() -> None:
    migrated = KnowledgeValue.migrate_legacy(None, legacy_field="n_planned")
    assert migrated.knowledge_state is KnowledgeState.NOT_REPORTED
    assert migrated.migration_note
    unknown = KnowledgeValue.migrate_legacy(None, legacy_field="assignment_mechanism")
    assert unknown.knowledge_state is KnowledgeState.UNKNOWN
    assert unknown.migration_note
    with pytest.raises(ValueError, match="field-specific"):
        KnowledgeValue.migrate_legacy(None, legacy_field="never_seen_field")
    present = KnowledgeValue.migrate_legacy(3, legacy_field="n_planned")
    assert present.knowledge_state is KnowledgeState.PRESENT
    assert present.value == 3


# ---------------------------------------------------------------------------
# SensitivityRecord (§9.7)
# ---------------------------------------------------------------------------


def test_section_9_7_sensitivity_record() -> None:
    payload = load_fixture("section_9_7_sensitivity_record.yaml")["sensitivity_record"]
    record = SensitivityRecord.model_validate(payload)
    assert record.current_support_grade is SupportGrade.SELF_REPORT_ONLY
    assert record.current_output == {"experimental_unit_count": 4}
    assert record.counterfactual_output == {"experimental_unit_count": 1}
    assert record.current_value is True and record.counterfactual_value is False


# ---------------------------------------------------------------------------
# DerivedClaim (§10.2, Appendice AF, Appendice A)
# ---------------------------------------------------------------------------


def test_section_10_2_derived_claim() -> None:
    payload = load_fixture("section_10_2_derived_claim.yaml")["derived_claim"]
    claim = DerivedClaim.model_validate(payload)
    assert claim.claim_id == "CLAIM-EU-001"
    assert claim.claim_type is ClaimType.EXPERIMENTAL_UNIT
    assert claim.query_id == "IQ-001"
    assert claim.determinability_state is Determinability.DETERMINATE
    assert claim.support_grade is SupportGrade.DIRECT_SINGLE_SOURCE
    # §10.2 non espone knowledge_state nel value: la normalizzazione lo marca
    # PRESENT in modo esplicito (mai silenzio implicito).
    assert claim.value.knowledge_state is KnowledgeState.PRESENT
    assert claim.value.value == {"unit_type": "well"}
    assert claim.value.migration_note
    assert claim.irrelevant_predicates[0].predicate_id == "biological_source_independence"
    assert claim.irrelevant_predicates[0].rationale
    assert claim.profile_coverage.status is ProfileCoverageStatus.COVERED_WITH_KNOWN_GAPS


def test_appendix_af_derived_claim() -> None:
    payload = load_fixture("appendix_af_derived_claim.yaml")["derived_claim"]
    claim = DerivedClaim.model_validate(payload)
    assert claim.value.knowledge_state is KnowledgeState.PRESENT
    assert claim.value.value == {"unit_type": "well"}
    assumption = claim.assumptions[0]
    assert not isinstance(assumption, str)
    assert assumption.predicate_id == "PRED-ASSIGN-SEPARABLE"
    assert assumption.authority_event_id == "CONF-001"
    assert claim.ruleset_version == "ntruth-core-0.3.0"
    assert claim.profile_coverage.status is ProfileCoverageStatus.COVERED_WITH_KNOWN_GAPS
    assert claim.profile_coverage.known_gaps == ("interference_pathway_not_observed",)


def test_appendix_a_derived_claims() -> None:
    bundle = load_fixture("appendix_a_experiment_bundle.yaml")
    claims = [DerivedClaim.model_validate(raw) for raw in bundle["derived_claims"]]
    assert [claim.claim_id for claim in claims] == [
        "CLAIM-EU-01",
        "CLAIM-SOURCE-01",
        "CLAIM-ADEQUACY-01",
    ]
    assert claims[0].determinability_state is Determinability.MULTIPLE_PLAUSIBLE_GRAPHS
    assert claims[0].support_grade is SupportGrade.MIXED_UNRESOLVED
    assert claims[1].support_grade is SupportGrade.NOT_SUPPORTED
    assert claims[2].claim_type is ClaimType.DESIGN_ADEQUACY_FINDING
    for claim in claims:
        assert claim.value.knowledge_state is KnowledgeState.UNKNOWN


def test_claim_types_match_prd_examples() -> None:
    assert {kind.value for kind in ClaimType} == {
        "EXPERIMENTAL_UNIT",
        "EXPERIMENTAL_UNIT_COUNT",
        "BIOLOGICAL_SOURCE_COUNT",
        "DESIGN_ADEQUACY_FINDING",
    }


def test_support_grade_union_covers_all_prd_lists() -> None:
    # Unione verbatim di §0.4, Appendice R.1 ed esempi normativi (SRR-0005).
    section_0_4 = {
        "ADJUDICATED",
        "CORROBORATED_DIRECT",
        "DIRECT_SINGLE_SOURCE",
        "AUTHOR_CLARIFIED",
        "SELF_REPORT_ONLY",
        "ASSERTION_ONLY",
        "MODEL_CANDIDATE",
        "CONFLICTED",
    }
    appendix_r_1 = {
        "ADJUDICATED_REFERENCE",
        "CORROBORATED_EXECUTION_RECORD",
        "AUTHOR_CLARIFIED",
        "DOMAIN_EXPERT_INTERPRETATION",
        "SELF_REPORT_ONLY",
        "DOCUMENT_ASSERTION_ONLY",
        "MODEL_CANDIDATE_ONLY",
        "MIXED_UNRESOLVED",
    }
    examples = {"NOT_SUPPORTED", "DIRECT_SINGLE_SOURCE"}
    expected = section_0_4 | appendix_r_1 | examples
    assert {grade.value for grade in SupportGrade} == expected


def test_derived_claim_set_keyed_to_query() -> None:
    bundle = load_fixture("appendix_a_experiment_bundle.yaml")
    claim_set = DerivedClaimSet(
        query_id="IQ-001",
        claims=tuple(DerivedClaim.model_validate(raw) for raw in bundle["derived_claims"]),
    )
    assert len(claim_set.claims) == 3
    with pytest.raises(ValidationError):
        DerivedClaimSet(
            query_id="IQ-002",
            claims=(DerivedClaim.model_validate(bundle["derived_claims"][0]),),
        )


# ---------------------------------------------------------------------------
# Output condizionale (§10.6) e ConditionRecord (§10.12)
# ---------------------------------------------------------------------------


def test_section_10_6_conditional_output() -> None:
    payload = load_fixture("section_10_6_conditional_output.json")
    output = ConditionalClaimOutput.model_validate(payload)
    assert output.claim_type is ClaimType.EXPERIMENTAL_UNIT_COUNT
    assert output.determinability_state is Determinability.CONDITIONALLY_DETERMINATE
    assert output.scenario_coverage is ScenarioCoverageStatus.EXHAUSTIVE_WITHIN_PROFILE
    assert len(output.branches) == 2
    assert all(branch.condition.strip() for branch in output.branches)
    assert output.branches[0].output == {"control": 4, "drug": 4}
    assert output.primary_question
    assert output.theory_clause == "DT-EU-04"


def test_section_10_12_condition_record() -> None:
    payload = load_fixture("section_10_12_condition_record.yaml")["condition_record"]
    record = ConditionRecord.model_validate(payload)
    assert record.predicate == "independent_preparations_before_assignment"
    assert record.human_readable["it"] and record.human_readable["en"]
    assert record.primary_question_id == "Q-001"
    assert record.scenario_coverage is ScenarioCoverageStatus.EXHAUSTIVE_WITHIN_PROFILE


# ---------------------------------------------------------------------------
# ScenarioCoverage (§10.7)
# ---------------------------------------------------------------------------


def test_scenario_coverage_statuses_match_prd() -> None:
    assert {status.value for status in ScenarioCoverageStatus} == {
        "EXHAUSTIVE_WITHIN_PROFILE",
        "NON_EXHAUSTIVE",
        "UNKNOWN",
    }


def test_section_10_7_scenario_coverage_core_fields() -> None:
    raw = load_fixture("section_10_7_scenario_coverage.yaml")["scenario_coverage"]
    for token in raw["status"].split("|"):
        assert ScenarioCoverageStatus(token)
    core = {
        key: value
        for key, value in resolve_alternatives(raw).items()
        if key not in {"omitted_dimensions", "caveat"}
    }
    coverage = ScenarioCoverage.model_validate(core)
    assert coverage.status is ScenarioCoverageStatus.EXHAUSTIVE_WITHIN_PROFILE
    assert coverage.emitting_clauses == ("DT-EU-04", "DT-EXP-02")


def test_section_10_7_example_violates_appendix_ac_strict_rules() -> None:
    """FINDING (SRR-0008): §10.7 omette evidence/rationale richiesti da AC.

    ``omitted_dimensions`` usa ABSENT_EXPLICIT senza evidence e ``caveat`` usa
    NOT_APPLICABLE senza rationale: il contratto fail-closed applica le regole
    dell'Appendice AC e rifiuta i due sotto-campi dell'esempio.
    """
    raw = load_fixture("section_10_7_scenario_coverage.yaml")["scenario_coverage"]
    with pytest.raises(ValidationError):
        KnowledgeValue[Any].model_validate(raw["omitted_dimensions"])
    with pytest.raises(ValidationError):
        KnowledgeValue[Any].model_validate(raw["caveat"])
    with pytest.raises(ValidationError):
        ScenarioCoverage.model_validate(resolve_alternatives(raw))


# ---------------------------------------------------------------------------
# Count registry v8 (§15.10, Appendice A, Appendice P)
# ---------------------------------------------------------------------------


def test_section_15_10_count_record() -> None:
    payload = load_fixture("section_15_10_count_record.yaml")
    record = V8CountRecord.model_validate(payload)
    assert record.kind is CountKind.EXPERIMENTAL_UNIT_COUNT
    assert record.knowledge_state is KnowledgeState.PRESENT
    assert record.value == 6
    assert record.quantifier is CountQuantifier.EXACT
    assert record.source_evidence == ("EV-01", "EV-02", "EV-03")
    assert record.rule_trace == ("EU-ALLOC-001", "COUNT-004")
    # Il wire v8 ri-serializza il naming canonico §7.9 verbatim.
    dumped = record.model_dump(mode="json")
    assert dumped["kind"] == payload["kind"] == "experimental_unit_count"


def test_appendix_a_counts() -> None:
    bundle = load_fixture("appendix_a_experiment_bundle.yaml")
    declared, observational = (V8CountRecord.model_validate(raw) for raw in bundle["counts"])
    assert declared.kind is CountKind.DECLARED_N
    assert declared.value == 3
    assert declared.query_id == "IQ-001"
    assert declared.cohort_id == "COHORT-01"
    assert declared.group_id == "ALL"
    assert declared.scope_status is not None
    assert isinstance(declared.unit_type, KnowledgeValue)
    assert declared.unit_type.value == "experiment_run"
    assert observational.knowledge_state is KnowledgeState.NOT_REPORTED
    assert observational.value is None
    assert observational.quantifier is CountQuantifier.NOT_REPORTED


def test_count_kind_union_covers_prd_vocabularies() -> None:
    # §7.9, Appendice P.1, §15.10 e vocabolario v6 (SRR-0006).
    section_7_9 = {
        "declared_n",
        "planned_unit_count",
        "allocated_unit_count",
        "treated_unit_count",
        "observed_unit_count",
        "excluded_unit_count",
        "analyzed_unit_count",
        "observational_measurement_count",
        "analytical_row_count",
        "experimental_unit_count",
        "biological_source_count",
        "diagnostic_effective_n",
    }
    appendix_p_1 = {
        "planned_n",
        "allocated_n",
        "treated_n",
        "observed_n",
        "excluded_n",
        "analyzed_n",
        "declared_n",
        "observational_n",
        "analytical_n",
        "experimental_unit_count",
        "biological_source_count",
        "effective_n_diagnostic",
        "independent_n",
    }
    # AE.1: i valori serializzati restano quelli v6 congelati.
    frozen_v6_values = {
        "planned_n",
        "allocated_n",
        "treated_n",
        "observed_n",
        "excluded_n",
        "analysed_n",
        "declared_n",
        "observational_n",
        "analytical_n",
        "independent_n",
        "biological_source_count",
        "effective_n",
    }
    canonical_values = {member.value for member in CountKind}
    assert canonical_values == frozen_v6_values
    # Entrambi i vocabolari restano caricabili (alias + _missing_).
    for token in section_7_9 | appendix_p_1:
        assert CountKind(token), token
    # Alias: stessa identita di membro, valore serializzato congelato.
    assert CountKind("independent_n") is CountKind.EXPERIMENTAL_UNIT_COUNT
    assert CountKind("experimental_unit_count") is CountKind.INDEPENDENT_N
    assert CountKind("planned_n") is CountKind.PLANNED_UNIT_COUNT
    assert CountKind("effective_n") is CountKind.DIAGNOSTIC_EFFECTIVE_N
    assert CountKind("effective_n_diagnostic") is CountKind.DIAGNOSTIC_EFFECTIVE_N
    assert CountKind.EXPERIMENTAL_UNIT_COUNT.value == "independent_n"
    # Il naming canonico v8 vive solo nella mappa wire usata da V8CountRecord.
    assert set(COUNT_KIND_V8_WIRE.values()) == section_7_9
    assert set(COUNT_KIND_V8_WIRE) == set(CountKind)


# ---------------------------------------------------------------------------
# ContaminationAttestation (Appendice AG)
# ---------------------------------------------------------------------------


def test_appendix_ag_contamination_attestation() -> None:
    raw = load_fixture("appendix_ag_contamination_attestation.yaml")
    for token in raw["source_class"].split("|"):
        assert ChallengeSourceClass(token)
    for token in raw["text_exposure_risk"].split("|"):
        assert TextExposureRisk(token)
    attestation = ContaminationAttestation.model_validate(resolve_alternatives(raw))
    assert attestation.challenge_item_id == "ECH-001"
    assert attestation.source_class is ChallengeSourceClass.PROSPECTIVE_PRIVATE
    assert attestation.publication_or_creation_date == dt.date(2026, 9, 1)
    assert attestation.training_eligible is False
    assert attestation.model_selection_eligible is False
    assert attestation.backbone.model_id == "ibm-granite/granite-4.1-3b"
    assert attestation.backbone.release_date == "2026-XX-XX"
    assert attestation.backbone.documented_training_cutoff.knowledge_state is KnowledgeState.UNKNOWN
    assert attestation.text_exposure_risk is TextExposureRisk.LOW
    assert attestation.exposure_assessment.probes_run == ()
    assert attestation.permitted_claim == ("project_pipeline_generalization",)
    assert attestation.forbidden_claim == ("proof_of_no_pretraining_exposure",)


# ---------------------------------------------------------------------------
# ReportResolutionState (§10.4) e aggregazione
# ---------------------------------------------------------------------------


def test_report_resolution_states_match_section_10_4() -> None:
    assert {state.value for state in ReportResolutionState} == {
        "COMPLETE_FOR_REQUESTED_CLAIMS",
        "PARTIAL_WITH_ACTIONABLE_GAPS",
        "MULTI_SCENARIO",
        "CONFLICTED",
        "INVALID",
        "OUT_OF_SCOPE",
    }


def test_appendix_a_report_resolution_token_is_a_finding() -> None:
    """FINDING (SRR-0007): l'Appendice A usa un token fuori dal §10.4.

    ``MULTIPLE_PLAUSIBLE_GRAPHS`` e' uno stato di determinabilita' claim-level,
    non uno stato di risoluzione report-level: il contratto §10.4 lo rifiuta.
    """
    bundle = load_fixture("appendix_a_experiment_bundle.yaml")
    with pytest.raises(ValueError):
        ReportResolutionState(bundle["report_resolution_state"])
    states = tuple(
        DerivedClaim.model_validate(raw).determinability_state for raw in bundle["derived_claims"]
    )
    # Claim (MPG, INSUFFICIENT, INSUFFICIENT): la precedenza fail-closed mette
    # i gap azionabili davanti al multi-scenario (SRR-0011).
    assert aggregate_report_resolution(states) is ReportResolutionState.PARTIAL_WITH_ACTIONABLE_GAPS


def test_aggregation_precedence_is_fail_closed() -> None:
    D = Determinability
    R = ReportResolutionState
    assert aggregate_report_resolution((D.DETERMINATE,)) is R.COMPLETE_FOR_REQUESTED_CLAIMS
    assert (
        aggregate_report_resolution((D.DETERMINATE, D.INSUFFICIENT_INFORMATION))
        is R.PARTIAL_WITH_ACTIONABLE_GAPS
    )
    assert (
        aggregate_report_resolution((D.MULTIPLE_PLAUSIBLE_GRAPHS, D.DETERMINATE))
        is R.MULTI_SCENARIO
    )
    assert (
        aggregate_report_resolution((D.MULTIPLE_PLAUSIBLE_GRAPHS, D.INSUFFICIENT_INFORMATION))
        is R.PARTIAL_WITH_ACTIONABLE_GAPS
    )
    assert aggregate_report_resolution((D.CONFLICTING_INFORMATION, D.DETERMINATE)) is R.CONFLICTED
    assert aggregate_report_resolution((D.INVALID_GRAPH,)) is R.INVALID
    assert aggregate_report_resolution((D.OUT_OF_SCOPE,)) is R.OUT_OF_SCOPE
    assert (
        aggregate_report_resolution((D.OUT_OF_SCOPE, D.DETERMINATE))
        is R.PARTIAL_WITH_ACTIONABLE_GAPS
    )
    with pytest.raises(ValueError):
        aggregate_report_resolution(())


# ---------------------------------------------------------------------------
# DesignAdequacyFinding (§10.5, §7.18)
# ---------------------------------------------------------------------------


def test_design_adequacy_families_match_section_10_5() -> None:
    expected = {
        "DESIGN_REPLICATION_SUPPORTED",
        "DESIGN_REPLICATION_LIMITED",
        "DESIGN_REPLICATION_ABSENT",
        "DESIGN_REPLICATION_UNKNOWN",
        "HARD_CONFOUNDING_DOCUMENTED",
        "HARD_CONFOUNDING_POSSIBLE",
        "HARD_CONFOUNDING_NOT_IDENTIFIED",
        "HARD_CONFOUNDING_UNKNOWN",
        "INTERFERENCE_DOCUMENTED",
        "INTERFERENCE_POSSIBLE",
        "INTERFERENCE_NO_KNOWN_PATH",
        "INTERFERENCE_UNKNOWN",
        "SOURCE_SCOPE_SINGLE",
        "SOURCE_SCOPE_MULTIPLE",
        "SOURCE_SCOPE_UNKNOWN",
        "ANALYTICAL_DEPENDENCE_CLUSTERED",
        "ANALYTICAL_DEPENDENCE_REPEATED",
        "ANALYTICAL_DEPENDENCE_SIMPLE",
        "ANALYTICAL_DEPENDENCE_UNKNOWN",
        "REPORTING_COMPLETE_FOR_CLAIM",
        "REPORTING_INCOMPLETE",
        "REPORTING_CONFLICTING",
    }
    assert DesignAdequacyFinding.finding_values() == expected


def test_design_adequacy_requires_evidence_and_never_derives_from_determinability() -> None:
    with pytest.raises(ValidationError):
        DesignAdequacyFinding(
            finding="DESIGN_REPLICATION_SUPPORTED",
            evidence_ids=(),
        )
    with pytest.raises(ValidationError):
        DesignAdequacyFinding(
            finding="DESIGN_REPLICATION_SUPPORTED",
            evidence_ids=("EV-01",),
            source_determinability_state=Determinability.DETERMINATE,
        )
    finding = DesignAdequacyFinding(
        finding="DESIGN_REPLICATION_LIMITED",
        evidence_ids=("EV-01",),
        rationale="Single donor across all cultures.",
    )
    assert finding.finding == "DESIGN_REPLICATION_LIMITED"


# ---------------------------------------------------------------------------
# Enum kernel: token verbatim PRD
# ---------------------------------------------------------------------------


def test_source_class_verbatim_tokens() -> None:
    # Token verbatim da §9.1/Appendice A/Appendice AG (SRR-0009).
    assert {member.value for member in SourceClass} == {
        "PUBLISHED_METHODS",
        "SAMPLE_METADATA_EXECUTED",
        "PROSPECTIVE_PRIVATE",
        "POST_CUTOFF_PUBLIC",
        "LEGACY_PUBLIC",
    }


def test_bundle_sources_use_known_source_classes() -> None:
    bundle = load_fixture("appendix_a_experiment_bundle.yaml")
    for source in bundle["sources"]:
        assert SourceClass(source["source_class"])
