"""Paths, seeds, and constants for task corpora."""

from __future__ import annotations

import os
from pathlib import Path

from ntruth.task_corpora.readiness import (
    CANONICAL_FORBIDDEN_GOLD_USES,
    ROOT_CONTRACT_MERGE_SHA,
)

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

# Public/silver corpora (PRD v7 §14.1) never satisfy these N-Truth gold roles.
FORBIDDEN_GOLD_USES = (
    "experimental_unit_gold",
    "independent_n_gold",
    "pseudoreplication_verdict_gold",
    "allocation_gold",
    "biological_independence_gold",
    "interference_gold",
    "estimand_gold",
)

if not set(CANONICAL_FORBIDDEN_GOLD_USES).issubset(set(FORBIDDEN_GOLD_USES)):
    raise RuntimeError("FORBIDDEN_GOLD_USES must cover canonical root gold bans")

# Reality Gate: root owns the full schema (packages/ntruth/reality_gate).
# Dataset manifests project status only (task_corpora.readiness.DatasetReadinessProjection).
# PROVISIONAL_* string retained as a deprecated alias for older manifests.
PROVISIONAL_REALITY_GATE_REF = "prd_v7_section_0.7_provisional_dataset_manifest"
ROOT_REALITY_GATE_REF = f"reality_gate@main:{ROOT_CONTRACT_MERGE_SHA[:12]}"
REALITY_GATE_STATUS_BLOCKED = "BLOCKED"
ENGINEERING_READINESS_C0_C1 = "VERIFIED_FOR_C0_C1"
DATA_READINESS_BLOCKED = "BLOCKED"
SCIENTIFIC_VALIDATION_NOT_STARTED = "NOT_STARTED"

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
