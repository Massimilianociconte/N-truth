"""Invarianti v6 per lifecycle, quantificatori, esclusioni e hard verifier."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ntruth.graph.validation import validate_experiment_block
from ntruth.reporting.positive import build_positive_output
from ntruth.schemas.core import Determinability, EvidenceSpan, Provenance, ProvenanceKind
from ntruth.schemas.experiment import (
    Contrast,
    CountKind,
    CountQuantifier,
    CountRecord,
    CountScope,
    Endpoint,
    ExclusionPhase,
    ExclusionRecord,
    ExperimentBlock,
    Factor,
    Hierarchy,
    LifecycleStatus,
    NKind,
    NScope,
    NStatement,
    TriState,
    Versions,
)
from ntruth.schemas.graph import GraphNode, NodeType
from ntruth.verifier import (
    VerificationStatus,
    apply_output_policy,
    output_policy_violations,
    verify_block,
)


def _provenance() -> Provenance:
    return Provenance(origin=ProvenanceKind.USER, actor_role="annotator")


def _versions() -> Versions:
    return Versions(
        schema_version="0.3.0",
        parser_version="0.3.0",
        graph_version="0.3.0",
        ruleset_id="ntruth-core",
        ruleset_version="0.1.0",
    )


def _scope(lifecycle: LifecycleStatus) -> CountScope:
    return CountScope(
        unit_type=NodeType.WELL,
        factor_id="factor-treatment",
        contrast_id="contrast-drug-vehicle",
        group_or_level="drug",
        endpoint_id="endpoint-viability",
        timepoint=None,
        lifecycle=lifecycle,
        population="cell cultures in the declared assay",
        condition="drug",
        unknown_reasons={"timepoint": "not applicable to this endpoint"},
    )


def _design() -> tuple[Factor, Contrast, Endpoint]:
    factor = Factor(
        id="factor-treatment",
        name="treatment",
        levels=("drug", "vehicle"),
        allocation_level=NodeType.WELL,
        independently_assigned=TriState.UNKNOWN,
        provenance=_provenance(),
    )
    endpoint = Endpoint(
        id="endpoint-viability",
        name="viability",
        measured_on=NodeType.WELL,
        provenance=_provenance(),
    )
    contrast = Contrast(
        id="contrast-drug-vehicle",
        label="drug vs vehicle",
        factor_ids=(factor.id,),
        endpoint_ids=(endpoint.id,),
        compared_levels=("drug", "vehicle"),
        provenance=_provenance(),
    )
    return factor, contrast, endpoint


def test_quantifiers_do_not_turn_bounds_or_silence_into_exact_zero() -> None:
    lower = CountRecord(
        count_id="count-lower",
        kind=CountKind.OBSERVED_N,
        value=8,
        quantifier=CountQuantifier.LOWER_BOUND,
        scope=_scope(LifecycleStatus.OBSERVED),
        provenance=_provenance(),
    )
    missing = CountRecord(
        count_id="count-not-reported",
        kind=CountKind.ANALYSED_N,
        value=None,
        quantifier=CountQuantifier.NOT_REPORTED,
        scope=_scope(LifecycleStatus.ANALYSED),
        provenance=_provenance(),
    )

    assert lower.value == 8 and lower.quantifier is CountQuantifier.LOWER_BOUND
    assert missing.value is None and missing.quantifier is CountQuantifier.NOT_REPORTED
    with pytest.raises(ValidationError, match="non ammette valori numerici"):
        CountRecord(
            count_id="count-invalid-zero",
            kind=CountKind.ANALYSED_N,
            value=0,
            quantifier=CountQuantifier.NOT_REPORTED,
            scope=_scope(LifecycleStatus.ANALYSED),
            provenance=_provenance(),
        )


def test_unknown_canonical_scope_is_not_falsely_adapted_to_global_legacy_scope() -> None:
    unknown = CountRecord(
        count_id="count-unknown-scope",
        kind=CountKind.OBSERVED_N,
        value=None,
        quantifier=CountQuantifier.NOT_REPORTED,
        scope=CountScope(
            unit_type=None,
            factor_id=None,
            contrast_id=None,
            group_or_level=None,
            endpoint_id=None,
            timepoint=None,
            lifecycle=None,
            population=None,
            condition=None,
            unknown_reasons={
                "unit_type": "not reported",
                "factor_id": "not reported",
                "contrast_id": "not reported",
                "group_or_level": "not reported",
                "endpoint_id": "not reported",
                "timepoint": "not reported",
                "lifecycle": "not reported",
            },
        ),
        provenance=_provenance(),
    )

    assert unknown.to_legacy() is None


def test_group_or_level_null_requires_an_explicit_reason_code() -> None:
    payload = _scope(LifecycleStatus.OBSERVED).model_dump(mode="json")
    payload["group_or_level"] = None

    with pytest.raises(ValidationError, match="group_or_level"):
        CountScope.model_validate(payload)

    payload["unknown_reasons"]["group_or_level"] = "not reported for this count"
    validated = CountScope.model_validate(payload)
    assert validated.group_or_level is None


def test_physical_counts_are_integral_and_effective_n_is_diagnostic_only() -> None:
    with pytest.raises(ValidationError):
        CountRecord(
            count_id="count-boolean",
            kind=CountKind.OBSERVED_N,
            value=True,
            quantifier=CountQuantifier.EXACT,
            scope=_scope(LifecycleStatus.OBSERVED),
            provenance=_provenance(),
        )
    with pytest.raises(ValidationError):
        CountRecord(
            count_id="count-boolean-bound",
            kind=CountKind.OBSERVED_N,
            value=None,
            lower_bound=True,
            upper_bound=4,
            quantifier=CountQuantifier.RANGE,
            scope=_scope(LifecycleStatus.OBSERVED),
            provenance=_provenance(),
        )
    with pytest.raises(ValidationError):
        NStatement(
            id="legacy-boolean-count",
            value=True,
            entity_type="well",
            node_type=NodeType.WELL,
            scope=NScope(),
            kind=NKind.OBSERVED,
            provenance=_provenance(),
        )
    with pytest.raises(ValidationError, match="valori frazionari"):
        CountRecord(
            count_id="count-fractional",
            kind=CountKind.OBSERVED_N,
            value=3.5,
            quantifier=CountQuantifier.EXACT,
            scope=_scope(LifecycleStatus.OBSERVED),
            provenance=_provenance(),
        )
    with pytest.raises(ValidationError, match="diagnostic_only"):
        CountRecord(
            count_id="effective-authoritative",
            kind=CountKind.EFFECTIVE_N,
            value=3.5,
            quantifier=CountQuantifier.EXACT,
            scope=_scope(LifecycleStatus.ANALYSED),
            provenance=_provenance(),
        )

    effective = CountRecord(
        count_id="effective-diagnostic",
        kind=CountKind.EFFECTIVE_N,
        value=3.5,
        quantifier=CountQuantifier.EXACT,
        scope=_scope(LifecycleStatus.ANALYSED),
        diagnostic_only=True,
        rule_trace_ids=("rule-effective-n",),
        provenance=_provenance(),
    )
    assert effective.diagnostic_only is True


def test_hard_verifier_rejects_lifecycle_mismatch_and_unproven_independent_n() -> None:
    factor, contrast, endpoint = _design()
    mismatched = CountRecord(
        count_id="allocated-but-observed",
        kind=CountKind.ALLOCATED_N,
        value=4,
        quantifier=CountQuantifier.EXACT,
        scope=_scope(LifecycleStatus.OBSERVED),
        provenance=_provenance(),
    )
    independent = CountRecord(
        count_id="independent-unproven",
        kind=CountKind.INDEPENDENT_N,
        value=4,
        quantifier=CountQuantifier.EXACT,
        scope=_scope(LifecycleStatus.ANALYSED),
        provenance=_provenance(),
    )
    block = ExperimentBlock(
        id="block-invalid-counts",
        document_id="document-invalid-counts",
        factors=(factor,),
        contrasts=(contrast,),
        endpoints=(endpoint,),
        count_records=(mismatched, independent),
        determinability=Determinability.INVALID_GRAPH,
        versions=_versions(),
    )

    result = verify_block(block, check_output_policy=False)

    assert result.status is VerificationStatus.FAILED
    assert {item.code for item in result.violations} >= {
        "count_lifecycle_mismatch",
        "independent_count_without_operational_independence",
    }


@pytest.mark.parametrize(
    "state",
    [item for item in Determinability if item is not Determinability.DETERMINATE],
)
def test_public_block_suppresses_scalar_independent_count_outside_determinate(
    state: Determinability,
) -> None:
    factor, contrast, endpoint = _design()
    factor = factor.model_copy(
        update={
            "independently_assigned": TriState.TRUE,
            "independence_mechanism": "separate wells received one assigned level",
        }
    )
    independent = CountRecord(
        count_id="independent-but-state-forbids-output",
        kind=CountKind.INDEPENDENT_N,
        value=4,
        quantifier=CountQuantifier.EXACT,
        scope=_scope(LifecycleStatus.ANALYSED),
        provenance=_provenance(),
    )
    legacy = independent.to_legacy()
    assert legacy is not None
    block = ExperimentBlock(
        id="block-insufficient-independent-count",
        document_id="document-insufficient-independent-count",
        factors=(factor,),
        contrasts=(contrast,),
        endpoints=(endpoint,),
        count_records=(independent,),
        n_statements=(legacy,),
        determinability=state,
        versions=_versions(),
    )

    codes = {item.code for item in output_policy_violations(block)}
    assert "single_independent_count_forbidden_by_state" in codes
    assert "legacy_independent_count_forbidden_by_state" in codes
    assert "single_independent_count_forbidden_by_state" in {
        item.code for item in verify_block(block).violations
    }
    projected = apply_output_policy(block)
    assert projected.count_records == ()
    assert projected.n_statements == ()
    projected_codes = {item.code for item in output_policy_violations(projected)}
    assert "single_independent_count_forbidden_by_state" not in projected_codes
    assert "legacy_independent_count_forbidden_by_state" not in projected_codes
    if state is not Determinability.MULTIPLE_PLAUSIBLE_GRAPHS:
        positive = build_positive_output(projected)
        assert positive.count_records == ()
        assert positive.suppressed_count_record_ids == ()


def test_non_numeric_independent_count_can_remain_as_an_explicit_unknown() -> None:
    factor, contrast, endpoint = _design()
    unknown = CountRecord(
        count_id="independent-explicitly-not-reported",
        kind=CountKind.INDEPENDENT_N,
        quantifier=CountQuantifier.NOT_REPORTED,
        scope=_scope(LifecycleStatus.ANALYSED),
        provenance=_provenance(),
    )
    block = ExperimentBlock(
        id="block-unknown-independent-count",
        document_id="document-unknown-independent-count",
        factors=(factor,),
        contrasts=(contrast,),
        endpoints=(endpoint,),
        count_records=(unknown,),
        determinability=Determinability.INSUFFICIENT_INFORMATION,
        versions=_versions(),
    )

    assert "single_independent_count_forbidden_by_state" not in {
        item.code for item in output_policy_violations(block)
    }
    assert apply_output_policy(block).count_records == (unknown,)


def test_hard_verifier_requires_dedicated_independence_evidence_for_machine_facts() -> None:
    factor = Factor(
        id="factor-machine-independence",
        name="treatment",
        levels=("drug", "vehicle"),
        allocation_level=NodeType.WELL,
        independently_assigned=TriState.TRUE,
        independence_mechanism="each well received one assigned level",
        provenance=Provenance(origin=ProvenanceKind.MODEL, model_version="candidate"),
    )
    block = ExperimentBlock(
        id="block-machine-independence",
        document_id="document-machine-independence",
        factors=(factor,),
        versions=_versions(),
    )

    result = verify_block(block, check_output_policy=False)

    assert result.status is VerificationStatus.FAILED
    assert "independence_without_evidence" in {item.code for item in result.violations}


def test_exclusion_is_endpoint_scoped_and_never_erases_source_count() -> None:
    factor, contrast, endpoint = _design()
    exclusion = ExclusionRecord(
        id="exclusion-1",
        unit_id="well-A01",
        unit_type=NodeType.WELL,
        phase=ExclusionPhase.POST_MEASUREMENT,
        prespecified=TriState.FALSE,
        endpoint_id="endpoint-viability",
        factor_id="factor-treatment",
        contrast_id="contrast-drug-vehicle",
        group="drug",
        author_role="wet-lab",
        reason="segmentation QC failure",
        impact="removed from analysed_n only",
        unknown_reasons={"evidence_ids": "recorded by reviewer outside imported sources"},
        provenance=_provenance(),
    )
    block = ExperimentBlock(
        id="block-exclusion",
        document_id="document-exclusion",
        factors=(factor,),
        contrasts=(contrast,),
        endpoints=(endpoint,),
        exclusion_records=(exclusion,),
        versions=_versions(),
    )

    assert block.exclusion_records == (exclusion,)
    assert block.count_records == ()
    assert exclusion.endpoint_id == "endpoint-viability"
    assert "dangling_exclusion_unit" in {item.code for item in validate_experiment_block(block)}

    wrong_type = GraphNode(
        id=exclusion.unit_id or "",
        type=NodeType.CELL,
        label="wrongly typed exclusion unit",
        provenance=Provenance(
            origin=ProvenanceKind.DERIVED,
            derivation="synthetic mismatch fixture",
        ),
    )
    mismatched_block = block.model_copy(update={"hierarchy": Hierarchy(nodes=(wrong_type,))})
    assert "exclusion_unit_type_mismatch" in {
        item.code for item in validate_experiment_block(mismatched_block)
    }


def test_exclusion_missing_audit_fields_requires_explicit_reason_codes() -> None:
    with pytest.raises(ValidationError, match="fields mancanti senza reason code"):
        ExclusionRecord(
            id="exclusion-incomplete",
            unit_type=NodeType.WELL,
            provenance=_provenance(),
        )

    explicit_missing = ExclusionRecord(
        id="exclusion-explicit-missing",
        unit_type=NodeType.WELL,
        unknown_reasons={
            "phase": "not reported",
            "prespecified": "not reported",
            "endpoint_id": "not reported",
            "group": "not reported",
            "author_role": "not reported",
            "reason": "not reported",
            "evidence_ids": "not available",
            "impact": "not reported",
        },
        provenance=_provenance(),
    )
    assert explicit_missing.phase is ExclusionPhase.UNKNOWN


def test_canonical_registries_reject_ghost_provenance_evidence() -> None:
    factor, contrast, endpoint = _design()
    evidence = EvidenceSpan(id="ev-known", file_id="file-1", text="reviewed source")
    provenance = Provenance(
        origin=ProvenanceKind.USER,
        evidence_ids=(evidence.id, "ev-ghost"),
        actor_role="annotator",
    )
    count = CountRecord(
        count_id="count-with-ghost-lineage",
        kind=CountKind.OBSERVED_N,
        value=4,
        quantifier=CountQuantifier.EXACT,
        scope=_scope(LifecycleStatus.OBSERVED),
        evidence_ids=(evidence.id,),
        provenance=provenance,
    )
    exclusion = ExclusionRecord(
        id="exclusion-with-ghost-lineage",
        unit_type=NodeType.WELL,
        phase=ExclusionPhase.POST_MEASUREMENT,
        prespecified=TriState.FALSE,
        endpoint_id=endpoint.id,
        factor_id=factor.id,
        contrast_id=contrast.id,
        group="drug",
        author_role="wet-lab",
        reason="failed QC",
        impact="removed from analysed_n only",
        evidence_ids=(evidence.id,),
        provenance=provenance,
    )
    block = ExperimentBlock(
        id="block-ghost-lineage",
        document_id="document-ghost-lineage",
        evidence=(evidence,),
        factors=(factor,),
        contrasts=(contrast,),
        endpoints=(endpoint,),
        count_records=(count,),
        exclusion_records=(exclusion,),
        versions=_versions(),
    )

    dangling_messages = {
        item.message
        for item in validate_experiment_block(block)
        if item.code == "dangling_evidence"
    }

    assert any("count record" in message and "ev-ghost" in message for message in dangling_messages)
    assert any(
        "exclusion record" in message and "ev-ghost" in message for message in dangling_messages
    )
