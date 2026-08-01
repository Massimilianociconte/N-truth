"""Caricamento dei ruleset versionati da disco (PRD FR-018, FR-034).

Le regole vivono in file JSON fuori dal codice: modificarle non richiede
retraining ne una nuova release del modello. Il ruleset attivo e il suo
checksum finiscono in ogni report.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from ntruth.schemas.rules import Ruleset

DEFAULT_RULESET_ID = "ntruth-core"
DEFAULT_RULESET_VERSION = "0.1.0"
ENV_VAR = "NTRUTH_RULESETS"


class RulesetNotFound(FileNotFoundError):
    """Ruleset assente: l'inferenza non parte senza regole dichiarate."""


def ruleset_directories() -> list[Path]:
    """Percorsi in cui cercare i ruleset, in ordine di precedenza."""
    paths: list[Path] = []
    override = os.environ.get(ENV_VAR)
    if override:
        paths.extend(Path(p).expanduser() for p in override.split(os.pathsep) if p)
    package_root = Path(__file__).resolve().parent.parent
    paths.append(package_root / "_bundled" / "rulesets")
    # Layout di sviluppo: packages/ntruth/rules/loader.py -> <repo>/rulesets
    paths.append(package_root.parent.parent / "rulesets")
    return paths


def available_rulesets() -> list[Path]:
    found: list[Path] = []
    for directory in ruleset_directories():
        if directory.is_dir():
            found.extend(sorted(directory.glob("*.json")))
    return found


@lru_cache(maxsize=8)
def load_ruleset(
    ruleset_id: str = DEFAULT_RULESET_ID, version: str = DEFAULT_RULESET_VERSION
) -> Ruleset:
    """Carica un ruleset per ID e versione."""
    filename = f"{ruleset_id}-{version}.json"
    for directory in ruleset_directories():
        candidate = directory / filename
        if candidate.is_file():
            return load_ruleset_file(candidate)
    searched = ", ".join(str(d) for d in ruleset_directories())
    raise RulesetNotFound(f"ruleset '{filename}' non trovato. Cercato in: {searched}")


def load_ruleset_file(path: Path) -> Ruleset:
    payload = json.loads(path.read_text(encoding="utf-8"))
    ruleset = Ruleset.model_validate(payload)
    return ruleset.model_copy(update={"source_path": str(path)})
