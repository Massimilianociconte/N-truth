from __future__ import annotations

import os
from pathlib import Path

from ntruth.data.config import configure_external_cache_environment


def test_configure_external_cache_environment_keeps_all_writable_caches_on_root(
    tmp_path: Path,
) -> None:
    root = tmp_path / "dataset-root"

    configured = configure_external_cache_environment(root)

    expected_keys = {
        "HF_HOME",
        "HF_DATASETS_CACHE",
        "HF_HUB_CACHE",
        "HUGGINGFACE_HUB_CACHE",
        "TRANSFORMERS_CACHE",
        "XDG_CACHE_HOME",
        "PIP_CACHE_DIR",
        "UV_CACHE_DIR",
        "TMPDIR",
        "TEMP",
        "TMP",
    }
    assert set(configured) == expected_keys
    for key, raw_path in configured.items():
        path = Path(raw_path)
        assert os.environ[key] == raw_path
        assert path.is_dir()
        assert path.is_relative_to(root.resolve())
