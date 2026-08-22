"""Limiti e controlli su input ostili (PRD NFR-13).

Copre: limiti di dimensione, zip bomb, macro, formule, path traversal e
prompt injection. Nessun controllo qui esprime un giudizio scientifico: la
funzione e impedire che un file arbitrario diventi codice, percorso o istruzione.
"""

from __future__ import annotations

import os
import re
import zipfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path

#: Limiti prudenti: il target e un MacBook con 24 GB unificati (PRD 18.1, NFR-07).
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_FILES = 500
MAX_ARCHIVE_MEMBERS = 5_000
MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200.0

#: Estensioni con macro: rifiutate a monte, non "ripulite".
MACRO_EXTENSIONS = frozenset({".docm", ".xlsm", ".xlsb", ".pptm", ".dotm", ".xltm"})

SUPPORTED_EXTENSIONS: dict[str, str] = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xml": "application/xml",
    ".nxml": "application/xml",
    ".jats": "application/xml",
    ".pdf": "application/pdf",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    # Script statistici: vengono letti esclusivamente come testo dal CodeParser.
    # Il media type dedicato evita che possano essere confusi con moduli Python
    # o comandi eseguibili in qualsiasi punto successivo della pipeline.
    ".r": "text/x-r-source",
    ".py": "text/x-python-source",
    ".rmd": "text/x-r-markdown",
}

#: Prefissi che i fogli di calcolo interpretano come formula (CSV injection).
_FORMULA_PREFIXES = ("=", "+", "-", "@")

#: Frasi che tentano di dare istruzioni a un agente. Il contenuto dei documenti
#: e sempre dato, mai comando: qui viene solo segnalato.
_INJECTION_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"ignore (all|any|the) (previous|prior|above) instructions",
        r"disregard (the )?(previous|prior|system) (instructions|prompt)",
        r"you are (now )?(an? )?(ai|assistant|language model)",
        r"system\s*:\s*you (must|should|will)",
        r"(do not|non) (report|segnalare) (any )?(alert|pseudoreplication)",
        r"ignora\s+(?:tutte\s+)?(?:le\s+)?(?:istruzioni|indicazioni)\s+precedenti",
        r"dimentica\s+(?:tutte\s+)?(?:le\s+)?(?:istruzioni|indicazioni)",
        r"<\s*/?\s*(system|assistant|instructions)\s*>",
    )
]


class SafetyError(ValueError):
    """Input rifiutato. Il fallimento e sempre esplicito (PRD FR-006)."""


@dataclass
class SafetyReport:
    """Esito dei controlli su un singolo file."""

    path: Path
    accepted: bool = True
    reason: str | None = None
    warnings: list[str] = field(default_factory=list)


def resolve_inside(root: Path, candidate: Path) -> Path:
    """Impedisce path traversal e symlink fuori dal workspace."""
    root_resolved = root.resolve()
    target = (
        (root_resolved / candidate).resolve()
        if not candidate.is_absolute()
        else candidate.resolve()
    )
    if root_resolved != target and root_resolved not in target.parents:
        raise SafetyError(f"percorso fuori dal workspace: {candidate}")
    return target


