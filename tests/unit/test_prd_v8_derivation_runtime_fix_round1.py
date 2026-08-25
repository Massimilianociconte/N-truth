"""RED regressions for Task 4 independent review round 1."""

from __future__ import annotations

from inspect import Parameter, signature
from pathlib import Path
from typing import Any

import pytest
import test_prd_v8_derivation_runtime as base
from pydantic import ValidationError

from ntruth.derivation_theory.loader import load_canonical_bundle
from ntruth.schemas.claims import IrrelevantPredicate
from ntruth.schemas.graph_v8 import (
    V8ExperimentGraph,
    V8GraphNode,
    V8GraphNodeType,
    V8GraphRelation,
    V8GraphRelationType,
)
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.support import (
    SUPPORT_GRADE_VOCABULARY_SECTION_0_4,
    SupportGrade,
)


def _bundle() -> object:
    return load_canonical_bundle(base.REPOSITORY_ROOT)


def test_public_runtime_requires_one_complete_bundle_and_has_no_theory_bypass() -> None:
    runtime, _ = base._request()
    parameters = signature(runtime.run_v8_pipeline).parameters

    assert parameters["conformance_bundle"].default is Parameter.empty
    assert "theory" not in parameters


def test_runtime_rejects_content_drift_even_when_model_copy_retains_declared_checksum() -> None:
    runtime, request = base._request()
    bundle = _bundle()
    first = bundle.theory.clauses[0]
    drifted = first.model_copy(
        update={"normative_statement": f"{first.normative_statement} unreviewed drift"}
    )
    malformed = bundle.model_copy(
        update={
            "theory": bundle.theory.model_copy(
                update={"clauses": (drifted, *bundle.theory.clauses[1:])}
            )
        }
    )

    with pytest.raises(runtime.V8PipelineConformanceError):
        runtime.run_v8_pipeline(request, conformance_bundle=malformed)


def _mutate_claim(claim: object, mutation: str) -> object:
    if mutation == "theory_version":
        return claim.model_copy(update={"theory_version": "forged-theory"})
    if mutation == "ruleset_version":
        return claim.model_copy(update={"ruleset_version": "forged-rules"})
    if mutation == "rule_and_proof_id":
        step = claim.proof_trace[0].model_copy(update={"rule_id": "FORGED-RULE"})
        return claim.model_copy(update={"rule_trace": ("FORGED-RULE",), "proof_trace": (step,)})
    if mutation == "predicate_bytes":
        step = claim.proof_trace[0]
        reference = step.predicate_references[0].model_copy(
            update={"predicate_value": base._present("forged-scientific-value")}
        )
        changed_step = step.model_copy(
            update={"predicate_references": (reference, *step.predicate_references[1:])}
        )
        return claim.model_copy(update={"proof_trace": (changed_step,)})
    if mutation == "value_query_scope":
        return claim.model_copy(
            update={"value": claim.value.model_copy(update={"query_scope_id": "IQ-OTHER"})}
        )
    if mutation == "support_grade":
        return claim.model_copy(
            update={
                "support_grade": SupportGrade(
                    vocabulary_id=SUPPORT_GRADE_VOCABULARY_SECTION_0_4,
                    token="MODEL_CANDIDATE",
                )
            }
        )
    if mutation == "irrelevant_predicate":
        original = claim.irrelevant_predicates[0]
        changed = IrrelevantPredicate(id=original.id, rationale="forged rationale")
        return claim.model_copy(update={"irrelevant_predicates": (changed,)})
    if mutation == "profile_coverage":
        changed = claim.profile_coverage.model_copy(update={"statement_id": "PCS-FORGED"})
        return claim.model_copy(update={"profile_coverage": changed})
    raise AssertionError(mutation)


@pytest.mark.parametrize(
    "mutation",
    (
        "theory_version",
        "ruleset_version",
        "rule_and_proof_id",
        "predicate_bytes",
        "value_query_scope",
        "support_grade",
        "irrelevant_predicate",
        "profile_coverage",
    ),
)
def test_claim_verifier_rejects_every_cross_contract_mutation(mutation: str) -> None:
    verifier = __import__("ntruth.verifier.v8", fromlist=["verify_v8_derived_claim_set"])
    runtime, request = base._request()
    bundle = _bundle()
    result = runtime.run_v8_pipeline(request, conformance_bundle=bundle)
    forged = _mutate_claim(result.claim_set.claims[0], mutation)
    forged_set = result.claim_set.model_copy(
        update={"claims": (forged, *result.claim_set.claims[1:])}
    )

    report = verifier.verify_v8_derived_claim_set(
        request,
        forged_set,
        conformance_bundle=bundle,
        execution_manifest=result.execution_manifest,
    )

    assert report.passed is False


