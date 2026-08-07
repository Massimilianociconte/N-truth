"""Caricamento dei ruleset versionati da disco (PRD FR-018, FR-034).

Le regole vivono in file JSON fuori dal codice: modificarle non richiede
retraining ne una nuova release del modello. Il ruleset attivo e il suo
checksum finiscono in ogni report.

Contratto theory v8 (PRD §7.14, §10.11, §20.3, NFR-33): un ruleset che
dichiara ``theory_version`` deve collegare ogni regola eseguibile a una
clausola esistente della teoria dichiarata; le violazioni sono rifiutate con
errore strutturato ``RULE_THEORY_MISMATCH`` (tassonomia §13.6). I ruleset
legacy senza ``theory_version`` restano caricabili senza collegamento theory.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from ntruth.derivation_theory import DerivationTheory, TheoryNotFound, load_theory_ref
from ntruth.schemas.rules import Ruleset, TheoryLinkageStatus

DEFAULT_RULESET_ID = "ntruth-core"
DEFAULT_RULESET_VERSION = "0.2.0"
ENV_VAR = "NTRUTH_RULESETS"

#: Codice dell'errore strutturato di collegamento theory (tassonomia PRD
#: §13.6; lo stesso token e' in ``parser_ai.stages.StageErrorCode``). Il
#: package rules non importa il runtime parser_ai per il vincolo di confine
#: testato in tests/unit/test_import_boundaries.py.
RULE_THEORY_MISMATCH = "RULE_THEORY_MISMATCH"


class RulesetNotFound(FileNotFoundError):
    """Ruleset assente: l'inferenza non parte senza regole dichiarate."""


class RuleTheoryMismatchError(ValueError):
    """Ruleset v8 con collegamento theory invalido: release blocker (§10.11).

    Errore strutturato fail-closed con codice ``RULE_THEORY_MISMATCH``
    (PRD §13.6). Il loader rifiuta il ruleset invece di degradare in
    silenzio: una regola eseguibile senza clausola non e' scientifica.
    """

    code: str = RULE_THEORY_MISMATCH

    def __init__(
        self,
        message: str,
        *,
        ruleset: str = "",
        rule_id: str | None = None,
        clause_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.ruleset = ruleset
        self.rule_id = rule_id
        self.clause_id = clause_id


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
    _enforce_theory_linkage(ruleset)
    return ruleset.model_copy(update={"source_path": str(path)})


def _enforce_theory_linkage(ruleset: Ruleset) -> None:
    """Valida il collegamento regola<->clausola dei ruleset v8 (NFR-33).

    Regole fail-closed (PRD §10.11, §20.3):
    - ruleset senza ``theory_version``: legacy, nessun collegamento richiesto;
    - teoria dichiarata ma non risolvibile: ``RULE_THEORY_MISMATCH``;
    - regola abilitata senza clausola (o con clausola inesistente): rifiutata,
      perche' e' un release blocker (§10.11: ogni regola deve avere theory
      clause);
    - regola disabilitata senza clausola: ammessa solo nella forma esplicita
      ``theory_status=SCIENTIFIC_REVIEW_REQUIRED`` (mai cancellata, mai
      silenziosa); ogni altra combinazione e' rifiutata.
    """
    if ruleset.theory_version is None:
        return
    ref = ruleset.theory_version
    label = f"{ruleset.ruleset_id}@{ruleset.version}"
    try:
        theory = load_theory_ref(ref)
    except (TheoryNotFound, ValueError) as exc:
        raise RuleTheoryMismatchError(
            f"ruleset {label} dichiara la teoria '{ref}' ma non e' risolvibile: {exc}",
            ruleset=label,
        ) from exc
    clause_ids = set(theory.clause_ids())
    for rule in ruleset.rules:
        if rule.theory_clause is not None:
            if rule.theory_clause not in clause_ids:
                raise RuleTheoryMismatchError(
                    f"regola {rule.rule_id} del ruleset {label} riferisce la clausola "
                    f"inesistente '{rule.theory_clause}' della teoria {theory.theory_ref}",
                    ruleset=label,
                    rule_id=rule.rule_id,
                    clause_id=rule.theory_clause,
                )
            continue
        if rule.enabled:
            raise RuleTheoryMismatchError(
                f"regola abilitata {rule.rule_id} del ruleset {label} senza theory clause: "
                f"release blocker (PRD §10.11)",
                ruleset=label,
                rule_id=rule.rule_id,
            )
        if rule.theory_status is not TheoryLinkageStatus.SCIENTIFIC_REVIEW_REQUIRED:
            raise RuleTheoryMismatchError(
                f"regola disabilitata {rule.rule_id} del ruleset {label} senza theory clause "
                "deve dichiarare theory_status=SCIENTIFIC_REVIEW_REQUIRED (forma fail-closed)",
                ruleset=label,
                rule_id=rule.rule_id,
            )
    for gap in ruleset.theory_coverage_gaps:
        if gap.clause_id not in clause_ids:
            raise RuleTheoryMismatchError(
                f"coverage gap del ruleset {label} riferisce la clausola inesistente "
                f"'{gap.clause_id}' della teoria {theory.theory_ref}",
                ruleset=label,
                clause_id=gap.clause_id,
            )


def declared_theory(ruleset: Ruleset) -> DerivationTheory | None:
    """Teoria dichiarata da un ruleset v8, o None per i ruleset legacy."""
    if ruleset.theory_version is None:
        return None
    return load_theory_ref(ruleset.theory_version)
