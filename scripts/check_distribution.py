#!/usr/bin/env python3
"""Verifica che sdist e wheel contengano core, regole, ontologia e UI compilata."""

from __future__ import annotations

import argparse
import tarfile
import zipfile
from pathlib import Path

FORBIDDEN_DIRECTORIES = {
    ".git",
    ".hypothesis",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "local-data",
    "node_modules",
    "workspace",
}
FORBIDDEN_PREFIXES = (
    "data/external/",
    "data/processed/",
    "data/raw/",
    "models/checkpoints/",
    "models/runs/",
)
PRIVATE_KEY_SUFFIXES = (".key", ".p12", ".pem", ".pfx")
GENERATED_FILE_SUFFIXES = (".pyc", ".pyo")
GENERATED_FILE_NAMES = {".DS_Store", ".coverage", "coverage.xml", "junit.xml"}


def _require(names: set[str], *, exact: tuple[str, ...], prefixes: tuple[str, ...]) -> None:
    missing = [name for name in exact if name not in names]
    missing.extend(
        prefix for prefix in prefixes if not any(name.startswith(prefix) for name in names)
    )
    if missing:
        raise ValueError("artefatti mancanti: " + ", ".join(missing))


def _reject_private_or_local(names: set[str], *, root: str | None = None) -> None:
    """Blocca file locali/sensibili anche se la configurazione di build regredisce."""

    rejected: list[str] = []
    for name in names:
        relative = name
        if root is not None:
            prefix = f"{root}/"
            if name == root:
                continue
            relative = name.removeprefix(prefix)
        normalized = relative.strip("/")
        if not normalized:
            continue
        parts = normalized.split("/")
        basename = parts[-1]
        if (
            any(part in FORBIDDEN_DIRECTORIES for part in parts)
            or any(normalized.startswith(prefix) for prefix in FORBIDDEN_PREFIXES)
            or ((basename == ".env" or basename.startswith(".env.")) and basename != ".env.example")
            or basename.lower().endswith(PRIVATE_KEY_SUFFIXES)
            or basename.lower().endswith(GENERATED_FILE_SUFFIXES)
            or basename in GENERATED_FILE_NAMES
        ):
            rejected.append(name)
    if rejected:
        sample = ", ".join(sorted(rejected)[:8])
        raise ValueError(f"artefatti locali o sensibili inclusi nella distribuzione: {sample}")


def check_wheel(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
    _require(
        names,
        exact=("ntruth/_ui/index.html",),
        prefixes=(
            "ntruth/_ui/assets/",
            "ntruth/_bundled/rulesets/",
            "ntruth/_bundled/ontology/",
        ),
    )
    if not any(name.endswith(".js") for name in names if name.startswith("ntruth/_ui/assets/")):
        raise ValueError("bundle JavaScript UI assente dal wheel")
    if not any(name.endswith(".css") for name in names if name.startswith("ntruth/_ui/assets/")):
        raise ValueError("bundle CSS UI assente dal wheel")
    _reject_private_or_local(names)


def check_sdist(path: Path) -> None:
    with tarfile.open(path, "r:gz") as archive:
        names = set(archive.getnames())
    roots = {name.split("/", 1)[0] for name in names if "/" in name}
    if len(roots) != 1:
        raise ValueError("sdist senza una singola root versionata")
    root = next(iter(roots))
    _reject_private_or_local(names, root=root)
    _require(
        names,
        exact=(f"{root}/apps/desktop/dist/index.html", f"{root}/pyproject.toml"),
        prefixes=(f"{root}/apps/desktop/dist/assets/",),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--sdist", type=Path)
    args = parser.parse_args()
    wheel = args.wheel or next(iter(sorted(Path("dist").glob("*.whl"))), None)
    sdist = args.sdist or next(iter(sorted(Path("dist").glob("*.tar.gz"))), None)
    if wheel is None or sdist is None:
        parser.error("wheel o sdist assente: eseguire `uv build`")
    check_wheel(wheel)
    check_sdist(sdist)
    print(f"Distribuzione verificata: {wheel.name}, {sdist.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
