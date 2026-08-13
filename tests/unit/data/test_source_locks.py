"""Tests for repository-pinned public archive identities."""

from __future__ import annotations

import hashlib
import importlib
import io
import json
from contextlib import nullcontext
from pathlib import Path

import pytest

from ntruth.data.source_locks import (
    ArchiveLock,
    SourceLockError,
    calculate_raw_tree_commitment,
    ensure_pinned_archive,
    ensure_pinned_archive_verified_copy,
    load_archive_lock,
    resume_marker_matches,
    write_authenticated_resume_marker,
)


def test_verified_archive_copy_remains_bound_after_download_path_replacement(
    tmp_path: Path,
):
    root = tmp_path / "dataset-root"
    downloads = root / "downloads"
    downloads.mkdir(parents=True)
    archive = downloads / "source.zip"
    verified_bytes = b"verified archive bytes"
    archive.write_bytes(verified_bytes)
    lock = ArchiveLock(
        dataset="fixture",
        marker_dataset="fixture",
        source_ref="revision",
        url="https://example.invalid/source.zip",
        sha256=hashlib.sha256(verified_bytes).hexdigest(),
    )

    with ensure_pinned_archive_verified_copy(archive, lock, refresh=False, root=root) as verified:
        assert list(downloads.glob(".source.zip.verified.*")) == []
        replacement = downloads / "replacement.zip"
        replacement.write_bytes(b"unverified replacement bytes")
        replacement.replace(archive)
        verified.handle.seek(0)

        assert verified.handle.read() == verified_bytes
        assert verified.sha256 == lock.sha256

    assert archive.read_bytes() == b"unverified replacement bytes"
    assert list(downloads.glob(".source.zip.verified.*")) == []


@pytest.mark.parametrize(
    ("dataset", "source_ref", "expected_sha256"),
    [
        (
            "preclinie",
            "f38df55a28505a77d30eefb5b867bbfdcc9baf25",
            "3aa37a6d801d8475093c94b3d44c709d08ed0c1a60a920e230f60208f2b4d5e7",
        ),
        (
            "measeval",
            "1fa738b6bc9b72c84c88a80344ca3ab39a310a44",
            "c53b28506befad2edf6da7f9782c7711c6f955d34322425a60d3743f05d8fd57",
        ),
        (
            "craft",
            "v5.0.2",
            "56677e5110f81303642f49ec21dce9d55e38c95cef1162212514d8b2c73077f2",
        ),
    ],
)
def test_public_archive_lock_contains_observed_sha256(
    dataset: str, source_ref: str, expected_sha256: str
):
    lock = load_archive_lock(dataset, source_ref=source_ref)

    assert lock.sha256 == expected_sha256
    assert lock.source_ref == source_ref


def test_existing_archive_must_match_lock_before_use(tmp_path: Path):
    archive = tmp_path / "source.zip"
    archive.write_bytes(b"not the pinned archive")
    lock = ArchiveLock(
        dataset="fixture",
        marker_dataset="fixture",
        source_ref="revision",
        url="https://example.invalid/source.zip",
        sha256="0" * 64,
    )

    with pytest.raises(SourceLockError, match="SHA-256 mismatch"):
        ensure_pinned_archive(archive, lock, refresh=False)


def test_download_is_verified_before_existing_archive_is_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    archive = tmp_path / "source.zip"
    verified = b"expected upstream bytes"
    archive.write_bytes(verified)
    downloaded = b"unexpected upstream bytes"
    lock = ArchiveLock(
        dataset="fixture",
        marker_dataset="fixture",
        source_ref="revision",
        url="https://example.invalid/source.zip",
        sha256=hashlib.sha256(verified).hexdigest(),
    )

    monkeypatch.setattr(
        "ntruth.data.source_locks.urllib.request.urlopen",
        lambda *_args, **_kwargs: io.BytesIO(downloaded),
    )

    with pytest.raises(SourceLockError, match="downloaded archive SHA-256 mismatch"):
        ensure_pinned_archive(archive, lock, refresh=True)

    assert archive.read_bytes() == verified
    assert archive.with_name("source.zip.part").read_bytes() == downloaded


