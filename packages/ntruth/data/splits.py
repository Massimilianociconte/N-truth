"""Group-stratified multilabel splitting, deterministic tie-breakers, and anti-leakage invariants."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

DEFAULT_SEED = "20260803"


class SplitError(RuntimeError):
    """Split calculation or validation failure."""


def _stable_hash(seed: str, group_id: str) -> str:
    return hashlib.sha256(f"{seed}\0{group_id}".encode("utf-8")).hexdigest()


def stable_split(
    group_ids: Sequence[str],
    seed: str = DEFAULT_SEED,
    ratios: tuple[int, int, int] = (80, 10, 10),
) -> dict[str, str]:
    if len(ratios) != 3 or any(x < 0 for x in ratios) or sum(ratios) <= 0:
        raise ValueError("Ratios must contain three non-negative values with positive sum")
    unique = sorted(set(str(x) for x in group_ids), key=lambda x: (_stable_hash(seed, x), x))
    n = len(unique)
    total = sum(ratios)
    exact = [n * ratio / total for ratio in ratios]
    counts = [int(val) for val in exact]
    remainder = n - sum(counts)
    order = sorted(range(3), key=lambda idx: (-(exact[idx] - counts[idx]), idx))
    for idx in order[:remainder]:
        counts[idx] += 1
    n_train, n_val, _n_test = counts
    mapping: dict[str, str] = {}
    for idx, group_id in enumerate(unique):
        if idx < n_train:
            split = "train"
        elif idx < n_train + n_val:
            split = "validation"
        else:
            split = "test"
        mapping[group_id] = split
    return mapping


def group_stratified_multilabel_split(
    group_labels: Mapping[str, Sequence[str] | Mapping[str, int]],
    seed: str = DEFAULT_SEED,
    ratios: tuple[int, int, int] = (80, 10, 10),
) -> dict[str, str]:
    """Greedy group-stratified multilabel splitting with SHA-256 tie-breaker."""
    if not group_labels:
        return {}

    sorted_groups = sorted(group_labels.keys(), key=lambda g: (_stable_hash(seed, g), g))
    all_labels: set[str] = set()
    counts_by_group: dict[str, dict[str, int]] = {}
    for g, labels in group_labels.items():
        if isinstance(labels, Mapping):
            counts_by_group[g] = dict(labels)
            all_labels.update(labels.keys())
        else:
            c: dict[str, int] = {}
            for lbl in labels:
                c[lbl] = c.get(lbl, 0) + 1
            counts_by_group[g] = c
            all_labels.update(labels)

    splits = ["train", "validation", "test"]
    total_ratio = sum(ratios)
    target_ratios = {s: ratios[i] / total_ratio for i, s in enumerate(splits)}
    split_counts: dict[str, dict[str, int]] = {s: {lbl: 0 for lbl in all_labels} for s in splits}
    group_assignment: dict[str, str] = {}

    for g in sorted_groups:
        g_counts = counts_by_group[g]
        best_split = "train"
        best_score = float("inf")

        for s in splits:
            score = 0.0
            for lbl, cnt in g_counts.items():
                current_total = sum(split_counts[sp][lbl] for sp in splits) + cnt
                target = current_total * target_ratios[s]
                diff = (split_counts[s][lbl] + cnt) - target
                score += diff * diff
            if score < best_score:
                best_score = score
                best_split = s

        group_assignment[g] = best_split
        for lbl, cnt in g_counts.items():
            split_counts[best_split][lbl] += cnt

    return group_assignment


def validate_anti_leakage(split_map: Mapping[str, str]) -> None:
    train_groups = {g for g, s in split_map.items() if s == "train"}
    val_groups = {g for g, s in split_map.items() if s == "validation"}
    test_groups = {g for g, s in split_map.items() if s in {"test", "trial"}}

    if not train_groups.isdisjoint(val_groups):
        overlap = sorted(train_groups & val_groups)
        raise SplitError(f"Leakage detected between train and validation: {overlap[:5]}")
    if not train_groups.isdisjoint(test_groups):
        overlap = sorted(train_groups & test_groups)
        raise SplitError(f"Leakage detected between train and test/trial: {overlap[:5]}")
    if not val_groups.isdisjoint(test_groups):
        overlap = sorted(val_groups & test_groups)
        raise SplitError(f"Leakage detected between validation and test/trial: {overlap[:5]}")


def load_craft_2019_shared_task_split(manifest_path: Path) -> tuple[str, dict[str, str]]:
    """Loads and validates official CRAFT Shared Task 2019 partition."""
    if not manifest_path.exists():
        raise SplitError(f"CRAFT shared task manifest missing: {manifest_path}")

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    train_dev = data.get("train_dev_pmcids", [])
    test_pmc = data.get("test_pmcids", [])

    if len(train_dev) != 67:
        raise SplitError(f"CRAFT train_dev_pmcids count must be 67, found {len(train_dev)}")
    if len(test_pmc) != 30:
        raise SplitError(f"CRAFT test_pmcids count must be 30, found {len(test_pmc)}")

    s_train_dev = set(train_dev)
    s_test = set(test_pmc)

    if not s_train_dev.isdisjoint(s_test):
        raise SplitError("CRAFT train_dev and test PMCID sets are not disjoint")
    if len(s_train_dev | s_test) != 97:
        raise SplitError(f"CRAFT total PMCID count must be 97, found {len(s_train_dev | s_test)}")

    train_val_map = stable_split(train_dev, seed=DEFAULT_SEED, ratios=(90, 10, 0))
    mapping: dict[str, str] = {}
    for pmcid in train_dev:
        mapping[pmcid] = "train" if train_val_map.get(pmcid) == "train" else "validation"
    for pmcid in test_pmc:
        mapping[pmcid] = "test"

    return "craft_shared_task_2019", mapping


def preclinie_group_id(doc_id: str) -> str:
    normalized = doc_id.strip()
    match = re.search(r"(?i)(my_pdf\d+)", normalized)
    if match:
        return match.group(1).lower()
    reduced = re.sub(
        r"(?i)(?:new)?(?:_|\^|-)?(?:method|methods|title|abstract|title\^abstract|title_abstract)$",
        "",
        normalized,
    )
    return reduced.lower() or normalized.lower()


def measeval_article_id(paragraph_id: str) -> str:
    stem = Path(paragraph_id).stem
    match = re.match(r"^(.+)-\d+$", stem)
    return match.group(1) if match else stem
