"""Cross-asset conformance checks; this module is not a derivation runtime."""

from __future__ import annotations

from enum import StrEnum

from ntruth.derivation_theory.contracts import (
    ConformanceBundle,
    ConformanceFixture,
    FixtureKind,
    ReferenceAvailability,
    V8ConformanceRule,
    V8Rulebook,
)
from ntruth.derivation_theory.loader import canonical_checksum
from ntruth.schemas.kernel import KernelModel, NonBlankStr


class ConformanceFailureCode(StrEnum):
    PIN_MISMATCH = "PIN_MISMATCH"
    CHECKSUM_MISMATCH = "CHECKSUM_MISMATCH"
    RULE_WITHOUT_THEORY_CLAUSE = "RULE_WITHOUT_THEORY_CLAUSE"
    UNIMPLEMENTED_THEORY_CLAUSE = "UNIMPLEMENTED_THEORY_CLAUSE"
    PREDICATE_CONTRACT_MISMATCH = "PREDICATE_CONTRACT_MISMATCH"
    UNCOVERED_DERIVED_OUTPUT = "UNCOVERED_DERIVED_OUTPUT"
    MISSING_FIXTURE_KIND = "MISSING_FIXTURE_KIND"
    NON_DISCRIMINATING_FIXTURE = "NON_DISCRIMINATING_FIXTURE"
    PROOF_TRACE_MISMATCH = "PROOF_TRACE_MISMATCH"
    OPEN_KNOWN_GAP = "OPEN_KNOWN_GAP"
    REFERENCE_ROLE_REUSE = "REFERENCE_ROLE_REUSE"


class ConformanceFailure(KernelModel):
    code: ConformanceFailureCode
    message: NonBlankStr
    clause_id: NonBlankStr | None = None
    rule_id: NonBlankStr | None = None
    fixture_id: NonBlankStr | None = None


class ConformanceReport(KernelModel):
    passed: bool
    failures: tuple[ConformanceFailure, ...]
    covered_clause_ids: tuple[NonBlankStr, ...]
    release_blocker_issue_ids: tuple[NonBlankStr, ...]
    theory_checksum: NonBlankStr
    rulebook_checksum: NonBlankStr
    reference_registry_checksum: NonBlankStr


def fixture_set_checksum(rulebook: V8Rulebook) -> str:
    fixtures = [
        fixture.model_dump(mode="json") for rule in rulebook.rules for fixture in rule.fixtures
    ]
    return canonical_checksum(fixtures)


def _claim_signature(fixture: ConformanceFixture) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (
            claim.claim_type,
            claim.determinability_state.value,
            claim.value.knowledge_state.value,
            canonical_checksum(claim.value.value),
            canonical_checksum(claim.value.conflicting_values),
        )
        for claim in fixture.expected_claims
    )


def _predicate_differences(left: ConformanceFixture, right: ConformanceFixture) -> set[str]:
    keys = set(left.predicate_values) | set(right.predicate_values)
    return {
        key
        for key in keys
        if canonical_checksum(left.predicate_values.get(key))
        != canonical_checksum(right.predicate_values.get(key))
    }


def _check_fixtures(rule: V8ConformanceRule, failures: list[ConformanceFailure]) -> None:
    required_kinds = set(FixtureKind)
    kinds = {fixture.kind for fixture in rule.fixtures}
    if kinds != required_kinds:
        failures.append(
            ConformanceFailure(
                code=ConformanceFailureCode.MISSING_FIXTURE_KIND,
                rule_id=rule.rule_id,
                message="executable rule requires positive, negative and minimal counterfactual",
            )
        )
        return

    positive = next(item for item in rule.fixtures if item.kind is FixtureKind.POSITIVE)
    counterfactual = next(
        item for item in rule.fixtures if item.kind is FixtureKind.MINIMAL_COUNTERFACTUAL
    )
    differences = _predicate_differences(positive, counterfactual)
    if differences != {positive.decisive_predicate_id} or _claim_signature(
        positive
    ) == _claim_signature(counterfactual):
        failures.append(
            ConformanceFailure(
                code=ConformanceFailureCode.NON_DISCRIMINATING_FIXTURE,
                rule_id=rule.rule_id,
                fixture_id=counterfactual.fixture_id,
                message="minimal counterfactual must change only its decisive predicate and claim",
            )
        )

    expected_outputs: set[str] = set()
    required_predicates = {item.predicate_id for item in rule.required_predicates}
    for fixture in rule.fixtures:
        for claim in fixture.expected_claims:
            expected_outputs.add(claim.claim_type)
            traced_predicates = {
                predicate_id for step in claim.proof_trace for predicate_id in step.predicate_ids
            }
            if any(
                step.theory_clause_id != rule.theory_clause_id or step.rule_id != rule.rule_id
                for step in claim.proof_trace
            ) or not required_predicates.issubset(traced_predicates):
                failures.append(
                    ConformanceFailure(
                        code=ConformanceFailureCode.PROOF_TRACE_MISMATCH,
                        rule_id=rule.rule_id,
                        fixture_id=fixture.fixture_id,
                        message="fixture proof must cover required predicates and mapped clause/rule",
                    )
                )
    missing_outputs = set(rule.output_claim_types) - expected_outputs
    if missing_outputs:
        failures.append(
            ConformanceFailure(
                code=ConformanceFailureCode.UNCOVERED_DERIVED_OUTPUT,
                rule_id=rule.rule_id,
                message=f"rule outputs lack fixture claims: {sorted(missing_outputs)}",
            )
        )


