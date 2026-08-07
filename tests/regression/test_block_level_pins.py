"""Cutover guard FASE 3: pin byte-identico degli output block-level correnti.

Prima di ogni refactor del motore di derivazione, questo modulo congela gli
output osservabili del percorso block-level deprecato: ``derive_determinability()``
(campo ``block.determinability``) e ``resolve_units()`` (i ``unit_assessments``
proiettati dal resolver e poi confermati dal rules engine). Lo snapshot in
``block_level_pins.json`` e stato catturato sullo stato pre-migrazione ed e
deterministico (stable_id content-addressed): qualunque deviazione significa che
il percorso deprecato ha cambiato comportamento, ed e un release blocker.

Il guard non misura accuratezza esterna: certifica solo che la migrazione verso
il motore claim-specific (``derive_claim_set``) non altera la semantica
block-level esistente (Appendice M, PRD v8).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import Case, analyze_directory, load_cases

from ntruth.schemas.experiment import ExperimentBlock, UnitAssessment

pytestmark = pytest.mark.regression

PINS_PATH = Path(__file__).with_name("block_level_pins.json")
CASES = load_cases()
PINS: dict[str, dict] = json.loads(PINS_PATH.read_text(encoding="utf-8"))


def _assessment_pin(assessment: UnitAssessment) -> dict:
    """Proiezione canonica di un assessment ai fini del pin.

    Conserva i campi semantici di derivazione (unita, tutti gli n, inferability,
    risk, scenari condizionali, cluster) e gli id di scope generati, che sono
    content-addressed e quindi parte integrante del contratto deterministico.
    """
    scope = assessment.scope
    return {
        "scope": {
            "group": scope.group,
            "endpoint_id": scope.endpoint_id,
            "contrast_id": scope.contrast_id,
            "factor_id": scope.factor_id,
        },
        "biological_unit": str(assessment.biological_unit) if assessment.biological_unit else None,
        "allocation_unit_candidate": (
            str(assessment.allocation_unit_candidate)
            if assessment.allocation_unit_candidate
            else None
        ),
        "experimental_unit": str(assessment.experimental_unit)
        if assessment.experimental_unit
        else None,
        "observational_unit": (
            str(assessment.observational_unit) if assessment.observational_unit else None
        ),
        "analytical_unit": str(assessment.analytical_unit) if assessment.analytical_unit else None,
        "n_planned": assessment.n_planned,
        "n_declared": assessment.n_declared,
        "n_allocated": assessment.n_allocated,
        "n_treated": assessment.n_treated,
        "n_observed": assessment.n_observed,
        "n_excluded": assessment.n_excluded,
        "n_analysed": assessment.n_analysed,
        "n_observational": assessment.n_observational,
        "n_analytical": assessment.n_analytical,
        "n_independent": assessment.n_independent,
        "biological_source_count": assessment.biological_source_count,
        "effective_n": assessment.effective_n,
        "independent_entity_type": assessment.independent_entity_type,
        "cluster_types": [str(t) for t in assessment.cluster_types],
        "inferability": assessment.inferability.value,
        "risk": assessment.risk.value,
        "conditional_scenarios": [
            {
                "conditional_on": s.conditional_on,
                "if_confirmed": s.if_confirmed,
                "if_rejected": s.if_rejected,
                "question": s.question,
                "rule_id": s.rule_id,
            }
            for s in assessment.conditional_scenarios
        ],
    }


def _block_pin(block: ExperimentBlock) -> dict:
    return {
        "determinability": block.determinability.value,
        "graph_status": block.graph_status.value,
        "unit_assessments": [_assessment_pin(a) for a in block.unit_assessments],
    }


@pytest.mark.parametrize("case", CASES, ids=[c.case_id for c in CASES])
def test_block_level_pin_unchanged(case: Case, tmp_path: Path) -> None:
    """Il percorso block-level deprecato resta byte-identico (cutover guard)."""
    expected = PINS[case.case_id]
    result = analyze_directory(case.path, tmp_path / case.name)
    actual = _block_pin(result.block)
    assert actual == expected, (
        f"{case.case_id}: il pin block-level e cambiato. "
        f"atteso={json.dumps(expected, sort_keys=True)} "
        f"ottenuto={json.dumps(actual, sort_keys=True)}"
    )


def test_pin_snapshot_covers_all_fixtures() -> None:
    """Lo snapshot deve coprire tutte le fixture scientifiche caricate."""
    case_ids = {case.case_id for case in CASES}
    pinned_ids = set(PINS)
    assert pinned_ids == case_ids, (
        f"copertura pin incompleta: manca {sorted(case_ids - pinned_ids)}, "
        f"in eccesso {sorted(pinned_ids - case_ids)}"
    )
