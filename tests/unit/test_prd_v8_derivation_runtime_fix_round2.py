"""RED regressions for the seven partial Task 4 review findings."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any

import pytest
import test_prd_v8_derivation_runtime as base
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from ntruth.schemas.claims import DeterminabilityState
from ntruth.schemas.count_registry import CountLifecyclePhase
from ntruth.schemas.knowledge import KnowledgeState
from ntruth.schemas.support import ScientificReviewRequirement


def _bound_request() -> tuple[Any, Any]:
    runtime, request = base._request()
    predicates = dict(request.predicate_values)
    predicates.update(
        {
            "biological_source_unit_type": base._present("culture_preparation"),
            "count_cohort_id": base._present("COHORT-RUNTIME-001"),
            "count_condition": base._present("confirmed_units"),
        }
    )
    payload = request.model_dump(mode="python")
    payload["predicate_values"] = predicates
    return runtime, type(request).model_validate(payload)


def _successor_request(request: Any) -> Any:
    return request.model_copy(
        update={
            "runtime_ruleset_version": "ntruth-v8-core-0.1.1",
            "profile_coverage": request.profile_coverage.model_copy(
                update={"theory_version": "0.1.1"}
            ),
        }
    )


def test_model_copy_successor_without_reviewed_evaluator_registry_fails_closed() -> None:
    runtime, request = _bound_request()

    with pytest.raises(Exception) as error:
        runtime.run_v8_pipeline(
            _successor_request(request),
            conformance_bundle=base._successor_bundle(),
        )

    assert error.value.__class__.__name__ == "V8EvaluatorReviewRequired"
    assert error.value.review_requirement.issue_id == "SRR-V8-024"


def test_execution_manifest_pins_each_semantic_evaluator_artifact() -> None:
    runtime, request = _bound_request()

    result = runtime.run_v8_pipeline(request, conformance_bundle=base.CANONICAL_BUNDLE)

    assert len(result.execution_manifest.implementation_rules) == 7
    for pin in result.execution_manifest.implementation_rules:
        assert pin.theory_id == base.CANONICAL_BUNDLE.theory.theory_id
        assert pin.theory_version == base.CANONICAL_BUNDLE.theory.theory_version
        assert pin.theory_checksum == base.CANONICAL_BUNDLE.theory.declared_checksum
        assert pin.implementation_artifact_id
        assert pin.implementation_artifact_version
        assert len(pin.implementation_artifact_checksum) == 64
    adequacy = result.execution_manifest.adequacy_evaluator
    assert adequacy.theory_id == base.CANONICAL_BUNDLE.theory.theory_id
    assert adequacy.theory_version == base.CANONICAL_BUNDLE.theory.theory_version
    assert adequacy.theory_checksum == base.CANONICAL_BUNDLE.theory.declared_checksum
    assert adequacy.theory_clause_id == "DT-E-INTERFERENCE-ESTIMAND"
    assert adequacy.rule_id == "V8-E-INTERFERENCE"
    assert adequacy.implementation_artifact_id
    assert adequacy.implementation_artifact_version
    assert len(adequacy.implementation_artifact_checksum) == 64


def _mutate_full_claim_contract(claim: Any, mutation: str) -> Any:
    if mutation == "value":
        if claim.value.knowledge_state is KnowledgeState.PRESENT:
            value = base._present("forged-output")
        else:
            value = base._unknown("forged non-determinate output")
        return claim.model_copy(update={"value": value})
    if mutation == "state":
        state = (
            DeterminabilityState.DETERMINATE
            if claim.determinability_state is not DeterminabilityState.DETERMINATE
            else DeterminabilityState.INSUFFICIENT_INFORMATION
        )
        return claim.model_copy(update={"determinability_state": state})
    if mutation == "state_review":
        review = (
            None
            if claim.state_contract_review is not None
            else ScientificReviewRequirement(
                issue_id="SRR-V8-023",
                rationale="forged state/output review boundary",
            )
        )
        return claim.model_copy(update={"state_contract_review": review})
    if mutation == "assumptions":
        return claim.model_copy(update={"assumptions": ("forged_assumption",)})
    if mutation == "sensitivity":
        return claim.model_copy(update={"sensitivity_records": ("SENS-FORGED",)})
    if mutation == "proof":
        proof = claim.proof_trace[0].model_copy(update={"step_id": "PROOF-FORGED"})
        return claim.model_copy(update={"proof_trace": (proof,)})
    raise AssertionError(mutation)


@pytest.mark.parametrize(
    "mutation",
    ("value", "state", "state_review", "assumptions", "sensitivity", "proof"),
)
def test_verifier_rejects_every_full_claim_contract_mutation(mutation: str) -> None:
    verifier = import_module("ntruth.verifier.v8")
    runtime, request = _bound_request()
    result = runtime.run_v8_pipeline(request, conformance_bundle=base.CANONICAL_BUNDLE)
    forged = _mutate_full_claim_contract(result.claim_set.claims[0], mutation)
    forged_set = result.claim_set.model_copy(
        update={"claims": (forged, *result.claim_set.claims[1:])}
    )

    report = verifier.verify_v8_derived_claim_set(
        request,
        forged_set,
        conformance_bundle=base.CANONICAL_BUNDLE,
        execution_manifest=result.execution_manifest,
    )

    assert report.passed is False


def test_standalone_claim_verifier_stops_at_nonconformant_bundle() -> None:
    verifier = import_module("ntruth.verifier.v8")
    runtime, request = _bound_request()
    result = runtime.run_v8_pipeline(request, conformance_bundle=base.CANONICAL_BUNDLE)
    first = base.CANONICAL_BUNDLE.theory.clauses[0]
    drifted_bundle = base.CANONICAL_BUNDLE.model_copy(
        update={
            "theory": base.CANONICAL_BUNDLE.theory.model_copy(
                update={
                    "clauses": (
                        first.model_copy(
                            update={"normative_statement": "unreviewed semantic drift"}
                        ),
                        *base.CANONICAL_BUNDLE.theory.clauses[1:],
                    )
                }
            )
        }
    )

    report = verifier.verify_v8_derived_claim_set(
        request,
        result.claim_set,
        conformance_bundle=drifted_bundle,
        execution_manifest=result.execution_manifest,
    )

    assert report.passed is False
    assert len(report.issues) == 1
    assert report.issues[0].code.value == "BUNDLE_CONFORMANCE_FAILED"


def test_open_profile_closure_never_emits_unconditional_determinate_claims() -> None:
    runtime, request = _bound_request()

    result = runtime.run_v8_pipeline(request, conformance_bundle=base.CANONICAL_BUNDLE)

    assert result.claim_set.claims
    assert all(
        claim.determinability_state is DeterminabilityState.INSUFFICIENT_INFORMATION
        and claim.value.knowledge_state is KnowledgeState.UNKNOWN
        and claim.state_contract_review is not None
        and claim.state_contract_review.issue_id == "SRR-V8-023"
        for claim in result.claim_set.claims
    )


@pytest.mark.parametrize("root", ("design_adequacy_evaluations", "execution_manifest"))
@pytest.mark.parametrize("operation", ("add", "remove", "replace", "test"))
def test_patch_guard_protects_every_canonical_output_target(root: str, operation: str) -> None:
    corrections = import_module("ntruth.corrections.v8")
    patch: dict[str, Any] = {"op": operation, "path": f"/result/{root}/target"}
    if operation in {"add", "replace", "test"}:
        patch["value"] = "forged"

    with pytest.raises(corrections.DirectDerivedClaimPatchError):
        corrections.reject_direct_derived_claim_patch((patch,))


@pytest.mark.parametrize("root", ("design_adequacy_evaluations", "execution_manifest"))
@pytest.mark.parametrize("operation", ("copy", "move"))
def test_patch_guard_protects_every_canonical_output_source(root: str, operation: str) -> None:
    corrections = import_module("ntruth.corrections.v8")

    with pytest.raises(corrections.DirectDerivedClaimPatchError):
        corrections.reject_direct_derived_claim_patch(
            (
                {
                    "op": operation,
                    "from": f"/envelope/result/{root}/source",
                    "path": "/facts/target",
                },
            )
        )


def test_unqualified_cli_analyze_fails_closed_without_writing(tmp_path: Path) -> None:
    cli = import_module("ntruth.cli.main")
    source = tmp_path / "methods.md"
    source.write_text("# Methods\nTwo wells received treatment.", encoding="utf-8")
    output = tmp_path / "canonical-out"

    result = CliRunner().invoke(cli.app, ["analyze", str(source), "--out", str(output)])

    assert result.exit_code == 2
    assert "SCIENTIFIC_REVIEW_REQUIRED" in result.output
    assert "SRR-V8-008" in result.output
    assert not output.exists()


def test_explicit_v7_cli_surface_is_named_and_visibly_deprecated(tmp_path: Path) -> None:
    cli = import_module("ntruth.cli.main")
    source = tmp_path / "methods.md"
    source.write_text("# Methods\nTwo wells received treatment.", encoding="utf-8")

    result = CliRunner().invoke(
        cli.app,
        [
            "analyze-v7",
            str(source),
            "--out",
            str(tmp_path / "legacy-out"),
            "--acknowledge-unvalidated-domain",
            "--quiet",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "DEPRECATED_V7_ADAPTER" in result.output


def test_unqualified_http_analyze_fails_closed_and_v7_is_explicit(tmp_path: Path) -> None:
    api_module = import_module("ntruth.api.app")
    source = tmp_path / "methods.md"
    source.write_text("# Methods\nTwo wells received treatment.", encoding="utf-8")
    client = TestClient(api_module.create_app(), base_url="http://127.0.0.1")
    canonical_out = tmp_path / "canonical-api-out"
    payload = {"source": str(source), "out": str(canonical_out)}

    canonical = client.post("/v1/analyze", json=payload)

    assert canonical.status_code == 409
    assert canonical.json()["detail"]["code"] == "SCIENTIFIC_REVIEW_REQUIRED"
    assert canonical.json()["detail"]["issue_id"] == "SRR-V8-008"
    assert not canonical_out.exists()

    legacy = client.post(
        "/v7/analyze",
        json={
            "source": str(source),
            "out": str(tmp_path / "legacy-api-out"),
            "acknowledge_unvalidated_domain": True,
        },
    )
    assert legacy.status_code == 200, legacy.text
    assert legacy.json()["contract"]["code"] == "DEPRECATED_V7_ADAPTER"


def _scope_mutation(request: Any, field_name: str, value: Any) -> Any:
    record = request.count_registry.records[0]
    changed_scope = record.scope.model_copy(update={field_name: base._present(value)})
    changed_record = record.model_copy(update={"scope": changed_scope})
    registry = request.count_registry.model_copy(
        update={"records": (changed_record, *request.count_registry.records[1:])}
    )
    return request.model_copy(update={"count_registry": registry})


@pytest.mark.parametrize(
    ("field_name", "wrong_value"),
    (
        ("factor_id", "FACTOR-WRONG"),
        ("contrast_id", "CONTRAST-WRONG"),
        ("group_id", "vehicle"),
        ("endpoint_id", "ENDPOINT-WRONG"),
        ("timepoint_id", "T24H"),
        ("cohort_id", "COHORT-WRONG"),
        ("lifecycle_phase", CountLifecyclePhase.ANALYZED),
        ("population_scope", "wrong_population"),
        ("condition", "wrong_condition"),
        ("unit_type", "dish"),
    ),
)
def test_count_scope_join_rejects_every_mismatched_component(
    field_name: str,
    wrong_value: Any,
) -> None:
    runtime, request = _bound_request()

    with pytest.raises(runtime.V8PipelineVerificationError):
        runtime.run_v8_pipeline(
            _scope_mutation(request, field_name, wrong_value),
            conformance_bundle=base.CANONICAL_BUNDLE,
        )


def test_count_join_rejects_instance_cardinality_mismatch_without_string_dedup() -> None:
    runtime, request = _bound_request()
    predicates = dict(request.predicate_values)
    predicates["experimental_unit_instances"] = base._present(("well-1", "well-2", "well-3"))

    with pytest.raises(runtime.V8PipelineVerificationError):
        runtime.run_v8_pipeline(
            request.model_copy(update={"predicate_values": predicates}),
            conformance_bundle=base.CANONICAL_BUNDLE,
        )


def test_typed_distinct_instance_ids_do_not_collide_through_stringification() -> None:
    runtime, request = _bound_request()
    predicates = dict(request.predicate_values)
    predicates["experimental_unit_instances"] = base._present([1, "1"])
    payload = request.model_dump(mode="python")
    payload["predicate_values"] = predicates

    result = runtime.run_v8_pipeline(
        type(request).model_validate(payload),
        conformance_bundle=base.CANONICAL_BUNDLE,
    )

    assert result.claim_set.claims


def test_count_record_id_value_and_scope_are_in_proof_lineage() -> None:
    runtime, request = _bound_request()
    result = runtime.run_v8_pipeline(request, conformance_bundle=base.CANONICAL_BUNDLE)
    claim = base._claim(result, "EXPERIMENTAL_UNIT_COUNT")

    lineage = claim.proof_trace[0].input_record_references

    assert len(lineage) == 1
    assert lineage[0].record_id == request.experimental_unit_count_record_id
    assert lineage[0].record_value == request.count_registry.records[0].value
    assert lineage[0].record_scope == request.count_registry.records[0].scope


def test_adequacy_uses_separate_artifact_pin_and_exact_dependencies() -> None:
    runtime, request = _bound_request()
    result = runtime.run_v8_pipeline(request, conformance_bundle=base.CANONICAL_BUNDLE)
    evaluation = result.design_adequacy_evaluations[0]
    pin = result.execution_manifest.adequacy_evaluator

    assert evaluation.theory_id == pin.theory_id
    assert evaluation.theory_version == pin.theory_version
    assert evaluation.theory_checksum == pin.theory_checksum
    assert evaluation.theory_clause_version == pin.theory_clause_version
    assert evaluation.rule_id == pin.rule_id
    assert evaluation.rule_version == pin.rule_version
    assert evaluation.rule_checksum == pin.rule_checksum
    assert evaluation.implementation_artifact_id == pin.implementation_artifact_id
    assert evaluation.implementation_artifact_version == pin.implementation_artifact_version
    assert evaluation.implementation_artifact_checksum == pin.implementation_artifact_checksum
    assert evaluation.implementation_artifact_checksum != evaluation.rule_checksum


def test_standalone_adequacy_rejects_forged_dependency_claim() -> None:
    engine = import_module("ntruth.rules.v8_engine")
    runtime, request = _bound_request()
    result = runtime.run_v8_pipeline(request, conformance_bundle=base.CANONICAL_BUNDLE)
    dependency = base._claim(result, "INTERFERENCE_ESTIMAND_SUPPORT")
    forged = dependency.model_copy(
        update={"value": base._unknown("forged dependency claim output")}
    )
    claims = result.claim_set.model_copy(
        update={
            "claims": tuple(
                forged if claim.claim_id == dependency.claim_id else claim
                for claim in result.claim_set.claims
            )
        }
    )

    with pytest.raises(Exception) as error:
        engine.evaluate_design_adequacy(
            request,
            claims,
            conformance_bundle=base.CANONICAL_BUNDLE,
            execution_manifest=result.execution_manifest,
        )

    assert error.value.__class__.__name__ == "V8AdequacyVerificationError"
