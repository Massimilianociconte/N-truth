"""Fixture theory-conformant per timing event-referenced (§7.7, Appendice P.4).

Le aspettative derivano SOLO dal testo normativo PRD v8.0 (§7.7, Appendice
P.4, P.5 #12), mai dall'output corrente del Rulebook (regola
anti-circolarita §10.9, tests/THEORY_ASSETS.md).

L'ordine degli eventi e' espresso esclusivamente tramite relazioni ancorate a
event IDs: l'ordine della frase nel testo sorgente non viene mai assunto.
"""

from __future__ import annotations

from ntruth.schemas.core import Provenance
from ntruth.schemas.experiment import Factor
from ntruth.schemas.kernel import EventTiming, TimingRelation

EVIDENCE_ID = "evidence-protocol"
APPLY_EVENT = "EVT-APPLY-01"
SPLIT_EVENT = "EVT-SPLIT-02"
POOL_EVENT = "EVT-POOL-02"


def _provenance() -> Provenance:
    return Provenance(origin="rule", evidence_ids=(EVIDENCE_ID,))


def pool_then_split() -> Factor:
    """P.5 #12: allocazione prima dello split (pool -> split)."""
    return Factor(
        id="factor-pool-then-split",
        name="treatment",
        provenance=_provenance(),
        allocation_event_id=APPLY_EVENT,
        relative_timing=EventTiming(
            subject_event_id=APPLY_EVENT,
            reference_event_id=SPLIT_EVENT,
            relation=TimingRelation.BEFORE,
            evidence_refs=(EVIDENCE_ID,),
        ),
    )


def split_then_pool() -> Factor:
    """P.5 #12: allocazione dopo il pool (split -> pool)."""
    return Factor(
        id="factor-split-then-pool",
        name="treatment",
        provenance=_provenance(),
        allocation_event_id=APPLY_EVENT,
        relative_timing=EventTiming(
            subject_event_id=APPLY_EVENT,
            reference_event_id=POOL_EVENT,
            relation=TimingRelation.AFTER,
            evidence_refs=(EVIDENCE_ID,),
        ),
    )


def legacy_sentence_order() -> Factor:
    """Alias libero deprecato con ordine di frase: mai convertito (§7.7)."""
    return Factor(
        id="factor-legacy-timing",
        name="treatment",
        provenance=_provenance(),
        allocation_event_id=APPLY_EVENT,
        allocation_timing="pool then split",
    )
