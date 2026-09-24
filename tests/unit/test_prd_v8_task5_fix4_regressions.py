from __future__ import annotations

import importlib
import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import ntruth.training.mlx_runtime as runtime
from ntruth.training.mlx_dataset import create_runtime_smoke_dataset

FD_ENV = "NTRUTH_MLX_JSONL_FDS"
FD_SENTINEL = "ntruth://mlx/inherited-jsonl-fds/v1"
FD_ENTRYPOINT = "ntruth.training.mlx_fd_entrypoint"


def _entrypoint() -> Any:
    return importlib.import_module(FD_ENTRYPOINT)


def _staged_views(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    source = tmp_path / "source"
    create_runtime_smoke_dataset(source)
    verified = runtime.validate_snapshot_integrity(source, smoke_test=True)
    training = runtime.stage_verified_training_view(
        source,
        tmp_path / "training-view",
        verified_snapshot=verified,
        smoke_test=True,
    )
    validation = runtime.stage_validation_consumer_view(
        Path(str(training["path"])),
        tmp_path / "validation-view",
        training_view=training,
    )
    return training, validation


def _jsonl_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.mark.parametrize(
    ("mode", "expected_splits"),
    (("train", ("train", "valid")), ("evaluation", ("test",))),
)
def test_post_copy_entry_substitution_cannot_change_child_fd_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    expected_splits: tuple[str, ...],
) -> None:
    training, validation = _staged_views(tmp_path)
    view = training if mode == "train" else validation
    root = Path(str(view["path"]))
    original = {split: _jsonl_rows(root / f"{split}.jsonl") for split in expected_splits}
    captured: dict[str, Any] = {}

    def consume_after_substitution(command: list[str], **kwargs: Any) -> runtime.CommandResult:
        assert command == [
            sys.executable,
            "-m",
            FD_ENTRYPOINT,
            "--config",
            str(tmp_path / f"{mode}.json"),
        ]
        config = json.loads(Path(command[-1]).read_text(encoding="utf-8"))
        assert config["data"] == FD_SENTINEL
        environment = kwargs["environment"]
        fd_map = json.loads(environment[FD_ENV])
        assert tuple(fd_map) == expected_splits
        assert kwargs["pass_fds"] == tuple(fd_map[split] for split in expected_splits)
        for descriptor in kwargs["pass_fds"]:
            metadata = os.fstat(descriptor)
            assert stat.S_ISREG(metadata.st_mode)
            assert metadata.st_nlink == 0

        root.chmod(0o755)
        for split in expected_splits:
            path = root / f"{split}.jsonl"
            path.chmod(0o644)
            replacement = tmp_path / f"replacement-{mode}-{split}.jsonl"
            replacement.write_text('{"record_id":"PROTECTED-REPLACEMENT"}\n', encoding="utf-8")
            os.replace(replacement, path)

        rows = _entrypoint().read_inherited_jsonl(
            expected_splits=expected_splits,
            environment=environment,
        )
        captured["rows"] = rows
        return runtime.CommandResult(
            command=("fd-entrypoint",),
            returncode=0,
            output="Test loss 1.0",
            elapsed_seconds=0.0,
            peak_memory_gb=None,
        )

    monkeypatch.setattr(runtime, "_stream_command", consume_after_substitution)
    runtime.stream_mlx_with_sealed_view(
        {
            "model": "fixture",
            "train": mode == "train",
            "test": mode == "evaluation",
        },
        view=view,
        config_path=tmp_path / f"{mode}.json",
        cwd=tmp_path,
        log_path=tmp_path / f"{mode}.log",
    )
    assert captured["rows"] == original
    assert "PROTECTED-REPLACEMENT" not in json.dumps(captured["rows"])


@pytest.mark.parametrize("mapping_kind", ("missing", "extra"))
def test_child_rejects_non_exact_fd_mapping(
    mapping_kind: str,
) -> None:
    with (
        tempfile.TemporaryFile(mode="w+b") as train_file,
        tempfile.TemporaryFile(mode="w+b") as valid_file,
        tempfile.TemporaryFile(mode="w+b") as test_file,
    ):
        mapping = {"train": train_file.fileno(), "valid": valid_file.fileno()}
        if mapping_kind == "missing":
            mapping.pop("valid")
        else:
            mapping["test"] = test_file.fileno()
        with pytest.raises(RuntimeError, match=r"exact|missing|extra"):
            _entrypoint().read_inherited_jsonl(
                expected_splits=("train", "valid"),
                environment={FD_ENV: json.dumps(mapping)},
            )


