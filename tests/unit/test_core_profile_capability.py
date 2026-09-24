"""Regressioni del capability boundary scientifico Core v0.1-D."""

from __future__ import annotations

import pytest

from ntruth.capabilities import (
    CORE_PROFILE_ID,
    CORE_PROFILE_REFERENCE,
    CORE_PROFILE_VERSION,
    CapabilityReason,
    CapabilityStatus,
    assess_core_profile_capability,
)
from ntruth.design import compile_experiment_block
from ntruth.graph.determinability import derive_determinability
from ntruth.pipeline import _supported_by_release_profile
from ntruth.schemas.core import Determinability, Provenance, ProvenanceKind
from ntruth.schemas.experiment import (
    Endpoint,
    ExperimentBlock,
    Factor,
    Hierarchy,
    ProcessFact,
    StatisticalModelFact,
    Versions,
)
from ntruth.schemas.graph import GraphNode, GraphRelation, NodeType, RelationType
from ntruth.schemas.manifest import ReleaseProfile


def _provenance() -> Provenance:
    return Provenance(
        origin=ProvenanceKind.DERIVED,
        derivation="synthetic capability-boundary fixture",
    )


def _versions() -> Versions:
    return Versions(
        schema_version="0.3.0",
        parser_version="0.3.0",
        graph_version="0.3.0",
        ruleset_id="ntruth-core",
        ruleset_version="0.2.0",
    )


def _core_block() -> ExperimentBlock:
    return ExperimentBlock(
        id="core-capability-block",
        document_id="core-capability-document",
        factors=(
            Factor(
                id="factor-treatment",
                name="treatment",
                kind="treatment",
                levels=("vehicle", "drug"),
                allocation_level=NodeType.WELL,
                application_level=NodeType.CELL,
                provenance=_provenance(),
            ),
        ),
        endpoints=(
            Endpoint(
                id="endpoint-intensity",
                name="fluorescence intensity",
                measured_on=NodeType.CELL,
                provenance=_provenance(),
            ),
        ),
        versions=_versions(),
    )


def _assert_out_of_scope(
    block: ExperimentBlock,
    expected_reason: CapabilityReason,
) -> None:
    decision = assess_core_profile_capability(block)
    assert decision.status is CapabilityStatus.OUT_OF_SCOPE
    assert decision.supported is False
    assert expected_reason in decision.reason_codes
    assert _supported_by_release_profile(block, ReleaseProfile.D0_CORE) is False
    assert (
        derive_determinability(
            block,
            compile_experiment_block(block),
            supported_profile=decision.supported,
        )
        is Determinability.OUT_OF_SCOPE
    )


def test_core_capability_contract_is_explicit_versioned_and_tri_state() -> None:
    supported = assess_core_profile_capability(_core_block())
    assert supported.status is CapabilityStatus.SUPPORTED
    assert supported.supported is True
    assert supported.profile_id == CORE_PROFILE_ID
    assert supported.profile_version == CORE_PROFILE_VERSION
    assert supported.profile_reference == CORE_PROFILE_REFERENCE == "ntruth-core@0.1-D"

    incomplete = assess_core_profile_capability(
        ExperimentBlock(id="incomplete", document_id="document", versions=_versions())
    )
    assert incomplete.status is CapabilityStatus.INCOMPLETE
    assert incomplete.supported is None
    assert set(incomplete.reason_codes) == {
        CapabilityReason.MISSING_PRIMARY_FACTOR,
        CapabilityReason.MISSING_PRIMARY_ENDPOINT,
    }


@pytest.mark.parametrize(
    ("relation_type", "expected_reason"),
    [
        (RelationType.REPEATED_MEASURE_OF, CapabilityReason.UNSUPPORTED_TOPOLOGY),
        (RelationType.PAIRED_WITH, CapabilityReason.UNSUPPORTED_TOPOLOGY),
        (RelationType.MATCHED_WITH, CapabilityReason.UNSUPPORTED_TOPOLOGY),
        (RelationType.CROSSED_WITH, CapabilityReason.UNSUPPORTED_TOPOLOGY),
        (RelationType.BLOCKED_BY, CapabilityReason.UNSUPPORTED_TOPOLOGY),
        (RelationType.SPLIT_FROM, CapabilityReason.UNSUPPORTED_TOPOLOGY),
        (RelationType.SPLIT_INTO, CapabilityReason.UNSUPPORTED_TOPOLOGY),
        (RelationType.POOLED_FROM, CapabilityReason.UNSUPPORTED_TOPOLOGY),
        (RelationType.POOLED_INTO, CapabilityReason.UNSUPPORTED_TOPOLOGY),
        (RelationType.MEMBER_OF_POOL, CapabilityReason.UNSUPPORTED_TOPOLOGY),
    ],
)
def test_non_core_graph_topologies_become_out_of_scope(
    relation_type: RelationType,
    expected_reason: CapabilityReason,
) -> None:
    left = GraphNode(
        id="well-left",
        type=NodeType.WELL,
        label="well left",
        provenance=_provenance(),
    )
    right = GraphNode(
        id="plate-right",
        type=NodeType.PLATE,
        label="plate right",
        provenance=_provenance(),
    )
    relation = GraphRelation(
        id=f"relation-{relation_type.value}",
        type=relation_type,
        source=left.id,
        target=right.id,
        provenance=_provenance(),
    )
    block = _core_block().model_copy(
        update={"hierarchy": Hierarchy(nodes=(left, right), relations=(relation,))}
    )

    _assert_out_of_scope(block, expected_reason)


