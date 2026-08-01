"""Compiler conservativo dal design IR a un analysis handoff neutro."""

from __future__ import annotations

from ntruth.design.elicit import elicit_design
from ntruth.design.schema import (
    AllocationHandoff,
    AnalysisHandoff,
    ApplicationHandoff,
    ClusterHandoff,
    CompilationStatus,
    DesignCompilation,
    DesignSpecification,
    EndpointHandoff,
    EstimandHandoff,
    NestingHandoff,
    RepeatedMeasureHandoff,
    TargetHandoff,
    TargetPopulationSupport,
    UnresolvedAssumption,
)
from ntruth.schemas.core import stable_id
from ntruth.schemas.experiment import (
    ExperimentBlock,
    InferenceTarget,
    InferenceTargetStatus,
    NScope,
    Question,
    inference_target_scope_mismatches,
)
from ntruth.schemas.graph import CLUSTER_TYPES, RelationType

_NESTING_RELATIONS = frozenset(
    {
        RelationType.CONTAINS,
        RelationType.NESTED_IN,
        RelationType.DERIVED_FROM,
        RelationType.SPLIT_FROM,
        RelationType.SPLIT_INTO,
        RelationType.POOLED_FROM,
        RelationType.POOLED_INTO,
        RelationType.MEMBER_OF_POOL,
    }
)


def compile_experiment_block(block: ExperimentBlock) -> DesignCompilation:
    """Compila un blocco senza mutarlo e senza invocare la pipeline o il grafo."""

    return compile_design(DesignSpecification.from_experiment_block(block))


def compile_design(specification: DesignSpecification) -> DesignCompilation:
    """Produce domande e handoff; si astiene se il target non e confermato/completo."""

    elicitation = elicit_design(specification)
    nodes_by_id = {node.id: node for node in specification.hierarchy.nodes}

    allocations = tuple(
        AllocationHandoff(
            factor_id=factor.id,
            factor_name=factor.name,
            allocation_level=factor.allocation_level,
            allocation_confidence=factor.allocation_confidence,
            randomized=factor.randomized,
            allocation_evidence_ids=factor.allocation_evidence_ids,
            evidence_ids=factor.evidence_ids,
        )
        for factor in specification.factors
    )
    applications = tuple(
        ApplicationHandoff(
            factor_id=factor.id,
            factor_name=factor.name,
            application_level=factor.application_level,
            application_confidence=factor.application_confidence,
            evidence_ids=factor.application_evidence_ids,
        )
        for factor in specification.factors
    )

    nesting = tuple(
        NestingHandoff(
            relation_id=relation.id,
            relation_type=relation.type,
            source_node_id=relation.source,
            source_node_type=(
                nodes_by_id[relation.source].type if relation.source in nodes_by_id else None
            ),
            target_node_id=relation.target,
            target_node_type=(
                nodes_by_id[relation.target].type if relation.target in nodes_by_id else None
            ),
            evidence_ids=relation.evidence_ids,
        )
        for relation in specification.hierarchy.relations
        if relation.type in _NESTING_RELATIONS
    )

    repeated_measures = tuple(
        RepeatedMeasureHandoff(
            relation_id=relation.id,
            source_node_id=relation.source,
            target_node_id=relation.target,
            evidence_ids=relation.evidence_ids,
        )
        for relation in specification.hierarchy.relations
        if relation.type is RelationType.REPEATED_MEASURE_OF
    )

    endpoints = tuple(
        EndpointHandoff(
            endpoint_id=endpoint.id,
            name=endpoint.name,
            measured_on=endpoint.measured_on,
            timepoints=endpoint.timepoints,
            aggregation=endpoint.aggregation,
            evidence_ids=endpoint.evidence_ids,
        )
        for endpoint in specification.endpoints
    )
    estimands = tuple(
        EstimandHandoff(
            estimand_id=estimand.id,
            endpoint_id=estimand.endpoint_id,
            effect_measure=estimand.effect_measure,
            target_population_or_unit=estimand.target_population_or_unit,
            generalization_level=estimand.generalization_level,
            factor_ids=estimand.factor_ids,
            timepoint=estimand.timepoint,
            condition=estimand.condition,
            evidence_ids=estimand.evidence_ids,
        )
        for estimand in specification.estimands
    )

    clusters = _compile_clusters(specification)
    targets = tuple(
        _compile_target(specification, target) for target in specification.inference_targets
    )
    overall_support = _overall_support(targets)
    unresolved = _compile_unresolved(
        specification, elicitation.questions, elicitation.blocking_question_ids
    )
    abstained = overall_support is not TargetPopulationSupport.SUPPORTED or any(
        assumption.blocking for assumption in unresolved
    )

    handoff = AnalysisHandoff(
        specification_id=specification.specification_id,
        block_id=specification.block_id,
        target_population_support=overall_support,
        targets=targets,
        allocations=allocations,
        applications=applications,
        nesting=nesting,
        clusters=clusters,
        repeated_measures=repeated_measures,
        endpoints=endpoints,
        estimands=estimands,
        unresolved_assumptions=unresolved,
    )
    return DesignCompilation(
        specification_id=specification.specification_id,
        status=CompilationStatus.ABSTAINED if abstained else CompilationStatus.READY,
        abstained=abstained,
        elicitation=elicitation,
        analysis_handoff=handoff,
    )


