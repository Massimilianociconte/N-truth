"""Contratto claim-specific di derive_claim_set (§10.2, §7.15, Appendice N.1).

Il motore claim-specific e' un adapter sopra i nuclei esistenti
(resolve_units, derive_determinability): questi test verificano la proiezione
in DerivedClaim senza toccare il percorso block-level (pin in
tests/regression).
"""

from __future__ import annotations

import pytest
from conftest import Case, analyze_directory, load_cases

from ntruth.derivation_theory.loader import load_theory
from ntruth.graph.claims import PredicateMemo, derive_claim_set
from ntruth.graph.index import GraphIndex
from ntruth.pipeline import BlockAnalysis
from ntruth.schemas.claims import ClaimType
from ntruth.schemas.core import Determinability
from ntruth.schemas.kernel import KnowledgeState, ProfileCoverageStatus, ScenarioCoverageStatus
from ntruth.schemas.rules import Ruleset

pytestmark = pytest.mark.scientific

THEORY = load_theory()


def derive_block(ba: BlockAnalysis, ruleset: Ruleset, *, index: GraphIndex | None = None):
    return derive_claim_set(
        ba.block,
        ba.compilation,
        None,
        THEORY,
        ruleset,
        build=ba.build,
        assessments=ba.block.unit_assessments,
        evaluations=ba.evaluations,
        index=index,
    )


@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c.case_id)
def test_claims_carry_full_contract(case: Case, tmp_path, ruleset: Ruleset) -> None:
    """Ogni claim porta query_id, stato, grado, predicati, versioni e trace (§10.2)."""
    result = analyze_directory(case.path, tmp_path / case.name)
    for ba in result.block_analyses:
        derivation = derive_block(ba, ruleset)
        for claim in derivation.claims:
            assert claim.query_id.strip(), "claim senza query (§10.2)"
            assert claim.determinability_state in set(Determinability)
            assert claim.support_grade is not None
            assert claim.theory_version == THEORY.metadata.version
            assert claim.ruleset_version == ruleset.version
            assert claim.theory_clauses, "claim senza clausole della teoria"
            assert claim.assumptions, "assunzioni §7.17 mancanti"
            assert "record_completeness" in claim.assumptions
            assert "predicate_sufficiency" in claim.assumptions
            # proof trace: rule ids + valori delle premesse quando valutati
            for entry in claim.rule_trace:
                assert entry.rule_id, "rule trace senza rule id"
            if claim.claim_type is ClaimType.EXPERIMENTAL_UNIT_COUNT:
                assert claim.required_predicates, "claim di count senza predicati richiesti"
        for claim_set in derivation.claim_sets:
            assert all(c.query_id == claim_set.query_id for c in claim_set.claims)


@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c.case_id)
def test_claim_ids_are_deterministic(case: Case, tmp_path, ruleset: Ruleset) -> None:
    """stable_id content-addressed: due derivazioni identiche -> stessi id."""
    result = analyze_directory(case.path, tmp_path / case.name)
    for ba in result.block_analyses:
        first = derive_block(ba, ruleset)
        second = derive_block(ba, ruleset)
        assert [c.claim_id for c in first.claims] == [c.claim_id for c in second.claims]
        assert first.report_resolution_state is second.report_resolution_state


@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c.case_id)
def test_determinate_claim_never_has_unknown_value(case: Case, tmp_path, ruleset: Ruleset) -> None:
    """M.1: nessun claim DETERMINATE con valore UNKNOWN (invariante schema)."""
    result = analyze_directory(case.path, tmp_path / case.name)
    for ba in result.block_analyses:
        derivation = derive_block(ba, ruleset)
        for claim in derivation.claims:
            if claim.determinability_state is Determinability.DETERMINATE:
                assert claim.value.knowledge_state is not KnowledgeState.UNKNOWN


def test_memo_evaluates_each_predicate_once_per_assessment(ruleset: Ruleset, tmp_path) -> None:
    """NFR-06/NFR-07: singolo passaggio, keyed (predicate, assessment)."""
    memo = PredicateMemo()
    key = ("pred-a", "ASSESSMENT-1")
    memo._values[key] = True
    before = memo.evaluations
    # valore gia' memoizzato: nessuna nuova valutazione
    assert memo.get("pred-a", "ASSESSMENT-1") is True
    assert memo.evaluations == before
    # flipped() produce una copia senza mutare l'originale
    clone = memo.flipped("pred-a", "ASSESSMENT-1", False)
    assert clone.get("pred-a", "ASSESSMENT-1") is False
    assert memo.get("pred-a", "ASSESSMENT-1") is True


def test_prebuilt_index_is_reused_not_rebuilt(tmp_path, ruleset: Ruleset) -> None:
    """Il GraphIndex pre-costruito viene accettato e mai ricostruito internamente."""
    import ntruth.graph.claims as claims_module

    constructions = {"count": 0}
    real_index = claims_module.GraphIndex

    class CountingIndex(real_index):
        def __init__(self, *args, **kwargs):
            constructions["count"] += 1
            super().__init__(*args, **kwargs)

    case = load_cases()[0]
    result = analyze_directory(case.path, tmp_path / case.name)
    ba = result.block_analyses[0]
    prebuilt = GraphIndex(ba.build.hierarchy)
    claims_module.GraphIndex = CountingIndex
    try:
        derivation = derive_claim_set(
            ba.block,
            ba.compilation,
            None,
            THEORY,
            ruleset,
            build=ba.build,
            assessments=ba.block.unit_assessments,
            evaluations=ba.evaluations,
            index=prebuilt,
        )
    finally:
        claims_module.GraphIndex = real_index
    assert constructions["count"] == 0, "indice ricostruito nonostante fosse fornito"
    assert derivation.claims


@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c.case_id)
def test_findings_never_derive_from_determinability(case: Case, tmp_path, ruleset: Ruleset) -> None:
    """§7.18: l'adeguatezza non deriva dalla determinabilita'.

    I finding sono emessi solo da alert con evidenza propria nel blocco;
    ogni evidence_id dichiarato deve esistere nel blocco.
    """
    result = analyze_directory(case.path, tmp_path / case.name)
    for ba in result.block_analyses:
        derivation = derive_block(ba, ruleset)
        evidence_ids = {e.id for e in ba.block.evidence}
        for finding in derivation.design_adequacy_findings:
            assert finding.evidence_ids, "finding senza evidenza propria (§10.5)"
            assert set(finding.evidence_ids) <= evidence_ids


@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c.case_id)
def test_coverage_is_fail_closed(case: Case, tmp_path, ruleset: Ruleset) -> None:
    """Scenario coverage mai dichiarata esaustiva senza revisione (§0.5)."""
    result = analyze_directory(case.path, tmp_path / case.name)
    for ba in result.block_analyses:
        derivation = derive_block(ba, ruleset)
        if not derivation.claim_sets:
            assert not derivation.scenario_coverages
            assert derivation.profile_coverage is None
            continue
        assert derivation.scenario_coverages
        for coverage in derivation.scenario_coverages:
            assert coverage.status is ScenarioCoverageStatus.NON_EXHAUSTIVE
            assert coverage.theory_version == THEORY.metadata.version
        profile = derivation.profile_coverage
        assert profile is not None
        assert profile.status is ProfileCoverageStatus.COVERED_WITH_KNOWN_GAPS
        assert set(profile.known_gaps) == set(THEORY.known_gap_predicates())
        assert profile.decisive_predicate_set, "nessun predicato decisivo dichiarato"
