"""Contratto del target inferenziale e design compiler conservativo."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from ntruth.design import (
    CompilationStatus,
    DesignSpecification,
    TargetPopulationSupport,
    compile_experiment_block,
    design_specification_json_schema,
    dumps_design_specification,
    load_design_specification,
    loads_design_specification,
    write_design_json_schema,
    write_design_specification,
)
from ntruth.graph.validation import validate_experiment_block
from ntruth.reporting import render_html
from ntruth.schemas.core import EvidenceSpan, Provenance, ProvenanceKind
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
    UnitAssessment,
    Versions,
)
from ntruth.schemas.graph import GraphNode, GraphRelation, NodeType, RelationType
from ntruth.schemas.report import Report


def _versions() -> Versions:
    return Versions(
        schema_version="0.1.0",
        parser_version="0.1.0",
        graph_version="0.1.0",
        ruleset_id="ntruth-core",
        ruleset_version="0.1.0",
    )


def _user_provenance() -> Provenance:
    return Provenance(origin=ProvenanceKind.USER, actor_role="researcher")


def _derived_provenance() -> Provenance:
    return Provenance(origin=ProvenanceKind.DERIVED, derivation="fixture deterministica")


def _complete_block() -> ExperimentBlock:
    factor = Factor(
        id="factor-treatment",
        name="treatment",
        levels=("drug", "vehicle"),
        kind="treatment",
        assignment_level=NodeType.WELL,
        assignment_confidence=1.0,
        application_level=NodeType.WELL,
        application_confidence=1.0,
        provenance=_user_provenance(),
    )
    endpoint_a = Endpoint(
        id="endpoint-intensity",
        name="cell intensity",
        measured_on=NodeType.CELL,
        provenance=_user_provenance(),
    )
    endpoint_b = Endpoint(
        id="endpoint-viability",
        name="well viability",
        measured_on=NodeType.WELL,
        provenance=_user_provenance(),
    )
    contrast = Contrast(
        id="contrast-drug-vehicle",
        label="drug vs vehicle",
        factor_id=factor.id,
        group_a="drug",
        group_b="vehicle",
        endpoint_ids=(endpoint_a.id, endpoint_b.id),
        provenance=_user_provenance(),
    )
    target_a = InferenceTarget(
        id="target-cell-line",
        question_text="Il farmaco cambia l'intensita nella cell line?",
        claim_text="Effetto nella cell line studiata.",
        population_of_inference="cell line studiata nelle condizioni dichiarate",
        factor_ids=(factor.id,),
        contrast_ids=(contrast.id,),
        endpoint_ids=(endpoint_a.id,),
        target_biological_unit=NodeType.CELL_LINE,
        provenance=_user_provenance(),
        status=InferenceTargetStatus.USER_CONFIRMED,
    )
    target_b = InferenceTarget(
        id="target-wells",
        question_text="Il farmaco cambia la vitalita dei pozzetti trattati?",
        claim_text="Effetto sui pozzetti di questa preparazione.",
        population_of_inference="pozzetti della preparazione studiata",
        factor_ids=(factor.id,),
        contrast_ids=(contrast.id,),
        endpoint_ids=(endpoint_b.id,),
        target_biological_unit=NodeType.CELL_CULTURE,
        provenance=_user_provenance(),
        status=InferenceTargetStatus.USER_CONFIRMED,
    )
    estimands = (
        Estimand(
            id="estimand-intensity",
            endpoint_id=endpoint_a.id,
            effect_measure="mean difference",
            target_population_or_unit=target_a.population_of_inference,
            generalization_level="cell line",
            factor_ids=(factor.id,),
            provenance=_user_provenance(),
        ),
        Estimand(
            id="estimand-viability",
            endpoint_id=endpoint_b.id,
            effect_measure="mean difference",
            target_population_or_unit=target_b.population_of_inference,
            generalization_level="cell culture",
            factor_ids=(factor.id,),
            provenance=_user_provenance(),
        ),
    )

    cell_line = GraphNode(
        id="cell-line-1",
        type=NodeType.CELL_LINE,
        label="cell line",
        count=1,
        provenance=_user_provenance(),
    )
    culture = GraphNode(
        id="culture-1",
        type=NodeType.CELL_CULTURE,
        label="culture",
        count=3,
        provenance=_user_provenance(),
    )
    well = GraphNode(
        id="well-1",
        type=NodeType.WELL,
        label="wells",
        count=12,
        provenance=_user_provenance(),
    )
    cell = GraphNode(
        id="cell-1",
        type=NodeType.CELL,
        label="cells",
        count=120,
        provenance=_user_provenance(),
    )
    nested_well = GraphRelation(
        id="well-in-culture",
        type=RelationType.NESTED_IN,
        source=well.id,
        target=culture.id,
        provenance=_user_provenance(),
    )
    culture_from_line = GraphRelation(
        id="culture-from-line",
        type=RelationType.DERIVED_FROM,
        source=culture.id,
        target=cell_line.id,
        provenance=_user_provenance(),
    )
    nested_cell = GraphRelation(
        id="cell-in-well",
        type=RelationType.NESTED_IN,
        source=cell.id,
        target=well.id,
        provenance=_user_provenance(),
    )
    repeated = GraphRelation(
        id="cell-repeat",
        type=RelationType.REPEATED_MEASURE_OF,
        source=cell.id,
        target=well.id,
        provenance=_user_provenance(),
    )
    assessments = (
        UnitAssessment(
            id="assessment-cell-line",
            scope=NScope(
                factor_id=factor.id,
                contrast_id=contrast.id,
                endpoint_id=endpoint_a.id,
                inference_target_id=target_a.id,
            ),
            experimental_unit=NodeType.WELL,
            observational_unit=NodeType.CELL,
            cluster_types=(NodeType.CELL_CULTURE,),
            inferability=Inferability.REQUIRES_CONFIRMATION,
            provenance=_derived_provenance(),
        ),
        UnitAssessment(
            id="assessment-wells",
            scope=NScope(
                factor_id=factor.id,
                contrast_id=contrast.id,
                endpoint_id=endpoint_b.id,
                inference_target_id=target_b.id,
            ),
            experimental_unit=NodeType.WELL,
            observational_unit=NodeType.WELL,
            cluster_types=(NodeType.CELL_CULTURE,),
            inferability=Inferability.REQUIRES_CONFIRMATION,
            provenance=_derived_provenance(),
        ),
    )
    return ExperimentBlock(
        id="block-1",
        title="Two scoped targets",
        document_id="document-1",
        inference_targets=(target_a, target_b),
        factors=(factor,),
        contrasts=(contrast,),
        endpoints=(endpoint_a, endpoint_b),
        estimands=estimands,
        hierarchy=Hierarchy(
            nodes=(cell_line, culture, well, cell),
            relations=(culture_from_line, nested_well, nested_cell, repeated),
        ),
        unit_assessments=assessments,
        versions=_versions(),
    )


def test_legacy_block_and_scope_remain_valid_without_inference_target() -> None:
    block = ExperimentBlock(
        id="legacy",
        document_id="document-legacy",
        versions=_versions(),
    )
    payload = block.model_dump(mode="json", exclude={"inference_targets"})
    restored = ExperimentBlock.model_validate(payload)

    assert restored.inference_targets == ()
    legacy_scope = NScope(factor_id="factor-legacy")
    assert legacy_scope.inference_target_id is None
    assert legacy_scope.key() == ("factor-legacy", None, None, None, None)
    assert NScope(factor_id="factor-legacy", inference_target_id="target-new").key() == (
        "factor-legacy",
        None,
        None,
        None,
        None,
        "target-new",
    )


def test_extracted_target_requires_local_evidence_and_provenance() -> None:
    with pytest.raises(ValidationError, match="senza evidence_ids"):
        InferenceTarget(
            id="target-extracted",
            question_text="Domanda estratta",
            provenance=Provenance(origin=ProvenanceKind.EXPLICIT),
            status=InferenceTargetStatus.EXTRACTED,
        )

    evidence = EvidenceSpan(id="ev-1", file_id="file-1", text="Claim source")
    target = InferenceTarget(
        id="target-extracted",
        question_text="Domanda estratta",
        evidence_ids=(evidence.id,),
        provenance=Provenance(
            origin=ProvenanceKind.EXPLICIT,
            evidence_ids=(evidence.id,),
        ),
        status=InferenceTargetStatus.EXTRACTED,
    )
    block = ExperimentBlock(
        id="block-evidence",
        document_id="document-evidence",
        inference_targets=(target,),
        evidence=(evidence,),
        versions=_versions(),
    )
    assert block.inference_targets[0].evidence_ids == ("ev-1",)


def test_block_rejects_unknown_target_references() -> None:
    target = InferenceTarget(
        id="target-invalid",
        question_text="Domanda",
        population_of_inference="popolazione",
        factor_ids=("missing-factor",),
        provenance=_user_provenance(),
        status=InferenceTargetStatus.USER_CONFIRMED,
    )
    with pytest.raises(ValidationError, match="factor refs sconosciuti"):
        ExperimentBlock(
            id="block-invalid",
            document_id="document-invalid",
            inference_targets=(target,),
            versions=_versions(),
        )


def test_two_targets_on_same_design_remain_distinct_scopes() -> None:
    compilation = compile_experiment_block(_complete_block())
    targets = {
        target.inference_target_id: target for target in compilation.analysis_handoff.targets
    }

    assert compilation.status is CompilationStatus.READY
    assert compilation.abstained is False
    assert targets["target-cell-line"].endpoint_ids == ("endpoint-intensity",)
    assert targets["target-cell-line"].assessment_ids == ("assessment-cell-line",)
    assert targets["target-wells"].endpoint_ids == ("endpoint-viability",)
    assert targets["target-wells"].assessment_ids == ("assessment-wells",)
    assert all(
        target.target_population_support is TargetPopulationSupport.SUPPORTED
        for target in targets.values()
    )


def test_unique_legacy_assessment_scope_is_bound_without_cartesian_fallback() -> None:
    base = _complete_block()
    only_target = base.inference_targets[0]
    only_assessment = base.unit_assessments[0].model_copy(
        update={
            "scope": base.unit_assessments[0].scope.model_copy(update={"inference_target_id": None})
        }
    )
    block = base.model_copy(
        update={
            "inference_targets": (only_target,),
            "endpoints": (base.endpoints[0],),
            "estimands": (base.estimands[0],),
            "contrasts": (
                base.contrasts[0].model_copy(update={"endpoint_ids": (base.endpoints[0].id,)}),
            ),
            "unit_assessments": (only_assessment,),
        }
    )

    compilation = compile_experiment_block(block)

    assert compilation.status is CompilationStatus.READY
    assert compilation.analysis_handoff.targets[0].assessment_ids == (only_assessment.id,)
    assert not any(
        item.code == "unscoped_unit_assessment"
        for item in compilation.analysis_handoff.unresolved_assumptions
    )


def test_ambiguous_legacy_assessment_scope_remains_unbound() -> None:
    base = _complete_block()
    ambiguous = base.unit_assessments[0].model_copy(
        update={
            "scope": NScope(
                factor_id=base.factors[0].id,
                contrast_id=base.contrasts[0].id,
            )
        }
    )
    block = base.model_copy(update={"unit_assessments": (ambiguous,)})

    compilation = compile_experiment_block(block)

    assert compilation.status is CompilationStatus.ABSTAINED
    assert all(not target.assessment_ids for target in compilation.analysis_handoff.targets)
    assert any(
        item.code == "unscoped_unit_assessment" and item.blocking
        for item in compilation.analysis_handoff.unresolved_assumptions
    )


def test_explicit_cross_target_endpoint_mismatch_is_blocking_and_never_falls_back() -> None:
    base = _complete_block()
    mismatched = base.unit_assessments[0].model_copy(
        update={
            "scope": base.unit_assessments[0].scope.model_copy(
                update={"inference_target_id": base.inference_targets[1].id}
            )
        }
    )
    block = base.model_copy(update={"unit_assessments": (mismatched,)})

    violations = validate_experiment_block(block)
    compilation = compile_experiment_block(block)

    assert "scope_target_endpoint_mismatch" in {item.code for item in violations}
    assert compilation.status is CompilationStatus.ABSTAINED
    assert all(not target.assessment_ids for target in compilation.analysis_handoff.targets)
    assert any(
        item.code == "scope_target_endpoint_mismatch"
        and item.inference_target_id == base.inference_targets[1].id
        and item.blocking
        for item in compilation.analysis_handoff.unresolved_assumptions
    )


def test_mismatched_n_statement_scope_alone_forces_compiler_abstention() -> None:
    base = _complete_block()
    statement = NStatement(
        id="n-cross-target",
        value=12,
        entity_type="wells",
        node_type=NodeType.WELL,
        scope=NScope(
            factor_id=base.factors[0].id,
            contrast_id=base.contrasts[0].id,
            endpoint_id=base.endpoints[0].id,
            inference_target_id=base.inference_targets[1].id,
        ),
        kind=NKind.ANALYZED,
        provenance=_user_provenance(),
    )
    block = base.model_copy(update={"n_statements": (statement,)})

    compilation = compile_experiment_block(block)

    assert compilation.status is CompilationStatus.ABSTAINED
    assert any(
        item.code == "scope_target_endpoint_mismatch" and item.blocking
        for item in compilation.analysis_handoff.unresolved_assumptions
    )


def test_explicit_cross_target_factor_contrast_and_endpoint_mismatches_all_abstain() -> None:
    base = _complete_block()
    second_factor = Factor(
        id="factor-genotype",
        name="genotype",
        levels=("wild-type", "mutant"),
        kind="genotype",
        assignment_level=NodeType.CELL_CULTURE,
        assignment_confidence=1.0,
        provenance=_user_provenance(),
    )
    second_contrast = Contrast(
        id="contrast-mutant-wild-type",
        label="mutant vs wild-type",
        factor_id=second_factor.id,
        group_a="mutant",
        group_b="wild-type",
        endpoint_ids=(base.endpoints[1].id,),
        provenance=_user_provenance(),
    )
    second_target = base.inference_targets[1].model_copy(
        update={
            "factor_ids": (second_factor.id,),
            "contrast_ids": (second_contrast.id,),
        }
    )
    mismatched = base.unit_assessments[0].model_copy(
        update={
            "scope": base.unit_assessments[0].scope.model_copy(
                update={"inference_target_id": second_target.id}
            )
        }
    )
    block = base.model_copy(
        update={
            "factors": (*base.factors, second_factor),
            "contrasts": (*base.contrasts, second_contrast),
            "inference_targets": (base.inference_targets[0], second_target),
            "unit_assessments": (mismatched,),
        }
    )

    violations = validate_experiment_block(block)
    compilation = compile_experiment_block(block)
    expected_codes = {
        "scope_target_factor_mismatch",
        "scope_target_contrast_mismatch",
        "scope_target_endpoint_mismatch",
    }

    assert expected_codes <= {item.code for item in violations}
    assert compilation.status is CompilationStatus.ABSTAINED
    assert expected_codes <= {
        item.code for item in compilation.analysis_handoff.unresolved_assumptions
    }
    assert all(not target.assessment_ids for target in compilation.analysis_handoff.targets)


@pytest.mark.parametrize(
    ("scope_update", "endpoint_timepoints", "expected_code"),
    [
        ({"group": "placebo"}, (), "scope_target_group_mismatch"),
        ({"timepoint": "48 h"}, ("24 h",), "scope_target_timepoint_mismatch"),
    ],
)
def test_explicit_target_rejects_incompatible_group_or_timepoint(
    scope_update: dict[str, str],
    endpoint_timepoints: tuple[str, ...],
    expected_code: str,
) -> None:
    base = _complete_block()
    endpoint = base.endpoints[0].model_copy(update={"timepoints": endpoint_timepoints})
    assessment = base.unit_assessments[0].model_copy(
        update={"scope": base.unit_assessments[0].scope.model_copy(update=scope_update)}
    )
    block = base.model_copy(
        update={
            "endpoints": (endpoint, base.endpoints[1]),
            "unit_assessments": (assessment,),
        }
    )

    violations = validate_experiment_block(block)
    compilation = compile_experiment_block(block)

    assert expected_code in {item.code for item in violations}
    assert compilation.status is CompilationStatus.ABSTAINED
    assert any(
        item.code == expected_code and item.blocking
        for item in compilation.analysis_handoff.unresolved_assumptions
    )


def test_missing_target_forces_elicitation_and_abstention() -> None:
    block = ExperimentBlock(
        id="block-missing-target",
        document_id="document-missing-target",
        versions=_versions(),
    )
    compilation = compile_experiment_block(block)

    assert compilation.status is CompilationStatus.ABSTAINED
    assert compilation.abstained is True
    assert compilation.analysis_handoff.target_population_support is TargetPopulationSupport.UNKNOWN
    assert "inference_targets" in {
        question.missing_field for question in compilation.elicitation.questions
    }


def test_extracted_unconfirmed_target_stays_conditional() -> None:
    base = _complete_block()
    evidence = EvidenceSpan(id="ev-target", file_id="file-1", text="Target extracted")
    original = base.inference_targets[0]
    extracted = original.model_copy(
        update={
            "evidence_ids": (evidence.id,),
            "provenance": Provenance(
                origin=ProvenanceKind.EXPLICIT,
                evidence_ids=(evidence.id,),
            ),
            "status": InferenceTargetStatus.EXTRACTED,
        }
    )
    block = base.model_copy(
        update={
            "inference_targets": (extracted, base.inference_targets[1]),
            "evidence": (evidence,),
        }
    )
    block = ExperimentBlock.model_validate(block.model_dump(mode="json"))

    compilation = compile_experiment_block(block)
    target = compilation.analysis_handoff.targets[0]
    assert target.target_population_support is TargetPopulationSupport.CONDITIONAL
    assert compilation.abstained is True
    assert any(
        question.missing_field == "inference_targets[target-cell-line].status"
        for question in compilation.elicitation.questions
    )


def test_handoff_is_structural_and_neutral() -> None:
    handoff = compile_experiment_block(_complete_block()).analysis_handoff
    fields = set(handoff.model_dump())

    assert {"model_formula", "statistical_test", "power_analysis"}.isdisjoint(fields)
    assert handoff.prohibited_outputs == (
        "statistical_test_selection",
        "model_formula",
        "power_analysis",
    )
    assert len(handoff.nesting) == 3
    assert len(handoff.repeated_measures) == 1
    assert handoff.clusters[0].node_type is NodeType.CELL_CULTURE


def test_html_renders_factor_levels_and_every_handoff_estimand() -> None:
    block = _complete_block()
    compilation = compile_experiment_block(block)
    report = Report(
        report_id="report-html",
        project_id="project-html",
        project_name="HTML fixture",
        versions=block.versions,
        blocks=(block,),
        design_compilations={block.id: compilation},
    )

    rendered = render_html(report)

    assert "Fattori, allocazione e applicazione" in rendered
    assert "drug, vehicle" in rendered
    assert "Estimand nell'analysis handoff" in rendered
    for estimand in compilation.analysis_handoff.estimands:
        assert estimand.effect_measure in rendered
        assert estimand.target_population_or_unit in rendered


def test_design_json_and_schema_round_trip(tmp_path: Path) -> None:
    specification = DesignSpecification.from_experiment_block(_complete_block())
    payload = dumps_design_specification(specification)
    restored = loads_design_specification(payload)
    design_path = write_design_specification(specification, tmp_path / "design.json")
    schema_path = write_design_json_schema(tmp_path / "design.schema.json")
    schema = design_specification_json_schema()

    assert restored == specification
    assert load_design_specification(design_path) == specification
    assert schema_path.is_file()
    assert schema["title"] == "DesignSpecification"
    assert "inference_targets" in schema["properties"]
