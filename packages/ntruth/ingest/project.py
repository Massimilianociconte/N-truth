"""Progetto locale: ID stabile, copia delle fonti, checksum e manifest (PRD FR-001, FR-007).

Il progetto e una cartella riapribile offline senza perdita. Le fonti vengono
copiate dentro il workspace cosi che un report resti ricostruibile anche se
l'originale viene spostato (PRD 7.4: ogni report e ricostruibile da input,
checksum e versioni senza stato remoto).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from ntruth import SCHEMA_VERSION
from ntruth.ingest.safety import discover_ingest_candidates
from ntruth.ingest.safety import (
    MAX_FILES,
    SUPPORTED_EXTENSIONS,
    SafetyError,
    SafetyReport,
    check_file,
    resolve_inside,
)
from ntruth.schemas.core import stable_id
from ntruth.schemas.manifest import ProjectFile, ProjectManifest, ReleaseProfile
from ntruth.storage import BlobIntegrityError, BlobStore, StorageDatabase

MANIFEST_NAME = "manifest.json"
SOURCES_DIR = "sources"
BLOBS_DIR = "blobs"
DATABASE_NAME = "ntruth.sqlite3"
MANIFEST_CHECKSUM_KEY = "manifest_checksum"


class _ManifestStatus(StrEnum):
    CURRENT = "current"
    LEGACY_UNSIGNED = "legacy_unsigned"
    LEGACY_CHECKSUM = "legacy_checksum"


def _workspace_path(root: Path, name: str, *, kind: str) -> Path:
    """Restituisce un path di storage solo se resta nel workspace e non e un symlink."""

    root = root.expanduser().resolve()
    candidate = root / name
    if candidate.is_symlink():
        raise SafetyError(f"path di storage symlink non ammesso: {candidate}")
    resolved = candidate.resolve()
    if resolved != root and root not in resolved.parents:
        raise SafetyError(f"path di storage fuori dal workspace: {candidate}")
    if candidate.exists():
        if kind == "directory" and not candidate.is_dir():
            raise SafetyError(f"directory di storage non valida: {candidate}")
        if kind == "file" and not candidate.is_file():
            raise SafetyError(f"file di storage non valido: {candidate}")
    return candidate


def _validate_database_sidecars(database_path: Path) -> None:
    for suffix in ("-journal", "-shm", "-wal"):
        sidecar = Path(f"{database_path}{suffix}")
        if sidecar.is_symlink():
            raise SafetyError(f"sidecar SQLite symlink non ammesso: {sidecar}")


def _validate_workspace_storage(root: Path) -> None:
    _workspace_path(root, MANIFEST_NAME, kind="file")
    _workspace_path(root, SOURCES_DIR, kind="directory")
    _workspace_path(root, BLOBS_DIR, kind="directory")
    database_path = _workspace_path(root, DATABASE_NAME, kind="file")
    _validate_database_sidecars(database_path)


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write_text(path: Path, content: str) -> None:
    """Scrive nella stessa directory e pubblica con replace atomico dopo fsync."""

    if path.is_symlink():
        raise SafetyError(f"manifest symlink non ammesso: {path}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if path.is_symlink():
            raise SafetyError(f"manifest symlink non ammesso: {path}")
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _verify_declared_manifest_digest(
    declared: str | None,
    actual: str,
    *,
    required: bool,
) -> None:
    if declared is None:
        if required:
            raise SafetyError(
                "manifest legacy senza checksum: fornire lo SHA-256 esplicito "
                "del file manifest.json"
            )
        return
    normalized = declared.strip()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise SafetyError("SHA-256 dichiarato del manifest non canonico")
    if not hmac.compare_digest(normalized, actual):
        raise SafetyError("SHA-256 dichiarato non corrisponde al manifest legacy")


@dataclass
class IngestResult:
    """Esito dell'ingestione: cosa e entrato e cosa e stato scartato, con motivo."""

    accepted: list[ProjectFile] = field(default_factory=list)
    rejected: list[SafetyReport] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def has_rejections(self) -> bool:
        return bool(self.rejected)

    def summary(self) -> str:
        lines = [f"{len(self.accepted)} file accettati, {len(self.rejected)} scartati"]
        for rep in self.rejected:
            lines.append(f"  scartato {rep.path.name}: {rep.reason}")
        for warn in self.warnings:
            lines.append(f"  attenzione: {warn}")
        return "\n".join(lines)


