"""SampleSheetSpec v9 (PRD v9, Appendice O): righe, stati e round-trip JSON."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from ntruth.sample_sheet.v9_schema import (
    SAMPLE_SHEET_V9_SCHEMA_VERSION,
    PlannedOrExecutedContext,
    RowLifecycleStatus,
    SampleSheetFactorColumnsV9,
    SampleSheetRowV9,
    SampleSheetSpecV9,
    TimepointValue,
    TypedValue,
    UnitType,
    not_applicable,
    not_reported,
    present,
    sample_sheet_v9_json_schema,
    unknown,
    validate_lifecycle_progression,
)
from ntruth.schemas.knowledge import KnowledgeState


def _row(**overrides: object) -> SampleSheetRowV9:
    base: dict[str, object] = {
        "row_id": "ROW-001",
        "experiment_block_id": "BLOCK-A",
        "unit_instance_id": "UNIT-001",
        "unit_type": UnitType.WELL,
        "source_instance_id": present("SRC-01"),
        "preparation_id": unknown("source preparation split non documentato"),
        "lifecycle_status": RowLifecycleStatus.PLANNED,
        "planned_or_executed_context": PlannedOrExecutedContext.PLANNED,
    }
    base.update(overrides)
    return SampleSheetRowV9.model_validate(base)


def _assigned_factor_group() -> dict[str, object]:
    return {
        "factor_id": present("FAC-treatment"),
        "factor_role": present("ASSIGNED_INTERVENTION"),
        "factor_level": present("L1"),
        "assignment_event_id": present("EVT-ASSIGN-01"),
    }


def test_valid_row_round_trips_through_json() -> None:
    row = _row(
        factors={"treatment": SampleSheetFactorColumnsV9.model_validate(_assigned_factor_group())},
        timepoint_id=TimepointValue(knowledge_state=KnowledgeState.PRESENT, value=24.0, unit="h"),
        well_id=present("PL01_W03"),
    )
    payload = json.loads(row.model_dump_json())
    restored = SampleSheetRowV9.model_validate(payload)

    assert restored == row
    assert restored.factors["treatment"].assignment_event_id is not None
    assert restored.timepoint_id is not None and restored.timepoint_id.unit == "h"


def test_spec_validates_and_exposes_json_schema() -> None:
    spec = SampleSheetSpecV9(
        experiment_block_id="BLOCK-A",
        rows=(_row(),),
        content_sha256="a" * 64,
    )

    assert spec.schema_version == SAMPLE_SHEET_V9_SCHEMA_VERSION
    schema = sample_sheet_v9_json_schema()
    assert schema["title"] == "SampleSheetSpecV9"
    properties = schema["properties"]
    assert isinstance(properties, dict)
    assert set(properties) >= {"rows", "experiment_block_id", "schema_version"}


def test_blank_cell_without_state_is_invalid() -> None:
    with pytest.raises(ValidationError):
        TypedValue(knowledge_state=KnowledgeState.PRESENT, value=None)
    with pytest.raises(ValidationError):
        TypedValue(knowledge_state=KnowledgeState.PRESENT, value="   ")
    with pytest.raises(ValidationError):
        TypedValue(knowledge_state=KnowledgeState.UNKNOWN, value="SRC-01")


def test_present_value_requires_state_and_unknown_forbids_value() -> None:
    assert present("SRC-01").knowledge_state is KnowledgeState.PRESENT
    declared = not_reported()
    assert declared.value is None
    with pytest.raises(ValidationError):
        TypedValue.model_validate({"knowledge_state": "NOT_REPORTED", "value": "SRC-01"})


def test_source_and_preparation_are_required_or_unknown() -> None:
    with pytest.raises(ValidationError, match="required-or-unknown"):
        _row(source_instance_id=not_applicable("non pertinente"))
    with pytest.raises(ValidationError, match="rationale"):
        _row(preparation_id=TypedValue(knowledge_state=KnowledgeState.UNKNOWN))


def test_conflicting_state_is_not_representable_in_typed_value() -> None:
    with pytest.raises(ValidationError, match="CONFLICTING"):
        TypedValue(knowledge_state=KnowledgeState.CONFLICTING)


def test_excluded_row_requires_reason_and_reason_forbidden_elsewhere() -> None:
    excluded = _row(
        lifecycle_status=RowLifecycleStatus.EXCLUDED,
        exclusion_reason=present("hemolysis after treatment (actor: lab, day 2)"),
    )
    assert excluded.lifecycle_status is RowLifecycleStatus.EXCLUDED

    with pytest.raises(ValidationError, match="exclusion_reason"):
        _row(lifecycle_status=RowLifecycleStatus.EXCLUDED)
    with pytest.raises(ValidationError, match="EXCLUDED"):
        _row(exclusion_reason=present("no reason yet"))


def test_assignment_event_only_for_assigned_factor() -> None:
    assigned = SampleSheetFactorColumnsV9.model_validate(_assigned_factor_group())
    assert assigned.assignment_event_id is not None

    intrinsic_without_assignment = {
        "factor_id": present("FAC-genotype"),
        "factor_role": present("INTRINSIC_ATTRIBUTE"),
        "factor_level": present("wt"),
    }
    assert SampleSheetFactorColumnsV9.model_validate(intrinsic_without_assignment)

    with pytest.raises(ValidationError, match="ASSIGNED_INTERVENTION"):
        SampleSheetFactorColumnsV9.model_validate(
            {**intrinsic_without_assignment, "assignment_event_id": present("EVT-1")}
        )
    with pytest.raises(ValidationError, match="assignment_event_id"):
        SampleSheetFactorColumnsV9.model_validate(
            {
                "factor_id": present("FAC-dose"),
                "factor_role": present("ASSIGNED_INTERVENTION"),
                "factor_level": present("10uM"),
            }
        )
    with pytest.raises(ValidationError, match="factor_role non canonico"):
        SampleSheetFactorColumnsV9.model_validate(
            {
                "factor_id": present("FAC-x"),
                "factor_role": present("SOMETHING_ELSE"),
                "factor_level": present("L0"),
            }
        )


def test_duplicate_row_ids_and_foreign_blocks_rejected() -> None:
    with pytest.raises(ValidationError, match="univoco"):
        SampleSheetSpecV9(
            experiment_block_id="BLOCK-A",
            rows=(_row(), _row()),
        )
    with pytest.raises(ValidationError, match="experiment block"):
        SampleSheetSpecV9(
            experiment_block_id="BLOCK-A",
            rows=(
                _row(),
                _row(row_id="ROW-002", experiment_block_id="BLOCK-B"),
            ),
        )
    with pytest.raises(ValidationError):
        SampleSheetSpecV9(
            experiment_block_id="BLOCK-A",
            rows=(_row(content_sha256="zzz"),),
        )


def test_lifecycle_monotony_per_unit_is_enforced() -> None:
    def progression(*statuses: RowLifecycleStatus) -> tuple[SampleSheetRowV9, ...]:
        return tuple(
            _row(
                row_id=f"ROW-{index:03d}",
                unit_instance_id="UNIT-001",
                lifecycle_status=status,
                exclusion_reason=(
                    present("post-outcome exclusion")
                    if status is RowLifecycleStatus.EXCLUDED
                    else None
                ),
            )
            for index, status in enumerate(statuses, start=1)
        )

    ok = SampleSheetSpecV9(
        experiment_block_id="BLOCK-A",
        rows=progression(
            RowLifecycleStatus.PLANNED,
            RowLifecycleStatus.ALLOCATED,
            RowLifecycleStatus.TREATED,
            RowLifecycleStatus.OBSERVED,
        ),
    )
    assert len(ok.rows) == 4

    excluded_then_nothing = SampleSheetSpecV9(
        experiment_block_id="BLOCK-A",
        rows=progression(
            RowLifecycleStatus.TREATED,
            RowLifecycleStatus.OBSERVED,
            RowLifecycleStatus.EXCLUDED,
        ),
    )
    assert excluded_then_nothing.rows[-1].lifecycle_status is (RowLifecycleStatus.EXCLUDED)

    with pytest.raises(ValidationError, match="monotonico"):
        SampleSheetSpecV9(
            experiment_block_id="BLOCK-A",
            rows=progression(
                RowLifecycleStatus.OBSERVED,
                RowLifecycleStatus.ALLOCATED,
            ),
        )
    with pytest.raises(ValidationError, match="EXCLUDED"):
        SampleSheetSpecV9(
            experiment_block_id="BLOCK-A",
            rows=progression(
                RowLifecycleStatus.TREATED,
                RowLifecycleStatus.EXCLUDED,
                RowLifecycleStatus.ANALYZED,
            ),
        )
    with pytest.raises(ValidationError, match="OBSERVED precedente"):
        SampleSheetSpecV9(
            experiment_block_id="BLOCK-A",
            rows=progression(
                RowLifecycleStatus.TREATED,
                RowLifecycleStatus.ANALYZED,
            ),
        )
    analyzed_after_observed = SampleSheetSpecV9(
        experiment_block_id="BLOCK-A",
        rows=progression(
            RowLifecycleStatus.OBSERVED,
            RowLifecycleStatus.ANALYZED,
        ),
    )
    assert analyzed_after_observed.rows[-1].lifecycle_status is (RowLifecycleStatus.ANALYZED)


def test_single_row_per_unit_has_no_history_constraints() -> None:
    analyzed = SampleSheetSpecV9(
        experiment_block_id="BLOCK-A",
        rows=(_row(lifecycle_status=RowLifecycleStatus.ANALYZED),),
    )
    assert analyzed.rows[0].lifecycle_status is RowLifecycleStatus.ANALYZED


def test_lifecycle_progression_helper_transitions() -> None:
    validate_lifecycle_progression(RowLifecycleStatus.PLANNED, RowLifecycleStatus.ALLOCATED)
    validate_lifecycle_progression(RowLifecycleStatus.TREATED, RowLifecycleStatus.OBSERVED)
    with pytest.raises(ValueError, match="monotonico"):
        validate_lifecycle_progression(RowLifecycleStatus.ANALYZED, RowLifecycleStatus.TREATED)


def test_timepoint_requires_explicit_unit_when_present() -> None:
    with pytest.raises(ValidationError, match="unita temporale"):
        TimepointValue(knowledge_state=KnowledgeState.PRESENT, value=24.0)
    declared = TimepointValue(knowledge_state=KnowledgeState.NOT_REPORTED)
    assert declared.value is None and declared.unit is None
