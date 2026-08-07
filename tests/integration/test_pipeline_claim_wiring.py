"""Wiring pipeline -> proiezione claim-specific v8 (FASE 3 step 4).

La pipeline espone per blocco claim set, finding di adeguatezza e
``ReportResolutionState`` senza alterare attributi o output esistenti.
"""

from __future__ import annotations

import pytest
from conftest import Case, analyze_directory, load_cases

from ntruth.pipeline import BlockAnalysis
from ntruth.schemas.claims import ReportResolutionState

pytestmark = pytest.mark.scientific


@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c.case_id)
def test_block_analysis_exposes_claim_projection(case: Case, tmp_path) -> None:
    result = analyze_directory(case.path, tmp_path / case.name)
    for ba in result.block_analyses:
        assert isinstance(ba.report_resolution_state, ReportResolutionState)
        assert isinstance(ba.derived_claim_sets, tuple)
        assert isinstance(ba.design_adequacy_findings, tuple)
        for claim_set in ba.derived_claim_sets:
            assert claim_set.claims
            assert all(claim.query_id == claim_set.query_id for claim in claim_set.claims)


@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c.case_id)
def test_resolution_state_aggregates_claim_states(case: Case, tmp_path) -> None:
    """Lo stato aggregato riflette gli stati claim del blocco (§10.4)."""
    result = analyze_directory(case.path, tmp_path / case.name)
    for ba in result.block_analyses:
        states = [
            claim.determinability_state for cs in ba.derived_claim_sets for claim in cs.claims
        ]
        if not states:
            continue
        # mai COMPLETE in presenza di claim non chiusi
        if any(s.value not in {"DETERMINATE"} for s in states):
            assert ba.report_resolution_state is not (
                ReportResolutionState.COMPLETE_FOR_REQUESTED_CLAIMS
            )


def test_block_analysis_defaults_preserve_legacy_construction() -> None:
    """I campi nuovi hanno default: la costruzione legacy resta valida."""
    defaults = BlockAnalysis.report_resolution_state
    assert defaults is ReportResolutionState.INVALID
