"""Test factory sintetica P0-alpha e anti-leakage DEV."""

from __future__ import annotations

from pathlib import Path

from ntruth.model_backends.stage_schemas import (
    CandidateRelationStage,
    EntityCountStage,
    EvidenceExtractionStage,
)
from ntruth.training.p0_synthetic import (
    generate_p0_alpha_records,
    quality_gate,
    write_snapshot,
)


def test_generate_small_snapshot_passes_gate(tmp_path: Path) -> None:
    records, report = generate_p0_alpha_records(
        n_train=80,
        n_val=20,
        seed=7,
        dev_cases_path=Path("benchmarks/fewshot_p0/cases.jsonl"),
    )
    assert report["n_train"] >= 40
    assert report["n_validation"] >= 10
    gate = quality_gate(records, report)
    assert gate["error_count"] == 0
    train_f = {r["family_id"] for r in records if r["split"] == "train"}
    val_f = {r["family_id"] for r in records if r["split"] == "validation"}
    assert not (train_f & val_f)
    # targets validate
    for r in records[:10]:
        if r["task"] == "TASK_EVIDENCE":
            EvidenceExtractionStage.model_validate(r["target"])
        elif r["task"] == "TASK_ENTITY_COUNT":
            EntityCountStage.model_validate(r["target"])
        elif r["task"] == "TASK_EXPLICIT_RELATIONS":
            CandidateRelationStage.model_validate(r["target"])


def test_write_snapshot(tmp_path: Path) -> None:
    man = write_snapshot(
        tmp_path,
        n_train=60,
        n_val=15,
        seed=3,
        dev_cases_path=Path("benchmarks/fewshot_p0/cases.jsonl"),
    )
    assert man["quality_gate"]["passed"] is True
    assert (tmp_path / "train.chat.jsonl").is_file()
    assert (tmp_path / "validation.chat.jsonl").is_file()
    assert (tmp_path / "DATASET_CARD.md").is_file()
