"""Supporto offline per coppie preprint vs pubblicato (bioRxiv/medRxiv).

Questo package non tocca mai la rete: legge solo snapshot JSON scaricati
esplicitamente con ``scripts/fetch_biorxiv.py`` in ``local-data/evidence/``
(cache versionata, mai nel repository). Confronta metadati preprint vs
versione peer-reviewed per misurare se N-Truth rileva a monte le stesse
criticita sollevate dai revisori (correzione di N, chiarimenti sul disegno).
"""

from ntruth.evidence.biorxiv import (
    CachedRecord,
    PreprintPublishedPair,
    cache_key_for_doi,
    diff_pair,
    load_cached_json,
    pair_from_cache,
)

__all__ = [
    "CachedRecord",
    "PreprintPublishedPair",
    "cache_key_for_doi",
    "diff_pair",
    "load_cached_json",
    "pair_from_cache",
]
