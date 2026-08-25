"""Integration: build entity_roles from real stick snapshot when available."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from ntruth.task_corpora.adapters.sourcedata_entity_roles import build_sourcedata_entity_roles
from ntruth.task_corpora.cli import main

STICK = Path(os.environ.get("NTRUTH_DATA_ROOT", "/Volumes/FLASH128/N-Truth-Datasets"))
SRC = STICK / "training_ready" / "sourcedata_multitask" / "train" / "records.jsonl"


@pytest.mark.skipif(not SRC.exists(), reason="SourceData multitask snapshot not mounted")
def test_stick_build_and_second_run_idempotent():
    m1 = build_sourcedata_entity_roles(STICK)
    m2 = build_sourcedata_entity_roles(STICK)
    assert m1.records_sha256 == m2.records_sha256
    assert m1.record_counts["train"] > 0
    assert sum(m1.record_counts.values()) > 0
    # licence blocks training_eligible even on train split
    out = STICK / "task_corpora" / "entity_roles" / "sourcedata" / "v2.0.3" / "train.jsonl"
    first = json.loads(out.open().readline())
    assert first["authority_level"] == "AUXILIARY"
    assert first["training_eligible"] is False
    assert main(["validate", "--root", str(STICK), "--task", "entity_roles"]) == 0
