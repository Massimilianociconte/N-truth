"""Invarianti dei contratti dati (PRD 12.4, NFR-02, NFR-03)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ntruth.schemas.core import Provenance, ProvenanceKind, Severity, stable_id
from ntruth.schemas.experiment import (
    Alert,
    ConditionalScenario,
    DataSufficiency,
    Inferability,
    NScope,
    UnitAssessment,
)
from ntruth.schemas.graph import NodeType
from ntruth.schemas.rules import Rule, Ruleset, normalize_predicate


def test_scope_cannot_be_empty() -> None:
    """n e per gruppo, contrasto ed endpoint: uno scope vuoto non esiste (GEN-006)."""
    with pytest.raises(ValidationError):
        NScope()


def test_global_scope_must_be_explicit() -> None:
    scope = NScope(is_global=True)
    assert scope.describe() == "scope globale dichiarato"


def test_alert_requires_evidence_or_missing_information() -> None:
    """NFR-03: nessun alert senza evidenza, informazione mancante o conflitto."""
    with pytest.raises(ValidationError):
        Alert(
            id="alr-1",
            rule_id="GEN-001",
            ruleset_version="0.1.0",
            severity=Severity.INFO,
            message="messaggio",
            provenance=Provenance(origin=ProvenanceKind.RULE),
        )


def test_alert_with_missing_information_is_valid() -> None:
    alert = Alert(
        id="alr-1",
        rule_id="GEN-010",
        ruleset_version="0.1.0",
        severity=Severity.INSUFFICIENT,
        message="informazione insufficiente",
        missing_information=("indipendenza delle colture",),
        provenance=Provenance(origin=ProvenanceKind.RULE),
    )
    assert alert.severity is Severity.INSUFFICIENT


def test_not_inferable_cannot_carry_an_independent_n() -> None:
    """n_independent puo essere null e non viene sostituito da altri n (PRD 12.4)."""
    with pytest.raises(ValidationError):
        UnitAssessment(
            id="uas-1",
            scope=NScope(is_global=True),
            n_independent=12,
            inferability=Inferability.NOT_INFERABLE,
            provenance=Provenance(origin=ProvenanceKind.DERIVED),
        )


def test_conditional_scenario_cannot_carry_an_authoritative_scalar_n() -> None:
    scenario = ConditionalScenario(
        conditional_on="cultures_are_independent",
        if_confirmed={"drug": 4},
        if_rejected={"drug": 1},
        question="Le colture sono preparazioni indipendenti?",
        rule_id="GEN-010",
    )

    with pytest.raises(ValidationError, match="n_independent=null"):
        UnitAssessment(
            id="uas-conditional",
            scope=NScope(is_global=True),
            n_independent=4,
            inferability=Inferability.CONDITIONAL,
            conditional_scenarios=(scenario,),
            provenance=Provenance(origin=ProvenanceKind.DERIVED),
        )


def test_sufficiency_overall_is_the_minimum_not_the_average() -> None:
    """Un aggregato non deve nascondere una lacuna (FR-014)."""
    from ntruth.schemas.core import Confidence

    sufficiency = DataSufficiency(
        intervention_level=Confidence.HIGH,
        source_independence=Confidence.UNKNOWN,
        exclusions=Confidence.HIGH,
        aggregation=Confidence.HIGH,
        statistical_model=Confidence.HIGH,
    )
    assert sufficiency.overall is Confidence.UNKNOWN


def test_stable_id_is_deterministic_and_content_addressed() -> None:
    """NFR-02: stesso input, stesso ID, senza timestamp ne contatori."""
    assert stable_id("nd", NodeType.CELL, "cell") == stable_id("nd", NodeType.CELL, "cell")
    assert stable_id("nd", NodeType.CELL, "cell") != stable_id("nd", NodeType.WELL, "cell")


def test_ruleset_rejects_duplicate_rule_ids() -> None:
    rule = Rule(
        rule_id="GEN-001",
        version="1.0.0",
        domain="general",
        inference="x",
        message_it="x",
        severity=Severity.INFO,
    )
    with pytest.raises(ValidationError):
        Ruleset(ruleset_id="dup", version="0.0.1", rules=(rule, rule))


@pytest.mark.parametrize(
    ("expression", "normalized"),
    [
        ("Cell nested_in Field", "nested(Cell, Field)"),
        ("Well derived_from Culture", "derived(Well, Culture)"),
        ("Analysis analyzed_as Cell", "analyzed_as(Cell)"),
        ("Treatment assigned_at Culture or higher", "assigned_at_or_above(Culture)"),
        ("model_accounts_for_assignment()", "model_accounts_for_assignment()"),
    ],
)
def test_triple_syntax_is_normalized(expression: str, normalized: str) -> None:
    """Le precondizioni del PRD sono scritte in forma triple e restano leggibili."""
    assert normalize_predicate(expression) == normalized
