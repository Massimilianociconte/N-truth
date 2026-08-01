"""Contratti scientifici introdotti dal PRD N-Truth v3."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ntruth.graph.builder import BuildResult
from ntruth.graph.validation import validate_hierarchy
from ntruth.rules.engine import apply_rules
from ntruth.schemas.core import (
    AlertClass,
    Determinability,
    EvidenceSpan,
    EvidenceType,
    Provenance,
    ProvenanceKind,
    Severity,
)
from ntruth.schemas.experiment import (
    Alert,
    ConditionalScenario,
    Contrast,
    Endpoint,
    Estimand,
    ExperimentBlock,
    Factor,
    Hierarchy,
    Inferability,
    NScope,
    RiskLabel,
    StatisticalModelFact,
    UnitAssessment,
    Versions,
)
from ntruth.schemas.graph import GraphNode, GraphRelation, NodeType, RelationType
from ntruth.schemas.rules import Rule, Ruleset


def _provenance(
    origin: ProvenanceKind = ProvenanceKind.EXPLICIT,
    *evidence_ids: str,
) -> Provenance:
    return Provenance(origin=origin, evidence_ids=evidence_ids)


def _versions() -> Versions:
    return Versions(
        schema_version="0.2.0",
        parser_version="0.2.0",
        graph_version="0.2.0",
        ruleset_id="ntruth-core",
        ruleset_version="0.2.0",
    )


def test_evidence_taxonomy_has_exactly_the_eight_v3_categories() -> None:
    assert {item.value for item in EvidenceType} == {
        "STRUCTURAL_FACT",
        "AUTHOR_ASSERTION",
        "SAMPLE_METADATA",
        "STATISTICAL_CODE",
        "USER_CONFIRMATION",
        "MODEL_INFERENCE",
        "DERIVED_FACT",
        "CONFLICTING_EVIDENCE",
    }

    span = EvidenceSpan(
        id="ev-structural",
        file_id="methods.pdf",
        text="Each culture was split into four wells.",
        evidence_type=EvidenceType.STRUCTURAL_FACT,
        page=4,
        document_version="accepted-v2",
        extraction_method="pdf_text_layer",
        confidence=0.93,
    )
    assert span.page == 4
    assert span.document_version == "accepted-v2"
    assert span.extraction_method == "pdf_text_layer"


def test_provenance_timestamp_is_explicit_and_never_generated_implicitly() -> None:
    provenance = Provenance(
        origin=ProvenanceKind.USER,
        document_version="accepted-manuscript-v2",
        extraction_method="manual graph correction",
        correction_role="biostatistician",
    )
    assert provenance.timestamp is None

    timestamp = datetime(2026, 8, 1, 9, 30, tzinfo=UTC)
    recorded = provenance.model_copy(update={"timestamp": timestamp})
    assert recorded.timestamp == timestamp


def test_factor_separates_allocation_from_application_and_syncs_legacy_aliases() -> None:
    factor = Factor(
        id="fac-treatment",
        name="treatment",
        levels=("control", "drug"),
        allocation_level=NodeType.CELL_CULTURE,
        application_level=NodeType.WELL,
        allocation_confidence=0.9,
        application_confidence=0.8,
        randomized=True,
        provenance=_provenance(),
    )
    assert factor.assignment_level is NodeType.CELL_CULTURE
    assert factor.assignment_confidence == 0.9
    assert factor.application_level is NodeType.WELL
    assert factor.randomised is True

    legacy = Factor(
        id="fac-legacy",
        name="treatment",
        assignment_level=NodeType.PLATE,
        assignment_confidence=0.75,
        provenance=_provenance(),
    )
    assert legacy.allocation_level is NodeType.PLATE
    assert legacy.allocation_confidence == 0.75


def test_factor_uses_canonical_v3_value_when_a_legacy_alias_is_stale() -> None:
    factor = Factor(
        id="fac-conflict",
        name="treatment",
        allocation_level=NodeType.CELL_CULTURE,
        assignment_level=NodeType.WELL,
        provenance=_provenance(),
    )
    assert factor.allocation_level is NodeType.CELL_CULTURE
    assert factor.assignment_level is NodeType.CELL_CULTURE


@pytest.mark.parametrize(
    "field_name, invalid_level",
    [
        ("allocation_level", NodeType.FACTOR),
        ("allocation_level", NodeType.ENDPOINT),
        ("application_level", NodeType.ESTIMAND),
    ],
)
def test_factor_rejects_non_allocatable_design_objects(
    field_name: str, invalid_level: NodeType
) -> None:
    with pytest.raises(ValidationError, match="non e un NodeType allocabile"):
        Factor(
            id="fac-invalid",
            name="treatment",
            provenance=_provenance(),
            **{field_name: invalid_level},
        )


def test_contrast_supports_multifactor_v3_and_preserves_legacy_fields() -> None:
    contrast = Contrast(
        id="cnt-main",
        label="drug_by_time",
        factor_ids=("treatment", "time"),
        compared_levels=("control", "drug"),
        endpoint_id="end-fluorescence",
        provenance=_provenance(),
    )
    assert contrast.factor_id == "treatment"
    assert contrast.group_a == "control"
    assert contrast.group_b == "drug"
    assert contrast.endpoint_ids == ("end-fluorescence",)

    legacy = Contrast(
        id="cnt-legacy",
        label="drug_vs_control",
        factor_id="treatment",
        group_a="drug",
        group_b="control",
        provenance=_provenance(),
    )
    assert legacy.factor_ids == ("treatment",)
    assert legacy.compared_levels == ("drug", "control")


def test_estimand_requires_the_minimum_inferential_object_and_is_block_scoped() -> None:
    factor = Factor(id="fac", name="treatment", provenance=_provenance())
    endpoint = Endpoint(id="end", name="fluorescence", provenance=_provenance())
    estimand = Estimand(
        id="est",
        endpoint_id=endpoint.id,
        effect_measure="mean difference",
        target_population_or_unit="sampled primary cultures",
        generalization_level="culture",
        factor_ids=(factor.id,),
        condition="drug versus control",
    )
    block = ExperimentBlock(
        id="blk",
        document_id="doc",
        factors=(factor,),
        endpoints=(endpoint,),
        estimands=(estimand,),
        determinability=Determinability.MULTIPLE_PLAUSIBLE_GRAPHS,
        versions=_versions(),
    )
    assert block.estimands == (estimand,)
    assert block.determinability is Determinability.MULTIPLE_PLAUSIBLE_GRAPHS

    with pytest.raises(ValidationError, match="effect_measure"):
        estimand.model_copy(update={"effect_measure": ""}, deep=True).__class__.model_validate(
            estimand.model_dump() | {"effect_measure": ""}
        )


def test_conditional_scenario_keeps_both_n_alternatives_and_sets_inferability() -> None:
    scenario = ConditionalScenario(
        conditional_on="cultures_are_independent_preparations",
        if_confirmed={"control": 4, "drug": 4},
        if_rejected={"control": 1, "drug": 1},
        question="Le colture derivano da preparazioni indipendenti?",
        rule_id="EU-CULT-004",
    )
    assessment = UnitAssessment(
        id="uas",
        scope=NScope(is_global=True),
        conditional_scenarios=(scenario,),
        provenance=_provenance(ProvenanceKind.DERIVED),
    )
    assert assessment.inferability is Inferability.CONDITIONAL
    assert assessment.n_independent is None
    assert assessment.conditional_scenarios[0].if_confirmed["drug"] == 4


def test_declared_clustering_is_separate_from_factor_allocation() -> None:
    model = StatisticalModelFact(
        id="mdl",
        kind="mixed",
        declared_clustering=(NodeType.CELL_CULTURE, NodeType.WELL),
        provenance=_provenance(),
    )
    factor = Factor(id="fac", name="treatment", provenance=_provenance())
    assert model.accounts_for == (NodeType.CELL_CULTURE, NodeType.WELL)
    assert factor.allocation_level is None


def test_v3_graph_vocabulary_is_available_without_removing_legacy_terms() -> None:
    assert {
        RelationType.SPLIT_FROM,
        RelationType.POOLED_FROM,
        RelationType.PAIRED_WITH,
        RelationType.MATCHED_WITH,
        RelationType.BLOCKED_BY,
        RelationType.CROSSED_WITH,
        RelationType.SAME_SOURCE_AS,
        RelationType.ALLOCATED_TO,
        RelationType.APPLIED_TO,
        RelationType.BELONGS_TO_GROUP,
        RelationType.SUPPORTS,
        RelationType.DECLARES_CLUSTERING,
    } <= set(RelationType)
    assert {
        NodeType.THAW,
        NodeType.PASSAGE,
        NodeType.IMAGE,
        NodeType.OBJECT,
        NodeType.SIGNAL,
        NodeType.TIMEPOINT,
        NodeType.ASSAY_RESULT,
        NodeType.ESTIMAND,
        NodeType.INFERENCE_TARGET,
        NodeType.CODE_SPAN,
    } <= set(NodeType)


def test_candidate_model_nodes_and_edges_require_localized_evidence() -> None:
    nodes = (
        GraphNode(
            id="candidate",
            type=NodeType.CELL_CULTURE,
            label="candidate culture",
            provenance=_provenance(ProvenanceKind.MODEL),
            confidence=0.7,
        ),
        GraphNode(
            id="well",
            type=NodeType.WELL,
            label="well",
            provenance=_provenance(),
        ),
    )
    relation = GraphRelation(
        id="candidate-edge",
        type=RelationType.NESTED_IN,
        source="well",
        target="candidate",
        provenance=_provenance(ProvenanceKind.MODEL),
        confidence=0.6,
    )
    codes = {
        item.code for item in validate_hierarchy(Hierarchy(nodes=nodes, relations=(relation,)))
    }
    assert {"model_node_without_evidence", "model_relation_without_evidence"} <= codes

    no_confidence = GraphNode(
        id="candidate-without-confidence",
        type=NodeType.CELL_CULTURE,
        label="candidate culture",
        evidence_ids=("ev-model",),
        provenance=_provenance(ProvenanceKind.MODEL, "ev-model"),
    )
    codes = {item.code for item in validate_hierarchy(Hierarchy(nodes=(no_confidence,)))}
    assert "model_node_without_confidence" in codes


def test_rules_propagate_alert_class_and_rank_decisive_questions() -> None:
    factor = Factor(
        id="fac",
        name="treatment",
        allocation_level=NodeType.CELL_CULTURE,
        allocation_confidence=0.85,
        provenance=_provenance(),
    )
    endpoint = Endpoint(id="end", name="response", provenance=_provenance())
    contrast = Contrast(
        id="cnt",
        label="treated_vs_control",
        factor_id=factor.id,
        endpoint_ids=(endpoint.id,),
        provenance=_provenance(),
    )
    assessment = UnitAssessment(
        id="uas",
        scope=NScope(factor_id=factor.id, contrast_id=contrast.id, endpoint_id=endpoint.id),
        inferability=Inferability.INFERABLE,
        n_independent=4,
        risk=RiskLabel.NO_ISSUE,
        provenance=_provenance(ProvenanceKind.DERIVED),
    )
    build = BuildResult(
        hierarchy=Hierarchy(),
        factors=(factor,),
        contrasts=(contrast,),
        endpoints=(endpoint,),
    )
    rule = Rule(
        rule_id="V3-TEST",
        version="1.0.0",
        domain="contract",
        inference="scope exceeds replication",
        severity=Severity.HIGH,
        alert_class=AlertClass.INFERENCE_SCOPE,
        questions=("Qual e la popolazione target?",),
    )
    result = apply_rules(
        "blk",
        build,
        (assessment,),
        Ruleset(ruleset_id="contract", version="1.0.0", rules=(rule,)),
    )
    assert result.alerts[0].alert_class is AlertClass.INFERENCE_SCOPE
    assert result.alerts[0].premise_confidence == 0.6
    assert result.alerts[0].confidence == result.alerts[0].premise_confidence
    assert result.questions[0].decisive is True
    assert result.questions[0].priority == 80
    assert result.questions[0].impact == AlertClass.INFERENCE_SCOPE.value
    assert result.assessments[0].risk is RiskLabel.NO_ISSUE

    dependence_rule = rule.model_copy(
        update={
            "rule_id": "V3-DEPENDENCE",
            "alert_class": AlertClass.ANALYTICAL_DEPENDENCE,
        }
    )
    dependence_result = apply_rules(
        "blk",
        build,
        (assessment,),
        Ruleset(ruleset_id="contract", version="1.0.0", rules=(dependence_rule,)),
    )
    assert dependence_result.assessments[0].risk is RiskLabel.LIKELY


def test_alert_legacy_confidence_is_a_deprecated_premise_alias() -> None:
    alert = Alert(
        id="alr",
        rule_id="V3-TEST",
        ruleset_version="1.0.0",
        severity=Severity.INFO,
        message="candidate premises",
        missing_information=("allocation level",),
        confidence=0.4,
        provenance=_provenance(ProvenanceKind.RULE),
    )
    assert alert.premise_confidence == 0.4