def test_child_binds_mlx_loader_to_inherited_rows_only() -> None:
    entrypoint = _entrypoint()
    rows = {
        "train": [{"messages": [{"role": "user", "content": "train-original"}]}],
        "valid": [{"messages": [{"role": "user", "content": "valid-original"}]}],
    }
    created: list[list[dict[str, Any]]] = []

    def create_dataset(
        values: list[dict[str, Any]], _tokenizer: object, _args: object
    ) -> list[dict[str, Any]]:
        created.append(values)
        return values

    lora_module = SimpleNamespace(load_dataset=lambda *_a: "PATH-LOADER-MUST-NOT-RUN")
    dataset_module = SimpleNamespace(create_dataset=create_dataset)
    entrypoint.bind_fd_dataset_loader(lora_module, dataset_module, rows)
    train, valid, test = lora_module.load_dataset(
        SimpleNamespace(train=True, test=False, data=FD_SENTINEL), object()
    )
    assert (train, valid, test) == (rows["train"], rows["valid"], [])
    assert created == [rows["train"], rows["valid"]]


@pytest.mark.parametrize("outcome", ("normal", "popen_failure", "nonzero"))
def test_anonymous_files_close_exactly_once_for_every_subprocess_outcome(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
) -> None:
    training, _validation = _staged_views(tmp_path)
    real_temporary_file = tempfile.TemporaryFile
    tracked: list[Any] = []

    class TrackedAnonymousFile:
        def __init__(self) -> None:
            self.handle = real_temporary_file(mode="w+b")
            self.close_calls = 0

        def __getattr__(self, name: str) -> Any:
            return getattr(self.handle, name)

        def __enter__(self) -> TrackedAnonymousFile:
            return self

        def __exit__(self, *_args: Any) -> None:
            self.close()

        def close(self) -> None:
            self.close_calls += 1
            self.handle.close()

    def temporary_file(**_kwargs: Any) -> TrackedAnonymousFile:
        value = TrackedAnonymousFile()
        tracked.append(value)
        return value

    monkeypatch.setattr(
        runtime,
        "tempfile",
        SimpleNamespace(TemporaryFile=temporary_file),
        raising=False,
    )
    inherited_fds: tuple[int, ...] = ()

    def stream(_command: list[str], **kwargs: Any) -> runtime.CommandResult:
        nonlocal inherited_fds
        inherited_fds = kwargs["pass_fds"]
        if outcome == "popen_failure":
            raise OSError("Popen failed")
        if outcome == "nonzero":
            raise runtime.MLXPipelineError("command MLX failed (7)")
        return runtime.CommandResult(
            command=("fd-entrypoint",),
            returncode=0,
            output="ok",
            elapsed_seconds=0.0,
            peak_memory_gb=None,
        )

    monkeypatch.setattr(runtime, "_stream_command", stream)

    def call() -> runtime.CommandResult:
        return runtime.stream_mlx_with_sealed_view(
            {"model": "fixture", "train": True, "test": False},
            view=training,
            config_path=tmp_path / "train.json",
            cwd=tmp_path,
            log_path=tmp_path / "train.log",
        )

    if outcome == "normal":
        call()
    else:
        with pytest.raises((OSError, runtime.MLXPipelineError)):
            call()
    assert len(tracked) == 2
    assert all(item.close_calls == 1 for item in tracked)
    for descriptor in inherited_fds:
        with pytest.raises(OSError):
            os.fstat(descriptor)


def test_parent_handoff_never_exposes_a_directory_or_dataset_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    training, _validation = _staged_views(tmp_path)
    observed: dict[str, Any] = {}

    def inspect_handoff(command: list[str], **kwargs: Any) -> runtime.CommandResult:
        observed["command"] = command
        observed["environment"] = kwargs["environment"]
        observed["pass_fds"] = kwargs["pass_fds"]
        observed["config"] = json.loads(Path(command[-1]).read_text(encoding="utf-8"))
        return runtime.CommandResult(
            command=("fd-entrypoint",),
            returncode=0,
            output="ok",
            elapsed_seconds=0.0,
            peak_memory_gb=None,
        )

    monkeypatch.setattr(runtime, "_stream_command", inspect_handoff)
    runtime.stream_mlx_with_sealed_view(
        {"model": "fixture", "train": True, "test": False},
        view=training,
        config_path=tmp_path / "train.json",
        cwd=tmp_path,
        log_path=tmp_path / "train.log",
    )
    serialized = json.dumps(observed, default=str)
    assert observed["config"]["data"] == FD_SENTINEL
    assert str(training["path"]) not in serialized
    assert "/dev/fd/" not in serialized
    assert observed["command"][2] == FD_ENTRYPOINT
