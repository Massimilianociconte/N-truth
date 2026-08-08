"""Cross-asset conformance checks; this module is not a derivation runtime."""

from __future__ import annotations

from enum import StrEnum

from ntruth.derivation_theory.contracts import (
    ConformanceBundle,
    ConformanceFixture,
    ConformanceFixtureSet,
    FixtureContentPin,
    FixtureKind,
    FixtureOutcome,
    ReferenceAvailability,
    ReferenceRole,
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
    UNIMPLEMENTED_THEORY_OUTPUT = "UNIMPLEMENTED_THEORY_OUTPUT"
    MISSING_FIXTURE_KIND = "MISSING_FIXTURE_KIND"
    FIXTURE_CARDINALITY_MISMATCH = "FIXTURE_CARDINALITY_MISMATCH"
    FIXTURE_PREDICATE_CONTRACT_MISMATCH = "FIXTURE_PREDICATE_CONTRACT_MISMATCH"
    FIXTURE_KIND_OUTCOME_MISMATCH = "FIXTURE_KIND_OUTCOME_MISMATCH"
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


def fixture_content_pins(rulebook: V8Rulebook) -> tuple[FixtureContentPin, ...]:
    return tuple(
        FixtureContentPin(
            rule_id=rule.rule_id,
            fixture_id=fixture.fixture_id,
            fixture_version=fixture.fixture_version,
            content_checksum=canonical_checksum(fixture),
        )
        for rule in rulebook.rules
        for fixture in rule.fixtures
    )


def fixture_set_checksum(source: V8Rulebook | ConformanceFixtureSet) -> str:
    if isinstance(source, V8Rulebook):
        payload = {
            "schema_version": source.schema_version,
            "fixture_set_id": source.fixture_set_id,
            "fixture_set_version": source.fixture_set_version,
            "role": ReferenceRole.IMPLEMENTATION_CONFORMANCE_FIXTURES.value,
            "fixture_pins": [pin.model_dump(mode="json") for pin in fixture_content_pins(source)],
        }
        return canonical_checksum(payload)
    return canonical_checksum(source, exclude_declared_checksum=True)


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


def _check_fixtures(
    rule: V8ConformanceRule,
    clause_output_claim_types: set[str],
    failures: list[ConformanceFailure],
) -> None:
    fixtures_by_kind = {
        kind: [fixture for fixture in rule.fixtures if fixture.kind is kind] for kind in FixtureKind
    }
    missing_kinds = {kind for kind, fixtures in fixtures_by_kind.items() if not fixtures}
    if missing_kinds:
        failures.append(
            ConformanceFailure(
                code=ConformanceFailureCode.MISSING_FIXTURE_KIND,
                rule_id=rule.rule_id,
                message=f"missing normative fixture kinds: {sorted(item.value for item in missing_kinds)}",
            )
        )
    if len(rule.fixtures) != len(FixtureKind) or any(
        len(fixtures) != 1 for fixtures in fixtures_by_kind.values()
    ):
        failures.append(
            ConformanceFailure(
                code=ConformanceFailureCode.FIXTURE_CARDINALITY_MISMATCH,
                rule_id=rule.rule_id,
                message="v0.x requires exactly one positive, negative and minimal counterfactual",
            )
        )

    required_predicates = {item.predicate_id for item in rule.required_predicates}
    allowed_outputs = set(rule.output_claim_types) & clause_output_claim_types
    expected_outputs: set[str] = set()
    expected_outcome_by_kind = {
        FixtureKind.POSITIVE: FixtureOutcome.DERIVED,
        FixtureKind.NEGATIVE: FixtureOutcome.NOT_APPLICABLE,
        FixtureKind.MINIMAL_COUNTERFACTUAL: FixtureOutcome.DERIVED,
    }
    for fixture in rule.fixtures:
        fixture_predicates = set(fixture.predicate_values)
        missing_predicates = required_predicates - fixture_predicates
        if (
            fixture.decisive_predicate_id not in required_predicates
            or fixture.decisive_predicate_id not in fixture_predicates
            or missing_predicates
        ):
            failures.append(
                ConformanceFailure(
                    code=ConformanceFailureCode.FIXTURE_PREDICATE_CONTRACT_MISMATCH,
                    rule_id=rule.rule_id,
                    fixture_id=fixture.fixture_id,
                    message=(
                        "fixture decisive predicate must be required and every required input "
                        f"must be present; missing={sorted(missing_predicates)}"
                    ),
                )
            )
        expected_outcome = expected_outcome_by_kind[fixture.kind]
        if (
            fixture.expected_outcome is not expected_outcome
            or (expected_outcome is FixtureOutcome.DERIVED and not fixture.expected_claims)
            or (expected_outcome is FixtureOutcome.NOT_APPLICABLE and fixture.expected_claims)
        ):
            failures.append(
                ConformanceFailure(
                    code=ConformanceFailureCode.FIXTURE_KIND_OUTCOME_MISMATCH,
                    rule_id=rule.rule_id,
                    fixture_id=fixture.fixture_id,
                    message="fixture kind, outcome and expected-claim shape are inconsistent",
                )
            )
        for claim in fixture.expected_claims:
            expected_outputs.add(claim.claim_type)
            if claim.claim_type not in allowed_outputs:
                failures.append(
                    ConformanceFailure(
                        code=ConformanceFailureCode.UNCOVERED_DERIVED_OUTPUT,
                        rule_id=rule.rule_id,
                        fixture_id=fixture.fixture_id,
                        message=f"fixture claim is absent from Rulebook/Theory: {claim.claim_type}",
                    )
                )
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

    if all(len(fixtures) == 1 for fixtures in fixtures_by_kind.values()):
        positive = fixtures_by_kind[FixtureKind.POSITIVE][0]
        negative = fixtures_by_kind[FixtureKind.NEGATIVE][0]
        counterfactual = fixtures_by_kind[FixtureKind.MINIMAL_COUNTERFACTUAL][0]
        negative_differences = _predicate_differences(positive, negative)
        if (
            negative.decisive_predicate_id != positive.decisive_predicate_id
            or negative.decisive_predicate_id not in negative_differences
        ):
            failures.append(
                ConformanceFailure(
                    code=ConformanceFailureCode.NON_DISCRIMINATING_FIXTURE,
                    rule_id=rule.rule_id,
                    fixture_id=negative.fixture_id,
                    message="negative fixture must differ on the declared decisive predicate",
                )
            )
        counterfactual_differences = _predicate_differences(positive, counterfactual)
        if (
            counterfactual.decisive_predicate_id != positive.decisive_predicate_id
            or counterfactual_differences != {counterfactual.decisive_predicate_id}
            or _claim_signature(positive) == _claim_signature(counterfactual)
        ):
            failures.append(
                ConformanceFailure(
                    code=ConformanceFailureCode.NON_DISCRIMINATING_FIXTURE,
                    rule_id=rule.rule_id,
                    fixture_id=counterfactual.fixture_id,
                    message="minimal pair must change one decisive predicate and expected claim",
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
    profile = bundle.profile_closure
    registry = bundle.reference_registry
    fixture_set = bundle.fixture_set

    implementation_slots = [
        slot
        for slot in registry.slots
        if slot.role is ReferenceRole.IMPLEMENTATION_CONFORMANCE_FIXTURES
    ]
    fixture_registry_assets = [asset for slot in implementation_slots for asset in slot.assets]
    fixture_registry_asset = (
        fixture_registry_assets[0] if len(fixture_registry_assets) == 1 else None
    )

    if (
        rulebook.theory_id != theory.theory_id
        or rulebook.theory_version != theory.theory_version
        or rulebook.profile_id != theory.profile_id
        or rulebook.profile_version != theory.profile_version
        or profile.profile_id != theory.profile_id
        or profile.profile_version != theory.profile_version
        or rulebook.profile_closure_asset_id != profile.asset_id
        or rulebook.profile_closure_asset_version != profile.asset_version
        or theory.profile_closure_asset_id != profile.asset_id
        or theory.profile_closure_asset_version != profile.asset_version
        or theory.reference_registry_id != registry.registry_id
        or theory.reference_registry_version != registry.registry_version
        or rulebook.reference_registry_id != registry.registry_id
        or rulebook.reference_registry_version != registry.registry_version
        or rulebook.fixture_set_id != fixture_set.fixture_set_id
        or rulebook.fixture_set_version != fixture_set.fixture_set_version
        or fixture_registry_asset is None
        or fixture_registry_asset.asset_id != fixture_set.fixture_set_id
        or fixture_registry_asset.asset_version != fixture_set.fixture_set_version
    ):
        failures.append(
            ConformanceFailure(
                code=ConformanceFailureCode.PIN_MISMATCH,
                message="Theory/profile/Rulebook/reference/fixture identity pins do not match",
            )
        )
    if (
        rulebook.theory_checksum != theory.declared_checksum
        or theory.profile_closure_checksum != profile.declared_checksum
        or rulebook.profile_closure_checksum != profile.declared_checksum
        or rulebook.reference_registry_checksum != registry.declared_checksum
        or rulebook.fixture_set_checksum != fixture_set.declared_checksum
        or fixture_set_checksum(fixture_set) != fixture_set.declared_checksum
        or fixture_set_checksum(rulebook) != fixture_set.declared_checksum
        or fixture_registry_asset is None
        or fixture_registry_asset.content_checksum != fixture_set.declared_checksum
    ):
        failures.append(
            ConformanceFailure(
                code=ConformanceFailureCode.CHECKSUM_MISMATCH,
                message="Theory/profile/Rulebook/reference/fixture checksum pins do not match",
            )
        )

    clauses = {clause.clause_id: clause for clause in theory.clauses}
    theory_predicate_ids = {
        requirement.predicate_id
        for clause in theory.clauses
        for requirement in clause.required_predicates
    }
    missing_profile_predicates = theory_predicate_ids - set(profile.candidate_predicate_ids)
    if missing_profile_predicates:
        failures.append(
            ConformanceFailure(
                code=ConformanceFailureCode.PREDICATE_CONTRACT_MISMATCH,
                message=(
                    "profile candidate closure omits Theory predicates: "
                    f"{sorted(missing_profile_predicates)}"
                ),
            )
        )
    mapped_clause_ids: set[str] = set()
    mapped_outputs: dict[str, set[str]] = {clause_id: set() for clause_id in clauses}
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
        mapped_outputs[clause.clause_id].update(rule.output_claim_types)
        if rule.theory_clause_version != clause.clause_version:
            failures.append(
                ConformanceFailure(
                    code=ConformanceFailureCode.PIN_MISMATCH,
                    clause_id=clause.clause_id,
                    rule_id=rule.rule_id,
                    message="rule clause version differs from the normative theory clause",
                )
            )
        clause_predicates = {
            item.predicate_id: canonical_checksum(item) for item in clause.required_predicates
        }
        rule_predicates = {
            item.predicate_id: canonical_checksum(item) for item in rule.required_predicates
        }
        if rule_predicates != clause_predicates:
            failures.append(
                ConformanceFailure(
                    code=ConformanceFailureCode.PREDICATE_CONTRACT_MISMATCH,
                    clause_id=clause.clause_id,
                    rule_id=rule.rule_id,
                    message="Rulebook required predicate ID/rationale must equal the Theory",
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
        _check_fixtures(rule, set(clause.output_claim_types), failures)

    for clause in theory.clauses:
        if clause.clause_id not in mapped_clause_ids:
            failures.append(
                ConformanceFailure(
                    code=ConformanceFailureCode.UNIMPLEMENTED_THEORY_CLAUSE,
                    clause_id=clause.clause_id,
                    message="theory clause has no Rulebook conformance mapping",
                )
            )
        missing_outputs = set(clause.output_claim_types) - mapped_outputs[clause.clause_id]
        if missing_outputs:
            failures.append(
                ConformanceFailure(
                    code=ConformanceFailureCode.UNIMPLEMENTED_THEORY_OUTPUT,
                    clause_id=clause.clause_id,
                    message=f"theory outputs lack mapped Rulebook rules: {sorted(missing_outputs)}",
                )
            )

    _check_reference_roles(bundle, failures)

    blocker_ids = {item.issue_id for item in rulebook.scientific_review_requirements}
    blocker_ids.add(profile.review_requirement.issue_id)
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
    "fixture_content_pins",
    "fixture_set_checksum",
]
