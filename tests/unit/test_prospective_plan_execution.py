"""Il gold prospettico conserva il confronto esplicito piano-esecuzione."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ntruth.prospective import (
    ProspectiveD0Draft,
    ProspectiveDeviation,
    ProspectiveDeviationCategory,
    ProspectiveExecutionExclusion,
    ProspectiveGoldRecord,
    ProspectiveLostSample,
    ProspectivePlanExecutionRecord,
    ProspectivePoolingEvent,
    ProspectiveSubstitution,
    ProspectiveTreatmentChange,
)
from ntruth.sample_sheet import SampleLifecycleStatus, SampleSheetRow, SampleSheetSpec
from ntruth.schemas.experiment import ExclusionPhase, TriState


def _design(*, title: str = "Planned design") -> ProspectiveD0Draft:
    return ProspectiveD0Draft(
        experiment_block_id="EB-PROSPECTIVE-1",
        title=title,
        question_text="Does treatment alter the endpoint?",
        population_of_inference="declared experimental units",
        factor_name="treatment",
        factor_kind="treatment",
        level_a="vehicle",
        level_b="drug",
        endpoint_name="viability",
        endpoint_id="endpoint-1",
        measured_on="Well",
        allocation_level="Well",
        application_level="Well",
        independently_assigned=TriState.TRUE,
        independence_mechanism=(
            "Each well is assigned independently from the recorded randomisation list."
        ),
        target_biological_unit="Well",
        reviewer_role="researcher",
    )


def _row(
    sample_id: str,
    level: str,
    *,
    lifecycle: SampleLifecycleStatus = SampleLifecycleStatus.PLANNED,
    exclusion_reason: str | None = None,
) -> SampleSheetRow:
    return SampleSheetRow(
        sample_id=sample_id,
        source_id="source-1",
        preparation_id="preparation-1",
        well_id=sample_id,
        factor_levels={"factor_level_treatment": level},
        lifecycle_status=lifecycle,
        exclusion_reason=exclusion_reason,
    )


def _sheet(*rows: SampleSheetRow) -> SampleSheetSpec:
    return SampleSheetSpec(
        headers=(
            "sample_id",
            "source_id",
            "preparation_id",
            "well_id",
            "factor_level_treatment",
            "lifecycle_status",
            "exclusion_reason",
        ),
        factor_columns=("factor_level_treatment",),
        rows=rows,
    )


def _record() -> ProspectivePlanExecutionRecord:
    planned = _sheet(
        _row("P1", "vehicle"),
        _row("P2", "vehicle"),
        _row("P3", "vehicle"),
        _row("P4", "drug"),
        _row("P5", "drug"),
        _row("P6", "drug"),
    )
    final = _sheet(
        _row("P1", "drug", lifecycle=SampleLifecycleStatus.TREATED),
        _row(
            "P2",
            "vehicle",
            lifecycle=SampleLifecycleStatus.EXCLUDED,
            exclusion_reason="prespecified contamination criterion",
        ),
        _row("S4", "drug", lifecycle=SampleLifecycleStatus.TREATED),
        _row("POOL1", "drug", lifecycle=SampleLifecycleStatus.OBSERVED),
    )
    return ProspectivePlanExecutionRecord(
        record_id="plan-execution-1",
        planned_design=_design(),
        planned_sample_sheet=planned,
        executed_design=_design(),
        deviations=(
            ProspectiveDeviation(
                deviation_id="dev-1",
                category=ProspectiveDeviationCategory.PROCEDURE_CHANGE,
                description="Documented execution events changed the planned inventory.",
                affected_sample_ids=("P1", "P2", "P3", "P4", "P5", "P6", "S4", "POOL1"),
            ),
        ),
        substitutions=(
            ProspectiveSubstitution(
                substitution_id="sub-1",
                planned_sample_id="P4",
                substitute_sample_id="S4",
                reason="P4 failed pre-treatment quality control.",
            ),
        ),
        exclusions=(
            ProspectiveExecutionExclusion(
                exclusion_id="exc-1",
                sample_id="P2",
                reason="prespecified contamination criterion",
                phase=ExclusionPhase.POST_TREATMENT,
                prespecified=TriState.TRUE,
                author_role="wet_lab_reviewer",
            ),
        ),
        pooling=(
            ProspectivePoolingEvent(
                pooling_id="pool-1",
                input_sample_ids=("P5", "P6"),
                output_sample_id="POOL1",
                reason="Protocol-required pooled assay.",
            ),
        ),
        lost_samples=(
            ProspectiveLostSample(
                lost_sample_id="lost-1",
                sample_id="P3",
                phase="before measurement",
                reason="Sample container was lost during transfer.",
            ),
        ),
        treatment_changes=(
            ProspectiveTreatmentChange(
                treatment_change_id="treatment-1",
                sample_id="P1",
                factor_column="factor_level_treatment",
                planned_level="vehicle",
                executed_level="drug",
                reason="Recorded dispensing correction before treatment application.",
            ),
        ),
        final_sample_sheet=final,
        recorded_by_role="prospective_researcher",
    )


def test_plan_execution_keeps_all_execution_event_classes_separate() -> None:
    record = _record()

    assert record.planned_sample_sheet.rows[0].factor_levels == {
        "factor_level_treatment": "vehicle"
    }
    assert record.final_sample_sheet.rows[0].factor_levels == {"factor_level_treatment": "drug"}
    assert len(record.substitutions) == 1
    assert len(record.exclusions) == 1
    assert len(record.pooling) == 1
    assert len(record.lost_samples) == 1
    assert len(record.treatment_changes) == 1
    assert ProspectivePlanExecutionRecord.model_validate_json(record.model_dump_json()) == record


def test_unexplained_added_or_removed_samples_fail_closed() -> None:
    record = _record()
    extra = _row("UNPLANNED", "drug", lifecycle=SampleLifecycleStatus.TREATED)
    invalid_final = record.final_sample_sheet.model_copy(
        update={"rows": (*record.final_sample_sheet.rows, extra)}
    )

    with pytest.raises(ValueError, match="non pianificati"):
        ProspectivePlanExecutionRecord.model_validate(
            {**record.model_dump(), "final_sample_sheet": invalid_final}
        )


def test_undeclared_treatment_change_fails_closed() -> None:
    record = _record()

    with pytest.raises(ValueError, match="treatment_changes non coincide"):
        ProspectivePlanExecutionRecord.model_validate(
            {**record.model_dump(), "treatment_changes": ()}
        )


def test_final_exclusion_requires_a_matching_typed_event() -> None:
    record = _record()

    with pytest.raises(ValueError, match="exclusions non coincide"):
        ProspectivePlanExecutionRecord.model_validate({**record.model_dump(), "exclusions": ()})


def test_executed_design_change_requires_a_deviation_record() -> None:
    record = _record()

    with pytest.raises(ValueError, match="richiede almeno una deviation"):
        ProspectivePlanExecutionRecord.model_validate(
            {
                **record.model_dump(),
                "executed_design": _design(title="Executed design changed"),
                "deviations": (),
            }
        )


def test_prospective_gold_requires_distinct_double_annotation_and_adjudication() -> None:
    gold = ProspectiveGoldRecord(
        gold_id="prospective-gold-1",
        plan_execution=_record(),
        source_annotation_ids=("annotation-a", "annotation-b"),
        reviewer_roles=("wet_lab_reviewer", "biostatistician"),
        adjudicator_role="independent_adjudicator",
        adjudicated_at=datetime(2026, 8, 1, tzinfo=UTC),
    )

    assert gold.status == "adjudicated_gold"
    with pytest.raises(ValueError, match="annotazioni distinte"):
        ProspectiveGoldRecord.model_validate(
            {**gold.model_dump(), "source_annotation_ids": ("same", "same")}
        )
    with pytest.raises(ValueError, match="due ruoli distinti"):
        ProspectiveGoldRecord.model_validate(
            {**gold.model_dump(), "reviewer_roles": ("reviewer", "reviewer")}
        )
