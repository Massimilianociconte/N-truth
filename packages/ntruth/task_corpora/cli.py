"""CLI for task corpora build / validate / stats."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ntruth.data.fs import sha256_file
from ntruth.task_corpora.adapters.sourcedata_entity_roles import build_sourcedata_entity_roles
from ntruth.task_corpora.config import (
    DEFAULT_DATA_ROOT,
    IMPLEMENTED_TASKS,
    TASK_ENTITY_ROLES,
    task_output_dir,
)
from ntruth.task_corpora.io_util import (
    iter_jsonl_physical_lines,
    records_content_sha256,
)


def cmd_build(root: Path, task: str, source: str, resume: bool) -> int:
    if task != TASK_ENTITY_ROLES or source != "sourcedata":
        print(
            f"Only entity_roles/sourcedata implemented in C0-C1 (got task={task} source={source})",
            file=sys.stderr,
        )
        return 2
    manifest = build_sourcedata_entity_roles(root, resume=resume)
    print(json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True))
    return 0


def cmd_validate(root: Path, task: str) -> int:
    if task != TASK_ENTITY_ROLES:
        print(f"validate: unsupported task {task}", file=sys.stderr)
        return 2
    out = task_output_dir(root, task) / "sourcedata" / "v2.0.3"
    manifest_path = out / "manifest.json"
    if not manifest_path.exists():
        print(f"missing manifest: {manifest_path}", file=sys.stderr)
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors = 0
    for split in ("train", "validation", "test"):
        path = out / f"{split}.jsonl"
        if not path.exists():
            print(f"missing {path}", file=sys.stderr)
            errors += 1
            continue
        # LF-only: do not use str.splitlines() (breaks on U+2028 in scientific text).
        for i, line in enumerate(iter_jsonl_physical_lines(path), 1):
            rec = json.loads(line)
            tokens = rec["payload"]["tokens"]
            ent = rec["payload"]["entity_labels"]
            roles = rec["payload"]["role_labels"]
            if not (len(tokens) == len(ent) == len(roles)):
                print(f"{path}:{i} length mismatch", file=sys.stderr)
                errors += 1
            if rec.get("authority_level") != "AUXILIARY":
                print(f"{path}:{i} authority not AUXILIARY", file=sys.stderr)
                errors += 1
            if rec.get("training_eligible") and rec.get("split") in {"test", "trial"}:
                print(f"{path}:{i} test training_eligible", file=sys.stderr)
                errors += 1
            if rec.get("licence", {}).get("training_allowed") is False and rec.get(
                "training_eligible"
            ):
                print(f"{path}:{i} training_eligible despite licence", file=sys.stderr)
                errors += 1
    lines: list[str] = []
    for split in ("train", "validation", "test"):
        path = out / f"{split}.jsonl"
        if path.exists():
            lines.extend(iter_jsonl_physical_lines(path))
    recomputed = records_content_sha256(lines)
    expected = manifest.get("records_sha256")
    if expected and expected != recomputed:
        print(f"records_sha256 mismatch expected={expected} got={recomputed}", file=sys.stderr)
        errors += 1
    counts = {
        split: sum(1 for _ in iter_jsonl_physical_lines(out / f"{split}.jsonl"))
        if (out / f"{split}.jsonl").exists()
        else 0
        for split in ("train", "validation", "test")
    }
    expected_counts = manifest.get("record_counts") or {}
    for split, n in counts.items():
        exp_n = expected_counts.get(split)
        if exp_n is not None and exp_n != n:
            print(f"record_counts mismatch {split}: expected={exp_n} got={n}", file=sys.stderr)
            errors += 1
    if errors:
        print(f"validate FAILED errors={errors}")
        return 1
    print(
        json.dumps(
            {"status": "OK", "records_sha256": recomputed, "manifest": str(manifest_path)},
            indent=2,
        )
    )
    return 0


def cmd_stats(root: Path, task: str) -> int:
    if task != TASK_ENTITY_ROLES:
        print(f"stats: unsupported task {task}", file=sys.stderr)
        return 2
    stats_path = task_output_dir(root, task) / "sourcedata" / "v2.0.3" / "stats.json"
    if not stats_path.exists():
        print(f"missing {stats_path}", file=sys.stderr)
        return 1
    print(stats_path.read_text(encoding="utf-8"))
    return 0


def cmd_status(root: Path) -> int:
    print(f"root={root}")
    print(f"implemented_tasks={sorted(IMPLEMENTED_TASKS)}")
    for task in sorted(IMPLEMENTED_TASKS):
        out = task_output_dir(root, task) / "sourcedata" / "v2.0.3"
        man = out / "manifest.json"
        print(f"  {task}: manifest={'yes' if man.exists() else 'no'} dir={out}")
        if man.exists():
            print(f"    sha256={sha256_file(man)}")
    return 0


def _add_root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--root", type=Path, default=DEFAULT_DATA_ROOT)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="N-Truth task corpora CLI (Workstream C)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status")
    _add_root(p_status)

    p_build = sub.add_parser("build")
    _add_root(p_build)
    p_build.add_argument("--task", required=True)
    p_build.add_argument("--source", required=True)
    p_build.add_argument("--resume", action="store_true", default=True)

    p_val = sub.add_parser("validate")
    _add_root(p_val)
    p_val.add_argument("--task", required=True)

    p_stats = sub.add_parser("stats")
    _add_root(p_stats)
    p_stats.add_argument("--task", required=True)

    args = parser.parse_args(argv)
    if args.command == "status":
        return cmd_status(args.root)
    if args.command == "build":
        return cmd_build(args.root, args.task, args.source, args.resume)
    if args.command == "validate":
        return cmd_validate(args.root, args.task)
    if args.command == "stats":
        return cmd_stats(args.root, args.task)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
