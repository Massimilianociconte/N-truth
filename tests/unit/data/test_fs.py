"""Tests for filesystem operations, AppleDouble filtering, ZIP security, and Merkle manifests."""

from __future__ import annotations

import os
import zipfile
from hashlib import sha256
from pathlib import Path
from stat import S_IFIFO, S_IFLNK

import pytest

import ntruth.data.fs as fs_module
from ntruth.data.fs import (
    FSError,
    calculate_merkle_root,
    canonical_file_manifest,
    is_ignorable_metadata,
    safe_extract_zip,
    strip_single_root,
)


def test_is_ignorable_metadata():
    assert is_ignorable_metadata(".DS_Store")
    assert is_ignorable_metadata(".ds_store")
    assert is_ignorable_metadata("__MACOSX")
    assert is_ignorable_metadata("__macosx")
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


def test_safe_extract_zip_rejects_unix_symlink(tmp_path: Path):
    zip_path = tmp_path / "symlink.zip"
    dest = tmp_path / "extracted"
    symlink = zipfile.ZipInfo("linked.txt")
    symlink.create_system = 3
    symlink.external_attr = (S_IFLNK | 0o777) << 16

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(symlink, "target.txt")

    with pytest.raises(FSError, match="Symlinks in ZIP archives are blocked"):
        safe_extract_zip(zip_path, dest)
    assert not (dest / "linked.txt").exists()


def test_safe_extract_zip_rejects_unix_special_file(tmp_path: Path):
    zip_path = tmp_path / "special.zip"
    dest = tmp_path / "extracted"
    fifo = zipfile.ZipInfo("named-pipe")
    fifo.create_system = 3
    fifo.external_attr = (S_IFIFO | 0o600) << 16

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(fifo, b"")

    with pytest.raises(FSError, match="Special files in ZIP archives are blocked"):
        safe_extract_zip(zip_path, dest)
    assert not (dest / "named-pipe").exists()


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


def test_canonical_file_manifest_namespaces_roots_and_records_integrity(tmp_path: Path):
    raw = tmp_path / "raw"
    processed = tmp_path / "processed"
    raw.mkdir()
    processed.mkdir()
    (raw / "shared.txt").write_bytes(b"hello")
    (processed / "shared.txt").write_bytes(b"world")

    manifest = canonical_file_manifest([processed, raw])

    assert manifest == [
        {
            "path": "processed/shared.txt",
            "sha256": "486ea46224d1bb4fb680f34f7c9ad96a8f24ec88be73ea8e5a6c65260e9cb8a7",
            "size_bytes": 5,
        },
        {
            "path": "raw/shared.txt",
            "sha256": "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
            "size_bytes": 5,
        },
    ]


def test_canonical_manifest_excludes_noncanonical_trees_and_temporary_files(tmp_path: Path):
    canonical = tmp_path / "raw" / "dataset.jsonl"
    canonical.parent.mkdir()
    canonical.write_text("canonical", encoding="utf-8")

    excluded_files = [
        tmp_path / "raw" / ".DS_Store",
        tmp_path / "raw" / "._dataset.jsonl",
        tmp_path / "raw" / "__MACOSX" / "metadata",
        tmp_path / "raw" / ".dataset.extract.123" / "partial.jsonl",
        tmp_path / "raw" / "download.zip.part",
        tmp_path / "raw" / "download-2.zip.PART",
        tmp_path / "raw" / "logs" / "run.log",
        tmp_path / "raw" / "LOGS" / "run-2.log",
        tmp_path / "raw" / "run-history" / "run.json",
        tmp_path / "raw" / "quarantine" / "suspect.jsonl",
        tmp_path / "raw" / "temporary" / "scratch.jsonl",
    ]
    for path in excluded_files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("noncanonical", encoding="utf-8")

    manifest_before = canonical_file_manifest([tmp_path / "raw"])
    merkle_before = calculate_merkle_root([tmp_path / "raw"])
    for path in reversed(excluded_files):
        path.unlink()
    manifest_after = canonical_file_manifest([tmp_path / "raw"])
    merkle_after = calculate_merkle_root([tmp_path / "raw"])

    assert manifest_before == [
        {
            "path": "dataset.jsonl",
            "sha256": sha256(b"canonical").hexdigest(),
            "size_bytes": 9,
        }
    ]
    assert manifest_after == manifest_before
    assert merkle_after == merkle_before


def test_canonical_file_manifest_rejects_symlinks(tmp_path: Path):
    canonical_root = tmp_path / "raw"
    canonical_root.mkdir()
    external = tmp_path / "external.txt"
    external.write_text("external", encoding="utf-8")
    (canonical_root / "linked.txt").symlink_to(external)

    with pytest.raises(FSError, match="Symlink"):
        canonical_file_manifest([canonical_root])


def test_canonical_file_manifest_accepts_file_symlinks_between_declared_roots(tmp_path: Path):
    raw = tmp_path / "raw"
    processed = tmp_path / "processed"
    raw.mkdir()
    processed.mkdir()
    source = raw / "data.jsonl"
    source.write_text("canonical", encoding="utf-8")
    (processed / "data.jsonl").symlink_to(source)

    manifest = canonical_file_manifest([raw, processed])

    assert [entry["path"] for entry in manifest] == ["processed/data.jsonl", "raw/data.jsonl"]
    assert manifest[0]["sha256"] == manifest[1]["sha256"]