def test_profile_coverage_must_cover_every_theory_required_predicate() -> None:
    runtime, request = base._request()
    bundle = _bundle()
    reduced = tuple(
        item
        for item in request.profile_coverage.covered_predicate_ids
        if item != "realized_exposure_separability"
    )
    invalid = request.model_copy(
        update={
            "profile_coverage": request.profile_coverage.model_copy(
                update={"covered_predicate_ids": reduced}
            )
        }
    )

    with pytest.raises(runtime.V8PipelineVerificationError):
        runtime.run_v8_pipeline(invalid, conformance_bundle=bundle)


def test_scenario_coverage_status_has_open_world_invariants() -> None:
    runtime, _ = base._request()

    with pytest.raises(ValidationError):
        runtime.ScenarioCoverage(
            status=runtime.ScenarioCoverageStatus.EXHAUSTIVE_WITHIN_PROFILE,
            profile_id=base.PROFILE_ID,
            theory_version="0.1.0",
            emitting_clause_ids=("DT-B-EXPERIMENTAL-UNIT",),
            omitted_dimensions=base._unknown("omissions were not assessed"),
            caveat=base._present("cannot prove exhaustiveness"),
        )


def test_srr_008_never_allows_scenario_space_complete() -> None:
    runtime = __import__("ntruth.pipeline_v8", fromlist=["ScenarioCoverage"])
    coverage = runtime.ScenarioCoverage(
        status=runtime.ScenarioCoverageStatus.EXHAUSTIVE_WITHIN_PROFILE,
        profile_id=base.PROFILE_ID,
        theory_version="0.1.0",
        emitting_clause_ids=("DT-B-EXPERIMENTAL-UNIT",),
        omitted_dimensions=KnowledgeValue[tuple[str, ...]](
            knowledge_state=KnowledgeState.ABSENT_EXPLICIT,
            evidence_ids=("EV-COVERAGE-REVIEW",),
            query_scope_id=base.QUERY_ID,
        ),
        caveat=KnowledgeValue[str](
            knowledge_state=KnowledgeState.NOT_APPLICABLE,
            rationale="no caveat after bounded review",
            query_scope_id=base.QUERY_ID,
        ),
    )
    runtime, request = base._request(scenario_coverages=(coverage,))

    result = runtime.run_v8_pipeline(request, conformance_bundle=_bundle())

    assert result.scenario_space_complete is False


def _exact_view(edge_types: tuple[V8GraphRelationType, ...]) -> object:
    equality = __import__("ntruth.graph.equality_v8", fromlist=["ExactGraphView"])
    nodes = (
        V8GraphNode(node_id="a", node_type=V8GraphNodeType.EXPERIMENT_BLOCK),
        V8GraphNode(node_id="b", node_type=V8GraphNodeType.INFERENTIAL_QUERY),
    )
    relations = tuple(
        V8GraphRelation(
            relation_id=f"edge-{index}",
            relation_type=relation_type,
            source_node_id="a",
            target_node_id="b",
            query_scope=base._graph_query_scope("b"),
            factor_scope=base._graph_not_applicable(
                "b", "This equality fixture is not factor-scoped."
            ),
            decisive_attributes=base._graph_not_applicable(
                "b", "This equality fixture has no additional attributes."
            ),
        )
        for index, relation_type in enumerate(edge_types)
    )
    return equality.ExactGraphView(
        graph=V8ExperimentGraph(nodes=nodes, relations=relations),
        node_semantics=(
            equality.GraphNodeSemanticIdentity(
                node_id="a", role="block", semantic_key="semantic-block"
            ),
            equality.GraphNodeSemanticIdentity(
                node_id="b", role="query", semantic_key="semantic-query"
            ),
        ),
    )


def test_exact_graph_equality_preserves_parallel_relation_type_multiplicity() -> None:
    equality = __import__("ntruth.graph.equality_v8", fromlist=["exact_graph_equal"])
    left = _exact_view(
        (
            V8GraphRelationType.SUPPORTS,
            V8GraphRelationType.SUPPORTS,
            V8GraphRelationType.CONTRADICTS,
        )
    )
    right = _exact_view(
        (
            V8GraphRelationType.SUPPORTS,
            V8GraphRelationType.CONTRADICTS,
            V8GraphRelationType.CONTRADICTS,
        )
    )

    assert equality.exact_graph_equal(left, right) is False


