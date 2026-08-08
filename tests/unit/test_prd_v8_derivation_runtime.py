"""Task 4 regressions for the deterministic PRD v8 claim lane."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from importlib import import_module
from pathlib import Path
from typing import Any

import pytest

from ntruth.derivation_theory.loader import canonical_checksum, load_canonical_bundle
from ntruth.schemas.authority import AuthorityType
from ntruth.schemas.causal_context import (
    InterferenceStatus,
    QueryCausalContext,
    QueryCausalEventAggregate,
)
from ntruth.schemas.core import content_checksum
from ntruth.schemas.count_registry import (
    CanonicalCountKind,
    CanonicalCountRecord,
    CanonicalCountRegistry,
    CountLifecyclePhase,
    CountOrigin,
    CountQuantifier,
    CountScope,
)
from ntruth.schemas.events import ApplicationEvent, AssignmentEvent, EventRegistry, ExposureEvent
from ntruth.schemas.graph_v8 import (
    V8ExperimentGraph,
    V8GraphNode,
    V8GraphNodeType,
    V8GraphRelation,
    V8GraphRelationType,
)
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.query import InferentialQuery
from ntruth.schemas.support import (
    SUPPORT_GRADE_VOCABULARY_SECTION_0_4,
    EvidenceBasis,
    RuleChallenge,
    RuleChallengeDecision,
    RuleChallengeDecisionOutcome,
    ScientificReviewRequirement,
    SourceClassRef,
    SupportDescriptor,
    SupportGrade,
)

REPOSITORY_ROOT = Path(__file__).parents[2]
QUERY_ID = "IQ-RUNTIME-001"
BLOCK_ID = "BLOCK-RUNTIME-001"
PROFILE_ID = "simple_cell_culture"
PROFILE_VERSION = "0.1.0"
CANONICAL_BUNDLE = load_canonical_bundle(REPOSITORY_ROOT)


def _present(value: Any, *, evidence_id: str = "EV-RUNTIME-001") -> KnowledgeValue[Any]:
    return KnowledgeValue(
        knowledge_state=KnowledgeState.PRESENT,
        value=value,
        evidence_ids=(evidence_id,),
        query_scope_id=QUERY_ID,
    )


def _unknown(rationale: str) -> KnowledgeValue[Any]:
    return KnowledgeValue(
        knowledge_state=KnowledgeState.UNKNOWN,
        rationale=rationale,
        query_scope_id=QUERY_ID,
    )


def _query() -> InferentialQuery:
    return InferentialQuery(
        id=QUERY_ID,
        profile_id=PROFILE_ID,
        factor_id="FACTOR-TREATMENT",
        contrast_id="CONTRAST-VEHICLE-DRUG",
        compared_levels=("vehicle", "drug"),
        endpoint_id="ENDPOINT-VIABILITY",
        timepoint_id=_present("T48H"),
        effect_measure_or_estimand=_present("mean_difference"),
        inference_population=_present("cultures_under_protocol_x"),
        inference_level=_present("culture"),
    )


def _causal_aggregate(*, interference: InterferenceStatus) -> QueryCausalEventAggregate:
    assignment = AssignmentEvent(
        event_id="EVT-ASSIGN-001",
        experiment_block_id=BLOCK_ID,
        evidence_refs=("EV-RUNTIME-001",),
        factor_id="FACTOR-TREATMENT",
        assigned_unit_type=_present("well"),
        assigned_unit_ids=_present(("well-1", "well-2")),
    )
    application = ApplicationEvent(
        event_id="EVT-APPLY-001",
        experiment_block_id=BLOCK_ID,
        evidence_refs=("EV-RUNTIME-001",),
        factor_id="FACTOR-TREATMENT",
        intervention_id=_present("drug"),
        application_unit_type=_present("well"),
        application_unit_ids=_present(("well-1", "well-2")),
    )
    exposure = ExposureEvent(
        event_id="EVT-EXPOSURE-001",
        experiment_block_id=BLOCK_ID,
        evidence_refs=("EV-RUNTIME-001",),
        exposure_pathway=_present("shared_medium"),
        exposure_container=_present("plate"),
        effective_exposure_unit=_present("plate"),
        exposed_unit_ids=_present(("well-1", "well-2")),
    )
    return QueryCausalEventAggregate(
        experiment_block_id=BLOCK_ID,
        event_registry=EventRegistry(events=(assignment, application, exposure)),
        causal_context=QueryCausalContext(
            inferential_query_id=QUERY_ID,
            assignment_event_id=_present(assignment.event_id),
            application_event_id=_present(application.event_id),
            exposure_event_id=_present(exposure.event_id),
            assignment_unit_type=_present("well"),
            application_unit_type=_present("well"),
            effective_exposure_unit_type=_present("plate"),
            experimental_unit_type=_present("well"),
            biological_source_unit_type=_present("culture_preparation"),
            interference_status=_present(interference),
        ),
    )


def _predicate_values() -> dict[str, KnowledgeValue[Any]]:
    return {
        "factor": _present("FACTOR-TREATMENT"),
        "factor_levels": _present(("vehicle", "drug")),
        "assignment_event_or_equivalent_mechanism": _present("EVT-ASSIGN-001"),
        "candidate_unit": _present("well"),
        "biological_source_unit_type": _present("culture_preparation"),
        "assignment_separability_support": _present(True),
        "relevant_treatment_assignment": _present("EVT-ASSIGN-001"),
        "realized_treatment_application_or_exposure": _present("EVT-EXPOSURE-001"),
        "assignment_separability": _present(True),
        "realized_exposure_separability": _present(True),
        "experimental_unit_instances": _present(("well-1", "well-2")),
        "inferential_query": _present(QUERY_ID),
        "contrast_scope": _present("CONTRAST-VEHICLE-DRUG"),
        "lifecycle_phase": _present("treated"),
        "group_or_paired_set": _present("drug"),
        "count_cohort_id": _present("COHORT-RUNTIME-001"),
        "count_condition": _present("confirmed_units"),
        "confirmed_biological_provenance": _present(True),
        "biological_source_instances": _present(("source-1", "source-2")),
        "interference_status": _present("possible"),
        "claim_no_interference_dependency": _present(True),
        "analytical_grouping": _present("well"),
        "repeated_measure_status": _present("repeated"),
        "measurement_process": _present("segmentation-pipeline-v1"),
        "source_diversity": _present("multiple_confirmed_sources"),
        "protocol_scope": _present("protocol-x"),
        "external_replication": _present(False),
        "exposure_interference": _present("possible"),
        "profile_coverage": _present("structured_statement_with_open_review"),
        # This fact is deliberately extra: no evaluator may use it as assignment support.
        "biological_source_independence": _present(True),
    }


def _support() -> SupportDescriptor:
    return SupportDescriptor(
        source_class=SourceClassRef(
            registry_id="ntruth-source-class-v8.0",
            token="metadata",
        ),
        authority_type=AuthorityType.EXPERT_ADJUDICATION,
        evidence_basis=EvidenceBasis.ADJUDICATED_REFERENCE,
        support_grade=SupportGrade(
            vocabulary_id=SUPPORT_GRADE_VOCABULARY_SECTION_0_4,
            token="ADJUDICATED",
        ),
    )


def _count_scope(*, unit_type: str) -> CountScope:
    return CountScope(
        query_id=QUERY_ID,
        unit_type=_present(unit_type),
        factor_id=_present("FACTOR-TREATMENT"),
        contrast_id=_present("CONTRAST-VEHICLE-DRUG"),
        group_id=_present("drug"),
        endpoint_id=_present("ENDPOINT-VIABILITY"),
        timepoint_id=_present("T48H"),
        cohort_id=_present("COHORT-RUNTIME-001"),
        lifecycle_phase=_present(CountLifecyclePhase.TREATED),
        population_scope=_present("cultures_under_protocol_x"),
        condition=_present("confirmed_units"),
    )


def _count_registry() -> CanonicalCountRegistry:
    eu = CanonicalCountRecord(
        count_id="COUNT-EU-RUNTIME-001",
        kind=CanonicalCountKind.EXPERIMENTAL_UNIT_COUNT,
        value=_present(2),
        quantifier=CountQuantifier.EXACT,
        scope=_count_scope(unit_type="well"),
        source_evidence=("EV-RUNTIME-001",),
        origin=CountOrigin.RULE_DERIVATION,
        rule_trace=("V8-C-EXPERIMENTAL-UNIT-COUNT",),
    )
    source = CanonicalCountRecord(
        count_id="COUNT-SOURCE-RUNTIME-001",
        kind=CanonicalCountKind.BIOLOGICAL_SOURCE_COUNT,
        value=_present(2),
        quantifier=CountQuantifier.EXACT,
        scope=_count_scope(unit_type="culture_preparation"),
        source_evidence=("EV-RUNTIME-001",),
        origin=CountOrigin.SOURCE_DECLARATION,
    )
    return CanonicalCountRegistry(records=(eu, source))


def _successor_bundle() -> object:
    theory = CANONICAL_BUNDLE.theory.model_copy(update={"theory_version": "0.1.1"})
    theory = theory.model_copy(
        update={
            "declared_checksum": canonical_checksum(
                theory.model_dump(mode="json", exclude_unset=True),
                exclude_declared_checksum=True,
            )
        }
    )
    rules = tuple(
        rule.model_copy(update={"rule_version": "0.1.1"})
        for rule in CANONICAL_BUNDLE.rulebook.rules
    )
    rulebook = CANONICAL_BUNDLE.rulebook.model_copy(
        update={
            "rulebook_version": "0.1.1",
            "theory_version": theory.theory_version,
            "theory_checksum": theory.declared_checksum,
            "rules": rules,
        }
    )
    rulebook = rulebook.model_copy(
        update={
            "declared_checksum": canonical_checksum(
                rulebook.model_dump(mode="json", exclude_unset=True),
                exclude_declared_checksum=True,
            )
        }
    )
    return CANONICAL_BUNDLE.model_copy(update={"theory": theory, "rulebook": rulebook})


def _request(
    *,
    overrides: dict[str, KnowledgeValue[Any]] | None = None,
    interference: InterferenceStatus = InterferenceStatus.POSSIBLE,
    scenario_coverages: tuple[object, ...] = (),
) -> tuple[object, object]:
    runtime = import_module("ntruth.pipeline_v8")
    bundle = CANONICAL_BUNDLE
    predicates = _predicate_values()
    predicates.update(overrides or {})
    profile_coverage = runtime.ProfileCoverageStatement(
        statement_id="PCS-RUNTIME-001",
        profile_id=PROFILE_ID,
        profile_version=PROFILE_VERSION,
        theory_version=bundle.theory.theory_version,
        predicate_closure_argument_id=bundle.profile_closure.asset_id,
        covered_predicate_ids=tuple(
            sorted(set(predicates) & set(bundle.profile_closure.candidate_predicate_ids))
        ),
        known_gap_ids=("SRR-V8-008",),
        contract_review=ScientificReviewRequirement(
            issue_id="SRR-V8-008",
            rationale="Predicate closure remains under profile governance review.",
        ),
    )
    request = runtime.V8PipelineRequest(
        experiment_block_id=BLOCK_ID,
        graph=V8ExperimentGraph(
            nodes=(
                V8GraphNode(node_id=BLOCK_ID, node_type=V8GraphNodeType.EXPERIMENT_BLOCK),
                V8GraphNode(node_id=QUERY_ID, node_type=V8GraphNodeType.INFERENTIAL_QUERY),
            )
        ),
        query=_query(),
        causal_aggregate=_causal_aggregate(interference=interference),
        predicate_values=predicates,
        support_by_clause={clause.clause_id: _support() for clause in bundle.theory.clauses},
        profile_coverage=profile_coverage,
        scenario_coverages=scenario_coverages,
        count_registry=_count_registry(),
        experimental_unit_count_record_id="COUNT-EU-RUNTIME-001",
        biological_source_count_record_id="COUNT-SOURCE-RUNTIME-001",
        runtime_ruleset_version="ntruth-v8-core-0.1.0",
    )
    return runtime, request


def _claim(result: object, claim_type: str) -> object:
    return next(claim for claim in result.claim_set.claims if claim.claim_type == claim_type)


def test_source_independence_never_promotes_assignment_eu_or_count() -> None:
    """Catches using source diversity as an assignment/EU/count proxy."""

    runtime, request = _request(
        overrides={
            "assignment_separability_support": _unknown("assignment mechanism is not reported"),
            "assignment_separability": _unknown("assignment separability is not established"),
        }
    )

    result = runtime.run_v8_pipeline(request, conformance_bundle=CANONICAL_BUNDLE)

    assert _claim(result, "ASSIGNMENT_UNIT").determinability_state.value == (
        "INSUFFICIENT_INFORMATION"
    )
    assert _claim(result, "EXPERIMENTAL_UNIT").determinability_state.value == (
        "INSUFFICIENT_INFORMATION"
    )
    source_count = _claim(result, "BIOLOGICAL_SOURCE_COUNT")
    assert source_count.determinability_state.value == "INSUFFICIENT_INFORMATION"
    assert source_count.state_contract_review.issue_id == "SRR-V8-023"


def test_documented_interference_never_auto_replaces_experimental_unit() -> None:
    """Catches the universal but forbidden mapping interference -> larger EU."""

    runtime, request = _request(
        interference=InterferenceStatus.DOCUMENTED,
        overrides={
            "interference_status": _present("documented"),
            "exposure_interference": _present("documented"),
            "realized_exposure_separability": _unknown(
                "shared exposure is documented but its treatment-realization consequence is unresolved"
            ),
        },
    )

    result = runtime.run_v8_pipeline(request, conformance_bundle=CANONICAL_BUNDLE)
    eu_claim = _claim(result, "EXPERIMENTAL_UNIT")

    assert eu_claim.determinability_state.value == "INSUFFICIENT_INFORMATION"
    assert eu_claim.value.knowledge_state is KnowledgeState.UNKNOWN
    assert eu_claim.value.value is None
    assert _claim(result, "INTERFERENCE_ESTIMAND_SUPPORT").claim_id != eu_claim.claim_id


def test_same_block_query_retains_different_claim_specific_states() -> None:
    """Catches collapsing all query claims into one global determinability state."""

    runtime, request = _request(
        overrides={
            "source_diversity": KnowledgeValue[Any](
                knowledge_state=KnowledgeState.CONFLICTING,
                conflicting_values=("single_source", "multiple_sources"),
                evidence_ids=("EV-RUNTIME-001", "EV-RUNTIME-002"),
                query_scope_id=QUERY_ID,
            )
        }
    )

    result = runtime.run_v8_pipeline(request, conformance_bundle=CANONICAL_BUNDLE)

    assert _claim(result, "ASSIGNMENT_UNIT").determinability_state.value == (
        "INSUFFICIENT_INFORMATION"
    )
    assert _claim(result, "INFERENCE_SCOPE").determinability_state.value == (
        "CONFLICTING_INFORMATION"
    )
    assert result.report_resolution.state is None
    assert result.report_resolution.review_requirement.issue_id == "SRR-V8-014"


def test_non_exhaustive_scenario_coverage_is_retained_and_never_presented_as_complete() -> None:
    """Catches turning a bounded alternative set into an exhaustive possibility space."""

    runtime = import_module("ntruth.pipeline_v8")
    coverage = runtime.ScenarioCoverage(
        status=runtime.ScenarioCoverageStatus.NON_EXHAUSTIVE,
        profile_id=PROFILE_ID,
        theory_version="0.1.0",
        emitting_clause_ids=("DT-B-EXPERIMENTAL-UNIT",),
        omitted_dimensions=_present(("unreviewed_interference_topology",)),
        caveat=_present("Additional exposure topologies may exist."),
    )
    runtime, request = _request(scenario_coverages=(coverage,))

    result = runtime.run_v8_pipeline(request, conformance_bundle=CANONICAL_BUNDLE)

    assert result.scenario_coverages == (coverage,)
    assert result.scenario_space_complete is False


def test_direct_derived_claim_patch_is_forbidden_and_requires_rule_challenge() -> None:
    """Catches bypassing theory review by mutating deterministic output in place."""

    corrections_v8 = import_module("ntruth.corrections.v8")
    patch = (
        {
            "op": "replace",
            "path": "/derived_claims/0/value",
            "value": {"knowledge_state": "PRESENT", "unit_type": "plate"},
        },
    )

    with pytest.raises(corrections_v8.DirectDerivedClaimPatchError, match="RuleChallenge"):
        corrections_v8.reject_direct_derived_claim_patch(patch)


def test_equal_numeric_eu_and_source_counts_remain_distinct_claims() -> None:
    """Catches collapsing biological-source count into experimental-unit count."""

    runtime, request = _request()
    result = runtime.run_v8_pipeline(request, conformance_bundle=CANONICAL_BUNDLE)
    eu_count = _claim(result, "EXPERIMENTAL_UNIT_COUNT")
    source_count = _claim(result, "BIOLOGICAL_SOURCE_COUNT")

    eu_lineage = eu_count.proof_trace[0].input_record_references[0]
    source_lineage = source_count.proof_trace[0].input_record_references[0]
    assert eu_lineage.record_value.value == 2
    assert source_lineage.record_value.value == 2
    assert eu_lineage.record_kind.value == "experimental_unit_count"
    assert source_lineage.record_kind.value == "biological_source_count"
    assert eu_count.claim_id != source_count.claim_id
    assert eu_count.required_predicates != source_count.required_predicates


def test_design_adequacy_is_separate_and_cannot_change_claim_determinability() -> None:
    """Catches an adequacy finding rewriting a claim-specific state."""

    runtime, possible_request = _request(interference=InterferenceStatus.POSSIBLE)
    possible = runtime.run_v8_pipeline(possible_request, conformance_bundle=CANONICAL_BUNDLE)
    runtime, documented_request = _request(
        interference=InterferenceStatus.DOCUMENTED,
        overrides={
            "interference_status": _present("documented"),
            "exposure_interference": _present("documented"),
        },
    )
    documented = runtime.run_v8_pipeline(documented_request, conformance_bundle=CANONICAL_BUNDLE)

    assert _claim(possible, "EXPERIMENTAL_UNIT").determinability_state.value == (
        "INSUFFICIENT_INFORMATION"
    )
    assert _claim(documented, "EXPERIMENTAL_UNIT").determinability_state.value == (
        "INSUFFICIENT_INFORMATION"
    )
    assert possible.design_adequacy_findings[0].finding_type == "INTERFERENCE_POSSIBLE"
    assert documented.design_adequacy_findings[0].finding_type == "INTERFERENCE_DOCUMENTED"


def test_progressive_verifier_fails_closed_before_theory_derivation() -> None:
    """Catches silently treating an omitted decisive predicate as false or absent."""

    verifier = import_module("ntruth.verifier.v8")
    _, request = _request()
    valid = verifier.verify_v8_pipeline_request(request, conformance_bundle=CANONICAL_BUNDLE)
    predicates = dict(request.predicate_values)
    del predicates["realized_exposure_separability"]
    invalid_request = request.model_copy(update={"predicate_values": predicates})

    invalid = verifier.verify_v8_pipeline_request(
        invalid_request, conformance_bundle=CANONICAL_BUNDLE
    )

    assert valid.passed is True
    assert invalid.passed is False
    assert invalid.highest_completed_stage == "NONE"
    assert invalid.failed_stage == "FACT_VERIFICATION"
    assert invalid.issues[0].code == "MISSING_EXPLICIT_PREDICATE"
    assert invalid.issues[0].theory_clause_id == "DT-B-EXPERIMENTAL-UNIT"


def test_pipeline_stops_at_typed_fact_verification_failure() -> None:
    """Catches entering theory evaluation after a progressive verifier failure."""

    runtime, request = _request()
    predicates = dict(request.predicate_values)
    del predicates["experimental_unit_instances"]
    invalid_request = request.model_copy(update={"predicate_values": predicates})

    with pytest.raises(runtime.V8PipelineVerificationError) as error:
        runtime.run_v8_pipeline(invalid_request, conformance_bundle=CANONICAL_BUNDLE)

    assert error.value.report.highest_completed_stage == "NONE"
    assert error.value.report.failed_stage == "FACT_VERIFICATION"
    assert error.value.report.issues[0].theory_clause_id == "DT-C-EXPERIMENTAL-UNIT-COUNT"


def test_exact_graph_equality_is_identifier_invariant_and_semantic() -> None:
    """Catches comparing local IDs instead of typed semantic graph structure."""

    equality = import_module("ntruth.graph.equality_v8")
    left = equality.ExactGraphView(
        graph=V8ExperimentGraph(
            nodes=(
                V8GraphNode(node_id="left-block", node_type=V8GraphNodeType.EXPERIMENT_BLOCK),
                V8GraphNode(node_id="left-query", node_type=V8GraphNodeType.INFERENTIAL_QUERY),
            ),
            relations=(
                V8GraphRelation(
                    relation_id="left-edge",
                    relation_type=V8GraphRelationType.CONTAINED_IN,
                    source_node_id="left-query",
                    target_node_id="left-block",
                ),
            ),
        ),
        node_semantics=(
            equality.GraphNodeSemanticIdentity(
                node_id="left-block", role="experiment_block", semantic_key="block:study-1"
            ),
            equality.GraphNodeSemanticIdentity(
                node_id="left-query", role="primary_query", semantic_key="query:drug-vs-control"
            ),
        ),
    )
    right = equality.ExactGraphView(
        graph=V8ExperimentGraph(
            nodes=(
                V8GraphNode(node_id="renamed-1", node_type=V8GraphNodeType.EXPERIMENT_BLOCK),
                V8GraphNode(node_id="renamed-2", node_type=V8GraphNodeType.INFERENTIAL_QUERY),
            ),
            relations=(
                V8GraphRelation(
                    relation_id="renamed-edge",
                    relation_type=V8GraphRelationType.CONTAINED_IN,
                    source_node_id="renamed-2",
                    target_node_id="renamed-1",
                ),
            ),
        ),
        node_semantics=(
            equality.GraphNodeSemanticIdentity(
                node_id="renamed-1", role="experiment_block", semantic_key="block:study-1"
            ),
            equality.GraphNodeSemanticIdentity(
                node_id="renamed-2", role="primary_query", semantic_key="query:drug-vs-control"
            ),
        ),
    )

    assert equality.exact_graph_equal(left, right) is True
    changed = right.model_copy(
        update={
            "node_semantics": (
                right.node_semantics[0],
                right.node_semantics[1].model_copy(update={"semantic_key": "query:different"}),
            )
        }
    )
    assert equality.exact_graph_equal(left, changed) is False


def test_partial_graph_scoring_is_a_typed_scientific_review_blocker() -> None:
    """Catches inventing unreviewed weights or tolerances for partial graph scores."""

    equality = import_module("ntruth.graph.equality_v8")
    blocker = equality.partial_graph_score()

    assert blocker.status.value == "SCIENTIFIC_REVIEW_REQUIRED"
    assert blocker.issue_id == "SRR-V8-012"


def test_rule_challenge_requires_a_registered_successor_evaluator() -> None:
    """Catches executing successor Theory bytes without reviewed evaluator registration."""

    corrections_v8 = import_module("ntruth.corrections.v8")
    runtime, original_request = _request()
    original = runtime.run_v8_pipeline(original_request, conformance_bundle=CANONICAL_BUNDLE)
    frozen_claim = _claim(original, "EXPERIMENTAL_UNIT")
    created_at = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
    challenge = RuleChallenge(
        challenge_id="RC-RUNTIME-001",
        derived_claim_id=frozen_claim.claim_id,
        frozen_claim_checksum=content_checksum(frozen_claim.model_dump(mode="json")),
        theory_version=frozen_claim.theory_version,
        theory_clause_ids=frozen_claim.theory_clauses,
        ruleset_version=frozen_claim.ruleset_version,
        rule_ids=frozen_claim.rule_trace,
        rationale="The reviewed clause implementation requires a successor release.",
        actor_role="domain_method_reviewer",
        created_at=created_at,
    )
    successor_bundle = _successor_bundle()
    successor_request = original_request.model_copy(
        update={
            "runtime_ruleset_version": "ntruth-v8-core-0.1.1",
            "profile_coverage": original_request.profile_coverage.model_copy(
                update={"theory_version": "0.1.1"}
            ),
        }
    )
    decision = RuleChallengeDecision(
        decision_id="RCD-RUNTIME-001",
        challenge_id=challenge.challenge_id,
        outcome=RuleChallengeDecisionOutcome.ACCEPTED,
        reviewer_role="derivation_theory_reviewer",
        rationale="Reviewed successor theory and runtime implementation approved.",
        resulting_theory_version="0.1.1",
        resulting_ruleset_version="ntruth-v8-core-0.1.1",
        change_record_id="CHANGE-RUNTIME-001",
        rederivation_record_id="REDERIVE-RUNTIME-001",
        outcome_contract_review=ScientificReviewRequirement(
            issue_id="SRR-V8-024",
            rationale="Outcome payload mapping remains fail-closed pending governance review.",
        ),
        created_at=created_at + timedelta(minutes=5),
    )

    with pytest.raises(Exception) as error:
        corrections_v8.rederive_after_rule_challenge(
            previous=original,
            request=successor_request,
            conformance_bundle=successor_bundle,
            challenge=challenge,
            decision=decision,
        )

    assert frozen_claim.theory_version == "0.1.0"
    assert error.value.__class__.__name__ == "V8EvaluatorReviewRequired"
    assert error.value.review_requirement.issue_id == "SRR-V8-024"


def test_main_deterministic_pipeline_is_v8_and_v7_is_an_explicit_adapter() -> None:
    """Catches leaving the legacy rule-first lane as the unqualified main contract."""

    main_pipeline = import_module("ntruth.pipeline")
    runtime = import_module("ntruth.pipeline_v8")

    assert main_pipeline.run_deterministic_pipeline is runtime.run_v8_pipeline
    assert main_pipeline.analyze_project_v7_adapter is not main_pipeline.analyze_project
    assert main_pipeline.LEGACY_PIPELINE_CONTRACT == "ntruth-v7-deprecated-adapter"


def test_v8_pipeline_order_is_facts_theory_claims_adequacy_report() -> None:
    """Catches deriving theory from rule findings or feeding adequacy into claims."""

    runtime, request = _request()

    result = runtime.run_v8_pipeline(request, conformance_bundle=CANONICAL_BUNDLE)

    assert result.stage_order == (
        "FACT_VERIFICATION",
        "THEORY_DERIVATION",
        "CLAIM_VERIFICATION",
        "RULE_ADEQUACY",
        "REPORT_RESOLUTION",
    )


def test_task4_contracts_have_public_schema_and_correction_exports() -> None:
    """Catches exposing the v8 lane while hiding its validation/audit contracts."""

    schemas = import_module("ntruth.schemas")
    corrections = import_module("ntruth.corrections")
    kernel = import_module("ntruth.schemas.kernel")

    assert schemas.ProfileCoverageStatement is not None
    assert schemas.DesignAdequacyFinding is not None
    assert schemas.ReportResolutionOutcome is not None
    assert corrections.reject_direct_derived_claim_patch is not None
    assert {
        "profile_coverage_statement",
        "scenario_coverage",
        "design_adequacy_finding",
        "report_resolution_outcome",
    } <= kernel.kernel_json_schemas().keys()


def test_runtime_gates_rulebook_conformance_without_using_it_as_theory() -> None:
    """Catches executing an unpinned implementation or deriving claims from its metadata."""

    runtime, request = _request()
    bundle = load_canonical_bundle(REPOSITORY_ROOT)
    first_rule = bundle.rulebook.rules[0]
    malformed_rule = first_rule.model_copy(update={"theory_clause_id": "DT-Z-MISSING"})
    malformed_bundle = bundle.model_copy(
        update={
            "rulebook": bundle.rulebook.model_copy(
                update={"rules": (malformed_rule, *bundle.rulebook.rules[1:])}
            )
        }
    )

    with pytest.raises(runtime.V8PipelineConformanceError) as error:
        runtime.run_v8_pipeline(request, conformance_bundle=malformed_bundle)

    assert error.value.report.passed is False
    assert _claim(
        runtime.run_v8_pipeline(request, conformance_bundle=CANONICAL_BUNDLE),
        "ASSIGNMENT_UNIT",
    ).rule_trace == ("V8-A-ASSIGNMENT-UNIT",)
