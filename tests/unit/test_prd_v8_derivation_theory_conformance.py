"""PRD v8 Derivation Theory and Rulebook conformance boundaries."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import ModuleType

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[2]


def _module(name: str) -> ModuleType:
    """Turn a missing Task 3 API into an assertion failure during the RED cycle."""

    try:
        return importlib.import_module(name)
    except ModuleNotFoundError:
        pytest.fail(f"Task 3 API is missing: {name}")


def _contracts() -> ModuleType:
    return _module("ntruth.derivation_theory.contracts")


def _loader() -> ModuleType:
    return _module("ntruth.derivation_theory.loader")


def _harness() -> ModuleType:
    return _module("ntruth.conformance.harness")


def _bundle() -> object:
    return _loader().load_canonical_bundle(ROOT)


def _failure_codes(report: object) -> set[str]:
    return {failure.code.value for failure in report.failures}


def _replace_rule(bundle: object, rule_id: str, **updates: object) -> object:
    rules = list(bundle.rulebook.rules)
    index = next(index for index, rule in enumerate(rules) if rule.rule_id == rule_id)
    rules[index] = rules[index].model_copy(update=updates)
    rulebook = bundle.rulebook.model_copy(update={"rules": tuple(rules)})
    return bundle.model_copy(update={"rulebook": rulebook})


def test_canonical_v8_bundle_conforms_without_promoting_missing_scientific_assets() -> None:
    """Catches a malformed A-G asset or a blocked reference set being called reviewed."""

    bundle = _bundle()
    report = _harness().evaluate_conformance(bundle)

    assert report.passed
    assert {clause.letter.value for clause in bundle.theory.clauses} == set("ABCDEFG")
    assert report.covered_clause_ids == tuple(clause.clause_id for clause in bundle.theory.clauses)
    assert set(report.release_blocker_issue_ids) >= {
        "SRR-V8-012",
        "SRR-V8-014",
        "SRR-V8-017",
        "SRR-V8-021",
        "SRR-V8-023",
        "SRR-V8-024",
    }

    slots = {slot.role.value: slot for slot in bundle.reference_registry.slots}
    assert slots["IMPLEMENTATION_CONFORMANCE_FIXTURES"].availability.value == "AVAILABLE"
    assert slots["THEORY_REFERENCE_SET"].availability.value == "SCIENTIFIC_REVIEW_REQUIRED"
    assert slots["DERIVATION_GOLD"].availability.value == "SCIENTIFIC_REVIEW_REQUIRED"


def test_rule_without_theory_clause_fails_conformance() -> None:
    """Catches a Rulebook entry becoming its own source of scientific theory."""

    bundle = _bundle()
    mutated = _replace_rule(bundle, "V8-A-ASSIGNMENT-UNIT", theory_clause_id="DT-Z-MISSING")

    report = _harness().evaluate_conformance(mutated)

    assert "RULE_WITHOUT_THEORY_CLAUSE" in _failure_codes(report)


def test_rule_output_not_declared_by_theory_clause_fails_conformance() -> None:
    """Catches the implementation inventing a claim absent from its theory clause."""

    bundle = _bundle()
    rule = next(rule for rule in bundle.rulebook.rules if rule.rule_id == "V8-A-ASSIGNMENT-UNIT")
    mutated = _replace_rule(
        bundle,
        rule.rule_id,
        output_claim_types=(*rule.output_claim_types, "UNREVIEWED_SCIENTIFIC_CLAIM"),
    )

    report = _harness().evaluate_conformance(mutated)

    assert "UNCOVERED_DERIVED_OUTPUT" in _failure_codes(report)


def test_minimal_counterfactual_must_discriminate_the_decisive_predicate() -> None:
    """Catches a nominal counterfactual that changes neither one predicate nor the claim."""

    bundle = _bundle()
    rule = next(rule for rule in bundle.rulebook.rules if rule.rule_id == "V8-A-ASSIGNMENT-UNIT")
    positive = next(fixture for fixture in rule.fixtures if fixture.kind.value == "POSITIVE")
    counterfactual = next(
        fixture for fixture in rule.fixtures if fixture.kind.value == "MINIMAL_COUNTERFACTUAL"
    )
    replacement = counterfactual.model_copy(
        update={
            "predicate_values": positive.predicate_values,
            "expected_claims": positive.expected_claims,
        }
    )
    fixtures = tuple(
        replacement if item.fixture_id == replacement.fixture_id else item for item in rule.fixtures
    )
    mutated = _replace_rule(bundle, rule.rule_id, fixtures=fixtures)

    report = _harness().evaluate_conformance(mutated)

    assert "NON_DISCRIMINATING_FIXTURE" in _failure_codes(report)


def test_executable_rule_rejects_irrelevant_predicate_without_rationale() -> None:
    """Catches a dimension being silently omitted from claim-specific proof obligations."""

    contracts = _contracts()
    bundle = _bundle()
    rule = bundle.rulebook.rules[0]
    payload = rule.model_dump(mode="json")
    payload["irrelevant_predicates"][0]["rationale"] = ""

    with pytest.raises(ValidationError, match="rationale"):
        contracts.V8ConformanceRule.model_validate(payload)


def test_reference_asset_cannot_be_reused_as_conformance_fixture_and_gold() -> None:
    """Catches engineering expectations being promoted to scientific gold by relabeling."""

    bundle = _bundle()
    slots = list(bundle.reference_registry.slots)
    conformance = next(
        slot for slot in slots if slot.role.value == "IMPLEMENTATION_CONFORMANCE_FIXTURES"
    )
    gold_index = next(
        index for index, slot in enumerate(slots) if slot.role.value == "DERIVATION_GOLD"
    )
    slots[gold_index] = slots[gold_index].model_copy(
        update={
            "availability": _contracts().ReferenceAvailability.AVAILABLE,
            "assets": conformance.assets,
            "review_requirement": None,
        }
    )
    registry = bundle.reference_registry.model_copy(update={"slots": tuple(slots)})
    mutated = bundle.model_copy(update={"reference_registry": registry})

    report = _harness().evaluate_conformance(mutated)

    assert "REFERENCE_ROLE_REUSE" in _failure_codes(report)


def test_open_known_gap_without_fail_closed_handling_fails_conformance() -> None:
    """Catches an unresolved topology or policy gap becoming executable by omission."""

    bundle = _bundle()
    rule = next(rule for rule in bundle.rulebook.rules if rule.rule_id == "V8-E-INTERFERENCE")
    assert "SRR-V8-017" in rule.known_gap_issue_ids
    mutated = _replace_rule(bundle, rule.rule_id, known_gap_handling=())

    report = _harness().evaluate_conformance(mutated)

    assert "OPEN_KNOWN_GAP" in _failure_codes(report)


def test_executable_rule_requires_positive_negative_and_minimal_counterfactual() -> None:
    """Catches a rule mapping that cannot be falsified or sensitivity-checked."""

    bundle = _bundle()
    rule = bundle.rulebook.rules[0]
    mutated = _replace_rule(
        bundle,
        rule.rule_id,
        fixtures=tuple(
            fixture for fixture in rule.fixtures if fixture.kind.value != "MINIMAL_COUNTERFACTUAL"
        ),
    )

    report = _harness().evaluate_conformance(mutated)

    assert "MISSING_FIXTURE_KIND" in _failure_codes(report)


def test_fixture_proof_trace_must_name_mapped_clause_and_rule() -> None:
    """Catches an expected claim whose proof cannot be joined to its executable mapping."""

    bundle = _bundle()
    rule = bundle.rulebook.rules[0]
    positive = next(fixture for fixture in rule.fixtures if fixture.kind.value == "POSITIVE")
    claim = positive.expected_claims[0]
    proof = claim.proof_trace[0].model_copy(update={"rule_id": "V8-OTHER-RULE"})
    changed_claim = claim.model_copy(update={"proof_trace": (proof,)})
    changed_fixture = positive.model_copy(update={"expected_claims": (changed_claim,)})
    fixtures = tuple(
        changed_fixture if item.fixture_id == positive.fixture_id else item
        for item in rule.fixtures
    )
    mutated = _replace_rule(bundle, rule.rule_id, fixtures=fixtures)

    report = _harness().evaluate_conformance(mutated)

    assert "PROOF_TRACE_MISMATCH" in _failure_codes(report)


def test_asset_checksums_are_deterministic_and_tampering_fails_closed(tmp_path: Path) -> None:
    """Catches unpinned theory content loading under a trusted version."""

    loader = _loader()
    first = _bundle()
    second = _bundle()
    assert first.theory.declared_checksum == second.theory.declared_checksum
    assert first.rulebook.declared_checksum == second.rulebook.declared_checksum
    assert first.reference_registry.declared_checksum == second.reference_registry.declared_checksum
    assert all(
        len(checksum) == 64
        for checksum in (
            first.theory.declared_checksum,
            first.rulebook.declared_checksum,
            first.reference_registry.declared_checksum,
        )
    )

    source = ROOT / "theories" / "ntruth-derivation-theory-0.1.0.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["clauses"][0]["title"] = "tampered"
    target = tmp_path / source.name
    target.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(loader.AssetChecksumError, match="checksum"):
        loader.load_derivation_theory_file(target)


def test_rulebook_pins_theory_profile_reference_registry_and_fixture_checksums() -> None:
    """Catches a ruleset being evaluated against a different theory/profile/reference snapshot."""

    bundle = _bundle()
    rulebook = bundle.rulebook

    assert rulebook.theory_id == bundle.theory.theory_id
    assert rulebook.theory_version == bundle.theory.theory_version
    assert rulebook.theory_checksum == bundle.theory.declared_checksum
    assert rulebook.profile_id == bundle.theory.profile_id
    assert rulebook.profile_version == bundle.theory.profile_version
    assert rulebook.reference_registry_id == bundle.reference_registry.registry_id
    assert rulebook.reference_registry_version == bundle.reference_registry.registry_version
    assert rulebook.reference_registry_checksum == bundle.reference_registry.declared_checksum
    assert rulebook.fixture_set_checksum == _harness().fixture_set_checksum(rulebook)
