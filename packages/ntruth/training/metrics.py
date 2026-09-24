"""Metriche strutturate per il contratto Parser AI v2."""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterable
from typing import Any

from ntruth.parser_ai.contract import ParserCandidateOutput
from ntruth.training.calibration import ConfidenceObservation


def _text(value: str) -> str:
    return " ".join(value.casefold().split())


def _ontology(value: Any) -> str:
    raw = value.value if hasattr(value, "value") else value
    return str(raw.value if hasattr(raw, "value") else raw)


FactKey = tuple[Any, ...]
FactMultiset = Counter[FactKey]


def _fact_count(values: FactMultiset) -> int:
    return sum(values.values())


def _scores(predicted: FactMultiset, gold: FactMultiset) -> dict[str, float | int]:
    true_positive = _fact_count(predicted & gold)
    false_positive = _fact_count(predicted - gold)
    false_negative = _fact_count(gold - predicted)
    predicted_count = _fact_count(predicted)
    gold_count = _fact_count(gold)
    precision = true_positive / predicted_count if predicted_count else float(not gold_count)
    recall = true_positive / gold_count if gold_count else float(not predicted_count)
    f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def _evidence_key(span: Any) -> FactKey:
    """Return an evidence identity that deliberately excludes the local evidence ID."""

    return (
        span.file_id,
        _ontology(span.evidence_type),
        span.start,
        span.end,
        span.table_id,
        span.row,
        span.column,
        span.code_artifact_id,
        _text(span.text),
    )


def _sorted_facts(values: Iterable[FactKey]) -> tuple[FactKey, ...]:
    return tuple(sorted(values, key=repr))


def _candidate_fact_rows(
    output: ParserCandidateOutput,
) -> dict[str, list[tuple[FactKey, float]]]:
    """Build ID-invariant candidate facts with their exact evidence bindings."""

    evidence = {span.evidence_id: _evidence_key(span) for span in output.evidence_spans}

    def bound(evidence_ids: tuple[str, ...]) -> tuple[FactKey, ...]:
        return _sorted_facts(evidence[evidence_id] for evidence_id in evidence_ids)

    blocks = {block.block_id: (_text(block.title),) for block in output.experiment_blocks}
    nodes = {
        node.node_id: (
            blocks.get(node.block_id, (node.block_id,)),
            _ontology(node.node_type),
            _text(node.label),
        )
        for node in output.candidate_nodes
    }
    factors = {
        factor.factor_id: (
            blocks.get(factor.block_id, (factor.block_id,)),
            _text(factor.name),
            tuple(sorted(_text(level) for level in factor.levels)),
            _ontology(factor.allocation_level) if factor.allocation_level else None,
            _ontology(factor.application_level) if factor.application_level else None,
        )
        for factor in output.factors
    }
    endpoints = {
        endpoint.endpoint_id: (
            blocks.get(endpoint.block_id, (endpoint.block_id,)),
            _text(endpoint.name),
        )
        for endpoint in output.endpoints
    }
    edges = {
        edge.edge_id: (
            blocks.get(edge.block_id, (edge.block_id,)),
            nodes.get(edge.source_id, (edge.source_id,)),
            nodes.get(edge.target_id, (edge.target_id,)),
            _ontology(edge.relation_type),
        )
        for edge in output.candidate_edges
    }
    contrasts = {
        contrast.contrast_id: (
            blocks.get(contrast.block_id, (contrast.block_id,)),
            _sorted_facts(factors.get(item, (item,)) for item in contrast.factor_ids),
            tuple(sorted(_text(item) for item in contrast.compared_levels)),
            _sorted_facts(endpoints.get(item, (item,)) for item in contrast.endpoint_ids),
        )
        for contrast in output.contrasts
    }
    estimands = {
        estimand.estimand_id: (
            blocks.get(estimand.block_id, (estimand.block_id,)),
            _sorted_facts(factors.get(item, (item,)) for item in estimand.factor_ids),
            contrasts.get(estimand.contrast_id, (estimand.contrast_id,))
            if estimand.contrast_id is not None
            else None,
            endpoints.get(estimand.endpoint_id, (estimand.endpoint_id,)),
            _text(estimand.effect_measure),
            _text(estimand.target_population_or_unit),
            _text(estimand.generalization_level),
            _text(estimand.timepoint) if estimand.timepoint else None,
            _text(estimand.condition) if estimand.condition else None,
        )
        for estimand in output.candidate_estimands
    }
    counts = {
        count.count_id: (
            blocks.get(count.block_id, (count.block_id,)),
            _text(count.kind),
            count.candidate_value,
            _text(count.raw_text),
        )
        for count in output.candidate_counts
    }
    events = {
        event.event_id: (
            blocks.get(event.block_id, (event.block_id,)),
            _text(event.event_type),
            _sorted_facts(
                nodes.get(participant_id, (participant_id,))
                for participant_id in event.participant_candidate_ids
            ),
        )
        for event in output.candidate_events
    }
    graphs = {
        graph.graph_id: (
            blocks.get(graph.block_id, (graph.block_id,)),
            _sorted_facts(nodes.get(item, (item,)) for item in graph.candidate_node_ids),
            _sorted_facts(edges.get(item, (item,)) for item in graph.candidate_edge_ids),
            _sorted_facts(events.get(item, (item,)) for item in graph.candidate_event_ids),
        )
        for graph in output.candidate_graphs
    }
    alternatives = {
        alternative.alternative_id: (
            blocks.get(alternative.block_id, (alternative.block_id,)),
            _text(alternative.description),
            _sorted_facts(nodes.get(item, (item,)) for item in alternative.candidate_node_ids),
            _sorted_facts(edges.get(item, (item,)) for item in alternative.candidate_edge_ids),
        )
        for alternative in output.alternatives
    }
    return {
        "experiment_blocks": [
            ((*blocks[block.block_id], bound(block.evidence_ids)), block.confidence)
            for block in output.experiment_blocks
        ],
        "block_boundaries": [
            (
                (
                    blocks.get(boundary.block_id, (boundary.block_id,)),
                    tuple(
                        sorted(
                            (
                                _ontology(predicate.criterion),
                                _ontology(predicate.internal_query_representability),
                            )
                            for predicate in boundary.boundary_predicates
                        )
                    ),
                    bound(boundary.evidence_ids),
                ),
                boundary.confidence,
            )
            for boundary in output.block_boundaries
        ],
        "candidate_nodes": [
            ((*nodes[node.node_id], bound(node.evidence_ids)), node.confidence)
            for node in output.candidate_nodes
        ],
        "candidate_edges": [
            (
                (*edges[edge.edge_id], bound(edge.evidence_ids)),
                edge.confidence,
            )
            for edge in output.candidate_edges
        ],
        "factors": [
            ((*factors[factor.factor_id], bound(factor.evidence_ids)), factor.confidence)
            for factor in output.factors
        ],
        "endpoints": [
            ((*endpoints[endpoint.endpoint_id], bound(endpoint.evidence_ids)), endpoint.confidence)
            for endpoint in output.endpoints
        ],
        "contrasts": [
            (
                (*contrasts[contrast.contrast_id], bound(contrast.evidence_ids)),
                contrast.confidence,
            )
            for contrast in output.contrasts
        ],
        "candidate_estimands": [
            (
                (*estimands[estimand.estimand_id], bound(estimand.evidence_ids)),
                estimand.confidence,
            )
            for estimand in output.candidate_estimands
        ],
        "candidate_counts": [
            (
                (*counts[count.count_id], bound(count.evidence_ids)),
                count.confidence,
            )
            for count in output.candidate_counts
        ],
        "candidate_events": [
            (
                (*events[event.event_id], bound(event.evidence_ids)),
                event.confidence,
            )
            for event in output.candidate_events
        ],
        "candidate_graphs": [
            (
                (*graphs[graph.graph_id], bound(graph.evidence_ids)),
                graph.confidence,
            )
            for graph in output.candidate_graphs
        ],
        "alternatives": [
            (
                (*alternatives[alternative.alternative_id], bound(alternative.evidence_ids)),
                alternative.confidence,
            )
            for alternative in output.alternatives
        ],
    }


