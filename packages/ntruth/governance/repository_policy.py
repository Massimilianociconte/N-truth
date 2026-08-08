"""Bounded PRD v8 policy scan over an explicit tracked-tree path set.

The scanner never walks outside the supplied repository root and never claims
coverage of external datasets.  Callers normally obtain ``tracked_paths`` from
``git ls-files``; accepting the list explicitly keeps the core deterministic
and makes path-escape and symlink behavior testable.
"""

from __future__ import annotations

import re
import subprocess
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
    {".arrow", ".db", ".feather", ".jsonl", ".ndjson", ".parquet", ".sqlite", ".sqlite3"}
)
_STRUCTURED_DATA_SUFFIXES = frozenset({".csv", ".json", ".tsv"})
_ARCHIVE_SUFFIXES = frozenset({".7z", ".bz2", ".gz", ".tar", ".xz", ".zip"})
_CORPUS_NAME_MARKERS = frozenset(
    {"challenge", "corpus", "dataset", "participants", "records", "subjects"}
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
    stem_tokens = {token for token in re.split(r"[^a-z0-9]+", path.stem.lower()) if token}
    return suffix in _STRUCTURED_DATA_SUFFIXES and bool(stem_tokens & _CORPUS_NAME_MARKERS)


def _has_symlink_ancestor(root: Path, relative: PurePosixPath) -> bool:
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _binary_findings(path: Path) -> tuple[RepositoryPolicyFindingKindV8, ...]:
    try:
        with path.open("rb") as stream:
            head = stream.read(4096)
    except OSError:
        return ()
    kinds: list[RepositoryPolicyFindingKindV8] = []
    if head.startswith((b"\x1f\x8b", b"PK\x03\x04", b"SQLite format 3\x00")):
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
        path = root.joinpath(*relative.parts)
        if _has_symlink_ancestor(root, relative):
            findings.append(
                _finding(
                    raw,
                    RepositoryPolicyFindingKindV8.UNSAFE_PATH,
                    "tracked path contains a symlink leaf or ancestor",
                )
            )
            continue
        try:
            resolved = path.resolve(strict=True)
        except (OSError, RuntimeError):
            resolved = None
        if resolved is None or not resolved.is_relative_to(root) or not resolved.is_file():
            findings.append(
                _finding(
                    raw,
                    RepositoryPolicyFindingKindV8.UNSAFE_PATH,
                    "tracked path is missing, escapes the root, or is not a regular file",
                )
            )
            continue
        scanned += 1
        path = resolved
        size = path.stat().st_size
        suffix = relative.suffix.lower()
        basename = relative.name
        if size > max_file_bytes:
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
        for binary_kind in _binary_findings(path):
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
        if size <= max_file_bytes:
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                text = ""
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
