"""Integration tests for CLI subcommands: status, verify, lock, repair-existing, clean-temp."""

from __future__ import annotations

import json
from pathlib import Path
from ntruth.data.acquire import cmd_clean_temp, cmd_lock_resolve, cmd_lock_verify, cmd_repair_existing, cmd_status, cmd_verify


def test_cli_status(tmp_path: Path):
    cmd_status(tmp_path)


def test_cli_clean_temp(tmp_path: Path):
    part_file = tmp_path / "download.zip.part"
    part_file.write_text("partial content")
    cmd_clean_temp(tmp_path)
    assert not part_file.exists()


def test_cli_verify(tmp_path: Path):
    (tmp_path / "raw").mkdir()
    (tmp_path / "processed").mkdir()
    (tmp_path / "training_ready").mkdir()
    (tmp_path / "manifests").mkdir()
    (tmp_path / "manifests" / "splits.json").write_text("{}")
    (tmp_path / "manifests" / "datasets.json").write_text("{}")

    merkle_root = cmd_verify(tmp_path)
    assert len(merkle_root) == 64


def test_cli_lock_resolve_and_verify(tmp_path: Path):
    cand_path = tmp_path / "lock.candidate.json"
    cmd_lock_resolve(tmp_path, "sourcedata", cand_path)
    assert cand_path.exists()


def test_cli_repair_existing(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    downloads_dir = tmp_path / "downloads"
    raw_dir.mkdir()
    downloads_dir.mkdir()

    incomplete_extract = raw_dir / "dataset.extract.123"
    incomplete_extract.mkdir()

    plan_path = tmp_path / "repair_plan.json"
    cmd_repair_existing(tmp_path, write_plan=plan_path)
    assert plan_path.exists()

    cmd_repair_existing(tmp_path, apply_plan=plan_path)
    assert not incomplete_extract.exists()
    assert (tmp_path / "quarantine" / "dataset.extract.123").exists()
