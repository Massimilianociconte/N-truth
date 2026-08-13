"""Integration tests for CLI subcommands: status, verify, lock, repair-existing, clean-temp."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ntruth.data.acquire import (
    _load_verified_integrity_snapshot,
    cmd_all,
    cmd_clean_temp,
    cmd_lock_resolve,
    cmd_repair_existing,
    cmd_snapshot_integrity,
    cmd_status,
    cmd_verify,
)
from ntruth.data.fs import sha256_file


def _create_canonical_integrity_tree(root: Path) -> None:
    for directory in (
        root / "downloads",
        root / "raw",
        root / "processed",
        root / "manifests" / "licenses",
        root / "manifests" / "reports" / "quality",
        root / "manifests" / "sources",
    ):
        directory.mkdir(parents=True, exist_ok=True)
    (root / "raw" / "sample.txt").write_text("raw", encoding="utf-8")
    (root / "processed" / "sample.jsonl").write_text("{}\n", encoding="utf-8")
    (root / "downloads" / "source.zip").write_bytes(b"archive")
    (root / "manifests" / "licenses" / "source.txt").write_text("licence", encoding="utf-8")
    (root / "manifests" / "sources" / "source.json").write_text("{}\n", encoding="utf-8")
    for name in ("datasets.json", "files.jsonl", "splits.json"):
        (root / "manifests" / name).write_text("{}\n", encoding="utf-8")


def test_cli_status(tmp_path: Path):
    cmd_status(tmp_path)


def test_cli_clean_temp(tmp_path: Path):
    part_file = tmp_path / "download.zip.part"
    part_file.write_text("partial content")
    cmd_clean_temp(tmp_path)
    assert not part_file.exists()


def test_cli_verify(tmp_path: Path):
    _create_canonical_integrity_tree(tmp_path)
    (tmp_path / "training_ready").mkdir()

    pinned_root = cmd_snapshot_integrity(tmp_path)
    merkle_root = cmd_verify(tmp_path)
    assert merkle_root == pinned_root
    assert len(merkle_root) == 64
    snapshot = json.loads(
        (tmp_path / "manifests" / "checksums" / "merkle_manifest.json").read_text(encoding="utf-8")
    )
    assert snapshot["required_roots"] == [
        "downloads",
        "manifests/datasets.json",
        "manifests/files.jsonl",
        "manifests/licenses",
        "manifests/reports/quality",
        "manifests/sources",
        "manifests/splits.json",
        "processed",
        "raw",
    ]
    assert snapshot["optional_roots"] == {
        "task_corpora": False,
        "training_ready": True,
    }


def test_cli_verify_does_not_rewrite_integrity_snapshot(tmp_path: Path):
    _create_canonical_integrity_tree(tmp_path)
    cmd_snapshot_integrity(tmp_path)
    snapshot = tmp_path / "manifests" / "checksums" / "merkle_manifest.json"
    before_sha = sha256_file(snapshot)
    before_mtime_ns = snapshot.stat().st_mtime_ns

    cmd_verify(tmp_path)

    assert sha256_file(snapshot) == before_sha
    assert snapshot.stat().st_mtime_ns == before_mtime_ns


def test_cli_verify_fails_when_canonical_file_is_tampered(tmp_path: Path):
    _create_canonical_integrity_tree(tmp_path)
    cmd_snapshot_integrity(tmp_path)
    (tmp_path / "raw" / "sample.txt").write_text("tampered", encoding="utf-8")

    with pytest.raises(ValueError, match="integrity snapshot mismatch"):
        cmd_verify(tmp_path)


def test_cli_verify_authenticates_quality_evidence(tmp_path: Path):
    _create_canonical_integrity_tree(tmp_path)
    quality = tmp_path / "manifests" / "reports" / "quality" / "sample.json"
    quality.write_text('{"status":"PASS"}\n', encoding="utf-8")
    cmd_snapshot_integrity(tmp_path)
    quality.write_text('{"status":"FAIL"}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="integrity snapshot mismatch"):
        cmd_verify(tmp_path)


def test_cli_verify_fails_when_required_root_is_missing(tmp_path: Path):
    _create_canonical_integrity_tree(tmp_path)
    cmd_snapshot_integrity(tmp_path)
    (tmp_path / "raw" / "sample.txt").unlink()
    (tmp_path / "raw").rmdir()

    with pytest.raises(FileNotFoundError, match="required canonical roots"):
        cmd_verify(tmp_path)


def test_cli_verify_fails_without_pinned_snapshot(tmp_path: Path):
    _create_canonical_integrity_tree(tmp_path)

    with pytest.raises(FileNotFoundError, match="integrity snapshot"):
        cmd_verify(tmp_path)


def test_cli_snapshot_refuses_semantically_stale_sourcedata_training_export(
    tmp_path: Path,
):
    _create_canonical_integrity_tree(tmp_path)
    (tmp_path / "training_ready" / "sourcedata_multitask").mkdir(parents=True)

    with pytest.raises(ValueError, match="semantically stale SourceData training export"):
        cmd_snapshot_integrity(tmp_path)


def test_cli_all_builds_task_corpus_after_sourcedata_and_snapshots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    events: list[str] = []

    def install(dataset: str):
        def run(root: Path, *, refresh: bool):
            del refresh
            events.append(dataset)
            (root / "downloads").mkdir(parents=True, exist_ok=True)
            (root / "raw" / dataset).mkdir(parents=True, exist_ok=True)
            (root / "processed" / dataset).mkdir(parents=True, exist_ok=True)
            return {
                "dataset": dataset,
                "raw_path": str(root / "raw" / dataset),
                "nested": {"evidence_path": str(root / "processed" / dataset / "evidence.json")},
                "split_counts": {},
                "files": [],
            }

        return run

    def build_task_corpus(root: Path, *, resume: bool):
        del resume
        events.append("task_corpus")
        (root / "task_corpora" / "entity_roles").mkdir(parents=True)

    monkeypatch.setattr("ntruth.data.acquire.install_sourcedata", install("sourcedata"))
    monkeypatch.setattr("ntruth.data.acquire.install_preclinie", install("preclinie"))
    monkeypatch.setattr("ntruth.data.acquire.install_measeval", install("measeval"))
    monkeypatch.setattr("ntruth.data.acquire.install_craft", install("craft"))
    monkeypatch.setattr("ntruth.data.acquire.build_sourcedata_entity_roles", build_task_corpus)

    cmd_all(tmp_path, resume=False)

    assert events == ["sourcedata", "preclinie", "measeval", "craft", "task_corpus"]
    assert (tmp_path / "manifests" / "licenses").is_dir()
    assert (tmp_path / "manifests" / "sources").is_dir()
    for dataset in ("sourcedata", "preclinie", "measeval", "craft"):
        quality_path = tmp_path / "manifests" / "reports" / "quality" / f"{dataset}.json"
        assert quality_path.is_file()
        assert json.loads(quality_path.read_text(encoding="utf-8"))["status"] == "FAIL"
    manifest = json.loads((tmp_path / "manifests" / "datasets.json").read_text(encoding="utf-8"))
    assert manifest["generated_at_utc"] is None
    assert manifest["generated_at_policy"] == (
        "omitted_from_canonical_manifest_for_reproducibility"
    )
    datasets = manifest["datasets"]
    assert datasets["sourcedata"]["quality"]["status"] == "FAIL"
    assert datasets["sourcedata"]["quality"]["blockers"] == [
        {"code": "NO_VALID_RECORDS", "count": 1}
    ]
    assert datasets["sourcedata"]["raw_path"] == "raw/sourcedata"
    assert datasets["sourcedata"]["nested"]["evidence_path"] == (
        "processed/sourcedata/evidence.json"
    )
    assert str(tmp_path) not in json.dumps(manifest)
    quality_report = json.loads(
        (tmp_path / "manifests" / "reports" / "quality" / "sourcedata.json").read_text(
            encoding="utf-8"
        )
    )
    assert str(tmp_path) not in json.dumps(quality_report)
    cmd_verify(tmp_path)


def test_cli_all_resume_refuses_stale_integrity_pin_before_installers_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _create_canonical_integrity_tree(tmp_path)
    cmd_snapshot_integrity(tmp_path)
    (tmp_path / "raw" / "sample.txt").write_text("stale", encoding="utf-8")
    installers_called = 0

    def install(dataset: str):
        def run(root: Path, *, refresh: bool):
            nonlocal installers_called
            del refresh
            installers_called += 1
            (root / "raw" / dataset).mkdir(parents=True, exist_ok=True)
            (root / "processed" / dataset).mkdir(parents=True, exist_ok=True)
            return {"dataset": dataset, "split_counts": {}, "files": []}

        return run

    def build_task_corpus(root: Path, *, resume: bool):
        del resume
        (root / "task_corpora").mkdir(exist_ok=True)

    monkeypatch.setattr("ntruth.data.acquire.install_sourcedata", install("sourcedata"))
    monkeypatch.setattr("ntruth.data.acquire.install_preclinie", install("preclinie"))
    monkeypatch.setattr("ntruth.data.acquire.install_measeval", install("measeval"))
    monkeypatch.setattr("ntruth.data.acquire.install_craft", install("craft"))
    monkeypatch.setattr("ntruth.data.acquire.build_sourcedata_entity_roles", build_task_corpus)

    with pytest.raises(ValueError, match="integrity snapshot mismatch"):
        cmd_all(tmp_path, resume=True)

    assert installers_called == 0


def test_cli_all_resume_requires_existing_integrity_pin_before_installers_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    installers_called = 0

    def install(root: Path, *, refresh: bool):
        nonlocal installers_called
        del root, refresh
        installers_called += 1
        return {"dataset": "unexpected", "split_counts": {}, "files": []}

    monkeypatch.setattr("ntruth.data.acquire.install_sourcedata", install)
    monkeypatch.setattr("ntruth.data.acquire.install_preclinie", install)
    monkeypatch.setattr("ntruth.data.acquire.install_measeval", install)
    monkeypatch.setattr("ntruth.data.acquire.install_craft", install)

    with pytest.raises(FileNotFoundError, match="pinned integrity snapshot"):
        cmd_all(tmp_path, resume=True)

    assert installers_called == 0
    assert not (tmp_path / "manifests" / "checksums" / "merkle_manifest.json").exists()


def test_cli_all_resume_refuses_malformed_integrity_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _create_canonical_integrity_tree(tmp_path)
    integrity = tmp_path / "manifests" / "checksums" / "merkle_manifest.json"
    integrity.parent.mkdir(parents=True)
    integrity.write_text("not-json\n", encoding="utf-8")

    def install(dataset: str):
        def run(root: Path, *, refresh: bool):
            del refresh
            (root / "raw" / dataset).mkdir(parents=True, exist_ok=True)
            (root / "processed" / dataset).mkdir(parents=True, exist_ok=True)
            return {"dataset": dataset, "split_counts": {}, "files": []}

        return run

    def build_task_corpus(root: Path, *, resume: bool):
        del resume
        (root / "task_corpora").mkdir(exist_ok=True)

    monkeypatch.setattr("ntruth.data.acquire.install_sourcedata", install("sourcedata"))
    monkeypatch.setattr("ntruth.data.acquire.install_preclinie", install("preclinie"))
    monkeypatch.setattr("ntruth.data.acquire.install_measeval", install("measeval"))
    monkeypatch.setattr("ntruth.data.acquire.install_craft", install("craft"))
    monkeypatch.setattr("ntruth.data.acquire.build_sourcedata_entity_roles", build_task_corpus)

    with pytest.raises(ValueError, match="pinned integrity snapshot"):
        cmd_all(tmp_path, resume=True)


def test_cli_all_resume_does_not_bless_post_build_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _create_canonical_integrity_tree(tmp_path)
    cmd_snapshot_integrity(tmp_path)
    integrity = tmp_path / "manifests" / "checksums" / "merkle_manifest.json"
    pinned_bytes = integrity.read_bytes()

    def install(dataset: str):
        def run(root: Path, *, refresh: bool):
            del refresh
            (root / "raw" / dataset).mkdir(parents=True, exist_ok=True)
            (root / "processed" / dataset).mkdir(parents=True, exist_ok=True)
            if dataset == "sourcedata":
                (root / "raw" / "sample.txt").write_text("post-build drift", encoding="utf-8")
            return {"dataset": dataset, "split_counts": {}, "files": []}

        return run

    def build_task_corpus(root: Path, *, resume: bool):
        del resume
        (root / "task_corpora").mkdir(exist_ok=True)

    monkeypatch.setattr("ntruth.data.acquire.install_sourcedata", install("sourcedata"))
    monkeypatch.setattr("ntruth.data.acquire.install_preclinie", install("preclinie"))
    monkeypatch.setattr("ntruth.data.acquire.install_measeval", install("measeval"))
    monkeypatch.setattr("ntruth.data.acquire.install_craft", install("craft"))
    monkeypatch.setattr("ntruth.data.acquire.build_sourcedata_entity_roles", build_task_corpus)

    with pytest.raises(ValueError, match="resume build changed canonical data"):
        cmd_all(tmp_path, resume=True)

    assert integrity.read_bytes() == pinned_bytes


def test_cli_all_resume_binds_the_pin_object_used_for_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _create_canonical_integrity_tree(tmp_path)
    cmd_snapshot_integrity(tmp_path)
    integrity = tmp_path / "manifests" / "checksums" / "merkle_manifest.json"
    original_pin = integrity.read_bytes()

    sample = tmp_path / "raw" / "sample.txt"
    sample.write_text("post-build drift", encoding="utf-8")
    cmd_snapshot_integrity(tmp_path)
    forged_post_build_pin = integrity.read_bytes()
    sample.write_text("raw", encoding="utf-8")
    integrity.write_bytes(original_pin)

    def replace_pin_after_bound_verify(root: Path) -> tuple[dict[str, object], str]:
        snapshot, merkle_root = _load_verified_integrity_snapshot(root)
        replacement = integrity.with_name("merkle_manifest.swap.json")
        replacement.write_bytes(forged_post_build_pin)
        replacement.replace(integrity)
        return snapshot, merkle_root

    def install(dataset: str):
        def run(root: Path, *, refresh: bool):
            del refresh
            if dataset == "sourcedata":
                sample.write_text("post-build drift", encoding="utf-8")
            return {
                "dataset": dataset,
                "raw_path": str(root / "raw"),
                "processed_path": str(root / "processed"),
                "split_counts": {},
                "files": [],
            }

        return run

    def build_task_corpus(root: Path, *, resume: bool):
        del root, resume

    monkeypatch.setattr(
        "ntruth.data.acquire._load_verified_integrity_snapshot",
        replace_pin_after_bound_verify,
    )
    monkeypatch.setattr("ntruth.data.acquire.install_sourcedata", install("sourcedata"))
    monkeypatch.setattr("ntruth.data.acquire.install_preclinie", install("preclinie"))
    monkeypatch.setattr("ntruth.data.acquire.install_measeval", install("measeval"))
    monkeypatch.setattr("ntruth.data.acquire.install_craft", install("craft"))
    monkeypatch.setattr("ntruth.data.acquire.build_sourcedata_entity_roles", build_task_corpus)

    with pytest.raises(ValueError, match="resume build changed canonical data"):
        cmd_all(tmp_path, resume=True)

    assert integrity.read_bytes() == forged_post_build_pin


def test_cli_lock_resolve_and_verify(tmp_path: Path):
    cand_path = tmp_path / "lock.candidate.json"
    cmd_lock_resolve(tmp_path, "sourcedata", cand_path)
    assert cand_path.exists()
    lock = json.loads(cand_path.read_text(encoding="utf-8"))["sourcedata"]
    assert all(len(item["sha256"]) == 64 for item in lock["files"])
    assert all(item["sha256"] != "SKIP_CHECK" for item in lock["files"])


def test_cli_lock_verify_rejects_non_sha_placeholder(tmp_path: Path):
    candidate = tmp_path / "invalid-lock.json"
    candidate.write_text(
        json.dumps(
            {
                "sourcedata": {
                    "revision": "b457c14041b61c56f671c6f966b4324f682855b7",
                    "files": [
                        {"path": f"file-{index}.jsonl", "sha256": "SKIP_CHECK"}
                        for index in range(6)
                    ],
                }
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="valid lowercase SHA-256"):
        from ntruth.data.acquire import cmd_lock_verify

        cmd_lock_verify(candidate)


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
    assert (tmp_path / "quarantine" / "raw" / "dataset.extract.123").exists()

    application = json.loads(
        (plan_path.with_name("repair_plan.application.json")).read_text(encoding="utf-8")
    )
    assert application["planned_action_count"] == 1
    assert application["applied_action_count"] == 1
    assert application["skipped_action_count"] == 0


def test_cli_repair_quarantines_semantically_stale_sourcedata_training_export(
    tmp_path: Path,
):
    (tmp_path / "raw").mkdir()
    (tmp_path / "downloads").mkdir()
    stale = tmp_path / "training_ready" / "sourcedata_multitask"
    stale.mkdir(parents=True)
    (stale / "train.jsonl").write_text('{"unsafe":true}\n', encoding="utf-8")
    plan = tmp_path / "repair-plan.json"

    cmd_repair_existing(tmp_path, write_plan=plan)

    entry = next(
        item
        for item in json.loads(plan.read_text(encoding="utf-8"))["plan"]
        if item["path"] == "training_ready/sourcedata_multitask"
    )
    assert entry["classification"] == "SEMANTICALLY_STALE"
    assert entry["action"] == "quarantine"
    assert len(entry["observed_tree_sha256"]) == 64

    cmd_repair_existing(tmp_path, apply_plan=plan)

    assert not stale.exists()
    assert (
        tmp_path / "quarantine" / "training_ready" / "sourcedata_multitask" / "train.jsonl"
    ).is_file()


def test_cli_repair_rejects_changed_stale_directory_since_plan(tmp_path: Path):
    (tmp_path / "raw").mkdir()
    (tmp_path / "downloads").mkdir()
    stale = tmp_path / "training_ready" / "sourcedata_multitask"
    stale.mkdir(parents=True)
    record = stale / "train.jsonl"
    record.write_text("first\n", encoding="utf-8")
    plan = tmp_path / "repair-plan.json"
    cmd_repair_existing(tmp_path, write_plan=plan)
    record.write_text("changed\n", encoding="utf-8")

    with pytest.raises(ValueError, match="changed since plan creation"):
        cmd_repair_existing(tmp_path, apply_plan=plan)


def test_cli_repair_rejects_plan_for_another_root(tmp_path: Path):
    plan = tmp_path / "foreign-plan.json"
    plan.write_text(
        json.dumps(
            {
                "root": str(tmp_path / "different-root"),
                "plan": [
                    {
                        "path": "raw/item.extract.1",
                        "classification": "INCOMPLETE",
                        "action": "quarantine",
                        "observed_type": "directory",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="root does not match"):
        cmd_repair_existing(tmp_path, apply_plan=plan)


def test_cli_repair_rejects_changed_file_since_plan(tmp_path: Path):
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    suspect = downloads / "suspect.part"
    suspect.write_text("first", encoding="utf-8")
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps(
            {
                "root": str(tmp_path.resolve()),
                "plan": [
                    {
                        "path": "downloads/suspect.part",
                        "classification": "INCOMPLETE",
                        "action": "quarantine",
                        "observed_type": "file",
                        "observed_sha256": sha256_file(suspect),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    suspect.write_text("changed", encoding="utf-8")

    with pytest.raises(ValueError, match="changed since plan creation"):
        cmd_repair_existing(tmp_path, apply_plan=plan)


def test_cli_repair_preflights_all_actions_before_first_move(tmp_path: Path):
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    (tmp_path / "raw").mkdir()
    first = downloads / "first.part"
    second = downloads / "second.part"
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")
    plan = tmp_path / "plan.json"
    cmd_repair_existing(tmp_path, write_plan=plan)
    second.write_text("changed", encoding="utf-8")

    with pytest.raises(ValueError, match="changed since plan creation"):
        cmd_repair_existing(tmp_path, apply_plan=plan)

    assert first.is_file()
    assert not (tmp_path / "quarantine" / "downloads" / "first.part").exists()


def test_cli_repair_missing_planned_target_fails_before_first_move(tmp_path: Path):
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    (tmp_path / "raw").mkdir()
    first = downloads / "first.part"
    missing = downloads / "missing.part"
    first.write_text("first", encoding="utf-8")
    missing.write_text("missing", encoding="utf-8")
    plan = tmp_path / "plan.json"
    cmd_repair_existing(tmp_path, write_plan=plan)
    missing.unlink()

    with pytest.raises(ValueError, match=r"changed since plan creation.*missing\.part"):
        cmd_repair_existing(tmp_path, apply_plan=plan)

    assert first.is_file()
    assert not (tmp_path / "quarantine" / "downloads" / "first.part").exists()
    assert not plan.with_name("plan.application.json").exists()


def test_cli_repair_rejects_symlink_target_without_moving_referent(tmp_path: Path):
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    (tmp_path / "raw").mkdir()
    referent = downloads / "referent.bin"
    referent.write_text("keep", encoding="utf-8")
    suspect = downloads / "suspect.part"
    suspect.symlink_to(referent.name)
    plan = tmp_path / "plan.json"
    cmd_repair_existing(tmp_path, write_plan=plan)

    with pytest.raises(ValueError, match=r"symlink component.*suspect\.part"):
        cmd_repair_existing(tmp_path, apply_plan=plan)

    assert suspect.is_symlink()
    assert referent.read_text(encoding="utf-8") == "keep"
    assert not (tmp_path / "quarantine" / "downloads" / "referent.bin").exists()


def test_cli_repair_rejects_symlink_parent_without_moving_referent(tmp_path: Path):
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    (tmp_path / "raw").mkdir()
    real_parent = downloads / "real"
    real_parent.mkdir()
    referent = real_parent / "x.part"
    referent.write_text("keep", encoding="utf-8")
    alias = downloads / "alias"
    alias.symlink_to(real_parent.name, target_is_directory=True)
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps(
            {
                "root": str(tmp_path.resolve()),
                "plan": [
                    {
                        "path": "downloads/alias/x.part",
                        "classification": "INCOMPLETE",
                        "action": "quarantine",
                        "observed_type": "file",
                        "observed_sha256": sha256_file(referent),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"symlink component.*downloads/alias"):
        cmd_repair_existing(tmp_path, apply_plan=plan)

    assert alias.is_symlink()
    assert referent.read_text(encoding="utf-8") == "keep"
    assert not (tmp_path / "quarantine" / "downloads" / "alias" / "x.part").exists()
    assert not plan.with_name("plan.application.json").exists()


def test_cli_repair_refuses_reapplying_a_recorded_plan(tmp_path: Path):
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    (tmp_path / "raw").mkdir()
    suspect = downloads / "suspect.part"
    suspect.write_text("partial", encoding="utf-8")
    plan = tmp_path / "plan.json"
    cmd_repair_existing(tmp_path, write_plan=plan)
    cmd_repair_existing(tmp_path, apply_plan=plan)

    with pytest.raises(ValueError, match="already has an application record"):
        cmd_repair_existing(tmp_path, apply_plan=plan)


def test_cli_repair_refuses_replay_from_identical_renamed_plan(tmp_path: Path):
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    (tmp_path / "raw").mkdir()
    suspect = downloads / "suspect.part"
    suspect.write_text("partial", encoding="utf-8")
    plan = tmp_path / "plan.json"
    cmd_repair_existing(tmp_path, write_plan=plan)
    plan_sha256 = sha256_file(plan)
    cmd_repair_existing(tmp_path, apply_plan=plan)

    renamed_plan = tmp_path / "copied-plan.json"
    renamed_plan.write_bytes(plan.read_bytes())
    with pytest.raises(ValueError, match="already has an application record"):
        cmd_repair_existing(tmp_path, apply_plan=renamed_plan)

    assert (tmp_path / "quarantine" / "repair-ledger" / f"{plan_sha256}.application.json").is_file()
    assert not renamed_plan.with_name("copied-plan.application.json").exists()


def test_cli_repair_rolls_back_and_records_move_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    (tmp_path / "raw").mkdir()
    first = downloads / "first.part"
    second = downloads / "second.part"
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")
    plan = tmp_path / "plan.json"
    cmd_repair_existing(tmp_path, write_plan=plan)

    real_move = __import__("os").replace

    def fail_second_move(source: Path, destination: Path):
        if Path(source).name == "second.part" and "quarantine" in Path(destination).parts:
            raise OSError("simulated move failure")
        return real_move(source, destination)

    monkeypatch.setattr("ntruth.data.acquire._atomic_repair_move", fail_second_move)

    with pytest.raises(OSError, match="simulated move failure"):
        cmd_repair_existing(tmp_path, apply_plan=plan)

    assert first.read_text(encoding="utf-8") == "first"
    assert second.read_text(encoding="utf-8") == "second"
    assert not (tmp_path / "quarantine" / "downloads" / "first.part").exists()
    application = json.loads(plan.with_name("plan.application.json").read_text(encoding="utf-8"))
    assert application["status"] == "ROLLED_BACK"
    assert application["applied_action_count"] == 0
