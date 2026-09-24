"""Fetch esplicito bioRxiv/medRxiv + Crossref/EuropePMC/OpenAlex (solo stdlib).

Default ``--cache-only``: legge la cache locale e non tocca la rete.
Con ``--refresh`` esegue GET esplicite, throttled, con fallback host e
manifest.jsonl per audit. Mai chiamato da core/API/CLI in automatico.

Esempi:
    python scripts/fetch_biorxiv.py --doi 10.1101/2021.04.29.21256344 \\
        --server medrxiv --sources details,pubs --cache-dir local-data/evidence
    python scripts/fetch_biorxiv.py --doi 10.1101/2021.04.29.21256344 \\
        --server medrxiv --refresh --mailto tuamail@dominio.it
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages"))

from ntruth.evidence.biorxiv import (
    EVIDENCE_SUBDIRS,
    cache_key_for_doi,
    record_checksum,
)

BIORXIV_HOSTS = ("https://api.biorxiv.org", "https://api.medrxiv.org")
USER_AGENT = "N-Truth/0.1 (offline-first evidence cache; +mailto:{mailto})"


def _slug(doi: str) -> str:
    return cache_key_for_doi(doi)


def _get(url: str, mailto: str, timeout: int = 20) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT.format(mailto=mailto or "unknown@localhost")},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            time.sleep(5)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read().decode("utf-8")
        raise


def _fetch_with_fallback(path: str, mailto: str) -> tuple[str, str]:
    """GET con fallback tra i due host; ritorna (body, url). Fail-closed."""

    last_error: Exception | None = None
    for host in BIORXIV_HOSTS:
        url = host + path
        try:
            body = _get(url, mailto)
        except Exception as exc:
            last_error = exc
            continue
        if body.strip():
            return body, url
        last_error = ValueError(f"risposta vuota da {url}")
        time.sleep(1)
    raise ValueError(f"fetch fallito su entrambi gli host per {path}: {last_error}")


def _store(cache_dir: Path, relative: str, doi: str, source: str, url: str, raw: str) -> Path:
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise ValueError(f"risposta non JSON da {url}: {exc}") from exc
    slug = _slug(doi)
    target = cache_dir / relative.format(slug=slug)
    target.parent.mkdir(parents=True, exist_ok=True)
    fetched_at = datetime.now(UTC).isoformat()
    checksum = record_checksum(payload if isinstance(payload, dict) else {"data": payload})
    envelope = {
        "doi": doi.strip().lower(),
        "source": source,
        "api_url": url,
        "fetched_at": fetched_at,
        "sha256": checksum,
        "payload": payload,
    }
    target.write_text(
        json.dumps(envelope, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    manifest = cache_dir / "manifest.jsonl"
    with manifest.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "doi": doi.strip().lower(),
                    "source": source,
                    "fetched_at": fetched_at,
                    "sha256": checksum,
                    "api_url": url,
                    "path": relative.format(slug=slug),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        )
    return target


def fetch_details(doi: str, server: str, cache_dir: Path, mailto: str) -> Path:
    """Snapshot details per DOI preprint (prova entrambi gli host)."""

    path = f"/details/{server}/{urllib.parse.quote(doi, safe='')}/na/json"
    body, url = _fetch_with_fallback(path, mailto)
    return _store(cache_dir, f"biorxiv/details/{server}/{{slug}}.json", doi, "details", url, body)


def fetch_pubs(doi: str, cache_dir: Path, mailto: str) -> Path:
    """Snapshot pubs (accetta DOI preprint o pubblicato, reverse-lookup)."""

    path = f"/pubs/biorxiv/{urllib.parse.quote(doi, safe='')}/na/json"
    try:
        body, url = _fetch_with_fallback(path, mailto)
    except ValueError:
        path = f"/pubs/medrxiv/{urllib.parse.quote(doi, safe='')}/na/json"
        body, url = _fetch_with_fallback(path, mailto)
    return _store(cache_dir, "biorxiv/pubs/{slug}.json", doi, "pubs", url, body)


def fetch_crossref(doi: str, cache_dir: Path, mailto: str) -> Path:
    """Metadati Crossref del DOI pubblicato (mailto = polite pool)."""

    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi, safe='')}"
    body = _get(url, mailto)
    return _store(cache_dir, "crossref/{slug}.json", doi, "crossref", url, body)


def fetch_europepmc(doi: str, cache_dir: Path, mailto: str) -> Path:
    """Ricerca Europe PMC per DOI (core, fair-use sequenziale)."""

    query = urllib.parse.quote(f'DOI:"{doi}"', safe="")
    url = (
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        f"?query={query}&format=json&resultType=core"
    )
    body = _get(url, mailto)
    return _store(cache_dir, "europepmc/{slug}.json", doi, "europepmc", url, body)


def fetch_openalex(doi: str, cache_dir: Path, mailto: str) -> Path:
    """Record OpenAlex per DOI (CC0, select minimale)."""

    select = "id,doi,title,publication_year,primary_location,open_access,is_retracted"
    url = f"https://api.openalex.org/works/https://doi.org/{urllib.parse.quote(doi, safe='')}?select={select}"
    body = _get(url, mailto)
    return _store(cache_dir, "openalex/{slug}.json", doi, "openalex", url, body)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--doi", required=True, help="DOI preprint o pubblicato.")
    parser.add_argument("--server", default="biorxiv", choices=("biorxiv", "medrxiv"))
    parser.add_argument(
        "--sources",
        default="details,pubs",
        help="details,pubs,crossref-published,europepmc-published,openalex-published",
    )
    parser.add_argument("--cache-dir", type=Path, default=Path("local-data") / "evidence")
    parser.add_argument("--refresh", action="store_true", help="Tocca la rete (throttled).")
    parser.add_argument("--mailto", default="", help="Email per il polite pool Crossref.")
    parser.add_argument("--published-doi", default="", help="DOI pubblicato se gia noto.")
    args = parser.parse_args()

    cache_dir: Path = args.cache_dir
    for subdir in EVIDENCE_SUBDIRS:
        (cache_dir / subdir / args.server).mkdir(parents=True, exist_ok=True)
    sources = [item.strip() for item in args.sources.split(",") if item.strip()]
    if not args.refresh:
        missing = []
        slug = _slug(args.doi)
        for source in sources:
            candidates = sorted(cache_dir.rglob(f"{slug}.json"))
            if not candidates:
                missing.append(source)
        if missing:
            print(f"cache-only: snapshot assenti per {missing}; usare --refresh", flush=True)
            return 1
        print(f"cache-only: snapshot presenti per {args.doi}", flush=True)
        return 0

    stored: list[str] = []
    for source in sources:
        if source == "details":
            stored.append(str(fetch_details(args.doi, args.server, cache_dir, args.mailto)))
        elif source == "pubs":
            stored.append(str(fetch_pubs(args.doi, cache_dir, args.mailto)))
        elif source in {"crossref-published", "europepmc-published", "openalex-published"}:
            published = args.published_doi or args.doi
            if source == "crossref-published":
                stored.append(str(fetch_crossref(published, cache_dir, args.mailto)))
            elif source == "europepmc-published":
                stored.append(str(fetch_europepmc(published, cache_dir, args.mailto)))
            else:
                stored.append(str(fetch_openalex(published, cache_dir, args.mailto)))
        else:
            print(f"sorgente sconosciuta: {source}", flush=True)
            return 2
        time.sleep(1)
    print(json.dumps({"stored": stored}, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