def discover_ingest_candidates(
    source: Path,
) -> tuple[tuple[Path, ...], tuple[SafetyReport, ...]]:
    """Elenca i file da ingerire senza seguire symlink di file o di cartella.

    ``Path.rglob`` attraversa le directory symlink e puo copiare file esterni
    al workspace. Questo enumeratore usa ``os.walk(followlinks=False)`` e
    rifiuta ogni symlink prima che ``check_file`` ne legga il contenuto.
    """

    root = source.expanduser()
    if root.is_symlink():
        return (
            (),
            (
                SafetyReport(
                    path=root,
                    accepted=False,
                    reason="symlink di directory non ammesso"
                    if root.is_dir()
                    else "symlink non ammesso",
                ),
            ),
        )
    if not root.is_dir():
        return (root,), ()

    accepted: list[Path] = []
    rejected: list[SafetyReport] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False, topdown=True):
        current = Path(dirpath)
        keep: list[str] = []
        for name in dirnames:
            child = current / name
            if child.is_symlink():
                rejected.append(
                    SafetyReport(
                        path=child,
                        accepted=False,
                        reason="symlink di directory non ammesso",
                    )
                )
                continue
            keep.append(name)
        dirnames[:] = keep
        for name in filenames:
            path = current / name
            if path.is_symlink():
                rejected.append(
                    SafetyReport(path=path, accepted=False, reason="symlink non ammesso")
                )
                continue
            if not path.is_file():
                rejected.append(
                    SafetyReport(path=path, accepted=False, reason="non e un file regolare")
                )
                continue
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                rejected.append(
                    SafetyReport(
                        path=path,
                        accepted=False,
                        reason=f"estensione non supportata ({path.suffix or 'assente'})",
                    )
                )
                continue
            accepted.append(path)
    return tuple(sorted(accepted)), tuple(rejected)


def check_file(path: Path, *, total_bytes_so_far: int = 0) -> SafetyReport:
    """Controlli statici prima di aprire il contenuto."""
    report = SafetyReport(path=path)
    if not path.is_file():
        return SafetyReport(path=path, accepted=False, reason="non e un file regolare")
    if path.is_symlink():
        return SafetyReport(path=path, accepted=False, reason="symlink non ammesso")

    suffix = path.suffix.lower()
    if suffix in MACRO_EXTENSIONS:
        return SafetyReport(
            path=path, accepted=False, reason=f"formato con macro rifiutato ({suffix})"
        )
    if suffix not in SUPPORTED_EXTENSIONS:
        return SafetyReport(
            path=path, accepted=False, reason=f"estensione non supportata ({suffix or 'assente'})"
        )

    size = path.stat().st_size
    if size == 0:
        return SafetyReport(path=path, accepted=False, reason="file vuoto")
    if size > MAX_FILE_BYTES:
        return SafetyReport(
            path=path,
            accepted=False,
            reason=f"file oltre il limite ({size} > {MAX_FILE_BYTES} byte)",
        )
    if total_bytes_so_far + size > MAX_TOTAL_BYTES:
        return SafetyReport(
            path=path, accepted=False, reason="limite complessivo di progetto superato"
        )

    if zipfile.is_zipfile(path):
        report.warnings.extend(_check_archive(path))
        if any(w.startswith("BLOCK:") for w in report.warnings):
            blocking = next(w for w in report.warnings if w.startswith("BLOCK:"))
            return SafetyReport(
                path=path, accepted=False, reason=blocking.removeprefix("BLOCK:").strip()
            )
        # I metadati del central directory sono forgabili: la decisione usa i
        # byte decompressi reali, contati durante una passata di verifica.
        report.warnings.extend(_probe_decompressed_bytes(path))
        if any(w.startswith("BLOCK:") for w in report.warnings):
            blocking = next(w for w in report.warnings if w.startswith("BLOCK:"))
            return SafetyReport(
                path=path, accepted=False, reason=blocking.removeprefix("BLOCK:").strip()
            )
    return report


_PROBE_CHUNK_BYTES = 1024 * 1024


