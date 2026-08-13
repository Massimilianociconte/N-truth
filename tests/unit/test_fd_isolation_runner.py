"""Adversarial tests for the anonymous/unlinked inherited read-only FD runner."""

from __future__ import annotations

import fcntl
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from ntruth.training.fd_isolation import (
    FdIsolationError,
    IsolatedFd,
    bind_run_state,
    close_isolated,
    consume_isolated_bytes,
    consume_via_inherited_child,
    fd_access_mode,
    fd_isolation_contract_holds,
    inherit_fd,
    isolate_verified_file,
    materialize_unlinked_readonly_fd,
    read_regular_file_bytes,
)


def test_validate_then_consume_survives_same_user_swap(tmp_path: Path) -> None:
    path = tmp_path / "train.jsonl"
    original = b'{"record_id":"keep"}\n'
    path.write_bytes(original)

    isolated = isolate_verified_file(path, label="train.jsonl")
    try:
        path.write_bytes(b'{"record_id":"swapped-by-same-user"}\n')
        consumed = consume_isolated_bytes(isolated)
        child = consume_via_inherited_child(isolated)
    finally:
        close_isolated(isolated)

    assert consumed == original
    assert child == original
    assert path.read_bytes() != original
    assert isolated.nlink == 0


def test_symlink_after_validation_cannot_change_consumed_bytes(tmp_path: Path) -> None:
    target = tmp_path / "real.jsonl"
    decoy = tmp_path / "decoy.jsonl"
    path = tmp_path / "valid.jsonl"
    original = b"validated-bytes\n"
    target.write_bytes(original)
    decoy.write_bytes(b"decoy-bytes\n")
    os.link(target, path)

    isolated = isolate_verified_file(path, label="valid.jsonl")
    try:
        path.unlink()
        path.symlink_to(decoy)
        consumed = consume_isolated_bytes(isolated)
    finally:
        close_isolated(isolated)

    assert consumed == original
    assert path.is_symlink()
    assert path.read_bytes() == b"decoy-bytes\n"


def test_pathname_reopen_after_validation_sees_swap_fd_does_not(tmp_path: Path) -> None:
    path = tmp_path / "payload.bin"
    original = b"alpha-bytes"
    path.write_bytes(original)
    isolated = isolate_verified_file(path, label="payload")
    try:
        path.write_bytes(b"beta-bytes")
        reopened = read_regular_file_bytes(path, label="reopen")
        consumed = consume_isolated_bytes(isolated)
    finally:
        close_isolated(isolated)

    assert reopened == b"beta-bytes"
    assert consumed == original


def test_named_still_linked_file_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "named.bin"
    path.write_bytes(b"still-named")
    fd = os.open(path, os.O_RDONLY)
    try:
        with pytest.raises(FdIsolationError, match="named file"):
            IsolatedFd(
                fd=fd,
                sha256="0" * 64,
                size_bytes=11,
                label="named",
                nlink=os.fstat(fd).st_nlink,
            )
    finally:
        os.close(fd)


def test_directory_fd_is_rejected(tmp_path: Path) -> None:
    directory = tmp_path / "dir"
    directory.mkdir()
    with pytest.raises(FdIsolationError, match="directory"):
        isolate_verified_file(directory, label="dir")


def test_expected_hash_detects_swap_between_validate_and_isolate(tmp_path: Path) -> None:
    path = tmp_path / "train.jsonl"
    original = b"first\n"
    path.write_bytes(original)
    expected = __import__("hashlib").sha256(original).hexdigest()
    path.write_bytes(b"second\n")
    with pytest.raises(FdIsolationError, match="bytes cambiati dopo la validazione"):
        isolate_verified_file(path, label="train.jsonl", expected_sha256=expected)


def test_run_state_binds_required_hashes() -> None:
    digest = "ab" * 32
    state = bind_run_state(
        dataset_sha256=digest,
        authorization_sha256="cd" * 32,
        model_sha256="ef" * 32,
        tokenizer_sha256="11" * 32,
        checkpoint_sha256="22" * 32,
        consumed_labels=("train.jsonl",),
    )
    assert state.dataset_sha256 == digest
    assert state.authorization_sha256
    assert state.model_sha256
    assert state.tokenizer_sha256
    assert state.checkpoint_sha256
    with pytest.raises(FdIsolationError, match="hash mancante"):
        bind_run_state(
            dataset_sha256="nope",
            authorization_sha256="cd" * 32,
            model_sha256="ef" * 32,
            tokenizer_sha256="11" * 32,
            checkpoint_sha256="22" * 32,
            consumed_labels=(),
        )


def test_isolated_and_inherited_fd_reject_writes() -> None:
    original = b"immutable-payload\n"
    isolated = materialize_unlinked_readonly_fd(original, label="ro-payload")
    try:
        flags = fcntl.fcntl(isolated.fd, fcntl.F_GETFL)
        assert flags & os.O_ACCMODE == os.O_RDONLY
        assert fd_access_mode(isolated.fd) == os.O_RDONLY
        with pytest.raises(OSError):
            os.write(isolated.fd, b"MUTATED!")
        assert consume_isolated_bytes(isolated) == original

        inherit_fd(isolated)
        child = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import os,sys\n"
                    "fd=int(sys.argv[1])\n"
                    "failed=False\n"
                    "try:\n"
                    "    os.write(fd, b'MUTATED!')\n"
                    "except OSError:\n"
                    "    failed=True\n"
                    "os.lseek(fd,0,os.SEEK_SET)\n"
                    "sys.stdout.buffer.write(bytes([int(failed)])+os.read(fd,1<<20))\n"
                ),
                str(isolated.fd),
            ],
            check=False,
            capture_output=True,
            close_fds=True,
            pass_fds=(isolated.fd,),
        )
        assert child.returncode == 0, child.stderr
        assert child.stdout[:1] == b"\x01"
        assert child.stdout[1:] == original
        assert consume_isolated_bytes(isolated) == original
    finally:
        close_isolated(isolated)


def test_rdwr_unlinked_fd_is_rejected() -> None:
    write_fd, path = tempfile.mkstemp(prefix="ntruth-rdwr-")
    try:
        os.write(write_fd, b"x")
        os.unlink(path)
        assert os.fstat(write_fd).st_nlink == 0
        assert fd_access_mode(write_fd) != os.O_RDONLY
        with pytest.raises(FdIsolationError, match="O_RDONLY"):
            IsolatedFd(
                fd=write_fd,
                sha256="0" * 64,
                size_bytes=1,
                label="rdwr",
                nlink=0,
            )
    finally:
        os.close(write_fd)


def test_shipped_contract_probe_holds() -> None:
    assert fd_isolation_contract_holds() is True
    isolated = materialize_unlinked_readonly_fd(b"probe", label="manual")
    try:
        assert stat.S_ISREG(os.fstat(isolated.fd).st_mode)
        assert isolated.nlink == 0
        assert fd_access_mode(isolated.fd) == os.O_RDONLY
        with pytest.raises(OSError):
            os.write(isolated.fd, b"MUTATED!")
        assert consume_isolated_bytes(isolated) == b"probe"
    finally:
        close_isolated(isolated)
