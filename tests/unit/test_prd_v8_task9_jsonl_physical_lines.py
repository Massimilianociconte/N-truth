from __future__ import annotations

import json
from pathlib import Path

import pytest
import test_prd_v8_task5_protected_runtime as protected_fixtures
import test_prd_v8_training_records_splits as record_fixtures

import ntruth.training.mlx_runtime as runtime
from ntruth.governance.lineage import CorpusSplit
from ntruth.parser_ai.contract import ParserAIInput
from ntruth.training.mlx_dataset import export_mlx_dataset
from ntruth.training.preparation import prepare_dataset
from ntruth.training.protected_evaluation import (
    ProtectedEvaluationSnapshotManifest,
    validate_protected_evaluation_snapshot,
)
from ntruth.training.records import (
    DatasetFormatError,
    SupervisedRecord,
    dumps_prepared_jsonl,
    dumps_supervised_jsonl,
    loads_supervised_jsonl,
)

_SEPARATORS = "alpha\u2028beta\u2029gamma"


def _supervised_record(record_id: str = "a-unicode") -> SupervisedRecord:
    return record_fixtures._record(
        record_id,
        CorpusSplit.TRAIN,
        training=True,
        input_text=ParserAIInput(metadata={"physical_line": _SEPARATORS}).model_dump_json(),
    )


def _export_chat_jsonl(tmp_path: Path) -> Path:
    dataset = prepare_dataset((_supervised_record(),))
    output = tmp_path / "mlx"
    export_mlx_dataset(dataset, output)
    return output / "train.jsonl"


def _read_runtime_jsonl(reader: str, path: Path) -> object:
    if reader == "profile":
        return runtime._jsonl_profile(path)
    if reader == "iter":
        return tuple(runtime.iter_jsonl(path))
    return tuple(
        runtime.iter_verified_jsonl(
            path,
            expected_sha256=runtime.sha256_file(path),
        )
    )


def _resign_protected_payload(
    payload_path: Path,
    manifest: ProtectedEvaluationSnapshotManifest,
) -> ProtectedEvaluationSnapshotManifest:
    raw = manifest.model_dump(mode="json")
    raw.update(
        {
            "snapshot_id": "",
            "snapshot_sha256": "",
            "payload_sha256": runtime.sha256_file(payload_path),
            "payload_size_bytes": payload_path.stat().st_size,
        }
    )
    updated = ProtectedEvaluationSnapshotManifest.model_validate(raw)
    (payload_path.parent / "protected-evaluation-manifest.json").write_text(
        json.dumps(updated.model_dump(mode="json"), sort_keys=True),
        encoding="utf-8",
    )
    return updated


def test_supervised_jsonl_round_trip_preserves_unicode_separators_and_one_lf() -> None:
    record = _supervised_record()
    payload = dumps_supervised_jsonl((record,))
    raw = payload.encode("utf-8")

    assert raw.count(b"\n") == 1
    assert "\u2028" in payload and "\u2029" in payload
    assert loads_supervised_jsonl(payload) == (record,)
    assert loads_supervised_jsonl(raw[:-1] + b"\r\n") == (record,)


def test_supervised_jsonl_error_uses_physical_lf_line_number() -> None:
    valid = dumps_supervised_jsonl((_supervised_record(),)).encode("utf-8")

    with pytest.raises(DatasetFormatError) as captured:
        loads_supervised_jsonl(valid + b"\r\n{}\r\n")

    assert captured.value.line_number == 3


def test_supervised_jsonl_does_not_treat_bare_cr_as_record_boundary() -> None:
    line = dumps_supervised_jsonl((_supervised_record(),)).encode("utf-8").removesuffix(b"\n")

    with pytest.raises(DatasetFormatError) as captured:
        loads_supervised_jsonl(line + b"\r" + line + b"\n")

    assert captured.value.line_number == 1


def test_prepared_jsonl_reader_preserves_separators_crlf_and_line_number(
    tmp_path: Path,
) -> None:
    dataset = prepare_dataset((_supervised_record(),))
    raw = dumps_prepared_jsonl(dataset.records).encode("utf-8")
    path = tmp_path / "prepared-records.jsonl"
    path.write_bytes(raw[:-1] + b"\r\n")

    assert runtime._load_prepared_records(path) == dataset.records

    path.write_bytes(raw + b"\r\n{}\r\n")
    with pytest.raises(runtime.MLXPipelineError, match=r"prepared-records\.jsonl:3"):
        runtime._load_prepared_records(path)


def test_runtime_jsonl_readers_preserve_unicode_separators_and_hash(
    tmp_path: Path,
) -> None:
    path = _export_chat_jsonl(tmp_path)
    before = path.read_bytes()

    assert before.count(b"\n") == 1
    assert "\u2028".encode() in before and "\u2029".encode() in before
    assert runtime._jsonl_profile(path)["count"] == 1
    assert tuple(runtime.iter_jsonl(path)) == tuple(
        runtime.iter_verified_jsonl(path, expected_sha256=runtime.sha256_file(path))
    )
    assert path.read_bytes() == before


@pytest.mark.parametrize("reader", ("profile", "iter", "verified"))
def test_runtime_jsonl_readers_do_not_treat_bare_cr_as_record_boundary(
    tmp_path: Path,
    reader: str,
) -> None:
    path = _export_chat_jsonl(tmp_path)
    line = path.read_bytes().removesuffix(b"\n")
    path.write_bytes(line + b"\r" + line + b"\n")

    with pytest.raises(runtime.MLXPipelineError, match=r"train\.jsonl:1"):
        _read_runtime_jsonl(reader, path)


@pytest.mark.parametrize("reader", ("profile", "iter", "verified"))
def test_runtime_jsonl_errors_count_only_physical_lf(
    tmp_path: Path,
    reader: str,
) -> None:
    path = _export_chat_jsonl(tmp_path)
    path.write_bytes(path.read_bytes() + b"\r\n{\r\n")

    with pytest.raises(runtime.MLXPipelineError, match=r"train\.jsonl:3"):
        _read_runtime_jsonl(reader, path)


def test_protected_jsonl_reader_preserves_separators_crlf_and_line_number(
    tmp_path: Path,
) -> None:
    payload_path, source_path, manifest = protected_fixtures._write_protected_snapshot(
        tmp_path,
        rows=({"record_id": "protected-1", "note": _SEPARATORS},),
    )
    raw = payload_path.read_bytes()
    assert raw.count(b"\n") == 1
    assert "\u2028".encode() in raw and "\u2029".encode() in raw

    verified = validate_protected_evaluation_snapshot(
        payload_path.parent,
        declared_split="TEST",
        source_manifest_path=source_path,
    )
    assert verified.snapshot_id == manifest.snapshot_id

    payload_path.write_bytes(raw[:-1] + b"\r\n")
    _resign_protected_payload(payload_path, manifest)
    validate_protected_evaluation_snapshot(
        payload_path.parent,
        declared_split="TEST",
        source_manifest_path=source_path,
    )

    payload_path.write_bytes(raw + b"\r\n{\r\n")
    _resign_protected_payload(payload_path, manifest)
    with pytest.raises(runtime.MLXPipelineError, match=r"test\.jsonl:3"):
        validate_protected_evaluation_snapshot(
            payload_path.parent,
            declared_split="TEST",
            source_manifest_path=source_path,
        )
