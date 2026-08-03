"""Quick Design Session vertical slice for simple_cell_culture."""

from __future__ import annotations

import json

import pytest

from ntruth.quick_design import (
    QuickDesignAnswers,
    export_for_biostatistician,
    freeze_plan,
    run_quick_design_session,
)
from ntruth.schemas.determinability_v7 import DeterminabilityStateV7


def test_quick_design_unknowns_are_insufficient() -> None:
    result = run_quick_design_session(
        QuickDesignAnswers(source_description="primary human fibroblasts")
    )
    assert result.determinability is DeterminabilityStateV7.INSUFFICIENT_INFORMATION
    assert result.primary_question
    assert "sample_id" in result.sample_sheet_csv
    assert "NOT REPORTED" in result.methods_draft


def test_bio_independence_is_not_assignment_proxy() -> None:
    result = run_quick_design_session(
        QuickDesignAnswers(
            source_description="line X",
            biological_source_independence="TRUE",
            independently_assigned="UNKNOWN",
            allocation_level="well",
            interference_status="POSSIBLE",
            planned_units_per_level=2,
            planned_unit_type="well",
        )
    )
    assert result.determinability is not DeterminabilityStateV7.DETERMINATE
    assert result.bootstrap.independently_assigned == "UNKNOWN"
    assert result.bootstrap.independence.independently_assigned.value == "UNKNOWN"
    assert result.bootstrap.independence.biological_source_independence.value == "TRUE"


def test_invalid_allocation_cannot_be_known() -> None:
    result = run_quick_design_session(
        QuickDesignAnswers(
            source_description="cells",
            allocation_level="not-a-real-level",
            independently_assigned="TRUE",
            biological_source_independence="TRUE",
            interference_status="POSSIBLE",
            assignment_method="random",
            assignment_confirmation_event_id="conf-alloc",
        )
    )
    assert result.bootstrap.allocation_level == "unknown"
    assert result.determinability is not DeterminabilityStateV7.DETERMINATE


def test_manual_assignment_has_no_randomization_unit() -> None:
    result = run_quick_design_session(
        QuickDesignAnswers(
            source_description="cells",
            allocation_level="well",
            assignment_method="manual",
            independently_assigned="FALSE",
        )
    )
    assert result.bootstrap.causal_context is not None
    assert result.bootstrap.causal_context.assignment_mechanism.randomization_unit is None


def test_no_fabricated_paired_ids_across_levels() -> None:
    result = run_quick_design_session(
        QuickDesignAnswers(
            source_description="cells",
            planned_units_per_level=2,
            planned_unit_type="well",
        )
    )
    assert "SRC001" not in result.sample_sheet_csv
    assert "P001" not in result.sample_sheet_csv
    assert "PL01" not in result.sample_sheet_csv
    assert "B01" not in result.sample_sheet_csv
    rows = [r for r in result.sample_sheet_csv.strip().splitlines()[1:] if r]
    assert len(rows) == 4


def test_n_per_level_non_positive_rejected() -> None:
    with pytest.raises(ValueError):
        run_quick_design_session(
            QuickDesignAnswers(source_description="cells", planned_units_per_level=0)
        )


def test_top_level_matches_nested_independently_assigned() -> None:
    result = run_quick_design_session(
        QuickDesignAnswers(
            source_description="cells",
            independently_assigned="FALSE",
            assignment_method="manual",
            allocation_level="culture",
        )
    )
    assert result.bootstrap.independently_assigned == "FALSE"
    assert result.bootstrap.independence.independently_assigned.value == "FALSE"


def test_quick_design_export_and_freeze() -> None:
    result = run_quick_design_session(
        QuickDesignAnswers(
            source_description="line X",
            allocation_level="well",
            assignment_timing="before",
            assignment_method="random",
            independently_assigned="UNKNOWN",
            biological_source_independence="TRUE",
            interference_status="POSSIBLE",
            planned_units_per_level=3,
            planned_unit_type="well",
        )
    )
    payload = export_for_biostatistician(result)
    assert payload["export_kind"] == "quick_design_biostat_handoff"
    assert '"independent_n"' not in json.dumps(payload)
    frozen = freeze_plan(result)
    assert frozen.plan_frozen is True


def test_quick_design_never_emits_final_independent_n_in_bootstrap() -> None:
    result = run_quick_design_session(
        QuickDesignAnswers(
            source_description="cells",
            planned_units_per_level=4,
            planned_unit_type="culture",
        )
    )
    kinds = {c.kind.value for c in result.bootstrap.counts}
    assert "independent_n" not in kinds
    if result.bootstrap.counts:
        assert result.bootstrap.counts[0].unit_type == "culture"
