"""Anonymous / unlinked inherited read-only file-descriptor isolation.

MLX-facing consumption may use only already-verified inherited descriptors.
A named temporary path, a still-named copy, or a directory FD is rejected.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import stat
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ntruth.training.blockers import FD_ISOLATION_BLOCKER_CODE, FD_ISOLATION_BLOCKER_DETAIL

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX
    fcntl = None  # type: ignore[assignment]

O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_SHA256 = hashlib.sha256


class FdIsolationError(RuntimeError):
    """Isolation contract violation."""


@dataclass
class IsolatedFd:
    fd: int
    sha256: str
    size_bytes: int
    label: str
    nlink: int

    def __post_init__(self) -> None:
        if self.nlink != 0:
            raise FdIsolationError(f"{self.label}: named file is not an anonymous/unlinked FD")
        if self.fd < 0:
            raise FdIsolationError(f"{self.label}: invalid file descriptor")


@dataclass(frozen=True)
class IsolatedRunState:
    schema_version: str
    dataset_sha256: str
    authorization_sha256: str
    model_sha256: str
    tokenizer_sha256: str
    checkpoint_sha256: str
    consumed_labels: tuple[str, ...]
    checksum: str


_REQUIRED_RUN_HASHES: tuple[str, ...] = (
    "dataset_sha256",
    "authorization_sha256",
    "model_sha256",
    "tokenizer_sha256",
    "checkpoint_sha256",
)
_CONTRACT_HOLDS: bool | None = None


def _sha256_bytes(payload: bytes) -> str:
    return _SHA256(payload).hexdigest()


def read_regular_file_bytes(path: Path, *, label: str) -> bytes:
    flags = os.O_RDONLY | O_CLOEXEC | O_NOFOLLOW
    descriptor: int | None = None
    try:
        descriptor = os.open(path, flags)
        metadata = os.fstat(descriptor)
        if stat.S_ISDIR(metadata.st_mode):
            raise FdIsolationError(f"{label} e una directory, non un file regolare: {path}")
        if not stat.S_ISREG(metadata.st_mode):
            raise FdIsolationError(f"{label} non e un file regolare: {path}")
        chunks: list[bytes] = []
        while chunk := os.read(descriptor, 1024 * 1024):
            chunks.append(chunk)
        return b"".join(chunks)
    except OSError as exc:
        raise FdIsolationError(
            f"{label} non leggibile o symlink non ammesso: {path}: {exc}"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _materialize_memfd(payload: bytes, *, label: str) -> IsolatedFd:
    flags = getattr(os, "MFD_CLOEXEC", 0)
    fd = os.memfd_create(f"ntruth-{label}", flags)  # type: ignore[attr-defined]
    try:
        os.write(fd, payload)
        os.fsync(fd)
        os.fchmod(fd, 0o400)
        os.lseek(fd, 0, os.SEEK_SET)
        metadata = os.fstat(fd)
        isolated = IsolatedFd(
            fd=fd,
            sha256=_sha256_bytes(payload),
            size_bytes=len(payload),
            label=label,
            nlink=int(metadata.st_nlink),
        )
    except Exception:
        os.close(fd)
        raise
    return isolated


def _materialize_unlinked_tmp(payload: bytes, *, label: str) -> IsolatedFd:
    fd, path = tempfile.mkstemp(prefix="ntruth-fd-", suffix=".bin")
    try:
        os.write(fd, payload)
        os.fsync(fd)
        os.unlink(path)
        if os.path.exists(path):
            raise FdIsolationError(f"{label}: unlinked path still exists")
        metadata = os.fstat(fd)
        if metadata.st_nlink != 0:
            raise FdIsolationError(f"{label}: file still has a directory link")
        os.fchmod(fd, 0o400)
        os.lseek(fd, 0, os.SEEK_SET)
        return IsolatedFd(
            fd=fd,
            sha256=_sha256_bytes(payload),
            size_bytes=len(payload),
            label=label,
            nlink=int(os.fstat(fd).st_nlink),
        )
    except Exception:
        with contextlib.suppress(OSError):
            os.close(fd)
        if os.path.exists(path):
            with contextlib.suppress(OSError):
                os.unlink(path)
        raise


def materialize_unlinked_readonly_fd(payload: bytes, *, label: str) -> IsolatedFd:
    """Copy verified bytes into an anonymous/unlinked read-only descriptor."""

    if hasattr(os, "memfd_create"):
        try:
            return _materialize_memfd(payload, label=label)
        except OSError:
            pass
    return _materialize_unlinked_tmp(payload, label=label)


def isolate_verified_file(
    path: Path,
    *,
    label: str,
    expected_sha256: str | None = None,
) -> IsolatedFd:
    payload = read_regular_file_bytes(path, label=label)
    digest = _sha256_bytes(payload)
    if expected_sha256 is not None and digest != expected_sha256:
        raise FdIsolationError(
            f"{label}: bytes cambiati dopo la validazione (path reopen rifiutato)"
        )
    return materialize_unlinked_readonly_fd(payload, label=label)


def consume_isolated_bytes(isolated: IsolatedFd) -> bytes:
    """Read only from the inherited/unlinked descriptor. Never reopen a path."""

    if isolated.nlink != 0:
        raise FdIsolationError(f"{isolated.label}: consume rejected for named FD")
    metadata = os.fstat(isolated.fd)
    if stat.S_ISDIR(metadata.st_mode):
        raise FdIsolationError(f"{isolated.label}: directory FD rejected")
    if metadata.st_nlink != 0:
        raise FdIsolationError(f"{isolated.label}: FD regained a pathname")
    os.lseek(isolated.fd, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    remaining = isolated.size_bytes
    while remaining > 0:
        chunk = os.read(isolated.fd, min(1024 * 1024, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    payload = b"".join(chunks)
    if _sha256_bytes(payload) != isolated.sha256:
        raise FdIsolationError(f"{isolated.label}: consumed bytes != validated hash")
    return payload


def inherit_fd(isolated: IsolatedFd) -> IsolatedFd:
    if fcntl is None:
        raise FdIsolationError("fcntl unavailable: cannot clear FD_CLOEXEC")
    flags = fcntl.fcntl(isolated.fd, fcntl.F_GETFD)
    fcntl.fcntl(isolated.fd, fcntl.F_SETFD, flags & ~fcntl.FD_CLOEXEC)
    return isolated


def consume_via_inherited_child(isolated: IsolatedFd) -> bytes:
    """Prove a child process can read only the inherited FD, not a pathname."""

    inherit_fd(isolated)
    script = (
        "import os,sys;"
        "fd=int(sys.argv[1]);"
        "os.lseek(fd,0,os.SEEK_SET);"
        "sys.stdout.buffer.write(os.read(fd,1<<30))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script, str(isolated.fd)],
        check=False,
        capture_output=True,
        close_fds=True,
        pass_fds=(isolated.fd,),
    )
    if completed.returncode != 0:
        raise FdIsolationError(
            f"{isolated.label}: inherited child failed: {completed.stderr!r}"
        )
    payload = completed.stdout
    if _sha256_bytes(payload) != isolated.sha256:
        raise FdIsolationError(f"{isolated.label}: inherited child consumed unexpected bytes")
    return payload


def close_isolated(isolated: IsolatedFd) -> None:
    with contextlib.suppress(OSError):
        os.close(isolated.fd)


def bind_run_state(
    *,
    dataset_sha256: str,
    authorization_sha256: str,
    model_sha256: str,
    tokenizer_sha256: str,
    checkpoint_sha256: str,
    consumed_labels: tuple[str, ...],
) -> IsolatedRunState:
    payload = {
        "schema_version": "1.0.0",
        "dataset_sha256": dataset_sha256,
        "authorization_sha256": authorization_sha256,
        "model_sha256": model_sha256,
        "tokenizer_sha256": tokenizer_sha256,
        "checkpoint_sha256": checkpoint_sha256,
        "consumed_labels": list(consumed_labels),
    }
    for key in _REQUIRED_RUN_HASHES:
        value = payload[key]
        if not isinstance(value, str) or len(value) != 64 or any(
            char not in "0123456789abcdef" for char in value
        ):
            raise FdIsolationError(f"run-state hash mancante o non valido: {key}")
    canonical = "".join(str(payload[key]) for key in _REQUIRED_RUN_HASHES)
    digest = _sha256_bytes(canonical.encode("ascii"))
    return IsolatedRunState(
        schema_version="1.0.0",
        dataset_sha256=dataset_sha256,
        authorization_sha256=authorization_sha256,
        model_sha256=model_sha256,
        tokenizer_sha256=tokenizer_sha256,
        checkpoint_sha256=checkpoint_sha256,
        consumed_labels=consumed_labels,
        checksum=digest,
    )


def isolate_verified_mapping(
    files: Mapping[str, Path],
    *,
    expected_hashes: Mapping[str, str] | None = None,
) -> dict[str, IsolatedFd]:
    isolated: dict[str, IsolatedFd] = {}
    try:
        for label, path in files.items():
            expected = None if expected_hashes is None else expected_hashes.get(label)
            isolated[label] = isolate_verified_file(path, label=label, expected_sha256=expected)
    except Exception:
        for item in isolated.values():
            close_isolated(item)
        raise
    return isolated


def fd_isolation_contract_holds() -> bool:
    """Prove the shipped isolate → consume path, including a same-user swap."""

    global _CONTRACT_HOLDS
    if _CONTRACT_HOLDS is True:
        return True
    payload = b"ntruth-fd-contract-probe-v1\n"
    directory = tempfile.mkdtemp(prefix="ntruth-fd-probe-")
    path = Path(directory) / "payload.bin"
    isolated: IsolatedFd | None = None
    try:
        path.write_bytes(payload)
        isolated = isolate_verified_file(path, label="probe")
        path.write_bytes(b"swapped-after-validation")
        consumed = consume_isolated_bytes(isolated)
        if consumed != payload:
            return False
        reopened = path.read_bytes()
        if reopened == consumed:
            return False
        if isolated.nlink != 0:
            return False
        child = consume_via_inherited_child(isolated)
        holds = child == payload
        if holds:
            _CONTRACT_HOLDS = True
        return holds
    except (FdIsolationError, OSError):
        return False
    finally:
        if isolated is not None:
            close_isolated(isolated)
        try:
            path.unlink(missing_ok=True)
            os.rmdir(directory)
        except OSError:
            pass


def isolation_blocker_if_unproven() -> tuple[str, str] | None:
    if fd_isolation_contract_holds():
        return None
    return FD_ISOLATION_BLOCKER_CODE, FD_ISOLATION_BLOCKER_DETAIL


def run_state_as_dict(state: IsolatedRunState) -> dict[str, Any]:
    return {
        "schema_version": state.schema_version,
        "dataset_sha256": state.dataset_sha256,
        "authorization_sha256": state.authorization_sha256,
        "model_sha256": state.model_sha256,
        "tokenizer_sha256": state.tokenizer_sha256,
        "checkpoint_sha256": state.checkpoint_sha256,
        "consumed_labels": list(state.consumed_labels),
        "checksum": state.checksum,
    }
