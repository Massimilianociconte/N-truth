"""Compiler prospettico D0: contratti, astensione e lifecycle prudente."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ntruth.prospective import (
    ProspectiveD0CompileRequest,
    ProspectiveD0ValidationError,
    ProspectiveSessionNotFound,
    ProspectiveSessionRegistry,
    compile_prospective_d0,
)
from ntruth.reporting import write_all
from ntruth.schemas.core import Determinability, EvidenceType, content_checksum
from ntruth.schemas.experiment import (
    CountKind,
    CountQuantifier,
    ExclusionPhase,
    Inferability,
)
from ntruth.schemas.graph import NodeType
from ntruth.schemas.report import Report, VerificationSummary
from ntruth.verifier import output_policy_violations


def _payload() -> dict[str, object]:
    return {
        "draft": {
            "experimentBlockId": "EB-D0-TEST-001",
            "question": "Does treatment change viability at 24 hours?",
            "inferenceTarget": "wells in the declared cell-culture conditions",
            "factorName": "Treatment",
            "factorKind": "treatment",
            "levelA": "vehicle",
            "levelB": "drug",
            "endpointName": "cell viability",
            "endpointId": "EP-VIABILITY-24H",
            "measuredOn": "Well",
            "allocationLevel": "Well",
            "applicationLevel": "Well",
            "independentlyAssigned": "TRUE",
            "independenceMechanism": (
                "Each well is independently assigned using the recorded randomisation list."
            ),
            "sharedEnvironment": "plate P01 and acquisition day",
            "targetBiologicalUnit": "Well",
            "estimand": {
                "effectMeasure": "difference in mean viability",
                "targetPopulationOrUnit": "declared wells",
                "generalizationLevel": "declared cell-culture conditions",
                "timepoint": "24 h",
            },
            "reviewerRole": "prospective_researcher",
        },
        "rows": [
            {
                "sampleId": "D0-CTL-001",
                "sourceId": "SRC-001",
                "preparationId": "PREP-001",
                "cultureId": "CULT-001",
                "plateId": "P01",
                "wellId": "A01",
                "factorLevel": "vehicle",
                "timepoint": "24 h",
                "endpointId": "EP-VIABILITY-24H",
                "lifecycleStatus": "planned",
            },
            {
                "sampleId": "D0-CTL-002",
                "sourceId": "SRC-001",
                "preparationId": "PREP-001",
                "cultureId": "CULT-001",
                "plateId": "P01",
                "wellId": "A02",
                "factorLevel": "vehicle",
                "timepoint": "24 h",
                "endpointId": "EP-VIABILITY-24H",
                "lifecycleStatus": "planned",
            },
            {
                "sampleId": "D0-TRT-001",
                "sourceId": "SRC-001",
                "preparationId": "PREP-001",
                "cultureId": "CULT-001",
                "plateId": "P01",
                "wellId": "A03",
                "factorLevel": "drug",
                "timepoint": "24 h",
                "endpointId": "EP-VIABILITY-24H",
                "lifecycleStatus": "planned",
            },
            {
                "sampleId": "D0-TRT-002",
                "sourceId": "SRC-001",
                "preparationId": "PREP-001",
                "cultureId": "CULT-001",
                "plateId": "P01",
                "wellId": "A04",
                "factorLevel": "drug",
                "timepoint": "24 h",
                "endpointId": "EP-VIABILITY-24H",
                "lifecycleStatus": "planned",
            },
        ],
    }


def _request(payload: dict[str, object] | None = None) -> ProspectiveD0CompileRequest:
    return ProspectiveD0CompileRequest.model_validate(payload or _payload())


def test_complete_d0_request_compiles_to_verified_canonical_block() -> None:
    first = compile_prospective_d0(_request())
    second = compile_prospective_d0(_request())

    assert first.compilation_id == second.compilation_id
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.determinability is Determinability.DETERMINATE
    assert first.ready_for_handoff is True
    assert first.capability.status.value == "supported"
    assert first.design_compilation.status.value == "ready"
    assert first.verification.valid
    assert first.scientific_validation_status == "not_performed"
    assert first.compiler_version == "1.0.0"
    assert len(first.ruleset_checksum) == 64
    assert first.sample_sheet.factor_columns == ("factor_level_treatment",)
    assert len(first.block.unit_assessments) == 2
    assert {item.experimental_unit.value for item in first.block.unit_assessments} == {"Well"}
    assert {item.n_independent for item in first.block.unit_assessments} == {2}
    assert {item.biological_source_count for item in first.block.unit_assessments} == {1}
    assert all(item.analytical_unit is None for item in first.block.unit_assessments)

    planned = [item for item in first.block.count_records if item.kind is CountKind.PLANNED_N]
    independent = [
        item for item in first.block.count_records if item.kind is CountKind.INDEPENDENT_N
    ]
    allocated = [item for item in first.block.count_records if item.kind is CountKind.ALLOCATED_N]
    biological_sources = [
        item for item in first.block.count_records if item.kind is CountKind.BIOLOGICAL_SOURCE_COUNT
    ]
    assert [(item.value, item.quantifier) for item in planned] == [
        (2, CountQuantifier.EXACT),
        (2, CountQuantifier.EXACT),
    ]
    assert [(item.value, item.quantifier) for item in independent] == [
        (2, CountQuantifier.EXACT),
        (2, CountQuantifier.EXACT),
    ]
    assert all(item.value is None for item in allocated)
    assert all(item.quantifier is CountQuantifier.NOT_REPORTED for item in allocated)
    assert [(item.value, item.quantifier) for item in biological_sources] == [
        (1, CountQuantifier.EXACT),
        (1, CountQuantifier.EXACT),
    ]
    assert {item.scope.unit_type for item in biological_sources} == {NodeType.BIOLOGICAL_SOURCE}
    assert first.rule_evaluations
    assert {item.provenance.ruleset_version for item in first.block.count_records} == {
        first.block.versions.ruleset_version
    }
    assert {item.provenance.ruleset_version for item in first.block.unit_assessments} == {
        first.block.versions.ruleset_version
    }

    evidence_by_id = {item.id: item for item in first.block.evidence}
    for item in (*independent, *first.block.unit_assessments):
        linked = [evidence_by_id[evidence_id] for evidence_id in item.evidence_ids]
        assert {span.evidence_type for span in linked} >= {
            EvidenceType.USER_CONFIRMATION,
            EvidenceType.SAMPLE_METADATA,
        }
        user_sections = {
            span.section_id
            for span in linked
            if span.evidence_type is EvidenceType.USER_CONFIRMATION
        }
        assert user_sections >= {"allocation", "independence", "target", "estimand"}


def test_missing_estimand_and_target_unit_abstain_without_leaking_independent_n() -> None:
    payload = _payload()
    draft = dict(payload["draft"])  # type: ignore[arg-type]
    draft.pop("estimand")
    draft.pop("targetBiologicalUnit")
    payload["draft"] = draft

    result = compile_prospective_d0(_request(payload))

    assert result.determinability is Determinability.INSUFFICIENT_INFORMATION
    assert result.ready_for_handoff is False
    assert result.design_compilation.abstained is True
    assert {item.code for item in result.issues} >= {
        "missing_estimand",
        "missing_target_biological_unit",
    }
    assert all(item.experimental_unit is None for item in result.block.unit_assessments)
    assert all(item.n_independent is None for item in result.block.unit_assessments)
    assert not any(item.kind is CountKind.INDEPENDENT_N for item in result.block.count_records)
    assert any(
        question.missing_field == "estimands"
        for question in result.design_compilation.elicitation.questions
    )


def test_true_independence_rejects_vacuous_mechanism_placeholder() -> None:
    payload = _payload()
    draft = dict(payload["draft"])  # type: ignore[arg-type]
    draft["independenceMechanism"] = "yes"
    payload["draft"] = draft

    with pytest.raises(ValueError, match="operativo e non vacuo"):
        _request(payload)


def test_write_boundary_reverifies_block_and_ignores_stale_complete_cache(
    tmp_path: Path,
) -> None:
    compilation = compile_prospective_d0(_request())
    block = compilation.block
    source_count = next(
        item for item in block.count_records if item.kind is CountKind.INDEPENDENT_N
    )
    invalid_scope = source_count.scope.model_copy(
        update={
            "factor_id": None,
            "unknown_reasons": {
                **source_count.scope.unknown_reasons,
                "factor_id": "deliberate stale-verifier fixture",
            },
        }
    )
    injected = source_count.model_copy(
        update={
            "count_id": "tampered-independent-count-without-factor",
            "value": 99991,
            "scope": invalid_scope,
        }
    )
    tampered = block.model_copy(update={"count_records": (*block.count_records, injected)})
    report = Report(
        report_id="stale-verifier-report",
        project_id="stale-verifier-project",
        project_name="Stale verifier regression",
        versions=block.versions,
        blocks=(tampered,),
        design_compilations={block.id: compilation.design_compilation},
        verifier_results={
            block.id: VerificationSummary(
                status="complete",
                checked_invariants=("deliberately_stale_cache",),
            )
        },
    )

    written = write_all(report, tmp_path / "stale-verifier-export")
    exported = json.loads(written["json"].read_text(encoding="utf-8"))
    public_block = exported["blocks"][0]

    assert public_block["determinability"] == "INVALID_GRAPH"
    assert exported["status"] == "failed"
    assert exported["design_compilations"][block.id]["status"] == "abstained"
    assert exported["verifier_results"][block.id]["status"] == "failed"
    assert (
        "independent_count_without_operational_independence"
        in (exported["verifier_results"][block.id]["violation_codes"])
    )
    assert any(
        item["code"] == "independent_count_without_operational_independence"
        for item in exported["graph_violations"]
    )
    assert any("Verificatore hard live fallito" in item for item in exported["limits"])
    assert not any(
        item["kind"] == "independent_n" and item["value"] is not None
        for item in public_block["count_records"]
    )
    assert "99991" not in written["html"].read_text(encoding="utf-8")


def test_current_lifecycle_states_produce_bounds_not_false_exact_history() -> None:
    payload = _payload()
    rows = list(payload["rows"])  # type: ignore[arg-type]
    rows[0] = {**rows[0], "lifecycleStatus": "analysed"}
    payload["rows"] = rows

    result = compile_prospective_d0(_request(payload))
    vehicle_counts = {
        item.kind: item
        for item in result.block.count_records
        if item.scope.group_or_level == "vehicle"
    }

    assert vehicle_counts[CountKind.PLANNED_N].value == 2
    assert vehicle_counts[CountKind.PLANNED_N].quantifier is CountQuantifier.EXACT
    for kind in (
        CountKind.ALLOCATED_N,
        CountKind.TREATED_N,
        CountKind.OBSERVED_N,
    ):
        assert vehicle_counts[kind].value == 1
        assert vehicle_counts[kind].quantifier is CountQuantifier.LOWER_BOUND
    assert vehicle_counts[CountKind.ANALYSED_N].value == 1
    assert vehicle_counts[CountKind.ANALYSED_N].quantifier is CountQuantifier.EXACT
    assert vehicle_counts[CountKind.EXCLUDED_N].value is None
    assert vehicle_counts[CountKind.EXCLUDED_N].quantifier is CountQuantifier.NOT_REPORTED


def test_exclusion_requires_phase_author_and_actual_criterion() -> None:
    payload = _payload()
    rows = list(payload["rows"])  # type: ignore[arg-type]
    rows[0] = {
        **rows[0],
        "lifecycleStatus": "excluded",
        "exclusionReason": ("QC threshold exceeded | post-treatment | author: wet_lab_reviewer"),
    }
    payload["rows"] = rows
    result = compile_prospective_d0(_request(payload))

    assert len(result.block.exclusion_records) == 1
    exclusion = result.block.exclusion_records[0]
    assert exclusion.phase is ExclusionPhase.POST_TREATMENT
    assert exclusion.author_role == "wet_lab_reviewer"
    assert exclusion.reason == "QC threshold exceeded"
    assert exclusion.evidence_ids
    graph_node = next(item for item in result.block.hierarchy.nodes if item.id == exclusion.unit_id)
    assert graph_node.type is exclusion.unit_type is NodeType.WELL

    invalid = _payload()
    invalid_rows = list(invalid["rows"])  # type: ignore[arg-type]
    invalid_rows[0] = {
        **invalid_rows[0],
        "lifecycleStatus": "excluded",
        "exclusionReason": "post-treatment | autore: revisore_wet_lab",
    }
    invalid["rows"] = invalid_rows
    with pytest.raises(ProspectiveD0ValidationError) as caught:
        compile_prospective_d0(_request(invalid))
    assert "missing_exclusion_criterion" in {item.code for item in caught.value.issues}


@pytest.mark.parametrize(
    ("reason", "phase", "author_role", "expected_code"),
    [
        (
            "contamination | post-measurement | author: wet_lab",
            "post_treatment",
            "wet_lab",
            "conflicting_exclusion_phase",
        ),
        (
            "contamination | post-treatment | author: statistician",
            "post_treatment",
            "wet_lab",
            "conflicting_exclusion_author_role",
        ),
    ],
)
def test_structured_and_packed_exclusion_metadata_cannot_conflict_silently(
    reason: str,
    phase: str,
    author_role: str,
    expected_code: str,
) -> None:
    payload = _payload()
    rows = list(payload["rows"])  # type: ignore[arg-type]
    rows[0] = {
        **rows[0],
        "lifecycleStatus": "excluded",
        "exclusionReason": reason,
        "exclusionPhase": phase,
        "exclusionAuthorRole": author_role,
    }
    payload["rows"] = rows

    with pytest.raises(ProspectiveD0ValidationError) as caught:
        compile_prospective_d0(_request(payload))

    assert expected_code in {item.code for item in caught.value.issues}


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (
            {"wellId": "A01", "factorLevel": "drug"},
            "duplicate_well_allocation_unit",
        ),
        ({"endpointId": "EP-OTHER"}, "row_endpoint_mismatch"),
        ({"factorLevel": "dose-high"}, "factor_level_outside_primary_contrast"),
    ],
)
def test_cross_row_inconsistencies_fail_before_session_or_export(
    mutation: dict[str, str], expected_code: str
) -> None:
    payload = _payload()
    rows = list(payload["rows"])  # type: ignore[arg-type]
    rows[1] = {**rows[1], **mutation}
    payload["rows"] = rows

    with pytest.raises(ProspectiveD0ValidationError) as caught:
        compile_prospective_d0(_request(payload))

    assert expected_code in {item.code for item in caught.value.issues}


def test_multiple_timepoints_are_valid_input_but_outside_d0_capability() -> None:
    payload = _payload()
    rows = list(payload["rows"])  # type: ignore[arg-type]
    rows[1] = {**rows[1], "timepoint": "48 h"}
    payload["rows"] = rows

    result = compile_prospective_d0(_request(payload))

    assert result.determinability is Determinability.OUT_OF_SCOPE
    assert result.capability.status.value == "out_of_scope"
    assert "multiple_timepoints" in {item.value for item in result.capability.reason_codes}
    assert result.design_compilation.status.value == "abstained"
    assert result.design_compilation.abstained is True
    assert result.design_compilation.elicitation.complete is False
    assert output_policy_violations(result.block) == ()
    assert not any(item.rule_id in {"GEN-001", "CC-006"} for item in result.block.alerts)
    projected_evaluations = [
        item for item in result.rule_evaluations if item.rule_id in {"GEN-001", "CC-006"}
    ]
    assert projected_evaluations
    assert all(item.outcome.value == "abstained" for item in projected_evaluations)
    assert all(not item.scope_label for item in projected_evaluations)
    assert all(not item.matched for item in projected_evaluations)
    assert all(not item.output_ids for item in projected_evaluations)
    assert not any(item.kind is CountKind.INDEPENDENT_N for item in result.block.count_records)


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("measuredOn", "Animal", "unsupported_measurement_level"),
        ("measuredOn", "Image", "unsupported_measurement_level"),
        ("measuredOn", "Field", "unsupported_measurement_level"),
        ("targetBiologicalUnit", "Animal", "unsupported_target_unit"),
        ("targetBiologicalUnit", "Image", "unsupported_target_unit"),
    ],
)
def test_non_cell_culture_measurement_or_target_topology_is_out_of_scope(
    field: str, value: str, reason: str
) -> None:
    payload = _payload()
    draft = dict(payload["draft"])  # type: ignore[arg-type]
    draft[field] = value
    payload["draft"] = draft

    result = compile_prospective_d0(_request(payload))

    assert result.determinability is Determinability.OUT_OF_SCOPE
    assert result.ready_for_handoff is False
    assert result.design_compilation.status.value == "abstained"
    assert result.design_compilation.abstained is True
    assert result.design_compilation.elicitation.complete is False
    assert reason in {item.value for item in result.capability.reason_codes}
    assert not any(item.kind is CountKind.INDEPENDENT_N for item in result.block.count_records)


def test_unknown_measurement_level_is_incomplete_and_never_defaults_to_well() -> None:
    payload = _payload()
    draft = dict(payload["draft"])  # type: ignore[arg-type]
    draft.pop("measuredOn")
    payload["draft"] = draft

    result = compile_prospective_d0(_request(payload))

    assert result.determinability is Determinability.INSUFFICIENT_INFORMATION
    assert result.capability.status.value == "incomplete"
    assert "missing_measurement_level" in {item.value for item in result.capability.reason_codes}
    assert all(item.observational_unit is None for item in result.block.unit_assessments)


def test_missing_factor_kind_is_incomplete_and_never_invented_as_treatment() -> None:
    payload = _payload()
    draft = dict(payload["draft"])  # type: ignore[arg-type]
    draft.pop("factorKind")
    payload["draft"] = draft

    result = compile_prospective_d0(_request(payload))

    assert result.determinability is Determinability.INSUFFICIENT_INFORMATION
    assert result.capability.status.value == "incomplete"
    assert "missing_factor_kind" in {item.value for item in result.capability.reason_codes}
    assert result.block.factors[0].kind == "unknown"
    factor_evidence = next(item for item in result.block.evidence if item.section_id == "factor")
    assert "factor_kind=unknown" in factor_evidence.text


def test_unknown_independence_materializes_two_explicit_fail_closed_branches() -> None:
    payload = _payload()
    draft = dict(payload["draft"])  # type: ignore[arg-type]
    draft["independentlyAssigned"] = "UNKNOWN"
    draft.pop("independenceMechanism")
    payload["draft"] = draft

    result = compile_prospective_d0(_request(payload))

    assert result.determinability is Determinability.CONDITIONALLY_DETERMINATE
    assert result.ready_for_handoff is False
    assert not any(item.kind is CountKind.INDEPENDENT_N for item in result.block.count_records)
    assert any(question.decisive for question in result.block.questions)
    for assessment in result.block.unit_assessments:
        assert assessment.inferability is Inferability.CONDITIONAL
        assert assessment.allocation_unit_candidate is NodeType.WELL
        assert assessment.experimental_unit is None
        assert assessment.n_independent is None
        assert len(assessment.conditional_scenarios) == 1
        scenario = assessment.conditional_scenarios[0]
        assert scenario.if_confirmed == {"n_independent": 2}
        assert scenario.if_rejected == {"n_independent": None}


def test_child_lifecycle_counts_are_not_projected_to_plate_allocation() -> None:
    payload = _payload()
    draft = dict(payload["draft"])  # type: ignore[arg-type]
    draft["allocationLevel"] = "Plate"
    draft["applicationLevel"] = "Plate"
    draft["targetBiologicalUnit"] = "Plate"
    draft["independenceMechanism"] = "Each plate is independently allocated."
    payload["draft"] = draft
    rows = list(payload["rows"])  # type: ignore[arg-type]
    rows[0] = {**rows[0], "lifecycleStatus": "analysed"}
    rows[1] = {
        **rows[1],
        "lifecycleStatus": "excluded",
        "exclusionReason": "QC threshold exceeded",
        "exclusionPhase": "post_measurement",
        "exclusionPrespecified": "TRUE",
        "exclusionAuthorRole": "wet_lab_reviewer",
        "exclusionImpact": "removed from analysed count",
    }
    rows[2] = {**rows[2], "plateId": "P02", "wellId": "A01"}
    rows[3] = {**rows[3], "plateId": "P02", "wellId": "A02"}
    payload["rows"] = rows

    result = compile_prospective_d0(_request(payload))
    vehicle_counts = {
        item.kind: item
        for item in result.block.count_records
        if item.scope.group_or_level == "vehicle"
    }

    assert vehicle_counts[CountKind.PLANNED_N].value == 1
    assert vehicle_counts[CountKind.PLANNED_N].scope.unit_type is NodeType.PLATE
    assert vehicle_counts[CountKind.ANALYSED_N].value == 1
    assert vehicle_counts[CountKind.ANALYSED_N].scope.unit_type is NodeType.WELL
    assert vehicle_counts[CountKind.EXCLUDED_N].value == 1
    assert vehicle_counts[CountKind.EXCLUDED_N].scope.unit_type is NodeType.WELL
    exclusion = result.block.exclusion_records[0]
    node = next(item for item in result.block.hierarchy.nodes if item.id == exclusion.unit_id)
    assert node.type is exclusion.unit_type is NodeType.WELL
    row_evidence = next(item for item in result.block.evidence if item.id in exclusion.evidence_ids)
    for expected in (
        "ntruth_exclusion_phase",
        "ntruth_exclusion_prespecified",
        "ntruth_exclusion_author_role",
        "ntruth_exclusion_impact",
    ):
        assert expected in row_evidence.text


def test_estimand_mutation_changes_value_and_exact_user_evidence() -> None:
    first = compile_prospective_d0(_request())
    payload = _payload()
    draft = dict(payload["draft"])  # type: ignore[arg-type]
    estimand = dict(draft["estimand"])  # type: ignore[arg-type]
    estimand["effectMeasure"] = "ratio of mean viability"
    draft["estimand"] = estimand
    payload["draft"] = draft
    second = compile_prospective_d0(_request(payload))

    first_evidence = next(item for item in first.block.evidence if item.section_id == "estimand")
    second_evidence = next(item for item in second.block.evidence if item.section_id == "estimand")
    assert first.block.estimands[0].effect_measure == "difference in mean viability"
    assert second.block.estimands[0].effect_measure == "ratio of mean viability"
    assert first_evidence.id != second_evidence.id
    assert first_evidence.text != second_evidence.text
    assert second.block.estimands[0].evidence_ids == (second_evidence.id,)


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ({"wellId": "A01", "factorLevel": "vehicle"}, "duplicate_physical_well_row"),
        (
            {
                "sourceId": "SRC-OTHER",
                "cultureId": "CULT-OTHER",
                "plateId": "P02",
            },
            "preparation_origin_not_functional",
        ),
        ({"cultureId": "CULT-001", "preparationId": "PREP-OTHER"}, "culture_origin_not_functional"),
        ({"plateId": "P01", "cultureId": "CULT-OTHER"}, "plate_origin_not_functional"),
    ],
)
def test_physical_and_functional_dependency_conflicts_fail_closed(
    mutation: dict[str, str], expected_code: str
) -> None:
    payload = _payload()
    rows = list(payload["rows"])  # type: ignore[arg-type]
    rows[1] = {**rows[1], **mutation}
    payload["rows"] = rows

    with pytest.raises(ProspectiveD0ValidationError) as caught:
        compile_prospective_d0(_request(payload))

    assert expected_code in {item.code for item in caught.value.issues}


@pytest.mark.parametrize(
    ("field", "warning_code"),
    [
        ("sourceId", "source_id_not_reported"),
        ("preparationId", "preparation_id_not_reported"),
        ("cultureId", "culture_id_not_reported"),
    ],
)
def test_missing_lineage_cell_is_unknown_not_a_competing_origin(
    field: str, warning_code: str
) -> None:
    payload = _payload()
    rows = list(payload["rows"])  # type: ignore[arg-type]
    rows[1] = {**rows[1], field: None}
    payload["rows"] = rows

    result = compile_prospective_d0(_request(payload))

    assert result.ready_for_handoff is True
    assert warning_code in {item.code for item in result.issues}
    canonical_row = result.sample_sheet.rows[1]
    canonical_field = {
        "sourceId": "source_id",
        "preparationId": "preparation_id",
        "cultureId": "culture_id",
    }[field]
    assert getattr(canonical_row, canonical_field) is None
    evidence = next(
        item for item in result.block.evidence if item.section_id == "SampleSheetSpec.rows[1]"
    )
    assert f"'{canonical_field}': None" in evidence.text
    if field == "sourceId":
        source_count = next(
            item
            for item in result.block.count_records
            if item.kind is CountKind.BIOLOGICAL_SOURCE_COUNT
            and item.scope.group_or_level == "vehicle"
        )
        assert source_count.value == 1
        assert source_count.quantifier is CountQuantifier.LOWER_BOUND


def test_declared_application_measurement_and_target_units_must_be_materializable() -> None:
    payload = _payload()
    draft = dict(payload["draft"])  # type: ignore[arg-type]
    draft["allocationLevel"] = "Plate"
    draft["applicationLevel"] = "Well"
    draft["measuredOn"] = "Well"
    draft["targetBiologicalUnit"] = "Well"
    draft["independenceMechanism"] = "Each plate is independently allocated."
    payload["draft"] = draft
    rows = list(payload["rows"])  # type: ignore[arg-type]
    payload["rows"] = [
        {**rows[0], "plateId": "PL1", "wellId": None},
        {**rows[2], "plateId": "PL2", "wellId": None},
    ]

    with pytest.raises(ProspectiveD0ValidationError) as caught:
        compile_prospective_d0(_request(payload))

    codes = {item.code for item in caught.value.issues}
    assert codes >= {
        "missing_application_unit_identifier",
        "missing_measurement_unit_identifier",
        "missing_target_unit_identifier",
    }


def test_allocation_cannot_be_finer_than_actual_application_unit() -> None:
    payload = _payload()
    draft = dict(payload["draft"])  # type: ignore[arg-type]
    draft["applicationLevel"] = "Plate"
    payload["draft"] = draft

    with pytest.raises(ProspectiveD0ValidationError) as caught:
        compile_prospective_d0(_request(payload))

    codes = {item.code for item in caught.value.issues}
    assert codes >= {
        "allocation_level_finer_than_application_level",
        "application_unit_assigned_to_multiple_levels",
    }


@pytest.mark.parametrize("missing_indexes", [(0, 1, 2, 3), (0, 2)])
def test_estimand_timepoint_is_never_implicitly_propagated_to_missing_rows(
    missing_indexes: tuple[int, ...],
) -> None:
    payload = _payload()
    rows = list(payload["rows"])  # type: ignore[arg-type]
    for index in missing_indexes:
        rows[index] = {**rows[index], "timepoint": None}
    payload["rows"] = rows

    with pytest.raises(ProspectiveD0ValidationError) as caught:
        compile_prospective_d0(_request(payload))

    codes = {item.code for item in caught.value.issues}
    if len(missing_indexes) == len(rows):
        assert "missing_row_timepoint_for_estimand" in codes
    else:
        assert "mixed_reported_and_missing_timepoint" in codes


def test_perfect_cluster_confounding_is_materialized_and_blocks_handoff() -> None:
    payload = _payload()
    rows = list(payload["rows"])  # type: ignore[arg-type]
    for index in (0, 1):
        rows[index] = {**rows[index], "batchId": "B1"}
    for index in (2, 3):
        rows[index] = {
            **rows[index],
            "sourceId": "SRC-002",
            "preparationId": "PREP-002",
            "cultureId": "CULT-002",
            "plateId": "P02",
            "batchId": "B2",
        }
    payload["rows"] = rows

    result = compile_prospective_d0(_request(payload))

    assert result.determinability is Determinability.CONFLICTING_INFORMATION
    assert result.ready_for_handoff is False
    assert result.design_compilation.abstained is True
    assert result.block.contradictions
    assert result.block.factors[0].confounded_with == (
        "source_id",
        "preparation_id",
        "culture_id",
        "plate_id",
        "batch_id",
    )
    assert {item.kind for item in result.block.processes} == {"confounding"}
    assert {item.type for item in result.block.hierarchy.nodes} >= {NodeType.BATCH}
    assert any(item.rule_id == "GEN-005" for item in result.block.alerts)
    assert any(item.rule_id == "CC-004" for item in result.block.alerts)
    assert output_policy_violations(result.block) == ()
    assert not any(item.rule_id == "GEN-001" for item in result.block.alerts)
    gen001_evaluation = next(item for item in result.rule_evaluations if item.rule_id == "GEN-001")
    assert gen001_evaluation.outcome.value == "abstained"
    assert gen001_evaluation.triggered_abstention == (
        "output_withheld_by_determinability:CONFLICTING_INFORMATION"
    )
    assert not gen001_evaluation.scope_label
    assert not gen001_evaluation.matched
    assert not gen001_evaluation.output_ids
    assert any(question.decisive for question in result.block.questions)
    assert not any(item.kind is CountKind.INDEPENDENT_N for item in result.block.count_records)
    assert all(item.experimental_unit is None for item in result.block.unit_assessments)
    assert all(item.n_independent is None for item in result.block.unit_assessments)


def test_disjoint_multiple_plates_per_level_still_withhold_well_independent_n() -> None:
    payload = _payload()
    base_rows = list(payload["rows"])  # type: ignore[arg-type]
    rows: list[dict[str, object]] = []
    for group_index, plate_ids in ((0, ("P01", "P02")), (2, ("P03", "P04"))):
        for plate_id in plate_ids:
            for well_id in ("A01", "A02"):
                rows.append(
                    {
                        **base_rows[group_index],
                        "sampleId": f"{plate_id}-{well_id}",
                        "plateId": plate_id,
                        "wellId": well_id,
                    }
                )
    payload["rows"] = rows

    result = compile_prospective_d0(_request(payload))

    assert result.determinability is Determinability.CONFLICTING_INFORMATION
    assert result.ready_for_handoff is False
    assert "plate_id" in result.block.factors[0].confounded_with
    assert any(item.rule_id == "GEN-005" for item in result.block.alerts)
    assert not any(item.kind is CountKind.INDEPENDENT_N for item in result.block.count_records)
    assert all(item.experimental_unit is None for item in result.block.unit_assessments)
    assert all(item.n_independent is None for item in result.block.unit_assessments)


def test_one_to_one_plate_row_key_is_not_misclassified_as_cluster_confounding() -> None:
    payload = _payload()
    rows = list(payload["rows"])  # type: ignore[arg-type]
    for index, plate_id in enumerate(("P01", "P02", "P03", "P04")):
        rows[index] = {**rows[index], "plateId": plate_id, "wellId": "A01"}
    payload["rows"] = rows

    result = compile_prospective_d0(_request(payload))

    assert result.determinability is Determinability.DETERMINATE
    assert result.ready_for_handoff is True
    assert result.block.factors[0].confounded_with == ()
    assert not any(item.rule_id == "GEN-005" for item in result.block.alerts)


@pytest.mark.parametrize("dimension", ["day_id", "operator_id", "incubator_id"])
def test_whitelisted_row_context_cluster_is_checked_for_confounding(dimension: str) -> None:
    payload = _payload()
    rows = list(payload["rows"])  # type: ignore[arg-type]
    for index in (0, 1):
        rows[index] = {**rows[index], "extraFields": {dimension: "CTX-1"}}
    for index in (2, 3):
        rows[index] = {**rows[index], "extraFields": {dimension: "CTX-2"}}
    payload["rows"] = rows

    result = compile_prospective_d0(_request(payload))

    assert result.determinability is Determinability.CONFLICTING_INFORMATION
    assert result.ready_for_handoff is False
    assert dimension in result.block.factors[0].confounded_with
    assert any(item.rule_id == "GEN-005" for item in result.block.alerts)
    assert not any(item.kind is CountKind.INDEPENDENT_N for item in result.block.count_records)


@pytest.mark.parametrize("independence", ["UNKNOWN", "FALSE"])
def test_confounding_without_true_independence_is_risk_not_false_contradiction(
    independence: str,
) -> None:
    payload = _payload()
    draft = dict(payload["draft"])  # type: ignore[arg-type]
    draft["independentlyAssigned"] = independence
    draft.pop("independenceMechanism")
    payload["draft"] = draft
    rows = list(payload["rows"])  # type: ignore[arg-type]
    for index in (0, 1):
        rows[index] = {**rows[index], "batchId": "B1"}
    for index in (2, 3):
        rows[index] = {
            **rows[index],
            "sourceId": "SRC-002",
            "preparationId": "PREP-002",
            "cultureId": "CULT-002",
            "plateId": "P02",
            "batchId": "B2",
        }
    payload["rows"] = rows

    result = compile_prospective_d0(_request(payload))

    assert result.determinability is Determinability.INSUFFICIENT_INFORMATION
    assert result.ready_for_handoff is False
    assert result.block.contradictions == ()
    assert result.block.processes
    assert result.block.factors[0].confounded_with
    assert any(item.rule_id == "GEN-005" for item in result.block.alerts)
    assert not any(item.kind is CountKind.INDEPENDENT_N for item in result.block.count_records)
    assert all(not item.conditional_scenarios for item in result.block.unit_assessments)


def test_cell_roles_require_and_materialize_non_enumerating_population_plan() -> None:
    payload = _payload()
    draft = dict(payload["draft"])  # type: ignore[arg-type]
    draft["applicationLevel"] = "Cell"
    draft["measuredOn"] = "Cell"
    draft["targetBiologicalUnit"] = "Cell"
    payload["draft"] = draft

    with pytest.raises(ValueError, match="cell_population_plan"):
        _request(payload)

    draft["cellPopulationPlan"] = (
        "Cells will receive stable segmentation object IDs within each declared well."
    )
    payload["draft"] = draft
    result = compile_prospective_d0(_request(payload))

    assert result.determinability is Determinability.DETERMINATE
    assert result.ready_for_handoff is True
    assert result.capability.status.value == "supported"
    assert any(item.type is NodeType.CELL for item in result.block.hierarchy.nodes)
    assert all(
        "planned-cell-population" in item.label
        for item in result.block.hierarchy.nodes
        if item.type is NodeType.CELL
    )
    assert {item.observational_unit for item in result.block.unit_assessments} == {NodeType.CELL}
    assert all(item.analytical_unit is None for item in result.block.unit_assessments)
    assert {item.experimental_unit for item in result.block.unit_assessments} == {NodeType.WELL}


def test_prospective_registry_is_bounded_and_does_not_persist_evicted_session() -> None:
    result = compile_prospective_d0(_request())
    registry = ProspectiveSessionRegistry(max_sessions=1)
    input_checksum = content_checksum(_request().model_dump(mode="json"))
    first = registry.create(
        result, actor_role="prospective_researcher", input_checksum=input_checksum
    )
    second = registry.create(
        result, actor_role="prospective_researcher", input_checksum=input_checksum
    )

    with pytest.raises(ProspectiveSessionNotFound):
        registry.get(first.id)
    assert registry.get(second.id).compilation.compilation_id == result.compilation_id
    assert second.audit_trail[0].input_checksum == input_checksum
    assert second.audit_trail[0].recorded_at.utcoffset() is not None
    assert second.audit_trail[0].output_checksum == content_checksum(result.model_dump(mode="json"))
