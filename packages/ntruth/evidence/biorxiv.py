"""Coppie preprint->pubblicato da cache locale; nessuna chiamata di rete.

Layout cache (sotto ``local-data/evidence/``, git-ignorata)::
    biorxiv/details/<server>/<doi-slug>.json   # raw api.biorxiv.org details
    biorxiv/pubs/<doi-slug>.json               # raw api.biorxiv.org pubs
    crossref/<doi-slug>.json                   # raw api.crossref.org works
    europepmc/<doi-slug>.json                  # raw Europe PMC search
    openalex/<doi-slug>.json                   # raw api.openalex.org works
    manifest.jsonl                             # doi, source, fetched_at, sha256

Ogni record conserva il payload raw + metadati di fetch per audit.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from pydantic import Field

from ntruth.schemas.core import FrozenModel

EVIDENCE_SUBDIRS: tuple[str, ...] = (
    "biorxiv/details",
    "biorxiv/pubs",
    "crossref",
    "europepmc",
    "openalex",
)


class EvidenceCacheError(ValueError):
    """Errore fail-closed della cache di evidenza offline."""


class CachedRecord(FrozenModel):
    """Snapshot versionato di una risposta API, con checksum per audit."""

    doi: str = Field(min_length=3, max_length=300)
    source: str = Field(min_length=1, max_length=64)
    api_url: str = Field(min_length=8, max_length=2000)
    fetched_at: str = Field(min_length=8, max_length=64)
    sha256: str = Field(min_length=16, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)


class PairDiff(FrozenModel):
    """Differenze preprint vs pubblicato rilevanti per la validazione."""

    preprint_doi: str = Field(min_length=3, max_length=300)
    published_doi: str = Field(min_length=1, max_length=300)
    title_changed: bool = False
    abstract_changed: bool = False
    version_count: int = Field(default=1, ge=1)
    published_journal: str = Field(default="", max_length=500)
    notes: tuple[str, ...] = ()


class PreprintPublishedPair(FrozenModel):
    """Coppia preprint vUltima + metadati peer-reviewed, da cache."""

    preprint_doi: str = Field(min_length=3, max_length=300)
    published_doi: str = Field(min_length=1, max_length=300)
    published_journal: str = Field(default="", max_length=500)
    preprint_title: str = Field(default="", max_length=2000)
    preprint_abstract: str = Field(default="", max_length=20000)
    preprint_version: str = Field(default="", max_length=32)
    preprint_date: str = Field(default="", max_length=32)
    published_date: str = Field(default="", max_length=32)
    diff: PairDiff | None = None


def cache_key_for_doi(doi: str) -> str:
    """Slug deterministico per DOI; fail-closed su DOI vuoti o malformati."""

    cleaned = doi.strip().lower()
    if not cleaned or "/" not in cleaned:
        raise EvidenceCacheError(f"DOI non valido per la cache: {doi!r}")
    slug = re.sub(r"[^a-z0-9]+", "_", cleaned).strip("_")
    if not slug:
        raise EvidenceCacheError(f"DOI non valido per la cache: {doi!r}")
    return slug


def default_cache_dir() -> Path:
    """Directory cache locale (mai nel repository)."""

    return Path("local-data") / "evidence"


def load_cached_json(cache_dir: Path, relative: str) -> dict[str, Any]:
    """Legge un JSON dalla cache; fail-closed se assente o invalido."""

    candidate = (cache_dir / relative).resolve()
    root = cache_dir.resolve()
    if candidate != root and root not in candidate.parents:
        raise EvidenceCacheError(f"Percorso fuori dalla cache: {relative!r}")
    if not candidate.is_file():
        raise EvidenceCacheError(f"Snapshot assente in cache: {relative!r}")
    try:
        loaded = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EvidenceCacheError(f"Snapshot invalido {relative!r}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise EvidenceCacheError(f"Snapshot non oggetto: {relative!r}")
    return loaded


def _first_collection(payload: dict[str, Any]) -> dict[str, Any]:
    collection = payload.get("collection")
    if isinstance(collection, list) and collection and isinstance(collection[0], dict):
        return collection[0]
    results = payload.get("results") or payload.get("resultList", {}).get("result")
    if isinstance(results, list) and results and isinstance(results[0], dict):
        return results[0]
    message = payload.get("message")
    if isinstance(message, dict):
        return message
    return {}


def _published_doi(details: dict[str, Any], pubs: dict[str, Any]) -> str:
    candidate = str(details.get("published") or "").strip()
    if candidate and candidate != "na":
        return candidate
    return str(pubs.get("published_doi") or pubs.get("published", "") or "").strip()


def pair_from_cache(
    cache_dir: Path,
    preprint_doi: str,
    server: str = "biorxiv",
) -> PreprintPublishedPair:
    """Ricostruisce la coppia preprint->pubblicato solo da snapshot locali."""

    slug = cache_key_for_doi(preprint_doi)
    details_doc = load_cached_json(cache_dir, f"biorxiv/details/{server}/{slug}.json")
    pubs_doc = load_cached_json(cache_dir, f"biorxiv/pubs/{slug}.json")
    details = _first_collection(details_doc.get("payload", details_doc))
    pubs = _first_collection(pubs_doc.get("payload", pubs_doc))
    published = _published_doi(details, pubs)
    if not published or published == "na":
        raise EvidenceCacheError(
            f"Nessun DOI pubblicato noto per {preprint_doi!r}: la coppia "
            "preprint-vs-pubblicato non esiste ancora."
        )
    return PreprintPublishedPair(
        preprint_doi=preprint_doi.strip().lower(),
        published_doi=published,
        published_journal=str(pubs.get("published_journal") or details.get("journal") or ""),
        preprint_title=str(details.get("title") or pubs.get("title") or ""),
        preprint_abstract=str(details.get("abstract") or ""),
        preprint_version=str(details.get("version") or ""),
        preprint_date=str(details.get("date") or ""),
        published_date=str(pubs.get("published_date") or ""),
    )


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def diff_pair(pair: PreprintPublishedPair, published_abstract: str = "") -> PreprintPublishedPair:
    """Confronta abstract/titolo preprint vs pubblicato (solo stringhe locali)."""

    published_norm = _normalize_text(published_abstract)
    preprint_norm = _normalize_text(pair.preprint_abstract)
    try:
        version_count = max(1, int(pair.preprint_version or "1"))
    except ValueError:
        version_count = 1
    notes: list[str] = []
    if published_abstract and published_norm != preprint_norm:
        notes.append("abstract modificato tra preprint e versione pubblicata")
    if version_count > 1:
        notes.append(f"{version_count} versioni preprint prima della pubblicazione")
    diff = PairDiff(
        preprint_doi=pair.preprint_doi,
        published_doi=pair.published_doi,
        title_changed=False,
        abstract_changed=bool(published_abstract and published_norm != preprint_norm),
        version_count=version_count,
        published_journal=pair.published_journal,
        notes=tuple(notes),
    )
    return pair.model_copy(update={"diff": diff})


def record_checksum(payload: dict[str, Any]) -> str:
    """Checksum canonica di un payload per manifest.jsonl."""

    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "EVIDENCE_SUBDIRS",
    "CachedRecord",
    "EvidenceCacheError",
    "PairDiff",
    "PreprintPublishedPair",
    "cache_key_for_doi",
    "default_cache_dir",
    "diff_pair",
    "load_cached_json",
    "pair_from_cache",
    "record_checksum",
]
