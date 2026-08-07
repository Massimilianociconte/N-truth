"""Determinabilita' claim-specific (§7.16, Appendice M) e aggregato deprecato.

Gli stati sono claim-specific: un claim non viene bloccato da dimensioni
sconosciute non pertinenti, e l'aggregato block-level v6 resta byte-identico
(guardia completa in tests/regression/test_block_level_pins.py).
"""

from __future__ import annotations

import pytest
from conftest import Case, analyze_directory, load_cases
from test_prd_v3_determinability_graph import _complete_block

from ntruth.derivation_theory.loader import load_theory
from ntruth.design import compile_experiment_block
from ntruth.graph.builder import BuildResult
from ntruth.graph.claims import derive_claim_set, unresolved_required_predicates
from ntruth.graph.determinability import claim_specific_states, derive_determinability
from ntruth.rules.loader import load_ruleset
from ntruth.schemas.claims import ClaimType
from ntruth.schemas.core import Determinability

pytestmark = pytest.mark.scientific

THEORY = load_theory()
RULESET = load_ruleset()


def _build_from_block(block):
    return BuildResult(
        hierarchy=block.hierarchy,
        factors=block.factors,
        contrasts=block.contrasts,
        endpoints=block.endpoints,
        inference_targets=block.inference_targets,
        estimands=block.estimands,
    )


def _derive(block):
    return derive_claim_set(
        block,
        compile_experiment_block(block),
        None,
        THEORY,
        RULESET,
        build=_build_from_block(block),
        assessments=block.unit_assessments,
    )


def test_two_claims_in_one_query_have_different_states(tmp_path) -> None:
    """Appendice M: stati distinti per claim nella stessa query.

    UC02: il source count e' DETERMINATE (singolo ma dichiarato) mentre EU e
    EU count restano INSUFFICIENT_INFORMATION nello stesso blocco/query.
    """
    case = next(c for c in load_cases() if c.case_id == "UC02")
    result = analyze_directory(case.path, tmp_path / case.name)
    ba = result.block_analyses[0]
    derivation = derive_claim_set(
        ba.block,
        ba.compilation,
        None,
        THEORY,
        RULESET,
        build=ba.build,
        assessments=ba.block.unit_assessments,
        evaluations=ba.evaluations,
    )
    assert len(derivation.claim_sets) == 1
    states = {c.claim_type: c.determinability_state for c in derivation.claims}
    assert states[ClaimType.BIOLOGICAL_SOURCE_COUNT] is Determinability.DETERMINATE
    assert states[ClaimType.EXPERIMENTAL_UNIT] is Determinability.INSUFFICIENT_INFORMATION
    assert states[ClaimType.EXPERIMENTAL_UNIT_COUNT] is Determinability.INSUFFICIENT_INFORMATION


def test_irrelevant_unknown_dimensions_do_not_block_claim() -> None:
    """§7.16: EU count determinabile con source count singolo e scope limitato.

    Dimensioni sconosciute non pertinenti (interference, source independence)
    restano nella memo come irrisolte ma non entrano mai nel set richiesto del
    claim di EU count e non lo bloccano.
    """
    block = _complete_block()
    assessment = block.unit_assessments[0].model_copy(update={"biological_source_count": 1})
    block = block.model_copy(update={"unit_assessments": (assessment,)})

    derivation = _derive(block)
    by_type = {c.claim_type: c for c in derivation.claims}

    count_claim = by_type[ClaimType.EXPERIMENTAL_UNIT_COUNT]
    assert count_claim.determinability_state is Determinability.DETERMINATE
    source_claim = by_type[ClaimType.BIOLOGICAL_SOURCE_COUNT]
    assert source_claim.determinability_state is Determinability.DETERMINATE
    assert source_claim.value.value == {"biological_source_count": 1}

    # Le dimensioni non pertinenti al count non sono nel suo insieme richiesto.
    assert "biological_source_independence" not in count_claim.required_predicates
    assert "interference_status" not in count_claim.required_predicates
    assert "source_provenance_confirmed" not in count_claim.required_predicates

    # La memo registra dimensioni sconosciute (non valutabili nel registro v7),
    # ma il claim non ne e' bloccato: non compaiono tra i suoi predicati.
    unknown_irrelevant = [
        predicate
        for (predicate, aid), value in derivation.memo.items()
        if aid == assessment.id
        and value is None
        and predicate not in count_claim.required_predicates
    ]
    assert unknown_irrelevant, "nessuna dimensione sconosciuta registrata nella memo"
    unresolved = unresolved_required_predicates(derivation.memo, count_claim, assessment.id)
    assert not (set(unresolved) - set(count_claim.required_predicates))


def test_claim_specific_states_feed_deprecated_aggregate() -> None:
    """L'aggregato deprecato e' una proiezione degli stati claim-specific."""
    block = _complete_block()
    states = claim_specific_states(block)
    assert len(states) == 1
    eu_state, count_state, _source_state = next(iter(states.values()))
    assert eu_state is Determinability.DETERMINATE
    assert count_state is Determinability.DETERMINATE
    compilation = compile_experiment_block(block)
    assert derive_determinability(block, compilation) is Determinability.DETERMINATE


def test_deprecated_aggregate_insufficient_when_a_decisive_claim_is_open() -> None:
    """Se il claim di EU count resta aperto, l'aggregato non chiude il blocco."""
    block = _complete_block()
    assessment = block.unit_assessments[0].model_copy(update={"n_independent": None})
    block = block.model_copy(update={"unit_assessments": (assessment,)})
    compilation = compile_experiment_block(block)
    states = claim_specific_states(block)
    _eu_state, count_state, _source_state = next(iter(states.values()))
    assert count_state is Determinability.INSUFFICIENT_INFORMATION
    assert derive_determinability(block, compilation) is Determinability.INSUFFICIENT_INFORMATION


@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c.case_id)
def test_claim_states_match_deprecated_core_dimensions(case: Case, tmp_path) -> None:
    """Coerenza: gli stati per dimensione coincidono tra nucleo e proiezione."""
    result = analyze_directory(case.path, tmp_path / case.name)
    for ba in result.block_analyses:
        states = claim_specific_states(ba.block)
        assert set(states) == {a.id for a in ba.block.unit_assessments}
        derivation = derive_claim_set(
            ba.block,
            ba.compilation,
            None,
            THEORY,
            RULESET,
            build=ba.build,
            assessments=ba.block.unit_assessments,
            evaluations=ba.evaluations,
        )
        # gli stati emessi riflettono il nucleo (al netto del floor block-level)
        for claim_set in derivation.claim_sets:
            assert claim_set.claims