def _fact_multisets(output: ParserCandidateOutput) -> dict[str, FactMultiset]:
    rows = _candidate_fact_rows(output)
    result = {
        category: Counter(key for key, _confidence in candidates)
        for category, candidates in rows.items()
    }
    evidence = {span.evidence_id: _evidence_key(span) for span in output.evidence_spans}
    blocks = {block.block_id: (_text(block.title),) for block in output.experiment_blocks}
    candidate_refs: dict[str, FactKey] = {}
    candidate_source_items = {
        "candidate_nodes": output.candidate_nodes,
        "candidate_edges": output.candidate_edges,
        "factors": output.factors,
        "endpoints": output.endpoints,
        "contrasts": output.contrasts,
        "candidate_estimands": output.candidate_estimands,
        "candidate_counts": output.candidate_counts,
        "candidate_events": output.candidate_events,
        "candidate_graphs": output.candidate_graphs,
        "alternatives": output.alternatives,
    }
    for category, candidates in rows.items():
        source_items = candidate_source_items.get(category)
        if source_items is None:
            continue
        for item, (key, _confidence) in zip(source_items, candidates, strict=True):
            identifier = next(
                value
                for name, value in item.__dict__.items()
                if name.endswith("_id") and name != "block_id"
            )
            candidate_refs[identifier] = key

    def bound(evidence_ids: tuple[str, ...]) -> tuple[FactKey, ...]:
        return _sorted_facts(evidence[evidence_id] for evidence_id in evidence_ids)

    result.update(
        {
            "evidence_spans": Counter(_evidence_key(span) for span in output.evidence_spans),
            "clarification_questions": Counter(
                (
                    blocks.get(question.block_id, (question.block_id,)),
                    _text(question.question),
                    _sorted_facts(
                        candidate_refs.get(item, (item,))
                        for item in question.resolves_candidate_ids
                    ),
                    _text(question.rationale),
                )
                for question in output.clarification_questions
            ),
            "missing_predicates": Counter(
                (
                    blocks.get(missing.block_id, (missing.block_id,)),
                    _text(missing.predicate_name),
                    _text(missing.rationale),
                    bound(missing.evidence_ids),
                )
                for missing in output.missing_predicates
            ),
            "coverage": Counter(
                {
                    (
                        output.coverage.status.value,
                        tuple(sorted(output.coverage.covered_artifact_ids)),
                        tuple(sorted(output.coverage.missing_artifact_ids)),
                        _text(output.coverage.rationale),
                    ): 1
                }
            ),
        }
    )
    return result


