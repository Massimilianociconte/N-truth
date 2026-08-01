"""Contratti graph/design introdotti dal PRD scientifico v3."""

from __future__ import annotations

from ntruth.calibration.abstention import evaluate_abstention
from ntruth.design.compiler import compile_experiment_block
from ntruth.design.schema import CompilationStatus, DesignSpecification
from ntruth.graph.builder import BuildResult, _build_design_graph
from ntruth.graph.index import GraphIndex
from ntruth.graph.units import resolve_units
from ntruth.schemas.core import Provenance, ProvenanceKind
from ntruth.schemas.document import DocumentIR
from ntruth.schemas.experiment import (
    Contrast,
    Endpoint,
    Estimand,
    ExperimentBlock,
    Factor,
    Hierarchy,
    Inferability,
    InferenceTarget,
    InferenceTargetStatus,
    NKind,
    NScope,
    NStatement,
    StatisticalModelFact,
    UnitAssessment,
    Versions,
)
from ntruth.schemas.graph import GraphNode, GraphRelation, NodeType, RelationType


def _user_provenance() -> Provenance:
    return Provenance(origin=ProvenanceKind.USER, actor_role="researcher")


def _derived_provenance() -> Provenance:
    return Provenance(origin=ProvenanceKind.DERIVED, derivation="fixture v3")


def _versions() -> Versions:
    return Versions(
        schema_version="0.2.0",
        parser_version="0.1.0",
        graph_version="0.2.0",
        ruleset_id="ntruth-core",
        ruleset_version="0.1.0",
    )


def _node(node_id: str, node_type: NodeType, *, count: int | None = None) -> GraphNode:
    return GraphNode(
        id=node_id,
        type=node_type,
        label=node_id,
        count=count,
        attributes={"aggregate": True},
        provenance=_user_provenance(),
    )


def _complete_block() -> ExperimentBlock:
    factor = Factor(
        id="factor-treatment",
        name="treatment",
        levels=("drug", "vehicle"),
        kind="treatment",
        allocation_level=NodeType.ANIMAL,
        application_level=NodeType.WELL,
        allocation_confidence=1.0,
        application_confidence=1.0,
        randomized=True,
        provenance=_user_provenance(),
    )
    endpoint = Endpoint(
        id="endpoint-intensity",
        name="intensity",
        measured_on=NodeType.WELL,
        provenance=_user_provenance(),
    )
    contrast = Contrast(
        id="contrast-drug-vehicle",
        label="drug vs vehicle",
        factor_ids=(factor.id,),
        compared_levels=("drug", "vehicle"),
        endpoint_id=endpoint.id,
        provenance=_user_provenance(),
    )
    target = InferenceTarget(
        id="target-animal",
        question_text="Il trattamento cambia l'intensita?",
        claim_text="Effetto negli animali studiati.",
        population_of_inference="animali nelle condizioni dichiarate",
        factor_ids=(factor.id,),
        contrast_ids=(contrast.id,),
        endpoint_ids=(endpoint.id,),
        target_biological_unit=NodeType.ANIMAL,
        provenance=_user_provenance(),
        status=InferenceTargetStatus.USER_CONFIRMED,
    )
    estimand = Estimand(
        id="estimand-intensity",
        endpoint_id=endpoint.id,
        effect_measure="mean difference",
        target_population_or_unit="animali nelle condizioni dichiarate",
        generalization_level="animal",
        factor_ids=(factor.id,),
        provenance=_user_provenance(),
    )
    animal = _node("animal", NodeType.ANIMAL, count=4)
    well = _node("well", NodeType.WELL, count=24)
    nested = GraphRelation(
        id="well-in-animal",
        type=RelationType.NESTED_IN,
        source=well.id,
        target=animal.id,
        provenance=_user_provenance(),
    )
    assessment = UnitAssessment(
        id="assessment",
        scope=NScope(
            factor_id=factor.id,
            contrast_id=contrast.id,
            endpoint_id=endpoint.id,
            inference_target_id=target.id,
        ),
        experimental_unit=NodeType.ANIMAL,
        observational_unit=NodeType.WELL,
        n_independent=4,
        inferability=Inferability.INFERABLE,
        provenance=_derived_provenance(),
    )
    return ExperimentBlock(
        id="block-v3",
        document_id="document-v3",
        inference_targets=(target,),
        factors=(factor,),
        contrasts=(contrast,),
        endpoints=(endpoint,),
        estimands=(estimand,),
        hierarchy=Hierarchy(nodes=(animal, well), relations=(nested,)),
        unit_assessments=(assessment,),
        versions=_versions(),
    )


def test_only_allocation_determines_experimental_unit() -> None:
    block = _complete_block()
    build = BuildResult(
        hierarchy=block.hierarchy,
        factors=block.factors,
        contrasts=block.contrasts,
        endpoints=block.endpoints,
    )

    assessments, _ = resolve_units(block.id, build)

    assert assessments[0].experimental_unit is NodeType.ANIMAL
    assert assessments[0].experimental_unit is not NodeType.WELL
    assert assessments[0].n_allocated == 4
    assert assessments[0].n_analyzed == 24
    assert assessments[0].n_independent is None
    assert assessments[0].inferability is Inferability.REQUIRES_CONFIRMATION
    assert "applicazione fisica avviene a Well" in assessments[0].rationale


