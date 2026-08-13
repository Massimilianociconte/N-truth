"""Filesystem utilities for exFAT resilience, security, AppleDouble filtering, and Merkle manifests."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import tarfile
import tempfile
import zipfile
from collections.abc import Iterator, Mapping
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import IO, Any, BinaryIO, TypedDict, cast

MAX_ARCHIVE_FILE_COUNT = 100_000
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 20 * 1024 * 1024 * 1024  # 20 GB
MAX_ARCHIVE_COMPRESSION_RATIO = 100.0
EMPTY_FILE_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


class FSError(RuntimeError):
    """Filesystem operational error."""


class CanonicalFileEntry(TypedDict):
    """Content-addressed file entry with a location-independent path."""

    path: str
    sha256: str
    size_bytes: int


class AnchoredTreeCommitment(TypedDict):
    sha256: str
    file_count: int
    directory_count: int
    size_bytes: int


@dataclass(frozen=True)
class VerifiedArchiveCopy:
    """Private seekable archive stream whose exact bytes already matched a source lock."""

    handle: BinaryIO
    name: str
    sha256: str
    size_bytes: int


@dataclass
class _AnchoredPath:
    absolute_path: Path
    descriptor: int
    opened_descriptors: list[int]
    bindings: list[tuple[int, str, int]]

    def validate(self, *, label: str) -> None:
        for parent_fd, name, child_fd in self.bindings:
            try:
                path_stat = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                opened_stat = os.fstat(child_fd)
            except OSError as exc:
                raise FSError(f"{label} changed while in use: {self.absolute_path}") from exc
            if _identity_stat_signature(path_stat) != _identity_stat_signature(opened_stat):
                raise FSError(f"{label} changed while in use: {self.absolute_path}")


def _no_follow_flag() -> int:
    flag = getattr(os, "O_NOFOLLOW", None)
    if flag is None:
        raise FSError("This platform cannot enforce no-follow filesystem I/O")
    return flag


def _directory_open_flags() -> int:
    directory_flag = getattr(os, "O_DIRECTORY", None)
    if directory_flag is None:
        raise FSError("This platform cannot securely open directories")
    return os.O_RDONLY | directory_flag | _no_follow_flag() | getattr(os, "O_CLOEXEC", 0)


def _regular_open_flags() -> int:
    return os.O_RDONLY | _no_follow_flag() | getattr(os, "O_CLOEXEC", 0)


def _identity_stat_signature(file_stat: os.stat_result) -> tuple[int, int, int]:
    return (file_stat.st_dev, file_stat.st_ino, file_stat.st_mode)


@contextlib.contextmanager
def _open_anchored_path(path: Path) -> Iterator[_AnchoredPath]:
    absolute_path = Path(os.path.abspath(os.fspath(path)))
    if not absolute_path.is_absolute():
        raise FSError(f"Path cannot be made absolute: {path}")
    opened_descriptors: list[int] = []
    bindings: list[tuple[int, str, int]] = []
    try:
        current_fd = os.open("/", _directory_open_flags())
        opened_descriptors.append(current_fd)
        if absolute_path == Path("/"):
            anchored = _AnchoredPath(
                absolute_path=absolute_path,
                descriptor=current_fd,
                opened_descriptors=opened_descriptors,
                bindings=bindings,
            )
            yield anchored
            anchored.validate(label="Anchored path")
            return

        components = absolute_path.parts[1:]
        for index, component in enumerate(components):
            if component in {"", ".", ".."}:
                raise FSError(f"Unsafe path component: {component!r}")
            is_final = index == len(components) - 1
            try:
                entry_stat = os.stat(component, dir_fd=current_fd, follow_symlinks=False)
                flags = _regular_open_flags() if is_final else _directory_open_flags()
                child_fd = os.open(component, flags, dir_fd=current_fd)
                opened_stat = os.fstat(child_fd)
            except OSError as exc:
                raise FSError(
                    f"Path component cannot be opened without following links: {absolute_path}"
                ) from exc
            if _identity_stat_signature(entry_stat) != _identity_stat_signature(opened_stat):
                os.close(child_fd)
                raise FSError(f"Path changed while being opened: {absolute_path}")
            if not is_final and not stat.S_ISDIR(opened_stat.st_mode):
                os.close(child_fd)
                raise FSError(f"Path component is not a directory: {absolute_path}")
            opened_descriptors.append(child_fd)
            bindings.append((current_fd, component, child_fd))
            current_fd = child_fd

        anchored = _AnchoredPath(
            absolute_path=absolute_path,
            descriptor=current_fd,
            opened_descriptors=opened_descriptors,
            bindings=bindings,
        )
        yield anchored
        anchored.validate(label="Anchored path")
    finally:
        for descriptor in reversed(opened_descriptors):
            with contextlib.suppress(OSError):
                os.close(descriptor)


@contextlib.contextmanager
def open_anchored_path(path: Path) -> Iterator[_AnchoredPath]:
    """Open an existing path component-by-component without following links."""

    with _open_anchored_path(path) as anchored:
        yield anchored


def is_ignorable_metadata(path: Path | str) -> bool:
    name = Path(path).name
    normalized = name.casefold()
    return normalized == "__macosx" or normalized == ".ds_store" or name.startswith("._")


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp_name)
        raise


def atomic_write_json(path: Path, value: Any) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    atomic_write_text(path, text)


def link_or_copy(source: Path, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        destination.unlink()
    try:
        os.link(source, destination)
        return "hardlink"
    except OSError:
        pass
    try:
        destination.symlink_to(os.path.relpath(source, destination.parent))
        return "symlink"
    except OSError:
        shutil.copy2(source, destination)
        return "copy"


def safe_extract_zip(archive: Path | BinaryIO, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    base = destination.resolve()
    total_files = 0
    total_uncompressed = 0
    if isinstance(archive, Path):
        archive_size = archive.stat().st_size or 1
    else:
        archive.seek(0, os.SEEK_END)
        archive_size = archive.tell() or 1
        archive.seek(0)

    with zipfile.ZipFile(archive) as zf:
        infolist = zf.infolist()
        if len(infolist) > MAX_ARCHIVE_FILE_COUNT:
            raise FSError(
                f"ZIP file count exceeds safety limit ({len(infolist)} > {MAX_ARCHIVE_FILE_COUNT})"
            )
        for info in infolist:
            name = info.filename.replace("\\", "/")
            if is_ignorable_metadata(name):
                continue
            unix_file_type = stat.S_IFMT((info.external_attr >> 16) & 0xFFFF)
            if unix_file_type == stat.S_IFLNK:
                raise FSError(f"Symlinks in ZIP archives are blocked for security: {info.filename}")
            if unix_file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
                raise FSError(f"Special files in ZIP archives are blocked: {info.filename}")
            if name.startswith("/") or re.match(r"^[A-Za-z]:", name):
                raise FSError(f"Unsafe absolute path in ZIP: {info.filename}")
            target = (destination / name).resolve()
            try:
                target.relative_to(base)
            except ValueError as exc:
                raise FSError(f"ZIP path traversal detected: {info.filename}") from exc

            total_files += 1
            total_uncompressed += info.file_size
            if total_uncompressed > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                raise FSError(f"ZIP uncompressed size exceeds limit ({total_uncompressed} bytes)")

        if (total_uncompressed / archive_size) > MAX_ARCHIVE_COMPRESSION_RATIO:
            raise FSError("ZIP compression ratio exceeds safe threshold (zip bomb protection)")

        for info in infolist:
            if is_ignorable_metadata(info.filename):
                continue
            zf.extract(info, destination)


def safe_extract_tar(archive: Path | BinaryIO, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    base = destination.resolve()
    total_files = 0
    total_uncompressed = 0
    if isinstance(archive, Path):
        archive_size = archive.stat().st_size or 1
    else:
        archive.seek(0, os.SEEK_END)
        archive_size = archive.tell() or 1
        archive.seek(0)

    with _open_tar_source(archive) as tf:
        members = tf.getmembers()
        if len(members) > MAX_ARCHIVE_FILE_COUNT:
            raise FSError(
                f"TAR file count exceeds safety limit ({len(members)} > {MAX_ARCHIVE_FILE_COUNT})"
            )

        for member in members:
            if is_ignorable_metadata(member.name):
                continue
            if member.islnk() or member.issym():
                raise FSError(f"Links in TAR archives are blocked for security: {member.name}")
            if member.isblk() or member.ischr() or member.isfifo():
                raise FSError(f"Special device files in TAR archives are blocked: {member.name}")
            name = member.name.replace("\\", "/")
            if name.startswith("/") or re.match(r"^[A-Za-z]:", name):
                raise FSError(f"Unsafe absolute path in TAR: {member.name}")
            target = (destination / name).resolve()
            try:
                target.relative_to(base)
            except ValueError as exc:
                raise FSError(f"TAR path traversal detected: {member.name}") from exc

            total_files += 1
            total_uncompressed += member.size
            if total_uncompressed > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                raise FSError(f"TAR uncompressed size exceeds limit ({total_uncompressed} bytes)")

        if (total_uncompressed / archive_size) > MAX_ARCHIVE_COMPRESSION_RATIO:
            raise FSError("TAR compression ratio exceeds safe threshold (zip bomb protection)")

        for member in members:
            if is_ignorable_metadata(member.name):
                continue
            tf.extract(member, destination, filter="data")


@contextlib.contextmanager
def _open_tar_source(archive: Path | BinaryIO) -> Iterator[tarfile.TarFile]:
    if isinstance(archive, Path):
        with tarfile.open(archive, "r:*") as handle:
            yield handle
    else:
        with tarfile.open(fileobj=cast(Any, archive), mode="r:*") as handle:
            yield handle


def safe_extract_archive(archive: Path | VerifiedArchiveCopy, destination: Path) -> None:
    name = archive.name.lower()
    source: Path | BinaryIO = archive if isinstance(archive, Path) else archive.handle
    if not isinstance(archive, Path):
        archive.handle.seek(0)
    if name.endswith(".zip"):
        safe_extract_zip(source, destination)
    elif name.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2")):
        safe_extract_tar(source, destination)
    else:
        raise FSError(f"Unsupported archive format: {archive.name}")


def meaningfull_entries(directory: Path) -> list[Path]:
    if not directory.exists() or not directory.is_dir():
        return []
    return [path for path in directory.iterdir() if not is_ignorable_metadata(path)]


def strip_single_root(extracted: Path) -> Path:
    entries = meaningfull_entries(extracted)
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return extracted


@contextlib.contextmanager
def _open_destination_parent(
    trusted_root: Path,
    destination: Path,
) -> Iterator[tuple[int, str, _AnchoredPath]]:
    trusted_absolute = Path(os.path.abspath(os.fspath(trusted_root)))
    destination_absolute = Path(os.path.abspath(os.fspath(destination)))
    try:
        relative = destination_absolute.relative_to(trusted_absolute)
    except ValueError as exc:
        raise FSError(
            f"Archive destination is outside trusted root: {destination_absolute}"
        ) from exc
    if relative == Path(".") or not relative.name:
        raise FSError(f"Archive destination must be below trusted root: {destination_absolute}")

    with _open_anchored_path(trusted_absolute) as anchored_root:
        if not stat.S_ISDIR(os.fstat(anchored_root.descriptor).st_mode):
            raise FSError(f"Trusted archive root is not a directory: {trusted_absolute}")
        opened: list[int] = []
        bindings: list[tuple[int, str, int]] = []
        current_fd = anchored_root.descriptor
        try:
            for component in relative.parent.parts:
                if component in {"", ".", ".."}:
                    raise FSError(f"Unsafe archive destination component: {component!r}")
                with contextlib.suppress(FileExistsError):
                    os.mkdir(component, mode=0o755, dir_fd=current_fd)
                try:
                    path_stat = os.stat(component, dir_fd=current_fd, follow_symlinks=False)
                    child_fd = os.open(component, _directory_open_flags(), dir_fd=current_fd)
                    opened_stat = os.fstat(child_fd)
                except OSError as exc:
                    raise FSError(
                        "Archive destination parent cannot be opened without following links: "
                        f"{destination_absolute.parent}"
                    ) from exc
                if _identity_stat_signature(path_stat) != _identity_stat_signature(opened_stat):
                    os.close(child_fd)
                    raise FSError(
                        f"Archive destination parent changed while opening: {destination_absolute.parent}"
                    )
                opened.append(child_fd)
                bindings.append((current_fd, component, child_fd))
                current_fd = child_fd
            anchored_parent = _AnchoredPath(
                absolute_path=destination_absolute.parent,
                descriptor=current_fd,
                opened_descriptors=[],
                bindings=bindings,
            )
            yield current_fd, relative.name, anchored_parent
            anchored_parent.validate(label="Archive destination parent")
        finally:
            for descriptor in reversed(opened):
                os.close(descriptor)


def _archive_member_parts(name: str) -> tuple[str, ...]:
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        raise FSError(f"Unsafe absolute path in archive: {name}")
    path = PurePosixPath(normalized)
    parts = tuple(part for part in path.parts if part not in {"", "."})
    if not parts or any(part == ".." for part in parts):
        raise FSError(f"Archive path traversal detected: {name}")
    return parts


def _archive_member_is_ignorable(parts: tuple[str, ...]) -> bool:
    return any(is_ignorable_metadata(part) for part in parts)


@contextlib.contextmanager
def _open_directory_chain(root_fd: int, parts: tuple[str, ...]) -> Iterator[int]:
    current_fd = root_fd
    opened: list[int] = []
    try:
        for component in parts:
            with contextlib.suppress(FileExistsError):
                os.mkdir(component, mode=0o700, dir_fd=current_fd)
            try:
                child_fd = os.open(component, _directory_open_flags(), dir_fd=current_fd)
            except OSError as exc:
                raise FSError(
                    f"Archive extraction path contains a symlink or non-directory: {component}"
                ) from exc
            opened.append(child_fd)
            current_fd = child_fd
        yield current_fd
    finally:
        for descriptor in reversed(opened):
            os.close(descriptor)


def _write_archive_member(root_fd: int, parts: tuple[str, ...], source: IO[bytes]) -> None:
    with _open_directory_chain(root_fd, parts[:-1]) as parent_fd:
        try:
            descriptor = os.open(
                parts[-1],
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | _no_follow_flag(),
                0o600,
                dir_fd=parent_fd,
            )
        except OSError as exc:
            raise FSError(f"Archive member cannot be created safely: {'/'.join(parts)}") from exc
        with os.fdopen(descriptor, "wb") as destination_handle:
            shutil.copyfileobj(source, destination_handle, length=1024 * 1024)
            destination_handle.flush()
            os.fsync(destination_handle.fileno())


def _extract_zip_to_fd(archive: Path | VerifiedArchiveCopy, destination_fd: int) -> None:
    source: Path | BinaryIO = archive if isinstance(archive, Path) else archive.handle
    if not isinstance(archive, Path):
        archive.handle.seek(0)
    archive_size = (
        archive.stat().st_size if isinstance(archive, Path) else archive.size_bytes
    ) or 1
    with zipfile.ZipFile(source) as zf:
        archive_members = zf.infolist()
        if len(archive_members) > MAX_ARCHIVE_FILE_COUNT:
            raise FSError(
                f"ZIP file count exceeds safety limit "
                f"({len(archive_members)} > {MAX_ARCHIVE_FILE_COUNT})"
            )
        members: list[tuple[zipfile.ZipInfo, tuple[str, ...]]] = []
        total_uncompressed = 0
        for info in archive_members:
            parts = _archive_member_parts(info.filename)
            if _archive_member_is_ignorable(parts):
                continue
            unix_file_type = stat.S_IFMT((info.external_attr >> 16) & 0xFFFF)
            if unix_file_type == stat.S_IFLNK:
                raise FSError(f"Symlinks in ZIP archives are blocked for security: {info.filename}")
            if unix_file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
                raise FSError(f"Special files in ZIP archives are blocked: {info.filename}")
            members.append((info, parts))
            total_uncompressed += info.file_size
        if total_uncompressed > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
            raise FSError(f"ZIP uncompressed size exceeds limit ({total_uncompressed} bytes)")
        if (total_uncompressed / archive_size) > MAX_ARCHIVE_COMPRESSION_RATIO:
            raise FSError("ZIP compression ratio exceeds safe threshold (zip bomb protection)")

        for info, parts in members:
            if info.is_dir() or stat.S_IFMT((info.external_attr >> 16) & 0xFFFF) == stat.S_IFDIR:
                with _open_directory_chain(destination_fd, parts):
                    pass
                continue
            with zf.open(info, "r") as source_handle:
                _write_archive_member(destination_fd, parts, source_handle)


def _extract_tar_to_fd(archive: Path | VerifiedArchiveCopy, destination_fd: int) -> None:
    source: Path | BinaryIO = archive if isinstance(archive, Path) else archive.handle
    if not isinstance(archive, Path):
        archive.handle.seek(0)
    archive_size = (
        archive.stat().st_size if isinstance(archive, Path) else archive.size_bytes
    ) or 1
    tar_name = os.fspath(source) if isinstance(source, Path) else None
    tar_fileobj = None if isinstance(source, Path) else source
    with tarfile.open(name=tar_name, fileobj=tar_fileobj, mode="r:*") as tf:
        archive_members = tf.getmembers()
        if len(archive_members) > MAX_ARCHIVE_FILE_COUNT:
            raise FSError(
                f"TAR file count exceeds safety limit "
                f"({len(archive_members)} > {MAX_ARCHIVE_FILE_COUNT})"
            )
        members: list[tuple[tarfile.TarInfo, tuple[str, ...]]] = []
        total_uncompressed = 0
        for member in archive_members:
            parts = _archive_member_parts(member.name)
            if _archive_member_is_ignorable(parts):
                continue
            if not member.isdir() and not member.isfile():
                raise FSError(f"Links or special files in TAR archives are blocked: {member.name}")
            members.append((member, parts))
            total_uncompressed += member.size
        if total_uncompressed > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
            raise FSError(f"TAR uncompressed size exceeds limit ({total_uncompressed} bytes)")
        if (total_uncompressed / archive_size) > MAX_ARCHIVE_COMPRESSION_RATIO:
            raise FSError("TAR compression ratio exceeds safe threshold (zip bomb protection)")

        for member, parts in members:
            if member.isdir():
                with _open_directory_chain(destination_fd, parts):
                    pass
                continue
            source_handle = tf.extractfile(member)
            if source_handle is None:
                raise FSError(f"TAR member has no readable payload: {member.name}")
            with source_handle:
                _write_archive_member(destination_fd, parts, source_handle)


def _extract_archive_to_fd(archive: Path | VerifiedArchiveCopy, destination_fd: int) -> None:
    name = archive.name.lower()
    if name.endswith(".zip"):
        _extract_zip_to_fd(archive, destination_fd)
    elif name.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2")):
        _extract_tar_to_fd(archive, destination_fd)
    else:
        raise FSError(f"Unsupported archive format: {archive.name}")


def _write_json_at(directory_fd: int, name: str, value: Any) -> None:
    payload = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    descriptor = os.open(
        name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | _no_follow_flag(),
        0o600,
        dir_fd=directory_fd,
    )
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def atomic_extract_archive(
    archive: Path | VerifiedArchiveCopy,
    destination: Path,
    metadata: Mapping[str, Any],
    *,
    trusted_root: Path | None = None,
) -> None:
    if trusted_root is None:
        trusted_root = destination.parent
    with _open_destination_parent(trusted_root, destination) as (
        parent_fd,
        destination_name,
        anchored_parent,
    ):
        temp_name = f".{destination_name}.extract.{secrets.token_hex(8)}"
        os.mkdir(temp_name, mode=0o700, dir_fd=parent_fd)
        temp_fd = os.open(temp_name, _directory_open_flags(), dir_fd=parent_fd)
        previous_preserved = False
        try:
            os.mkdir("unpack", mode=0o700, dir_fd=temp_fd)
            unpack_fd = os.open("unpack", _directory_open_flags(), dir_fd=temp_fd)
            try:
                _extract_archive_to_fd(archive, unpack_fd)
                entries = sorted(
                    name for name in os.listdir(unpack_fd) if not is_ignorable_metadata(name)
                )
                if len(entries) == 1:
                    entry_stat = os.stat(entries[0], dir_fd=unpack_fd, follow_symlinks=False)
                else:
                    entry_stat = None
                if entry_stat is not None and stat.S_ISDIR(entry_stat.st_mode):
                    os.replace(entries[0], "final", src_dir_fd=unpack_fd, dst_dir_fd=temp_fd)
                else:
                    os.mkdir("final", mode=0o700, dir_fd=temp_fd)
                    final_fd = os.open("final", _directory_open_flags(), dir_fd=temp_fd)
                    try:
                        for entry in entries:
                            os.replace(entry, entry, src_dir_fd=unpack_fd, dst_dir_fd=final_fd)
                    finally:
                        os.close(final_fd)
            finally:
                os.close(unpack_fd)

            final_fd = os.open("final", _directory_open_flags(), dir_fd=temp_fd)
            try:
                archive_sha256 = (
                    archive.sha256
                    if isinstance(archive, VerifiedArchiveCopy)
                    else sha256_file(archive)
                )
                _write_json_at(
                    final_fd,
                    ".ntruth_complete.json",
                    {**metadata, "archive_sha256": archive_sha256},
                )
            finally:
                os.close(final_fd)

            anchored_parent.validate(label="Archive destination parent")
            try:
                destination_stat = os.stat(
                    destination_name, dir_fd=parent_fd, follow_symlinks=False
                )
            except FileNotFoundError:
                destination_stat = None
            if destination_stat is not None and stat.S_ISLNK(destination_stat.st_mode):
                raise FSError(f"Archive destination may not be a symlink: {destination}")
            if destination_stat is not None:
                os.replace(
                    destination_name,
                    "previous",
                    src_dir_fd=parent_fd,
                    dst_dir_fd=temp_fd,
                )
                previous_preserved = True
            try:
                os.replace("final", destination_name, src_dir_fd=temp_fd, dst_dir_fd=parent_fd)
            except BaseException:
                if previous_preserved:
                    try:
                        os.replace(
                            "previous",
                            destination_name,
                            src_dir_fd=temp_fd,
                            dst_dir_fd=parent_fd,
                        )
                        previous_preserved = False
                    except BaseException as rollback_error:
                        raise FSError(
                            f"Archive publish failed and rollback could not restore {destination}; "
                            f"previous tree preserved under {temp_name}/previous"
                        ) from rollback_error
                raise
            if previous_preserved:
                shutil.rmtree("previous", dir_fd=temp_fd)
                previous_preserved = False
        finally:
            os.close(temp_fd)
            if not previous_preserved:
                shutil.rmtree(temp_name, dir_fd=parent_fd, ignore_errors=True)


def calculate_merkle_root(directories: list[Path]) -> str:
    """Calculate a deterministic SHA-256 Merkle root from the canonical manifest."""
    return calculate_manifest_merkle_root(canonical_file_manifest(directories))


_NONCANONICAL_TREE_NAMES = frozenset(
    {
        "__MACOSX",
        "logs",
        "quarantine",
        "run-history",
        "temp",
        "temporary",
        "tmp",
    }
)


def _is_noncanonical_relative_path(path: Path) -> bool:
    for part in path.parts:
        normalized = part.casefold()
        if is_ignorable_metadata(part):
            return True
        if normalized in _NONCANONICAL_TREE_NAMES:
            return True
        if ".extract." in normalized or normalized.endswith(".part"):
            return True
    return False


def _canonical_root_specs(paths: list[Path]) -> list[tuple[str, Path]]:
    for path in paths:
        if not path.exists():
            raise FSError(f"Canonical root is missing: {path}")
        if path.is_symlink():
            raise FSError(f"Symlink canonical root is blocked: {path}")
        if not path.is_file() and not path.is_dir():
            raise FSError(f"Canonical root is not a regular file or directory: {path}")
    multiple_roots = len(paths) > 1
    specs: list[tuple[str, Path]] = []
    namespaces: set[str] = set()
    for path in paths:
        namespace = path.name if multiple_roots or path.is_file() else ""
        if namespace in namespaces:
            raise FSError(f"Canonical root namespace collision: {namespace!r}")
        namespaces.add(namespace)
        specs.append((namespace, path))
    return sorted(specs, key=lambda item: item[0])


def _stable_stat_signature(file_stat: os.stat_result) -> tuple[int, ...]:
    return (
        file_stat.st_dev,
        file_stat.st_ino,
        file_stat.st_mode,
        file_stat.st_nlink,
        file_stat.st_size,
        file_stat.st_mtime_ns,
        file_stat.st_ctime_ns,
    )


@dataclass(frozen=True)
class _DirectorySnapshotBinding:
    parent_fd: int | None
    name: str | None
    descriptor: int
    display_path: Path
    signature: tuple[int, ...]

    def validate(self) -> None:
        try:
            descriptor_stat = os.fstat(self.descriptor)
            path_stat = (
                os.stat(self.name, dir_fd=self.parent_fd, follow_symlinks=False)
                if self.parent_fd is not None and self.name is not None
                else descriptor_stat
            )
        except OSError as exc:
            raise FSError(
                f"Canonical directory changed during snapshot: {self.display_path}"
            ) from exc
        if self.signature != _stable_stat_signature(
            descriptor_stat
        ) or self.signature != _stable_stat_signature(path_stat):
            raise FSError(f"Canonical directory changed during snapshot: {self.display_path}")


def _hash_open_descriptor(
    descriptor: int,
    display_path: Path,
    chunk_size: int = 1024 * 1024,
) -> tuple[str, int]:
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode):
        raise FSError(f"Canonical path is not a regular file: {display_path}")
    digest = hashlib.sha256()
    while chunk := os.read(descriptor, chunk_size):
        digest.update(chunk)
    after = os.fstat(descriptor)
    if _stable_stat_signature(before) != _stable_stat_signature(after):
        raise FSError(f"Canonical file changed during canonical manifest read: {display_path}")
    return digest.hexdigest(), before.st_size


@contextlib.contextmanager
def _open_relative_regular(
    root_fd: int, parts: tuple[str, ...], display_path: Path
) -> Iterator[int]:
    if not parts:
        raise FSError(f"Canonical file has no relative path: {display_path}")
    current_fd = root_fd
    opened: list[int] = []
    bindings: list[tuple[int, str, int]] = []
    try:
        for component in parts[:-1]:
            try:
                path_stat = os.stat(component, dir_fd=current_fd, follow_symlinks=False)
                child_fd = os.open(component, _directory_open_flags(), dir_fd=current_fd)
                opened_stat = os.fstat(child_fd)
            except OSError as exc:
                raise FSError(
                    f"Canonical target cannot be opened without following links: {display_path}"
                ) from exc
            if _identity_stat_signature(path_stat) != _identity_stat_signature(opened_stat):
                os.close(child_fd)
                raise FSError(f"Canonical target changed while opening: {display_path}")
            opened.append(child_fd)
            bindings.append((current_fd, component, child_fd))
            current_fd = child_fd

        name = parts[-1]
        try:
            path_stat = os.stat(name, dir_fd=current_fd, follow_symlinks=False)
            descriptor = os.open(name, _regular_open_flags(), dir_fd=current_fd)
            opened_stat = os.fstat(descriptor)
        except OSError as exc:
            raise FSError(
                f"Canonical file cannot be opened without following links: {display_path}"
            ) from exc
        if _stable_stat_signature(path_stat) != _stable_stat_signature(opened_stat):
            os.close(descriptor)
            raise FSError(f"Canonical file changed while opening: {display_path}")
        opened.append(descriptor)
        bindings.append((current_fd, name, descriptor))
        yield descriptor
        for parent_fd, bound_name, child_fd in bindings:
            final_stat = os.stat(bound_name, dir_fd=parent_fd, follow_symlinks=False)
            if _stable_stat_signature(final_stat) != _stable_stat_signature(os.fstat(child_fd)):
                raise FSError(
                    f"Canonical file changed during canonical manifest read: {display_path}"
                )
    finally:
        for descriptor in reversed(opened):
            os.close(descriptor)


def _resolve_declared_symlink_target(
    parent_fd: int,
    name: str,
    link_path: Path,
    declared_directories: tuple[tuple[Path, int], ...],
) -> tuple[int, tuple[str, ...], os.stat_result, str]:
    before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if not stat.S_ISLNK(before.st_mode):
        raise FSError(f"Canonical link changed before resolution: {link_path}")
    try:
        link_value = os.readlink(name, dir_fd=parent_fd)
    except OSError as exc:
        raise FSError(f"Canonical symlink target is unavailable: {link_path}") from exc
    target_path = Path(link_value)
    if not target_path.is_absolute():
        target_path = link_path.parent / target_path
    target_absolute = Path(os.path.abspath(os.fspath(target_path)))
    for root_path, root_fd in declared_directories:
        try:
            relative = target_absolute.relative_to(root_path)
        except ValueError:
            continue
        if relative == Path("."):
            break
        return root_fd, relative.parts, before, link_value
    raise FSError(f"Symlink target is outside canonical roots: {link_path}")


def _read_canonical_symlink(
    parent_fd: int,
    name: str,
    link_path: Path,
    declared_directories: tuple[tuple[Path, int], ...],
) -> tuple[str, int]:
    root_fd, target_parts, before, link_value = _resolve_declared_symlink_target(
        parent_fd, name, link_path, declared_directories
    )
    with _open_relative_regular(root_fd, target_parts, link_path) as descriptor:
        digest, size_bytes = _hash_open_descriptor(descriptor, link_path)
    try:
        after = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        final_value = os.readlink(name, dir_fd=parent_fd)
    except OSError as exc:
        raise FSError(f"Canonical symlink changed during manifest read: {link_path}") from exc
    if _stable_stat_signature(before) != _stable_stat_signature(after) or link_value != final_value:
        raise FSError(f"Canonical symlink changed during manifest read: {link_path}")
    return digest, size_bytes


def _walk_canonical_directory(
    directory_fd: int,
    root_path: Path,
    relative_parent: Path,
    namespace: str,
    declared_directories: tuple[tuple[Path, int], ...],
    entries: list[CanonicalFileEntry],
    retained_directories: list[_DirectorySnapshotBinding],
) -> None:
    try:
        names = sorted(os.listdir(directory_fd))
    except OSError as exc:
        raise FSError(
            f"Canonical directory cannot be enumerated: {root_path / relative_parent}"
        ) from exc
    for name in names:
        relative_path = relative_parent / name
        if _is_noncanonical_relative_path(relative_path):
            continue
        display_path = root_path / relative_path
        try:
            entry_stat = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except OSError as exc:
            raise FSError(f"Canonical entry changed during enumeration: {display_path}") from exc
        if stat.S_ISDIR(entry_stat.st_mode):
            try:
                child_fd = os.open(name, _directory_open_flags(), dir_fd=directory_fd)
            except OSError as exc:
                raise FSError(f"Canonical directory contains a symlink: {display_path}") from exc
            opened_stat = os.fstat(child_fd)
            if _stable_stat_signature(entry_stat) != _stable_stat_signature(opened_stat):
                os.close(child_fd)
                raise FSError(f"Canonical directory changed while opening: {display_path}")
            retained_directories.append(
                _DirectorySnapshotBinding(
                    parent_fd=directory_fd,
                    name=name,
                    descriptor=child_fd,
                    display_path=display_path,
                    signature=_stable_stat_signature(opened_stat),
                )
            )
            _walk_canonical_directory(
                child_fd,
                root_path,
                relative_path,
                namespace,
                declared_directories,
                entries,
                retained_directories,
            )
            continue
        if stat.S_ISLNK(entry_stat.st_mode):
            digest, size_bytes = _read_canonical_symlink(
                directory_fd, name, display_path, declared_directories
            )
        elif stat.S_ISREG(entry_stat.st_mode):
            with _open_relative_regular(directory_fd, (name,), display_path) as descriptor:
                digest, size_bytes = _hash_open_descriptor(descriptor, display_path)
        else:
            raise FSError(f"Canonical entry is not a regular file or directory: {display_path}")
        manifest_path = Path(namespace, relative_path) if namespace else relative_path
        entries.append(
            {"path": manifest_path.as_posix(), "sha256": digest, "size_bytes": size_bytes}
        )


def canonical_file_manifest(paths: list[Path]) -> list[CanonicalFileEntry]:
    """Enumerate canonical files using root-anchored no-follow descriptor traversal."""
    root_specs = _canonical_root_specs(paths)
    entries: list[CanonicalFileEntry] = []
    retained_directories: list[_DirectorySnapshotBinding] = []
    with ExitStack() as stack:
        opened_roots: list[tuple[str, Path, _AnchoredPath]] = []
        for namespace, root_path in root_specs:
            absolute_root = Path(os.path.abspath(os.fspath(root_path)))
            anchored = stack.enter_context(_open_anchored_path(absolute_root))
            opened_roots.append((namespace, absolute_root, anchored))
        try:
            declared_directories = tuple(
                (root_path, anchored.descriptor)
                for _, root_path, anchored in opened_roots
                if stat.S_ISDIR(os.fstat(anchored.descriptor).st_mode)
            )
            for namespace, root_path, anchored in opened_roots:
                root_stat = os.fstat(anchored.descriptor)
                if stat.S_ISREG(root_stat.st_mode):
                    digest, size_bytes = _hash_open_descriptor(anchored.descriptor, root_path)
                    entries.append(
                        {"path": root_path.name, "sha256": digest, "size_bytes": size_bytes}
                    )
                elif stat.S_ISDIR(root_stat.st_mode):
                    retained_directories.append(
                        _DirectorySnapshotBinding(
                            parent_fd=None,
                            name=None,
                            descriptor=anchored.descriptor,
                            display_path=root_path,
                            signature=_stable_stat_signature(root_stat),
                        )
                    )
                    _walk_canonical_directory(
                        anchored.descriptor,
                        root_path,
                        Path(),
                        namespace,
                        declared_directories,
                        entries,
                        retained_directories,
                    )
                else:
                    raise FSError(f"Canonical root is not a regular file or directory: {root_path}")
            for binding in retained_directories:
                binding.validate()
            canonical_paths = [entry["path"] for entry in entries]
            if len(canonical_paths) != len(set(canonical_paths)):
                raise FSError("Canonical file path collision")
            return sorted(entries, key=lambda entry: entry["path"])
        finally:
            root_descriptors = {anchored.descriptor for _, _, anchored in opened_roots}
            for binding in reversed(retained_directories):
                if binding.descriptor not in root_descriptors:
                    with contextlib.suppress(OSError):
                        os.close(binding.descriptor)


def _is_relative_to(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def _commitment_path_bytes(kind: str, relative_path: str) -> bytes:
    return kind.encode("ascii") + b"\0" + relative_path.encode("utf-8", "surrogateescape") + b"\0"


def anchored_tree_commitment(
    root: Path,
    *,
    excluded_relative_paths: frozenset[str] = frozenset(),
) -> AnchoredTreeCommitment:
    """Commit a real directory tree using only anchored, no-follow descriptor traversal."""

    directories: list[str] = []
    files: list[tuple[str, str, int]] = []

    def visit(directory_fd: int, relative_parent: Path) -> None:
        for name in sorted(os.listdir(directory_fd)):
            relative_path = relative_parent / name
            relative_posix = relative_path.as_posix()
            if relative_posix in excluded_relative_paths or is_ignorable_metadata(name):
                continue
            display_path = root / relative_path
            try:
                entry_stat = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            except OSError as exc:
                raise FSError(f"Tree entry changed during commitment: {display_path}") from exc
            if stat.S_ISLNK(entry_stat.st_mode):
                raise FSError(f"Tree contains a symlink: {display_path}")
            if stat.S_ISDIR(entry_stat.st_mode):
                try:
                    child_fd = os.open(name, _directory_open_flags(), dir_fd=directory_fd)
                except OSError as exc:
                    raise FSError(
                        f"Tree directory cannot be opened without following links: {display_path}"
                    ) from exc
                try:
                    opened_stat = os.fstat(child_fd)
                    if _identity_stat_signature(entry_stat) != _identity_stat_signature(
                        opened_stat
                    ):
                        raise FSError(f"Tree directory changed while opening: {display_path}")
                    directories.append(relative_posix)
                    visit(child_fd, relative_path)
                    final_stat = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                    if _identity_stat_signature(final_stat) != _identity_stat_signature(
                        opened_stat
                    ):
                        raise FSError(f"Tree directory changed during commitment: {display_path}")
                finally:
                    os.close(child_fd)
                continue
            if not stat.S_ISREG(entry_stat.st_mode):
                raise FSError(f"Tree contains a non-regular file: {display_path}")
            with _open_relative_regular(directory_fd, (name,), display_path) as descriptor:
                file_sha256, size_bytes = _hash_open_descriptor(descriptor, display_path)
            files.append((relative_posix, file_sha256, size_bytes))

    absolute_root = Path(os.path.abspath(os.fspath(root)))
    with _open_anchored_path(absolute_root) as anchored:
        if not stat.S_ISDIR(os.fstat(anchored.descriptor).st_mode):
            raise FSError(f"Tree root must be a real directory: {absolute_root}")
        visit(anchored.descriptor, Path())

    digest = hashlib.sha256()
    for relative_path in sorted(
        directories, key=lambda value: value.encode("utf-8", "surrogateescape")
    ):
        digest.update(_commitment_path_bytes("directory", relative_path))
    size_total = 0
    for relative_path, file_sha256, size_bytes in sorted(
        files, key=lambda value: value[0].encode("utf-8", "surrogateescape")
    ):
        digest.update(_commitment_path_bytes("file", relative_path))
        digest.update(str(size_bytes).encode("ascii") + b"\0")
        digest.update(file_sha256.encode("ascii") + b"\0")
        size_total += size_bytes
    return {
        "sha256": digest.hexdigest(),
        "file_count": len(files),
        "directory_count": len(directories),
        "size_bytes": size_total,
    }


def calculate_manifest_merkle_root(entries: list[CanonicalFileEntry]) -> str:
    """Calculate the deterministic binary Merkle root for canonical file entries."""
    leaves = [
        hashlib.sha256(
            json.dumps(entry, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
                "utf-8"
            )
        ).digest()
        for entry in entries
    ]
    if not leaves:
        return hashlib.sha256(b"").hexdigest()

    level = leaves
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [
            hashlib.sha256(level[index] + level[index + 1]).digest()
            for index in range(0, len(level), 2)
        ]
    return level[0].hex()
