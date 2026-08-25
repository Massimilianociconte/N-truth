"""Filesystem utilities for exFAT resilience, security, AppleDouble filtering, and Merkle manifests."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shutil
import tarfile
import tempfile
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

MAX_ARCHIVE_FILE_COUNT = 100_000
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 20 * 1024 * 1024 * 1024  # 20 GB
MAX_ARCHIVE_COMPRESSION_RATIO = 100.0
EMPTY_FILE_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


class FSError(RuntimeError):
    """Filesystem operational error."""


def is_ignorable_metadata(path: Path | str) -> bool:
    name = Path(path).name
    return name == "__MACOSX" or name == ".DS_Store" or name.startswith("._")


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


def safe_extract_zip(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    base = destination.resolve()
    total_files = 0
    total_uncompressed = 0
    archive_size = archive.stat().st_size or 1

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


def safe_extract_tar(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    base = destination.resolve()
    total_files = 0
    total_uncompressed = 0
    archive_size = archive.stat().st_size or 1

    with tarfile.open(archive, "r:*") as tf:
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
            tf.extract(member, destination)


def safe_extract_archive(archive: Path, destination: Path) -> None:
    name = archive.name.lower()
    if name.endswith(".zip"):
        safe_extract_zip(archive, destination)
    elif name.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2")):
        safe_extract_tar(archive, destination)
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


def atomic_extract_archive(archive: Path, destination: Path, metadata: Mapping[str, Any]) -> None:
    temp_parent = destination.parent
    temp_parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=f".{destination.name}.extract.", dir=str(temp_parent)))
    try:
        unpack = temp_dir / "unpack"
        safe_extract_archive(archive, unpack)
        root = strip_single_root(unpack)
        final_temp = temp_dir / "final"
        if root == unpack:
            final_temp.mkdir()
            for child in meaningfull_entries(unpack):
                if child == final_temp or not child.exists() or is_ignorable_metadata(child):
                    continue
                shutil.move(str(child), str(final_temp / child.name))
        else:
            shutil.move(str(root), str(final_temp))

        marker_data = dict(metadata)
        marker_data.update({"archive_sha256": sha256_file(archive)})
        atomic_write_json(final_temp / ".ntruth_complete.json", marker_data)

        if destination.exists():
            shutil.rmtree(destination)
        os.replace(final_temp, destination)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def calculate_merkle_root(directories: list[Path]) -> str:
    """Calculates a deterministic SHA-256 Merkle root across canonical files in given directories."""
    file_hashes: list[str] = []
    for directory in sorted(directories, key=lambda p: str(p)):
        if not directory.exists():
            continue
        if directory.is_file():
            if not is_ignorable_metadata(directory):
                file_hashes.append(f"{directory.name}:{sha256_file(directory)}")
            continue
        for root, dirs, files in os.walk(directory):
            # Sort in place for deterministic walk
            dirs.sort()
            files.sort()
            for file_name in files:
                rel_path = Path(root, file_name)
                if is_ignorable_metadata(rel_path):
                    continue
                if (
                    "logs" in rel_path.parts
                    or "run-history" in rel_path.parts
                    or "quarantine" in rel_path.parts
                ):
                    continue
                file_hash = sha256_file(rel_path)
                item_rel = rel_path.relative_to(directory)
                file_hashes.append(f"{item_rel}:{file_hash}")

    combined = "\n".join(sorted(file_hashes)).encode("utf-8")
    return hashlib.sha256(combined).hexdigest()
