"""Semantic verifier runtime: indipendente, fail-closed, non override hard."""

from __future__ import annotations

from ntruth.schemas.core import (
    Determinability,
    EvidenceSpan,
    EvidenceType,
    Provenance,
    ProvenanceKind,
)
from ntruth.schemas.experiment import (
    Contrast,
    CountKind,
    CountQuantifier,
    CountRecord,
    CountScope,
    Endpoint,
    ExperimentBlock,
    Factor,
    Hierarchy,
    LifecycleStatus,
    TriState,
    Versions,
)
from ntruth.schemas.graph import NodeType
from ntruth.verifier.semantic import (
    SemanticBackend,
    SemanticStatus,
    verify_semantic,
)


def _prov(origin: ProvenanceKind = ProvenanceKind.USER) -> Provenance:
    return Provenance(origin=origin, actor_role="annotator")


def _versions() -> Versions:
    return Versions(
        schema_version="0.3.0",
        parser_version="0.3.0",
        graph_version="0.3.0",
        ruleset_id="ntruth-core",
        ruleset_version="0.2.0",
    )


def _span(
    span_id: str,
    *,
    etype: EvidenceType,
    text: str = "three independent wells",
) -> EvidenceSpan:
    return EvidenceSpan(
        id=span_id,
        file_id="methods.md",
        section_id="methods",
        section_title="Methods",
        start=0,
        end=max(1, len(text)),
        text=text,
        parser_version="test",
        evidence_type=etype,
    )


def _scope(lifecycle: LifecycleStatus) -> CountScope:
    return CountScope(
        unit_type=NodeType.WELL,
        factor_id="factor-treatment",
        contrast_id="contrast-drug-vehicle",
        group_or_level="drug",
        endpoint_id="endpoint-viability",
        timepoint=None,
        lifecycle=lifecycle,
        population="cell cultures in the declared assay",
        condition="drug",
        unknown_reasons={"timepoint": "not applicable to this endpoint"},
    )


def _design() -> tuple[Factor, Contrast, Endpoint]:
    factor = Factor(
        id="factor-treatment",
        name="treatment",
        levels=("drug", "vehicle"),
        allocation_level=NodeType.WELL,
        independently_assigned=TriState.UNKNOWN,
        provenance=_prov(),
    )
    endpoint = Endpoint(
        id="endpoint-viability",
        name="viability",
        measured_on=NodeType.WELL,
        provenance=_prov(),
    )
    contrast = Contrast(
        id="contrast-drug-vehicle",
        label="drug vs vehicle",
        factor_ids=(factor.id,),
        endpoint_ids=(endpoint.id,),
        compared_levels=("drug", "vehicle"),
        provenance=_prov(),
    )
    return factor, contrast, endpoint


def _block(
    *,
    factors: tuple[Factor, ...] | None = None,
    contrasts: tuple[Contrast, ...] = (),
    endpoints: tuple[Endpoint, ...] = (),
    evidence: tuple[EvidenceSpan, ...] = (),
    counts: tuple[CountRecord, ...] = (),
    determinability: Determinability = Determinability.INSUFFICIENT_INFORMATION,
) -> ExperimentBlock:
    if factors is None:
        factor, contrast, endpoint = _design()
        factors = (factor,)
        contrasts = (contrast,)
        endpoints = (endpoint,)
    return ExperimentBlock(
        id="blk-semantic-1",
        title="Semantic fixture",
        document_id="doc-1",
        source_file_ids=("methods.md",),
        factors=factors,
        contrasts=contrasts,
        endpoints=endpoints,
        count_records=counts,
        evidence=evidence,
        hierarchy=Hierarchy(nodes=(), relations=()),
        determinability=determinability,
        versions=_versions(),
    )


def test_author_assertion_alone_fails_decisive_independence() -> None:
    evidence = (_span("ev-1", etype=EvidenceType.AUTHOR_ASSERTION),)
    factor = Factor(
        id="factor-treatment",
        name="treatment",
        levels=("vehicle", "drug"),
        independently_assigned=TriState.TRUE,
        independence_mechanism="Each well assigned from randomisation list",
        independence_evidence_ids=("ev-1",),
        provenance=Provenance(origin=ProvenanceKind.EXPLICIT, parser_version="test"),
    )
    _, contrast, endpoint = _design()
    result = verify_semantic(
        _block(
            factors=(factor,),
            contrasts=(contrast,),
            endpoints=(endpoint,),
            evidence=evidence,
        )
    )
    assert result.backend is SemanticBackend.ALGORITHMIC_V1
    assert result.status is SemanticStatus.FAIL
    assert "author_assertion_alone_insufficient" in result.blocking_failure_codes
    assert result.can_override_hard_invalid is False


def test_structural_evidence_supports_independence() -> None:
    evidence = (_span("ev-2", etype=EvidenceType.STRUCTURAL_FACT),)
    factor = Factor(
        id="factor-treatment",
        name="treatment",
        levels=("vehicle", "drug"),
        independently_assigned=TriState.TRUE,
        independence_mechanism="Each well assigned from randomisation list",
        independence_evidence_ids=("ev-2",),
        provenance=Provenance(origin=ProvenanceKind.EXPLICIT, parser_version="test"),
    )
    _, contrast, endpoint = _design()
    result = verify_semantic(
        _block(
            factors=(factor,),
            contrasts=(contrast,),
            endpoints=(endpoint,),
            evidence=evidence,
        )
    )
    assert result.passed
    assert result.status is SemanticStatus.PASS


def test_numeric_lifecycle_order_blocking() -> None:
    evidence = (_span("ev-num", etype=EvidenceType.STRUCTURAL_FACT, text="n planned 4"),)
    prov = Provenance(
        origin=ProvenanceKind.EXPLICIT,
        evidence_ids=("ev-num",),
        parser_version="test",
    )
    counts = (
        CountRecord(
            count_id="c-planned",
            kind=CountKind.PLANNED_N,
            value=4,
            quantifier=CountQuantifier.EXACT,
            scope=_scope(LifecycleStatus.PLANNED),
            evidence_ids=("ev-num",),
            provenance=prov,
        ),
        CountRecord(
            count_id="c-alloc",
            kind=CountKind.ALLOCATED_N,
            value=10,
            quantifier=CountQuantifier.EXACT,
            scope=_scope(LifecycleStatus.ALLOCATED),
            evidence_ids=("ev-num",),
            provenance=prov,
        ),
    )
    result = verify_semantic(_block(counts=counts, evidence=evidence))
    assert result.status is SemanticStatus.FAIL
    assert "numeric_lifecycle_order" in result.blocking_failure_codes


def test_model_provisional_backend_fail_closed() -> None:
    result = verify_semantic(_block(), backend=SemanticBackend.MODEL_PROVISIONAL)
    assert result.status is SemanticStatus.FAIL
    assert result.scientifically_validated_backend is False
    assert "model_semantic_backend_not_configured" in result.blocking_failure_codes


def test_source_grounding_detects_missing_excerpt() -> None:
    evidence = (_span("ev-g", etype=EvidenceType.STRUCTURAL_FACT, text="unique-token-xyz"),)
    result = verify_semantic(
        _block(evidence=evidence),
        source_texts={"methods.md": "Methods without the token."},
    )
    assert any(
        item.code == "evidence_span_not_in_source" for item in result.checks if not item.passed
    )