def _probe_decompressed_bytes(path: Path) -> list[str]:
    """Decomprime davvero ogni membro contando i byte prodotti.

    I limiti dichiarati nell'header non sono fiducia: qui il budget
    ``MAX_UNCOMPRESSED_BYTES`` e il rapporto ``MAX_COMPRESSION_RATIO`` vengono
    applicati ai byte effettivamente letti dallo stream deflate, chiudendo la
    via della zip bomb con metadati forgiati.
    """

    warnings: list[str] = []
    try:
        with zipfile.ZipFile(path) as zf:
            cumulative = 0
            for member in zf.infolist():
                if member.is_dir():
                    continue
                produced = 0
                try:
                    with zf.open(member) as stream:
                        while True:
                            chunk = stream.read(_PROBE_CHUNK_BYTES)
                            if not chunk:
                                break
                            produced += len(chunk)
                            cumulative += len(chunk)
                            if produced > MAX_UNCOMPRESSED_BYTES:
                                warnings.append(
                                    f"BLOCK: membro {member.filename} supera "
                                    f"{MAX_UNCOMPRESSED_BYTES} byte decompressi reali"
                                )
                                return warnings
                            if cumulative > MAX_UNCOMPRESSED_BYTES:
                                warnings.append(
                                    f"BLOCK: totale decompresso reale supera "
                                    f"{MAX_UNCOMPRESSED_BYTES} byte su {member.filename}"
                                )
                                return warnings
                except (zipfile.BadZipFile, OSError, EOFError, zlib.error) as exc:
                    warnings.append(f"BLOCK: membro {member.filename} illeggibile ({exc})")
                    return warnings
                if (
                    member.compress_size > 0
                    and produced / member.compress_size > MAX_COMPRESSION_RATIO
                ):
                    warnings.append(
                        "BLOCK: rapporto di compressione reale anomalo su "
                        f"{member.filename} ({produced / member.compress_size:.0f}x)"
                    )
                    return warnings
    except zipfile.BadZipFile as exc:
        warnings.append(f"BLOCK: archivio illeggibile durante la verifica ({exc})")
    return warnings


def _check_archive(path: Path) -> list[str]:
    """DOCX e XLSX sono archivi zip: verificare rapporto di compressione e macro."""
    warnings: list[str] = []
    try:
        with zipfile.ZipFile(path) as zf:
            members = zf.infolist()
            if len(members) > MAX_ARCHIVE_MEMBERS:
                warnings.append(
                    f"BLOCK: archivio con {len(members)} membri (limite {MAX_ARCHIVE_MEMBERS})"
                )
                return warnings
            total_uncompressed = 0
            for member in members:
                name = member.filename
                if name.startswith("/") or ".." in Path(name).parts:
                    warnings.append(f"BLOCK: membro con percorso sospetto ({name})")
                    return warnings
                if name.endswith("vbaProject.bin") or (
                    name.endswith(".bin") and "vba" in name.lower()
                ):
                    warnings.append("BLOCK: archivio contiene macro VBA")
                    return warnings
                total_uncompressed += member.file_size
                if member.compress_size > 0:
                    ratio = member.file_size / member.compress_size
                    if ratio > MAX_COMPRESSION_RATIO:
                        warnings.append(
                            f"BLOCK: rapporto di compressione anomalo su {name} ({ratio:.0f}x)"
                        )
                        return warnings
            if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
                warnings.append(
                    f"BLOCK: contenuto decompresso {total_uncompressed} byte oltre il limite"
                )
    except zipfile.BadZipFile as exc:
        warnings.append(f"BLOCK: archivio illeggibile ({exc})")
    return warnings


def neutralize_formula(value: str) -> tuple[str, bool]:
    """Disinnesca le formule nelle celle. Il valore originale resta nel testo citato.

    Un valore numerico negativo non e una formula; un valore con ``+`` iniziale
    viene neutralizzato perche Excel/LibreOffice lo reinterprettano come formula
    al round-trip (OWASP CSV injection).
    """

    stripped = value.lstrip()
    if stripped.startswith(_FORMULA_PREFIXES):
        try:
            float(stripped)
        except ValueError:
            return "'" + value, True
        if stripped.startswith("+"):
            # "+49" e numericamente valido ma resta un vettore di injection.
            return "'" + value, True
    return value, False


def detect_injection(text: str) -> list[str]:
    """Segnala tentativi di istruire un agente dal contenuto del documento.

    Il testo dei documenti e dato osservato, non istruzione: N-Truth non lo
    esegue mai. La segnalazione serve all'utente e all'audit.
    """
    hits: list[str] = []
    for pattern in _INJECTION_PATTERNS:
        match = pattern.search(text)
        if match:
            snippet = match.group(0)[:80].replace("\n", " ")
            hits.append(f'possibile prompt injection nel documento: "{snippet}"')
    return hits
