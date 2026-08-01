#!/usr/bin/env python3
"""Smoke-test wheel and sdist from isolated virtual environments.

The regular test suite imports the checkout.  This release gate instead installs
each built distribution into a fresh environment, constrained by ``uv.lock``,
then exercises the installed CLI and the local API health contract.  Network access
is allowed by default because an installed environment is not a complete wheelhouse;
``--offline`` is available when every locked dependency is already cached.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VERSION_PATTERN = re.compile(r"^N-Truth \S+ · schema \S+$")
RULESET_PATTERN = re.compile(r"^ntruth-core@\S+ — (\d+) regole \(checksum [0-9a-f]+\)$")

HEALTH_SMOKE = """
from ntruth import SCHEMA_VERSION, __version__
from ntruth.api.app import app

paths = {route.path for route in app.routes}
assert {"/health", "/v1/health"} <= paths, paths
route = next(route for route in app.routes if route.path == "/v1/health")
payload = route.endpoint()
assert payload["status"] == "ok", payload
assert payload["service"] == "ntruth", payload
assert payload["version"] == __version__, payload
assert payload["schema_version"] == SCHEMA_VERSION, payload
assert payload["offline_core"] is True, payload
print(f"health ok · ntruth {__version__} · schema {SCHEMA_VERSION}")
""".strip()


@dataclass(frozen=True)
class Distribution:
    kind: str
    path: Path


def discover_distributions(dist_dir: Path) -> tuple[Distribution, Distribution]:
    """Return exactly one wheel and one source distribution from ``dist_dir``."""

    if not dist_dir.is_dir():
        raise ValueError(f"Directory delle distribuzioni non trovata: {dist_dir}")
    wheels = sorted(dist_dir.glob("ntruth-*.whl"))
    sdists = sorted(dist_dir.glob("ntruth-*.tar.gz"))
    if len(wheels) != 1:
        raise ValueError(f"Atteso un solo wheel ntruth, trovati {len(wheels)} in {dist_dir}")
    if len(sdists) != 1:
        raise ValueError(f"Attesa una sola sdist ntruth, trovate {len(sdists)} in {dist_dir}")
    return Distribution("wheel", wheels[0]), Distribution("sdist", sdists[0])


def clean_environment(*, offline: bool) -> dict[str, str]:
    """Create a subprocess environment that cannot import from the checkout."""

    env = os.environ.copy()
    for name in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT"):
        env.pop(name, None)
    if offline:
        env["UV_OFFLINE"] = "1"
    else:
        env.pop("UV_OFFLINE", None)
    env["UV_PYTHON_DOWNLOADS"] = "never"
    return env


def run_checked(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    label: str,
) -> str:
    """Run one release assertion and retain output for useful CI failures."""

    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        details = "\n".join(part for part in (completed.stdout, completed.stderr) if part.strip())
        raise RuntimeError(f"{label} fallito (exit {completed.returncode})\n{details}")
    return completed.stdout.strip()


def environment_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def environment_command(venv_dir: Path, name: str) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / f"{name}.exe"
    return venv_dir / "bin" / name


def assert_cli_contract(version_output: str, rules_output: str) -> None:
    """Check that the installed entry point and bundled rules are usable."""

    version_line = version_output.strip()
    if VERSION_PATTERN.fullmatch(version_line) is None:
        raise RuntimeError(f"Output inatteso da `ntruth version`: {version_line!r}")

    lines = [line for line in rules_output.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("`ntruth rules list` non ha prodotto output")
    match = RULESET_PATTERN.fullmatch(lines[0])
    if match is None:
        raise RuntimeError(f"Header inatteso da `ntruth rules list`: {lines[0]!r}")
    declared_count = int(match.group(1))
    listed_count = len(lines) - 1
    if declared_count != listed_count:
        raise RuntimeError(
            f"Ruleset installato incompleto: header={declared_count}, righe_elencate={listed_count}"
        )


def export_constraints(uv: str, destination: Path, env: dict[str, str]) -> None:
    command = [
        uv,
        "export",
        "--locked",
        "--no-dev",
        "--extra",
        "api",
        "--no-emit-project",
        "--no-hashes",
        "--output-file",
        str(destination),
    ]
    run_checked(command, cwd=PROJECT_ROOT, env=env, label="Export vincoli da uv.lock")


def smoke_distribution(
    distribution: Distribution,
    *,
    uv: str,
    constraints: Path,
    work_dir: Path,
    env: dict[str, str],
    offline: bool,
) -> None:
    """Install and exercise one built distribution without network access."""

    venv_dir = work_dir / f"{distribution.kind}-env"
    run_dir = work_dir / f"{distribution.kind}-run"
    run_dir.mkdir()

    run_checked(
        [uv, "venv", "--python", sys.executable, "--no-python-downloads", str(venv_dir)],
        cwd=work_dir,
        env=env,
        label=f"Creazione ambiente {distribution.kind}",
    )
    python = environment_python(venv_dir)
    artifact_with_api_extra = f"{distribution.path.resolve()}[api]"
    install_command = [
        uv,
        "pip",
        "install",
        "--python",
        str(python),
        "--strict",
        "--constraint",
        str(constraints),
    ]
    if offline:
        install_command.append("--offline")
    install_command.append(artifact_with_api_extra)
    run_checked(
        install_command,
        cwd=run_dir,
        env=env,
        label=f"Installazione offline {distribution.kind}",
    )

    ntruth = environment_command(venv_dir, "ntruth")
    version_output = run_checked(
        [str(ntruth), "version"],
        cwd=run_dir,
        env=env,
        label=f"CLI version ({distribution.kind})",
    )
    rules_output = run_checked(
        [str(ntruth), "rules", "list"],
        cwd=run_dir,
        env=env,
        label=f"CLI rules list ({distribution.kind})",
    )
    assert_cli_contract(version_output, rules_output)
    health_output = run_checked(
        [str(python), "-c", HEALTH_SMOKE],
        cwd=run_dir,
        env=env,
        label=f"Import API e health contract ({distribution.kind})",
    )
    print(f"{distribution.kind}: {version_output} · {health_output}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Installa wheel e sdist in ambienti puliti e ne verifica CLI e API."
    )
    parser.add_argument(
        "--dist-dir",
        type=Path,
        default=PROJECT_ROOT / "dist",
        help="Directory contenente un wheel e una sdist N-Truth (default: ./dist).",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Vieta la rete; richiede che ogni dipendenza bloccata sia gia nella cache uv.",
    )
    args = parser.parse_args()

    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit("uv non trovato nel PATH")
    try:
        distributions = discover_distributions(args.dist_dir.resolve())
        env = clean_environment(offline=args.offline)
        with tempfile.TemporaryDirectory(prefix="ntruth-release-smoke-") as temporary:
            work_dir = Path(temporary)
            constraints = work_dir / "constraints.txt"
            export_constraints(uv, constraints, env)
            for distribution in distributions:
                smoke_distribution(
                    distribution,
                    uv=uv,
                    constraints=constraints,
                    work_dir=work_dir,
                    env=env,
                    offline=args.offline,
                )
    except (OSError, RuntimeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    mode = "offline" if args.offline else "con dipendenze vincolate da uv.lock"
    print(f"Release smoke test completato: wheel e sdist verificati {mode}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
