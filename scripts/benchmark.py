#!/usr/bin/env python3
"""Benchmark locale ripetibile del core rules-only.

Il risultato prova soltanto la macchina e il commit registrati nell'output. Non equivale al gate
M5 Pro finche non viene eseguito su un corpus MVP rappresentativo e revisionato.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import resource
import subprocess
import tempfile
import time
from pathlib import Path

from ntruth.ingest.project import Project
from ntruth.pipeline import analyze_project


def _git_state(root: Path) -> tuple[str | None, bool | None]:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, check=False
    )
    commit = result.stdout.strip() if result.returncode == 0 else None
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    dirty = bool(status.stdout.strip()) if status.returncode == 0 else None
    return commit, dirty


def _source_snapshot(root: Path) -> str:
    """Hash bounded inputs without including the benchmark output itself."""

    candidates = [root / "pyproject.toml", root / "uv.lock"]
    for directory in (root / "packages" / "ntruth", root / "rulesets", root / "ontology"):
        candidates.extend(path for path in directory.rglob("*") if path.is_file())
    selected = sorted(
        path
        for path in candidates
        if "__pycache__" not in path.parts and path.suffix not in {".pyc", ".pyo"}
    )
    digest = hashlib.sha256()
    for path in selected:
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "source",
        type=Path,
        nargs="?",
        default=Path("tests/scientific_fixtures/uc02_preparations"),
    )
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source = args.source.resolve()
    with tempfile.TemporaryDirectory(prefix="ntruth-benchmark-") as tmp:
        project = Project.create(Path(tmp) / "project", name=source.name)
        project.add(source)
        started = time.perf_counter()
        result = analyze_project(project)
        elapsed = time.perf_counter() - started
    # macOS restituisce byte, Linux KiB.
    raw_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss_bytes = raw_rss if platform.system() == "Darwin" else raw_rss * 1024
    target_result = {
        "time": elapsed < 60 * max(len(result.report.blocks), 1),
        "memory": rss_bytes < 20 * 1024**3,
    }
    commit, working_tree_dirty = _git_state(root)
    payload = {
        "benchmark_version": 1,
        "commit": commit,
        "working_tree_dirty": working_tree_dirty,
        "source_snapshot_sha256": _source_snapshot(root),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "source": str(args.source),
        "source_kind": "synthetic_fixture",
        "blocks": len(result.report.blocks),
        "elapsed_seconds": round(elapsed, 6),
        "peak_rss_bytes": rss_bytes,
        "targets": {"seconds_per_typical_block": 60, "peak_rss_bytes": 20 * 1024**3},
        "target_result": target_result,
        "scientific_release_evidence": False,
    }
    rendered = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.out:
        args.out.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if all(target_result.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