def test_canonical_file_manifest_rejects_symlinked_directories(tmp_path: Path):
    canonical_root = tmp_path / "raw"
    canonical_root.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    (external / "data.txt").write_text("external", encoding="utf-8")
    (canonical_root / "linked").symlink_to(external, target_is_directory=True)

    with pytest.raises(FSError, match="Symlink"):
        canonical_file_manifest([canonical_root])


def test_canonical_file_manifest_uses_filename_once_for_file_roots(tmp_path: Path):
    splits = tmp_path / "splits.json"
    splits.write_text("{}", encoding="utf-8")

    manifest = canonical_file_manifest([splits])

    assert manifest == [
        {
            "path": "splits.json",
            "sha256": "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
            "size_bytes": 2,
        }
    ]


def test_canonical_file_manifest_rejects_missing_declared_root(tmp_path: Path):
    present = tmp_path / "raw"
    present.mkdir()

    with pytest.raises(FSError, match="Canonical root is missing"):
        canonical_file_manifest([present, tmp_path / "processed"])


def test_canonical_file_manifest_rejects_path_replacement_during_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    canonical_root = tmp_path / "raw"
    canonical_root.mkdir()
    canonical_file = canonical_root / "data.jsonl"
    canonical_file.write_bytes(b"original")
    replacement = canonical_root / "replacement.jsonl"
    replacement.write_bytes(b"replacement-is-longer")
    original_read = fs_module.os.read
    replaced = False

    def replace_path_then_read(descriptor: int, size: int) -> bytes:
        nonlocal replaced
        if not replaced:
            replaced = True
            fs_module.os.replace(replacement, canonical_file)
        return original_read(descriptor, size)

    monkeypatch.setattr(fs_module.os, "read", replace_path_then_read)

    with pytest.raises(FSError, match=r"changed.*(?:manifest|use)"):
        canonical_file_manifest([canonical_root])


def test_canonical_file_manifest_rejects_parent_symlink_swap_before_file_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = tmp_path / "dataset-root"
    canonical_root = root / "raw"
    canonical_root.mkdir(parents=True)
    (canonical_root / "data.txt").write_bytes(b"trusted")
    external = tmp_path / "external"
    external.mkdir()
    (external / "data.txt").write_bytes(b"untrusted")
    parked = root / "raw-parked"
    original_open = fs_module.os.open
    swapped = False

    def swap_parent_then_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        nonlocal swapped
        if not swapped and str(path).endswith("data.txt"):
            swapped = True
            canonical_root.replace(parked)
            canonical_root.symlink_to(external, target_is_directory=True)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(fs_module.os, "open", swap_parent_then_open)

    with pytest.raises(FSError, match=r"changed.*(?:manifest|use)"):
        canonical_file_manifest([canonical_root])


def test_canonical_file_manifest_rejects_completed_directory_replacement_during_later_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    canonical_root = tmp_path / "raw"
    first = canonical_root / "a"
    later = canonical_root / "b"
    first.mkdir(parents=True)
    later.mkdir()
    (first / "first.txt").write_bytes(b"one!")
    (later / "later.txt").write_bytes(b"later")
    parked = canonical_root / "a-parked"
    replacement = tmp_path / "replacement-a"
    replacement.mkdir()
    (replacement / "first.txt").write_bytes(b"replacement")
    original_read = fs_module.os.read
    swapped = False

    def replace_completed_directory_then_read(descriptor: int, size: int) -> bytes:
        nonlocal swapped
        if not swapped and os.fstat(descriptor).st_size == len(b"later"):
            swapped = True
            first.replace(parked)
            replacement.replace(first)
        return original_read(descriptor, size)

    monkeypatch.setattr(fs_module.os, "read", replace_completed_directory_then_read)

    with pytest.raises(FSError, match=r"directory changed.*snapshot|snapshot.*changed"):
        canonical_file_manifest([canonical_root])


def test_canonical_file_manifest_closes_retained_directories_after_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    canonical_root = tmp_path / "raw"
    (canonical_root / "a").mkdir(parents=True)
    (canonical_root / "b").mkdir()
    original_open = fs_module.os.open
    original_listdir = fs_module.os.listdir
    retained_descriptors: dict[int, str] = {}

    def track_directory_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        descriptor = original_open(path, flags, *args, **kwargs)
        if flags & fs_module.os.O_DIRECTORY and path in {"a", "b"}:
            retained_descriptors[descriptor] = str(path)
        return descriptor

    def fail_while_enumerating_second_directory(path: object) -> list[str]:
        if isinstance(path, int) and retained_descriptors.get(path) == "b":
            raise OSError("injected enumeration failure")
        return original_listdir(path)

    monkeypatch.setattr(fs_module.os, "open", track_directory_open)
    monkeypatch.setattr(fs_module.os, "listdir", fail_while_enumerating_second_directory)

    with pytest.raises(FSError, match="cannot be enumerated"):
        canonical_file_manifest([canonical_root])

    assert set(retained_descriptors.values()) == {"a", "b"}
    for descriptor in retained_descriptors:
        with pytest.raises(OSError):
            os.fstat(descriptor)
