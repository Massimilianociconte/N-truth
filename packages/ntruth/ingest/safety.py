"""Limiti e controlli su input ostili (PRD NFR-13).

Copre: limiti di dimensione, zip bomb, macro, formule, path traversal e
prompt injection. Nessun controllo qui esprime un giudizio scientifico: la
funzione e impedire che un file arbitrario diventi codice, percorso o istruzione.
"""

from __future__ import annotations

import csv
import io
import os
import re
import zipfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path

from ntruth.schemas.manifest import ReleaseProfile

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

# Train D / D0 pubblica soltanto il percorso minimo verificabile. Tutti gli
# altri parser rimangono installabili e testabili, ma richiedono un opt-in nel
# manifest e non sono parte della superficie stabile iniziale.
D0_CORE_EXTENSIONS = frozenset({".txt", ".md", ".csv"})
EXTENDED_EXPERIMENTAL_EXTENSIONS = frozenset(SUPPORTED_EXTENSIONS)

_GENERIC_TEXT_MEDIA_TYPES = frozenset(
    {
        "text/plain",
        "text/markdown",
        "text/x-r-source",
        "text/x-python-source",
        "text/x-r-markdown",
    }
)
_ZIP_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
_SNIFF_BYTES = 256 * 1024
_XML_START = re.compile(
    rb"^\s*(?:<\?xml\b|<!DOCTYPE\b|<[A-Za-z_][\w:.-]*(?:\s|/?>))",
    re.IGNORECASE,
)

#: Prefissi che i fogli di calcolo interpretano come formula (CSV injection).
_FORMULA_PREFIXES = ("=", "+", "-", "@")

#: Connettori che rendono un prefisso +/- eseguibile come formula o DDE: senza
#: uno di questi il valore e testo osservato (fidelity), non vettore.
_FORMULA_CONNECTOR_CHARS = ("(", "|", "!", "=", "@", "+", "*", "/", "%", "\t", "\r", "\n")

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
    detected_media_type: str | None = None


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


def extension_allowed(extension: str, release_profile: ReleaseProfile | str) -> bool:
    """Restituisce se l'estensione appartiene al profilo dichiarato."""

    profile = ReleaseProfile(release_profile)
    suffix = extension.strip().casefold()
    allowed = (
        D0_CORE_EXTENSIONS
        if profile is ReleaseProfile.D0_CORE
        else EXTENDED_EXPERIMENTAL_EXTENSIONS
    )
    return suffix in allowed


