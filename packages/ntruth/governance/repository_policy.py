"""Bounded PRD v8 policy scan over an explicit tracked-tree path set.

The scanner never walks outside the supplied repository root and never claims
coverage of external datasets.  Callers normally obtain ``tracked_paths`` from
``git ls-files``; accepting the list explicitly keeps the core deterministic
and makes path-escape and symlink behavior testable.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, Literal, Self

from pydantic import Field, model_validator

from ntruth.schemas.core import content_checksum
from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
_SCAN_EVIDENCE_ID = "REPOSITORY-POLICY-SCAN-V8"
_MODEL_SUFFIXES = frozenset(
    {
        ".bin",
        ".ckpt",
        ".gguf",
        ".h5",
        ".hdf5",
        ".joblib",
        ".npy",
        ".npz",
        ".onnx",
        ".pkl",
        ".pt",
        ".pth",
        ".safetensors",
    }
)
_CORPUS_SUFFIXES = frozenset(
    {
        ".arrow",
        ".db",
        ".duckdb",
        ".feather",
        ".jsonl",
        ".mdb",
        ".ndjson",
        ".parquet",
        ".sqlite",
        ".sqlite3",
    }
)
_STRUCTURED_DATA_SUFFIXES = frozenset({".csv", ".json", ".tsv"})
_RAW_CORPUS_TEXT_SUFFIXES = frozenset(
    {".bio", ".conll", ".iob", ".iob2", ".tei", ".text", ".txt", ".xml"}
)
_CORPUS_NAME_SUFFIXES = _STRUCTURED_DATA_SUFFIXES | _RAW_CORPUS_TEXT_SUFFIXES
_DOCUMENTATION_SCHEMA_SUFFIX = ".schema.json"
_ARCHIVE_SUFFIXES = frozenset({".7z", ".bz2", ".gz", ".rar", ".tar", ".tgz", ".xz", ".zip", ".zst"})
_CORPUS_NAME_MARKERS = frozenset(
    {
        "challenge",
        "corpus",
        "dataset",
        "participant",
        "participants",
        "record",
        "records",
        "subject",
        "subjects",
    }
)
_SECRET_SUFFIXES = frozenset({".key", ".p12", ".pem", ".pfx"})
_PRIVACY_PAYLOAD_SUFFIXES = frozenset({".csv", ".json", ".jsonl", ".tsv", ".txt", ".xml"})
_PRIVATE_KEY = re.compile(r"-----BEGIN (?:DSA |EC |ENCRYPTED |OPENSSH |RSA )?PRIVATE KEY-----")
_HIGH_CONFIDENCE_TOKEN = re.compile(
    r"(?:AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,})"
)
_EMAIL = re.compile(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


class RepositoryPolicyFindingKindV8(StrEnum):
    NO_CORPUS = "NO_CORPUS"
    MODEL_OR_WEIGHT = "MODEL_OR_WEIGHT"
    PRIVACY_RISK = "PRIVACY_RISK"
    SECRET = "SECRET"
    LARGE_FILE = "LARGE_FILE"
    UNSAFE_PATH = "UNSAFE_PATH"


class RepositoryPolicyFindingV8(KernelModel):
    path: NonBlankStr
    kind: RepositoryPolicyFindingKindV8
    rationale: NonBlankStr


class RepositoryPolicyReportV8(KernelModel):
    report_id: NonBlankStr
    content_checksum: Sha256
    scope: Literal["GIT_TRACKED_TREE_ONLY"] = "GIT_TRACKED_TREE_ONLY"
    external_datasets_inspected: Literal[False] = False
    detection_semantics: Literal["NO_FINDING_DETECTED_NOT_AN_ATTESTATION"] = (
        "NO_FINDING_DETECTED_NOT_AN_ATTESTATION"
    )
    tracked_paths_checksum: Sha256
    scanned_file_count: int = Field(ge=0)
    max_file_bytes: int = Field(gt=0)
    findings: KnowledgeValue[tuple[RepositoryPolicyFindingV8, ...]]

    @property
    def clean(self) -> bool:
        return self.findings.knowledge_state is KnowledgeState.ABSENT_EXPLICIT

    @model_validator(mode="after")
    def _addressed(self) -> Self:
        expected = content_checksum(
            self.model_dump(mode="json", exclude={"report_id", "content_checksum"})
        )
        if self.content_checksum != expected:
            raise ValueError("repository policy report checksum mismatch")
        if self.report_id != f"REPOSITORY-POLICY-{expected[:20]}":
            raise ValueError("repository policy report ID mismatch")
        return self


def _finding(
    path: str, kind: RepositoryPolicyFindingKindV8, rationale: str
) -> RepositoryPolicyFindingV8:
    return RepositoryPolicyFindingV8(path=path, kind=kind, rationale=rationale)


def _unsafe_relative_path(raw: str) -> bool:
    if not raw or "\\" in raw:
        return True
    path = PurePosixPath(raw)
    return path.is_absolute() or ".." in path.parts or "." in path.parts


def _is_forbidden_corpus_path(path: PurePosixPath) -> bool:
    normalized = path.as_posix().lower()
    forbidden_prefixes = (
        "data/raw/",
        "data/external/",
        "data/processed/",
        "datasets/",
        "corpus/",
        "corpora/",
        "task_corpora/",
    )
    suffix = path.suffix.lower()
    if normalized.startswith(forbidden_prefixes) or suffix in _CORPUS_SUFFIXES:
        return True
    if suffix in _ARCHIVE_SUFFIXES:
        return True
    # Schemas below docs are metadata contracts, not record payloads.  The same
    # corpus-like name remains forbidden for every non-documentation location.
    if normalized.startswith("docs/") and path.name.lower().endswith(_DOCUMENTATION_SCHEMA_SUFFIX):
        return False
    stem_tokens = {token for token in re.split(r"[^a-z0-9]+", path.stem.lower()) if token}
    return suffix in _CORPUS_NAME_SUFFIXES and bool(stem_tokens & _CORPUS_NAME_MARKERS)


@dataclass(frozen=True)
class _TrackedFileInspection:
    size: int
    head: bytes
    text: str | None


def _open_flags(*, directory: bool) -> int:
    no_follow = getattr(os, "O_NOFOLLOW", 0)
    directory_only = getattr(os, "O_DIRECTORY", 0)
    if not no_follow or not directory_only:
        raise OSError("platform lacks required no-follow repository scan support")
    flags = os.O_RDONLY | no_follow | getattr(os, "O_CLOEXEC", 0)
    if directory:
        flags |= directory_only
    return flags


def _open_beneath(root_fd: int, relative: PurePosixPath) -> int:
    """Open a regular-file candidate below ``root_fd`` without following links."""

    parent_fd = os.dup(root_fd)
    try:
        for part in relative.parts[:-1]:
            child_fd = os.open(
                part,
                _open_flags(directory=True),
                dir_fd=parent_fd,
            )
            os.close(parent_fd)
            parent_fd = child_fd
        return os.open(
            relative.name,
            _open_flags(directory=False),
            dir_fd=parent_fd,
        )
    finally:
        os.close(parent_fd)


def _metadata_signature(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _read_up_to(file_fd: int, limit: int) -> bytes:
    chunks: list[bytes] = []
    remaining = limit
    while remaining:
        chunk = os.read(file_fd, min(remaining, 65_536))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _inspect_tracked_file(
    root_fd: int,
    relative: PurePosixPath,
    *,
    max_file_bytes: int,
) -> _TrackedFileInspection:
    """Read bytes and metadata from one stable, no-follow descriptor."""

    file_fd = _open_beneath(root_fd, relative)
    try:
        initial = os.fstat(file_fd)
        if not stat.S_ISREG(initial.st_mode):
            raise OSError("tracked path is not a regular file")
        read_limit = max_file_bytes + 1 if initial.st_size <= max_file_bytes else 4096
        payload = _read_up_to(file_fd, read_limit)
        final = os.fstat(file_fd)
        if _metadata_signature(initial) != _metadata_signature(final):
            raise OSError("tracked file changed while it was inspected")

        verification_fd = _open_beneath(root_fd, relative)
        try:
            verification = os.fstat(verification_fd)
        finally:
            os.close(verification_fd)
        if _metadata_signature(verification) != _metadata_signature(final):
            raise OSError("tracked path was replaced while it was inspected")

        observed_size = max(initial.st_size, len(payload))
        text: str | None = None
        if observed_size <= max_file_bytes:
            with suppress(UnicodeDecodeError):
                text = payload.decode("utf-8")
        return _TrackedFileInspection(
            size=observed_size,
            head=payload[:4096],
            text=text,
        )
    finally:
        os.close(file_fd)


def _binary_findings(head: bytes) -> tuple[RepositoryPolicyFindingKindV8, ...]:
    kinds: list[RepositoryPolicyFindingKindV8] = []
    archive_magic = (
        b"\x1f\x8b",
        b"BZh",
        b"PK\x03\x04",
        b"PK\x05\x06",
        b"PK\x07\x08",
        b"\x28\xb5\x2f\xfd",
        b"Rar!\x1a\x07\x00",
        b"Rar!\x1a\x07\x01\x00",
        b"\xfd7zXZ\x00",
        b"7z\xbc\xaf'\x1c",
    )
    if head.startswith((*archive_magic, b"SQLite format 3\x00")) or (
        len(head) >= 262 and head[257:262] == b"ustar"
    ):
        kinds.append(RepositoryPolicyFindingKindV8.NO_CORPUS)
    if head.startswith((b"\x89HDF\r\n\x1a\n", b"\x93NUMPY")):
        kinds.append(RepositoryPolicyFindingKindV8.MODEL_OR_WEIGHT)
    return tuple(kinds)


def _privacy_payload_path(path: PurePosixPath) -> bool:
    return path.suffix.lower() in _PRIVACY_PAYLOAD_SUFFIXES and any(
        part.lower() in {"annotations", "participants", "subjects"} for part in path.parts
    )


def scan_tracked_repository_v8(
    repository_root: Path,
    tracked_paths: tuple[str, ...],
    *,
    max_file_bytes: int = 1_048_576,
) -> RepositoryPolicyReportV8:
    if max_file_bytes < 1:
        raise ValueError("repository policy max_file_bytes must be positive")
    root = repository_root.resolve(strict=True)
    findings: list[RepositoryPolicyFindingV8] = []
    scanned = 0
    canonical_paths = tuple(sorted(dict.fromkeys(tracked_paths)))
    try:
        root_fd = os.open(root, _open_flags(directory=True))
    except OSError:
        root_fd = None
    try:
        for raw in canonical_paths:
            if _unsafe_relative_path(raw):
                findings.append(
                    _finding(
                        raw or "<blank>",
                        RepositoryPolicyFindingKindV8.UNSAFE_PATH,
                        "path escapes or is not a canonical repository-relative path",
                    )
                )
                continue
            relative = PurePosixPath(raw)
            if root_fd is None:
                findings.append(
                    _finding(
                        raw,
                        RepositoryPolicyFindingKindV8.UNSAFE_PATH,
                        "repository root could not be opened for a no-follow policy scan",
                    )
                )
                continue
            try:
                inspection = _inspect_tracked_file(
                    root_fd,
                    relative,
                    max_file_bytes=max_file_bytes,
                )
            except (OSError, RuntimeError):
                findings.append(
                    _finding(
                        raw,
                        RepositoryPolicyFindingKindV8.UNSAFE_PATH,
                        "tracked file could not be inspected atomically; policy scan fails closed",
                    )
                )
                continue
            scanned += 1
            suffix = relative.suffix.lower()
            basename = relative.name
            if inspection.size > max_file_bytes:
                findings.append(
                    _finding(
                        raw,
                        RepositoryPolicyFindingKindV8.LARGE_FILE,
                        f"tracked file exceeds {max_file_bytes} bytes",
                    )
                )
            if _is_forbidden_corpus_path(relative):
                findings.append(
                    _finding(
                        raw,
                        RepositoryPolicyFindingKindV8.NO_CORPUS,
                        "tracked path has corpus payload semantics",
                    )
                )
            if suffix in _MODEL_SUFFIXES or relative.as_posix().startswith("models/checkpoints/"):
                findings.append(
                    _finding(
                        raw,
                        RepositoryPolicyFindingKindV8.MODEL_OR_WEIGHT,
                        "model weights or checkpoints must not be tracked",
                    )
                )
            existing_kinds = {item.kind for item in findings if item.path == raw}
            for binary_kind in _binary_findings(inspection.head):
                if binary_kind not in existing_kinds:
                    findings.append(
                        _finding(
                            raw,
                            binary_kind,
                            "forbidden archive, database, model or weight magic detected",
                        )
                    )
            if (
                suffix in _SECRET_SUFFIXES
                or basename == ".env"
                or (basename.startswith(".env.") and basename != ".env.example")
            ):
                findings.append(
                    _finding(
                        raw,
                        RepositoryPolicyFindingKindV8.SECRET,
                        "secret-bearing filename is forbidden",
                    )
                )
            text = inspection.text
            if text and (_PRIVATE_KEY.search(text) or _HIGH_CONFIDENCE_TOKEN.search(text)):
                findings.append(
                    _finding(
                        raw,
                        RepositoryPolicyFindingKindV8.SECRET,
                        "high-confidence secret marker detected",
                    )
                )
            if text and _privacy_payload_path(relative) and _EMAIL.search(text):
                findings.append(
                    _finding(
                        raw,
                        RepositoryPolicyFindingKindV8.PRIVACY_RISK,
                        "direct identifier found in a payload-like tracked file",
                    )
                )
    finally:
        if root_fd is not None:
            os.close(root_fd)

    ordered = tuple(
        sorted(
            findings,
            key=lambda item: (item.path, item.kind.value, item.rationale),
        )
    )
    if ordered:
        knowledge = KnowledgeValue[tuple[RepositoryPolicyFindingV8, ...]](
            knowledge_state=KnowledgeState.PRESENT,
            value=ordered,
            evidence_ids=(_SCAN_EVIDENCE_ID,),
            claim_scope_id="REPOSITORY-POLICY:TRACKED-TREE",
        )
    else:
        knowledge = KnowledgeValue[tuple[RepositoryPolicyFindingV8, ...]](
            knowledge_state=KnowledgeState.ABSENT_EXPLICIT,
            evidence_ids=(_SCAN_EVIDENCE_ID,),
            claim_scope_id="REPOSITORY-POLICY:TRACKED-TREE",
        )
    fields: dict[str, Any] = {
        "scope": "GIT_TRACKED_TREE_ONLY",
        "external_datasets_inspected": False,
        "detection_semantics": "NO_FINDING_DETECTED_NOT_AN_ATTESTATION",
        "tracked_paths_checksum": content_checksum(canonical_paths),
        "scanned_file_count": scanned,
        "max_file_bytes": max_file_bytes,
        "findings": knowledge,
    }
    draft = RepositoryPolicyReportV8.model_construct(
        report_id="REPOSITORY-POLICY-PENDING",
        content_checksum="0" * 64,
        **fields,
    )
    checksum = content_checksum(
        draft.model_dump(mode="json", exclude={"report_id", "content_checksum"})
    )
    return RepositoryPolicyReportV8(
        report_id=f"REPOSITORY-POLICY-{checksum[:20]}",
        content_checksum=checksum,
        **fields,
    )


def tracked_paths_from_git_v8(repository_root: Path) -> tuple[str, ...]:
    """Read the bounded tracked path set without inspecting untracked/external data."""

    completed = subprocess.run(
        ["git", "-C", str(repository_root.resolve()), "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    return tuple(item.decode("utf-8") for item in completed.stdout.split(b"\0") if item)


__all__ = [
    "RepositoryPolicyFindingKindV8",
    "RepositoryPolicyFindingV8",
    "RepositoryPolicyReportV8",
    "scan_tracked_repository_v8",
    "tracked_paths_from_git_v8",
]