def test_download_partial_rejects_symlink_without_touching_archive_or_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = tmp_path / "dataset-root"
    downloads = root / "downloads"
    downloads.mkdir(parents=True)
    archive = downloads / "source.zip"
    archive.write_bytes(b"previous verified bytes")
    external_target = tmp_path / "external-target"
    external_target.write_bytes(b"must remain unchanged")
    archive.with_name("source.zip.part").symlink_to(external_target)
    lock = ArchiveLock(
        dataset="fixture",
        marker_dataset="fixture",
        source_ref="revision",
        url="https://example.invalid/source.zip",
        sha256=hashlib.sha256(b"expected upstream bytes").hexdigest(),
    )
    monkeypatch.setattr(
        "ntruth.data.source_locks.urllib.request.urlopen",
        lambda *_args, **_kwargs: pytest.fail("network must not open for a symlinked partial"),
    )

    with pytest.raises(SourceLockError, match=r"partial.*symlink"):
        ensure_pinned_archive(archive, lock, refresh=True, root=root)

    assert archive.read_bytes() == b"previous verified bytes"
    assert external_target.read_bytes() == b"must remain unchanged"
    assert archive.with_name("source.zip.part").is_symlink()


def test_existing_hardlinked_partial_is_recreated_without_touching_external_inode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = tmp_path / "dataset-root"
    root.mkdir()
    archive = root / "source.zip"
    verified = b"expected upstream bytes"
    archive.write_bytes(verified)
    external_target = tmp_path / "external-target"
    external_target.write_bytes(b"must remain unchanged")
    partial = archive.with_name("source.zip.part")
    partial.hardlink_to(external_target)
    downloaded = b"unexpected upstream bytes"
    lock = ArchiveLock(
        dataset="fixture",
        marker_dataset="fixture",
        source_ref="revision",
        url="https://example.invalid/source.zip",
        sha256=hashlib.sha256(verified).hexdigest(),
    )
    monkeypatch.setattr(
        "ntruth.data.source_locks.urllib.request.urlopen",
        lambda *_args, **_kwargs: io.BytesIO(downloaded),
    )

    with pytest.raises(SourceLockError, match="downloaded archive SHA-256 mismatch"):
        ensure_pinned_archive(archive, lock, refresh=True, root=root)

    assert archive.read_bytes() == verified
    assert external_target.read_bytes() == b"must remain unchanged"
    assert partial.read_bytes() == downloaded
    assert partial.stat().st_ino != external_target.stat().st_ino


def test_download_directory_symlink_cannot_redirect_partial_outside_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = tmp_path / "dataset-root"
    root.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    (root / "downloads").symlink_to(external, target_is_directory=True)
    archive = root / "downloads" / "source.zip"
    lock = ArchiveLock(
        dataset="fixture",
        marker_dataset="fixture",
        source_ref="revision",
        url="https://example.invalid/source.zip",
        sha256=hashlib.sha256(b"expected upstream bytes").hexdigest(),
    )
    monkeypatch.setattr(
        "ntruth.data.source_locks.urllib.request.urlopen",
        lambda *_args, **_kwargs: pytest.fail("network must not open outside the dataset root"),
    )

    with pytest.raises(SourceLockError, match="download directory"):
        ensure_pinned_archive(archive, lock, refresh=True, root=root)

    assert not (external / "source.zip.part").exists()
    assert not (external / "source.zip").exists()


def test_dataset_root_move_during_download_fails_before_archive_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    trusted = tmp_path / "trusted"
    root = trusted / "dataset-root"
    downloads = root / "downloads"
    downloads.mkdir(parents=True)
    archive = downloads / "source.zip"
    outside = tmp_path / "outside"
    outside.mkdir()
    moved_root = outside / "moved-root"
    downloaded = b"expected upstream bytes"
    lock = ArchiveLock(
        dataset="fixture",
        marker_dataset="fixture",
        source_ref="revision",
        url="https://example.invalid/source.zip",
        sha256=hashlib.sha256(downloaded).hexdigest(),
    )

    class MovingResponse(io.BytesIO):
        moved = False

        def read(self, size: int = -1) -> bytes:
            if not self.moved:
                self.moved = True
                root.replace(moved_root)
                root.mkdir()
            return super().read(size)

    monkeypatch.setattr(
        "ntruth.data.source_locks.urllib.request.urlopen",
        lambda *_args, **_kwargs: MovingResponse(downloaded),
    )

    with pytest.raises(SourceLockError, match=r"root|parent.*changed"):
        ensure_pinned_archive(archive, lock, refresh=True, root=root)

    assert not archive.exists()
    assert not (moved_root / "downloads" / "source.zip").exists()
    assert not (moved_root / "downloads" / "source.zip.part").exists()


