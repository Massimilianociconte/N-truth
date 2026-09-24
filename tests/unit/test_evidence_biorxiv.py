"""Cache offline bioRxiv: coppie preprint->pubblicato senza rete."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ntruth.evidence.biorxiv import (
    EvidenceCacheError,
    cache_key_for_doi,
    diff_pair,
    load_cached_json,
    pair_from_cache,
)


def _write_envelope(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"doi": "10.1101/x", "payload": payload}, ensure_ascii=False),
        encoding="utf-8",
    )


def test_pair_from_cache_links_preprint_to_published(tmp_path: Path) -> None:
    doi = "10.1101/2021.04.29.21256344"
    slug = cache_key_for_doi(doi)
    _write_envelope(
        tmp_path / f"biorxiv/details/medrxiv/{slug}.json",
        {
            "collection": [
                {
                    "doi": doi,
                    "title": "Preprint title",
                    "abstract": "Preprint abstract v1.",
                    "version": "1",
                    "date": "2021-04-30",
                    "published": "10.1371/journal.pone.0256482",
                }
            ]
        },
    )
    _write_envelope(
        tmp_path / f"biorxiv/pubs/{slug}.json",
        {
            "collection": [
                {
                    "preprint_doi": doi,
                    "published_doi": "10.1371/journal.pone.0256482",
                    "published_journal": "PLOS ONE",
                    "published_date": "2021-08-27",
                }
            ]
        },
    )
    pair = pair_from_cache(tmp_path, doi, server="medrxiv")
    assert pair.published_doi == "10.1371/journal.pone.0256482"
    assert pair.published_journal == "PLOS ONE"
    differed = diff_pair(pair, published_abstract="Final abstract, revised after review.")
    assert differed.diff is not None
    assert differed.diff.abstract_changed is True


def test_pair_without_published_doi_is_fail_closed(tmp_path: Path) -> None:
    doi = "10.1101/9999.99.99999999"
    slug = cache_key_for_doi(doi)
    _write_envelope(
        tmp_path / f"biorxiv/details/biorxiv/{slug}.json",
        {"collection": [{"doi": doi, "published": "na"}]},
    )
    _write_envelope(tmp_path / f"biorxiv/pubs/{slug}.json", {"collection": [{}]})
    with pytest.raises(EvidenceCacheError, match="Nessun DOI pubblicato"):
        pair_from_cache(tmp_path, doi, server="biorxiv")


def test_cache_rejects_missing_and_escaping_paths(tmp_path: Path) -> None:
    with pytest.raises(EvidenceCacheError, match="assente"):
        load_cached_json(tmp_path, "biorxiv/pubs/missing.json")
    with pytest.raises(EvidenceCacheError, match="fuori dalla cache"):
        load_cached_json(tmp_path, "../escape.json")
    with pytest.raises(EvidenceCacheError, match="DOI non valido"):
        cache_key_for_doi("not-a-doi")