def sha256_of(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def _copy_source_exclusive(source: Path, destination: Path, *, expected_sha256: str) -> None:
    """Copia e pubblica senza poter sovrascrivere una fonte gia presente."""

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copy2(source, temporary)
        if sha256_of(temporary) != expected_sha256:
            raise SafetyError("la sorgente e cambiata durante la copia")
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        try:
            os.link(temporary, destination)
        except FileExistsError:
            if (
                destination.is_symlink()
                or not destination.is_file()
                or sha256_of(destination) != expected_sha256
            ):
                raise SafetyError(f"collisione sul percorso sorgente: {destination}") from None
        _fsync_directory(destination.parent)
    finally:
        temporary.unlink(missing_ok=True)


class Project:
    """Workspace locale di N-Truth."""

    def __init__(self, root: Path, manifest: ProjectManifest) -> None:
        # Root sempre risolta: i controlli di containment confrontano percorsi reali
        # e su macOS /var e un symlink verso /private/var.
        self.root = root.expanduser().resolve()
        self.manifest = manifest

    # ---------------------------------------------------------------- lifecycle

    @classmethod
    def create(
        cls,
        root: Path,
        *,
        name: str | None = None,
        domain: str = "quantitative_microscopy",
        language: str = "en",
        ruleset_id: str = "ntruth-core",
        ruleset_version: str = "0.2.0",
        release_profile: ReleaseProfile = ReleaseProfile.D0_CORE,
    ) -> Project:
        root = root.expanduser()
        root.mkdir(parents=True, exist_ok=True)
        root = root.resolve()
        _validate_workspace_storage(root)
        _workspace_path(root, SOURCES_DIR, kind="directory").mkdir(exist_ok=True)
        _workspace_path(root, BLOBS_DIR, kind="directory").mkdir(exist_ok=True)
        project_name = name or root.name
        manifest = ProjectManifest(
            project_id=stable_id("prj", project_name, domain, language),
            name=project_name,
            domain=domain,
            language=language,
            schema_version=SCHEMA_VERSION,
            release_profile=release_profile,
            ruleset_id=ruleset_id,
            ruleset_version=ruleset_version,
        )
        project = cls(root, manifest)
        project.save()
        return project

    @classmethod
    def open(
        cls,
        root: Path,
        *,
        migrate_legacy_manifest: bool = False,
        legacy_manifest_sha256: str | None = None,
    ) -> Project:
        root = root.expanduser().resolve()
        _validate_workspace_storage(root)
        manifest_path = _workspace_path(root, MANIFEST_NAME, kind="file")
        if not manifest_path.is_file():
            raise SafetyError(f"manifest assente in {root}")
        payload, manifest, status, raw_digest = _load_manifest(manifest_path)
        is_legacy = status is not _ManifestStatus.CURRENT
        if is_legacy:
            database_exists = _workspace_path(root, DATABASE_NAME, kind="file").exists()
            if "release_profile" in payload or database_exists:
                raise SafetyError(
                    "manifest v6 degradato: integrity completa obbligatoria; "
                    "la migrazione legacy non puo rifirmarlo"
                )
            if not migrate_legacy_manifest:
                raise SafetyError(
                    "manifest legacy senza checksum v6 completo; richiedere "
                    "esplicitamente la migrazione"
                )
            _verify_declared_manifest_digest(
                legacy_manifest_sha256,
                raw_digest,
                required=status is _ManifestStatus.LEGACY_UNSIGNED,
            )
        _validate_manifest_paths(root, manifest)
        project = cls(root, manifest)
        if is_legacy:
            source_problems = project._source_copy_integrity_problems()
            if source_problems:
                raise SafetyError("manifest legacy non migrabile: " + "; ".join(source_problems))
            # La migrazione e consentita soltanto dopo la verifica read-only di
            # tutte le copie sorgente. Da questo punto puo creare blob/DB e infine
            # riscrive il manifest con il checksum canonico.
            project._synchronize_content_storage()
            project.save()
            return project

        # Il checksum e gia stato validato da _load_manifest. Solo ora sono
        # consentiti la revisione SQLite e il backfill content-addressed.
        project._persist_manifest_revision(payload)
        project._synchronize_content_storage()
        return project

    @classmethod
    def open_or_create(
        cls,
        root: Path,
        *,
        migrate_legacy_manifest: bool = False,
        legacy_manifest_sha256: str | None = None,
        **kwargs: object,
    ) -> Project:
        if (root / MANIFEST_NAME).is_file():
            project = cls.open(
                root,
                migrate_legacy_manifest=migrate_legacy_manifest,
                legacy_manifest_sha256=legacy_manifest_sha256,
            )
            requested = kwargs.get("release_profile")
            if requested is not None:
                if not isinstance(requested, (str, ReleaseProfile)):
                    raise SafetyError("release_profile non valido")
                requested_profile = ReleaseProfile(requested)
                if project.manifest.release_profile is not requested_profile:
                    raise SafetyError(
                        "release_profile richiesto non coincide con il manifest esistente "
                        f"({requested_profile.value} != "
                        f"{project.manifest.release_profile.value})"
                    )
            return project
        return cls.create(root, **kwargs)  # type: ignore[arg-type]

    def save(self) -> Path:
        checksum = self.manifest.checksum()
        updated_manifest = self.manifest.model_copy(
            update={"integrity": {MANIFEST_CHECKSUM_KEY: checksum}}
        )
        payload = updated_manifest.model_dump(mode="json")
        path = _workspace_path(self.root, MANIFEST_NAME, kind="file")
        _atomic_write_text(
            path,
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
        )
        self.manifest = updated_manifest
        self._persist_manifest_revision(payload)
        return path

    # ------------------------------------------------------------------ ingest

    def add(self, source: Path) -> IngestResult:
        """Registra un file o l'intero contenuto supportato di una cartella."""
        source = source.expanduser()
        result = IngestResult()
        if source.is_dir() or source.is_symlink():
            candidates, skipped = discover_ingest_candidates(source)
            result.rejected.extend(skipped)
        else:
            candidates = (source,)

        if len(candidates) > MAX_FILES:
            raise SafetyError(f"troppi file ({len(candidates)} > {MAX_FILES})")

        total = sum(f.size_bytes for f in self.manifest.files)
        for path in candidates:
            report = check_file(
                path,
                total_bytes_so_far=total,
                release_profile=self.manifest.release_profile,
            )
            if not report.accepted:
                result.rejected.append(report)
                continue
            project_file = self._register(path, report)
            if project_file is None:
                result.warnings.append(f"{path.name}: gia presente con lo stesso checksum")
                continue
            total += project_file.size_bytes
            result.accepted.append(project_file)
            result.warnings.extend(f"{path.name}: {w}" for w in report.warnings)

        self.save()
        return result

    def _register(self, path: Path, report: SafetyReport) -> ProjectFile | None:
        checksum = sha256_of(path)
        existing = next(
            (
                project_file
                for project_file in self.manifest.files
                if (project_file.filename, project_file.sha256) == (path.name, checksum)
            ),
            None,
        )
        if existing is not None:
            existing_path = self.path_of(existing)
            if existing_path.is_file() and sha256_of(existing_path) == existing.sha256:
                self._record_blob(existing, existing_path)
            return None

        _workspace_path(self.root, SOURCES_DIR, kind="directory")
        destination = resolve_inside(self.root, Path(SOURCES_DIR) / path.name)
        if destination.is_symlink():
            raise SafetyError(f"destinazione sorgente symlink non ammessa: {destination}")
        if destination.exists():
            if not destination.is_file():
                raise SafetyError(f"destinazione sorgente non regolare: {destination}")
            if sha256_of(destination) != checksum:
                # Il digest completo evita la collisione deliberata del vecchio
                # suffisso a 32 bit e resta entro i limiti del nome file.
                destination = resolve_inside(
                    self.root,
                    Path(SOURCES_DIR) / f"{checksum}{path.suffix.lower()}",
                )
        if destination.is_symlink():
            raise SafetyError(f"destinazione sorgente symlink non ammessa: {destination}")
        if destination.exists():
            if not destination.is_file() or sha256_of(destination) != checksum:
                raise SafetyError(f"collisione sul percorso sorgente: {destination}")
        else:
            _copy_source_exclusive(path, destination, expected_sha256=checksum)

        project_file = ProjectFile(
            file_id=stable_id("fil", path.name, checksum),
            filename=path.name,
            relative_path=str(destination.relative_to(self.root)),
            media_type=SUPPORTED_EXTENSIONS[path.suffix.lower()],
            size_bytes=destination.stat().st_size,
            sha256=checksum,
        )
        self.manifest = self.manifest.model_copy(
            update={"files": (*self.manifest.files, project_file)}
        )
        self._record_blob(project_file, destination)
        return project_file

    # ------------------------------------------------------------------ access

    def path_of(self, project_file: ProjectFile) -> Path:
        relative = Path(project_file.relative_path)
        if relative.is_absolute():
            raise SafetyError(
                f"percorso assoluto non ammesso nel manifest: {project_file.relative_path}"
            )
        target = resolve_inside(self.root, relative)
        sources_root = (self.root / SOURCES_DIR).resolve()
        if target != sources_root and sources_root not in target.parents:
            raise SafetyError(
                f"percorso del manifest fuori da '{SOURCES_DIR}': {project_file.relative_path}"
            )
        return target

    def verify_integrity(self) -> list[str]:
        """Ricontrolla i checksum registrati (PRD FR-007)."""
        problems: list[str] = []
        try:
            _, persisted_manifest, status, _ = _load_manifest(self.root / MANIFEST_NAME)
            if status is not _ManifestStatus.CURRENT:
                problems.append(
                    "manifest: checksum v6 completo assente; migrazione esplicita richiesta"
                )
            elif persisted_manifest.checksum() != self.manifest.checksum():
                problems.append("manifest: payload su disco diverso dal progetto aperto")
        except (OSError, ValueError) as error:
            problems.append(f"manifest: {error}")

        blob_store = self.blob_store
        for pf in self.manifest.files:
            path = self.path_of(pf)
            if not path.is_file():
                problems.append(f"{pf.filename}: file mancante nel workspace")
            elif sha256_of(path) != pf.sha256:
                problems.append(f"{pf.filename}: checksum non corrispondente")
            try:
                blob_store.verify(pf.sha256, expected_size=pf.size_bytes)
            except BlobIntegrityError as error:
                problems.append(f"{pf.filename}: {error}")
        return problems

    def _source_copy_integrity_problems(self) -> list[str]:
        """Verifica le sole copie legacy prima di rendere autorevole il manifest."""

        problems: list[str] = []
        for project_file in self.manifest.files:
            path = self.path_of(project_file)
            if path.is_symlink():
                problems.append(f"{project_file.filename}: symlink non ammesso")
            elif not path.is_file():
                problems.append(f"{project_file.filename}: file mancante nel workspace")
            elif path.stat().st_size != project_file.size_bytes:
                problems.append(f"{project_file.filename}: dimensione non corrispondente")
            elif sha256_of(path) != project_file.sha256:
                problems.append(f"{project_file.filename}: checksum non corrispondente")
        return problems

    def untracked_license_files(self) -> list[ProjectFile]:
        """File senza license manifest: bloccano training e redistribuzione (FR-032)."""
        return [f for f in self.manifest.files if f.license_manifest is None]

    # ---------------------------------------------------------- local storage v6

    @property
    def database_path(self) -> Path:
        path = _workspace_path(self.root, DATABASE_NAME, kind="file")
        _validate_database_sidecars(path)
        return path

    @property
    def blob_store(self) -> BlobStore:
        return BlobStore(_workspace_path(self.root, BLOBS_DIR, kind="directory"))

    def _persist_manifest_revision(self, payload: dict[str, object] | None = None) -> None:
        manifest_payload = payload or self.manifest.model_dump(mode="json")
        manifest_payload["integrity"] = {MANIFEST_CHECKSUM_KEY: self.manifest.checksum()}
        with StorageDatabase(self.database_path) as database:
            database.upsert_project(
                project_id=self.manifest.project_id,
                name=self.manifest.name,
                manifest_path=MANIFEST_NAME,
                manifest_checksum=self.manifest.checksum(),
            )
            database.append_revision(
                project_id=self.manifest.project_id,
                payload=manifest_payload,
                actor_role="system",
            )

    def _record_blob(self, project_file: ProjectFile, source: Path) -> None:
        result = self.blob_store.put_file(source, expected_sha256=project_file.sha256)
        with StorageDatabase(self.database_path) as database, database.transaction():
            database.upsert_project(
                project_id=self.manifest.project_id,
                name=self.manifest.name,
                manifest_path=MANIFEST_NAME,
                manifest_checksum=self.manifest.checksum(),
            )
            database.register_blob(result.record, media_type=project_file.media_type)
            database.link_project_blob(
                project_id=self.manifest.project_id,
                file_id=project_file.file_id,
                blob_sha256=result.record.sha256,
                filename=project_file.filename,
                media_type=project_file.media_type,
                legacy_relative_path=project_file.relative_path,
            )

    def _synchronize_content_storage(self) -> None:
        """Backfill non distruttivo dei blob per manifest creati da versioni precedenti."""

        for project_file in self.manifest.files:
            source = self.path_of(project_file)
            if source.is_file() and sha256_of(source) == project_file.sha256:
                self._record_blob(project_file, source)


def _load_manifest(
    path: Path,
) -> tuple[dict[str, object], ProjectManifest, _ManifestStatus, str]:
    """Carica e verifica l'integrita dichiarata prima di qualsiasi side effect."""

    try:
        raw_bytes = path.read_bytes()
        raw = json.loads(raw_bytes.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise SafetyError("manifest non codificato UTF-8") from error
    except json.JSONDecodeError as error:
        raise SafetyError(f"manifest JSON non valido: {error.msg}") from error
    if not isinstance(raw, dict):
        raise SafetyError("manifest JSON deve essere un oggetto")

    payload: dict[str, object] = dict(raw)
    manifest = ProjectManifest.model_validate(payload)
    raw_digest = hashlib.sha256(raw_bytes).hexdigest()
    raw_integrity = payload.get("integrity")
    if raw_integrity is None or raw_integrity == {}:
        return payload, manifest, _ManifestStatus.LEGACY_UNSIGNED, raw_digest
    if not isinstance(raw_integrity, Mapping):
        raise SafetyError("integrity del manifest deve essere un oggetto")
    if MANIFEST_CHECKSUM_KEY not in raw_integrity:
        raise SafetyError("integrity del manifest presente ma priva di manifest_checksum")

    registered = raw_integrity[MANIFEST_CHECKSUM_KEY]
    if (
        not isinstance(registered, str)
        or len(registered) != 64
        or any(character not in "0123456789abcdef" for character in registered)
    ):
        raise SafetyError("integrity.manifest_checksum non e uno SHA-256 canonico")
    expected = manifest.checksum()
    if hmac.compare_digest(registered, expected):
        return payload, manifest, _ManifestStatus.CURRENT, raw_digest
    if hmac.compare_digest(registered, manifest.legacy_checksum_v5()):
        return payload, manifest, _ManifestStatus.LEGACY_CHECKSUM, raw_digest
    raise SafetyError(
        "checksum manifest non corrispondente: il payload potrebbe essere stato alterato"
    )


def _validate_manifest_paths(root: Path, manifest: ProjectManifest) -> None:
    """Reject a tampered project before any source path can be opened.

    A project manifest is data supplied at a trust boundary.  It may only refer
    to regular project sources, even when a syntactically valid Pydantic payload
    contains ``..`` components or an absolute path.
    """
    sources_root = (root / SOURCES_DIR).resolve()
    for project_file in manifest.files:
        relative = Path(project_file.relative_path)
        if relative.is_absolute():
            raise SafetyError(
                f"percorso assoluto non ammesso nel manifest: {project_file.relative_path}"
            )
        target = resolve_inside(root, relative)
        if target != sources_root and sources_root not in target.parents:
            raise SafetyError(
                f"percorso del manifest fuori da '{SOURCES_DIR}': {project_file.relative_path}"
            )
