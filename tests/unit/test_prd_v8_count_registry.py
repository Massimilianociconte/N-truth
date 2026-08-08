"""PRD v8 §§7.9-7.11 and 15.10 canonical count invariants."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from ntruth.schemas.count_registry import (
    CANONICAL_COUNT_REGISTRY_VERSION,
    CanonicalCountKind,
    CanonicalCountRecord,
    CanonicalCountRegistry,
    CountCompatibility,
    CountInterval,
    CountLifecyclePhase,
    CountOrigin,
    CountQuantifier,
    CountScope,
    canonical_count_kind,
    count_compatibility,
    independent_n_presentation_alias,
)
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue


def _present[T](value: T, *, evidence_id: str = "EV-COUNT-01") -> KnowledgeValue[T]:
    return KnowledgeValue[T](
        knowledge_state=KnowledgeState.PRESENT,
        value=value,
        evidence_ids=(evidence_id,),
    )


def _scope(
    *,
    query_id: str = "IQ-001",
    cohort_id: str = "COHORT-01",
    lifecycle_phase: CountLifecyclePhase = CountLifecyclePhase.ANALYZED,
) -> CountScope:
    return CountScope(
        query_id=query_id,
        unit_type=_present("culture"),
        factor_id=_present("treatment"),
        contrast_id=_present("vehicle_vs_drug"),
        group_id=_present("drug"),
        endpoint_id=_present("viability"),
        timepoint_id=_present("T48H"),
        cohort_id=_present(cohort_id),
        lifecycle_phase=_present(lifecycle_phase),
        population_scope=_present("cultures_under_protocol_x"),
        condition=_present("confirmed_independent_cultures"),
    )


def _record(
    *,
    count_id: str,
    kind: CanonicalCountKind = CanonicalCountKind.ANALYZED_UNIT_COUNT,
    value: int | CountInterval = 6,
    quantifier: CountQuantifier = CountQuantifier.EXACT,
    query_id: str = "IQ-001",
    cohort_id: str = "COHORT-01",
    lifecycle_phase: CountLifecyclePhase = CountLifecyclePhase.ANALYZED,
) -> CanonicalCountRecord:
    origin = (
        CountOrigin.RULE_DERIVATION
        if kind is CanonicalCountKind.EXPERIMENTAL_UNIT_COUNT
        else CountOrigin.SOURCE_DECLARATION
    )
    return CanonicalCountRecord(
        count_id=count_id,
        kind=kind,
        value=_present(value),
        quantifier=quantifier,
        scope=_scope(
            query_id=query_id,
            cohort_id=cohort_id,
            lifecycle_phase=lifecycle_phase,
        ),
        source_evidence=("EV-COUNT-01",),
        origin=origin,
        rule_trace=("THEORY-7.2",) if origin is CountOrigin.RULE_DERIVATION else (),
    )


def test_registry_exposes_only_section_7_9_canonical_names() -> None:
    assert CANONICAL_COUNT_REGISTRY_VERSION == "8.0.0"
    assert {kind.value for kind in CanonicalCountKind} == {
        "declared_n",
        "planned_unit_count",
        "allocated_unit_count",
        "treated_unit_count",
        "observed_unit_count",
        "excluded_unit_count",
        "analyzed_unit_count",
        "observational_measurement_count",
        "analytical_row_count",
        "experimental_unit_count",
        "biological_source_count",
        "diagnostic_effective_n",
    }
    with pytest.raises(ValueError, match="non-canonical"):
        canonical_count_kind("planned_n")
    with pytest.raises(ValueError, match="non-canonical"):
        canonical_count_kind("independent_n")


def test_query_and_cohort_are_part_of_count_identity() -> None:
    q1 = _record(count_id="CNT-001", query_id="IQ-001")
    q2 = _record(count_id="CNT-002", query_id="IQ-002")
    c2 = _record(count_id="CNT-003", cohort_id="COHORT-02")
    registry = CanonicalCountRegistry(records=(q1, q2, c2))

    assert q1.semantic_identity() != q2.semantic_identity()
    assert q1.semantic_identity() != c2.semantic_identity()
    assert registry.records_for_query("IQ-001") == (q1, c2)
    assert count_compatibility(q1, q2) is CountCompatibility.NOT_COMPARABLE
    assert count_compatibility(q1, c2) is CountCompatibility.NOT_COMPARABLE


def test_same_scope_collision_is_rejected_not_silently_aggregated() -> None:
    first = _record(count_id="CNT-001", value=5)
    second = _record(count_id="CNT-002", value=6)
    with pytest.raises(ValidationError, match="ConflictRecord"):
        CanonicalCountRegistry(records=(first, second))


def test_biological_source_and_eu_are_distinct_at_equal_numeric_value() -> None:
    eu = _record(
        count_id="CNT-EU",
        kind=CanonicalCountKind.EXPERIMENTAL_UNIT_COUNT,
        value=6,
        lifecycle_phase=CountLifecyclePhase.ANALYZED,
    )
    sources = _record(
        count_id="CNT-SOURCE",
        kind=CanonicalCountKind.BIOLOGICAL_SOURCE_COUNT,
        value=6,
        lifecycle_phase=CountLifecyclePhase.ANALYZED,
    )
    registry = CanonicalCountRegistry(records=(eu, sources))

    assert eu.semantic_identity() != sources.semantic_identity()
    assert len(registry.records) == 2
    assert count_compatibility(eu, sources) is CountCompatibility.NOT_COMPARABLE
    assert independent_n_presentation_alias(eu) == "independent_n"
    with pytest.raises(ValueError, match="experimental_unit_count"):
        independent_n_presentation_alias(sources)


def test_quantified_bounds_are_not_promoted_to_exact() -> None:
    exact_five = _record(count_id="CNT-EXACT", value=5)
    lower_five = _record(
        count_id="CNT-LOWER",
        value=5,
        quantifier=CountQuantifier.LOWER_BOUND,
    )
    range_four_six = _record(
        count_id="CNT-RANGE",
        value=CountInterval(lower=4, upper=6),
        quantifier=CountQuantifier.RANGE,
    )

    assert count_compatibility(exact_five, lower_five) is CountCompatibility.COMPATIBLE
    assert count_compatibility(exact_five, range_four_six) is CountCompatibility.COMPATIBLE
    assert lower_five.quantifier is CountQuantifier.LOWER_BOUND
    assert isinstance(range_four_six.value.value, CountInterval)

    with pytest.raises(ValidationError, match="RANGE"):
        _record(count_id="CNT-BAD", value=5, quantifier=CountQuantifier.RANGE)


def test_silence_is_not_zero() -> None:
    not_reported = KnowledgeValue[int | CountInterval](
        knowledge_state=KnowledgeState.NOT_REPORTED,
        source_scope_ids=("METHODS",),
    )
    count = CanonicalCountRecord(
        count_id="CNT-NR",
        kind=CanonicalCountKind.EXCLUDED_UNIT_COUNT,
        value=not_reported,
        quantifier=CountQuantifier.NOT_REPORTED,
        scope=_scope(lifecycle_phase=CountLifecyclePhase.EXCLUDED),
        source_evidence=("EV-METHODS-REVIEW",),
        origin=CountOrigin.SOURCE_DECLARATION,
    )
    assert count.value.value is None

    with pytest.raises(ValidationError):
        KnowledgeValue[int | CountInterval](
            knowledge_state=KnowledgeState.NOT_REPORTED,
            value=0,
            source_scope_ids=("METHODS",),
        )


@given(left=st.integers(min_value=0, max_value=1000), right=st.integers(0, 1000))
def test_cross_cohort_values_are_never_numeric_conflicts(left: int, right: int) -> None:
    first = _record(count_id="CNT-A", value=left, cohort_id="COHORT-A")
    second = _record(count_id="CNT-B", value=right, cohort_id="COHORT-B")
    assert count_compatibility(first, second) is CountCompatibility.NOT_COMPARABLE
