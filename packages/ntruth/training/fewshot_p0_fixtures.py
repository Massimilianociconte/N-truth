"""Fixture canoniche P0 per baseline few-shot Granite (CandidateGraphSet v6).

- Sintetiche controllate + parafrasi realistiche da UC scientifici (solo testo Methods).
- Non usate per addestrare il rules engine.
- Gold e ``CandidateGraphSet`` candidate-only: nessun verdetto, nessun n finale.
- Split: ``demo`` (few-shot examples), ``eval`` (valutazione).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, Literal

from ntruth.parser_ai.contract import (
    CandidateEdge,
    CandidateEndpoint,
    CandidateExperimentBlock,
    CandidateFactor,
    CandidateNode,
    NodeOntologyValue,
    ParserAIDocumentInput,
    ParserAIEvidenceSpan,
    ParserAIInput,
    ParserAISectionInput,
    RelationOntologyValue,
)
from ntruth.parser_ai.stages import (
    CandidateCountRecord,
    CandidateGraphSet,
    ChunkCoverageRecord,
    MissingFactRecord,
    StageAuthority,
    StageName,
    StageProvenance,
    StageStatus,
    validate_candidate_graph_pair,
)
from ntruth.schemas.core import EvidenceType
from ntruth.schemas.experiment import CountKind, CountQuantifier, LifecycleStatus
from ntruth.schemas.graph import NodeType, RelationType

FixtureKind = Literal[
    "empty_incomplete",
    "evidence_only",
    "entity_count",
    "factor_endpoint",
    "explicit_relation",
    "candidate_graph",
    "contradiction",
    "realistic",
]

TASK_TAGS = (
    "TASK_EVIDENCE",
    "TASK_ENTITY_COUNT",
    "TASK_FACTOR_ENDPOINT",
    "TASK_EXPLICIT_RELATIONS",
    "TASK_CANDIDATE_GRAPH",
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _span(
    *,
    evidence_id: str,
    file_id: str,
    text: str,
    full: str,
    evidence_type: EvidenceType = EvidenceType.AUTHOR_ASSERTION,
    section_id: str = "sec-methods",
    confidence: float = 0.9,
) -> ParserAIEvidenceSpan:
    start = full.index(text)
    end = start + len(text)
    return ParserAIEvidenceSpan(
        evidence_id=evidence_id,
        file_id=file_id,
        evidence_type=evidence_type,
        text=text,
        confidence=confidence,
        section_id=section_id,
        start=start,
        end=end,
    )


def _document(file_id: str, filename: str, text: str) -> ParserAIDocumentInput:
    return ParserAIDocumentInput(
        file_id=file_id,
        filename=filename,
        sha256=_sha(text),
        text=text,
        sections=(
            ParserAISectionInput(
                section_id="sec-methods",
                role="methods",
                title="Methods",
                start=0,
                end=len(text),
                text=text,
            ),
        ),
    )


def _input(text: str, *, case_id: str, domain: str = "fewshot_p0_synthetic") -> ParserAIInput:
    file_id = f"file-{case_id}"
    return ParserAIInput(
        documents=(_document(file_id, f"{case_id}.md", text),),
        metadata={"case_id": case_id, "suite": "fewshot_p0"},
        domain_hint=domain,
        language="en",
    )


def _provenance(case_id: str) -> StageProvenance:
    return StageProvenance(
        stage_run_id=f"stage-{case_id}",
        stage=StageName.CANDIDATE_GRAPH_SET,
        authority=StageAuthority.MODEL,
        producer="ntruth-fewshot-p0-gold",
        producer_version="1.0.0",
    )


def _empty_graph(case_id: str, *, file_id: str | None = None) -> CandidateGraphSet:
    coverage: tuple[ChunkCoverageRecord, ...] = ()
    if file_id is not None:
        coverage = (
            ChunkCoverageRecord(
                file_id=file_id,
                total_chunks=1,
                processed_chunks=(0,),
                failed_chunks=(),
            ),
        )
    return CandidateGraphSet(
        result_id=f"result-{case_id}",
        stage=StageName.CANDIDATE_GRAPH_SET,
        status=StageStatus.COMPLETE,
        provenance=_provenance(case_id),
        graph_set_id=f"graph-{case_id}",
        chunk_coverage=coverage,
    )


def _node_type(value: NodeType) -> NodeOntologyValue:
    return NodeOntologyValue(value=value)


def _rel(value: RelationType) -> RelationOntologyValue:
    return RelationOntologyValue(value=value)


def _case(
    *,
    case_id: str,
    kind: FixtureKind,
    tasks: Sequence[str],
    text: str,
    gold: CandidateGraphSet,
    split: Literal["demo", "eval"],
    notes: str = "",
    domain: str = "fewshot_p0_synthetic",
) -> dict[str, Any]:
    parser_input = _input(text, case_id=case_id, domain=domain)
    gold = validate_candidate_graph_pair(parser_input, gold)
    return {
        "case_id": case_id,
        "split": split,
        "kind": kind,
        "tasks": list(tasks),
        "notes": notes,
        "parser_input": parser_input.model_dump(mode="json"),
        "gold": gold.model_dump(mode="json"),
        "source_text": text,
    }


# ---------------------------------------------------------------------------
# Builders for families
# ---------------------------------------------------------------------------


def _family_empty() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    templates = [
        ("empty-01", "No experimental methods are described.", "eval"),
        ("empty-02", "Supplementary material contains only figure layouts.", "eval"),
        ("empty-03", "Abstract only; methods section missing.", "eval"),
        ("empty-demo", "This document has no countable experimental units.", "demo"),
    ]
    for case_id, text, split in templates:
        gold = _empty_graph(case_id, file_id=f"file-{case_id}")
        # incomplete: no inventable facts; empty arrays + full chunk coverage.
        cases.append(
            _case(
                case_id=case_id,
                kind="empty_incomplete",
                tasks=["TASK_CANDIDATE_GRAPH", "TASK_EVIDENCE"],
                text=text,
                gold=gold,
                split=split,  # type: ignore[arg-type]
                notes="Empty source: empty CandidateGraphSet is correct; do not invent facts.",
            )
        )
    return cases


def _family_evidence_entity() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    specs = [
        (
            "ev-ent-01",
            "eval",
            "Mice were housed in standard cages. Primary cultures were prepared from cortex.",
            "Mice were housed in standard cages.",
            "Primary cultures were prepared from cortex.",
            NodeType.ANIMAL,
            "Mice",
            NodeType.PRIMARY_CULTURE,
            "Primary cultures",
        ),
        (
            "ev-ent-02",
            "eval",
            "Human donors provided blood samples. Cells were cultured in plates.",
            "Human donors provided blood samples.",
            "Cells were cultured in plates.",
            NodeType.HUMAN_DONOR,
            "Human donors",
            NodeType.CELL,
            "Cells",
        ),
        (
            "ev-ent-03",
            "eval",
            "Organoids were derived from iPSC lines and imaged on day 14.",
            "Organoids were derived from iPSC lines",
            "imaged on day 14",
            NodeType.ORGANOID,
            "Organoids",
            NodeType.CELL_LINE,
            "iPSC lines",
        ),
        (
            "ev-ent-04",
            "eval",
            "Wells received treatment A or B. Plates were incubated for 24 h.",
            "Wells received treatment A or B.",
            "Plates were incubated for 24 h.",
            NodeType.WELL,
            "Wells",
            NodeType.PLATE,
            "Plates",
        ),
        (
            "ev-ent-demo",
            "demo",
            "Animals were allocated to diet groups. Tissue samples were collected at sacrifice.",
            "Animals were allocated to diet groups.",
            "Tissue samples were collected at sacrifice.",
            NodeType.ANIMAL,
            "Animals",
            NodeType.TISSUE,
            "Tissue samples",
        ),
        (
            "ev-ent-05",
            "eval",
            "Batches of medium were prepared weekly. Aliquots were stored at -80 C.",
            "Batches of medium were prepared weekly.",
            "Aliquots were stored at -80 C.",
            NodeType.BATCH,
            "Batches",
            NodeType.ALIQUOT,
            "Aliquots",
        ),
    ]
    for (
        case_id,
        split,
        text,
        span_a,
        span_b,
        type_a,
        label_a,
        type_b,
        label_b,
    ) in specs:
        file_id = f"file-{case_id}"
        e1 = _span(evidence_id=f"ev-{case_id}-a", file_id=file_id, text=span_a, full=text)
        e2 = _span(evidence_id=f"ev-{case_id}-b", file_id=file_id, text=span_b, full=text)
        block = CandidateExperimentBlock(
            block_id=f"block-{case_id}",
            title="Main experiment",
            evidence_ids=(e1.evidence_id,),
            confidence=0.85,
        )
        n1 = CandidateNode(
            node_id=f"node-{case_id}-a",
            block_id=block.block_id,
            node_type=_node_type(type_a),
            label=label_a,
            evidence_ids=(e1.evidence_id,),
            confidence=0.88,
        )
        n2 = CandidateNode(
            node_id=f"node-{case_id}-b",
            block_id=block.block_id,
            node_type=_node_type(type_b),
            label=label_b,
            evidence_ids=(e2.evidence_id,),
            confidence=0.86,
        )
        gold = CandidateGraphSet(
            result_id=f"result-{case_id}",
            stage=StageName.CANDIDATE_GRAPH_SET,
            status=StageStatus.COMPLETE,
            provenance=_provenance(case_id),
            graph_set_id=f"graph-{case_id}",
            experiment_blocks=(block,),
            evidence_spans=(e1, e2),
            candidate_nodes=(n1, n2),
            chunk_coverage=(
                ChunkCoverageRecord(
                    file_id=file_id, total_chunks=1, processed_chunks=(0,), failed_chunks=()
                ),
            ),
        )
        cases.append(
            _case(
                case_id=case_id,
                kind="entity_count" if "count" in case_id else "evidence_only",
                tasks=["TASK_EVIDENCE", "TASK_ENTITY_COUNT"],
                text=text,
                gold=gold,
                split=split,  # type: ignore[arg-type]
            )
        )
    return cases


def _family_counts() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    specs = [
        (
            "count-01",
            "eval",
            "Five independent donors contributed PBMCs (n = 5 donors).",
            "Five independent donors",
            5,
            NodeType.HUMAN_DONOR,
            "donors",
        ),
        (
            "count-02",
            "eval",
            "A total of 12 animals were used in the study (n = 12).",
            "12 animals were used",
            12,
            NodeType.ANIMAL,
            "animals",
        ),
        (
            "count-03",
            "eval",
            "Approximately 200 cells were imaged per well.",
            "Approximately 200 cells were imaged per well.",
            200,
            NodeType.CELL,
            "cells",
            CountQuantifier.APPROXIMATE,
        ),
        (
            "count-04",
            "eval",
            "Between 8 and 10 cages were assigned per diet arm.",
            "Between 8 and 10 cages",
            None,
            NodeType.CAGE,
            "cages",
            CountQuantifier.RANGE,
            8,
            10,
        ),
        (
            "count-demo",
            "demo",
            "Three biological replicates were analysed (n = 3).",
            "Three biological replicates",
            3,
            NodeType.PRIMARY_SAMPLE,
            "biological replicates",
        ),
        (
            "count-05",
            "eval",
            "n was not reported for technical replicates.",
            "n was not reported for technical replicates.",
            None,
            NodeType.CELL,
            "technical replicates",
            CountQuantifier.NOT_REPORTED,
        ),
    ]
    for spec in specs:
        case_id = spec[0]
        split = spec[1]
        text = spec[2]
        span = spec[3]
        value = spec[4]
        unit = spec[5]
        label = spec[6]
        quant = spec[7] if len(spec) > 7 else CountQuantifier.EXACT
        lo = spec[8] if len(spec) > 8 else None
        hi = spec[9] if len(spec) > 9 else None
        file_id = f"file-{case_id}"
        e1 = _span(evidence_id=f"ev-{case_id}", file_id=file_id, text=span, full=text)
        block = CandidateExperimentBlock(
            block_id=f"block-{case_id}",
            title="Counting experiment",
            evidence_ids=(e1.evidence_id,),
            confidence=0.9,
        )
        node = CandidateNode(
            node_id=f"node-{case_id}",
            block_id=block.block_id,
            node_type=_node_type(unit),
            label=label,
            evidence_ids=(e1.evidence_id,),
            confidence=0.9,
        )
        count_kwargs: dict[str, Any] = {
            "count_id": f"count-{case_id}",
            "block_id": block.block_id,
            "kind": CountKind.DECLARED_N,
            "quantifier": quant,
            "unit_type": _node_type(unit),
            "evidence_ids": (e1.evidence_id,),
            "confidence": 0.9,
            "population_scope": label,
        }
        if quant is CountQuantifier.EXACT or quant is CountQuantifier.APPROXIMATE:
            count_kwargs["value"] = value
        elif quant is CountQuantifier.RANGE:
            count_kwargs["lower_bound"] = lo
            count_kwargs["upper_bound"] = hi
        # NOT_REPORTED: no numeric values
        count = CandidateCountRecord(**count_kwargs)
        gold = CandidateGraphSet(
            result_id=f"result-{case_id}",
            stage=StageName.CANDIDATE_GRAPH_SET,
            status=StageStatus.COMPLETE,
            provenance=_provenance(case_id),
            graph_set_id=f"graph-{case_id}",
            experiment_blocks=(block,),
            evidence_spans=(e1,),
            candidate_nodes=(node,),
            counts=(count,),
            chunk_coverage=(
                ChunkCoverageRecord(
                    file_id=file_id, total_chunks=1, processed_chunks=(0,), failed_chunks=()
                ),
            ),
        )
        cases.append(
            _case(
                case_id=case_id,
                kind="entity_count",
                tasks=["TASK_ENTITY_COUNT", "TASK_EVIDENCE"],
                text=text,
                gold=gold,
                split=split,  # type: ignore[arg-type]
            )
        )
    return cases


def _family_factor_endpoint_relations() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    specs = [
        (
            "fac-01",
            "eval",
            "Treatment (LPS or vehicle) was applied to wells. Intensity was the primary endpoint.",
            "Treatment (LPS or vehicle)",
            "Intensity was the primary endpoint",
            "treatment",
            ("LPS", "vehicle"),
            "Intensity",
            NodeType.WELL,
        ),
        (
            "fac-02",
            "eval",
            "Diet (high-fat vs control) was assigned to cages. Body weight was recorded.",
            "Diet (high-fat vs control)",
            "Body weight was recorded",
            "diet",
            ("high-fat", "control"),
            "Body weight",
            NodeType.CAGE,
        ),
        (
            "fac-03",
            "eval",
            "Drug dose (0, 1, 10 uM) was applied to cell cultures. Viability was measured.",
            "Drug dose (0, 1, 10 uM)",
            "Viability was measured",
            "drug_dose",
            ("0 uM", "1 uM", "10 uM"),
            "Viability",
            NodeType.CELL_CULTURE,
        ),
        (
            "fac-demo",
            "demo",
            "Genotype (WT or KO) was defined at the animal level. Latency was the endpoint.",
            "Genotype (WT or KO)",
            "Latency was the endpoint",
            "genotype",
            ("WT", "KO"),
            "Latency",
            NodeType.ANIMAL,
        ),
        (
            "fac-04",
            "eval",
            "Stimulus intensity (low/high) was delivered per ROI. Spike rate was quantified.",
            "Stimulus intensity (low/high)",
            "Spike rate was quantified",
            "stimulus_intensity",
            ("low", "high"),
            "Spike rate",
            NodeType.ROI,
        ),
    ]
    for (
        case_id,
        split,
        text,
        span_f,
        span_e,
        fname,
        levels,
        ename,
        alloc,
    ) in specs:
        file_id = f"file-{case_id}"
        ef = _span(evidence_id=f"ev-{case_id}-f", file_id=file_id, text=span_f, full=text)
        ee = _span(evidence_id=f"ev-{case_id}-e", file_id=file_id, text=span_e, full=text)
        block = CandidateExperimentBlock(
            block_id=f"block-{case_id}",
            title="Factor endpoint block",
            evidence_ids=(ef.evidence_id, ee.evidence_id),
            confidence=0.9,
        )
        factor = CandidateFactor(
            factor_id=f"factor-{case_id}",
            block_id=block.block_id,
            name=fname,
            levels=levels,
            allocation_level=_node_type(alloc),
            application_level=_node_type(alloc),
            evidence_ids=(ef.evidence_id,),
            confidence=0.9,
        )
        endpoint = CandidateEndpoint(
            endpoint_id=f"endpoint-{case_id}",
            block_id=block.block_id,
            name=ename,
            evidence_ids=(ee.evidence_id,),
            confidence=0.9,
        )
        gold = CandidateGraphSet(
            result_id=f"result-{case_id}",
            stage=StageName.CANDIDATE_GRAPH_SET,
            status=StageStatus.COMPLETE,
            provenance=_provenance(case_id),
            graph_set_id=f"graph-{case_id}",
            experiment_blocks=(block,),
            evidence_spans=(ef, ee),
            factors=(factor,),
            endpoints=(endpoint,),
            chunk_coverage=(
                ChunkCoverageRecord(
                    file_id=file_id, total_chunks=1, processed_chunks=(0,), failed_chunks=()
                ),
            ),
        )
        cases.append(
            _case(
                case_id=case_id,
                kind="factor_endpoint",
                tasks=["TASK_FACTOR_ENDPOINT", "TASK_EVIDENCE"],
                text=text,
                gold=gold,
                split=split,  # type: ignore[arg-type]
            )
        )

    # Explicit nested_in / derived_from
    rel_specs = [
        (
            "rel-01",
            "eval",
            "Cells were nested in wells; wells were nested in plates.",
            "Cells were nested in wells",
            "wells were nested in plates",
            NodeType.CELL,
            "Cells",
            NodeType.WELL,
            "wells",
            RelationType.NESTED_IN,
        ),
        (
            "rel-02",
            "eval",
            "Images were derived from wells after staining.",
            "Images were derived from wells after staining.",
            "Images were derived from wells after staining.",
            NodeType.IMAGE,
            "Images",
            NodeType.WELL,
            "wells",
            RelationType.DERIVED_FROM,
        ),
        (
            "rel-demo",
            "demo",
            "Aliquots were nested in batches of medium.",
            "Aliquots were nested in batches of medium.",
            "Aliquots were nested in batches of medium.",
            NodeType.ALIQUOT,
            "Aliquots",
            NodeType.BATCH,
            "batches",
            RelationType.NESTED_IN,
        ),
        (
            "rel-03",
            "eval",
            "ROIs were nested in images acquired from organoids.",
            "ROIs were nested in images",
            "images acquired from organoids",
            NodeType.ROI,
            "ROIs",
            NodeType.IMAGE,
            "images",
            RelationType.NESTED_IN,
        ),
        (
            "rel-04",
            "eval",
            "Libraries were derived from primary samples.",
            "Libraries were derived from primary samples.",
            "Libraries were derived from primary samples.",
            NodeType.LIBRARY,
            "Libraries",
            NodeType.PRIMARY_SAMPLE,
            "primary samples",
            RelationType.DERIVED_FROM,
        ),
    ]
    for (
        case_id,
        split,
        text,
        span_a,
        span_b,
        type_a,
        label_a,
        type_b,
        label_b,
        rel,
    ) in rel_specs:
        file_id = f"file-{case_id}"
        # same span ok if identical text
        ea = _span(evidence_id=f"ev-{case_id}-a", file_id=file_id, text=span_a, full=text)
        if span_b != span_a:
            eb = _span(evidence_id=f"ev-{case_id}-b", file_id=file_id, text=span_b, full=text)
            spans = (ea, eb)
            edge_ev = (ea.evidence_id, eb.evidence_id)
        else:
            spans = (ea,)
            edge_ev = (ea.evidence_id,)
        block = CandidateExperimentBlock(
            block_id=f"block-{case_id}",
            title="Relation block",
            evidence_ids=(ea.evidence_id,),
            confidence=0.88,
        )
        n_src = CandidateNode(
            node_id=f"node-{case_id}-src",
            block_id=block.block_id,
            node_type=_node_type(type_a),
            label=label_a,
            evidence_ids=(ea.evidence_id,),
            confidence=0.88,
        )
        n_tgt = CandidateNode(
            node_id=f"node-{case_id}-tgt",
            block_id=block.block_id,
            node_type=_node_type(type_b),
            label=label_b,
            evidence_ids=(spans[-1].evidence_id,),
            confidence=0.88,
        )
        edge = CandidateEdge(
            edge_id=f"edge-{case_id}",
            block_id=block.block_id,
            source_id=n_src.node_id,
            target_id=n_tgt.node_id,
            relation_type=_rel(rel),
            evidence_ids=edge_ev,
            confidence=0.87,
        )
        gold = CandidateGraphSet(
            result_id=f"result-{case_id}",
            stage=StageName.CANDIDATE_GRAPH_SET,
            status=StageStatus.COMPLETE,
            provenance=_provenance(case_id),
            graph_set_id=f"graph-{case_id}",
            experiment_blocks=(block,),
            evidence_spans=spans,
            candidate_nodes=(n_src, n_tgt),
            candidate_edges=(edge,),
            chunk_coverage=(
                ChunkCoverageRecord(
                    file_id=file_id, total_chunks=1, processed_chunks=(0,), failed_chunks=()
                ),
            ),
        )
        cases.append(
            _case(
                case_id=case_id,
                kind="explicit_relation",
                tasks=["TASK_EXPLICIT_RELATIONS", "TASK_ENTITY_COUNT"],
                text=text,
                gold=gold,
                split=split,  # type: ignore[arg-type]
            )
        )
    return cases


def _family_full_graph_and_contradiction() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    # Complete small graph
    full_specs = [
        (
            "graph-01",
            "eval",
            (
                "Five donors provided cells. Treatment (LPS or vehicle) was applied at the donor level. "
                "Cells nested in donors were analysed. Marker intensity was quantified."
            ),
        ),
        (
            "graph-02",
            "eval",
            (
                "Twelve animals were housed in cages. Diet (high-fat or control) was assigned to cages. "
                "Animals nested in cages were weighed. Body weight was the endpoint."
            ),
        ),
        (
            "graph-demo",
            "demo",
            (
                "Eight wells on a plate received drug A or B. Cells nested in wells were imaged. "
                "Viability was the primary endpoint (n = 8 wells)."
            ),
        ),
        (
            "graph-03",
            "eval",
            (
                "Three batches of organoids were derived from one cell line. "
                "Stimulus (low/high) was applied per organoid. Spike rate was measured."
            ),
        ),
    ]
    for case_id, split, text in full_specs:
        file_id = f"file-{case_id}"
        # pick three non-overlapping spans
        parts = [s.strip() for s in text.replace(". ", ".|").split("|") if s.strip()]
        spans = []
        for i, part in enumerate(parts[:3]):
            snippet = part if part.endswith(".") else part
            # ensure substring exists
            if snippet not in text:
                snippet = text[: min(40, len(text))]
            spans.append(
                _span(
                    evidence_id=f"ev-{case_id}-{i}",
                    file_id=file_id,
                    text=snippet[: max(10, min(len(snippet), 80))],
                    full=text,
                )
            )
        e0, e1, e2 = spans[0], spans[1], spans[2] if len(spans) > 2 else spans[1]
        block = CandidateExperimentBlock(
            block_id=f"block-{case_id}",
            title="Full candidate graph",
            evidence_ids=(e0.evidence_id,),
            confidence=0.9,
        )
        n_parent = CandidateNode(
            node_id=f"node-{case_id}-parent",
            block_id=block.block_id,
            node_type=_node_type(NodeType.HUMAN_DONOR if "donor" in text.lower() else NodeType.ANIMAL),
            label="primary units",
            evidence_ids=(e0.evidence_id,),
            confidence=0.88,
        )
        n_child = CandidateNode(
            node_id=f"node-{case_id}-child",
            block_id=block.block_id,
            node_type=_node_type(NodeType.CELL if "cell" in text.lower() else NodeType.ANIMAL),
            label="nested units",
            evidence_ids=(e1.evidence_id,),
            confidence=0.86,
        )
        edge = CandidateEdge(
            edge_id=f"edge-{case_id}",
            block_id=block.block_id,
            source_id=n_child.node_id,
            target_id=n_parent.node_id,
            relation_type=_rel(RelationType.NESTED_IN),
            evidence_ids=(e1.evidence_id,),
            confidence=0.85,
        )
        factor = CandidateFactor(
            factor_id=f"factor-{case_id}",
            block_id=block.block_id,
            name="treatment_or_diet",
            levels=("level_a", "level_b"),
            allocation_level=n_parent.node_type,
            application_level=n_parent.node_type,
            evidence_ids=(e1.evidence_id,),
            confidence=0.84,
        )
        endpoint = CandidateEndpoint(
            endpoint_id=f"endpoint-{case_id}",
            block_id=block.block_id,
            name="primary_endpoint",
            evidence_ids=(e2.evidence_id,),
            confidence=0.84,
        )
        gold = CandidateGraphSet(
            result_id=f"result-{case_id}",
            stage=StageName.CANDIDATE_GRAPH_SET,
            status=StageStatus.COMPLETE,
            provenance=_provenance(case_id),
            graph_set_id=f"graph-{case_id}",
            experiment_blocks=(block,),
            evidence_spans=tuple(spans),
            candidate_nodes=(n_parent, n_child),
            candidate_edges=(edge,),
            factors=(factor,),
            endpoints=(endpoint,),
            chunk_coverage=(
                ChunkCoverageRecord(
                    file_id=file_id, total_chunks=1, processed_chunks=(0,), failed_chunks=()
                ),
            ),
        )
        cases.append(
            _case(
                case_id=case_id,
                kind="candidate_graph",
                tasks=["TASK_CANDIDATE_GRAPH", "TASK_FACTOR_ENDPOINT", "TASK_EXPLICIT_RELATIONS"],
                text=text,
                gold=gold,
                split=split,  # type: ignore[arg-type]
            )
        )

    # Contradiction / conflict: two conflicting n statements → evidence + missing definitive count
    conflict_specs = [
        (
            "conf-01",
            "eval",
            "The methods state n = 6 animals. The figure legend states n = 8 animals.",
            "n = 6 animals",
            "n = 8 animals",
        ),
        (
            "conf-02",
            "eval",
            "Text reports 10 donors. The sample sheet lists 9 donors.",
            "10 donors",
            "9 donors",
        ),
        (
            "conf-03",
            "eval",
            "Caption claims n = 4 wells; methods claim n = 12 wells.",
            "n = 4 wells",
            "n = 12 wells",
        ),
        (
            "conf-demo",
            "demo",
            "Abstract reports 20 mice; methods report 18 mice.",
            "20 mice",
            "18 mice",
        ),
    ]
    for case_id, split, text, s1, s2 in conflict_specs:
        file_id = f"file-{case_id}"
        e1 = _span(
            evidence_id=f"ev-{case_id}-a",
            file_id=file_id,
            text=s1,
            full=text,
            evidence_type=EvidenceType.CONFLICTING_EVIDENCE,
        )
        e2 = _span(
            evidence_id=f"ev-{case_id}-b",
            file_id=file_id,
            text=s2,
            full=text,
            evidence_type=EvidenceType.CONFLICTING_EVIDENCE,
        )
        block = CandidateExperimentBlock(
            block_id=f"block-{case_id}",
            title="Conflict block",
            evidence_ids=(e1.evidence_id, e2.evidence_id),
            confidence=0.7,
        )
        missing = MissingFactRecord(
            missing_fact_id=f"miss-{case_id}",
            block_id=block.block_id,
            predicate="declared_n_consensus",
            reason="Conflicting numeric claims; no single candidate count without resolution.",
            evidence_ids=(e1.evidence_id, e2.evidence_id),
        )
        gold = CandidateGraphSet(
            result_id=f"result-{case_id}",
            stage=StageName.CANDIDATE_GRAPH_SET,
            status=StageStatus.COMPLETE,
            provenance=_provenance(case_id),
            graph_set_id=f"graph-{case_id}",
            experiment_blocks=(block,),
            evidence_spans=(e1, e2),
            missing_facts=(missing,),
            chunk_coverage=(
                ChunkCoverageRecord(
                    file_id=file_id, total_chunks=1, processed_chunks=(0,), failed_chunks=()
                ),
            ),
        )
        cases.append(
            _case(
                case_id=case_id,
                kind="contradiction",
                tasks=["TASK_EVIDENCE", "TASK_CANDIDATE_GRAPH"],
                text=text,
                gold=gold,
                split=split,  # type: ignore[arg-type]
                notes="Do not resolve conflict into a single n; record evidence and missing consensus.",
            )
        )
    return cases


def _family_realistic() -> list[dict[str, Any]]:
    """Parafrasi realistiche basate su UC scientifici (solo testo; gold candidate minimale)."""

    realistic_texts = [
        (
            "real-01",
            "eval",
            (
                "Peripheral blood mononuclear cells were obtained from five independent donors. "
                "Cells were treated with LPS or vehicle at the donor level for 6 h. "
                "Marker intensity per cell was quantified by flow cytometry."
            ),
            "five independent donors",
            NodeType.HUMAN_DONOR,
            "donors",
            5,
        ),
        (
            "real-02",
            "eval",
            (
                "Primary neuronal cultures were prepared from E18 cortices. "
                "Cultures were exposed to vehicle or compound X for 24 h. "
                "Synaptic puncta density was measured in 20 fields per culture."
            ),
            "20 fields per culture",
            NodeType.FIELD,
            "fields",
            20,
        ),
        (
            "real-03",
            "eval",
            (
                "Male C57BL/6 mice were housed three per cage. "
                "Cages were assigned to control or high-fat diet for 8 weeks. "
                "Body weight was recorded weekly for each animal."
            ),
            "three per cage",
            NodeType.ANIMAL,
            "mice",
            3,
        ),
        (
            "real-04",
            "eval",
            (
                "Organoids were generated from three iPSC lines. "
                "Each organoid was imaged at day 14 and day 28. "
                "Cortical thickness was the primary endpoint."
            ),
            "three iPSC lines",
            NodeType.CELL_LINE,
            "iPSC lines",
            3,
        ),
        (
            "real-05",
            "eval",
            (
                "Wells in 96-well plates received serial dilutions of drug Y. "
                "Cell viability was assessed by MTT assay. "
                "Technical triplicates were averaged before analysis."
            ),
            "Technical triplicates were averaged",
            NodeType.WELL,
            "wells",
            None,  # not exact n
        ),
        (
            "real-06",
            "eval",
            (
                "Tissue sections were obtained from six animals. "
                "Three ROIs were analysed per section. "
                "Mean fluorescence intensity was quantified."
            ),
            "six animals",
            NodeType.ANIMAL,
            "animals",
            6,
        ),
        (
            "real-07",
            "eval",
            (
                "Pooled samples from four donors were aliquoted into eight libraries. "
                "Libraries were sequenced. The number of independent biological units is unclear."
            ),
            "four donors",
            NodeType.HUMAN_DONOR,
            "donors",
            4,
        ),
        (
            "real-08",
            "eval",
            (
                "Explants from two dams were cultured. "
                "Treatments were applied to explants. "
                "Outgrowth length was measured after 48 h."
            ),
            "two dams",
            NodeType.DAM,
            "dams",
            2,
        ),
        (
            "real-09",
            "eval",
            (
                "Images were acquired from 15 wells. "
                "Five fields of view were selected per well. "
                "Object counts per field were recorded."
            ),
            "15 wells",
            NodeType.WELL,
            "wells",
            15,
        ),
        (
            "real-10",
            "eval",
            (
                "A cohort of 24 patients contributed archival tissue. "
                "Sections nested in patients were stained. "
                "H-score was the endpoint."
            ),
            "24 patients",
            NodeType.HUMAN_DONOR,
            "patients",
            24,
        ),
        (
            "real-11",
            "eval",
            (
                "Cell lines (A549 and HEK293) were seeded in plates. "
                "Drug Z or vehicle was applied to wells. "
                "IC50 was estimated from dose-response curves."
            ),
            "Cell lines (A549 and HEK293)",
            NodeType.CELL_LINE,
            "cell lines",
            None,
        ),
        (
            "real-12",
            "eval",
            (
                "Litters were randomly assigned to early or late weaning. "
                "Offspring nested in litters were tested at P60. "
                "Latency to criterion was measured."
            ),
            "Litters were randomly assigned",
            NodeType.LITTER,
            "litters",
            None,
        ),
        (
            "real-demo",
            "demo",
            (
                "Blood samples from eight donors were processed into PBMCs. "
                "Stimulation (PMA/ionomycin or control) was applied per donor. "
                "Cytokine concentration was quantified by ELISA."
            ),
            "eight donors",
            NodeType.HUMAN_DONOR,
            "donors",
            8,
        ),
    ]
    cases: list[dict[str, Any]] = []
    for case_id, split, text, span, unit, label, value in realistic_texts:
        file_id = f"file-{case_id}"
        e1 = _span(evidence_id=f"ev-{case_id}", file_id=file_id, text=span, full=text)
        block = CandidateExperimentBlock(
            block_id=f"block-{case_id}",
            title="Realistic methods excerpt",
            evidence_ids=(e1.evidence_id,),
            confidence=0.85,
        )
        node = CandidateNode(
            node_id=f"node-{case_id}",
            block_id=block.block_id,
            node_type=_node_type(unit),
            label=label,
            evidence_ids=(e1.evidence_id,),
            confidence=0.85,
        )
        counts: tuple[CandidateCountRecord, ...] = ()
        if value is not None:
            counts = (
                CandidateCountRecord(
                    count_id=f"count-{case_id}",
                    block_id=block.block_id,
                    kind=CountKind.DECLARED_N,
                    quantifier=CountQuantifier.EXACT,
                    value=value,
                    unit_type=_node_type(unit),
                    evidence_ids=(e1.evidence_id,),
                    confidence=0.85,
                    population_scope=label,
                ),
            )
        gold = CandidateGraphSet(
            result_id=f"result-{case_id}",
            stage=StageName.CANDIDATE_GRAPH_SET,
            status=StageStatus.COMPLETE,
            provenance=_provenance(case_id),
            graph_set_id=f"graph-{case_id}",
            experiment_blocks=(block,),
            evidence_spans=(e1,),
            candidate_nodes=(node,),
            counts=counts,
            chunk_coverage=(
                ChunkCoverageRecord(
                    file_id=file_id, total_chunks=1, processed_chunks=(0,), failed_chunks=()
                ),
            ),
        )
        cases.append(
            _case(
                case_id=case_id,
                kind="realistic",
                tasks=["TASK_EVIDENCE", "TASK_ENTITY_COUNT", "TASK_CANDIDATE_GRAPH"],
                text=text,
                gold=gold,
                split=split,  # type: ignore[arg-type]
                domain="fewshot_p0_realistic_paraphrase",
                notes="Realistic paraphrase; gold is minimal candidate structure, not full scientific truth.",
            )
        )
    return cases


def build_all_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for builder in (
        _family_empty,
        _family_evidence_entity,
        _family_counts,
        _family_factor_endpoint_relations,
        _family_full_graph_and_contradiction,
        _family_realistic,
    ):
        cases.extend(builder())
    # stable order
    cases.sort(key=lambda c: (0 if c["split"] == "demo" else 1, c["case_id"]))
    return cases


def write_fixture_suite(output_dir: Path) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cases = build_all_cases()
    path = output_dir / "cases.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for case in cases:
            handle.write(json.dumps(case, ensure_ascii=False, sort_keys=True) + "\n")
    demos = [c for c in cases if c["split"] == "demo"]
    evals = [c for c in cases if c["split"] == "eval"]
    by_kind: dict[str, int] = {}
    for case in cases:
        by_kind[case["kind"]] = by_kind.get(case["kind"], 0) + 1
    manifest = {
        "suite": "fewshot_p0_v1",
        "contract": "CandidateGraphSet/1.0.0",
        "parser_input_contract": "2.0.0",
        "scientific_validation": "NOT_STARTED",
        "purpose": "B4 baseline few-shot / zero-shot contract conformance (not model selection)",
        "not_for": [
            "rules_engine_training",
            "scientific_release_claims",
            "external_challenge",
        ],
        "counts": {
            "total": len(cases),
            "demo": len(demos),
            "eval": len(evals),
            "by_kind": by_kind,
        },
        "demo_case_ids": [c["case_id"] for c in demos],
        "eval_case_ids": [c["case_id"] for c in evals],
        "cases_path": str(path.name),
        "task_tags": list(TASK_TAGS),
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "README.md").write_text(
        """# Few-shot P0 baseline suite (B4)

Synthetic + realistic paraphrase fixtures for **contract/runtime** baseline of
Granite on P0 candidate-graph tasks.

- Gold targets are `CandidateGraphSet` candidate-only (no verdicts, no final n).
- Not used to train the rules engine.
- Not scientific validation; `scientific_validation_status` remains `NOT_STARTED`.
- Safe structural normalization may fill missing list fields as `[]`; it must not
  invent scientific content.

## Layout

- `cases.jsonl` — one JSON object per case (`split`: `demo` | `eval`)
- `manifest.json` — counts and ids

## Tasks covered

TASK_EVIDENCE, TASK_ENTITY_COUNT, TASK_FACTOR_ENDPOINT,
TASK_EXPLICIT_RELATIONS, TASK_CANDIDATE_GRAPH
""",
        encoding="utf-8",
    )
    return manifest


__all__ = [
    "TASK_TAGS",
    "build_all_cases",
    "write_fixture_suite",
]