def _candidate_confidences(
    output: ParserCandidateOutput,
) -> dict[str, list[tuple[FactKey, float]]]:
    return _candidate_fact_rows(output)


def parse_prediction_text(text: str) -> ParserCandidateOutput:
    """Accetta JSON puro o un singolo code fence, poi applica lo schema Pydantic."""

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
    return ParserCandidateOutput.model_validate(value)


def score_output(predicted: ParserCandidateOutput, gold: ParserCandidateOutput) -> dict[str, Any]:
    predicted_multisets = _fact_multisets(predicted)
    gold_multisets = _fact_multisets(gold)
    category_scores = {
        category: _scores(predicted_multisets[category], gold_multisets[category])
        for category in predicted_multisets
    }
    predicted_all: FactMultiset = Counter()
    gold_all: FactMultiset = Counter()
    for category, values in predicted_multisets.items():
        predicted_all.update({(category, *key): count for key, count in values.items()})
    for category, values in gold_multisets.items():
        gold_all.update({(category, *key): count for key, count in values.items()})
    return {
        "schema_valid": True,
        "exact_contract_match": predicted.model_dump(mode="json") == gold.model_dump(mode="json"),
        "categories": category_scores,
        "micro": _scores(predicted_all, gold_all),
    }


def score_invalid_output(gold: ParserCandidateOutput, error: str) -> dict[str, Any]:
    """Conta un output non validabile come mancata estrazione, senza ripararlo."""

    gold_multisets = _fact_multisets(gold)
    false_negative = sum(_fact_count(values) for values in gold_multisets.values())
    return {
        "schema_valid": False,
        "invalid_output": True,
        "validation_error": error,
        "exact_contract_match": False,
        "categories": {
            category: {
                "true_positive": 0,
                "false_positive": 0,
                "false_negative": _fact_count(values),
                "precision": 0.0,
                "recall": 0.0,
                "f1": 0.0,
            }
            for category, values in gold_multisets.items()
        },
        "micro": {
            "true_positive": 0,
            "false_positive": 0,
            "false_negative": false_negative,
            # An output that cannot be parsed is never a perfect extraction,
            # including the edge case where the gold fact sets are empty.
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
        },
    }


def confidence_observations(
    predicted: ParserCandidateOutput, gold: ParserCandidateOutput
) -> tuple[ConfidenceObservation, ...]:
    """Etichetta ogni fatto predetto come corretto/non corretto per la calibrazione."""

    remaining_gold = _fact_multisets(gold)
    observations: list[ConfidenceObservation] = []
    for category, candidates in _candidate_confidences(predicted).items():
        for key, confidence in candidates:
            correct = remaining_gold[category][key] > 0
            if correct:
                remaining_gold[category][key] -= 1
            observations.append(ConfidenceObservation(confidence=confidence, correct=correct))
    return tuple(observations)


def aggregate_scores(scores: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(scores)
    if not rows:
        raise ValueError("nessun risultato da aggregare")
    counts = {
        name: sum(int(row["micro"][name]) for row in rows)
        for name in ("true_positive", "false_positive", "false_negative")
    }
    tp = counts["true_positive"]
    fp = counts["false_positive"]
    fn = counts["false_negative"]
    invalid_outputs = sum(not bool(row.get("schema_valid")) for row in rows)
    precision = tp / (tp + fp) if tp + fp else float(invalid_outputs == 0)
    recall = tp / (tp + fn) if tp + fn else float(invalid_outputs == 0)
    category_names = sorted(
        {str(category) for row in rows for category in row.get("categories", {})}
    )
    categories: dict[str, dict[str, float | int]] = {}
    for category in category_names:
        category_counts = {
            name: sum(int(row["categories"][category][name]) for row in rows)
            for name in ("true_positive", "false_positive", "false_negative")
        }
        category_tp = category_counts["true_positive"]
        category_fp = category_counts["false_positive"]
        category_fn = category_counts["false_negative"]
        category_precision = (
            category_tp / (category_tp + category_fp)
            if category_tp + category_fp
            else float(invalid_outputs == 0)
        )
        category_recall = (
            category_tp / (category_tp + category_fn)
            if category_tp + category_fn
            else float(invalid_outputs == 0)
        )
        categories[category] = {
            **category_counts,
            "precision": category_precision,
            "recall": category_recall,
            "f1": (
                2.0 * category_precision * category_recall / (category_precision + category_recall)
                if category_precision + category_recall
                else 0.0
            ),
        }

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
            "f1": 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0,
        },
    }