def test_design_graph_materializes_typed_relations_without_clustering_as_allocation() -> None:
    block = _complete_block()
    factor = block.factors[0]
    contrast = block.contrasts[0]
    endpoint = block.endpoints[0]
    model = StatisticalModelFact(
        id="model-mixed",
        kind="mixed",
        declared_clustering=(NodeType.CAGE,),
        provenance=_user_provenance(),
    )
    unit_nodes = {
        NodeType.ANIMAL: _node("animal", NodeType.ANIMAL),
        NodeType.WELL: _node("well", NodeType.WELL),
        NodeType.CAGE: _node("cage", NodeType.CAGE),
    }

    nodes, relations = _build_design_graph(
        block.id,
        factors=(factor,),
        contrasts=(contrast,),
        endpoints=(endpoint,),
        models=(model,),
        unit_nodes=unit_nodes,
    )
    triples = {(relation.source, relation.type, relation.target) for relation in relations}

    assert (factor.id, RelationType.ALLOCATED_TO, "animal") in triples
    assert (factor.id, RelationType.APPLIED_TO, "well") in triples
    assert (model.id, RelationType.DECLARES_CLUSTERING, "cage") in triples
    assert (factor.id, RelationType.DEFINES_CONTRAST, contrast.id) in triples
    assert (contrast.id, RelationType.HAS_ENDPOINT, endpoint.id) in triples
    assert (endpoint.id, RelationType.MEASURED_ON, "well") in triples
    assert (factor.id, RelationType.ALLOCATED_TO, "cage") not in triples
    assert {node.type for node in nodes} >= {
        NodeType.EXPERIMENT_BLOCK,
        NodeType.FACTOR,
        NodeType.CONTRAST,
        NodeType.ENDPOINT,
        NodeType.STATISTICAL_MODEL,
    }


def test_graph_index_normalizes_canonical_relation_orientation() -> None:
    plate = _node("plate", NodeType.PLATE)
    well = _node("well", NodeType.WELL)
    animal = _node("animal", NodeType.ANIMAL)
    pool = _node("pool", NodeType.POOL)
    split = GraphRelation(
        id="well-split-from-plate",
        type=RelationType.SPLIT_FROM,
        source=well.id,
        target=plate.id,
        provenance=_user_provenance(),
    )
    pooled = GraphRelation(
        id="pool-from-animal",
        type=RelationType.POOLED_FROM,
        source=pool.id,
        target=animal.id,
        provenance=_user_provenance(),
    )
    index = GraphIndex(Hierarchy(nodes=(plate, well, animal, pool), relations=(split, pooled)))

    assert index.is_nested_in(NodeType.WELL, NodeType.PLATE)
    assert index.is_nested_in(NodeType.ANIMAL, NodeType.POOL)
    assert index.relations_from(pool.id, RelationType.POOLED_FROM) == [pooled]


def test_design_v02_accepts_v01_and_compiles_estimand_neutral_handoff() -> None:
    block = _complete_block()
    specification = DesignSpecification.from_experiment_block(block)
    compilation = compile_experiment_block(block)

    assert specification.specification_version == "0.2.0"
    assert compilation.status is CompilationStatus.READY
    assert compilation.analysis_handoff.allocations[0].allocation_level is NodeType.ANIMAL
    assert compilation.analysis_handoff.applications[0].application_level is NodeType.WELL
    assert compilation.analysis_handoff.estimands[0].effect_measure == "mean difference"
    assert compilation.analysis_handoff.targets[0].estimand_ids == ("estimand-intensity",)
    assert compilation.analysis_handoff.prohibited_outputs == (
        "statistical_test_selection",
        "model_formula",
        "power_analysis",
    )

    legacy_payload = specification.model_dump(mode="json")
    legacy_payload["specification_version"] = "0.1.0"
    legacy_factor = legacy_payload["factors"][0]
    legacy_factor.pop("allocation_level")
    legacy_factor.pop("allocation_confidence")
    legacy_factor.pop("allocation_evidence_ids")
    restored = DesignSpecification.model_validate(legacy_payload)

    assert restored.specification_version == "0.2.0"
    assert restored.factors[0].allocation_level is NodeType.ANIMAL


def test_compiler_abstains_and_prioritizes_question_when_estimand_is_missing() -> None:
    block = _complete_block().model_copy(update={"estimands": ()})

    compilation = compile_experiment_block(block)

    assert compilation.status is CompilationStatus.ABSTAINED
    estimand_questions = [
        question
        for question in compilation.elicitation.questions
        if question.missing_field == "estimands"
    ]
    assert estimand_questions
    assert all(question.decisive and question.priority == 100 for question in estimand_questions)