@pytest.mark.parametrize(
    "process_kind",
    [
        "repeated_measure",
        "pairing",
        "matched_design",
        "crossed_factors",
        "split_plot",
        "pooling",
        "longitudinal_follow_up",
    ],
)
def test_non_core_processes_become_out_of_scope(process_kind: str) -> None:
    process = ProcessFact(
        id=f"process-{process_kind}",
        kind=process_kind,
        provenance=_provenance(),
    )
    block = _core_block().model_copy(update={"processes": (process,)})

    _assert_out_of_scope(block, CapabilityReason.UNSUPPORTED_PROCESS)


def test_multiple_endpoint_timepoints_become_out_of_scope() -> None:
    endpoint = _core_block().endpoints[0].model_copy(update={"timepoints": ("24 h", "48 h")})
    block = _core_block().model_copy(update={"endpoints": (endpoint,)})

    _assert_out_of_scope(block, CapabilityReason.MULTIPLE_TIMEPOINTS)


def test_multi_level_time_factor_becomes_out_of_scope() -> None:
    time_factor = (
        _core_block().factors[0].model_copy(update={"kind": "time", "levels": ("baseline", "24 h")})
    )
    block = _core_block().model_copy(update={"factors": (time_factor,)})

    _assert_out_of_scope(block, CapabilityReason.MULTIPLE_TIMEPOINTS)


@pytest.mark.parametrize(
    ("kind", "raw_text", "clustering"),
    [
        ("mixed", "linear mixed-effects model", ()),
        ("longitudinal", "longitudinal model", ()),
        ("gee", "generalized estimating equations", ()),
        ("simple", "paired t-test", ()),
        ("simple", "two-way ANOVA", ()),
        ("simple", "t-test", (NodeType.CELL_CULTURE,)),
    ],
)
def test_advanced_or_longitudinal_models_become_out_of_scope(
    kind: str,
    raw_text: str,
    clustering: tuple[NodeType, ...],
) -> None:
    model = StatisticalModelFact(
        id=f"model-{kind}-{len(clustering)}",
        kind=kind,
        raw_text=raw_text,
        declared_clustering=clustering,
        provenance=_provenance(),
    )
    block = _core_block().model_copy(update={"models": (model,)})

    _assert_out_of_scope(block, CapabilityReason.UNSUPPORTED_STATISTICAL_MODEL)


def test_simple_unpaired_model_remains_inside_capability_boundary() -> None:
    model = StatisticalModelFact(
        id="model-unpaired",
        kind="simple",
        raw_text="unpaired t-test",
        provenance=_provenance(),
    )
    block = _core_block().model_copy(update={"models": (model,)})

    assert assess_core_profile_capability(block).status is CapabilityStatus.SUPPORTED


@pytest.mark.parametrize(
    ("block", "expected_reason"),
    [
        (
            _core_block().model_copy(
                update={
                    "factors": (
                        *_core_block().factors,
                        Factor(
                            id="factor-dose",
                            name="dose",
                            levels=("low", "high"),
                            allocation_level=NodeType.WELL,
                            provenance=_provenance(),
                        ),
                    )
                }
            ),
            CapabilityReason.TOO_MANY_FACTORS,
        ),
        (
            _core_block().model_copy(
                update={
                    "endpoints": (
                        *_core_block().endpoints,
                        Endpoint(
                            id="endpoint-viability",
                            name="viability",
                            measured_on=NodeType.CELL,
                            provenance=_provenance(),
                        ),
                    )
                }
            ),
            CapabilityReason.TOO_MANY_ENDPOINTS,
        ),
        (
            _core_block().model_copy(
                update={
                    "factors": (
                        _core_block()
                        .factors[0]
                        .model_copy(update={"levels": ("vehicle", "low", "high")}),
                    )
                }
            ),
            CapabilityReason.TOO_MANY_FACTOR_LEVELS,
        ),
    ],
)
def test_existing_d0_cardinality_limits_remain_fail_closed(
    block: ExperimentBlock,
    expected_reason: CapabilityReason,
) -> None:
    _assert_out_of_scope(block, expected_reason)


def test_extended_input_profile_does_not_expand_scientific_capability() -> None:
    process = ProcessFact(
        id="process-repeated-measure",
        kind="repeated_measure",
        provenance=_provenance(),
    )
    block = _core_block().model_copy(update={"processes": (process,)})

    assert _supported_by_release_profile(block, ReleaseProfile.EXTENDED_EXPERIMENTAL) is False


def test_topology_nodes_fail_closed_even_when_relation_is_missing() -> None:
    pool = GraphNode(
        id="pool",
        type=NodeType.POOL,
        label="pool",
        provenance=_provenance(),
    )
    block = _core_block().model_copy(update={"hierarchy": Hierarchy(nodes=(pool,))})

    _assert_out_of_scope(block, CapabilityReason.UNSUPPORTED_TOPOLOGY)
