"""Atomic mount-identity and Feather v1 regressions for the PRD v8 policy gate."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ntruth.governance import repository_policy
from ntruth.governance.repository_policy import (
    RepositoryPolicyFindingKindV8,
    scan_tracked_repository_v8,
)

_MountIdentity = tuple[str, ...]


def _write(root: Path, relative: str, payload: bytes) -> str:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return relative


def _kinds_for(report: object, relative: str) -> set[RepositoryPolicyFindingKindV8]:
    findings = report.findings.value or ()  # type: ignore[attr-defined]
    return {finding.kind for finding in findings if finding.path == relative}


@pytest.mark.parametrize(
    "payload",
    (
        b"FEA0syntheticFEA1",
        b"FEA1syntheticFEA0",
        b"XFEA1syntheticFEA1",
    ),
)
def test_feather_v1_near_prefixes_are_not_misclassified(payload: bytes, tmp_path: Path) -> None:
    """A one-byte near-prefix or footer must not satisfy the exact Feather v1 signature."""

    relative = _write(tmp_path, "assets/ordinary.safe", payload)

    report = scan_tracked_repository_v8(tmp_path, (relative,))

    assert report.clean is True


def test_unavailable_descriptor_mount_identity_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A runtime without descriptor-bound mount identity must not inspect tracked bytes."""

    relative = _write(tmp_path, "assets/ordinary.safe", b"synthetic internal bytes\n")
    tracked_inode = (tmp_path / relative).stat().st_ino
    tracked_reads = 0
    real_read = os.read

    def observing_read(fd: int, size: int) -> bytes:
        nonlocal tracked_reads
        if os.fstat(fd).st_ino == tracked_inode:
            tracked_reads += 1
        return real_read(fd, size)

    monkeypatch.setattr(os, "read", observing_read)
    monkeypatch.setattr(
        repository_policy,
        "_descriptor_mount_identity",
        lambda _fd: None,
        raising=False,
    )

    report = scan_tracked_repository_v8(tmp_path, (relative,))

    assert RepositoryPolicyFindingKindV8.UNSAFE_PATH in _kinds_for(report, relative)
    assert report.scanned_file_count == 0
    assert tracked_reads == 0


def test_darwin_descriptor_binding_error_becomes_typed_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A failed platform binding must yield UNSAFE_PATH instead of escaping the scanner."""

    relative = _write(tmp_path, "assets/ordinary.safe", b"synthetic internal bytes\n")

    class FailingLibc:
        @staticmethod
        def fstatfs(_fd: int, _buffer: object) -> int:
            raise repository_policy.ctypes.ArgumentError("synthetic fstatfs binding failure")

    monkeypatch.setattr(repository_policy.sys, "platform", "darwin")
    monkeypatch.setattr(repository_policy.ctypes, "CDLL", lambda *_args, **_kwargs: FailingLibc())

    report = scan_tracked_repository_v8(tmp_path, (relative,))

    assert RepositoryPolicyFindingKindV8.UNSAFE_PATH in _kinds_for(report, relative)
    assert report.scanned_file_count == 0


def test_same_device_mount_race_is_rejected_by_open_descriptor_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An inventory-clean path whose opened leaf belongs to another mount must fail before read."""

    relative = _write(tmp_path, "assets/ordinary.safe", b"synthetic mounted bytes\n")
    tracked_inode = (tmp_path / relative).stat().st_ino
    tracked_reads = 0
    real_read = os.read

    def observing_read(fd: int, size: int) -> bytes:
        nonlocal tracked_reads
        if os.fstat(fd).st_ino == tracked_inode:
            tracked_reads += 1
        return real_read(fd, size)

    def injected_identity(fd: int) -> _MountIdentity:
        if os.fstat(fd).st_ino == tracked_inode:
            return ("synthetic-foreign-mount",)
        return ("synthetic-root-mount",)

    monkeypatch.setattr(os, "read", observing_read)
    monkeypatch.setattr(
        repository_policy,
        "_descriptor_mount_identity",
        injected_identity,
        raising=False,
    )
    monkeypatch.setattr(
        repository_policy,
        "_mount_points_for_repository",
        lambda _root: frozenset(),
    )

    report = scan_tracked_repository_v8(tmp_path, (relative,))

    assert RepositoryPolicyFindingKindV8.UNSAFE_PATH in _kinds_for(report, relative)
    assert report.scanned_file_count == 0
    assert tracked_reads == 0
    assert report.external_datasets_inspected is False