def test_dataset_root_with_symlinked_intermediate_ancestor_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    real_parent = tmp_path / "real-parent"
    root = real_parent / "dataset-root"
    (root / "downloads").mkdir(parents=True)
    alias_parent = tmp_path / "alias-parent"
    alias_parent.symlink_to(real_parent, target_is_directory=True)
    archive = alias_parent / "dataset-root" / "downloads" / "source.zip"
    lock = ArchiveLock(
        dataset="fixture",
        marker_dataset="fixture",
        source_ref="revision",
        url="https://example.invalid/source.zip",
        sha256=hashlib.sha256(b"expected upstream bytes").hexdigest(),
    )
    monkeypatch.setattr(
        "ntruth.data.source_locks.urllib.request.urlopen",
        lambda *_args, **_kwargs: pytest.fail("network must not open through a symlinked ancestor"),
    )

    with pytest.raises(SourceLockError, match=r"root.*without following links"):
        ensure_pinned_archive(archive, lock, refresh=True, root=alias_parent / "dataset-root")

    assert not archive.exists()


def test_archive_outside_explicit_root_is_rejected(tmp_path: Path):
    root = tmp_path / "dataset-root"
    root.mkdir()
    archive = tmp_path / "outside" / "source.zip"
    lock = ArchiveLock(
        dataset="fixture",
        marker_dataset="fixture",
        source_ref="revision",
        url="https://example.invalid/source.zip",
        sha256="0" * 64,
    )

    with pytest.raises(SourceLockError, match="outside dataset root"):
        ensure_pinned_archive(archive, lock, refresh=True, root=root)


def test_authenticated_resume_marker_binds_current_raw_tree(tmp_path: Path):
    lock = ArchiveLock(
        dataset="preclinie",
        marker_dataset="preclinie",
        source_ref="revision",
        url="https://example.invalid/source.zip",
        sha256="a" * 64,
    )
    raw_root = tmp_path / "raw"
    nested = raw_root / "nested"
    nested.mkdir(parents=True)
    (raw_root / "alpha.txt").write_text("alpha\n", encoding="utf-8")
    (nested / "beta.bin").write_bytes(b"beta")
    marker = raw_root / ".ntruth_complete.json"

    expected = calculate_raw_tree_commitment(raw_root)
    write_authenticated_resume_marker(raw_root, lock)
    marker_document = json.loads(marker.read_text(encoding="utf-8"))

    assert resume_marker_matches(marker, lock)
    assert marker_document["raw_tree"] == {
        "schema_version": "ntruth.raw-tree-commitment.v1",
        "sha256": expected.sha256,
        "file_count": 2,
        "directory_count": 1,
        "size_bytes": 10,
    }

    (nested / "beta.bin").write_bytes(b"mutated")
    assert not resume_marker_matches(marker, lock)


def test_legacy_resume_marker_without_tree_commitment_fails_closed(tmp_path: Path):
    lock = ArchiveLock(
        dataset="preclinie",
        marker_dataset="preclinie",
        source_ref="revision",
        url="https://example.invalid/source.zip",
        sha256="a" * 64,
    )
    marker = tmp_path / ".ntruth_complete.json"
    marker.write_text(
        json.dumps(
            {
                "dataset": "preclinie",
                "source_ref": "revision",
                "archive_sha256": "a" * 64,
            }
        ),
        encoding="utf-8",
    )

    assert not resume_marker_matches(marker, lock)


