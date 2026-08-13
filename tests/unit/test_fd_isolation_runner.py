"""Adversarial tests for the anonymous/unlinked inherited read-only FD runner."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from ntruth.training.fd_isolation import (
    FdIsolationError,
    bind_run_state,
    close_isolated,
    consume_isolated_bytes,
    consume_via_inherited_child,
    fd_isolation_contract_holds,
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
            from ntruth.training.fd_isolation import IsolatedFd

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


def test_shipped_contract_probe_holds() -> None:
    assert fd_isolation_contract_holds() is True
    isolated = materialize_unlinked_readonly_fd(b"probe", label="manual")
    try:
        assert stat.S_ISREG(os.fstat(isolated.fd).st_mode)
        assert isolated.nlink == 0
        assert consume_isolated_bytes(isolated) == b"probe"
    finally:
        close_isolated(isolated)
