"""Scope-aware counts and relation registry (PRD v7 §7.9, §8.5)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ntruth.schemas.counts import (
    COUNT_KIND_ALIASES,
    CountKind,
    CountOrigin,
    CountRecord,
    Quantifier,
    canonical_count_kind,
    require_scope_for_multi_scope_bundle,
)
from ntruth.schemas.relations import V7Relation, canonical_relation, registry_checksum


def test_analysed_alias_to_analyzed() -> None:
    assert canonical_count_kind("analysed") is CountKind.N_ANALYZED
    assert canonical_count_kind("n_analysed") is CountKind.N_ANALYZED
    assert "analysed" in COUNT_KIND_ALIASES


def test_parser_cannot_emit_independent_n() -> None:
    with pytest.raises(ValidationError):
        CountRecord(
            id="c1",
            kind=CountKind.INDEPENDENT_N,
            value=6,
            quantifier=Quantifier.EXACT,
            origin=CountOrigin.ANNOTATION_CANDIDATE,
        )


def test_rule_engine_may_emit_independent_n() -> None:
    rec = CountRecord(
        id="c1",
        kind=CountKind.INDEPENDENT_N,
        value=6,
        unit_type="culture",
        factor_id="treatment",
        endpoint_id="viability",
        quantifier=Quantifier.EXACT,
        origin=CountOrigin.RULE_DERIVATION,
        rule_trace=("MIC-001",),
    )
    assert rec.kind is CountKind.INDEPENDENT_N


def test_effective_n_diagnostic_only() -> None:
    with pytest.raises(ValidationError):
        CountRecord(
            id="c2",
            kind=CountKind.EFFECTIVE_N,
            value=4,
            quantifier=Quantifier.EXACT,
            origin=CountOrigin.RULE_DERIVATION,
            condition=None,
        )
    ok = CountRecord(
        id="c2",
        kind=CountKind.EFFECTIVE_N,
        value=4,
        quantifier=Quantifier.EXACT,
        origin=CountOrigin.RULE_DERIVATION,
        condition="diagnostic only - does not repair design replication",
    )
    assert ok.kind is CountKind.EFFECTIVE_N


def test_multi_factor_requires_scope() -> None:
    counts = (
        CountRecord(
            id="c",
            kind=CountKind.DECLARED_N,
            value=3,
            quantifier=Quantifier.EXACT,
            origin=CountOrigin.DECLARED_IN_SOURCE,
        ),
    )
    with pytest.raises(ValueError, match="factor_id"):
        require_scope_for_multi_scope_bundle(
            counts, multi_factor=True, multi_endpoint=False, multi_timepoint=False
        )


def test_acquired_from_in_registry() -> None:
    assert canonical_relation("acquired_from") is V7Relation.ACQUIRED_FROM
    assert registry_checksum()
