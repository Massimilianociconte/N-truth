"""Invariants sulle eccezioni delle regole del ruleset core.

Storia: l'audit aveva segnalato come fragilita il fatto che le fixture
``exception`` delle regole senza clausole dichiarate producono sempre
``NOT_APPLICABLE``. La verifica diretta ha corretto il quadro: le 7 regole con
eccezioni dichiarate esercitano realmente il ramo ``EXCEPTED``, mentre le 25
restanti non dichiarano alcuna eccezione e quindi non hanno nulla da
esercitare. Questo modulo sigilla l'invariante che rende quella situazione
corretta e permanente.
"""

from __future__ import annotations

import pytest
from rule_fixtures.context_factory import evaluate_fixture
from unit.test_rules_contract import RULESET

from ntruth.rules.engine import apply_rules
from ntruth.schemas.rules import RuleOutcome

_SCENARIOS = ("positive", "negative", "ambiguous", "exception")


def test_rules_without_declared_exceptions_never_return_excepted() -> None:
    """Nessuna regola puo restare EXCEPTED senza clausole di eccezione dichiarate."""

    for rule in RULESET.rules:
        if rule.exceptions:
            continue
        for scenario in _SCENARIOS:
            outcome = evaluate_fixture(rule, scenario)
            assert outcome is not RuleOutcome.EXCEPTED, (
                f"{rule.rule_id}: EXCEPTED nello scenario {scenario!r} senza "
                "eccezioni dichiarate nel ruleset"
            )


def test_excepted_outcome_always_carries_the_declared_exception() -> None:
    """Se il motore restituisce EXCEPTED, la clausola attivata e una dichiarata."""

    for rule in RULESET.rules:
        result = apply_rules(
            "blk-invariant",
            *_context_and_assessment(rule),
            RULESET,
            lang="en",
        )
        for evaluation in result.evaluations:
            if evaluation.outcome is not RuleOutcome.EXCEPTED:
                continue
            declared = set(rule.normalized_exceptions())
            assert evaluation.triggered_exception in declared, (
                f"{rule.rule_id}: eccezione attivata {evaluation.triggered_exception!r} "
                f"non dichiarata ({sorted(declared)})"
            )


def _context_and_assessment(rule: object):
    from rule_fixtures.context_factory import _materialize, _scenario

    build, assessment = _materialize(_scenario(rule, "positive"))
    return build, (assessment,)


def test_declared_exceptions_are_actually_exercised() -> None:
    """Ogni eccezione dichiarata produce EXCEPTED nello scenario dedicato."""

    exercised = [
        rule.rule_id
        for rule in RULESET.rules
        if rule.exceptions and evaluate_fixture(rule, "exception") is RuleOutcome.EXCEPTED
    ]
    declared = [rule.rule_id for rule in RULESET.rules if rule.exceptions]
    assert sorted(exercised) == sorted(declared), (
        f"eccezioni dichiarate ma non esercitate: {sorted(set(declared) - set(exercised))}"
    )


@pytest.mark.parametrize("scenario", _SCENARIOS)
def test_every_scenario_is_executable_for_every_rule(scenario: str) -> None:
    """I quattro scenari NFR-12 restano eseguibili per tutte le regole."""

    outcomes = {evaluate_fixture(rule, scenario) for rule in RULESET.rules}
    assert outcomes, scenario