@pytest.mark.parametrize("operation", ("add", "remove", "replace", "test"))
def test_v8_patch_guard_rejects_every_operation_on_canonical_claim_set(operation: str) -> None:
    corrections = __import__("ntruth.corrections.v8", fromlist=["apply_v8_patch"])
    patch: dict[str, Any] = {"op": operation, "path": "/result/claim_set/claims/0/value"}
    if operation in {"add", "replace", "test"}:
        patch["value"] = {"knowledge_state": "UNKNOWN"}

    with pytest.raises(corrections.DirectDerivedClaimPatchError):
        corrections.reject_direct_derived_claim_patch((patch,))


@pytest.mark.parametrize("operation", ("copy", "move"))
def test_v8_patch_guard_rejects_from_pointer_into_canonical_claim_set(operation: str) -> None:
    corrections = __import__("ntruth.corrections.v8", fromlist=["apply_v8_patch"])

    with pytest.raises(corrections.DirectDerivedClaimPatchError):
        corrections.reject_direct_derived_claim_patch(
            (
                {
                    "op": operation,
                    "from": "/envelope/result/claim_set/claims/0/value",
                    "path": "/facts/copied",
                },
            )
        )


def test_patch_guard_is_integrated_in_the_v8_patch_api() -> None:
    corrections = __import__("ntruth.corrections.v8", fromlist=["apply_v8_patch"])
    runtime, request = base._request()
    result = runtime.run_v8_pipeline(request, conformance_bundle=_bundle())

    with pytest.raises(corrections.DirectDerivedClaimPatchError):
        corrections.apply_v8_patch(
            {"result": result.model_dump(mode="json"), "facts": {}},
            (
                {
                    "op": "replace",
                    "path": "/result/claim_set/claims/0/value",
                    "value": {"knowledge_state": "UNKNOWN"},
                },
            ),
        )


def test_canonical_pipeline_and_application_are_not_legacy_aliases() -> None:
    application = __import__("ntruth.application", fromlist=["execute_analysis"])
    pipeline = __import__("ntruth.pipeline", fromlist=["analyze_project"])

    assert pipeline.analyze_project is not pipeline.analyze_project_v7_adapter
    assert application.execute_analysis is not application.execute_analysis_v7_adapter


def test_project_input_fails_closed_at_canonical_v8_application_boundary(
    tmp_path: Path,
) -> None:
    application = __import__("ntruth.application", fromlist=["execute_analysis"])
    source = tmp_path / "methods.md"
    source.write_text("# Methods\nNo verified v8 facts bundle.", encoding="utf-8")

    with pytest.raises(application.V8ApplicationInputReviewRequired):
        application.execute_analysis(source, out=tmp_path / "out")


def test_v8_derivation_input_requires_canonical_count_registry_records() -> None:
    runtime = __import__("ntruth.derivation_theory.runtime", fromlist=["V8DerivationInput"])

    assert "count_registry" in runtime.V8DerivationInput.model_fields
    assert "experimental_unit_count_record_id" in runtime.V8DerivationInput.model_fields
    assert "biological_source_count_record_id" in runtime.V8DerivationInput.model_fields


def test_adequacy_is_a_nonempty_epistemic_evaluation_with_rule_pins() -> None:
    runtime, request = base._request(
        overrides={"interference_status": base._unknown("interference was not reconstructable")}
    )
    result = runtime.run_v8_pipeline(request, conformance_bundle=_bundle())

    assert result.design_adequacy_evaluations
    evaluation = result.design_adequacy_evaluations[0]
    assert evaluation.outcome.knowledge_state is KnowledgeState.UNKNOWN
    assert evaluation.rule_id == "V8-E-INTERFERENCE"
    assert evaluation.rule_version
    assert len(evaluation.rule_checksum) == 64
    assert evaluation.dependency_claim_ids
    assert evaluation.required_predicates
    assert evaluation.irrelevant_predicates


def test_progressive_verifier_separates_failed_from_completed_stage() -> None:
    verifier = __import__("ntruth.verifier.v8", fromlist=["verify_v8_pipeline_request"])
    _, request = base._request()
    predicates = dict(request.predicate_values)
    del predicates["realized_exposure_separability"]
    invalid = request.model_copy(update={"predicate_values": predicates})

    report = verifier.verify_v8_pipeline_request(invalid, conformance_bundle=_bundle())

    assert report.highest_completed_stage == "NONE"
    assert report.failed_stage == "FACT_VERIFICATION"
