"""Regression: euristica allocato/analizzato scoped per tipo e origin deterministico.

Copre due difetti storici del builder:
1. l'euristica "due totali + esclusioni = n allocato/n analizzato" era attivata
   da un flag globale al blocco: un'esclusione di tipo diverso (o senza tipo)
   sopprimeva la contraddizione e fabbricava un ``n`` arbitrario;
2. l'origine aggregata era scelta iterando un set di StrEnum con hash
   randomizzato per processo (violazione NFR-02).
"""

from __future__ import annotations

import pytest

from ntruth.extract.facts import EntityFact, ExtractionResult, ProcessFact
from ntruth.graph.builder import _aggregate_origin, build_graph
from ntruth.schemas.core import EvidenceSpan, ProvenanceKind
from ntruth.schemas.graph import NodeType


def _evidence(span_id: str) -> EvidenceSpan:
    return EvidenceSpan(
        id=span_id,
        file_id="doc-1",
        start=0,
        end=10,
        text="24 colture preparate, 12 analizzate",
    )


def _extraction(
    *entities: EntityFact,
    processes: tuple[ProcessFact, ...] = (),
) -> ExtractionResult:
    return ExtractionResult(
        entities=list(entities),
        processes=list(processes),
    )


def _count_fact(
    count: int,
    *,
    origin: ProvenanceKind = ProvenanceKind.EXPLICIT,
    label: str = "colture",
) -> EntityFact:
    return EntityFact(
        node_type=NodeType.CELL_CULTURE,
        label=label,
        count=count,
        evidence=_evidence(f"ev-{label}-{count}"),
        origin=origin,
    )


def _exclusion(
    node_type: NodeType | None,
    *,
    value: int | None = None,
) -> ProcessFact:
    return ProcessFact(kind="exclusion", node_type=node_type, value=value)


def test_conflicting_totals_with_untyped_exclusion_stay_contradiction() -> None:
    result = build_graph(
        "blk",
        _extraction(
            _count_fact(24),
            _count_fact(12),
            processes=(_exclusion(None, value=12),),
        ),
    )

    assert result.contradictions, "totali conflittuali devono restare una contraddizione"
    node = result.hierarchy.nodes_of(NodeType.CELL_CULTURE)[0]
    assert node.count is None
    assert "n_allocated" not in node.attributes
    assert "n_analyzed" not in node.attributes


def test_conflicting_totals_with_other_typed_exclusion_stay_contradiction() -> None:
    result = build_graph(
        "blk",
        _extraction(
            _count_fact(24),
            _count_fact(12),
            _count_fact(24, label="animali"),
            processes=(_exclusion(NodeType.ANIMAL, value=3),),
        ),
    )

    assert result.contradictions
    node = result.hierarchy.nodes_of(NodeType.CELL_CULTURE)[0]
    assert node.count is None


def test_conflicting_totals_with_same_typed_exclusion_resolve_allocated_analysed() -> None:
    result = build_graph(
        "blk",
        _extraction(
            _count_fact(24),
            _count_fact(12),
            processes=(_exclusion(NodeType.CELL_CULTURE, value=12),),
        ),
    )

    assert not result.contradictions
    node = result.hierarchy.nodes_of(NodeType.CELL_CULTURE)[0]
    assert node.count == 12
    assert node.attributes["n_allocated"] == 24
    assert node.attributes["n_analyzed"] == 12


@pytest.mark.parametrize("seed", range(8))
def test_mixed_origins_aggregate_deterministically(seed: int) -> None:
    facts = [
        _count_fact(24, origin=ProvenanceKind.MODEL),
        _count_fact(24, origin=ProvenanceKind.EXPLICIT),
    ]
    results = [build_graph(f"blk-{seed}-{run}", _extraction(*facts)) for run in range(2)]

    origins = {
        result.hierarchy.nodes_of(NodeType.CELL_CULTURE)[0].provenance.origin for result in results
    }
    assert origins == {ProvenanceKind.EXPLICIT}


def test_aggregate_origin_priority_is_total() -> None:
    assert _aggregate_origin(set()) is ProvenanceKind.DERIVED
    assert _aggregate_origin({ProvenanceKind.TABULAR, ProvenanceKind.MODEL}) is (
        ProvenanceKind.TABULAR
    )
    assert (
        _aggregate_origin({ProvenanceKind.MODEL, ProvenanceKind.EXPLICIT})
        is ProvenanceKind.EXPLICIT
    )


def test_declared_n_group_matching_is_case_insensitive() -> None:
    from ntruth.graph.units import _declared_n
    from ntruth.schemas.experiment import (
        NKind,
        NScope,
        NStatement,
    )
    from ntruth.schemas.experiment import Provenance as ExpProvenance

    provenance = ExpProvenance(origin=ProvenanceKind.USER, actor_role="researcher")
    statement = NStatement(
        id="n-wt",
        value=12,
        entity_type="cultures",
        scope=NScope(group="WT"),
        kind=NKind.DECLARED,
        provenance=provenance,
    )

    value, matched = _declared_n(
        (statement,),
        NScope(group="wt"),
        NodeType.CELL_CULTURE,
        allow_scope_fallback=False,
    )

    assert value == 12
    assert matched is statement


def test_malformed_predicate_arity_is_unevaluable_not_crash() -> None:
    import pytest as _pytest
    from rule_fixtures.context_factory import _materialize, _Spec

    from ntruth.graph.index import GraphIndex
    from ntruth.rules.predicates import RuleContext, UnknownPredicate, evaluate

    build, assessment = _materialize(_Spec(counts={NodeType.CELL_CULTURE: 12}))
    context = RuleContext(
        index=GraphIndex(build.hierarchy),
        build=build,
        assessment=assessment,
        factor=None,
        contrast=None,
        endpoint=None,
    )

    with _pytest.raises(UnknownPredicate):
        evaluate("level_present()", context)