def _check_reference_roles(bundle: ConformanceBundle, failures: list[ConformanceFailure]) -> None:
    ownership: dict[tuple[str, str], str] = {}
    for slot in bundle.reference_registry.slots:
        for asset in slot.assets:
            for key in (("asset_id", asset.asset_id), ("checksum", asset.content_checksum)):
                prior = ownership.get(key)
                if prior is not None and prior != slot.role.value:
                    failures.append(
                        ConformanceFailure(
                            code=ConformanceFailureCode.REFERENCE_ROLE_REUSE,
                            message=(
                                f"reference asset identity reused across {prior} and "
                                f"{slot.role.value}"
                            ),
                        )
                    )
                ownership[key] = slot.role.value


def evaluate_conformance(bundle: ConformanceBundle) -> ConformanceReport:
    failures: list[ConformanceFailure] = []
    theory = bundle.theory
    rulebook = bundle.rulebook
    registry = bundle.reference_registry

    if (
        rulebook.theory_id != theory.theory_id
        or rulebook.theory_version != theory.theory_version
        or rulebook.profile_id != theory.profile_id
        or rulebook.profile_version != theory.profile_version
        or rulebook.reference_registry_id != registry.registry_id
        or rulebook.reference_registry_version != registry.registry_version
    ):
        failures.append(
            ConformanceFailure(
                code=ConformanceFailureCode.PIN_MISMATCH,
                message="Rulebook theory/profile/reference version pins do not match the bundle",
            )
        )
    if (
        rulebook.theory_checksum != theory.declared_checksum
        or rulebook.reference_registry_checksum != registry.declared_checksum
        or rulebook.fixture_set_checksum != fixture_set_checksum(rulebook)
    ):
        failures.append(
            ConformanceFailure(
                code=ConformanceFailureCode.CHECKSUM_MISMATCH,
                message="Rulebook semantic checksum pins do not match the bundle",
            )
        )

    clauses = {clause.clause_id: clause for clause in theory.clauses}
    mapped_clause_ids: set[str] = set()
    for rule in rulebook.rules:
        clause = clauses.get(rule.theory_clause_id)
        if clause is None:
            failures.append(
                ConformanceFailure(
                    code=ConformanceFailureCode.RULE_WITHOUT_THEORY_CLAUSE,
                    rule_id=rule.rule_id,
                    message="Rulebook rule references no normative theory clause",
                )
            )
            continue
        mapped_clause_ids.add(clause.clause_id)
        if rule.theory_clause_version != clause.clause_version:
            failures.append(
                ConformanceFailure(
                    code=ConformanceFailureCode.PIN_MISMATCH,
                    clause_id=clause.clause_id,
                    rule_id=rule.rule_id,
                    message="rule clause version differs from the normative theory clause",
                )
            )
        clause_predicates = {item.predicate_id for item in clause.required_predicates}
        rule_predicates = {item.predicate_id for item in rule.required_predicates}
        if rule_predicates != clause_predicates:
            failures.append(
                ConformanceFailure(
                    code=ConformanceFailureCode.PREDICATE_CONTRACT_MISMATCH,
                    clause_id=clause.clause_id,
                    rule_id=rule.rule_id,
                    message="Rulebook cannot add or omit theory-required predicates",
                )
            )
        uncovered = set(rule.output_claim_types) - set(clause.output_claim_types)
        if uncovered:
            failures.append(
                ConformanceFailure(
                    code=ConformanceFailureCode.UNCOVERED_DERIVED_OUTPUT,
                    clause_id=clause.clause_id,
                    rule_id=rule.rule_id,
                    message=f"rule outputs absent from theory clause: {sorted(uncovered)}",
                )
            )
        handled = {item.issue_id for item in rule.known_gap_handling}
        open_gaps = set(rule.known_gap_issue_ids) - handled
        if open_gaps:
            failures.append(
                ConformanceFailure(
                    code=ConformanceFailureCode.OPEN_KNOWN_GAP,
                    clause_id=clause.clause_id,
                    rule_id=rule.rule_id,
                    message=f"known gaps lack fail-closed handling: {sorted(open_gaps)}",
                )
            )
        _check_fixtures(rule, failures)

    for clause in theory.clauses:
        if clause.clause_id not in mapped_clause_ids:
            failures.append(
                ConformanceFailure(
                    code=ConformanceFailureCode.UNIMPLEMENTED_THEORY_CLAUSE,
                    clause_id=clause.clause_id,
                    message="theory clause has no Rulebook conformance mapping",
                )
            )

    _check_reference_roles(bundle, failures)

    blocker_ids = {item.issue_id for item in rulebook.scientific_review_requirements}
    blocker_ids.update(
        slot.review_requirement.issue_id
        for slot in registry.slots
        if slot.availability is ReferenceAvailability.SCIENTIFIC_REVIEW_REQUIRED
        and slot.review_requirement is not None
    )
    blocker_ids.update(issue_id for rule in rulebook.rules for issue_id in rule.known_gap_issue_ids)
    return ConformanceReport(
        passed=not failures,
        failures=tuple(failures),
        covered_clause_ids=tuple(
            clause.clause_id for clause in theory.clauses if clause.clause_id in mapped_clause_ids
        ),
        release_blocker_issue_ids=tuple(sorted(blocker_ids)),
        theory_checksum=theory.declared_checksum,
        rulebook_checksum=rulebook.declared_checksum,
        reference_registry_checksum=registry.declared_checksum,
    )


__all__ = [
    "ConformanceFailure",
    "ConformanceFailureCode",
    "ConformanceReport",
    "evaluate_conformance",
    "fixture_set_checksum",
]
