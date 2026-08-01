"""Pubblicazione atomica di directory di artefatti append-only."""

from __future__ import annotations

import secrets
import shutil
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path


class ArtifactPublicationError(RuntimeError):
    """Una revisione non puo essere pubblicata senza sovrascrivere dati esistenti."""


def unique_run_path(output_root: Path) -> tuple[str, Path]:
    """Restituisce un percorso run non esistente sotto ``<out>/runs``.

    L'ID e deliberatamente operativo e non entra nei checksum scientifici. La
    directory viene poi riservata da :func:`staged_directory` con ``mkdir``
    esclusivo, per cui due processi non condividono mai lo stesso staging.
    """

    runs_root = output_root.expanduser().resolve() / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    for _ in range(32):
        run_id = secrets.token_hex(16)
        destination = runs_root / run_id
        if not destination.exists():
            return run_id, destination
    raise ArtifactPublicationError("impossibile allocare un ID di run univoco")


@contextmanager
def staged_directory(destination: Path) -> Iterator[Path]:
    """Costruisce una directory privata e la pubblica con un solo rename.

    ``destination`` non viene mai sostituita. Se la costruzione fallisce, lo
    staging viene eliminato e nessun artefatto parziale diventa visibile.
    """

    destination = destination.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise ArtifactPublicationError(f"destinazione gia pubblicata: {destination}")

    staging = destination.parent / f".{destination.name}.{secrets.token_hex(8)}.tmp"
    try:
        staging.mkdir(exist_ok=False)
    except FileExistsError as exc:  # pragma: no cover - token casuale a 64 bit
        raise ArtifactPublicationError(f"collisione nella directory temporanea: {staging}") from exc

    published = False
    try:
        yield staging
        if destination.exists():
            raise ArtifactPublicationError(
                f"la destinazione e comparsa durante la pubblicazione: {destination}"
            )
        staging.rename(destination)
        published = True
    finally:
        if not published and staging.exists():
            shutil.rmtree(staging)


def remap_artifact_paths(
    artifacts: Mapping[str, Path],
    *,
    source_root: Path,
    destination_root: Path,
) -> dict[str, Path]:
    """Rimappa percorsi dopo il rename atomico, rifiutando path esterni."""

    source_root = source_root.resolve()
    destination_root = destination_root.resolve()
    remapped: dict[str, Path] = {}
    for label, raw_path in artifacts.items():
        path = raw_path.resolve()
        try:
            relative = path.relative_to(source_root)
        except ValueError as exc:
            raise ArtifactPublicationError(
                f"artefatto '{label}' fuori dallo staging: {path}"
            ) from exc
        remapped[label] = destination_root / relative
    return remapped


__all__ = [
    "ArtifactPublicationError",
    "remap_artifact_paths",
    "staged_directory",
    "unique_run_path",
]
