"""Paths, seeds, and constants for task corpora."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_DATA_ROOT = Path(os.environ.get("NTRUTH_DATA_ROOT", "/Volumes/FLASH128/N-Truth-Datasets"))
DEFAULT_SEED = "20260803"
TRANSFORM_VERSION = "0.1.0"

TASK_ENTITY_ROLES = "entity_roles"
TASK_ROUTING = "routing"
TASK_QUANTITIES = "quantities"
TASK_RELATIONS = "relations"
TASK_COREFERENCE = "coreference"
TASK_METHOD_INDICATORS = "method_indicators"

IMPLEMENTED_TASKS = frozenset({TASK_ENTITY_ROLES})

# Routing inventory (approved; adapters later)
ROUTING_LABELS = (
    "METHODS",
    "STATISTICAL_METHODS",
    "FIGURE_CAPTION",
    "RESULTS",
    "OTHER",
    "UNKNOWN",
)

FORBIDDEN_GOLD_USES = (
    "experimental_unit_gold",
    "independent_n_gold",
    "pseudoreplication_verdict_gold",
    "allocation_gold",
    "biological_independence_gold",
)

DEFAULT_ALLOWED_USES = (
    "encoder_pretraining",
    "token_classification",
    "span_classification",
    "adapter_development",
    "dataset_statistics",
)


def task_corpora_root(root: Path) -> Path:
    return root / "task_corpora"


def task_output_dir(root: Path, task: str) -> Path:
    return task_corpora_root(root) / task


def package_dir() -> Path:
    return Path(__file__).resolve().parent
