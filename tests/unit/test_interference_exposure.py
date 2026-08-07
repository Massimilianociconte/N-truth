"""Semantica interference/exposure (FASE 3 step 5, §7.15 E, Appendice Y).

Invarianti scientifiche assolute:
- l'interference non modifica mai EU identita' o il suo conteggio (Y.1);
- l'indipendenza della provenienza biologica non e' mai un proxy della
  separabilita' di assegnazione;
- il silenzio non dichiara assenza di interference (NFR-26);
- DETERMINATE non significa mai disegno adeguato (§7.18).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from rule_fixtures import exposure_fixtures
from test_prd_v3_determinability_graph import _complete_block

import ntruth.graph.units as units_module
from ntruth.derivation_theory.loader import load_theory
from ntruth.design import compile_experiment_block
from ntruth.graph.builder import BuildResult
from ntruth.graph.claims import derive_claim_set, derive_estimand_support
from ntruth.rules.loader import load_ruleset
from ntruth.schemas.claims import AdequacyAxis, ClaimType
from ntruth.schemas.core import Determinability
from ntruth.schemas.kernel import (
    ESTIMAND_UNSUPPORTED_OR_UNSPECIFIED,
    ExposureAssessment,
    InterferenceStatus,
    KnowledgeState,
    KnowledgeValue,
)

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


def _derive(block, exposures=()):
    return derive_claim_set(
        block,
        compile_experiment_block(block),
        None,
        THEORY,
        RULESET,
        build=_build_from_block(block),
        assessments=block.unit_assessments,
        exposures=exposures,
    )


def _claims_by_type(derivation):
    by_type: dict[ClaimType, list] = {}
    for claim in derivation.claims:
        by_type.setdefault(claim.claim_type, []).append(claim)
    return by_type


def test_documented_interference_produces_estimand_caveat_not_eu_change() -> None:
    """Positiva: shared bath documented -> caveat estimand; EU invariata."""
    block = _complete_block()
    exposed = _derive(block, exposures=(exposure_fixtures.shared_bath_documented(),))

    findings = [f for f in exposed.design_adequacy_findings if f.axis is AdequacyAxis.INTERFERENCE]
    assert len(findings) == 1
    assert findings[0].finding == "INTERFERENCE_DOCUMENTED"
    assert ESTIMAND_UNSUPPORTED_OR_UNSPECIFIED in findings[0].rationale

    interference_claims = _claims_by_type(exposed)[ClaimType.DESIGN_ADEQUACY_FINDING]
    assert len(interference_claims) == 1
    value = interference_claims[0].value.value
    assert value["interference_status"] == InterferenceStatus.DOCUMENTED.value
    assert value["estimand_support"] == ESTIMAND_UNSUPPORTED_OR_UNSPECIFIED
    assert value["exposure_pathway"] == "shared_medium"
    assert value["exposure_container"] == "bath"


@pytest.mark.invariant
def test_interference_never_changes_eu_identity_or_count() -> None:
    """Negativa (PRD P.5 #21): interference non cambia EU o il suo count."""
    block = _complete_block()
    baseline = _derive(block)
    for exposures in (
        (exposure_fixtures.shared_bath_documented(),),
        (exposure_fixtures.no_known_path(),),
        (exposure_fixtures.silent(),),
    ):
        exposed = _derive(block, exposures=exposures)
        for claim_type in (ClaimType.EXPERIMENTAL_UNIT, ClaimType.EXPERIMENTAL_UNIT_COUNT):
            base = _claims_by_type(baseline)[claim_type]
            changed = _claims_by_type(exposed)[claim_type]
            assert [c.model_dump() for c in base] == [c.model_dump() for c in changed], (
                f"il claim {claim_type.value} e' mutato con interference "
                f"{exposures[0].interference_status.value}"
            )


def test_minimal_counterfactual_pair_only_exposure_outputs_differ() -> None:
    """§7.13: record identici salvo interference; solo exposure/estimand cambia."""
    block = _complete_block()
    documented = _derive(block, exposures=(exposure_fixtures.shared_bath_documented(),))
    no_path = _derive(block, exposures=(exposure_fixtures.no_known_path(),))

    for claim_type in (
        ClaimType.EXPERIMENTAL_UNIT,
        ClaimType.EXPERIMENTAL_UNIT_COUNT,
        ClaimType.BIOLOGICAL_SOURCE_COUNT,
    ):
        assert [c.model_dump() for c in _claims_by_type(documented)[claim_type]] == [
            c.model_dump() for c in _claims_by_type(no_path)[claim_type]
        ]

    documented_claims = _claims_by_type(documented)[ClaimType.DESIGN_ADEQUACY_FINDING]
    no_path_claims = _claims_by_type(no_path)[ClaimType.DESIGN_ADEQUACY_FINDING]
    assert documented_claims[0].claim_id == no_path_claims[0].claim_id
    assert (
        documented_claims[0].value.value["estimand_support"] == ESTIMAND_UNSUPPORTED_OR_UNSPECIFIED
    )
    assert no_path_claims[0].value.value["estimand_support"] == KnowledgeState.UNKNOWN.value
    assert no_path_claims[0].determinability_state is Determinability.DETERMINATE, (
        "no_known_path dichiarato con evidenza resta un fatto risolto, non una prova di assenza"
    )


def test_silence_never_declares_absence_of_interference() -> None:
    """NFR-26: esposizione silente -> UNKNOWN, nessun finding inventato."""
    silent = exposure_fixtures.silent()
    assert silent.interference_status is InterferenceStatus.UNKNOWN
    block = _complete_block()
    derivation = _derive(block, exposures=(silent,))
    assert not [
        f for f in derivation.design_adequacy_findings if f.axis is AdequacyAxis.INTERFERENCE
    ]
    interference_claims = _claims_by_type(derivation)[ClaimType.DESIGN_ADEQUACY_FINDING]
    assert interference_claims[0].determinability_state is (
        Determinability.INSUFFICIENT_INFORMATION
    )


def test_declared_interference_without_evidence_is_rejected() -> None:
    """Fail-closed: nessuno stato dichiarato senza evidenza propria."""
    for status in (
        InterferenceStatus.NO_KNOWN_PATH,
        InterferenceStatus.POSSIBLE,
        InterferenceStatus.DOCUMENTED,
    ):
        with pytest.raises(ValueError):
            ExposureAssessment(factor_id="factor-x", interference_status=status)


def test_estimand_support_documented_with_mapping_stays_fail_closed() -> None:
    """Token positivi di estimand non definiti dal PRD: mai inventati (SRR)."""
    exposure = ExposureAssessment(
        factor_id="factor-x",
        interference_status=InterferenceStatus.DOCUMENTED,
        exposure_mapping=KnowledgeValue(
            knowledge_state=KnowledgeState.PRESENT,
            value="dose_per_animal",
            evidence_ids=("evidence-allocation",),
        ),
        evidence_ids=("evidence-allocation",),
    )
    estimand = derive_estimand_support(exposure)
    assert estimand.knowledge_state is KnowledgeState.UNKNOWN
    assert estimand.value is None


@pytest.mark.invariant
def test_biological_source_independence_is_never_assignment_separability() -> None:
    """Audit: _confirmed_source_independence tocca solo la sufficiency di source.

    L'identita' dell'EU e' decisa esclusivamente da
    ``factor.independently_assigned is TriState.TRUE`` (nessun consumo della
    source independence); la funzione e' consumata in un solo punto, per la
    sola DataSufficiency.source_independence.
    """
    source = Path(units_module.__file__).read_text(encoding="utf-8")
    occurrences = [line for line in source.splitlines() if "_confirmed_source_independence" in line]
    assert len(occurrences) == 2, "consumo inatteso di _confirmed_source_independence"
    consumer = next(line for line in occurrences if "_confirmed_source_independence(node)" in line)
    assert "elif" in consumer

    lines = source.splitlines()
    index = next(i for i, line in enumerate(lines) if "elif _confirmed_source_independence" in line)
    window = lines[index : index + 8]
    assert any("source_independence = Confidence.HIGH" in line for line in window)
    assert not any("experimental_unit =" in line for line in window), (
        "la source independence non deve mai riassegnare l'EU"
    )

    eu_assignment = [
        line.strip() for line in lines if "factor.independently_assigned is TriState.TRUE" in line
    ]
    assert eu_assignment, "l'identita' dell'EU deve restare ancorata all'assegnazione"


@pytest.mark.invariant
def test_determinate_exposure_claim_is_not_adequacy() -> None:
    """§7.18: il claim exposure risolto non certifica un disegno adeguato."""
    block = _complete_block()
    derivation = _derive(block, exposures=(exposure_fixtures.no_known_path(),))
    claim = _claims_by_type(derivation)[ClaimType.DESIGN_ADEQUACY_FINDING][0]
    assert claim.determinability_state is Determinability.DETERMINATE
    finding = next(
        f for f in derivation.design_adequacy_findings if f.axis is AdequacyAxis.INTERFERENCE
    )
    assert finding.finding == "INTERFERENCE_NO_KNOWN_PATH"
    assert finding.source_determinability_state is not Determinability.DETERMINATE
