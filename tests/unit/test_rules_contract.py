"""Il ruleset deve essere interamente valutabile (PRD 8.1, NFR-12)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from rule_fixtures.context_factory import evaluate_fixture

from ntruth.rules.loader import load_ruleset
from ntruth.rules.predicates import REGISTRY, UnknownPredicate
from ntruth.schemas.core import AlertClass, Severity
from ntruth.schemas.rules import Rule, RuleFixture, RuleFixtureKind

RULESET = load_ruleset()
RULESET_PATH = Path(__file__).resolve().parents[2] / "rulesets" / "ntruth-core-0.1.0.json"
EXPECTED_ALERT_CLASSES = {
    AlertClass.DESIGN_REPLICATION: {
        "GEN-001",
        "GEN-003",
        "GEN-005",
        "GEN-007",
        "GEN-010",
        "CC-006",
        "SC-004",
        "ANI-001",
        "ANI-002",
        "ANI-005",
    },
    AlertClass.ANALYTICAL_DEPENDENCE: {
        "GEN-002",
        "GEN-004",
        "GEN-008",
        "GEN-009",
        "CC-001",
        "CC-004",
        *(f"MIC-{index:03d}" for index in range(1, 7)),
        "SC-002",
        "SC-003",
        "SC-005",
        "ANI-003",
        "ANI-004",
    },
    AlertClass.INFERENCE_SCOPE: {
        "GEN-006",
        "CC-002",
        "CC-003",
        "CC-005",
        "SC-001",
    },
}
ALL_EXPRESSIONS = [
    (rule.rule_id, expression)
    for rule in RULESET.rules
    for expression in (
        *rule.normalized_preconditions(),
        *rule.normalized_exceptions(),
        *rule.normalized_abstentions(),
    )
]


def _predicate_name(expression: str) -> str:
    body = expression.removeprefix("not ").strip()
    return body.split("(", 1)[0]


@pytest.mark.parametrize(
    ("rule_id", "expression"), ALL_EXPRESSIONS, ids=[f"{r}:{e}" for r, e in ALL_EXPRESSIONS]
)
def test_every_predicate_exists(rule_id: str, expression: str) -> None:
    """Un predicato sconosciuto renderebbe la regola non valutabile in silenzio."""
    name = _predicate_name(expression)
    assert name in REGISTRY, (
        f"{rule_id}: predicato '{name}' non implementato. Disponibili: {sorted(REGISTRY)}"
    )


def test_ruleset_covers_the_prd_rule_ids() -> None:
    """Le regole elencate nel PRD 8.2-8.6 devono esistere tutte."""
    expected = {
        *(f"GEN-{i:03d}" for i in range(1, 11)),
        *(f"CC-{i:03d}" for i in range(1, 7)),
        *(f"MIC-{i:03d}" for i in range(1, 7)),
        *(f"SC-{i:03d}" for i in range(1, 6)),
        *(f"ANI-{i:03d}" for i in range(1, 6)),
    }
    present = {rule.rule_id for rule in RULESET.rules}
    assert expected <= present, f"regole mancanti: {sorted(expected - present)}"


def test_critical_rules_declare_exception_or_abstention() -> None:
    """Una regola critical senza via d'uscita produce falsi allarmi (rischio R4)."""
    for rule in RULESET.rules:
        if rule.severity is Severity.CRITICAL:
            assert rule.exceptions or rule.abstain_if, (
                f"{rule.rule_id}: severity critical senza eccezioni ne condizioni di astensione"
            )
            assert rule.requires_human_confirmation, (
                f"{rule.rule_id}: severity critical senza richiesta di conferma umana"
            )


def test_every_rule_has_a_message_in_both_languages() -> None:
    """NFR-15: layer linguistico separato da quello scientifico."""
    for rule in RULESET.rules:
        assert rule.message("it"), f"{rule.rule_id}: messaggio italiano assente"
        assert rule.message("en"), f"{rule.rule_id}: messaggio inglese assente"


def test_every_rule_declares_an_explicit_v3_alert_class_and_covers_the_taxonomy() -> None:
    """Il ruleset non puo dipendere dal default Python e deve usare tutte le classi v3."""
    raw_rules = json.loads(RULESET_PATH.read_text(encoding="utf-8"))["rules"]
    missing = [item["rule_id"] for item in raw_rules if "alert_class" not in item]
    assert not missing, f"alert_class implicita per: {missing}"

    declared = {item["alert_class"] for item in raw_rules}
    assert declared == {item.value for item in AlertClass}

    loaded = {rule.rule_id: rule.alert_class.value for rule in RULESET.rules}
    assert loaded == {item["rule_id"]: item["alert_class"] for item in raw_rules}
    actual_by_class = {
        alert_class: {rule.rule_id for rule in RULESET.rules if rule.alert_class is alert_class}
        for alert_class in AlertClass
    }
    assert actual_by_class == EXPECTED_ALERT_CLASSES


def test_ruleset_checksum_is_stable() -> None:
    """Il checksum entra nel report: due caricamenti devono coincidere (FR-034)."""
    assert load_ruleset().checksum() == RULESET.checksum()


def test_unknown_predicate_is_reported_not_ignored() -> None:
    from ntruth.rules.predicates import evaluate

    with pytest.raises(UnknownPredicate):
        evaluate("predicato_inesistente(Cell)", None)  # type: ignore[arg-type]


def test_every_core_rule_declares_all_four_fixture_classes() -> None:
    """NFR-12: positivo, negativo, ambiguo ed eccezione sono dichiarati per regola."""
    required = set(RuleFixtureKind)
    for rule in RULESET.rules:
        kinds = {fixture.kind for fixture in rule.fixtures}
        assert kinds == required, (
            f"{rule.rule_id}: fixture mancanti={sorted(k.value for k in required - kinds)}, "
            f"extra={sorted(k.value for k in kinds - required)}"
        )
        ids = [fixture.id for fixture in rule.fixtures]
        assert len(ids) == len(set(ids)), f"{rule.rule_id}: fixture ID duplicati"
        for fixture in rule.fixtures:
            assert Path(fixture.path).is_file(), f"{fixture.id}: path assente {fixture.path}"


ALL_RULE_FIXTURES = [(rule, fixture) for rule in RULESET.rules for fixture in rule.fixtures]


@pytest.mark.parametrize(
    ("rule", "fixture"),
    ALL_RULE_FIXTURES,
    ids=[fixture.id for _, fixture in ALL_RULE_FIXTURES],
)
def test_declared_rule_fixture_has_the_expected_outcome(rule: Rule, fixture: RuleFixture) -> None:
    """Ogni dichiarazione e eseguibile sul rules engine reale, senza monkeypatch."""
    outcome = evaluate_fixture(rule, fixture.scenario)
    assert outcome is fixture.expected_outcome, (
        f"{fixture.id}: atteso {fixture.expected_outcome}, ottenuto {outcome}"
    )
