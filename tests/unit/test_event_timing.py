"""Timing event-referenced (FASE 3 step 6, §7.7, Appendice P.4/P.5 #12).

L'ordine degli eventi e' espresso solo da relazioni ancorate a event IDs:
l'ordine della frase non viene mai assunto e una catena incompleta resta
UNKNOWN (fail-closed).
"""

from __future__ import annotations

import pytest
from rule_fixtures import timing_fixtures

from ntruth.schemas.core import Provenance
from ntruth.schemas.experiment import Factor, legacy_timing_relation
from ntruth.schemas.kernel import EventTiming, TimingRelation

pytestmark = pytest.mark.scientific


def _factor(**kwargs: object) -> Factor:
    payload: dict[str, object] = {
        "id": "factor-timing",
        "name": "treatment",
        "provenance": Provenance(origin="rule"),
    }
    payload.update(kwargs)
    return Factor(**payload)  # type: ignore[arg-type]


def test_typed_relative_timing_wins() -> None:
    """§7.7: il timing tipizzato ancorato a event IDs e' normativo."""
    factor = timing_fixtures.pool_then_split()
    assert factor.timing_relation() is TimingRelation.BEFORE
    timing = factor.event_timing()
    assert timing is not None
    assert timing.reference_event_id == timing_fixtures.SPLIT_EVENT
    assert timing.subject_event_id == timing_fixtures.APPLY_EVENT


def test_pool_then_split_and_split_then_pool_are_distinct() -> None:
    """P.5 #12: i due ordini sono rappresentabili senza ambiguita'."""
    pool_first = timing_fixtures.pool_then_split()
    split_first = timing_fixtures.split_then_pool()
    assert pool_first.timing_relation() is TimingRelation.BEFORE
    assert split_first.timing_relation() is TimingRelation.AFTER
    assert (
        pool_first.event_timing().reference_event_id
        != split_first.event_timing().reference_event_id
    )


def test_sentence_order_is_never_assumed() -> None:
    """La frase 'pool then split' non produce alcuna relazione ordinata."""
    factor = timing_fixtures.legacy_sentence_order()
    assert factor.timing_relation() is TimingRelation.UNKNOWN
    assert factor.event_timing() is None
    assert legacy_timing_relation("pool then split") is None
    assert legacy_timing_relation("split before pool") is None


def test_legacy_alias_converts_only_unambiguous_markers() -> None:
    """Alias deprecato: solo marcatori univoci, case-insensitive."""
    assert legacy_timing_relation("before") is TimingRelation.BEFORE
    assert legacy_timing_relation("  After ") is TimingRelation.AFTER
    assert legacy_timing_relation("SAME EVENT") is TimingRelation.SAME_EVENT
    assert legacy_timing_relation("overlaps") is TimingRelation.OVERLAPS
    assert legacy_timing_relation("unknown") is TimingRelation.UNKNOWN
    assert legacy_timing_relation("day 3 post seeding") is None
    assert legacy_timing_relation(None) is None


def test_incomplete_chain_is_unknown() -> None:
    """Catena incompleta (nessun timing tipizzato) -> UNKNOWN, mai inventata."""
    assert _factor().timing_relation() is TimingRelation.UNKNOWN
    assert _factor(allocation_timing="before").timing_relation() is TimingRelation.BEFORE
    assert _factor(allocation_event_id="EVT-APPLY-01").event_timing() is None


def test_relative_timing_is_additive_and_serializable() -> None:
    """Il campo e' additivo: AE.1, assente dal wire legacy quando non impostato."""
    plain = _factor()
    assert plain.relative_timing is None
    assert "relative_timing" not in plain.model_dump()

    factor = timing_fixtures.split_then_pool()
    dumped = factor.model_dump()
    assert dumped["relative_timing"] is not None
    restored = Factor.model_validate(dumped)
    assert restored.relative_timing == factor.relative_timing
    assert restored.timing_relation() is TimingRelation.AFTER


def test_event_timing_requires_reference_event() -> None:
    """§7.7: nessuna relazione senza evento di riferimento."""
    with pytest.raises(ValueError):
        EventTiming(reference_event_id="  ", relation=TimingRelation.BEFORE)