def check_file(
    path: Path,
    *,
    total_bytes_so_far: int = 0,
    release_profile: ReleaseProfile | str = ReleaseProfile.D0_CORE,
) -> SafetyReport:
    """Controlli statici e sniffing prima che il parser apra il contenuto."""

    profile = ReleaseProfile(release_profile)
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
    if not extension_allowed(suffix, profile):
        return SafetyReport(
            path=path,
            accepted=False,
            reason=(
                f"formato {suffix} fuori dal profilo {profile.value}; "
                f"richiede release_profile={ReleaseProfile.EXTENDED_EXPERIMENTAL.value}"
            ),
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

    if _starts_with_zip_signature(path) or zipfile.is_zipfile(path):
        report.warnings.extend(_check_archive(path))
        if any(w.startswith("BLOCK:") for w in report.warnings):
            blocking = next(w for w in report.warnings if w.startswith("BLOCK:"))
            return SafetyReport(
                path=path, accepted=False, reason=blocking.removeprefix("BLOCK:").strip()
            )
        # I metadati sono forgabili: la decisione usa i byte decompressi reali.
        report.warnings.extend(_probe_decompressed_bytes(path))
        if any(w.startswith("BLOCK:") for w in report.warnings):
            blocking = next(w for w in report.warnings if w.startswith("BLOCK:"))
            return SafetyReport(
                path=path, accepted=False, reason=blocking.removeprefix("BLOCK:").strip()
            )

    detected = sniff_media_type(path)
    report.detected_media_type = detected
    expected = SUPPORTED_EXTENSIONS[suffix]
    if not _media_type_matches(expected, detected):
        return SafetyReport(
            path=path,
            accepted=False,
            reason=(
                "contenuto incoerente con l'estensione: "
                f"{suffix} dichiara {expected}, firma rilevata {detected}"
            ),
            warnings=report.warnings,
            detected_media_type=detected,
        )
    if profile is ReleaseProfile.D0_CORE and suffix == ".csv" and not _is_d0_simple_csv(path):
        return SafetyReport(
            path=path,
            accepted=False,
            reason="D0 accetta soltanto CSV semplice con delimitatore virgola e righe rettangolari",
            warnings=report.warnings,
            detected_media_type=detected,
        )
    return report


def _starts_with_zip_signature(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(4).startswith(_ZIP_SIGNATURES)
    except OSError:
        return False


def sniff_media_type(path: Path) -> str:
    """Rileva una famiglia media da byte e struttura, senza eseguire il file.

    Il risultato e deliberatamente piccolo e deterministico: serve a verificare
    la coerenza con l'estensione ammessa, non a sostituire un antivirus.
    """

    try:
        with path.open("rb") as handle:
            sample = handle.read(_SNIFF_BYTES)
    except OSError:
        return "application/octet-stream"

    stripped = sample.lstrip(b"\xef\xbb\xbf\x00\t\r\n ")
    if stripped.startswith(b"%PDF-"):
        return "application/pdf"
    if sample.startswith(_ZIP_SIGNATURES) or zipfile.is_zipfile(path):
        return _sniff_zip_media_type(path)
    if _XML_START.match(sample.lstrip(b"\xef\xbb\xbf")):
        return "application/xml"
    if not _is_probably_text(sample):
        return "application/octet-stream"

    suffix = path.suffix.casefold()
    if suffix == ".csv" and any(
        _looks_like_simple_delimited(sample, delimiter) for delimiter in (",", ";", "|")
    ):
        return "text/csv"
    if suffix == ".tsv" and _looks_like_simple_delimited(sample, "\t"):
        return "text/tab-separated-values"
    return "text/plain"


def _sniff_zip_media_type(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            names = frozenset(archive.namelist())
    except (OSError, zipfile.BadZipFile):
        return "application/zip"
    if "[Content_Types].xml" in names and "word/document.xml" in names:
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if "[Content_Types].xml" in names and "xl/workbook.xml" in names:
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return "application/zip"


def _is_probably_text(sample: bytes) -> bool:
    if not sample or b"\x00" in sample:
        return False
    try:
        decoded = sample.decode("utf-8-sig")
    except UnicodeDecodeError:
        decoded = sample.decode("latin-1")
    if not decoded:
        return False
    controls = sum(1 for character in decoded if ord(character) < 32 and character not in "\t\r\n")
    return controls / len(decoded) <= 0.01


def _looks_like_simple_delimited(sample: bytes, delimiter: str) -> bool:
    """Riconosce CSV/TSV rettangolare senza campi multilinea nel campione."""

    try:
        text = sample.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = sample.decode("latin-1")
    lines = [line for line in text.splitlines()[:64] if line.strip()]
    if not lines:
        return False
    try:
        rows = list(csv.reader(io.StringIO("\n".join(lines)), delimiter=delimiter))
    except csv.Error:
        return False
    if not rows or len(rows[0]) < 2 or any(not cell.strip() for cell in rows[0]):
        return False
    width = len(rows[0])
    return all(len(row) == width for row in rows[1:] if row)


def _is_d0_simple_csv(path: Path) -> bool:
    """Valida l'intero CSV D0 senza materializzarlo in memoria.

    Lo sniff iniziale serve soltanto a riconoscere il media type. La garanzia
    pubblica di rettangolarita deve invece coprire tutte le righe: limitarsi a
    un campione permetterebbe a celle tardive di essere troncate dal parser.
    Il limite di dimensione e gia applicato da :func:`check_file`.
    """

    for encoding in ("utf-8-sig", "latin-1"):
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                reader = csv.reader(handle, delimiter=",", strict=True)
                header: list[str] | None = None
                previous_line = 0
                for row in reader:
                    current_line = reader.line_num
                    # Il profilo semplice non ammette record distribuiti su piu
                    # righe fisiche, anche quando il modulo csv saprebbe leggerli.
                    if current_line != previous_line + 1:
                        return False
                    previous_line = current_line
                    if not row or not any(cell.strip() for cell in row):
                        continue
                    if header is None:
                        if len(row) < 2 or any(not cell.strip() for cell in row):
                            return False
                        header = row
                        continue
                    if len(row) != len(header):
                        return False
                return header is not None
        except UnicodeDecodeError:
            if encoding == "utf-8-sig":
                continue
            return False
        except (OSError, csv.Error):
            return False
    return False


def _media_type_matches(expected: str, detected: str) -> bool:
    if expected == detected:
        return True
    return expected in _GENERIC_TEXT_MEDIA_TYPES and detected == "text/plain"


def _check_archive(path: Path) -> list[str]:
    """DOCX e XLSX sono archivi zip: verificare rapporto di compressione e macro.

    I metadati del central directory sono forgabili: questa prima passata resta
    un filtro economico, ma la garanzia effettiva arriva da
    ``_probe_decompressed_bytes`` che conta i byte realmente decompressi.
    """

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


def neutralize_formula(value: str) -> tuple[str, bool]:
    """Disinnesca le formule eseguibili nelle celle, preservando il testo legittimo.

    Politica (OWASP CSV injection, orientata all'esecuzione di codice):

    - ``=`` e ``@`` iniziali sono sempre neutralizzati;
    - ``+`` seguito da un numero puro resta neutralizzato perche Excel/Office
      lo reinterprettano come formula al round-trip (``+49`` → ``=49``);
    - ``-`` seguito da un numero puro e un numero negativo, non una formula;
    - ``+``/``-`` seguito da testo senza connettori di formula (``(``, ``|``,
      ``!``, ``=``, ``@``, ``+``, ``*``, ``/``, ``%``, tab, CR, LF) e testo
      osservato (``-5mg``, ``-20 °C``, ``+ treated arm``) e non viene piu
      corrotto: non esiste percorso di esecuzione senza quei connettori;
    - qualunque altro prefisso con connettori di formula resta neutralizzato
      (``+SUM(A1)``, ``-cmd|' /c calc'!A1``, ``-2+3``).
    """

    stripped = value.lstrip()
    if not stripped.startswith(_FORMULA_PREFIXES):
        return value, False
    sign, rest = stripped[0], stripped[1:]
    if sign in {"+", "-"}:
        try:
            float(stripped)
        except ValueError:
            pass
        else:
            if sign == "-":
                return value, False
            # "+49" e numericamente valido ma resta un vettore di injection.
            return "'" + value, True
        if not any(ch in rest for ch in _FORMULA_CONNECTOR_CHARS):
            return value, False
    return "'" + value, True


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
