"""CLI smoke and NO_CORPUS repository policy."""

from __future__ import annotations

import json
from pathlib import Path

from ntruth.task_corpora.cli import main
from ntruth.task_corpora.io_util import (
    iter_jsonl_physical_lines,
    records_content_sha256,
    write_jsonl_records,
)


def test_cli_status_empty(tmp_path: Path, capsys):
    code = main(["status", "--root", str(tmp_path)])
    assert code == 0
    out = capsys.readouterr().out
    assert "entity_roles" in out


def test_cli_build_validate_stats(tmp_path: Path):
    root = tmp_path / "data"
    for split in ("train", "validation", "test"):
        d = root / "training_ready" / "sourcedata_multitask" / split
        d.mkdir(parents=True)
        rec = {
            "record_id": f"r-{split}",
            "source": {
                "dataset": "SourceData",
                "version": "2.0.3",
                "commit": "c",
                "document_id": f"d-{split}",
                "segment_id": "s",
            },
            "split": {"name": split, "authority": "upstream_official", "group_id": f"d-{split}"},
            "payload": {
                "tokens": ["x", "y"],
                "entity_tags": ["O", "B-GENEPROD"],
                "role_tags": ["O", "B-MEASURED_VAR"],
            },
        }
        (d / "records.jsonl").write_text(json.dumps(rec) + "\n")

    assert (
        main(["build", "--root", str(root), "--task", "entity_roles", "--source", "sourcedata"])
        == 0
    )
    assert main(["validate", "--root", str(root), "--task", "entity_roles"]) == 0
    assert main(["stats", "--root", str(root), "--task", "entity_roles"]) == 0


def test_jsonl_physical_lines_preserve_unicode_line_separator(tmp_path: Path):
    """U+2028 in token text must not split a JSONL record (splitlines trap)."""
    ls = "\u2028"
    rec = json.dumps(
        {"record_id": "r1", "tokens": ["Student", "'", "s", ls, "t", "-", "test"]},
        ensure_ascii=False,
    )
    path = tmp_path / "with_ls.jsonl"
    write_jsonl_records(path, [rec])
    # splitlines would inflate count; physical LF split must stay at 1
    assert path.read_text(encoding="utf-8").count("\n") == 1
    assert len(list(iter_jsonl_physical_lines(path))) == 1
    assert len([ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]) > 1
    loaded = json.loads(next(iter_jsonl_physical_lines(path)))
    assert loaded["tokens"][3] == ls
    # hash of in-memory line equals hash of re-read physical lines
    assert records_content_sha256([rec]) == records_content_sha256(iter_jsonl_physical_lines(path))


def test_cli_validate_with_unicode_line_separator_in_tokens(tmp_path: Path):
    """Full build/validate path survives U+2028 inside SourceData tokens."""
    root = tmp_path / "data"
    ls = "\u2028"
    for split in ("train", "validation", "test"):
        d = root / "training_ready" / "sourcedata_multitask" / split
        d.mkdir(parents=True)
        rec = {
            "record_id": f"r-{split}",
            "source": {
                "dataset": "SourceData",
                "version": "2.0.3",
                "commit": "c",
                "document_id": f"d-{split}",
                "segment_id": "s",
            },
            "split": {"name": split, "authority": "upstream_official", "group_id": f"d-{split}"},
            "payload": {
                "tokens": ["Student", "'", "s", ls, "t"],
                "entity_tags": ["O", "O", "O", "O", "O"],
                "role_tags": ["O", "O", "O", "O", "O"],
            },
        }
        (d / "records.jsonl").write_text(json.dumps(rec, ensure_ascii=False) + "\n")

    assert (
        main(["build", "--root", str(root), "--task", "entity_roles", "--source", "sourcedata"])
        == 0
    )
    assert main(["validate", "--root", str(root), "--task", "entity_roles"]) == 0


def test_no_task_corpora_data_dir_in_git_tree():
    """Repository tree must not track generated task_corpora data dumps."""
    repo_root = Path(__file__).resolve().parents[3]
    tracked_data = repo_root / "task_corpora"
    assert not tracked_data.exists()
    # package code may exist; ensure no large jsonl corpora under packages
    pkg = repo_root / "packages" / "ntruth" / "task_corpora"
    jsonl = list(pkg.rglob("*.jsonl"))
    assert jsonl == []
