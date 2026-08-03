"""Quick Design Session vertical slice for simple_cell_culture."""

from __future__ import annotations

import json

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
    assert result.bootstrap.domain == "simple_cell_culture"


def test_quick_design_export_and_freeze() -> None:
    result = run_quick_design_session(
        QuickDesignAnswers(
            source_description="line X",
            allocation_level="well",
            assignment_timing="before",
            biological_source_independence="TRUE",
            interference_status="POSSIBLE",
            n_per_level=3,
        )
    )
    payload = export_for_biostatistician(result)
    assert payload["export_kind"] == "quick_design_biostat_handoff"
    assert '"independent_n"' not in json.dumps(payload)
    assert "independent_n" not in {c.get("kind") for c in payload.get("counts", [])}
    frozen = freeze_plan(result)
    assert frozen.plan_frozen is True
    assert frozen.export_payload is not None
    assert frozen.export_payload["plan_frozen"] is True


def test_quick_design_never_emits_final_independent_n_in_bootstrap() -> None:
    result = run_quick_design_session(QuickDesignAnswers(source_description="cells", n_per_level=4))
    kinds = {c.kind.value for c in result.bootstrap.counts}
    assert "independent_n" not in kinds
