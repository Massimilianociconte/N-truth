"""Scoring semantico stage-level B4 (development only).

Versione 1.0.0 — non è validazione scientifica. Opera su predizioni già generate
(JSON stage-level) vs gold minimale derivato dalle fixture fewshot_p0.

I 39 casi hanno ruolo DEVELOPMENT / B4_CONSTRAINED_DEV.
"""

from __future__ import annotations

import json
import random
import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from typing import Any, Literal

SCORER_VERSION = "1.0.0"
DECISIVE_RELATIONS = frozenset(
    {
        "derived_from",
        "nested_in",
        "allocated_to",
        "applied_to",
        "split_from",
        "pooled_from",
        "measured_on",
        "same_source_as",
        "repeated_measure_of",
    }
)

FailureCode = Literal[
    "CORRECT_SCHEMA_WRONG_CONTENT",
    "MISSED_EVIDENCE",
    "HALLUCINATED_EVIDENCE",
    "WRONG_ENTITY_BOUNDARY",
    "WRONG_ENTITY_TYPE",
    "WRONG_COUNT_VALUE",
    "WRONG_QUANTIFIER",
    "WRONG_COUNT_SCOPE",
    "WRONG_RELATION_TYPE",
    "WRONG_RELATION_DIRECTION",
    "UNSUPPORTED_RELATION",
    "MISSING_REQUIRED_RELATION",
    "ENTITY_ID_MISMATCH",
    "CROSS_SENTENCE_FAILURE",
    "NEGATION_FAILURE",
    "EMPTY_OUTPUT_BIAS",
    "OVER_EXTRACTION",
    "UNDER_EXTRACTION",
]


def _norm_text(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(str(value).casefold().split())


def _prf(tp: int, fp: int, fn: int) -> dict[str, float | int]:
    precision = tp / (tp + fp) if tp + fp else float(fn == 0 and fp == 0)
    recall = tp / (tp + fn) if tp + fn else float(fp == 0 and tp == 0)
    f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "support_gold": tp + fn,
        "support_pred": tp + fp,
    }


def _set_prf(pred: set[Any], gold: set[Any]) -> dict[str, float | int]:
    tp = len(pred & gold)
    fp = len(pred - gold)
    fn = len(gold - pred)
    return _prf(tp, fp, fn)


def _span_overlap(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _iou(a: tuple[int, int], b: tuple[int, int]) -> float:
    left = max(a[0], b[0])
    right = min(a[1], b[1])
    inter = max(0, right - left)
    if inter == 0:
        return 0.0
    union = (a[1] - a[0]) + (b[1] - b[0]) - inter
    return inter / union if union else 0.0


def extract_json(text: str) -> dict[str, Any] | None:
    stripped = (text or "").strip()
    if not stripped:
        return None
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL | re.I)
    if fence:
        stripped = fence.group(1).strip()
    try:
        value = json.loads(stripped)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", stripped)
    if not match:
        return None
    try:
        value = json.loads(match.group(0))
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# Gold projections from full CandidateGraphSet fixture → stage mini targets
# ---------------------------------------------------------------------------


def gold_evidence_items(case: dict[str, Any]) -> list[dict[str, Any]]:
    gold = case["gold"]
    items = []
    for span in gold.get("evidence_spans") or []:
        items.append(
            {
                "file_id": span.get("file_id"),
                "text": span.get("text") or "",
                "start": int(span.get("start") or 0),
                "end": int(span.get("end") or 0),
                "evidence_type": (
                    span.get("evidence_type")
                    if not isinstance(span.get("evidence_type"), dict)
                    else span.get("evidence_type", {}).get("value")
                )
                or "AUTHOR_ASSERTION",
            }
        )
    return items