def test_conditional_n_uses_two_graph_derived_values_and_never_invents_missing_branch() -> None:
    factor = Factor(
        id="factor-well",
        name="treatment",
        levels=("drug", "vehicle"),
        allocation_level=NodeType.WELL,
        allocation_confidence=1.0,
        provenance=_user_provenance(),
    )
    model = StatisticalModelFact(
        id="model-cluster",
        kind="mixed",
        declared_clustering=(NodeType.CELL_CULTURE,),
        provenance=_user_provenance(),
    )
    well = _node("well", NodeType.WELL, count=8)
    culture = _node("culture", NodeType.CELL_CULTURE, count=2)
    build = BuildResult(
        hierarchy=Hierarchy(nodes=(well, culture)),
        factors=(factor,),
        models=(model,),
    )

    assessments, questions = resolve_units("block-conditional", build)
    scenario = assessments[0].conditional_scenarios[0]

    assert assessments[0].inferability is Inferability.CONDITIONAL
    assert assessments[0].n_allocated == 8
    assert assessments[0].n_independent is None
    assert scenario.if_confirmed == {"per_group": 8}
    assert scenario.if_rejected == {"per_group": 2}
    assert scenario.rule_id == "GEN-010"
    assert any(question.decisive and question.priority == 100 for question in questions)

    unknown_cluster = culture.model_copy(update={"count": None})
    unknown_build = BuildResult(
        hierarchy=Hierarchy(nodes=(well, unknown_cluster)),
        factors=(factor,),
        models=(model,),
    )
    unknown_assessments, unknown_questions = resolve_units("block-unknown", unknown_build)

    assert unknown_assessments[0].conditional_scenarios == ()
    assert any(question.missing_field == "source_independence" for question in unknown_questions)


def test_nested_counts_produce_a_conditional_n_instead_of_false_precision() -> None:
    factor = Factor(
        id="factor-well-nested",
        name="treatment",
        levels=("drug", "vehicle"),
        allocation_level=NodeType.WELL,
        allocation_confidence=1.0,
        provenance=_user_provenance(),
    )
    well = _node("well-nested", NodeType.WELL, count=8)
    culture = _node("culture-parent", NodeType.CELL_CULTURE, count=2)
    nested = GraphRelation(
        id="well-in-culture",
        type=RelationType.NESTED_IN,
        source=well.id,
        target=culture.id,
        provenance=_user_provenance(),
    )
    build = BuildResult(
        hierarchy=Hierarchy(nodes=(well, culture), relations=(nested,)),
        factors=(factor,),
    )

    assessments, questions = resolve_units("block-nested-counts", build)
    assessment = assessments[0]

    assert assessment.inferability is Inferability.CONDITIONAL
    assert assessment.n_allocated == 8
    assert assessment.n_independent is None
    assert assessment.conditional_scenarios[0].if_confirmed == {"per_group": 8}
    assert assessment.conditional_scenarios[0].if_rejected == {"per_group": 2}
    assert [question.missing_field for question in questions] == ["source_independence"]


def test_biological_count_without_independence_evidence_requires_confirmation() -> None:
    explicit = Provenance(origin=ProvenanceKind.EXPLICIT)
    factor = Factor(
        id="factor-primary-culture",
        name="treatment",
        levels=("drug", "vehicle"),
        allocation_level=NodeType.PRIMARY_CULTURE,
        allocation_confidence=1.0,
        provenance=explicit,
    )
    culture = GraphNode(
        id="primary-cultures",
        type=NodeType.PRIMARY_CULTURE,
        label="primary cultures",
        count=4,
        provenance=explicit,
    )
    build = BuildResult(hierarchy=Hierarchy(nodes=(culture,)), factors=(factor,))

    assessments, questions = resolve_units("block-primary-cultures", build)
    assessment = assessments[0]

    assert assessment.data_sufficiency.source_independence.value == "low"
    assert assessment.inferability is Inferability.REQUIRES_CONFIRMATION
    assert assessment.n_allocated == 4
    assert assessment.n_independent is None
    assert any(question.missing_field == "source_independence" for question in questions)
    abstention = evaluate_abstention(DocumentIR(id="document-primary-cultures"), build, assessments)
    assert abstention.abstained is True
    assert "source_independence_unknown" in abstention.codes


def test_unscoped_global_n_is_not_bound_when_contrast_is_absent() -> None:
    factor = Factor(
        id="factor-diet",
        name="diet",
        levels=("diet",),
        allocation_level=NodeType.CAGE,
        allocation_confidence=1.0,
        provenance=_user_provenance(),
    )
    statement = NStatement(
        id="n-global",
        value=32,
        entity_type="animals",
        node_type=NodeType.CAGE,
        scope=NScope(is_global=True),
        kind=NKind.DECLARED,
        provenance=_user_provenance(),
    )
    build = BuildResult(
        hierarchy=Hierarchy(nodes=(_node("cage", NodeType.CAGE, count=8),)),
        factors=(factor,),
        n_statements=(statement,),
    )

    assessments, _ = resolve_units("block-no-contrast", build)

    assert assessments[0].scope.contrast_id is None
    assert assessments[0].n_declared is None