def test_raw_tree_commitment_rejects_symlinks(tmp_path: Path):
    raw_root = tmp_path / "raw"
    raw_root.mkdir()
    external = tmp_path / "external.txt"
    external.write_text("external", encoding="utf-8")
    (raw_root / "linked.txt").symlink_to(external)

    with pytest.raises(SourceLockError, match="symlink"):
        calculate_raw_tree_commitment(raw_root)


def test_raw_tree_commitment_rejects_parent_replacement_during_file_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = tmp_path / "dataset-root"
    raw_root = root / "raw"
    raw_root.mkdir(parents=True)
    (raw_root / "record.txt").write_bytes(b"trusted")
    external = tmp_path / "external"
    external.mkdir()
    (external / "record.txt").write_bytes(b"untrusted")
    parked = root / "raw-parked"
    source_locks = importlib.import_module("ntruth.data.source_locks")
    original_open = source_locks.os.open
    swapped = False

    def swap_parent_then_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        nonlocal swapped
        if not swapped and str(path) == "record.txt":
            swapped = True
            raw_root.replace(parked)
            raw_root.symlink_to(external, target_is_directory=True)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(source_locks.os, "open", swap_parent_then_open)

    with pytest.raises(SourceLockError, match="changed while being committed"):
        calculate_raw_tree_commitment(raw_root)


@pytest.mark.parametrize(
    ("module_name", "installer_name", "dataset_name", "version_name"),
    [
        (
            "ntruth.data.datasets.preclinie",
            "install_preclinie",
            "preclinie",
            "PRECLINIE_VERSION",
        ),
        (
            "ntruth.data.datasets.measeval",
            "install_measeval",
            "measeval",
            "MEASEVAL_VERSION",
        ),
        ("ntruth.data.datasets.craft", "install_craft", "craft", "CRAFT_VERSION"),
    ],
)
def test_dataset_handler_reextracts_and_rebinds_marker_after_raw_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
    installer_name: str,
    dataset_name: str,
    version_name: str,
):
    module = importlib.import_module(module_name)
    installer = getattr(module, installer_name)
    source_ref = getattr(module, version_name)
    lock = load_archive_lock(dataset_name, source_ref=source_ref)
    events: list[str] = []

    raw_root = tmp_path / "raw" / dataset_name / source_ref
    raw_root.mkdir(parents=True)
    raw_record = raw_root / "record.txt"
    raw_record.write_text("original", encoding="utf-8")
    write_authenticated_resume_marker(raw_root, lock)
    raw_record.write_text("mutated", encoding="utf-8")
    assert not resume_marker_matches(raw_root / ".ntruth_complete.json", lock)

    monkeypatch.setattr(
        module,
        "ensure_pinned_archive_verified_copy",
        lambda *_args, **_kwargs: nullcontext(),
    )
    monkeypatch.setattr(
        module,
        "atomic_extract_archive",
        lambda *_args, **_kwargs: events.append("extract"),
    )

    class MarkerRebound(Exception):
        pass

    def record_marker(*_args: object, **_kwargs: object) -> None:
        events.append("marker")
        raise MarkerRebound

    monkeypatch.setattr(module, "write_authenticated_resume_marker", record_marker)

    with pytest.raises(MarkerRebound):
        installer(tmp_path)

    assert events == ["extract", "marker"]


def test_marker_lock_binding_mismatch_fails_closed(tmp_path: Path):
    lock = ArchiveLock(
        dataset="preclinie",
        marker_dataset="preclinie",
        source_ref="revision",
        url="https://example.invalid/source.zip",
        sha256="a" * 64,
    )
    raw_root = tmp_path / "raw"
    raw_root.mkdir()
    (raw_root / "record.txt").write_text("record", encoding="utf-8")
    marker = raw_root / ".ntruth_complete.json"
    write_authenticated_resume_marker(raw_root, lock)

    marker_document = json.loads(marker.read_text(encoding="utf-8"))
    marker_document["archive_sha256"] = "b" * 64
    marker.write_text(
        json.dumps(marker_document),
        encoding="utf-8",
    )
    assert not resume_marker_matches(marker, lock)

    marker.write_text("not-json", encoding="utf-8")
    assert not resume_marker_matches(marker, lock)