def gold_entity_items(case: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for node in case["gold"].get("candidate_nodes") or []:
        ntype = node.get("node_type")
        if isinstance(ntype, dict):
            ntype = ntype.get("value")
        items.append(
            {
                "label": node.get("label") or "",
                "node_type": str(ntype or "OTHER"),
                "evidence_ids": list(node.get("evidence_ids") or []),
            }
        )
    return items


def gold_count_items(case: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for count in case["gold"].get("counts") or []:
        unit = count.get("unit_type")
        if isinstance(unit, dict):
            unit = unit.get("value")
        items.append(
            {
                "quantifier": count.get("quantifier") or "UNKNOWN",
                "value": count.get("value"),
                "lower_bound": count.get("lower_bound"),
                "upper_bound": count.get("upper_bound"),
                "unit_label": str(unit or count.get("population_scope") or ""),
                "scope": count.get("population_scope") or "",
                "evidence_ids": list(count.get("evidence_ids") or []),
            }
        )
    return items


def gold_relation_items(case: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = {n.get("node_id"): n for n in (case["gold"].get("candidate_nodes") or [])}
    items = []
    for edge in case["gold"].get("candidate_edges") or []:
        rel = edge.get("relation_type")
        if isinstance(rel, dict):
            rel = rel.get("value")
        rel = str(rel or "other")
        src = nodes.get(edge.get("source_id"), {})
        tgt = nodes.get(edge.get("target_id"), {})
        items.append(
            {
                "source_label": src.get("label") or edge.get("source_id") or "",
                "target_label": tgt.get("label") or edge.get("target_id") or "",
                "relation_type": rel
                if rel in DECISIVE_RELATIONS or rel in {"nested_in", "derived_from", "other"}
                else "other",
                "evidence_ids": list(edge.get("evidence_ids") or []),
            }
        )
    return items


# ---------------------------------------------------------------------------
# Prediction projections from stage JSON
# ---------------------------------------------------------------------------


def pred_evidence_items(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not payload:
        return []
    items = []
    for span in payload.get("evidence_spans") or []:
        if not isinstance(span, dict):
            continue
        items.append(
            {
                "file_id": span.get("file_id"),
                "text": span.get("text") or "",
                "start": int(span.get("start") or 0),
                "end": int(span.get("end") or 0),
                "evidence_type": span.get("evidence_type") or "UNKNOWN",
            }
        )
    return items


def pred_entity_items(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not payload:
        return []
    items = []
    for ent in payload.get("entities") or []:
        if not isinstance(ent, dict):
            continue
        items.append(
            {
                "label": ent.get("label") or "",
                "node_type": str(ent.get("node_type") or "OTHER"),
                "evidence_ids": list(ent.get("evidence_ids") or []),
            }
        )
    return items


def pred_count_items(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not payload:
        return []
    items = []
    for count in payload.get("counts") or []:
        if not isinstance(count, dict):
            continue
        items.append(
            {
                "quantifier": count.get("quantifier") or "UNKNOWN",
                "value": count.get("value"),
                "lower_bound": count.get("lower_bound"),
                "upper_bound": count.get("upper_bound"),
                "unit_label": str(count.get("unit_label") or ""),
                "scope": str(count.get("unit_label") or ""),
                "evidence_ids": list(count.get("evidence_ids") or []),
            }
        )
    return items


def pred_relation_items(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not payload:
        return []
    items = []
    for rel in payload.get("relations") or []:
        if not isinstance(rel, dict):
            continue
        items.append(
            {
                "source_label": rel.get("source_label") or "",
                "target_label": rel.get("target_label") or "",
                "relation_type": str(rel.get("relation_type") or "other"),
                "evidence_ids": list(rel.get("evidence_ids") or []),
            }
        )
    return items


def pred_graph_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {
            "entities": [],
            "counts": [],
            "relations": [],
            "evidence_spans": [],
            "factors": [],
            "endpoints": [],
        }
    return {
        "entities": pred_entity_items(payload),
        "counts": pred_count_items(payload),
        "relations": pred_relation_items(payload),
        "evidence_spans": pred_evidence_items(payload),
        "factors": [f for f in (payload.get("factors") or []) if isinstance(f, dict)],
        "endpoints": [e for e in (payload.get("endpoints") or []) if isinstance(e, dict)],
        "missing_fact_predicates": list(payload.get("missing_fact_predicates") or []),
    }


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


def _exact_span_key(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        item.get("file_id"),
        int(item.get("start") or 0),
        int(item.get("end") or 0),
        _norm_text(item.get("text")),
    )


def _text_key(item: dict[str, Any]) -> str:
    return _norm_text(item.get("text") or item.get("label") or "")


def match_spans_exact(
    pred: Sequence[dict[str, Any]], gold: Sequence[dict[str, Any]]
) -> dict[str, float | int]:
    return _set_prf({_exact_span_key(x) for x in pred}, {_exact_span_key(x) for x in gold})


def match_spans_overlap(
    pred: Sequence[dict[str, Any]],
    gold: Sequence[dict[str, Any]],
    *,
    min_iou: float = 0.5,
) -> dict[str, float | int]:
    """Greedy IoU matching within same file_id (or any if missing)."""

    used_g: set[int] = set()
    tp = 0
    for p in pred:
        best_i = -1
        best_iou = 0.0
        p_span = (int(p.get("start") or 0), int(p.get("end") or 0))
        for gi, g in enumerate(gold):
            if gi in used_g:
                continue
            if p.get("file_id") and g.get("file_id") and p.get("file_id") != g.get("file_id"):
                continue
            g_span = (int(g.get("start") or 0), int(g.get("end") or 0))
            # also allow text containment if offsets missing/zero
            iou = _iou(p_span, g_span)
            if iou < min_iou:
                pt, gt = _norm_text(p.get("text")), _norm_text(g.get("text"))
                if pt and gt and (pt in gt or gt in pt):
                    iou = max(iou, 0.5)
            if iou > best_iou:
                best_iou = iou
                best_i = gi
        if best_i >= 0 and best_iou >= min_iou:
            tp += 1
            used_g.add(best_i)
    fp = len(pred) - tp
    fn = len(gold) - tp
    return _prf(tp, fp, fn)


def match_entities(
    pred: Sequence[dict[str, Any]], gold: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    # exact: normalized label + type
    pred_exact = {(_norm_text(p.get("label")), _norm_text(p.get("node_type"))) for p in pred}
    gold_exact = {(_norm_text(g.get("label")), _norm_text(g.get("node_type"))) for g in gold}
    exact = _set_prf(pred_exact, gold_exact)
    # relaxed: label only (substring match greedy)
    used: set[int] = set()
    tp = 0
    for p in pred:
        pl = _norm_text(p.get("label"))
        if not pl:
            continue
        for gi, g in enumerate(gold):
            if gi in used:
                continue
            gl = _norm_text(g.get("label"))
            if pl == gl or pl in gl or gl in pl:
                tp += 1
                used.add(gi)
                break
    relaxed = _prf(tp, len(pred) - tp, len(gold) - tp)
    # type macro
    types = sorted({t for _, t in gold_exact} | {t for _, t in pred_exact})
    type_rows = []
    for t in types:
        if not t:
            continue
        gp = {lab for lab, ty in gold_exact if ty == t}
        pp = {lab for lab, ty in pred_exact if ty == t}
        type_rows.append({"type": t, **_set_prf(pp, gp)})
    macro_f1 = sum(float(r["f1"]) for r in type_rows) / len(type_rows) if type_rows else 0.0
    return {
        "exact": exact,
        "relaxed": relaxed,
        "type_macro_f1": macro_f1,
        "type_rows": type_rows,
        "hallucinated_entity_rate": (float(exact["false_positive"]) / len(pred) if pred else 0.0),
        "missed_entity_rate": (float(exact["false_negative"]) / len(gold) if gold else 0.0),
    }


def match_counts(pred: Sequence[dict[str, Any]], gold: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Match greedy on (value, quantifier) then score attributes."""

    if not gold and not pred:
        return {
            "value_exact_accuracy": 1.0,
            "quantifier_accuracy": 1.0,
            "unit_type_accuracy": 1.0,
            "scope_accuracy": 1.0,
            "fully_correct_rate": 1.0,
            "numeric_hallucination_rate": 0.0,
            "support_gold": 0,
            "support_pred": 0,
            "matched": 0,
        }
    used: set[int] = set()
    matched = 0
    value_ok = quant_ok = unit_ok = scope_ok = full_ok = 0
    for p in pred:
        best = -1
        best_score = -1
        for gi, g in enumerate(gold):
            if gi in used:
                continue
            score = 0
            if p.get("value") is not None and p.get("value") == g.get("value"):
                score += 3
            if _norm_text(str(p.get("quantifier"))) == _norm_text(str(g.get("quantifier"))):
                score += 2
            if _norm_text(str(p.get("unit_label"))) == _norm_text(str(g.get("unit_label"))):
                score += 1
            if score > best_score:
                best_score = score
                best = gi
        if best < 0:
            continue
        used.add(best)
        g = gold[best]
        matched += 1
        v_ok = p.get("value") == g.get("value") and p.get("value") is not None
        q_ok = _norm_text(str(p.get("quantifier"))) == _norm_text(str(g.get("quantifier")))
        u_ok = _norm_text(str(p.get("unit_label"))) == _norm_text(str(g.get("unit_label")))
        s_ok = _norm_text(str(p.get("scope") or p.get("unit_label"))) == _norm_text(
            str(g.get("scope") or g.get("unit_label"))
        )
        # value alone wrong unit → not fully correct
        if v_ok:
            value_ok += 1
        if q_ok:
            quant_ok += 1
        if u_ok:
            unit_ok += 1
        if s_ok:
            scope_ok += 1
        if v_ok and q_ok and u_ok:
            full_ok += 1
    # quantifier-only golds (NOT_REPORTED etc.)
    for gi, g in enumerate(gold):
        if gi in used:
            continue
        if g.get("quantifier") in {"NOT_REPORTED", "UNKNOWN"} and g.get("value") is None:
            # look for any unmatched pred with same quantifier
            for _pi, p in enumerate(pred):
                if _norm_text(str(p.get("quantifier"))) == _norm_text(str(g.get("quantifier"))):
                    matched += 1
                    quant_ok += 1
                    if p.get("value") is None:
                        value_ok += 1
                        full_ok += 1
                    break
    n_g = max(1, len(gold))
    n_p = max(1, len(pred))
    # hallucination: pred counts with values when gold empty or unmatched numeric
    halluc = 0
    if not gold:
        halluc = sum(1 for p in pred if p.get("value") is not None)
    else:
        halluc = max(0, len(pred) - matched)
    return {
        "value_exact_accuracy": value_ok / n_g,
        "quantifier_accuracy": quant_ok / n_g,
        "unit_type_accuracy": unit_ok / n_g,
        "scope_accuracy": scope_ok / n_g,
        "fully_correct_rate": full_ok / n_g,
        "numeric_hallucination_rate": halluc / n_p if pred else 0.0,
        "support_gold": len(gold),
        "support_pred": len(pred),
        "matched": matched,
    }


def match_relations(
    pred: Sequence[dict[str, Any]], gold: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    def key(r: dict[str, Any], *, directed: bool = True) -> tuple[str, str, str]:
        s = _norm_text(r.get("source_label"))
        t = _norm_text(r.get("target_label"))
        rel = _norm_text(r.get("relation_type"))
        if not directed and s > t:
            s, t = t, s
        return (s, t, rel)

    pred_dir = {key(r, directed=True) for r in pred}
    gold_dir = {key(r, directed=True) for r in gold}
    directed = _set_prf(pred_dir, gold_dir)
    # reverse direction errors among same pair labels
    direction_errors = 0
    for p in pred:
        rev = (
            _norm_text(p.get("target_label")),
            _norm_text(p.get("source_label")),
            _norm_text(p.get("relation_type")),
        )
        fwd = key(p, directed=True)
        if rev in gold_dir and fwd not in gold_dir:
            direction_errors += 1
    types = sorted({_norm_text(r.get("relation_type")) for r in list(pred) + list(gold)} - {""})
    type_rows = []
    for t in types:
        gp = {key(r) for r in gold if _norm_text(r.get("relation_type")) == t}
        pp = {key(r) for r in pred if _norm_text(r.get("relation_type")) == t}
        type_rows.append({"type": t, **_set_prf(pp, gp)})
    macro = sum(float(r["f1"]) for r in type_rows) / len(type_rows) if type_rows else 0.0
    # decisive subset
    [
        r
        for r in gold
        if _norm_text(r.get("relation_type")) in DECISIVE_RELATIONS
        or r.get("relation_type") in DECISIVE_RELATIONS
    ]
    [
        r
        for r in pred
        if _norm_text(r.get("relation_type")) in DECISIVE_RELATIONS
        or r.get("relation_type") in DECISIVE_RELATIONS
    ]
    # our stage schema only has nested_in/derived_from/other — map
    gold_dec_keys = {
        key(r)
        for r in gold
        if str(r.get("relation_type")) in DECISIVE_RELATIONS
        or str(r.get("relation_type")) in {"nested_in", "derived_from"}
    }
    pred_dec_keys = {
        key(r)
        for r in pred
        if str(r.get("relation_type")) in DECISIVE_RELATIONS
        or str(r.get("relation_type")) in {"nested_in", "derived_from"}
    }
    decisive = _set_prf(pred_dec_keys, gold_dec_keys)
    # dangling: empty labels
    dangling = sum(
        1
        for r in pred
        if not _norm_text(r.get("source_label")) or not _norm_text(r.get("target_label"))
    )
    return {
        "directed_edge": directed,
        "relation_type_macro_f1": macro,
        "type_rows": type_rows,
        "direction_error_count": direction_errors,
        "direction_error_rate": direction_errors / len(pred) if pred else 0.0,
        "decisive_edge_metrics": decisive,
        "dangling_reference_rate": dangling / len(pred) if pred else 0.0,
        "duplicate_edge_rate": (1.0 - (len(pred_dir) / len(pred)) if pred else 0.0),
    }


def match_graph_minimal(pred: dict[str, Any], gold_case: dict[str, Any]) -> dict[str, Any]:
    g_ent = gold_entity_items(gold_case)
    g_rel = gold_relation_items(gold_case)
    g_ev = gold_evidence_items(gold_case)
    p_ent = pred.get("entities") or []
    p_rel = pred.get("relations") or []
    p_ev = pred.get("evidence_spans") or []
    nodes = match_entities(p_ent, g_ent)
    edges = match_relations(p_rel, g_rel)
    evidence = match_spans_overlap(p_ev, g_ev)
    # edit distance proxy: FN+FP nodes+edges normalized
    n_fp = int(nodes["exact"]["false_positive"]) + int(edges["directed_edge"]["false_positive"])
    n_fn = int(nodes["exact"]["false_negative"]) + int(edges["directed_edge"]["false_negative"])
    denom = max(
        1,
        len(g_ent) + len(g_rel) + len(p_ent) + len(p_rel),
    )
    ned = (n_fp + n_fn) / denom
    # empty output bias
    empty = (
        len(p_ent) == 0
        and len(p_rel) == 0
        and len(p_ev) == 0
        and (len(g_ent) + len(g_rel) + len(g_ev)) > 0
    )
    return {
        "nodes": nodes["exact"],
        "nodes_relaxed": nodes["relaxed"],
        "edges": edges["directed_edge"],
        "evidence_overlap": evidence,
        "normalized_graph_edit_distance": ned,
        "exact_minimal_graph_match": (
            nodes["exact"]["f1"] == 1.0
            and edges["directed_edge"]["f1"] == 1.0
            and int(nodes["exact"]["false_positive"]) == 0
            and int(edges["directed_edge"]["false_positive"]) == 0
        ),
        "empty_output_bias": empty,
        "referential_integrity": edges["dangling_reference_rate"] == 0.0,
    }


# ---------------------------------------------------------------------------
# Failure taxonomy
# ---------------------------------------------------------------------------


def classify_failures(
    *,
    stage: str,
    gold_case: dict[str, Any],
    payload: dict[str, Any] | None,
    metrics: dict[str, Any],
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    case_id = gold_case.get("case_id", "")

    def add(code: str, detail: str) -> None:
        failures.append({"case_id": case_id, "stage": stage, "code": code, "detail": detail})

    if payload is None:
        add("CORRECT_SCHEMA_WRONG_CONTENT", "payload missing after schema-valid claim")
        return failures

    if stage == "evidence_extraction":
        g = gold_evidence_items(gold_case)
        p = pred_evidence_items(payload)
        if not p and g:
            add("EMPTY_OUTPUT_BIAS", "empty evidence_spans with non-empty gold")
            add("UNDER_EXTRACTION", f"0 pred vs {len(g)} gold")
            add("MISSED_EVIDENCE", f"missed {len(g)} spans")
        if p and not g:
            add("OVER_EXTRACTION", f"{len(p)} pred spans on empty gold")
            add("HALLUCINATED_EVIDENCE", f"{len(p)} unsupported spans")
        exact = metrics.get("exact_span") or {}
        if int(exact.get("false_negative") or 0) > 0:
            add("MISSED_EVIDENCE", f"fn={exact.get('false_negative')}")
        if int(exact.get("false_positive") or 0) > 0:
            add("HALLUCINATED_EVIDENCE", f"fp={exact.get('false_positive')}")
        if float(exact.get("f1") or 0) < 1.0 and float(
            (metrics.get("overlap_span") or {}).get("f1") or 0
        ) > float(exact.get("f1") or 0):
            add("WRONG_ENTITY_BOUNDARY", "overlap better than exact (boundary mismatch)")
        if p and g and float(exact.get("f1") or 0) == 0:
            add("CORRECT_SCHEMA_WRONG_CONTENT", "schema ok, zero exact span match")

    elif stage == "entity_count":
        ge, pe = gold_entity_items(gold_case), pred_entity_items(payload)
        gc, pc = gold_count_items(gold_case), pred_count_items(payload)
        ent = metrics.get("entities") or {}
        cnt = metrics.get("counts") or {}
        if not pe and not pc and (ge or gc):
            add("EMPTY_OUTPUT_BIAS", "empty entities/counts")
            add("UNDER_EXTRACTION", "no entities or counts extracted")
        if int((ent.get("exact") or {}).get("false_negative") or 0) > 0:
            add("MISSED_EVIDENCE", f"missed entities fn={ent['exact']['false_negative']}")
        if int((ent.get("exact") or {}).get("false_positive") or 0) > 0:
            add(
                "HALLUCINATED_EVIDENCE",
                f"hallucinated entities fp={ent['exact']['false_positive']}",
            )
        if float(ent.get("hallucinated_entity_rate") or 0) > 0:
            add("WRONG_ENTITY_TYPE", "type or label mismatch contributing to FP")
        if gc and float(cnt.get("value_exact_accuracy") or 0) < 1.0:
            add("WRONG_COUNT_VALUE", f"value_acc={cnt.get('value_exact_accuracy')}")
        if gc and float(cnt.get("quantifier_accuracy") or 0) < 1.0:
            add("WRONG_QUANTIFIER", f"quant_acc={cnt.get('quantifier_accuracy')}")
        if gc and float(cnt.get("unit_type_accuracy") or 0) < 1.0:
            add("WRONG_COUNT_SCOPE", f"unit_acc={cnt.get('unit_type_accuracy')}")
        if float(cnt.get("numeric_hallucination_rate") or 0) > 0:
            add("HALLUCINATED_EVIDENCE", "numeric hallucination on counts")

    elif stage == "candidate_relations":
        gr, pr = gold_relation_items(gold_case), pred_relation_items(payload)
        rel = metrics.get("relations") or {}
        if not pr and gr:
            add("EMPTY_OUTPUT_BIAS", "empty relations")
            add("MISSING_REQUIRED_RELATION", f"missed {len(gr)} gold relations")
            add("UNDER_EXTRACTION", "no relations extracted")
        if pr and not gr:
            add("OVER_EXTRACTION", f"{len(pr)} relations on empty gold")
            add("UNSUPPORTED_RELATION", "relations without gold support")
        de = rel.get("directed_edge") or {}
        if int(de.get("false_negative") or 0) > 0:
            add("MISSING_REQUIRED_RELATION", f"fn={de.get('false_negative')}")
        if int(de.get("false_positive") or 0) > 0:
            add("UNSUPPORTED_RELATION", f"fp={de.get('false_positive')}")
        if float(rel.get("direction_error_rate") or 0) > 0:
            add("WRONG_RELATION_DIRECTION", f"rate={rel.get('direction_error_rate')}")
        if float(rel.get("relation_type_macro_f1") or 1) < 1.0 and gr and pr:
            add("WRONG_RELATION_TYPE", f"macro_f1={rel.get('relation_type_macro_f1')}")
        if float(rel.get("dangling_reference_rate") or 0) > 0:
            add("ENTITY_ID_MISMATCH", "dangling source/target labels")

    elif stage == "candidate_graph_minimal":
        graph_metrics = metrics.get("graph") or {}
        if graph_metrics.get("empty_output_bias"):
            add("EMPTY_OUTPUT_BIAS", "empty graph with non-empty gold")
            add("UNDER_EXTRACTION", "empty minimal graph")
        if float((graph_metrics.get("nodes") or {}).get("f1") or 0) < 1.0:
            add(
                "CORRECT_SCHEMA_WRONG_CONTENT",
                f"node_f1={graph_metrics.get('nodes', {}).get('f1')}",
            )
        if float((graph_metrics.get("edges") or {}).get("f1") or 0) < 1.0 and gold_relation_items(
            gold_case
        ):
            add("MISSING_REQUIRED_RELATION", f"edge_f1={graph_metrics.get('edges', {}).get('f1')}")

    return failures


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------


def bootstrap_ci(
    values: Sequence[float],
    *,
    n_boot: int = 2000,
    alpha: float = 0.05,
    seed: int = 0,
) -> dict[str, float | int | None]:
    if not values:
        return {"mean": None, "low": None, "high": None, "n": 0}
    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(n_boot):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo = means[int((alpha / 2) * n_boot)]
    hi = means[min(n_boot - 1, int((1 - alpha / 2) * n_boot))]
    return {
        "mean": sum(values) / n,
        "low": lo,
        "high": hi,
        "n": n,
        "n_boot": n_boot,
        "alpha": alpha,
    }


# ---------------------------------------------------------------------------
# Per-case and aggregate scoring
# ---------------------------------------------------------------------------


def score_case_stage(
    *,
    stage: str,
    case: dict[str, Any],
    raw_text: str | None,
    schema_valid: bool,
    truncated: bool,
) -> dict[str, Any]:
    payload = extract_json(raw_text or "")
    complete = bool(schema_valid and not truncated and payload is not None)
    metrics: dict[str, Any] = {
        "case_id": case["case_id"],
        "kind": case.get("kind"),
        "stage": stage,
        "schema_valid": schema_valid,
        "truncated": truncated,
        "complete": complete,
        "empty_lists": False,
    }

    if stage == "evidence_extraction":
        g, p = gold_evidence_items(case), pred_evidence_items(payload)
        metrics["exact_span"] = match_spans_exact(p, g) if complete else _zero_prf(g, p)
        metrics["overlap_span"] = match_spans_overlap(p, g) if complete else _zero_prf(g, p)
        metrics["empty_lists"] = complete and len(p) == 0
        metrics["unsupported_evidence_rate"] = (
            float(metrics["exact_span"]["false_positive"]) / len(p) if p else 0.0
        )
        metrics["duplicate_span_rate"] = (
            1.0 - len({_exact_span_key(x) for x in p}) / len(p) if p else 0.0
        )
        metrics["primary_f1"] = float(metrics["exact_span"]["f1"])
        metrics["relaxed_f1"] = float(metrics["overlap_span"]["f1"])

    elif stage == "entity_count":
        ge, pe = gold_entity_items(case), pred_entity_items(payload)
        gc, pc = gold_count_items(case), pred_count_items(payload)
        if complete:
            metrics["entities"] = match_entities(pe, ge)
            metrics["counts"] = match_counts(pc, gc)
        else:
            metrics["entities"] = {
                "exact": _zero_prf(ge, pe),
                "relaxed": _zero_prf(ge, pe),
                "type_macro_f1": 0.0,
                "hallucinated_entity_rate": 1.0 if pe else 0.0,
                "missed_entity_rate": 1.0 if ge else 0.0,
            }
            metrics["counts"] = {
                "value_exact_accuracy": 0.0 if gc else 1.0,
                "quantifier_accuracy": 0.0 if gc else 1.0,
                "unit_type_accuracy": 0.0 if gc else 1.0,
                "scope_accuracy": 0.0 if gc else 1.0,
                "fully_correct_rate": 0.0 if gc else 1.0,
                "numeric_hallucination_rate": 1.0 if pc else 0.0,
                "support_gold": len(gc),
                "support_pred": len(pc),
                "matched": 0,
            }
        metrics["empty_lists"] = complete and len(pe) == 0 and len(pc) == 0
        metrics["primary_f1"] = float(metrics["entities"]["exact"]["f1"])
        metrics["count_fully_correct"] = float(metrics["counts"]["fully_correct_rate"])

    elif stage == "candidate_relations":
        gr, pr = gold_relation_items(case), pred_relation_items(payload)
        if complete:
            metrics["relations"] = match_relations(pr, gr)
        else:
            metrics["relations"] = {
                "directed_edge": _zero_prf(gr, pr),
                "relation_type_macro_f1": 0.0,
                "direction_error_rate": 0.0,
                "decisive_edge_metrics": _zero_prf(gr, pr),
                "dangling_reference_rate": 0.0,
                "duplicate_edge_rate": 0.0,
            }
        metrics["empty_lists"] = complete and len(pr) == 0
        metrics["primary_f1"] = float(metrics["relations"]["directed_edge"]["f1"])
        metrics["decisive_f1"] = float(metrics["relations"]["decisive_edge_metrics"]["f1"])

    elif stage == "candidate_graph_minimal":
        if complete:
            gp = pred_graph_payload(payload)
            metrics["graph"] = match_graph_minimal(gp, case)
        else:
            metrics["graph"] = {
                "nodes": _zero_prf(gold_entity_items(case), []),
                "edges": _zero_prf(gold_relation_items(case), []),
                "normalized_graph_edit_distance": 1.0,
                "exact_minimal_graph_match": False,
                "empty_output_bias": True,
                "referential_integrity": False,
            }
        metrics["empty_lists"] = bool(complete and metrics["graph"].get("empty_output_bias"))
        metrics["primary_f1"] = (
            float(metrics["graph"]["nodes"]["f1"]) + float(metrics["graph"]["edges"]["f1"])
        ) / 2.0
    else:
        raise ValueError(f"stage sconosciuto: {stage}")

    metrics["failures"] = classify_failures(
        stage=stage, gold_case=case, payload=payload, metrics=metrics
    )
    # ALL-CASE primary: zero if incomplete
    metrics["primary_f1_all_case"] = float(metrics["primary_f1"]) if complete else 0.0
    return metrics


def _zero_prf(gold: Sequence[Any], pred: Sequence[Any]) -> dict[str, float | int]:
    return _prf(0, len(pred), len(gold))


def aggregate_stage_scores(
    case_scores: Sequence[dict[str, Any]],
    *,
    seed: int = 0,
) -> dict[str, Any]:
    complete = [c for c in case_scores if c.get("complete")]
    all_rows = list(case_scores)

    def collect(rows: Sequence[dict[str, Any]], key: str) -> list[float]:
        out: list[float] = []
        for r in rows:
            val: Any = r
            for part in key.split("."):
                if not isinstance(val, dict):
                    val = None
                    break
                val = val.get(part)
            if isinstance(val, (int, float)):
                out.append(float(val))
        return out

    primary_complete = collect(complete, "primary_f1")
    primary_all = collect(all_rows, "primary_f1_all_case")
    empty_rate_complete = (
        sum(1 for c in complete if c.get("empty_lists")) / len(complete) if complete else None
    )
    empty_rate_all = sum(1 for c in all_rows if c.get("empty_lists")) / len(all_rows)

    # by kind
    by_kind: dict[str, list[float]] = defaultdict(list)
    for c in all_rows:
        by_kind[str(c.get("kind") or "unknown")].append(float(c["primary_f1_all_case"]))

    # failure frequencies
    fail_counter: Counter[str] = Counter()
    fail_examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in all_rows:
        for f in c.get("failures") or []:
            code = str(f.get("code"))
            fail_counter[code] += 1
            if len(fail_examples[code]) < 3:
                fail_examples[code].append(f)

    return {
        "n_all": len(all_rows),
        "n_complete": len(complete),
        "complete_output_score": {
            "primary_f1": bootstrap_ci(primary_complete, seed=seed),
            "empty_output_rate": empty_rate_complete,
        },
        "all_case_score": {
            "primary_f1": bootstrap_ci(primary_all, seed=seed + 1),
            "empty_output_rate": empty_rate_all,
        },
        "by_kind_all_case_f1": {
            kind: bootstrap_ci(vals, seed=seed + 2) for kind, vals in sorted(by_kind.items())
        },
        "failure_taxonomy": {
            "counts": dict(fail_counter.most_common()),
            "examples": {k: v for k, v in fail_examples.items()},
        },
    }


def decide_lora_gate(report: dict[str, Any]) -> dict[str, Any]:
    """Decisione non basata su soglia unica; euristica multi-criterio documentata."""

    stages = report.get("stages") or {}
    schema_ok = True
    semantic_low = False
    empty_bias = False
    coherent_errors = False
    wide_ci = False
    reasons: list[str] = []

    primary_means = []
    for stage, block in stages.items():
        agg = block.get("aggregate") or {}
        all_score = (agg.get("all_case_score") or {}).get("primary_f1") or {}
        mean = all_score.get("mean")
        low, high = all_score.get("low"), all_score.get("high")
        if mean is not None:
            primary_means.append(mean)
            if mean < 0.35:
                semantic_low = True
                reasons.append(f"{stage}: primary_f1_all_case={mean:.3f} < 0.35")
            if low is not None and high is not None and (high - low) > 0.35:
                wide_ci = True
                reasons.append(f"{stage}: wide CI [{low:.3f},{high:.3f}]")
        empty = (agg.get("all_case_score") or {}).get("empty_output_rate")
        if empty is not None and empty >= 0.4:
            empty_bias = True
            reasons.append(f"{stage}: empty_output_rate={empty:.3f}")
        fails = (agg.get("failure_taxonomy") or {}).get("counts") or {}
        top = list(fails.keys())[:3]
        if any(
            code in fails
            for code in (
                "MISSED_EVIDENCE",
                "WRONG_COUNT_VALUE",
                "MISSING_REQUIRED_RELATION",
                "UNDER_EXTRACTION",
                "CORRECT_SCHEMA_WRONG_CONTENT",
            )
        ):
            coherent_errors = True
        if top:
            reasons.append(f"{stage}: top_failures={top}")

    mean_overall = sum(primary_means) / len(primary_means) if primary_means else 0.0

    # Decision tree
    if mean_overall < 0.05 and empty_bias:
        decision = "STOP_OR_CHANGE_MODEL"
        rationale = (
            "Semantica quasi nulla con forte empty-output bias: "
            "task P0 ristretto potrebbe non bastare senza cambio modello/prompt radicale."
        )
    elif wide_ci and mean_overall < 0.5:
        decision = "EXPAND_DEV_SET"
        rationale = (
            "Intervalli bootstrap ampi e supporto limitato (n=39): "
            "espandere development set prima di claim su LoRA."
        )
    elif empty_bias and mean_overall < 0.4:
        decision = "REVISE_PROMPT_OR_SCHEMA"
        rationale = (
            "Constrained decoding produce spesso liste vuote: "
            "rivedere prompt stage / few-shot SHORT / enum prima del training."
        )
    elif schema_ok and semantic_low and coherent_errors:
        decision = "GO_LORA_P0"
        rationale = (
            "Schema stabile (C), semantica insufficiente, errori concentrati in "
            "task supervisionabili (evidence/entity/count/relations). "
            "Primo adapter P0 giustificato; i 39 casi restano DEV, non train."
        )
    elif not semantic_low:
        decision = "REVISE_PROMPT_OR_SCHEMA"
        rationale = (
            "Semantica non chiaramente insufficiente su tutti gli stage; "
            "migliorare prompt/schema o metriche prima del LoRA."
        )
    else:
        decision = "EXPAND_DEV_SET"
        rationale = "Segnale misto: espandere DEV e ripetere scoring."

    return {
        "decision": decision,
        "overall_primary_f1_all_case_mean": mean_overall,
        "rationale": rationale,
        "reasons": reasons,
        "lora_task_scope_if_go": [
            "TASK_EVIDENCE",
            "TASK_ENTITY_COUNT",
            "TASK_FACTOR_ENDPOINT",
            "TASK_EXPLICIT_RELATIONS",
        ],
        "dev_set_policy": (
            "I 39 casi restano DEVELOPMENT / B4_CONSTRAINED_DEV; "
            "non usare per training né come test finale."
        ),
    }


__all__ = [
    "DECISIVE_RELATIONS",
    "SCORER_VERSION",
    "aggregate_stage_scores",
    "bootstrap_ci",
    "decide_lora_gate",
    "extract_json",
    "score_case_stage",
]
