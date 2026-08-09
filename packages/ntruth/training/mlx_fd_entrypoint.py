"""Child-only MLX entrypoint that consumes inherited anonymous JSONL files.

The parent process content-addresses and copies staged JSONL bytes into unlinked
files.  This module reads only those inherited descriptors, then lazily imports
the pinned MLX-LM runtime and replaces its path-based dataset loader.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any

FD_ENV = "NTRUTH_MLX_JSONL_FDS"
FD_SENTINEL = "ntruth://mlx/inherited-jsonl-fds/v1"
PINNED_MLX_LM_VERSION = "0.31.3"
_ALLOWED_SPLIT_SETS = {("train", "valid"), ("test",)}


class InheritedFDContractError(RuntimeError):
    """The child did not receive the exact anonymous JSONL descriptor set."""


def expected_splits_from_config(config: Mapping[str, Any]) -> tuple[str, ...]:
    train = config.get("train") is True
    test = config.get("test") is True
    if train == test:
        raise InheritedFDContractError("exactly one MLX consumer mode is required: train or test")
    return ("train", "valid") if train else ("test",)


def _validated_fd_map(
    *,
    expected_splits: tuple[str, ...],
    environment: Mapping[str, str],
) -> dict[str, int]:
    if expected_splits not in _ALLOWED_SPLIT_SETS:
        raise InheritedFDContractError("unsupported inherited FD split contract")
    raw = environment.get(FD_ENV)
    if not isinstance(raw, str) or not raw:
        raise InheritedFDContractError("exact inherited FD mapping is missing")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InheritedFDContractError("inherited FD mapping is invalid JSON") from exc
    if not isinstance(parsed, dict) or set(parsed) != set(expected_splits):
        raise InheritedFDContractError("inherited FD mapping has missing or extra split entries")
    mapping: dict[str, int] = {}
    for split in expected_splits:
        descriptor = parsed.get(split)
        if isinstance(descriptor, bool) or not isinstance(descriptor, int) or descriptor < 0:
            raise InheritedFDContractError(f"inherited FD is invalid for split {split}")
        mapping[split] = descriptor
    if len(set(mapping.values())) != len(mapping):
        raise InheritedFDContractError("inherited FD mapping contains descriptor aliases")
    return mapping


def read_inherited_jsonl(
    *,
    expected_splits: tuple[str, ...],
    environment: Mapping[str, str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Read exact JSON rows from anonymous inherited files, never from paths."""

    effective_environment = os.environ if environment is None else environment
    mapping = _validated_fd_map(
        expected_splits=expected_splits,
        environment=effective_environment,
    )
    rows_by_split: dict[str, list[dict[str, Any]]] = {}
    for split in expected_splits:
        descriptor = mapping[split]
        try:
            metadata = os.fstat(descriptor)
        except Exception as exc:
            raise InheritedFDContractError(f"inherited FD is not open for split {split}") from exc
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 0:
            raise InheritedFDContractError(
                f"inherited FD is not an anonymous regular file for split {split}"
            )
        try:
            duplicate = os.dup(descriptor)
        except Exception as exc:
            raise InheritedFDContractError(
                f"inherited FD cannot be duplicated for split {split}"
            ) from exc
        active_exception: BaseException | None = None
        try:
            try:
                with os.fdopen(duplicate, "rb", closefd=False) as handle:
                    os.lseek(handle.fileno(), 0, os.SEEK_SET)
                    rows: list[dict[str, Any]] = []
                    for line_number, line in enumerate(handle, 1):
                        if not line.strip():
                            continue
                        try:
                            row = json.loads(line)
                        except Exception as exc:
                            raise InheritedFDContractError(
                                f"inherited JSONL invalid at {split}:{line_number}"
                            ) from exc
                        if not isinstance(row, dict):
                            raise InheritedFDContractError(
                                f"inherited JSONL row is not an object at {split}:{line_number}"
                            )
                        rows.append(row)
            except InheritedFDContractError:
                raise
            except Exception as exc:
                raise InheritedFDContractError(
                    f"inherited JSONL unreadable for split {split}"
                ) from exc
        except BaseException as exc:
            active_exception = exc
            raise
        finally:
            try:
                os.close(duplicate)
            except Exception as exc:
                if active_exception is None:
                    raise InheritedFDContractError(
                        f"inherited FD cleanup failed for split {split}"
                    ) from exc
        if not rows:
            raise InheritedFDContractError(f"inherited JSONL is empty for split {split}")
        rows_by_split[split] = rows
    return rows_by_split


def bind_fd_dataset_loader(
    lora_module: Any,
    dataset_module: Any,
    rows_by_split: Mapping[str, list[dict[str, Any]]],
) -> None:
    """Replace MLX-LM's already-bound path loader with the exact FD rows."""

    row_splits = tuple(rows_by_split)
    if row_splits not in _ALLOWED_SPLIT_SETS:
        raise InheritedFDContractError("FD rows have a missing or extra split")

    def load_dataset(args: Any, tokenizer: Any) -> tuple[Any, Any, Any]:
        if getattr(args, "data", None) != FD_SENTINEL:
            raise InheritedFDContractError("MLX data config is not the inherited-FD sentinel")
        expected_splits = ("train", "valid") if getattr(args, "train", False) else ("test",)
        if getattr(args, "train", False) == getattr(args, "test", False):
            raise InheritedFDContractError("MLX consumer mode is not exact")
        if tuple(rows_by_split) != expected_splits:
            raise InheritedFDContractError("MLX mode and inherited FD rows do not match")
        datasets: list[Any] = []
        for split in ("train", "valid", "test"):
            rows = rows_by_split.get(split)
            datasets.append(
                dataset_module.create_dataset(rows, tokenizer, args) if rows is not None else []
            )
        return datasets[0], datasets[1], datasets[2]

    lora_module.load_dataset = load_dataset


def _config_path() -> Path:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config", type=Path, required=True)
    arguments = parser.parse_args()
    path = arguments.config.absolute()
    if path.is_symlink() or not path.is_file():
        raise InheritedFDContractError("MLX FD config is absent or symlinked")
    return path


def main() -> None:
    config_path = _config_path()
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InheritedFDContractError("MLX FD config is not valid JSON") from exc
    if not isinstance(config, dict) or config.get("data") != FD_SENTINEL:
        raise InheritedFDContractError("MLX FD config lacks the data sentinel")
    expected_splits = expected_splits_from_config(config)
    rows = read_inherited_jsonl(expected_splits=expected_splits)

    try:
        installed_version = importlib.metadata.version("mlx-lm")
    except importlib.metadata.PackageNotFoundError as exc:
        raise InheritedFDContractError("pinned mlx-lm runtime is not installed") from exc
    if installed_version != PINNED_MLX_LM_VERSION:
        raise InheritedFDContractError(f"mlx-lm version mismatch: expected {PINNED_MLX_LM_VERSION}")

    # These imports are intentionally child-only and occur after the FD contract.
    from mlx_lm import lora as lora_module
    from mlx_lm.tuner import datasets as dataset_module

    bind_fd_dataset_loader(lora_module, dataset_module, rows)
    lora_module.main()


if __name__ == "__main__":
    main()