def _compile_target(specification: DesignSpecification, target: InferenceTarget) -> TargetHandoff:
    assessments = tuple(
        assessment.id
        for assessment in specification.unit_assessments
        if _assessment_target_id(specification, assessment.scope) == target.id
    )
    support = _target_support(specification, target, assessments)
    estimand_ids = tuple(
        estimand.id
        for estimand in specification.estimands
        if estimand.endpoint_id in target.endpoint_ids
        and set(target.factor_ids).issubset(estimand.factor_ids)
    )
    return TargetHandoff(
        inference_target_id=target.id,
        status=target.status,
        question_text=target.question_text,
        claim_text=target.claim_text,
        population_of_inference=target.population_of_inference,
        target_biological_unit=target.target_biological_unit,
        factor_ids=target.factor_ids,
        contrast_ids=target.contrast_ids,
        endpoint_ids=target.endpoint_ids,
        estimand_ids=estimand_ids,
        assessment_ids=assessments,
        target_population_support=support,
    )


def _target_support(
    specification: DesignSpecification,
    target: InferenceTarget,
    assessment_ids: tuple[str, ...],
) -> TargetPopulationSupport:
    if target.status is InferenceTargetStatus.MISSING:
        return TargetPopulationSupport.UNKNOWN
    if not target.population_of_inference.strip():
        return TargetPopulationSupport.UNKNOWN
    if target.status is not InferenceTargetStatus.USER_CONFIRMED:
        return TargetPopulationSupport.CONDITIONAL

    complete_refs = bool(target.factor_ids and target.contrast_ids and target.endpoint_ids)
    allocations_known = all(
        factor.allocation_level is not None
        for factor in specification.factors
        if factor.id in target.factor_ids
    )
    estimands_complete = bool(target.endpoint_ids) and all(
        any(
            estimand.endpoint_id == endpoint_id
            and set(target.factor_ids).issubset(estimand.factor_ids)
            for estimand in specification.estimands
        )
        for endpoint_id in target.endpoint_ids
    )
    unresolved_conflicts = any(
        contradiction.status == "unresolved" for contradiction in specification.contradictions
    )
    hierarchy_types = {node.type for node in specification.hierarchy.nodes}
    if (
        complete_refs
        and allocations_known
        and estimands_complete
        and target.target_biological_unit in hierarchy_types
        and assessment_ids
        and not unresolved_conflicts
    ):
        # "supported" significa soltanto mapping target-scope confermato e
        # strutturalmente completo. Non certifica validita o generalizzabilita.
        return TargetPopulationSupport.SUPPORTED
    return TargetPopulationSupport.CONDITIONAL


def _overall_support(targets: tuple[TargetHandoff, ...]) -> TargetPopulationSupport:
    if not targets:
        return TargetPopulationSupport.UNKNOWN
    values = {target.target_population_support for target in targets}
    if values == {TargetPopulationSupport.SUPPORTED}:
        return TargetPopulationSupport.SUPPORTED
    if values == {TargetPopulationSupport.UNKNOWN}:
        return TargetPopulationSupport.UNKNOWN
    return TargetPopulationSupport.CONDITIONAL


def _compile_clusters(specification: DesignSpecification) -> tuple[ClusterHandoff, ...]:
    cluster_types = {
        *(node.type for node in specification.hierarchy.nodes if node.type in CLUSTER_TYPES),
        *(
            cluster_type
            for assessment in specification.unit_assessments
            for cluster_type in assessment.cluster_types
        ),
        *(
            cluster_type
            for model in specification.models
            for cluster_type in model.declared_clustering
        ),
    }
    compiled: list[ClusterHandoff] = []
    for node_type in sorted(cluster_types, key=str):
        nodes = tuple(node for node in specification.hierarchy.nodes if node.type is node_type)
        assessment_ids = tuple(
            assessment.id
            for assessment in specification.unit_assessments
            if node_type in assessment.cluster_types
        )
        source_models = tuple(
            model for model in specification.models if node_type in model.declared_clustering
        )
        evidence_ids = tuple(
            dict.fromkeys(
                [
                    *(evidence for node in nodes for evidence in node.evidence_ids),
                    *(evidence for model in source_models for evidence in model.evidence_ids),
                ]
            )
        )
        compiled.append(
            ClusterHandoff(
                node_type=node_type,
                node_ids=tuple(node.id for node in nodes),
                source_assessment_ids=assessment_ids,
                source_model_ids=tuple(model.id for model in source_models),
                evidence_ids=evidence_ids,
            )
        )
    return tuple(compiled)


