"""Progetto locale: ID stabile, copia delle fonti, checksum e manifest (PRD FR-001, FR-007).

Il progetto e una cartella riapribile offline senza perdita. Le fonti vengono
copiate dentro il workspace cosi che un report resti ricostruibile anche se
l'originale viene spostato (PRD 7.4: ogni report e ricostruibile da input,
checksum e versioni senza stato remoto).
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from ntruth import SCHEMA_VERSION
from ntruth.ingest.safety import (
    MAX_FILES,
    SUPPORTED_EXTENSIONS,
    SafetyError,
    SafetyReport,
    check_file,
    resolve_inside,
)
from ntruth.schemas.core import stable_id
from ntruth.schemas.manifest import ProjectFile, ProjectManifest

MANIFEST_NAME = "manifest.json"
SOURCES_DIR = "sources"


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
        ruleset_version: str = "0.1.0",
    ) -> Project:
        root = root.expanduser()
        root.mkdir(parents=True, exist_ok=True)
        (root / SOURCES_DIR).mkdir(exist_ok=True)
        project_name = name or root.name
        manifest = ProjectManifest(
            project_id=stable_id("prj", project_name, domain, language),
            name=project_name,
            domain=domain,
            language=language,
            schema_version=SCHEMA_VERSION,
            ruleset_id=ruleset_id,
            ruleset_version=ruleset_version,
        )
        project = cls(root, manifest)
        project.save()
        return project

    @classmethod
    def open(cls, root: Path) -> Project:
        root = root.expanduser().resolve()
        manifest_path = root / MANIFEST_NAME
        if not manifest_path.is_file():
            raise SafetyError(f"manifest assente in {root}")
        manifest = ProjectManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        _validate_manifest_paths(root, manifest)
        return cls(root, manifest)

    @classmethod
    def open_or_create(cls, root: Path, **kwargs: object) -> Project:
        if (root / MANIFEST_NAME).is_file():
            return cls.open(root)
        return cls.create(root, **kwargs)  # type: ignore[arg-type]

    def save(self) -> Path:
        payload = self.manifest.model_dump(mode="json")
        payload["integrity"] = {"manifest_checksum": self.manifest.checksum()}
        path = self.root / MANIFEST_NAME
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )
        return path

    # ------------------------------------------------------------------ ingest

    def add(self, source: Path) -> IngestResult:
        """Registra un file o l'intero contenuto supportato di una cartella."""
        source = source.expanduser()
        result = IngestResult()
        if source.is_dir():
            candidates = sorted(
                p
                for p in source.rglob("*")
                if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
            )
            skipped = sorted(
                p
                for p in source.rglob("*")
                if p.is_file() and p.suffix.lower() not in SUPPORTED_EXTENSIONS
            )
            for path in skipped:
                result.rejected.append(
                    SafetyReport(
                        path=path,
                        accepted=False,
                        reason=f"estensione non supportata ({path.suffix or 'assente'})",
                    )
                )
        else:
            candidates = [source]

        if len(candidates) > MAX_FILES:
            raise SafetyError(f"troppi file ({len(candidates)} > {MAX_FILES})")

        total = sum(f.size_bytes for f in self.manifest.files)
        for path in candidates:
            report = check_file(path, total_bytes_so_far=total)
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
        existing = {(f.filename, f.sha256) for f in self.manifest.files}
        if (path.name, checksum) in existing:
            return None

        destination = resolve_inside(self.root / SOURCES_DIR, Path(path.name))
        if destination.exists() and sha256_of(destination) != checksum:
            destination = destination.with_name(
                f"{destination.stem}-{checksum[:8]}{destination.suffix}"
            )
        shutil.copy2(path, destination)

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
        for pf in self.manifest.files:
            path = self.path_of(pf)
            if not path.is_file():
                problems.append(f"{pf.filename}: file mancante nel workspace")
                continue
            if sha256_of(path) != pf.sha256:
                problems.append(f"{pf.filename}: checksum non corrispondente")
        return problems

    def untracked_license_files(self) -> list[ProjectFile]:
        """File senza license manifest: bloccano training e redistribuzione (FR-032)."""
        return [f for f in self.manifest.files if f.license_manifest is None]


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
