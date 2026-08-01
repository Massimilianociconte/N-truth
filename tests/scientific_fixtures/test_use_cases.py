"""Casi normativi UC01-UC12 del PRD (sezione 6.2).

Ogni caso e una fixture sintetica normativa derivata dal PRD: verifica gli output
attesi del contratto software, ma non sostituisce un caso annotato e adjudicato da
esperti. Un cambiamento che rompe uno di questi test modifica il comportamento
scientifico atteso della baseline, non misura accuratezza o validita esterna.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import Case, analyze_directory, load_cases

from ntruth.schemas.experiment import ExperimentBlock, UnitAssessment

CASES = load_cases()


def _assessment_for(block: ExperimentBlock, factor_name: str | None) -> UnitAssessment:
    if factor_name is None:
        return block.unit_assessments[0]
    for assessment in block.unit_assessments:
        factor = block.factor(assessment.scope.factor_id) if assessment.scope.factor_id else None
        if factor is not None and factor.name == factor_name:
            return assessment
    raise AssertionError(
        f"nessun assessment per il fattore '{factor_name}'. "
        f"Fattori presenti: {[f.name for f in block.factors]}"
    )


@pytest.mark.scientific
@pytest.mark.parametrize("case", CASES, ids=[c.case_id for c in CASES])
def test_use_case(case: Case, tmp_path: Path) -> None:
    result = analyze_directory(case.path, tmp_path / case.name)
    block = result.block
    expected = case.expected["expect"]
    assessment = _assessment_for(block, case.expected.get("factor"))
    context = f"{case.case_id} ({case.expected['description']})"

    def as_str(value: object | None) -> str | None:
        return str(value) if value is not None else None

    assert as_str(assessment.experimental_unit) == expected["experimental_unit"], (
        f"{context}: unita sperimentale attesa {expected['experimental_unit']}, "
        f"ottenuta {assessment.experimental_unit}. {assessment.rationale}"
    )
    assert as_str(assessment.observational_unit) == expected["observational_unit"], context
    assert as_str(assessment.analytical_unit) == expected["analytical_unit"], context

    assert assessment.n_declared == expected["n_declared"], (
        f"{context}: n dichiarato atteso {expected['n_declared']}, ottenuto {assessment.n_declared}"
    )
    assert assessment.n_observational == expected["n_observational"], context
    assert assessment.n_independent == expected["n_independent"], (
        f"{context}: n indipendente atteso {expected['n_independent']}, "
        f"ottenuto {assessment.n_independent}. {assessment.rationale}"
    )
    if "n_allocated" in expected:
        assert assessment.n_allocated == expected["n_allocated"], context
    if "n_analyzed" in expected:
        assert assessment.n_analyzed == expected["n_analyzed"], context
    if "n_declared_global" in expected:
        # Un n globale resta disponibile come statement di fonte, ma il v3
        # vieta di legarlo a un assessment privo di contrasto esplicito.
        assert assessment.scope.contrast_id is None, context
        assert any(
            statement.scope.is_global and statement.value == expected["n_declared_global"]
            for statement in block.n_statements
        ), context

    expected_scopes = expected.get("scopes", [])
    if expected_scopes:
        actual_scopes = {
            (candidate.scope.group, candidate.scope.endpoint_id)
            for candidate in block.unit_assessments
        }
        assert len(actual_scopes) == len(expected_scopes), (
            f"{context}: prodotto cartesiano o scope mancanti: {actual_scopes}"
        )
        assert all(contrast.endpoint_ids for contrast in block.contrasts), context

    for scoped in expected_scopes:
        matching = []
        for candidate in block.unit_assessments:
            endpoint = (
                block.endpoint(candidate.scope.endpoint_id) if candidate.scope.endpoint_id else None
            )
            if (
                candidate.scope.group == scoped["group"]
                and endpoint is not None
                and endpoint.name == scoped["endpoint"]
            ):
                matching.append(candidate)
        assert len(matching) == 1, (
            f"{context}: atteso uno scope gruppo={scoped['group']}, "
            f"endpoint={scoped['endpoint']}; trovati {len(matching)}"
        )
        scoped_assessment = matching[0]
        assert scoped_assessment.n_declared == scoped["n_declared"], context
        assert scoped_assessment.n_observational == scoped["n_observational"], context
        assert scoped_assessment.n_independent == scoped["n_independent"], context

    assert assessment.inferability.value == expected["inferability"], context
    assert assessment.risk.value == expected["risk"], context

    fired = {alert.rule_id for alert in block.alerts}
    for rule_id in expected["alerts_include"]:
        assert rule_id in fired, f"{context}: regola {rule_id} attesa. Scattate: {sorted(fired)}"
    for rule_id in expected["alerts_exclude"]:
        assert rule_id not in fired, (
            f"{context}: regola {rule_id} non doveva scattare. Scattate: {sorted(fired)}"
        )

    assert result.abstention.abstained == expected["abstained"], (
        f"{context}: astensione attesa {expected['abstained']}, "
        f"ottenuta {result.abstention.abstained} ({result.abstention.codes})"
    )
    unresolved = sum(1 for c in block.contradictions if c.status == "unresolved")
    assert unresolved == expected["unresolved_conflicts"], context


@pytest.mark.scientific
@pytest.mark.parametrize("case", CASES, ids=[c.case_id for c in CASES])
def test_every_alert_is_traceable(case: Case, tmp_path: Path) -> None:
    """NFR-03: 100% degli alert con rule ID ed evidenza o informazione mancante."""
    result = analyze_directory(case.path, tmp_path / f"{case.name}-trace")
    block = result.block
    for alert in block.alerts:
        assert alert.rule_id, f"{case.case_id}: alert senza rule_id"
        assert alert.ruleset_version, f"{case.case_id}: alert senza versione di ruleset"
        assert alert.evidence_ids or alert.missing_information or alert.conflict_ids, (
            f"{case.case_id}: alert {alert.rule_id} senza evidenza ne informazione mancante"
        )
        for evidence_id in alert.evidence_ids:
            assert block.evidence_by_id(evidence_id) is not None, (
                f"{case.case_id}: alert {alert.rule_id} cita un'evidenza inesistente"
            )


@pytest.mark.scientific
@pytest.mark.parametrize("case", CASES, ids=[c.case_id for c in CASES])
def test_no_validity_verdict(case: Case, tmp_path: Path) -> None:
    """FR-023: il sistema non dichiara mai un paper valido, errato o fraudolento."""
    forbidden = [
        "paper valido",
        "paper errato",
        "non valido",
        "risultati non sono validi",
        "frode",
        "misconduct",
        "invalid paper",
        "scientifically valid",
    ]
    result = analyze_directory(case.path, tmp_path / f"{case.name}-verdict")
    text = " ".join(
        [
            *(a.message.lower() for a in result.block.alerts),
            *(a.rationale.lower() for a in result.block.unit_assessments),
            *(q.text.lower() for q in result.block.questions),
        ]
    )
    for phrase in forbidden:
        assert phrase not in text, f"{case.case_id}: linguaggio di verdetto vietato '{phrase}'"
