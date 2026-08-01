"""Regressioni v3 per oggetti inferenziali e determinabilita."""

from __future__ import annotations

from ntruth.design import compile_experiment_block
from ntruth.graph.builder import materialize_inferential_graph
from ntruth.graph.determinability import derive_determinability
from ntruth.graph.validation import validate_experiment_block
from ntruth.schemas.core import Determinability, Provenance, ProvenanceKind
from ntruth.schemas.experiment import (
    ConditionalScenario,
    Contradiction,
    Contrast,
    Endpoint,
    Estimand,
    ExperimentBlock,
    Factor,
    Hierarchy,
    Inferability,
    InferenceTarget,
    InferenceTargetStatus,
    NScope,
    UnitAssessment,
    Versions,
)
from ntruth.schemas.graph import GraphNode, NodeType


def _provenance(origin: ProvenanceKind = ProvenanceKind.USER) -> Provenance:
    return Provenance(origin=origin, actor_role="researcher")


def _versions() -> Versions:
    return Versions(
        schema_version="0.2.0",
        parser_version="0.2.0",
        graph_version="0.2.0",
        ruleset_id="ntruth-core",
        ruleset_version="0.1.0",
    )


def _complete_block() -> ExperimentBlock:
    factor = Factor(
        id="factor-treatment",
        name="treatment",
        levels=("control", "drug"),
        allocation_level=NodeType.ANIMAL,
        application_level=NodeType.ANIMAL,
        allocation_confidence=1.0,
        application_confidence=1.0,
        provenance=_provenance(),
    )
    endpoint = Endpoint(
        id="endpoint-weight",
        name="body weight",
        measured_on=NodeType.ANIMAL,
        provenance=_provenance(),
    )
    contrast = Contrast(
        id="contrast-drug-control",
        label="drug vs control",
        factor_ids=(factor.id,),
        compared_levels=("drug", "control"),
        endpoint_ids=(endpoint.id,),
        provenance=_provenance(),
    )
    target = InferenceTarget(
        id="target-animals",
        question_text="Qual e l'effetto del farmaco sul peso?",
        population_of_inference="animali nelle condizioni dichiarate",
        factor_ids=(factor.id,),
        contrast_ids=(contrast.id,),
        endpoint_ids=(endpoint.id,),
        target_biological_unit=NodeType.ANIMAL,
        provenance=_provenance(),
        status=InferenceTargetStatus.USER_CONFIRMED,
    )
    estimand = Estimand(
        id="estimand-weight",
        endpoint_id=endpoint.id,
        effect_measure="mean difference",
        target_population_or_unit="animali nelle condizioni dichiarate",
        generalization_level="animal",
        factor_ids=(factor.id,),
        provenance=_provenance(),
    )
    animal = GraphNode(
        id="animal",
        type=NodeType.ANIMAL,
        label="animals",
        count=4,
        provenance=_provenance(),
    )
    hierarchy = materialize_inferential_graph(
        Hierarchy(nodes=(animal,)),
        block_id="block-v3",
        inference_targets=(target,),
        estimands=(estimand,),
    )
    assessment = UnitAssessment(
        id="assessment-weight",
        scope=NScope(
            factor_id=factor.id,
            contrast_id=contrast.id,
            endpoint_id=endpoint.id,
            inference_target_id=target.id,
        ),
        experimental_unit=NodeType.ANIMAL,
        observational_unit=NodeType.ANIMAL,
        analytical_unit=NodeType.ANIMAL,
        n_independent=4,
        inferability=Inferability.INFERABLE,
        provenance=_provenance(ProvenanceKind.DERIVED),
    )
    return ExperimentBlock(
        id="block-v3",
        document_id="document-v3",
        inference_targets=(target,),
        factors=(factor,),
        contrasts=(contrast,),
        endpoints=(endpoint,),
        estimands=(estimand,),
        hierarchy=hierarchy,
        unit_assessments=(assessment,),
        versions=_versions(),
    )


def test_inference_target_and_estimand_are_idempotent_formal_graph_nodes() -> None:
    block = _complete_block()
    synchronized = materialize_inferential_graph(
        block.hierarchy,
        block_id=block.id,
        inference_targets=block.inference_targets,
        estimands=block.estimands,
    )
    assert synchronized == block.hierarchy
    assert {node.type for node in synchronized.nodes} >= {
        NodeType.EXPERIMENT_BLOCK,
        NodeType.INFERENCE_TARGET,
        NodeType.ESTIMAND,
    }
    codes = {item.code for item in validate_experiment_block(block)}
    assert "missing_inference_target_node" not in codes
    assert "missing_estimand_node" not in codes


def test_missing_inferential_graph_nodes_are_visible_until_recalculation() -> None:
    block = _complete_block().model_copy(
        update={
            "hierarchy": Hierarchy(
                nodes=tuple(
                    node
                    for node in _complete_block().hierarchy.nodes
                    if node.type not in {NodeType.INFERENCE_TARGET, NodeType.ESTIMAND}
                )
            )
        }
    )
    violations = validate_experiment_block(block)
    codes = {item.code for item in violations}
    assert {"missing_inference_target_node", "missing_estimand_node"} <= codes
    assert all(
        not item.blocking
        for item in violations
        if item.code in {"missing_inference_target_node", "missing_estimand_node"}
    )


def test_determinability_is_derived_from_conflicts_alternatives_and_completeness() -> None:
    block = _complete_block()
    compilation = compile_experiment_block(block)
    assert compilation.abstained is False
    assert derive_determinability(block, compilation) is Determinability.DETERMINATE

    scenario = ConditionalScenario(
        conditional_on="animals_are_independent",
        if_confirmed={"drug": 2, "control": 2},
        if_rejected={"drug": 1, "control": 1},
        question="Gli animali sono unita indipendenti?",
        rule_id="V3-TEST",
    )
    conditional_assessment = block.unit_assessments[0].model_copy(
        update={
            "n_independent": None,
            "inferability": Inferability.CONDITIONAL,
            "conditional_scenarios": (scenario,),
        }
    )
    conditional = block.model_copy(update={"unit_assessments": (conditional_assessment,)})
    assert (
        derive_determinability(conditional, compile_experiment_block(conditional))
        is Determinability.MULTIPLE_PLAUSIBLE_GRAPHS
    )

    conflicting = block.model_copy(
        update={
            "contradictions": (Contradiction(id="conflict", description="fonti incompatibili"),)
        }
    )
    assert (
        derive_determinability(conflicting, compile_experiment_block(conflicting))
        is Determinability.CONFLICTING_INFORMATION
    )

    incomplete = ExperimentBlock(
        id="incomplete",
        document_id="document-incomplete",
        versions=_versions(),
    )
    assert (
        derive_determinability(incomplete, compile_experiment_block(incomplete))
        is Determinability.INDETERMINATE
    )
