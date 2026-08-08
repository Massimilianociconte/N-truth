"""PRD v8 Canonical Count Registry.

The legacy v7 vocabulary remains isolated in :mod:`ntruth.schemas.counts`.
This module accepts only the §7.9 registry and never resolves scientific unit
identity, cohort equivalence or aggregation on the caller's behalf.
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue

CANONICAL_COUNT_REGISTRY_VERSION: Literal["8.0.0"] = "8.0.0"
NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]


class CanonicalCountKind(StrEnum):
    """The sole normative vocabulary from PRD v8 §7.9."""

    DECLARED_N = "declared_n"
    PLANNED_UNIT_COUNT = "planned_unit_count"
    ALLOCATED_UNIT_COUNT = "allocated_unit_count"
    TREATED_UNIT_COUNT = "treated_unit_count"
    OBSERVED_UNIT_COUNT = "observed_unit_count"
    EXCLUDED_UNIT_COUNT = "excluded_unit_count"
    ANALYZED_UNIT_COUNT = "analyzed_unit_count"
    OBSERVATIONAL_MEASUREMENT_COUNT = "observational_measurement_count"
    ANALYTICAL_ROW_COUNT = "analytical_row_count"
    EXPERIMENTAL_UNIT_COUNT = "experimental_unit_count"
    BIOLOGICAL_SOURCE_COUNT = "biological_source_count"
    DIAGNOSTIC_EFFECTIVE_N = "diagnostic_effective_n"


class CountQuantifier(StrEnum):
    EXACT = "EXACT"
    LOWER_BOUND = "LOWER_BOUND"
    UPPER_BOUND = "UPPER_BOUND"
    APPROXIMATE = "APPROXIMATE"
    RANGE = "RANGE"
    UNKNOWN = "UNKNOWN"
    NOT_REPORTED = "NOT_REPORTED"


class CountLifecyclePhase(StrEnum):
    """Closed lifecycle labels; unknown legacy labels require scientific review."""

    PLANNED = "planned"
    ALLOCATED = "allocated"
    TREATED = "treated"
    OBSERVED = "observed"
    EXCLUDED = "excluded"
    ANALYZED = "analyzed"


class CountOrigin(StrEnum):
    SOURCE_DECLARATION = "SOURCE_DECLARATION"
    HUMAN_CONFIRMATION = "HUMAN_CONFIRMATION"
    RULE_DERIVATION = "RULE_DERIVATION"
    MIGRATED_LEGACY = "MIGRATED_LEGACY"


class CountCompatibility(StrEnum):
    COMPATIBLE = "COMPATIBLE"
    CONFLICTING = "CONFLICTING"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class CountInterval(KernelModel):
    lower: NonNegativeInt
    upper: NonNegativeInt

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.lower > self.upper:
            raise ValueError("count interval lower must not exceed upper")
        return self


def _normalized_scope_component[T](
    field_name: str,
    value: KnowledgeValue[T],
) -> tuple[str, KnowledgeState, tuple[str, ...]]:
    normalized_values: tuple[str, ...] = ()
    if value.knowledge_state is KnowledgeState.PRESENT:
        normalized_values = (
            json.dumps(value.value, ensure_ascii=False, sort_keys=True, default=str),
        )
    elif value.knowledge_state is KnowledgeState.CONFLICTING:
        normalized_values = tuple(
            sorted(
                json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
                for item in value.conflicting_values
            )
        )
    return (field_name, value.knowledge_state, normalized_values)


class CountScopeIdentity(KernelModel):
    """Provenance-free scientific identity shared by every count comparison gate."""

    query_id: NonBlankStr
    components: tuple[tuple[NonBlankStr, KnowledgeState, tuple[NonBlankStr, ...]], ...] = Field(
        min_length=10,
        max_length=10,
    )

    @property
    def resolved(self) -> bool:
        return all(state is KnowledgeState.PRESENT for _, state, _ in self.components)

    def key(self) -> tuple[object, ...]:
        return (self.query_id, *self.components)


class CountScope(KernelModel):
    """Explicit query/cohort/lifecycle scope with no bare scientific nulls."""

    query_id: NonBlankStr
    unit_type: KnowledgeValue[NonBlankStr]
    factor_id: KnowledgeValue[NonBlankStr]
    contrast_id: KnowledgeValue[NonBlankStr]
    group_id: KnowledgeValue[NonBlankStr]
    endpoint_id: KnowledgeValue[NonBlankStr]
    timepoint_id: KnowledgeValue[NonBlankStr]
    cohort_id: KnowledgeValue[NonBlankStr]
    lifecycle_phase: KnowledgeValue[CountLifecyclePhase]
    population_scope: KnowledgeValue[NonBlankStr]
    condition: KnowledgeValue[NonBlankStr]

    @model_validator(mode="after")
    def _scope_references_query(self) -> Self:
        for field_name in (
            "unit_type",
            "factor_id",
            "contrast_id",
            "group_id",
            "endpoint_id",
            "timepoint_id",
            "cohort_id",
            "lifecycle_phase",
            "population_scope",
            "condition",
        ):
            value = getattr(self, field_name)
            if value.query_scope_id is not None and value.query_scope_id != self.query_id:
                raise ValueError(f"{field_name}.query_scope_id must match CountScope.query_id")
        return self

    def identity(self) -> CountScopeIdentity:
        """Normalize scientific state/value only; provenance never defines scope."""

        return CountScopeIdentity(
            query_id=self.query_id,
            components=(
                _normalized_scope_component("unit_type", self.unit_type),
                _normalized_scope_component("factor_id", self.factor_id),
                _normalized_scope_component("contrast_id", self.contrast_id),
                _normalized_scope_component("group_id", self.group_id),
                _normalized_scope_component("endpoint_id", self.endpoint_id),
                _normalized_scope_component("timepoint_id", self.timepoint_id),
                _normalized_scope_component("cohort_id", self.cohort_id),
                _normalized_scope_component("lifecycle_phase", self.lifecycle_phase),
                _normalized_scope_component("population_scope", self.population_scope),
                _normalized_scope_component("condition", self.condition),
            ),
        )


class CanonicalCountRecord(KernelModel):
    count_id: NonBlankStr
    registry_version: Literal["8.0.0"] = CANONICAL_COUNT_REGISTRY_VERSION
    kind: CanonicalCountKind
    value: KnowledgeValue[NonNegativeInt | CountInterval]
    quantifier: CountQuantifier
    scope: CountScope
    source_evidence: tuple[NonBlankStr, ...] = Field(min_length=1)
    origin: CountOrigin
    rule_trace: tuple[NonBlankStr, ...] = ()

    @model_validator(mode="after")
    def _quantifier_and_origin_invariants(self) -> Self:
        state = self.value.knowledge_state
        payload = self.value.value
        point_quantifiers = {
            CountQuantifier.EXACT,
            CountQuantifier.LOWER_BOUND,
            CountQuantifier.UPPER_BOUND,
            CountQuantifier.APPROXIMATE,
        }
        if state is KnowledgeState.PRESENT:
            if self.quantifier in point_quantifiers and not isinstance(payload, int):
                raise ValueError(f"{self.quantifier.value} requires a non-negative integer")
            if self.quantifier is CountQuantifier.RANGE and not isinstance(payload, CountInterval):
                raise ValueError("RANGE requires CountInterval")
            if self.quantifier in {CountQuantifier.UNKNOWN, CountQuantifier.NOT_REPORTED}:
                raise ValueError(f"PRESENT count cannot use {self.quantifier.value}")
        elif self.quantifier is CountQuantifier.NOT_REPORTED:
            if state is not KnowledgeState.NOT_REPORTED:
                raise ValueError("NOT_REPORTED quantifier requires NOT_REPORTED KnowledgeState")
        elif self.quantifier is CountQuantifier.UNKNOWN:
            if state is KnowledgeState.NOT_REPORTED:
                raise ValueError("NOT_REPORTED KnowledgeState requires NOT_REPORTED quantifier")
        else:
            raise ValueError(f"{self.quantifier.value} requires PRESENT KnowledgeState")

        if self.origin is CountOrigin.RULE_DERIVATION and not self.rule_trace:
            raise ValueError("RULE_DERIVATION requires rule_trace")

        if (
            self.value.query_scope_id is not None
            and self.value.query_scope_id != self.scope.query_id
        ):
            raise ValueError("value.query_scope_id must match scope.query_id")

        expected_lifecycle_phase = {
            CanonicalCountKind.PLANNED_UNIT_COUNT: CountLifecyclePhase.PLANNED,
            CanonicalCountKind.ALLOCATED_UNIT_COUNT: CountLifecyclePhase.ALLOCATED,
            CanonicalCountKind.TREATED_UNIT_COUNT: CountLifecyclePhase.TREATED,
            CanonicalCountKind.OBSERVED_UNIT_COUNT: CountLifecyclePhase.OBSERVED,
            CanonicalCountKind.EXCLUDED_UNIT_COUNT: CountLifecyclePhase.EXCLUDED,
            CanonicalCountKind.ANALYZED_UNIT_COUNT: CountLifecyclePhase.ANALYZED,
        }.get(self.kind)
        lifecycle_phase = self.scope.lifecycle_phase
        if (
            expected_lifecycle_phase is not None
            and lifecycle_phase.knowledge_state is KnowledgeState.PRESENT
            and lifecycle_phase.value is not expected_lifecycle_phase
        ):
            raise ValueError(
                f"{self.kind.value} requires lifecycle_phase={expected_lifecycle_phase.value}"
            )
        return self

    def semantic_identity(self) -> tuple[object, ...] | None:
        identity = self.scope.identity()
        if not identity.resolved:
            return None
        return (self.kind.value, *identity.key())

    def comparison_identity(self) -> tuple[object, ...] | None:
        return self.semantic_identity()


class CanonicalCountRegistry(KernelModel):
    registry_version: Literal["8.0.0"] = CANONICAL_COUNT_REGISTRY_VERSION
    records: tuple[CanonicalCountRecord, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _no_silent_collisions(self) -> Self:
        seen_ids: set[str] = set()
        seen_identities: set[tuple[object, ...]] = set()
        for record in self.records:
            if record.count_id in seen_ids:
                raise ValueError(f"duplicate count_id: {record.count_id}")
            seen_ids.add(record.count_id)
            identity = record.semantic_identity()
            if identity is None:
                raise ValueError(
                    "SCIENTIFIC_REVIEW_REQUIRED: unresolved decisive count scope cannot "
                    "enter collision comparison"
                )
            if identity in seen_identities:
                raise ValueError(
                    "same-scope count collision requires an explicit ConflictRecord; "
                    "records are never silently aggregated"
                )
            seen_identities.add(identity)
        return self

    def records_for_query(self, query_id: str) -> tuple[CanonicalCountRecord, ...]:
        return tuple(record for record in self.records if record.scope.query_id == query_id)


def canonical_count_kind(raw: str) -> CanonicalCountKind:
    """Accept exact §7.9 values only; legacy spelling belongs in migrations."""

    try:
        return CanonicalCountKind(raw)
    except ValueError as error:
        raise ValueError(f"non-canonical PRD v8 count kind: {raw!r}") from error


def independent_n_presentation_alias(record: CanonicalCountRecord) -> str:
    """Expose the deprecated report label in the permitted one-way direction."""

    if record.kind is not CanonicalCountKind.EXPERIMENTAL_UNIT_COUNT:
        raise ValueError("independent_n may present only experimental_unit_count")
    return "independent_n"


def _present_payload(
    record: CanonicalCountRecord,
) -> NonNegativeInt | CountInterval | None:
    if record.value.knowledge_state is not KnowledgeState.PRESENT:
        return None
    return record.value.value


def count_compatibility(
    left: CanonicalCountRecord,
    right: CanonicalCountRecord,
) -> CountCompatibility:
    """Apply only the explicit Appendix P.2 numeric cases within identical scope."""

    left_identity = left.comparison_identity()
    right_identity = right.comparison_identity()
    if left_identity is None or right_identity is None:
        return CountCompatibility.REVIEW_REQUIRED
    if left_identity != right_identity:
        return CountCompatibility.NOT_COMPARABLE

    left_value = _present_payload(left)
    right_value = _present_payload(right)
    if left_value is None or right_value is None:
        return CountCompatibility.REVIEW_REQUIRED
    if CountQuantifier.APPROXIMATE in {left.quantifier, right.quantifier}:
        return CountCompatibility.REVIEW_REQUIRED

    if left.quantifier is CountQuantifier.EXACT and right.quantifier is CountQuantifier.EXACT:
        return (
            CountCompatibility.COMPATIBLE
            if left_value == right_value
            else CountCompatibility.CONFLICTING
        )

    exact: int | None = None
    other_value: NonNegativeInt | CountInterval | None = None
    other_quantifier: CountQuantifier | None = None
    if left.quantifier is CountQuantifier.EXACT and isinstance(left_value, int):
        exact, other_value, other_quantifier = left_value, right_value, right.quantifier
    elif right.quantifier is CountQuantifier.EXACT and isinstance(right_value, int):
        exact, other_value, other_quantifier = right_value, left_value, left.quantifier
    if exact is not None:
        compatible = False
        if other_quantifier is CountQuantifier.LOWER_BOUND and isinstance(other_value, int):
            compatible = exact >= other_value
        elif other_quantifier is CountQuantifier.UPPER_BOUND and isinstance(other_value, int):
            compatible = exact <= other_value
        elif other_quantifier is CountQuantifier.RANGE and isinstance(other_value, CountInterval):
            compatible = other_value.lower <= exact <= other_value.upper
        else:
            return CountCompatibility.REVIEW_REQUIRED
        return CountCompatibility.COMPATIBLE if compatible else CountCompatibility.CONFLICTING

    if (
        left.quantifier is CountQuantifier.RANGE
        and right.quantifier is CountQuantifier.RANGE
        and isinstance(left_value, CountInterval)
        and isinstance(right_value, CountInterval)
    ):
        overlaps = max(left_value.lower, right_value.lower) <= min(
            left_value.upper, right_value.upper
        )
        return CountCompatibility.COMPATIBLE if overlaps else CountCompatibility.CONFLICTING

    return CountCompatibility.REVIEW_REQUIRED


__all__ = [
    "CANONICAL_COUNT_REGISTRY_VERSION",
    "CanonicalCountKind",
    "CanonicalCountRecord",
    "CanonicalCountRegistry",
    "CountCompatibility",
    "CountInterval",
    "CountLifecyclePhase",
    "CountOrigin",
    "CountQuantifier",
    "CountScope",
    "CountScopeIdentity",
    "canonical_count_kind",
    "count_compatibility",
    "independent_n_presentation_alias",
]
