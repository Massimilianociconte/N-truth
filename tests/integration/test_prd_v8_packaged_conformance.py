"""The PRD v8 normative bundle must load from an installed wheel, not only a checkout."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_built_wheel_installs_and_conforms_from_package_resources(tmp_path: Path) -> None:
    """Catches missing package data or a loader that falls back to checkout paths."""

    uv = shutil.which("uv")
    if uv is None:
        pytest.fail("uv is required for the distribution conformance gate")
    dist_dir = tmp_path / "dist"
    build = subprocess.run(
        [uv, "build", "--wheel", "--out-dir", str(dist_dir)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    wheels = list(dist_dir.glob("ntruth-*.whl"))
    assert len(wheels) == 1

    target = tmp_path / "installed"
    install = subprocess.run(
        [uv, "pip", "install", "--target", str(target), "--no-deps", str(wheels[0])],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert install.returncode == 0, install.stdout + install.stderr

    script = f"""
from pathlib import Path
import ntruth
from ntruth.conformance import evaluate_conformance
from ntruth.derivation_theory import load_installed_bundle

assert Path(ntruth.__file__).resolve().is_relative_to(Path({str(target)!r}).resolve())
bundle = load_installed_bundle()
report = evaluate_conformance(bundle)
assert report.passed, report.failures
assert len(bundle.theory.clauses) == 7
assert len(bundle.fixture_set.fixture_pins) == 21
print(bundle.rulebook.declared_checksum)
"""
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    run = subprocess.run(
        [sys.executable, "-c", f"import sys; sys.path.insert(0, {str(target)!r});\n{script}"],
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    assert len(run.stdout.strip()) == 64
