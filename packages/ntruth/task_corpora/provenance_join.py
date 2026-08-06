"""C1.1 provenance join utilities (investigation-only).

Pure, deterministic functions behind the C1.1 SourceData document-provenance
feasibility scripts. No canonical dataset file is ever written by this module;
it only classifies join candidates fail-closed.

Rules encoded here (from the C1.1 authorisation):
  - no fuzzy similarity matching;
  - no first-match behaviour: multiply matched records are never assigned;
  - multi-DOI candidate sets are always rejected;
  - single-DOI ambiguity may only yield ARTICLE-level provenance, never panel;
  - missing identifiers are reported, never invented;
  - malformed or missing DOI values are never used as article provenance;
  - containment evidence is consulted only when no exact candidate exists and can
    never override an exact-tier decision.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Literal

_WS: Final = re.compile(r"\s+")
_DOI: Final = re.compile(r"^10\.\d{4,9}/\S+$")

MIN_CONTAINMENT_SEGMENT_CHARS: Final = 40

ProvenanceGranularity = Literal[
    "ARTICLE", "FIGURE", "PANEL", "SEGMENT", "RECORD_FALLBACK", "UNKNOWN"
]

TierResult = Literal[
    "TIER1_UNIQUE_PANEL",
    "TIER2_SINGLE_DOI_ARTICLE",
    "UNMATCHED_MULTI_DOI",
    "UNMATCHED_NO_EVIDENCE",
    "UNMATCHED_SHORT_SEGMENT",
]


@dataclass(frozen=True)
class UpstreamCandidate:
    article_doi: str
    fig_id: str
    panel_id: str
    caption: str


@dataclass(frozen=True)
class JoinDecision:
    result: TierResult
    granularity: ProvenanceGranularity
    article_doi: str | None = None
    fig_id: str | None = None
    panel_id: str | None = None


def normalize_caption(text: str) -> str:
    """Whitespace-only canonical normalization (documented and deterministic).

    Unicode whitespace (incl. U+00A0, U+2028, U+2029) collapses to a single
    ASCII space. No case folding, no punctuation or symbol changes: case,
    punctuation and biological identifiers are preserved, and the complete
    original text remains authoritative elsewhere.
    """
    return _WS.sub(" ", text).strip()


def doi_is_well_formed(value: str) -> bool:
    """Conservative DOI shape check: registrant prefix 10.NNNN plus suffix."""
    return _DOI.match(value) is not None


def classify_exact_candidates(
    local_key: str, candidates: tuple[UpstreamCandidate, ...]
) -> JoinDecision:
    """Fail-closed classification of exact normalized-text candidates."""
    if len(candidates) == 0:
        if len(local_key) < MIN_CONTAINMENT_SEGMENT_CHARS:
            return JoinDecision("UNMATCHED_SHORT_SEGMENT", "UNKNOWN")
        return JoinDecision("UNMATCHED_NO_EVIDENCE", "UNKNOWN")
    if any(not doi_is_well_formed(c.article_doi) for c in candidates):
        # Unverifiable article identity: neither panel nor article counts can
        # be established, so nothing may be assigned.
        if len(candidates) == 1:
            return JoinDecision("UNMATCHED_NO_EVIDENCE", "UNKNOWN")
        return JoinDecision("UNMATCHED_MULTI_DOI", "UNKNOWN")
    if len(candidates) == 1:
        cand = candidates[0]
        return JoinDecision(
            "TIER1_UNIQUE_PANEL",
            "PANEL",
            article_doi=cand.article_doi,
            fig_id=cand.fig_id,
            panel_id=cand.panel_id,
        )
    dois = {c.article_doi for c in candidates}
    if len(dois) == 1:
        # Ambiguous panel within one article: article-level provenance only.
        return JoinDecision("TIER2_SINGLE_DOI_ARTICLE", "ARTICLE", article_doi=next(iter(dois)))
    return JoinDecision("UNMATCHED_MULTI_DOI", "UNKNOWN")


def classify_containment_dois(local_key: str, containing_dois: frozenset[str]) -> JoinDecision:
    """Fail-closed classification after a verbatim containment scan."""
    malformed = {d for d in containing_dois if not doi_is_well_formed(d)}
    usable = containing_dois - malformed
    if not usable:
        return JoinDecision("UNMATCHED_NO_EVIDENCE", "UNKNOWN")
    if malformed:
        # Article count cannot be established while any source is unverifiable.
        return JoinDecision("UNMATCHED_MULTI_DOI", "UNKNOWN")
    if len(usable) == 1:
        return JoinDecision("TIER2_SINGLE_DOI_ARTICLE", "ARTICLE", article_doi=next(iter(usable)))
    return JoinDecision("UNMATCHED_MULTI_DOI", "UNKNOWN")


def decide_provenance(
    local_key: str,
    exact_candidates: tuple[UpstreamCandidate, ...],
    containing_dois: frozenset[str],
) -> JoinDecision:
    """Tiered decision with strict precedence: exact evidence always wins.

    Containment is consulted only when the exact tier found no candidate at all
    and the segment is long enough to support containment evidence; it can never
    override an exact-tier decision, including exact-tier rejections.
    """
    exact = classify_exact_candidates(local_key, exact_candidates)
    if exact_candidates or exact.result == "UNMATCHED_SHORT_SEGMENT":
        return exact
    return classify_containment_dois(local_key, containing_dois)


def decision_is_fail_closed(decision: JoinDecision) -> bool:
    """Invariants used by tests: never invent IDs, never leak granularity."""
    if decision.result == "TIER1_UNIQUE_PANEL":
        return bool(decision.article_doi and decision.fig_id and decision.panel_id)
    if decision.result == "TIER2_SINGLE_DOI_ARTICLE":
        return decision.granularity == "ARTICLE" and decision.panel_id is None
    return decision.granularity == "UNKNOWN" and decision.article_doi is None
