"""Blob store locale content-addressed, atomico e senza operazioni di rete."""

from __future__ import annotations

import hashlib
import io
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO


class BlobStoreError(RuntimeError):
    """Errore base dello store locale."""


class BlobIntegrityError(BlobStoreError):
    """Il contenuto non corrisponde al digest dichiarato."""


class InvalidDigest(BlobStoreError):
    """Un digest non e uno SHA-256 canonico lowercase."""


@dataclass(frozen=True, slots=True)
class BlobRecord:
    sha256: str
    size_bytes: int
    relative_path: str


@dataclass(frozen=True, slots=True)
class BlobWriteResult:
    record: BlobRecord
    deduplicated: bool


class BlobStore:
    """Store immutabile con layout ``sha256/<2>/<digest>``."""

    def __init__(self, root: Path) -> None:
        expanded = root.expanduser()
        if expanded.is_symlink():
            raise BlobStoreError(f"root blob symlink non ammessa: {expanded}")
        self.root = expanded.resolve()

    def _validate_root(self) -> None:
        if self.root.is_symlink():
            raise BlobStoreError(f"root blob symlink non ammessa: {self.root}")

    def _validate_path(self, path: Path) -> None:
        self._validate_root()
        try:
            relative = path.relative_to(self.root)
        except ValueError as exc:  # pragma: no cover - costruzione interna
            raise BlobStoreError(f"path blob fuori dalla root: {path}") from exc
        current = self.root
        for part in relative.parts:
            current /= part
            if current.is_symlink():
                raise BlobStoreError(f"componente blob symlink non ammesso: {current}")
        resolved = path.resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise BlobStoreError(f"path blob fuori dalla root: {path}")

    def relative_path(self, digest: str) -> Path:
        normalized = _validate_digest(digest)
        return Path("sha256") / normalized[:2] / normalized

    def path(self, digest: str) -> Path:
        return self.root / self.relative_path(digest)

    def put_file(self, source: Path, *, expected_sha256: str | None = None) -> BlobWriteResult:
        source = source.expanduser().resolve()
        if not source.is_file():
            raise BlobStoreError(f"sorgente blob non regolare o assente: {source}")
        with source.open("rb") as stream:
            return self._put_stream(stream, expected_sha256=expected_sha256)

    def put_bytes(self, payload: bytes, *, expected_sha256: str | None = None) -> BlobWriteResult:
        return self._put_stream(io.BytesIO(payload), expected_sha256=expected_sha256)

    def verify(self, digest: str, *, expected_size: int | None = None) -> BlobRecord:
        self._validate_root()
        normalized = _validate_digest(digest)
        target = self.path(normalized)
        self._validate_path(target)
        if not target.is_file():
            raise BlobIntegrityError(f"blob mancante: {normalized}")
        actual_digest, actual_size = hash_file(target)
        if actual_digest != normalized:
            raise BlobIntegrityError(
                f"blob alterato: atteso {normalized}, calcolato {actual_digest}"
            )
        if expected_size is not None and actual_size != expected_size:
            raise BlobIntegrityError(
                f"dimensione blob incoerente: attesa {expected_size}, calcolata {actual_size}"
            )
        return BlobRecord(
            sha256=normalized,
            size_bytes=actual_size,
            relative_path=str(self.relative_path(normalized)),
        )

    def _put_stream(
        self,
        stream: BinaryIO,
        *,
        expected_sha256: str | None,
    ) -> BlobWriteResult:
        self._validate_root()
        if expected_sha256 is not None:
            expected_sha256 = _validate_digest(expected_sha256)
        temporary_root = self.root / ".tmp"
        self._validate_path(temporary_root)
        temporary_root.mkdir(parents=True, exist_ok=True)
        self._validate_path(temporary_root)
        descriptor, temporary_name = tempfile.mkstemp(prefix="blob-", dir=temporary_root)
        temporary = Path(temporary_name)
        digest = hashlib.sha256()
        size_bytes = 0
        try:
            with os.fdopen(descriptor, "wb") as handle:
                while chunk := stream.read(1 << 20):
                    digest.update(chunk)
                    size_bytes += len(chunk)
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())

            checksum = digest.hexdigest()
            if expected_sha256 is not None and checksum != expected_sha256:
                raise BlobIntegrityError(
                    f"checksum sorgente incoerente: atteso {expected_sha256}, calcolato {checksum}"
                )
            target = self.path(checksum)
            self._validate_path(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            self._validate_path(target)
            if target.exists():
                record = self.verify(checksum, expected_size=size_bytes)
                return BlobWriteResult(record=record, deduplicated=True)

            try:
                # Il link atomico pubblica il blob soltanto quando il contenuto e
                # completo e fsyncato. Non sovrascrive mai un digest esistente.
                os.link(temporary, target)
            except FileExistsError:
                record = self.verify(checksum, expected_size=size_bytes)
                return BlobWriteResult(record=record, deduplicated=True)
            _fsync_directory(target.parent)
            record = self.verify(checksum, expected_size=size_bytes)
            return BlobWriteResult(record=record, deduplicated=False)
        finally:
            temporary.unlink(missing_ok=True)


def hash_file(path: Path, chunk_size: int = 1 << 20) -> tuple[str, int]:
    digest = hashlib.sha256()
    size_bytes = 0
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
            size_bytes += len(chunk)
    return digest.hexdigest(), size_bytes


def _validate_digest(digest: str) -> str:
    normalized = digest.strip()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise InvalidDigest("digest atteso: SHA-256 lowercase di 64 caratteri")
    return normalized


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = [
    "BlobIntegrityError",
    "BlobRecord",
    "BlobStore",
    "BlobStoreError",
    "BlobWriteResult",
    "InvalidDigest",
    "hash_file",
]
