"""Metriche strutturate per il contratto Parser AI v2."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any

from ntruth.parser_ai.contract import ParserAIOutput
from ntruth.training.calibration import ConfidenceObservation


def _text(value: str) -> str:
    return " ".join(value.casefold().split())


def _ontology(value: Any) -> str:
    raw = value.value if hasattr(value, "value") else value
    return str(raw.value if hasattr(raw, "value") else raw)


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


def _fact_sets(output: ParserAIOutput) -> dict[str, set[tuple[Any, ...]]]:
    block_titles = {block.block_id: _text(block.title) for block in output.experiment_blocks}
    nodes = {
        node.node_id: (
            block_titles.get(node.block_id, node.block_id),
            _ontology(node.node_type),
            _text(node.label),
        )
        for node in output.candidate_nodes
    }
    factors = {
        factor.factor_id: (
            block_titles.get(factor.block_id, factor.block_id),
            _text(factor.name),
            _ontology(factor.allocation_level) if factor.allocation_level else None,
            _ontology(factor.application_level) if factor.application_level else None,
        )
        for factor in output.factors
    }
    endpoints = {
        endpoint.endpoint_id: (
            block_titles.get(endpoint.block_id, endpoint.block_id),
            _text(endpoint.name),
        )
        for endpoint in output.endpoints
    }
    return {
        "experiment_blocks": {(title,) for title in block_titles.values()},
        "evidence_spans": {
            (
                span.file_id,
                _ontology(span.evidence_type),
                span.start,
                span.end,
                span.table_id,
                span.row,
                span.column,
                _text(span.text),
            )
            for span in output.evidence_spans
        },
        "candidate_nodes": set(nodes.values()),
        "candidate_edges": {
            (
                block_titles.get(edge.block_id, edge.block_id),
                nodes.get(edge.source_id, (edge.source_id,)),
                nodes.get(edge.target_id, (edge.target_id,)),
                _ontology(edge.relation_type),
            )
            for edge in output.candidate_edges
        },
        "factors": set(factors.values()),
        "endpoints": set(endpoints.values()),
        "contrasts": {
            (
                block_titles.get(contrast.block_id, contrast.block_id),
                tuple(sorted(factors.get(item, (item,)) for item in contrast.factor_ids)),
                tuple(sorted(_text(item) for item in contrast.compared_levels)),
                tuple(sorted(endpoints.get(item, (item,)) for item in contrast.endpoint_ids)),
            )
            for contrast in output.contrasts
        },
        "candidate_estimands": {
            (
                block_titles.get(estimand.block_id, estimand.block_id),
                tuple(sorted(factors.get(item, (item,)) for item in estimand.factor_ids)),
                endpoints.get(estimand.endpoint_id, (estimand.endpoint_id,)),
                _text(estimand.effect_measure),
                _text(estimand.target_population_or_unit),
                _text(estimand.generalization_level),
                _text(estimand.timepoint) if estimand.timepoint else None,
                _text(estimand.condition) if estimand.condition else None,
            )
            for estimand in output.candidate_estimands
        },
    }


def _candidate_confidences(
    output: ParserAIOutput,
) -> dict[str, list[tuple[tuple[Any, ...], float]]]:
    block_titles = {block.block_id: _text(block.title) for block in output.experiment_blocks}
    nodes = {
        node.node_id: (
            block_titles.get(node.block_id, node.block_id),
            _ontology(node.node_type),
            _text(node.label),
        )
        for node in output.candidate_nodes
    }
    factors = {
        factor.factor_id: (
            block_titles.get(factor.block_id, factor.block_id),
            _text(factor.name),
            _ontology(factor.allocation_level) if factor.allocation_level else None,
            _ontology(factor.application_level) if factor.application_level else None,
        )
        for factor in output.factors
    }
    endpoints = {
        endpoint.endpoint_id: (
            block_titles.get(endpoint.block_id, endpoint.block_id),
            _text(endpoint.name),
        )
        for endpoint in output.endpoints
    }
    result: dict[str, list[tuple[tuple[Any, ...], float]]] = {
        "experiment_blocks": [
            ((block_titles[block.block_id],), block.confidence)
            for block in output.experiment_blocks
        ],
        "candidate_nodes": [
            (nodes[node.node_id], node.confidence) for node in output.candidate_nodes
        ],
        "candidate_edges": [
            (
                (
                    block_titles.get(edge.block_id, edge.block_id),
                    nodes.get(edge.source_id, (edge.source_id,)),
                    nodes.get(edge.target_id, (edge.target_id,)),
                    _ontology(edge.relation_type),
                ),
                edge.confidence,
            )
            for edge in output.candidate_edges
        ],
        "factors": [(factors[factor.factor_id], factor.confidence) for factor in output.factors],
        "endpoints": [
            (endpoints[endpoint.endpoint_id], endpoint.confidence) for endpoint in output.endpoints
        ],
        "contrasts": [
            (
                (
                    block_titles.get(contrast.block_id, contrast.block_id),
                    tuple(sorted(factors.get(item, (item,)) for item in contrast.factor_ids)),
                    tuple(sorted(_text(item) for item in contrast.compared_levels)),
                    tuple(sorted(endpoints.get(item, (item,)) for item in contrast.endpoint_ids)),
                ),
                contrast.confidence,
            )
            for contrast in output.contrasts
        ],
        "candidate_estimands": [
            (
                (
                    block_titles.get(estimand.block_id, estimand.block_id),
                    tuple(sorted(factors.get(item, (item,)) for item in estimand.factor_ids)),
                    endpoints.get(estimand.endpoint_id, (estimand.endpoint_id,)),
                    _text(estimand.effect_measure),
                    _text(estimand.target_population_or_unit),
                    _text(estimand.generalization_level),
                    _text(estimand.timepoint) if estimand.timepoint else None,
                    _text(estimand.condition) if estimand.condition else None,
                ),
                estimand.confidence,
            )
            for estimand in output.candidate_estimands
        ],
    }
    return result


def parse_prediction_text(text: str) -> ParserAIOutput:
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
    return ParserAIOutput.model_validate(value)


def score_output(predicted: ParserAIOutput, gold: ParserAIOutput) -> dict[str, Any]:
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
        "determinability_accuracy": float(
            predicted.determinability.status == gold.determinability.status
        ),
        "determinability": {
            "predicted": _ontology(predicted.determinability.status),
            "gold": _ontology(gold.determinability.status),
        },
        "categories": category_scores,
        "micro": _scores(predicted_all, gold_all),
    }


def score_invalid_output(gold: ParserAIOutput, error: str) -> dict[str, Any]:
    """Conta un output non validabile come mancata estrazione, senza ripararlo."""

    gold_sets = _fact_sets(gold)
    false_negative = sum(len(values) for values in gold_sets.values())
    return {
        "schema_valid": False,
        "invalid_output": True,
        "validation_error": error,
        "exact_contract_match": False,
        "determinability_accuracy": 0.0,
        "determinability": {
            "predicted": None,
            "gold": _ontology(gold.determinability.status),
        },
        "categories": {
            category: {
                "true_positive": 0,
                "false_positive": 0,
                "false_negative": len(values),
                "precision": 0.0,
                "recall": 0.0,
                "f1": 0.0,
            }
            for category, values in gold_sets.items()
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
    predicted: ParserAIOutput, gold: ParserAIOutput
) -> tuple[ConfidenceObservation, ...]:
    """Etichetta ogni fatto predetto come corretto/non corretto per la calibrazione."""

    gold_sets = _fact_sets(gold)
    observations: list[ConfidenceObservation] = []
    for category, candidates in _candidate_confidences(predicted).items():
        for key, confidence in candidates:
            observations.append(
                ConfidenceObservation(confidence=confidence, correct=key in gold_sets[category])
            )
    observations.append(
        ConfidenceObservation(
            confidence=predicted.determinability.confidence,
            correct=predicted.determinability.status == gold.determinability.status,
        )
    )
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

    determinability_pairs = [row["determinability"] for row in rows]
    determinability_labels = sorted(
        {
            str(value)
            for pair in determinability_pairs
            for value in (pair.get("gold"), pair.get("predicted"))
            if value is not None
        }
    )
    determinability_by_label: dict[str, dict[str, float | int]] = {}
    for label in determinability_labels:
        label_tp = sum(
            pair.get("gold") == label and pair.get("predicted") == label
            for pair in determinability_pairs
        )
        label_fp = sum(
            pair.get("gold") != label and pair.get("predicted") == label
            for pair in determinability_pairs
        )
        label_fn = sum(
            pair.get("gold") == label and pair.get("predicted") != label
            for pair in determinability_pairs
        )
        label_precision = label_tp / (label_tp + label_fp) if label_tp + label_fp else 0.0
        label_recall = label_tp / (label_tp + label_fn) if label_tp + label_fn else 0.0
        determinability_by_label[label] = {
            "true_positive": label_tp,
            "false_positive": label_fp,
            "false_negative": label_fn,
            "precision": label_precision,
            "recall": label_recall,
            "f1": (
                2.0 * label_precision * label_recall / (label_precision + label_recall)
                if label_precision + label_recall
                else 0.0
            ),
        }
    return {
        "records": len(rows),
        "invalid_output_count": invalid_outputs,
        "schema_valid_rate": sum(bool(row.get("schema_valid")) for row in rows) / len(rows),
        "exact_contract_match_rate": sum(bool(row.get("exact_contract_match")) for row in rows)
        / len(rows),
        "determinability_accuracy": sum(float(row["determinability_accuracy"]) for row in rows)
        / len(rows),
        "determinability_macro_f1": (
            sum(float(item["f1"]) for item in determinability_by_label.values())
            / len(determinability_by_label)
            if determinability_by_label
            else 0.0
        ),
        "determinability_by_label": determinability_by_label,
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
