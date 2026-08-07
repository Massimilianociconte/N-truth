"""Metriche di conformità strutturale per ``CandidateGraphSet`` (non scientifiche).

Separano:
- sintassi JSON
- conformità allo schema
- campi vietati / candidate-only
- referenze rotte / fatti senza evidence
- normalizzazione strutturale *sicura* (solo container vuoti o chiavi extra note)

Non inventano fatti scientifici. ``missing_facts: []`` e ammesso solo come
assenza di elementi nell'array, non come affermazione "non manca nulla".
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any

from ntruth.model_backends.base import MODEL_MUST_NOT_EMIT
from ntruth.parser_ai import ParserAIInput
from ntruth.parser_ai.stages import CandidateGraphSet, validate_candidate_graph_pair
from ntruth.training.metrics_v6 import (
    aggregate_scores,
    parse_prediction_text,
    score_invalid_output,
    score_output,
)

# Campi lista dello schema CandidateGraphSet: se assenti possono essere
# materializzati come [] solo in modalità structural_skeleton (non semantica).
_LIST_FIELDS: tuple[str, ...] = (
    "errors",
    "warnings",
    "source_result_ids",
    "experiment_blocks",
    "evidence_spans",
    "candidate_nodes",
    "candidate_edges",
    "factors",
    "endpoints",
    "contrasts",
    "candidate_estimands",
    "counts",
    "operational_independence",
    "procedural_events",
    "alternatives",
    "missing_facts",
    "chunk_coverage",
)

_FORBIDDEN_OUTPUT_KEYS = MODEL_MUST_NOT_EMIT | frozenset(
    {
        "determinability",
        "verdict",
        "n",
        "final_n",
        "independent_n",
        "final_independent_n",
        "paper_score",
        "paper_quality_score",
        "statistical_test",
        "statistical_test_choice",
        "clarification_questions",  # legacy v2; non nel contratto v6 graph set
        "model_metadata",
    }
)


def extract_json_object(text: str) -> tuple[dict[str, Any] | None, str | None]:
    """Estrae il primo oggetto JSON; None se assente o non oggetto."""

    stripped = text.strip()
    if not stripped:
        return None, "empty_output"
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL | re.I)
    if fence:
        stripped = fence.group(1).strip()
    try:
        value = json.loads(stripped)
        if isinstance(value, dict):
            return value, None
        return None, f"json_root_type={type(value).__name__}"
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", stripped)
    if not match:
        return None, "no_json_object"
    try:
        value = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        return None, f"json_decode_error:{exc.msg}"
    if not isinstance(value, dict):
        return None, f"embedded_root_type={type(value).__name__}"
    return value, None


def find_forbidden_keys(payload: Mapping[str, Any]) -> list[str]:
    found: list[str] = []
    for key in payload:
        if key in _FORBIDDEN_OUTPUT_KEYS or key.casefold() in {
            k.casefold() for k in _FORBIDDEN_OUTPUT_KEYS
        }:
            found.append(str(key))
    return sorted(set(found))


def safe_structural_normalize(
    payload: Mapping[str, Any],
    *,
    fill_missing_list_fields: bool = True,
    strip_forbidden_keys: bool = False,
) -> tuple[dict[str, Any], list[str]]:
    """Normalizzazione strutturale sicura.

    Operazioni ammesse:
    - rimozione opzionale di chiavi proibite (registrata come warning);
    - materializzazione di campi lista *assenti* come ``[]`` (skeleton);
    - nessun riparo di tipi sbagliati (es. string al posto di lista);
    - nessun riempimento di fatti scientifici.
    """

    notes: list[str] = []
    out: dict[str, Any] = dict(payload)
    if strip_forbidden_keys:
        for key in find_forbidden_keys(out):
            out.pop(key, None)
            notes.append(f"stripped_forbidden_key:{key}")
    if fill_missing_list_fields:
        for field in _LIST_FIELDS:
            if field not in out:
                out[field] = []
                notes.append(f"filled_missing_list:{field}")
            elif out[field] is None:
                # None → [] e assenza strutturale esplicita, non contenuto scientifico.
                out[field] = []
                notes.append(f"null_list_to_empty:{field}")
    return out, notes


def analyze_structural_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Analisi pre-schema: tipi container, chiavi proibite, pattern noti."""

    issues: list[str] = []
    forbidden = find_forbidden_keys(payload)
    if forbidden:
        issues.append(f"forbidden_keys:{','.join(forbidden)}")
    for field in _LIST_FIELDS:
        if field not in payload:
            issues.append(f"missing_list_field:{field}")
            continue
        value = payload[field]
        if value is None:
            issues.append(f"null_list_field:{field}")
        elif not isinstance(value, list | tuple):
            issues.append(f"wrong_type_list_field:{field}:{type(value).__name__}")
    for required in ("schema_version", "result_id", "stage", "status", "provenance", "graph_set_id"):
        if required not in payload:
            issues.append(f"missing_required:{required}")
    return {
        "forbidden_keys": forbidden,
        "structural_issues": issues,
        "list_field_present": {
            field: field in payload for field in _LIST_FIELDS
        },
    }