def _compile_unresolved(
    specification: DesignSpecification,
    questions: tuple[Question, ...],
    blocking_question_ids: tuple[str, ...],
) -> tuple[UnresolvedAssumption, ...]:
    blocking = set(blocking_question_ids)
    unresolved: list[UnresolvedAssumption] = []
    for question in questions:
        question_id = question.id
        scope = question.scope
        unresolved.append(
            UnresolvedAssumption(
                id=stable_id("asm", specification.specification_id, question_id),
                code=question.missing_field or "source_question",
                message=question.text,
                blocking=question_id in blocking,
                inference_target_id=(scope.inference_target_id if scope is not None else None),
                source_question_id=question_id,
            )
        )

    for contradiction in specification.contradictions:
        if contradiction.status != "unresolved":
            continue
        unresolved.append(
            UnresolvedAssumption(
                id=stable_id("asm", specification.specification_id, contradiction.id),
                code="unresolved_contradiction",
                message=contradiction.description,
                blocking=True,
                source_contradiction_id=contradiction.id,
            )
        )

    mismatched_assessment_ids: set[str] = set()
    scoped_items = [
        *(("n statement", item.id, item.scope) for item in specification.n_statements),
        *(("assessment", item.id, item.scope) for item in specification.unit_assessments),
        *(
            ("question", item.id, item.scope)
            for item in specification.questions
            if item.scope is not None
        ),
    ]
    for owner_kind, owner_id, scope in scoped_items:
        mismatches = _explicit_target_mismatches(specification, scope)
        if mismatches:
            target_id = scope.inference_target_id
            if owner_kind == "assessment":
                mismatched_assessment_ids.add(owner_id)
            for dimension in mismatches:
                unresolved.append(
                    UnresolvedAssumption(
                        id=stable_id(
                            "asm",
                            specification.specification_id,
                            owner_id,
                            "scope-target-mismatch",
                            dimension,
                        ),
                        code=f"scope_target_{dimension}_mismatch",
                        message=(
                            f"{owner_kind.capitalize()} {owner_id} usa {dimension} "
                            f"incompatibile con il target inferenziale {target_id}."
                        ),
                        blocking=True,
                        inference_target_id=target_id,
                    )
                )
    for assessment in specification.unit_assessments:
        if assessment.id in mismatched_assessment_ids:
            continue
        if _assessment_target_id(specification, assessment.scope) is not None:
            continue
        unresolved.append(
            UnresolvedAssumption(
                id=stable_id("asm", specification.specification_id, assessment.id, "unscoped"),
                code="unscoped_unit_assessment",
                message=(f"L'assessment {assessment.id} non e collegato a un target inferenziale."),
                blocking=True,
            )
        )

    by_id = {assumption.id: assumption for assumption in unresolved}
    return tuple(by_id.values())


def _assessment_target_id(specification: DesignSpecification, scope: NScope) -> str | None:
    """Collega uno scope legacy solo quando esiste un unico target compatibile.

    Gli assessment prodotti dalla baseline precedente non contengono
    ``inference_target_id``. Il compiler puo riusarli senza riscrivere il grafo quando
    factor/contrast/endpoint identificano un solo target. Con zero o piu candidati si
    astiene: nessun prodotto cartesiano e nessun fallback globale.
    """

    explicit = scope.inference_target_id
    if explicit is not None:
        target = next(
            (
                candidate
                for candidate in specification.inference_targets
                if candidate.id == explicit
            ),
            None,
        )
        if target is None or _scope_target_mismatches(specification, scope, target):
            return None
        return explicit

    factor_id = scope.factor_id
    contrast_id = scope.contrast_id
    endpoint_id = scope.endpoint_id
    dimensions = (factor_id, contrast_id, endpoint_id)
    if not any(dimensions):
        return None

    candidates = [
        target.id
        for target in specification.inference_targets
        if (factor_id is None or factor_id in target.factor_ids)
        and (contrast_id is None or contrast_id in target.contrast_ids)
        and (endpoint_id is None or endpoint_id in target.endpoint_ids)
        and not _scope_target_mismatches(specification, scope, target)
    ]
    return candidates[0] if len(candidates) == 1 else None


def _explicit_target_mismatches(
    specification: DesignSpecification,
    scope: NScope,
) -> tuple[str, ...]:
    target_id = scope.inference_target_id
    if target_id is None:
        return ()
    target = next(
        (candidate for candidate in specification.inference_targets if candidate.id == target_id),
        None,
    )
    if target is None:
        return ()
    return _scope_target_mismatches(specification, scope, target)


def _scope_target_mismatches(
    specification: DesignSpecification,
    scope: NScope,
    target: InferenceTarget,
) -> tuple[str, ...]:
    return inference_target_scope_mismatches(
        scope,
        target,
        factors={factor.id: factor for factor in specification.factors},
        contrasts={contrast.id: contrast for contrast in specification.contrasts},
        endpoints={endpoint.id: endpoint for endpoint in specification.endpoints},
    )
