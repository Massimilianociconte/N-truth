"""Tests for filesystem operations, AppleDouble filtering, ZIP security, and Merkle manifests."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from ntruth.data.fs import (
    FSError,
    calculate_merkle_root,
    is_ignorable_metadata,
    safe_extract_zip,
    strip_single_root,
)


def test_is_ignorable_metadata():
    assert is_ignorable_metadata(".DS_Store")
    assert is_ignorable_metadata("__MACOSX")
    assert is_ignorable_metadata("._Preclinical_IE_Dataset")
    assert not is_ignorable_metadata("data.csv")
    assert not is_ignorable_metadata("train.jsonl")


def test_safe_extract_zip_normal(tmp_path: Path):
    zip_path = tmp_path / "test.zip"
    dest = tmp_path / "extracted"

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("folder/file1.txt", "hello")
        zf.writestr("folder/file2.txt", "world")

    safe_extract_zip(zip_path, dest)
    assert (dest / "folder" / "file1.txt").read_text() == "hello"
    assert (dest / "folder" / "file2.txt").read_text() == "world"


def test_safe_extract_zip_with_appledouble(tmp_path: Path):
    zip_path = tmp_path / "appledouble.zip"
    dest = tmp_path / "extracted"

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("file.txt", "content")
        zf.writestr("._file.txt", "appledouble metadata")
        zf.writestr("__MACOSX/._file.txt", "macosx metadata")

    safe_extract_zip(zip_path, dest)
    assert (dest / "file.txt").exists()
    assert not (dest / "._file.txt").exists()
    assert not (dest / "__MACOSX").exists()


def test_safe_extract_zip_path_traversal(tmp_path: Path):
    zip_path = tmp_path / "traversal.zip"
    dest = tmp_path / "extracted"

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("../evil.txt", "malicious content")

    with pytest.raises(FSError, match="path traversal"):
        safe_extract_zip(zip_path, dest)


def test_strip_single_root(tmp_path: Path):
    root_dir = tmp_path / "root"
    sub_dir = root_dir / "single_folder"
    sub_dir.mkdir(parents=True)
    (sub_dir / "data.txt").write_text("data")

    res = strip_single_root(root_dir)
    assert res == sub_dir


def test_calculate_merkle_root(tmp_path: Path):
    d1 = tmp_path / "dir1"
    d1.mkdir()
    (d1 / "a.txt").write_text("hello")
    (d1 / "._a.txt").write_text("metadata")  # Ignored

    r1 = calculate_merkle_root([d1])

    d2 = tmp_path / "dir2"
    d2.mkdir()
    (d2 / "a.txt").write_text("hello")

    r2 = calculate_merkle_root([d2])

    assert r1 == r2
