"""Tests for TAR archive extraction and security limits."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from ntruth.data.fs import FSError, safe_extract_tar


def test_safe_extract_tar_normal(tmp_path: Path):
    tar_path = tmp_path / "test.tar.gz"
    dest = tmp_path / "extracted"

    file_a = tmp_path / "a.txt"
    file_a.write_text("hello tar")

    with tarfile.open(tar_path, "w:gz") as tf:
        tf.add(file_a, arcname="folder/a.txt")

    safe_extract_tar(tar_path, dest)
    assert (dest / "folder" / "a.txt").read_text() == "hello tar"


def test_safe_extract_tar_absolute_path(tmp_path: Path):
    tar_path = tmp_path / "absolute.tar"
    dest = tmp_path / "extracted"

    buf = io.BytesIO(b"hello")
    with tarfile.open(tar_path, "w") as tf:
        ti = tarfile.TarInfo(name="/etc/passwd")
        ti.size = 5
        tf.addfile(ti, fileobj=buf)

    with pytest.raises(FSError, match="Unsafe absolute path"):
        safe_extract_tar(tar_path, dest)
