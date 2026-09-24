"""Un effetto casuale sopra l'unita sperimentale non sopprime la pseudoreplicazione.

Scenario (Lazic 2010; Aarts et al. 2014): trattamento assegnato alla coltura,
colture annidate nei donatori, analisi sulle singole cellule, modello misto con
il solo intercetto casuale per donatore. Le cellule della stessa coltura
restano trattate come indipendenti: l'errore standard del contrasto e
sottostimato e il tasso di falsi positivi cresce. ``ntruth-core@0.2.0``
accettava l'antenato come eccezione; ``0.3.0`` richiede il termine per l'unita
sperimentale. La versione storica resta riproducibile.
"""

from __future__ import annotations

import pytest
from rule_fixtures.context_factory import _materialize, _Spec

from ntruth.rules.engine import apply_rules
from ntruth.rules.loader import load_ruleset
from ntruth.schemas.graph import NodeType, RelationType
from ntruth.schemas.rules import RuleOutcome, Ruleset


def _spec(model_levels: set[NodeType]) -> _Spec:
    spec = _Spec()
    spec.add(NodeType.HUMAN_DONOR, 3)
    spec.add(NodeType.CELL_CULTURE, 6)
    spec.add(NodeType.CELL, 600)
    spec.relations.add((RelationType.NESTED_IN, NodeType.CELL_CULTURE, NodeType.HUMAN_DONOR))
    spec.relations.add((RelationType.NESTED_IN, NodeType.CELL, NodeType.CELL_CULTURE))
    spec.experimental_unit = NodeType.CELL_CULTURE
    spec.observational_unit = NodeType.CELL
    spec.analytical_unit = NodeType.CELL
    spec.operational_independence = True
    spec.model_kind = "mixed"
    spec.model_levels = set(model_levels)
    return spec


def _outcome(version: str, rule_id: str, model_levels: set[NodeType]) -> RuleOutcome:
    rule = next(r for r in load_ruleset("ntruth-core", version).rules if r.rule_id == rule_id)
    build, assessment = _materialize(_spec(model_levels))
    ruleset = Ruleset(ruleset_id="strict-exception", version=version, rules=(rule,))
    result = apply_rules("blk-strict", build, (assessment,), ruleset)
    (evaluation,) = [item for item in result.evaluations if item.rule_id == rule_id]
    return evaluation.outcome


def test_ancestor_only_random_effect_no_longer_excepts_gen_002() -> None:
    donor_only = {NodeType.HUMAN_DONOR}
    assert _outcome("0.2.0", "GEN-002", donor_only) is RuleOutcome.EXCEPTED
    assert _outcome("0.3.0", "GEN-002", donor_only) is RuleOutcome.FIRED


@pytest.mark.parametrize("version", ["0.2.0", "0.3.0"])
def test_experimental_unit_term_still_excepts_gen_002(version: str) -> None:
    levels = {NodeType.CELL_CULTURE, NodeType.HUMAN_DONOR}
    assert _outcome(version, "GEN-002", levels) is RuleOutcome.EXCEPTED


@pytest.mark.parametrize("version", ["0.2.0", "0.3.0"])
def test_gen_009_wording_about_higher_levels_is_unchanged(version: str) -> None:
    # GEN-009 afferma "nessun termine per l'unita ne per i livelli superiori":
    # con il termine per il donatore dichiarato non deve scattare.
    assert _outcome(version, "GEN-009", {NodeType.HUMAN_DONOR}) is RuleOutcome.NOT_APPLICABLE
    assert _outcome(version, "GEN-009", set()) is RuleOutcome.FIRED


def test_intermediate_level_term_does_not_except_either() -> None:
    # Un termine per un livello tra unita sperimentale e analisi (qui il pozzetto)
    # non rappresenta la correlazione entro la coltura.
    spec_levels = {NodeType.WELL}
    assert _outcome("0.3.0", "GEN-002", spec_levels) is RuleOutcome.FIRED
