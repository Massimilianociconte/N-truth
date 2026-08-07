"""Conformance Theory/Rulebook sugli artefatti reali (PRD v8.0 §26.3, §10.9).

Esegue in-process la logica dell'harness ``scripts/conformance_check.py`` e
verifica gli invarianti del contratto theory v8:

- il loader rifiuta regole v8 abilitate senza clausola (RULE_THEORY_MISMATCH);
- il ruleset legacy 0.2.0 resta caricabile senza collegamento theory;
- l'integrita' del registro clausole di ntruth-core-0.3.0;
- l'audit esplicito delle regole disabilitate nel motore;
- la parita' del token di errore con la tassonomia §13.6.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from rule_fixtures.context_factory import _materialize, _scenario

from ntruth.parser_ai.stages import StageErrorCode
from ntruth.rules.engine import apply_rules
from ntruth.rules.loader import (
    RULE_THEORY_MISMATCH,
    RuleTheoryMismatchError,
    declared_theory,
    load_ruleset,
    load_ruleset_file,
)
from ntruth.schemas.rules import Rule, RuleOutcome, Ruleset, TheoryLinkageStatus

ROOT = Path(__file__).resolve().parents[2]

_SPEC = importlib.util.spec_from_file_location(
    "conformance_check", ROOT / "scripts" / "conformance_check.py"
)
assert _SPEC is not None and _SPEC.loader is not None
conformance = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = conformance  # richiesto dai dataclass su Python 3.14
_SPEC.loader.exec_module(conformance)


def _ruleset_v8() -> Ruleset:
    return load_ruleset("ntruth-core", "0.3.0")


def test_loader_refuses_enabled_rule_without_theory_clause(tmp_path: Path) -> None:
    payload = json.loads((ROOT / "rulesets" / "ntruth-core-0.3.0.json").read_text(encoding="utf-8"))
    payload["rules"][0]["theory_clause"] = None  # GEN-001 abilitata senza clausola
    candidate = tmp_path / "broken.json"
    candidate.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RuleTheoryMismatchError) as excinfo:
        load_ruleset_file(candidate)
    assert excinfo.value.code == RULE_THEORY_MISMATCH
    assert excinfo.value.rule_id == "GEN-001"


def test_loader_refuses_orphan_clause_mapping(tmp_path: Path) -> None:
    payload = json.loads((ROOT / "rulesets" / "ntruth-core-0.3.0.json").read_text(encoding="utf-8"))
    payload["rules"][0]["theory_clause"] = "DT-INESISTENTE-99"
    candidate = tmp_path / "orphan.json"
    candidate.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RuleTheoryMismatchError) as excinfo:
        load_ruleset_file(candidate)
    assert excinfo.value.code == RULE_THEORY_MISMATCH
    assert excinfo.value.clause_id == "DT-INESISTENTE-99"


def test_loader_refuses_disabled_rule_without_explicit_srr_mark(tmp_path: Path) -> None:
    payload = json.loads((ROOT / "rulesets" / "ntruth-core-0.3.0.json").read_text(encoding="utf-8"))
    target = next(r for r in payload["rules"] if r["rule_id"] == "GEN-005")
    del target["theory_status"]  # forma fail-closed incompleta
    candidate = tmp_path / "unmarked.json"
    candidate.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RuleTheoryMismatchError):
        load_ruleset_file(candidate)


def test_legacy_ruleset_020_still_loads_without_theory() -> None:
    legacy = load_ruleset("ntruth-core", "0.2.0")
    assert legacy.is_legacy
    assert legacy.theory_version is None
    assert len(legacy.rules) == 32
    assert all(rule.enabled for rule in legacy.rules)
    assert all(rule.theory_clause is None for rule in legacy.rules)
    assert declared_theory(legacy) is None


def test_v8_ruleset_clause_registry_integrity() -> None:
    ruleset = _ruleset_v8()
    theory = declared_theory(ruleset)
    assert theory is not None
    assert ruleset.theory_version == theory.theory_ref
    clause_ids = set(theory.clause_ids())

    mapped = [r for r in ruleset.rules if r.theory_clause is not None]
    disabled = [r for r in ruleset.rules if not r.enabled]
    assert len(ruleset.rules) == 32
    assert len(mapped) == 27
    assert len(disabled) == 5

    for rule in ruleset.rules:
        if rule.enabled:
            # ogni regola eseguibile riferisce una clausola esistente (§10.11)
            assert rule.theory_clause in clause_ids
        else:
            # forma fail-closed esplicita: nessuna clausola, marcatura SRR
            assert rule.theory_clause is None
            assert rule.theory_status is TheoryLinkageStatus.SCIENTIFIC_REVIEW_REQUIRED

    gap_ids = {gap.clause_id for gap in ruleset.theory_coverage_gaps}
    assert gap_ids == {"DT-EXP-02"}
    # le clausole mappate non sono dichiarate uncovered
    assert not gap_ids & {r.theory_clause for r in mapped}


def test_conformance_report_on_real_artifacts_has_no_unmarked_blockers() -> None:
    ruleset = _ruleset_v8()
    theory = declared_theory(ruleset)
    assert theory is not None
    report = conformance.run_conformance(ruleset, theory, repo_root=ROOT)

    assert report.ok(strict=False)
    assert report.unmarked_blockers == ()
    assert not report.ok(strict=True)  # la teoria non e' revisionata (SRR-0003)

    codes = {f.code for f in report.findings}
    assert "RULE_WITHOUT_THEORY_SRR" in codes  # le 5 regole disabilitate
    assert "DECLARED_UNCOVERED_CLAUSE" in codes  # DT-EXP-02
    assert "THEORY_UNREVIEWED" in codes

    # (a) ogni clausola e' coperta da regole oppure dichiarata uncovered
    declared_gaps = {gap.clause_id for gap in ruleset.theory_coverage_gaps}
    for clause_id in theory.clause_ids():
        assert report.clause_rule_map[clause_id] or clause_id in declared_gaps

    # (d) §10.11: nessuna regola abilitata senza teoria
    assert "RULE_WITHOUT_THEORY" not in codes
    assert "RULE_WITHOUT_THEORY_UNMARKED" not in codes


def test_conformance_flags_enabled_rule_without_theory_as_blocker() -> None:
    theory = declared_theory(_ruleset_v8())
    assert theory is not None
    ruleset = Ruleset(
        ruleset_id="synthetic",
        version="9.9.9",
        theory_version=theory.theory_ref,
        rules=(
            Rule(
                rule_id="SYN-001",
                version="1.0.0",
                domain="general",
                inference="regola sintetica senza clausola",
                severity="info",
            ),
        ),
    )
    report = conformance.run_conformance(ruleset, theory, repo_root=ROOT)
    assert not report.ok(strict=False)
    blockers = [f for f in report.unmarked_blockers if f.code == "RULE_WITHOUT_THEORY"]
    assert len(blockers) == 1
    assert "SYN-001" in blockers[0].detail


def test_disabled_rules_are_skipped_with_explicit_audit_record() -> None:
    ruleset = _ruleset_v8()
    gen001 = ruleset.rule("GEN-001")
    assert gen001 is not None
    spec = _scenario(gen001, "positive")
    build, assessment = _materialize(spec)
    result = apply_rules("blk-theory", build, (assessment,), ruleset)

    audits = [e for e in result.evaluations if "rule_disabled" in e.scope_label]
    disabled_ids = {r.rule_id for r in ruleset.rules if not r.enabled}
    assert {e.rule_id for e in audits} == disabled_ids
    assert all(e.outcome is RuleOutcome.NOT_APPLICABLE for e in audits)
    gen005_audit = next(e for e in audits if e.rule_id == "GEN-005")
    assert "rule_disabled:SCIENTIFIC_REVIEW_REQUIRED" in gen005_audit.scope_label
    assert any("GEN-005" in warning and "disabilitata" in warning for warning in result.warnings)


def test_theory_reference_entries_cover_every_clause_with_counterfactual() -> None:
    theory = declared_theory(_ruleset_v8())
    assert theory is not None
    entries = conformance._theory_reference_entries(ROOT)
    for clause in theory.clauses:
        assert clause.clause_id in entries, f"voce mancante per {clause.clause_id}"
        behavior = entries[clause.clause_id].get("expected_behavior", {})
        assert behavior.get("positive"), f"aspettativa positiva mancante per {clause.clause_id}"
        assert behavior.get("negative"), f"aspettativa negativa mancante per {clause.clause_id}"
        assert behavior.get("minimal_counterfactual"), (
            f"counterfactual mancante per {clause.clause_id}"
        )
        # anti-circolarita': la voce dichiara la base normativa PRD, non output del Rulebook
        assert entries[clause.clause_id].get("source_basis")
        # il puntatore minimal_counterfactual della clausola esiste su disco
        pointer = Path(ROOT / clause.minimal_counterfactual)
        assert pointer.is_file(), f"counterfactual pointer assente: {clause.minimal_counterfactual}"


def test_error_taxonomy_token_parity() -> None:
    assert StageErrorCode.RULE_THEORY_MISMATCH.value == RULE_THEORY_MISMATCH
    assert RuleTheoryMismatchError.code == "RULE_THEORY_MISMATCH"
