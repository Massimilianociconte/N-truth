from __future__ import annotations

import json
from pathlib import Path

import pytest
import test_prd_v8_training_records_splits as split_fixtures

from ntruth.governance.lineage import CorpusSplit
from ntruth.parser_ai.contract import ParserAIInput
from ntruth.training.mlx_dataset import export_mlx_dataset
from ntruth.training.mlx_runtime import MLXPipelineError
from ntruth.training.preparation import prepare_dataset
from ntruth.training.records import PreparedDataset


def _dataset(*, validation_model_selection: bool) -> PreparedDataset:
    return prepare_dataset(
        (
            split_fixtures._record(
                "a-train",
                CorpusSplit.TRAIN,
                training=True,
                model_selection=False,
            ),
            split_fixtures._record(
                "b-validation",
                CorpusSplit.VALIDATION,
                training=True,
                model_selection=validation_model_selection,
            ),
        )
    )


def test_validation_without_model_selection_eligibility_fails_closed_before_export() -> None:
    with pytest.raises(ValueError, match=r"VALIDATION.*model[_-]selection"):
        _dataset(validation_model_selection=False)


@pytest.mark.parametrize("mutated_surface", ("prepared_record", "source_manifest"))
def test_export_revalidates_validation_eligibility_after_preparation(
    tmp_path: Path,
    mutated_surface: str,
) -> None:
    dataset = _dataset(validation_model_selection=True)
    if mutated_surface == "prepared_record":
        forged_records = tuple(
            prepared.model_copy(
                update={
                    "record": prepared.record.model_copy(update={"model_selection_eligible": False})
                }
            )
            if prepared.split is CorpusSplit.VALIDATION
            else prepared
            for prepared in dataset.records
        )
        forged = dataset.model_copy(update={"records": forged_records})
    else:
        forged_manifest_records = tuple(
            record.model_copy(update={"model_selection_eligible": False})
            if record.split is CorpusSplit.VALIDATION
            else record
            for record in dataset.manifest.records
        )
        forged = dataset.model_copy(
            update={
                "manifest": dataset.manifest.model_copy(update={"records": forged_manifest_records})
            }
        )

    with pytest.raises(MLXPipelineError, match=r"VALIDATION.*model[_-]selection"):
        export_mlx_dataset(forged, tmp_path / "forged-validation")


def test_model_selection_eligible_validation_remains_exportable(tmp_path: Path) -> None:
    snapshot = export_mlx_dataset(
        _dataset(validation_model_selection=True),
        tmp_path / "valid-validation",
    )

    assert snapshot["counts"] == {"train": 1, "valid": 1}
    assert snapshot["training_approved"] is True


def test_train_eligibility_does_not_require_model_selection_eligibility(
    tmp_path: Path,
) -> None:
    output = tmp_path / "train-purpose"
    export_mlx_dataset(_dataset(validation_model_selection=True), output)

    train_row = json.loads((output / "train.jsonl").read_text(encoding="utf-8"))
    assert train_row["record_id"] == "a-train"


def test_test_and_external_challenge_content_remain_outside_training_view(
    tmp_path: Path,
) -> None:
    protected_sentinel = "PROTECTED-CONTENT-MUST-NOT-ENTER-TRAINING-VIEW"
    baseline = _dataset(validation_model_selection=True)
    protected = (
        split_fixtures._record(
            "c-test",
            CorpusSplit.TEST,
            evaluation=True,
            input_text=ParserAIInput(
                metadata={"protected": f"{protected_sentinel}-test"}
            ).model_dump_json(),
        ),
        split_fixtures._record(
            "d-external",
            CorpusSplit.EXTERNAL_CHALLENGE,
            input_text=ParserAIInput(
                metadata={"protected": f"{protected_sentinel}-external"}
            ).model_dump_json(),
        ),
    )
    dataset = prepare_dataset(tuple(prepared.record for prepared in baseline.records) + protected)
    output = tmp_path / "protected-splits"

    snapshot = export_mlx_dataset(dataset, output)

    assert snapshot["membership_counts"]["TEST"] == 1
    assert snapshot["membership_counts"]["EXTERNAL_CHALLENGE"] == 1
    assert not (output / "test.jsonl").exists()
    assert not (output / "external.jsonl").exists()
    serialized = "\n".join(
        path.read_text(encoding="utf-8") for path in output.iterdir() if path.is_file()
    )
    assert protected_sentinel not in serialized
