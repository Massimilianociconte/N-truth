"""Fail-closed verification for repository-pinned public source archives."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
import urllib.request
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from ntruth.data.config import get_manifests_dir
from ntruth.data.fs import (
    FSError,
    VerifiedArchiveCopy,
    anchored_tree_commitment,
    atomic_write_json,
    open_anchored_path,
)

LOCK_SCHEMA_VERSION = "ntruth.public-sources-lock.v2"
RESUME_MARKER_SCHEMA_VERSION = "ntruth.authenticated-raw-marker.v1"
RAW_TREE_SCHEMA_VERSION = "ntruth.raw-tree-commitment.v1"
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_RESUME_MARKER_NAME = ".ntruth_complete.json"
_READ_CHUNK_SIZE = 1024 * 1024


class SourceLockError(RuntimeError):
    """A source archive cannot be proven to match the repository lock."""


@dataclass(frozen=True)
class ArchiveLock:
    """Pinned identity and retrieval coordinates for one archive."""

    dataset: str
    marker_dataset: str
    source_ref: str
    url: str
    sha256: str


@dataclass(frozen=True)
class RawTreeCommitment:
    """Deterministic identity for canonical files and directories in one raw tree."""

    sha256: str
    file_count: int
    directory_count: int
    size_bytes: int

    def as_dict(self) -> dict[str, str | int]:
        return {
            "schema_version": RAW_TREE_SCHEMA_VERSION,
            "sha256": self.sha256,
            "file_count": self.file_count,
            "directory_count": self.directory_count,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True)
class _ArchiveParent:
    directory_fd: int
    archive_name: str
    root_anchor: Any
    bindings: tuple[tuple[int, str, int], ...]
    absolute_path: Path

    def validate(self) -> None:
        try:
            self.root_anchor.validate(label="Dataset root")
            for parent_fd, name, child_fd in self.bindings:
                path_stat = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                opened_stat = os.fstat(child_fd)
                if (path_stat.st_dev, path_stat.st_ino, path_stat.st_mode) != (
                    opened_stat.st_dev,
                    opened_stat.st_ino,
                    opened_stat.st_mode,
                ):
                    raise SourceLockError(
                        f"Archive download parent changed while in use: {self.absolute_path}"
                    )
        except (FSError, OSError) as exc:
            raise SourceLockError(
                f"Dataset root or archive parent changed while in use: {self.absolute_path}"
            ) from exc


def _load_lock_document() -> dict[str, Any]:
    lock_path = get_manifests_dir() / "public_sources.lock.json"
    try:
        document = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SourceLockError(f"Public source lock is unreadable: {lock_path}") from exc
    if not isinstance(document, dict) or document.get("schema_version") != LOCK_SCHEMA_VERSION:
        raise SourceLockError(
            f"Unsupported public source lock schema: {document.get('schema_version')!r}"
        )
    return document


def load_archive_lock(dataset: str, *, source_ref: str) -> ArchiveLock:
    """Load and structurally validate one exact archive lock entry."""

    normalized_dataset = dataset.casefold()
    document = _load_lock_document()
    archives = document.get("archives")
    entry = archives.get(normalized_dataset) if isinstance(archives, dict) else None
    if not isinstance(entry, dict):
        raise SourceLockError(f"Archive lock missing for dataset={normalized_dataset}")

    required = ("marker_dataset", "source_ref", "url", "sha256")
    if any(not isinstance(entry.get(field), str) or not entry[field] for field in required):
        raise SourceLockError(f"Archive lock is incomplete for dataset={normalized_dataset}")
    if entry["source_ref"] != source_ref:
        raise SourceLockError(
            f"Archive lock revision mismatch for {normalized_dataset}: "
            f"expected {source_ref}, found {entry['source_ref']}"
        )
    if not entry["url"].startswith("https://"):
        raise SourceLockError(f"Archive URL must use HTTPS for dataset={normalized_dataset}")
    if SHA256_PATTERN.fullmatch(entry["sha256"]) is None:
        raise SourceLockError(f"Invalid archive SHA-256 for dataset={normalized_dataset}")

    return ArchiveLock(
        dataset=normalized_dataset,
        marker_dataset=entry["marker_dataset"],
        source_ref=entry["source_ref"],
        url=entry["url"],
        sha256=entry["sha256"],
    )


def _hash_binary_handle(handle: BinaryIO) -> str:
    digest = hashlib.sha256()
    while chunk := handle.read(_READ_CHUNK_SIZE):
        digest.update(chunk)
    return digest.hexdigest()


def _no_follow_flag() -> int:
    flag = getattr(os, "O_NOFOLLOW", None)
    if flag is None:
        raise SourceLockError("This platform cannot enforce no-follow source archive I/O")
    return flag


def _directory_flags() -> int:
    directory_flag = getattr(os, "O_DIRECTORY", None)
    if directory_flag is None:
        raise SourceLockError("This platform cannot securely open the download directory")
    return os.O_RDONLY | directory_flag | _no_follow_flag()


def _absolute_without_resolving(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


@contextmanager
def _open_archive_parent(archive: Path, root: Path | None) -> Iterator[_ArchiveParent]:
    archive_absolute = _absolute_without_resolving(archive)
    root_absolute = (
        _absolute_without_resolving(root) if root is not None else archive_absolute.parent
    )
    try:
        relative = archive_absolute.relative_to(root_absolute)
    except ValueError as exc:
        raise SourceLockError(
            f"Archive path is outside dataset root: archive={archive_absolute}, root={root_absolute}"
        ) from exc
    if relative == Path(".") or not relative.name:
        raise SourceLockError(f"Archive path does not name a file: {archive_absolute}")

    opened_fds: list[int] = []
    try:
        try:
            root_context = open_anchored_path(root_absolute)
            root_anchor = root_context.__enter__()
        except (FSError, OSError) as exc:
            raise SourceLockError(
                f"Dataset root cannot be opened without following links: {root_absolute}"
            ) from exc
        current_fd = root_anchor.descriptor
        bindings: list[tuple[int, str, int]] = []

        for component in relative.parent.parts:
            if component in {"", ".", ".."}:
                raise SourceLockError(f"Unsafe archive parent component: {component!r}")
            with suppress(FileExistsError):
                os.mkdir(component, mode=0o755, dir_fd=current_fd)
            try:
                path_stat = os.stat(component, dir_fd=current_fd, follow_symlinks=False)
                child_fd = os.open(component, _directory_flags(), dir_fd=current_fd)
                opened_stat = os.fstat(child_fd)
            except OSError as exc:
                raise SourceLockError(
                    "Archive download directory contains a symlink or non-directory component: "
                    f"{archive_absolute.parent}"
                ) from exc
            if (path_stat.st_dev, path_stat.st_ino, path_stat.st_mode) != (
                opened_stat.st_dev,
                opened_stat.st_ino,
                opened_stat.st_mode,
            ):
                os.close(child_fd)
                raise SourceLockError(
                    f"Archive download parent changed while opening: {archive_absolute.parent}"
                )
            opened_fds.append(child_fd)
            bindings.append((current_fd, component, child_fd))
            current_fd = child_fd

        parent = _ArchiveParent(
            directory_fd=current_fd,
            archive_name=relative.name,
            root_anchor=root_anchor,
            bindings=tuple(bindings),
            absolute_path=archive_absolute.parent,
        )
        try:
            yield parent
        finally:
            parent.validate()
    finally:
        for descriptor in reversed(opened_fds):
            os.close(descriptor)
        if "root_context" in locals():
            try:
                root_context.__exit__(None, None, None)
            except FSError as exc:
                raise SourceLockError(
                    f"Dataset root changed while in use: {root_absolute}"
                ) from exc


def _entry_stat(directory_fd: int, name: str) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None


def _assert_regular_or_missing(directory_fd: int, name: str, *, label: str) -> bool:
    entry_stat = _entry_stat(directory_fd, name)
    if entry_stat is None:
        return False
    if stat.S_ISLNK(entry_stat.st_mode):
        raise SourceLockError(f"{label} may not be a symlink: {name}")
    if not stat.S_ISREG(entry_stat.st_mode):
        raise SourceLockError(f"{label} must be a regular file: {name}")
    return True


def _hash_regular_file_at(directory_fd: int, name: str, *, label: str) -> str:
    _assert_regular_or_missing(directory_fd, name, label=label)
    try:
        descriptor = os.open(name, os.O_RDONLY | _no_follow_flag(), dir_fd=directory_fd)
    except OSError as exc:
        raise SourceLockError(f"{label} cannot be opened without following links: {name}") from exc
    with os.fdopen(descriptor, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise SourceLockError(f"{label} must be a regular file: {name}")
        return _hash_binary_handle(handle)


def _copy_verified_archive_at(
    directory_fd: int,
    archive_name: str,
    lock: ArchiveLock,
) -> tuple[BinaryIO, int]:
    try:
        descriptor = os.open(
            archive_name,
            os.O_RDONLY | _no_follow_flag() | getattr(os, "O_CLOEXEC", 0),
            dir_fd=directory_fd,
        )
    except OSError as exc:
        raise SourceLockError(
            f"Source archive cannot be opened without following links: {archive_name}"
        ) from exc

    private_copy = None
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise SourceLockError(f"Source archive must be a regular file: {archive_name}")
        private_name = f".{archive_name}.verified.{secrets.token_hex(8)}"
        private_descriptor = os.open(
            private_name,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | _no_follow_flag(),
            0o600,
            dir_fd=directory_fd,
        )
        os.unlink(private_name, dir_fd=directory_fd)
        private_copy = os.fdopen(private_descriptor, "w+b")
        digest = hashlib.sha256()
        size_bytes = 0
        while chunk := os.read(descriptor, _READ_CHUNK_SIZE):
            private_copy.write(chunk)
            digest.update(chunk)
            size_bytes += len(chunk)
        after = os.fstat(descriptor)
        path_stat = os.stat(archive_name, dir_fd=directory_fd, follow_symlinks=False)
        stable_fields = ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(getattr(before, field) != getattr(after, field) for field in stable_fields) or any(
            getattr(after, field) != getattr(path_stat, field) for field in stable_fields
        ):
            raise SourceLockError(
                f"Source archive changed while being copied for verification: {archive_name}"
            )
        actual_sha256 = digest.hexdigest()
        if size_bytes != before.st_size:
            raise SourceLockError(
                f"Source archive size changed while being copied for verification: {archive_name}"
            )
        if actual_sha256 != lock.sha256:
            raise SourceLockError(
                f"Archive SHA-256 mismatch for {lock.dataset}: "
                f"expected {lock.sha256}, got {actual_sha256}"
            )
        private_copy.flush()
        private_copy.seek(0)
        return private_copy, size_bytes
    except BaseException:
        if private_copy is not None:
            private_copy.close()
        raise
    finally:
        os.close(descriptor)


def _download_to_partial(
    url: str,
    directory_fd: int,
    partial_name: str,
    *,
    timeout: int,
) -> str:
    partial_present = _assert_regular_or_missing(
        directory_fd, partial_name, label="Download partial"
    )
    if partial_present:
        os.unlink(partial_name, dir_fd=directory_fd)
    try:
        descriptor = os.open(
            partial_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | _no_follow_flag(),
            0o600,
            dir_fd=directory_fd,
        )
    except OSError as exc:
        raise SourceLockError(
            f"Download partial cannot be opened without following links: {partial_name}"
        ) from exc

    request = urllib.request.Request(url, headers={"User-Agent": "NTruthDataInstaller/1.0"})
    digest = hashlib.sha256()
    with os.fdopen(descriptor, "wb") as handle:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            while chunk := response.read(_READ_CHUNK_SIZE):
                handle.write(chunk)
                digest.update(chunk)
        handle.flush()
        os.fsync(handle.fileno())
    return digest.hexdigest()


def ensure_pinned_archive(
    archive: Path,
    lock: ArchiveLock,
    *,
    refresh: bool,
    timeout: int = 60,
    root: Path | None = None,
) -> str:
    """Return the pinned hash only after verifying local or newly downloaded bytes."""

    with ensure_pinned_archive_verified_copy(
        archive,
        lock,
        refresh=refresh,
        timeout=timeout,
        root=root,
    ) as verified:
        return verified.sha256


@contextmanager
def ensure_pinned_archive_verified_copy(
    archive: Path,
    lock: ArchiveLock,
    *,
    refresh: bool,
    timeout: int = 60,
    root: Path | None = None,
) -> Iterator[VerifiedArchiveCopy]:
    """Yield an unlinked private copy made from the exact archive FD that matched the lock."""

    with _open_archive_parent(archive, root) as parent:
        directory_fd = parent.directory_fd
        archive_name = parent.archive_name
        archive_present = _assert_regular_or_missing(
            directory_fd, archive_name, label="Source archive"
        )
        if archive_present and not refresh:
            private_copy, size_bytes = _copy_verified_archive_at(directory_fd, archive_name, lock)
            with private_copy:
                yield VerifiedArchiveCopy(
                    handle=private_copy,
                    name=archive_name,
                    sha256=lock.sha256,
                    size_bytes=size_bytes,
                )
            return

        partial_name = f"{archive_name}.part"
        actual_sha256 = _download_to_partial(lock.url, directory_fd, partial_name, timeout=timeout)
        if actual_sha256 != lock.sha256:
            raise SourceLockError(
                f"{lock.dataset} downloaded archive SHA-256 mismatch: "
                f"expected {lock.sha256}, got {actual_sha256}"
            )
        if (
            _hash_regular_file_at(directory_fd, partial_name, label="Download partial")
            != lock.sha256
        ):
            raise SourceLockError(f"{lock.dataset} download partial changed before publication")
        try:
            parent.validate()
        except SourceLockError:
            if _assert_regular_or_missing(directory_fd, partial_name, label="Download partial"):
                os.unlink(partial_name, dir_fd=directory_fd)
            raise
        os.replace(
            partial_name,
            archive_name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        private_copy, size_bytes = _copy_verified_archive_at(directory_fd, archive_name, lock)
        with private_copy:
            yield VerifiedArchiveCopy(
                handle=private_copy,
                name=archive_name,
                sha256=lock.sha256,
                size_bytes=size_bytes,
            )


def calculate_raw_tree_commitment(raw_root: Path) -> RawTreeCommitment:
    """Hash canonical raw paths and bytes, excluding the self-referential marker."""
    try:
        commitment = anchored_tree_commitment(
            raw_root,
            excluded_relative_paths=frozenset({_RESUME_MARKER_NAME}),
        )
    except FSError as exc:
        raise SourceLockError(
            f"Raw tree changed while being committed or contains a symlink: {raw_root}"
        ) from exc
    return RawTreeCommitment(**commitment)


def write_authenticated_resume_marker(
    raw_root: Path,
    lock: ArchiveLock,
    *,
    metadata: Mapping[str, Any] | None = None,
) -> RawTreeCommitment:
    """Bind a completion marker to both the pinned archive and extracted raw tree."""

    commitment = calculate_raw_tree_commitment(raw_root)
    document: dict[str, Any] = {
        "schema_version": RESUME_MARKER_SCHEMA_VERSION,
        "dataset": lock.marker_dataset,
        "source_ref": lock.source_ref,
        "archive_sha256": lock.sha256,
        "raw_tree": commitment.as_dict(),
    }
    if metadata:
        reserved = set(document).intersection(metadata)
        if reserved:
            raise SourceLockError(
                "Resume marker metadata cannot override authenticated fields: "
                + ", ".join(sorted(reserved))
            )
        document.update(metadata)
    atomic_write_json(raw_root / _RESUME_MARKER_NAME, document)
    return commitment


def resume_marker_matches(marker: Path, lock: ArchiveLock) -> bool:
    """Accept raw data only when the marker binds the lock and current tree bytes."""

    try:
        if marker.is_symlink():
            return False
        document = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(document, dict):
        return False
    raw_tree = document.get("raw_tree")
    if not isinstance(raw_tree, dict):
        return False
    expected_fields = {
        "schema_version": RAW_TREE_SCHEMA_VERSION,
        "sha256": raw_tree.get("sha256"),
        "file_count": raw_tree.get("file_count"),
        "directory_count": raw_tree.get("directory_count"),
        "size_bytes": raw_tree.get("size_bytes"),
    }
    if (
        document.get("schema_version") != RESUME_MARKER_SCHEMA_VERSION
        or document.get("dataset") != lock.marker_dataset
        or document.get("source_ref") != lock.source_ref
        or document.get("archive_sha256") != lock.sha256
        or raw_tree != expected_fields
        or SHA256_PATTERN.fullmatch(str(raw_tree.get("sha256", ""))) is None
        or not all(
            isinstance(raw_tree.get(field), int) and raw_tree[field] >= 0
            for field in ("file_count", "directory_count", "size_bytes")
        )
    ):
        return False
    try:
        observed = calculate_raw_tree_commitment(marker.parent)
    except SourceLockError:
        return False
    return raw_tree == observed.as_dict()
