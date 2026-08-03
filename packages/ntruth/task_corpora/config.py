"""Paths, seeds, and constants for task corpora."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_DATA_ROOT = Path(os.environ.get("NTRUTH_DATA_ROOT", "/Volumes/FLASH128/N-Truth-Datasets"))
DEFAULT_SEED = "20260803"
# Canonical task-record schema / transform versions (bump together when record body changes).
SCHEMA_VERSION = "0.2.0"
TRANSFORM_VERSION = "0.2.0"
# Historical content hashes retained for lineage (not rewritten).
RECORDS_SHA256_C1_INITIAL = "14638a55e96d7dd458d312774b7b1e93072383eedf5e70147d2991eb4a7b342c"
RECORDS_SHA256_C1_USE_DECISION = "0fe9c1190b10b49b8b2cd60fe32e7718f5041fda58858d79225e9c1831642fe2"

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
