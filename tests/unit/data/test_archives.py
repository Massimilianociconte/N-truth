"""Tests for TAR archive extraction and security limits."""

from __future__ import annotations

import hashlib
import io
import json
import stat
import tarfile
import warnings
import zipfile
from pathlib import Path

import pytest

import ntruth.data.fs as fs
from ntruth.data.fs import FSError, atomic_extract_archive, safe_extract_tar


def test_safe_extract_tar_normal(tmp_path: Path):
    tar_path = tmp_path / "test.tar.gz"
    dest = tmp_path / "extracted"

    file_a = tmp_path / "a.txt"
    file_a.write_text("hello tar")

    with tarfile.open(tar_path, "w:gz") as tf:
        tf.add(file_a, arcname="folder/a.txt")

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
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


def test_safe_extract_tar_strips_dangerous_unix_permissions(tmp_path: Path):
    tar_path = tmp_path / "permissions.tar"
    dest = tmp_path / "extracted"
    payload = tarfile.TarInfo(name="payload.txt")
    payload.mode = 0o7777
    payload.size = 1

    with tarfile.open(tar_path, "w") as tf:
        tf.addfile(payload, fileobj=io.BytesIO(b"x"))

    safe_extract_tar(tar_path, dest)

    extracted_mode = stat.S_IMODE((dest / "payload.txt").stat().st_mode)
    dangerous_permissions = stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX | stat.S_IWGRP | stat.S_IWOTH
    assert extracted_mode & dangerous_permissions == 0


def test_atomic_extract_archive_restores_previous_tree_when_publish_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    archive = tmp_path / "release.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("release/new.txt", "new-data")

    destination = tmp_path / "raw"
    destination.mkdir()
    (destination / "old.txt").write_text("verified-old-data", encoding="utf-8")
    old_marker = {"dataset": "example", "revision": "verified-old"}
    (destination / ".ntruth_complete.json").write_text(json.dumps(old_marker), encoding="utf-8")

    real_replace = fs.os.replace

    def fail_new_tree_publish(source: str | Path, target: str | Path, **kwargs: object) -> None:
        if Path(source).name == "final" and Path(target).name == destination.name:
            raise OSError("injected publish failure")
        real_replace(source, target, **kwargs)

    monkeypatch.setattr(fs.os, "replace", fail_new_tree_publish)

    with pytest.raises(OSError, match="injected publish failure"):
        atomic_extract_archive(
            archive,
            destination,
            {"dataset": "example", "revision": "new-candidate"},
        )

    assert (destination / "old.txt").read_text(encoding="utf-8") == "verified-old-data"
    assert not (destination / "new.txt").exists()
    assert json.loads((destination / ".ntruth_complete.json").read_text()) == old_marker
    assert list(tmp_path.glob(".raw.extract.*")) == []


def test_atomic_extract_archive_publishes_complete_tree_and_real_marker(tmp_path: Path):
    archive = tmp_path / "release.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("release/data.txt", "canonical-data")
        zf.writestr("release/nested/labels.json", '{"label":"MEASURE"}')

    destination = tmp_path / "raw"
    destination.mkdir()
    (destination / "stale.txt").write_text("stale", encoding="utf-8")
    metadata = {
        "dataset": "example",
        "source_ref": "0123456789abcdef0123456789abcdef01234567",
    }

    atomic_extract_archive(archive, destination, metadata)

    expected_marker = {
        **metadata,
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
    }
    assert sorted(
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*")
        if path.is_file()
    ) == [".ntruth_complete.json", "data.txt", "nested/labels.json"]
    assert (destination / "data.txt").read_text(encoding="utf-8") == "canonical-data"
    assert json.loads((destination / ".ntruth_complete.json").read_text()) == expected_marker
    assert "SKIP_CHECK" not in (destination / ".ntruth_complete.json").read_text()
    assert list(tmp_path.glob(".raw.extract.*")) == []


def test_atomic_extract_archive_rejects_symlinked_parent_below_trusted_root(tmp_path: Path):
    archive = tmp_path / "release.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("release/data.txt", "canonical-data")

    trusted_root = tmp_path / "dataset-root"
    trusted_root.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    (trusted_root / "raw").symlink_to(external, target_is_directory=True)
    destination = trusted_root / "raw" / "fixture"

    with pytest.raises(FSError, match=r"symlink|without following links"):
        atomic_extract_archive(
            archive,
            destination,
            {"dataset": "fixture", "source_ref": "revision"},
            trusted_root=trusted_root,
        )

    assert list(external.iterdir()) == []


def test_atomic_extract_archive_revalidates_parent_before_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    archive = tmp_path / "release.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("release/data.txt", "canonical-data")

    trusted_root = tmp_path / "dataset-root"
    raw_parent = trusted_root / "raw"
    raw_parent.mkdir(parents=True)
    destination = raw_parent / "fixture"
    outside = tmp_path / "outside"
    outside.mkdir()
    moved_parent = outside / "raw"
    original_extract = fs._extract_archive_to_fd

    def extract_then_move_parent(
        archive_value: Path | fs.VerifiedArchiveCopy, destination_fd: int
    ) -> None:
        original_extract(archive_value, destination_fd)
        raw_parent.replace(moved_parent)

    monkeypatch.setattr(fs, "_extract_archive_to_fd", extract_then_move_parent)

    with pytest.raises(FSError, match="parent changed while in use"):
        atomic_extract_archive(
            archive,
            destination,
            {"dataset": "fixture", "source_ref": "revision"},
            trusted_root=trusted_root,
        )

    assert not (moved_parent / "fixture").exists()
    assert list(moved_parent.glob(".fixture.extract.*")) == []
