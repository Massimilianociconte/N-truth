"""Tests for C1.1 provenance join utilities (fail-closed, no invented IDs)."""

from __future__ import annotations

from ntruth.task_corpora.provenance_join import (
    MIN_CONTAINMENT_SEGMENT_CHARS,
    JoinDecision,
    UpstreamCandidate,
    classify_containment_dois,
    classify_exact_candidates,
    decision_is_fail_closed,
    normalize_caption,
)


def _cand(
    doi: str = "10.1/a", fig: str = "1", panel: str = "2", caption: str = "x"
) -> UpstreamCandidate:
    return UpstreamCandidate(article_doi=doi, fig_id=fig, panel_id=panel, caption=caption)


class TestNormalization:
    def test_whitespace_collapse_is_deterministic(self) -> None:
        raw = "  Figure\t1B-D  left\nventricle. "
        once = normalize_caption(raw)
        again = normalize_caption(raw)
        assert once == again == "Figure 1B-D left ventricle."

    def test_normalization_does_not_fold_case_or_punctuation(self) -> None:
        assert normalize_caption("LXRα-Tg; n = 6") == "LXRα-Tg; n = 6"  # noqa: RUF001


class TestExactCandidateClassification:
    def test_unique_candidate_yields_panel_provenance(self) -> None:
        decision = classify_exact_candidates("western blot of x", (_cand(panel="76973"),))
        assert decision.result == "TIER1_UNIQUE_PANEL"
        assert decision.granularity == "PANEL"
        assert decision.panel_id == "76973"
        assert decision_is_fail_closed(decision)

    def test_duplicate_text_within_one_article_never_assigns_panel(self) -> None:
        cands = (_cand(panel="100"), _cand(panel="101"))
        decision = classify_exact_candidates("identical caption text used twice", cands)
        assert decision.result == "TIER2_SINGLE_DOI_ARTICLE"
        assert decision.granularity == "ARTICLE"
        assert decision.panel_id is None
        assert decision_is_fail_closed(decision)

    def test_no_first_match_behaviour_across_articles(self) -> None:
        cands = (_cand(doi="10.1/a", panel="1"), _cand(doi="10.2/b", panel="1"))
        decision = classify_exact_candidates("caption present in two articles", cands)
        assert decision.result == "UNMATCHED_MULTI_DOI"
        assert decision.article_doi is None
        assert decision.panel_id is None

    def test_missing_candidates_yield_unknown_not_invented_ids(self) -> None:
        key = "a segment that is long enough to be considered for containment scans"
        decision = classify_exact_candidates(key, ())
        assert decision.result == "UNMATCHED_NO_EVIDENCE"
        assert decision.granularity == "UNKNOWN"
        assert decision.article_doi is None and decision.panel_id is None

    def test_short_segments_reported_separately(self) -> None:
        key = "short"
        assert len(key) < MIN_CONTAINMENT_SEGMENT_CHARS
        decision = classify_exact_candidates(key, ())
        assert decision.result == "UNMATCHED_SHORT_SEGMENT"


class TestContainmentClassification:
    def test_single_doi_containment_is_article_level_only(self) -> None:
        decision = classify_containment_dois("segment text", frozenset({"10.1/a"}))
        assert decision.result == "TIER2_SINGLE_DOI_ARTICLE"
        assert decision.granularity == "ARTICLE"
        assert decision.panel_id is None

    def test_multi_doi_containment_rejected(self) -> None:
        decision = classify_containment_dois("segment text", frozenset({"10.1/a", "10.2/b"}))
        assert decision.result == "UNMATCHED_MULTI_DOI"

    def test_empty_containment_is_not_evidence(self) -> None:
        decision = classify_containment_dois("segment text", frozenset())
        assert decision.result == "UNMATCHED_NO_EVIDENCE"


class TestFailClosedInvariants:
    def test_all_decisions_pass_fail_closed_check(self) -> None:
        decisions = [
            classify_exact_candidates("unique caption text here", (_cand(),)),
            classify_exact_candidates("dup caption text", (_cand(panel="1"), _cand(panel="2"))),
            classify_exact_candidates("x", (_cand(doi="10.1/a"), _cand(doi="10.2/b"))),
            classify_exact_candidates("no candidates at all for this long enough key", ()),
            classify_containment_dois("s", frozenset({"10.1/a"})),
            classify_containment_dois("s", frozenset({"10.1/a", "10.2/b"})),
        ]
        assert all(decision_is_fail_closed(d) for d in decisions)

    def test_decisions_are_stable_across_repeated_runs(self) -> None:
        cands = (_cand(panel="9"), _cand(panel="9"))
        first = classify_exact_candidates("repeated caption", cands)
        second = classify_exact_candidates("repeated caption", cands)
        assert (
            first
            == second
            == JoinDecision("TIER2_SINGLE_DOI_ARTICLE", "ARTICLE", article_doi="10.1/a")
        )
