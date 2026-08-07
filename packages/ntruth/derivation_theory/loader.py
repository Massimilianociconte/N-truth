"""Caricamento degli artefatti Derivation Theory (PRD v8.0 §20.3, NFR-33).

La teoria vive in file JSON versionati fuori dal codice, come i ruleset
(PRD §26.5: versionamento separato). Un ruleset v8 che dichiara
``theory_version`` viene validato contro l'artefatto qui caricato
(``ntruth.rules.loader``): il Rulebook implementa le clausole, la teoria le
definisce e non coincidono mai in un unico artefatto (PRD §20.3).
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path

from ntruth.derivation_theory.models import DerivationTheory

DEFAULT_THEORY_ID = "derivation-theory"
DEFAULT_THEORY_VERSION = "0.1.0"
ENV_VAR = "NTRUTH_THEORIES"

_THEORY_REF_RE = re.compile(r"^(?P<theory_id>.+)-(?P<version>\d+\.\d+\.\d+)$")


class TheoryNotFound(FileNotFoundError):
    """Teoria assente: nessun ruleset v8 puo' dichiarare una teoria irrisolvibile."""


def parse_theory_ref(theory_ref: str) -> tuple[str, str]:
    """Scompone ``<theory_id>-<version>`` (es. ``derivation-theory-0.1.0``)."""
    match = _THEORY_REF_RE.match(theory_ref.strip())
    if not match:
        raise ValueError(f"theory_ref non valido: '{theory_ref}' (atteso <theory_id>-X.Y.Z)")
    return match.group("theory_id"), match.group("version")


def theory_directories() -> list[Path]:
    """Percorsi in cui cercare le teorie, in ordine di precedenza."""
    paths: list[Path] = []
    override = os.environ.get(ENV_VAR)
    if override:
        paths.extend(Path(p).expanduser() for p in override.split(os.pathsep) if p)
    package_root = Path(__file__).resolve().parent.parent
    paths.append(package_root / "_bundled" / "theories")
    # Layout di sviluppo: packages/ntruth/derivation_theory/loader.py -> <repo>/theories
    paths.append(package_root.parent.parent / "theories")
    return paths


def available_theories() -> list[Path]:
    found: list[Path] = []
    for directory in theory_directories():
        if directory.is_dir():
            found.extend(sorted(directory.glob("*.json")))
    return found


@lru_cache(maxsize=8)
def load_theory(
    theory_id: str = DEFAULT_THEORY_ID, version: str = DEFAULT_THEORY_VERSION
) -> DerivationTheory:
    """Carica una teoria per ID e versione."""
    filename = f"{theory_id}-{version}.json"
    for directory in theory_directories():
        candidate = directory / filename
        if candidate.is_file():
            theory = load_theory_file(candidate)
            if theory.metadata.theory_id != theory_id or theory.metadata.version != version:
                raise ValueError(
                    f"teoria '{candidate}' dichiara {theory.theory_ref}, atteso {theory_id}-{version}"
                )
            return theory
    searched = ", ".join(str(d) for d in theory_directories())
    raise TheoryNotFound(f"teoria '{filename}' non trovata. Cercato in: {searched}")


def load_theory_ref(theory_ref: str) -> DerivationTheory:
    """Carica una teoria dal riferimento completo dichiarato da un ruleset v8."""
    theory_id, version = parse_theory_ref(theory_ref)
    return load_theory(theory_id, version)


def load_theory_file(path: Path) -> DerivationTheory:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return DerivationTheory.model_validate(payload)
