"""Bounded PRD v8 policy scan over an explicit tracked-tree path set.

The scanner never walks outside the supplied repository root and never claims
coverage of external datasets.  Callers normally obtain ``tracked_paths`` from
``git ls-files``; accepting the list explicitly keeps the core deterministic
and makes path-escape and symlink behavior testable.
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import re
import stat
import subprocess
import sys
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
_MountIdentity = tuple[str, ...]
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
_ARCHIVE_SUFFIXES = frozenset({".7z", ".bz2", ".gz", ".rar", ".tar", ".tgz", ".xz", ".zip", ".zst"})
_CORPUS_NAME_MARKERS = frozenset(
    {
        "challenge",
        "corpus",
        "corpora",
        "dataset",
        "participant",
        "participants",
        "record",
        "records",
        "subject",
        "subjects",
    }
)
_GOVERNED_SOURCE_ROOTS = ("packages/", "scripts/", "tests/")
_GOVERNED_SOURCE_SUFFIXES = frozenset(
    {".c", ".cpp", ".go", ".js", ".jsx", ".mjs", ".py", ".pyi", ".rs", ".sh", ".ts", ".tsx"}
)
_REVIEWED_REPOSITORY_ASSET_SHA256 = {
    "docs/audits/dataset-pipeline-20260803/REPORT_B_DATASET_PIPELINE.md": (
        "5a2f6ea73a4fef0943c1834a57f7e9a3e8866c360bfe37365c14365ffc9aabe4"
    ),
    "docs/audits/dataset-pipeline-20260803/idempotency-summary.json": (
        "c7db93671152579563c38a01d652bab0aa5baa58ff219772ef523dac7ff3d889"
    ),
    "docs/audits/dataset-pipeline-20260803/merkle-lineage.json": (
        "4b8868455c92321c71d110b283fda58bbaf46848b4d462bfeea32f8ad689ea02"
    ),
    "docs/audits/dataset-pipeline-20260803/source-and-license-summary.json": (
        "4ef4ae2a910b25a5c39b5d1c8968cfb603b9527e908d8eca560b21145a0cdf80"
    ),
    "docs/audits/dataset-pipeline-20260803/split-authority-summary.json": (
        "ac19f7334bdbdd62d6a7e437d1474703c43cbb5d7f2c98d29e91a9d444f9507e"
    ),
    "docs/audits/dataset-pipeline-20260803/volume-constraints.md": (
        "9aadfee7de4877bafbba62bcc6c79dd2df7060f906e5d9ba93bc12f38e1de026"
    ),
    "docs/dataset-assessment.md": (
        "02a90ba8681aa0134de4c1be0e644af98351ccd4f67e5748443a0f17979e23d3"
    ),
    "docs/plans/modernbert-task-corpora-v1.md": (
        "5f6fe0c7c86fc7cdc958d836d33af0008e0228034711fb1598e8953e94feb035"
    ),
    "docs/task_corpora/build_manifest.schema.json": (
        "c082b3509e8fe3f54b8107ec932bacc029893882878f792facdfb198e68d9ffc"
    ),
    "docs/task_corpora/c1.1-sourcedata-document-provenance-investigation.md": (
        "12b632842fd3bbf4d005a697b2760c1d8f206334c537fd34d35495887555a04c"
    ),
    "docs/task_corpora/c1.1-sourcedata-document-provenance-plan.md": (
        "4d334d93251384bd8a6198fc4bd1495e523f1237955ea440fc40b08006aeeb2f"
    ),
    "docs/task_corpora/c1.1-sourcedata-upstream-assets.yaml": (
        "f6b62ce6bf0df697dd4ac1efe531255faa4b3f1f3d3a44e186ca40de60daaa0e"
    ),
    "docs/task_corpora/c2-preclinie-design.md": (
        "01939ff39aeca3ad4ce44a9f41af1cea7a3b91dff11ef2fbf7817e9c6c44162f"
    ),
    "docs/task_corpora/jsonl-framing-contract.md": (
        "a90ba402c8861f8e2dac6ceed6d72f8ee328e69b226c80d99da215ba9a62f222"
    ),
    "docs/task_corpora/license_use_decision.schema.json": (
        "187e2d832928c0648158d93495403cbe647d69c4798ae8acd16c8ba0839370a6"
    ),
    "docs/task_corpora/pr3-post-merge-attestation.md": (
        "55eb90b303412b7cb776029fbf9a62ed0bd8dabbba908d078627bd1cc193b3e0"
    ),
    "docs/task_corpora/pr4-pr5-post-merge-attestation.md": (
        "9d7ba16c0f5dacb39feb36e41dbf1450690e192e95b568dd3e094fa082ef9e4c"
    ),
    "docs/task_corpora/prd-v7-dataset-impact-matrix.md": (
        "37019d2cd7be209d9b027e71f95658cd954ede421a0db29a6655f984e74f70ae"
    ),
    "docs/task_corpora/provisional-reality-gate-ref.md": (
        "51d7d89b215e8b332fdc216aea0e960463aa0171acdc2bf7049258b33185a91a"
    ),
    "docs/task_corpora/root-dataset-contract-compatibility-matrix.md": (
        "1f8647ed087b97c9e9e7ff1dacdc8d07e1b739cb5ee5c235f291949df19c1a37"
    ),
    "docs/task_corpora/sourcedata-entity-roles-label-map.md": (
        "eb67bd97dead78eb39b8fdc9838f0ee68f77946e6629e28d9d6eda2236831296"
    ),
    "docs/task_corpora/storage-estimate-c0-c1.md": (
        "14155139b88d0002917d3cd3d3d3cb7f9989ea3bd63f0914af3659a3c63d8032"
    ),
    "docs/task_corpora/task_record.schema.json": (
        "2b19e6a390d0f35cc51afa149db3b18e1d9cb3e98b9969d005df1529f771a452"
    ),
    "docs/task_corpora/workstream-c-c0-c1-readiness.md": (
        "43428f95725530dc9792c397ddb77d6059e5ecdd786c84d13025b6fccb7213db"
    ),
    "packages/ntruth/task_corpora/label_maps/sourcedata_entity_roles.json": (
        "6b1921ba6c52761911ca3a59a0b4fff7f4a18c708c2a7e81a55c0ac54055bf6b"
    ),
    "packages/ntruth/task_corpora/license_decisions/sourcedata.json": (
        "1b40388623703ed39f3a13e0b330048031ee10168873d78ecb869c7558a79626"
    ),
}
_SECRET_SUFFIXES = frozenset({".key", ".p12", ".pem", ".pfx"})
_PRIVACY_PAYLOAD_SUFFIXES = frozenset({".csv", ".json", ".jsonl", ".tsv", ".txt", ".xml"})
_PRIVATE_KEY = re.compile(r"-----BEGIN (?:DSA |EC |ENCRYPTED |OPENSSH |RSA )?PRIVATE KEY-----")
_HIGH_CONFIDENCE_TOKEN = re.compile(
    r"(?:AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,})"
)
_EMAIL = re.compile(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_GIT_LFS_OID = re.compile(r"^oid sha256:[0-9a-f]{64}$")
_GIT_LFS_SIZE = re.compile(r"^size [0-9]+$")
_MOUNT_ESCAPE = re.compile(r"\\([0-7]{3})")


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
    tracked_path_count: int = Field(ge=0)
    scanned_file_count: int = Field(ge=0)
    inspection_complete: bool
    max_file_bytes: int = Field(gt=0)
    findings: KnowledgeValue[tuple[RepositoryPolicyFindingV8, ...]]

    @property
    def clean(self) -> bool:
        return self.findings.knowledge_state is KnowledgeState.ABSENT_EXPLICIT

    @model_validator(mode="after")
    def _addressed(self) -> Self:
        expected_complete = self.scanned_file_count == self.tracked_path_count
        if self.scanned_file_count > self.tracked_path_count:
            raise ValueError("repository policy scanned count exceeds tracked path count")
        if self.inspection_complete is not expected_complete:
            raise ValueError("repository policy inspection completeness mismatch")
        if not self.inspection_complete and not any(
            finding.kind is RepositoryPolicyFindingKindV8.UNSAFE_PATH
            for finding in self.findings.value or ()
        ):
            raise ValueError("incomplete repository policy scan lacks an unsafe-path finding")
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


def _path_marker_tokens(path: PurePosixPath) -> frozenset[str]:
    tokens: set[str] = set()
    for component in path.parts:
        tokens.update(token for token in re.split(r"[^a-z0-9]+", component.lower()) if token)
    return frozenset(tokens)


def _is_governed_metadata_path(path: PurePosixPath, text: str | None) -> bool:
    normalized = path.as_posix()
    suffix = path.suffix.lower()
    if (
        text is not None
        and normalized.startswith(_GOVERNED_SOURCE_ROOTS)
        and suffix in _GOVERNED_SOURCE_SUFFIXES
    ):
        return True
    expected_sha256 = _REVIEWED_REPOSITORY_ASSET_SHA256.get(normalized)
    return (
        expected_sha256 is not None
        and text is not None
        and hashlib.sha256(text.encode("utf-8")).hexdigest() == expected_sha256
    )


def _is_forbidden_corpus_path(path: PurePosixPath, text: str | None) -> bool:
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
    marker_semantics = bool(_path_marker_tokens(path) & _CORPUS_NAME_MARKERS)
    return marker_semantics and not _is_governed_metadata_path(path, text)


def _decode_mount_field(value: str) -> str:
    return _MOUNT_ESCAPE.sub(lambda match: chr(int(match.group(1), 8)), value)


def _platform_mount_points() -> frozenset[Path] | None:
    """Return a complete platform mount inventory, or ``None`` when unavailable."""

    try:
        raw_mounts: list[str] = []
        if sys.platform.startswith("linux"):
            lines = Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines()
            for line in lines:
                left, separator, _right = line.partition(" - ")
                fields = left.split()
                if not separator or len(fields) < 5:
                    return None
                raw_mounts.append(fields[4])
        elif sys.platform == "darwin":
            completed = subprocess.run(
                ["/sbin/mount"],
                check=True,
                capture_output=True,
                text=True,
            )
            for line in completed.stdout.splitlines():
                match = re.fullmatch(r".+ on (.+) \(.+\)", line)
                if match is None:
                    return None
                raw_mounts.append(match.group(1))
        else:
            return None
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return None

    mount_points: set[Path] = set()
    for raw_mount in raw_mounts:
        decoded = Path(_decode_mount_field(raw_mount))
        if not decoded.is_absolute():
            return None
        mount_points.add(decoded)
    return frozenset(mount_points)


def _mount_points_for_repository(repository_root: Path) -> frozenset[Path] | None:
    """Return mount points strictly below a resolved repository root."""

    platform_mounts = _platform_mount_points()
    if platform_mounts is None:
        return None
    descendants: set[Path] = set()
    for mount_point in platform_mounts:
        try:
            mount_point.relative_to(repository_root)
        except ValueError:
            continue
        if mount_point != repository_root:
            descendants.add(mount_point)
    return frozenset(descendants)


def _crosses_mount_boundary(
    repository_root: Path,
    relative: PurePosixPath,
    mount_points: frozenset[Path],
) -> bool:
    candidate = repository_root.joinpath(*relative.parts)
    return any(
        mount_point == candidate or mount_point in candidate.parents for mount_point in mount_points
    )


def _descriptor_mount_identity(file_fd: int) -> _MountIdentity | None:
    """Return mount identity bound to an already-open descriptor, or fail closed."""

    if sys.platform.startswith("linux"):
        try:
            lines = Path(f"/proc/self/fdinfo/{file_fd}").read_text(encoding="ascii").splitlines()
        except (OSError, UnicodeError):
            return None
        mount_ids = [line.partition(":")[2].strip() for line in lines if line.startswith("mnt_id:")]
        if len(mount_ids) != 1 or not mount_ids[0].isdigit():
            return None
        return ("linux-mnt-id", mount_ids[0])

    if sys.platform == "darwin":
        # Darwin's 64-bit ``struct statfs`` is 2168 bytes.  The selected
        # fields are descriptor-bound: fsid [48:56], filesystem type [72:88],
        # mount-on name [88:1112], and mount-from name [1112:2136].
        statfs_buffer = ctypes.create_string_buffer(2168)
        try:
            libc = ctypes.CDLL(None, use_errno=True)
            fstatfs = libc.fstatfs
            if fstatfs(file_fd, ctypes.byref(statfs_buffer)) != 0:
                return None
        except (AttributeError, OSError, ctypes.ArgumentError):
            return None
        payload = statfs_buffer.raw
        selected = payload[48:56] + payload[72:2136]
        return ("darwin-fstatfs", hashlib.sha256(selected).hexdigest())

    return None


def _require_same_mount(file_fd: int, root_mount_identity: _MountIdentity) -> None:
    observed = _descriptor_mount_identity(file_fd)
    if observed is None:
        raise OSError("descriptor-bound mount identity is unavailable")
    if observed != root_mount_identity:
        raise OSError("tracked path crosses a descriptor-observed mount boundary")


@dataclass(frozen=True)
class _TrackedFileInspection:
    size: int
    head: bytes
    tail: bytes
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


def _open_beneath(
    root_fd: int,
    relative: PurePosixPath,
    *,
    root_device: int,
    root_mount_identity: _MountIdentity,
) -> int:
    """Open a same-filesystem regular-file candidate below ``root_fd`` without links."""

    parent_fd = os.dup(root_fd)
    try:
        for part in relative.parts[:-1]:
            child_fd = os.open(
                part,
                _open_flags(directory=True),
                dir_fd=parent_fd,
            )
            try:
                _require_same_mount(child_fd, root_mount_identity)
                child_metadata = os.fstat(child_fd)
            except OSError:
                os.close(child_fd)
                raise
            if child_metadata.st_dev != root_device:
                os.close(child_fd)
                raise OSError("tracked path crosses a filesystem boundary")
            os.close(parent_fd)
            parent_fd = child_fd
        leaf_fd = os.open(
            relative.name,
            _open_flags(directory=False),
            dir_fd=parent_fd,
        )
        try:
            _require_same_mount(leaf_fd, root_mount_identity)
        except OSError:
            os.close(leaf_fd)
            raise
        return leaf_fd
    finally:
        os.close(parent_fd)


def _metadata_signature(metadata: os.stat_result) -> tuple[int, int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _read_exact(file_fd: int, expected_bytes: int) -> bytes:
    chunks: list[bytes] = []
    remaining = expected_bytes
    while remaining:
        chunk = os.read(file_fd, min(remaining, 65_536))
        if not chunk:
            raise OSError("tracked file ended before the expected bounded byte count")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _inspect_tracked_file(
    root_fd: int,
    relative: PurePosixPath,
    *,
    max_file_bytes: int,
    root_device: int,
    root_mount_identity: _MountIdentity,
) -> _TrackedFileInspection:
    """Read bytes and metadata from one stable, no-follow descriptor."""

    file_fd = _open_beneath(
        root_fd,
        relative,
        root_device=root_device,
        root_mount_identity=root_mount_identity,
    )
    try:
        initial = os.fstat(file_fd)
        if not stat.S_ISREG(initial.st_mode):
            raise OSError("tracked path is not a regular file")
        if initial.st_dev != root_device:
            raise OSError("tracked file crosses a filesystem boundary")
        if initial.st_nlink != 1:
            raise OSError(
                "tracked path has multiple hard links; repository provenance is ambiguous"
            )
        read_limit = max_file_bytes + 1 if initial.st_size <= max_file_bytes else 4096
        payload = _read_exact(file_fd, min(initial.st_size, read_limit))
        final = os.fstat(file_fd)
        if _metadata_signature(initial) != _metadata_signature(final):
            raise OSError("tracked file changed while it was inspected")

        verification_fd = _open_beneath(
            root_fd,
            relative,
            root_device=root_device,
            root_mount_identity=root_mount_identity,
        )
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
            tail=payload[-4096:],
            text=text,
        )
    finally:
        os.close(file_fd)


def _binary_findings(head: bytes, tail: bytes) -> tuple[RepositoryPolicyFindingKindV8, ...]:
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
    corpus_signature = (
        head.startswith((*archive_magic, b"SQLite format 3\x00", b"ARROW1"))
        or (head.startswith(b"PAR1") and tail.endswith(b"PAR1"))
        or (head.startswith(b"FEA1") and tail.endswith(b"FEA1"))
        or (len(head) >= 12 and head[8:12] == b"DUCK")
    )
    if corpus_signature or (len(head) >= 262 and head[257:262] == b"ustar"):
        kinds.append(RepositoryPolicyFindingKindV8.NO_CORPUS)
    if head.startswith((b"\x89HDF\r\n\x1a\n", b"\x93NUMPY", b"GGUF")):
        kinds.append(RepositoryPolicyFindingKindV8.MODEL_OR_WEIGHT)
    return tuple(kinds)


def _is_git_lfs_pointer(text: str) -> bool:
    lines = text.splitlines()
    return (
        len(lines) >= 3
        and lines[0] == "version https://git-lfs.github.com/spec/v1"
        and any(_GIT_LFS_OID.fullmatch(line) for line in lines[1:])
        and any(_GIT_LFS_SIZE.fullmatch(line) for line in lines[1:])
    )


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
    mount_points = _mount_points_for_repository(root)
    root_fd: int | None = None
    root_device: int | None = None
    root_mount_identity: _MountIdentity | None = None
    try:
        root_fd = os.open(root, _open_flags(directory=True))
        root_device = os.fstat(root_fd).st_dev
        root_mount_identity = _descriptor_mount_identity(root_fd)
    except OSError:
        if root_fd is not None:
            os.close(root_fd)
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
            if mount_points is None:
                findings.append(
                    _finding(
                        raw,
                        RepositoryPolicyFindingKindV8.UNSAFE_PATH,
                        "platform mount-boundary inventory is unavailable; policy scan fails closed",
                    )
                )
                continue
            if _crosses_mount_boundary(root, relative, mount_points):
                findings.append(
                    _finding(
                        raw,
                        RepositoryPolicyFindingKindV8.UNSAFE_PATH,
                        "tracked path crosses an inventoried mount boundary; bytes were not inspected",
                    )
                )
                continue
            if root_fd is None or root_device is None:
                findings.append(
                    _finding(
                        raw,
                        RepositoryPolicyFindingKindV8.UNSAFE_PATH,
                        "repository root could not be opened for a no-follow policy scan",
                    )
                )
                continue
            if root_mount_identity is None:
                findings.append(
                    _finding(
                        raw,
                        RepositoryPolicyFindingKindV8.UNSAFE_PATH,
                        "descriptor-bound mount identity is unavailable; policy scan fails closed",
                    )
                )
                continue
            try:
                inspection = _inspect_tracked_file(
                    root_fd,
                    relative,
                    max_file_bytes=max_file_bytes,
                    root_device=root_device,
                    root_mount_identity=root_mount_identity,
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
            if _is_forbidden_corpus_path(relative, inspection.text):
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
            for binary_kind in _binary_findings(inspection.head, inspection.tail):
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
            if text and _is_git_lfs_pointer(text):
                findings.append(
                    _finding(
                        raw,
                        RepositoryPolicyFindingKindV8.UNSAFE_PATH,
                        "Git LFS pointer references external bytes outside tracked-tree inspection",
                    )
                )
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
        "tracked_path_count": len(canonical_paths),
        "scanned_file_count": scanned,
        "inspection_complete": scanned == len(canonical_paths),
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
    payload = completed.stdout
    if payload and not payload.endswith(b"\0"):
        raise RuntimeError("incomplete tracked-path enumeration: missing terminal NUL")
    encoded_paths = payload[:-1].split(b"\0") if payload else []
    if any(not item for item in encoded_paths):
        raise RuntimeError("incomplete tracked-path enumeration: empty path entry")
    try:
        return tuple(item.decode("utf-8") for item in encoded_paths)
    except UnicodeDecodeError as exc:
        raise RuntimeError("incomplete tracked-path enumeration: invalid UTF-8 path") from exc


__all__ = [
    "RepositoryPolicyFindingKindV8",
    "RepositoryPolicyFindingV8",
    "RepositoryPolicyReportV8",
    "scan_tracked_repository_v8",
    "tracked_paths_from_git_v8",
]