def assess_prediction(
    raw_text: str,
    *,
    parser_input: ParserAIInput | None = None,
    gold: CandidateGraphSet | None = None,
    apply_safe_normalize: bool = True,
) -> dict[str, Any]:
    """Valuta un output grezzo: sintassi, schema, policy, score opzionale vs gold."""

    result: dict[str, Any] = {
        "json_extractable": False,
        "schema_valid": False,
        "schema_valid_after_safe_normalize": False,
        "candidate_only_ok": True,
        "forbidden_keys": [],
        "structural_issues": [],
        "safe_normalize_notes": [],
        "validation_error": None,
        "score": None,
        "predicted_summary": None,
    }
    payload, extract_error = extract_json_object(raw_text)
    if payload is None:
        result["validation_error"] = extract_error or "extract_failed"
        if gold is not None:
            result["score"] = score_invalid_output(gold, result["validation_error"])
        return result

    result["json_extractable"] = True
    structural = analyze_structural_payload(payload)
    result["forbidden_keys"] = structural["forbidden_keys"]
    result["structural_issues"] = structural["structural_issues"]
    result["candidate_only_ok"] = not structural["forbidden_keys"]

    # Tentativo diretto (stretto: parse_prediction_text)
    try:
        predicted = parse_prediction_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        )
        if parser_input is not None:
            predicted = validate_candidate_graph_pair(parser_input, predicted)
        result["schema_valid"] = True
        result["schema_valid_after_safe_normalize"] = True
        result["predicted_summary"] = _summary(predicted)
        if gold is not None:
            result["score"] = score_output(predicted, gold)
        return result
    except Exception as exc:  # noqa: BLE001 — diagnostica
        result["validation_error"] = str(exc)

    if not apply_safe_normalize:
        if gold is not None:
            result["score"] = score_invalid_output(gold, result["validation_error"] or "invalid")
        return result

    normalized, notes = safe_structural_normalize(
        payload,
        fill_missing_list_fields=True,
        strip_forbidden_keys=bool(structural["forbidden_keys"]),
    )
    result["safe_normalize_notes"] = notes
    try:
        predicted = CandidateGraphSet.model_validate(normalized)
        if parser_input is not None:
            predicted = validate_candidate_graph_pair(parser_input, predicted)
        result["schema_valid_after_safe_normalize"] = True
        result["predicted_summary"] = _summary(predicted)
        if gold is not None:
            result["score"] = score_output(predicted, gold)
        # schema_valid resta False: solo dopo normalize
    except Exception as exc:  # noqa: BLE001
        result["validation_error"] = (
            f"raw={result['validation_error']}; after_normalize={exc}"
        )
        if gold is not None:
            result["score"] = score_invalid_output(
                gold, result["validation_error"] or "invalid"
            )
    return result


def _summary(graph: CandidateGraphSet) -> dict[str, int | str]:
    return {
        "graph_set_id": graph.graph_set_id,
        "status": str(graph.status),
        "evidence_spans": len(graph.evidence_spans),
        "experiment_blocks": len(graph.experiment_blocks),
        "candidate_nodes": len(graph.candidate_nodes),
        "candidate_edges": len(graph.candidate_edges),
        "factors": len(graph.factors),
        "endpoints": len(graph.endpoints),
        "counts": len(graph.counts),
        "missing_facts": len(graph.missing_facts),
        "alternatives": len(graph.alternatives),
    }


def aggregate_conformance(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    if n == 0:
        return {"records": 0}
    scores = [row["score"] for row in rows if isinstance(row.get("score"), dict)]
    semantic = aggregate_scores(scores) if scores else None
    return {
        "records": n,
        "json_extractable_rate": sum(bool(r.get("json_extractable")) for r in rows) / n,
        "schema_valid_rate": sum(bool(r.get("schema_valid")) for r in rows) / n,
        "schema_valid_after_safe_normalize_rate": sum(
            bool(r.get("schema_valid_after_safe_normalize")) for r in rows
        )
        / n,
        "candidate_only_ok_rate": sum(bool(r.get("candidate_only_ok")) for r in rows) / n,
        "forbidden_key_hits": sum(len(r.get("forbidden_keys") or []) for r in rows),
        "semantic": semantic,
    }


__all__ = [
    "aggregate_conformance",
    "analyze_structural_payload",
    "assess_prediction",
    "extract_json_object",
    "find_forbidden_keys",
    "safe_structural_normalize",
]
