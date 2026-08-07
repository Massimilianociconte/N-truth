"""Metriche candidate-only per il contratto parser ``CandidateGraphSet`` v6.

La determinability e i verdict sono deliberatamente assenti: appartengono al
compilatore deterministico e non sono target, predizioni o metriche del parser.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any

from ntruth.parser_ai.stages import CandidateGraphSet
from ntruth.training.calibration import ConfidenceObservation


def _text(value: str | None) -> str | None:
    return " ".join(value.casefold().split()) if value is not None else None


def _ontology(value: Any) -> str | None:
    if value is None:
        return None
    raw = value.value if hasattr(value, "value") else value
    raw = raw.value if hasattr(raw, "value") else raw
    return str(raw)


def _confidence(value: Any) -> float:
    return float(value.confidence)


def _ordered(values: Iterable[Any]) -> tuple[Any, ...]:
    """Ordina firme eterogenee senza confrontare direttamente ``None`` ed enum."""

    return tuple(sorted(values, key=repr))


def _evidence_signature(item: Any) -> tuple[Any, ...]:
    """Firma semantica di uno span, indipendente dal suo ``evidence_id``."""

    return (
        item.file_id,
        _ontology(item.evidence_type),
        item.section_id,
        item.start,
        item.end,
        item.table_id,
        item.row,
        item.column,
        item.code_artifact_id,
        _text(item.text),
    )


def _linked_evidence(
    evidence_ids: tuple[str, ...],
    evidence: dict[str, tuple[Any, ...]],
) -> tuple[Any, ...]:
    """Normalizza i link senza rendere gli ID arbitrari parte della metrica."""

    return _ordered(evidence[evidence_id] for evidence_id in evidence_ids)


def _scores(predicted: set[tuple[Any, ...]], gold: set[tuple[Any, ...]]) -> dict[str, float | int]:
    true_positive = len(predicted & gold)
    false_positive = len(predicted - gold)
    false_negative = len(gold - predicted)
    precision = true_positive / len(predicted) if predicted else float(not gold)
    recall = true_positive / len(gold) if gold else float(not predicted)
    f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def _context(output: CandidateGraphSet) -> dict[str, dict[str, tuple[Any, ...]]]:
    evidence = {item.evidence_id: _evidence_signature(item) for item in output.evidence_spans}
    blocks = {item.block_id: (_text(item.title),) for item in output.experiment_blocks}
    nodes = {
        item.node_id: (
            blocks.get(item.block_id, (item.block_id,)),
            _ontology(item.node_type),
            _text(item.label),
        )
        for item in output.candidate_nodes
    }
    factors = {
        item.factor_id: (
            blocks.get(item.block_id, (item.block_id,)),
            _text(item.name),
            _ordered(_text(level) or "" for level in item.levels),
            _ontology(item.allocation_level),
            _ontology(item.application_level),
        )
        for item in output.factors
    }
    endpoints = {
        item.endpoint_id: (
            blocks.get(item.block_id, (item.block_id,)),
            _text(item.name),
        )
        for item in output.endpoints
    }
    edges = {
        item.edge_id: (
            blocks.get(item.block_id, (item.block_id,)),
            nodes.get(item.source_id, (item.source_id,)),
            nodes.get(item.target_id, (item.target_id,)),
            _ontology(item.relation_type),
        )
        for item in output.candidate_edges
    }
    contrasts = {
        item.contrast_id: (
            blocks.get(item.block_id, (item.block_id,)),
            _ordered(factors.get(value, (value,)) for value in item.factor_ids),
            _ordered(_text(value) or "" for value in item.compared_levels),
            _ordered(endpoints.get(value, (value,)) for value in item.endpoint_ids),
        )
        for item in output.contrasts
    }
    events = {
        item.event_id: (
            blocks.get(item.block_id, (item.block_id,)),
            _text(item.event_type),
            _ordered(nodes.get(value, (value,)) for value in item.subject_node_ids),
            _text(item.timing_text),
        )
        for item in output.procedural_events
    }
    return {
        "evidence": evidence,
        "blocks": blocks,
        "nodes": nodes,
        "factors": factors,
        "endpoints": endpoints,
        "edges": edges,
        "contrasts": contrasts,
        "events": events,
    }


def _fact_lists(output: CandidateGraphSet) -> dict[str, list[tuple[Any, ...]]]:
    context = _context(output)
    evidence = context["evidence"]
    blocks = context["blocks"]
    nodes = context["nodes"]
    factors = context["factors"]
    endpoints = context["endpoints"]
    edges = context["edges"]
    contrasts = context["contrasts"]
    events = context["events"]
    return {
        "experiment_blocks": [
            (*blocks[item.block_id], _linked_evidence(item.evidence_ids, evidence))
            for item in output.experiment_blocks
        ],
        "evidence_spans": list(evidence.values()),
        "candidate_nodes": [
            (*nodes[item.node_id], _linked_evidence(item.evidence_ids, evidence))
            for item in output.candidate_nodes
        ],
        "candidate_edges": [
            (*edges[item.edge_id], _linked_evidence(item.evidence_ids, evidence))
            for item in output.candidate_edges
        ],
        "factors": [
            (*factors[item.factor_id], _linked_evidence(item.evidence_ids, evidence))
            for item in output.factors
        ],
        "endpoints": [
            (*endpoints[item.endpoint_id], _linked_evidence(item.evidence_ids, evidence))
            for item in output.endpoints
        ],
        "contrasts": [
            (*contrasts[item.contrast_id], _linked_evidence(item.evidence_ids, evidence))
            for item in output.contrasts
        ],
        "candidate_estimands": [
            (
                blocks.get(item.block_id, (item.block_id,)),
                _ordered(factors.get(value, (value,)) for value in item.factor_ids),
                contrasts.get(item.contrast_id, (item.contrast_id,))
                if item.contrast_id is not None
                else None,
                endpoints.get(item.endpoint_id, (item.endpoint_id,)),
                _text(item.effect_measure),
                _text(item.target_population_or_unit),
                _text(item.generalization_level),
                _text(item.timepoint),
                _text(item.condition),
                _linked_evidence(item.evidence_ids, evidence),
            )
            for item in output.candidate_estimands
        ],
        "counts": [
            (
                blocks.get(item.block_id, (item.block_id,)),
                _ontology(item.kind),
                _ontology(item.quantifier),
                item.value,
                item.lower_bound,
                item.upper_bound,
                _ontology(item.unit_type),
                factors.get(item.factor_id, (item.factor_id,))
                if item.factor_id is not None
                else None,
                contrasts.get(item.contrast_id, (item.contrast_id,))
                if item.contrast_id is not None
                else None,
                _text(item.group_or_level),
                endpoints.get(item.endpoint_id, (item.endpoint_id,))
                if item.endpoint_id is not None
                else None,
                _text(item.timepoint),
                _ontology(item.lifecycle),
                _text(item.population_scope),
                _text(item.condition),
                _linked_evidence(item.evidence_ids, evidence),
            )
            for item in output.counts
        ],
        "operational_independence": [
            (
                blocks.get(item.block_id, (item.block_id,)),
                factors.get(item.factor_id, (item.factor_id,)),
                _ontology(item.independently_assigned),
                _ontology(item.randomization_unit),
                _text(item.independence_mechanism),
                _ordered(_text(value) for value in item.shared_environment),
                _ordered(_text(value) for value in item.confounded_with),
                _text(item.source_biological_preparation),
                events.get(item.allocation_event_id, (item.allocation_event_id,))
                if item.allocation_event_id is not None
                else None,
                _text(item.allocation_timing),
                _linked_evidence(item.evidence_ids, evidence),
            )
            for item in output.operational_independence
        ],
        "procedural_events": [
            (
                *events[item.event_id],
                _ordered(events.get(value, (value,)) for value in item.before_event_ids),
                _ordered(events.get(value, (value,)) for value in item.after_event_ids),
                _linked_evidence(item.evidence_ids, evidence),
            )
            for item in output.procedural_events
        ],
        "alternatives": [
            (
                blocks.get(item.block_id, (item.block_id,)),
                _text(item.description),
                _ordered(nodes.get(value, (value,)) for value in item.candidate_node_ids),
                _ordered(edges.get(value, (value,)) for value in item.candidate_edge_ids),
                _linked_evidence(item.evidence_ids, evidence),
            )
            for item in output.alternatives
        ],
        "missing_facts": [
            (
                blocks.get(item.block_id, (item.block_id,)),
                _text(item.predicate),
                _text(item.reason),
                _linked_evidence(item.evidence_ids, evidence),
            )
            for item in output.missing_facts
        ],
        "chunk_coverage": [
            (
                item.file_id,
                item.total_chunks,
                tuple(sorted(item.processed_chunks)),
                tuple(sorted(item.failed_chunks)),
            )
            for item in output.chunk_coverage
        ],
    }


def _fact_sets(output: CandidateGraphSet) -> dict[str, set[tuple[Any, ...]]]:
    return {category: set(values) for category, values in _fact_lists(output).items()}


def _candidate_confidences(
    output: CandidateGraphSet,
) -> dict[str, list[tuple[tuple[Any, ...], float]]]:
    signatures = _fact_lists(output)
    id_fields = {
        "experiment_blocks": (output.experiment_blocks, "block_id"),
        "evidence_spans": (output.evidence_spans, "evidence_id"),
        "candidate_nodes": (output.candidate_nodes, "node_id"),
        "candidate_edges": (output.candidate_edges, "edge_id"),
        "factors": (output.factors, "factor_id"),
        "endpoints": (output.endpoints, "endpoint_id"),
        "contrasts": (output.contrasts, "contrast_id"),
        "candidate_estimands": (output.candidate_estimands, "estimand_id"),
        "counts": (output.counts, "count_id"),
        "operational_independence": (output.operational_independence, "independence_id"),
        "procedural_events": (output.procedural_events, "event_id"),
        "alternatives": (output.alternatives, "alternative_id"),
    }
    # Preserve one confidence per emitted object while using the same normalized
    # key as scoring. IDs are intentionally ignored, but input order is retained.
    return {
        category: [
            (signature, _confidence(item))
            for signature, item in zip(signatures[category], items, strict=True)
        ]
        for category, (items, _id_field) in id_fields.items()
    }


def parse_prediction_text(text: str) -> CandidateGraphSet:
    """Accetta JSON puro o un singolo code fence e applica lo schema v6."""

    stripped = text.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL | re.I)
    if fence:
        stripped = fence.group(1).strip()
    decoder = json.JSONDecoder()
    try:
        value, end = decoder.raw_decode(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError(f"output non JSON: {exc.msg}") from exc
    if stripped[end:].strip():
        raise ValueError("testo extra dopo il payload JSON")
    return CandidateGraphSet.model_validate(value)


def score_output(predicted: CandidateGraphSet, gold: CandidateGraphSet) -> dict[str, Any]:
    predicted_sets = _fact_sets(predicted)
    gold_sets = _fact_sets(gold)
    category_scores = {
        category: _scores(predicted_sets[category], gold_sets[category])
        for category in predicted_sets
    }
    predicted_all = {
        (category, *value) for category, values in predicted_sets.items() for value in values
    }
    gold_all = {(category, *value) for category, values in gold_sets.items() for value in values}
    return {
        "schema_valid": True,
        "exact_contract_match": predicted.model_dump(mode="json") == gold.model_dump(mode="json"),
        "categories": category_scores,
        "micro": _scores(predicted_all, gold_all),
    }


def score_invalid_output(gold: CandidateGraphSet, error: str) -> dict[str, Any]:
    """Conta un output non validabile come mancata estrazione, anche su gold vuoto."""

    gold_sets = _fact_sets(gold)
    false_negative = sum(len(values) for values in gold_sets.values())
    empty = {
        "true_positive": 0,
        "false_positive": 0,
        "precision": 0.0,
        "recall": 0.0,
        "f1": 0.0,
    }
    return {
        "schema_valid": False,
        "invalid_output": True,
        "validation_error": error,
        "exact_contract_match": False,
        "categories": {
            category: {**empty, "false_negative": len(values)}
            for category, values in gold_sets.items()
        },
        "micro": {**empty, "false_negative": false_negative},
    }


def confidence_observations(
    predicted: CandidateGraphSet, gold: CandidateGraphSet
) -> tuple[ConfidenceObservation, ...]:
    """Etichetta solo confidence di fatti/evidenze candidati; mai un verdict."""

    gold_sets = _fact_sets(gold)
    return tuple(
        ConfidenceObservation(confidence=confidence, correct=key in gold_sets[category])
        for category, candidates in _candidate_confidences(predicted).items()
        for key, confidence in candidates
    )


def aggregate_scores(scores: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(scores)
    if not rows:
        raise ValueError("nessun risultato da aggregare")
    invalid_outputs = sum(not bool(row.get("schema_valid")) for row in rows)
    names = ("true_positive", "false_positive", "false_negative")
    counts = {name: sum(int(row["micro"][name]) for row in rows) for name in names}

    def aggregate_category(category: str) -> dict[str, float | int]:
        values = {
            name: sum(int(row["categories"][category][name]) for row in rows) for name in names
        }
        tp = values["true_positive"]
        fp = values["false_positive"]
        fn = values["false_negative"]
        precision = tp / (tp + fp) if tp + fp else float(invalid_outputs == 0)
        recall = tp / (tp + fn) if tp + fn else float(invalid_outputs == 0)
        return {
            **values,
            "precision": precision,
            "recall": recall,
            "f1": (2.0 * precision * recall / (precision + recall) if precision + recall else 0.0),
        }

    category_names = sorted(
        {str(category) for row in rows for category in row.get("categories", {})}
    )
    categories = {category: aggregate_category(category) for category in category_names}
    tp = counts["true_positive"]
    fp = counts["false_positive"]
    fn = counts["false_negative"]
    precision = tp / (tp + fp) if tp + fp else float(invalid_outputs == 0)
    recall = tp / (tp + fn) if tp + fn else float(invalid_outputs == 0)
    return {
        "records": len(rows),
        "invalid_output_count": invalid_outputs,
        "schema_valid_rate": sum(bool(row.get("schema_valid")) for row in rows) / len(rows),
        "exact_contract_match_rate": sum(bool(row.get("exact_contract_match")) for row in rows)
        / len(rows),
        "categories": categories,
        "macro_category_f1": (
            sum(float(item["f1"]) for item in categories.values()) / len(categories)
            if categories
            else 0.0
        ),
        "micro": {
            **counts,
            "precision": precision,
            "recall": recall,
            "f1": (2.0 * precision * recall / (precision + recall) if precision + recall else 0.0),
        },
    }


__all__ = [
    "aggregate_scores",
    "confidence_observations",
    "parse_prediction_text",
    "score_invalid_output",
    "score_output",
]
