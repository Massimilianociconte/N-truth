"""Tests for C1.1 provenance join utilities (fail-closed, no invented IDs)."""

from __future__ import annotations

from ntruth.task_corpora.provenance_join import (
    MIN_CONTAINMENT_SEGMENT_CHARS,
    JoinDecision,
    UpstreamCandidate,
    classify_containment_dois,
    classify_exact_candidates,
    decide_provenance,
    decision_is_fail_closed,
    doi_is_well_formed,
    normalize_caption,
)


def _cand(
    doi: str = "10.1000/a", fig: str = "1", panel: str = "2", caption: str = "x"
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
        cands = (_cand(doi="10.1000/a", panel="1"), _cand(doi="10.2000/b", panel="1"))
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
        decision = classify_containment_dois("segment text", frozenset({"10.1000/a"}))
        assert decision.result == "TIER2_SINGLE_DOI_ARTICLE"
        assert decision.granularity == "ARTICLE"
        assert decision.panel_id is None

    def test_multi_doi_containment_rejected(self) -> None:
        decision = classify_containment_dois("segment text", frozenset({"10.1000/a", "10.2000/b"}))
        assert decision.result == "UNMATCHED_MULTI_DOI"

    def test_empty_containment_is_not_evidence(self) -> None:
        decision = classify_containment_dois("segment text", frozenset())
        assert decision.result == "UNMATCHED_NO_EVIDENCE"


class TestFailClosedInvariants:
    def test_all_decisions_pass_fail_closed_check(self) -> None:
        decisions = [
            classify_exact_candidates("unique caption text here", (_cand(),)),
            classify_exact_candidates("dup caption text", (_cand(panel="1"), _cand(panel="2"))),
            classify_exact_candidates("x", (_cand(doi="10.1000/a"), _cand(doi="10.2000/b"))),
            classify_exact_candidates("no candidates at all for this long enough key", ()),
            classify_containment_dois("s", frozenset({"10.1000/a"})),
            classify_containment_dois("s", frozenset({"10.1000/a", "10.2000/b"})),
        ]
        assert all(decision_is_fail_closed(d) for d in decisions)

    def test_decisions_are_stable_across_repeated_runs(self) -> None:
        cands = (_cand(panel="9"), _cand(panel="9"))
        first = classify_exact_candidates("repeated caption", cands)
        second = classify_exact_candidates("repeated caption", cands)
        assert (
            first
            == second
            == JoinDecision("TIER2_SINGLE_DOI_ARTICLE", "ARTICLE", article_doi="10.1000/a")
        )


class TestDoiWellFormedness:
    def test_valid_dois_accepted(self) -> None:
        assert doi_is_well_formed("10.15252/embr.202153809")
        assert doi_is_well_formed("10.1000/a")

    def test_malformed_dois_rejected(self) -> None:
        for bad in (
            "",
            "doi:10.1000/a",
            "https://doi.org/10.1000/a",
            "10.1",
            "10.1/",
            "10.123",
            "10.123/",
            "11.1000/a",
            "10.1/a",
            "10.1000/a\n",  # trailing newline must not slip past the end anchor
        ):
            assert not doi_is_well_formed(bad), bad


class TestMalformedOrMissingDoi:
    def test_unique_candidate_with_malformed_doi_is_not_assigned(self) -> None:
        decision = classify_exact_candidates("unique caption", (_cand(doi="not-a-doi"),))
        assert decision.result == "UNMATCHED_NO_EVIDENCE"
        assert decision.granularity == "UNKNOWN"
        assert decision.article_doi is None and decision.panel_id is None

    def test_missing_empty_doi_is_rejected(self) -> None:
        decision = classify_exact_candidates("unique caption", (_cand(doi=""),))
        assert decision.result == "UNMATCHED_NO_EVIDENCE"
        assert decision.article_doi is None

    def test_malformed_doi_among_multiple_candidates_rejected(self) -> None:
        # One valid DOI plus one unverifiable candidate: article count unknown.
        cands = (_cand(doi="10.1000/a"), _cand(doi=""))
        decision = classify_exact_candidates("caption seen twice upstream", cands)
        assert decision.result == "UNMATCHED_MULTI_DOI"
        assert decision.article_doi is None

    def test_malformed_doi_containment_is_not_evidence(self) -> None:
        decision = classify_containment_dois("segment text", frozenset({"broken"}))
        assert decision.result == "UNMATCHED_NO_EVIDENCE"
        assert decision.article_doi is None

    def test_mixed_valid_and_malformed_containment_dois_rejected(self) -> None:
        decision = classify_containment_dois("segment text", frozenset({"10.1000/a", "broken"}))
        assert decision.result == "UNMATCHED_MULTI_DOI"
        assert decision.article_doi is None


class TestExactBeatsContainment:
    def test_exact_multi_doi_not_overridden_by_single_doi_containment(self) -> None:
        decision = decide_provenance(
            "caption shared by two articles",
            (_cand(doi="10.1000/a"), _cand(doi="10.2000/b")),
            frozenset({"10.1000/a"}),
        )
        assert decision.result == "UNMATCHED_MULTI_DOI"
        assert decision.article_doi is None

    def test_exact_unmatched_short_segment_not_overridden_by_containment(self) -> None:
        decision = decide_provenance("short", (), frozenset({"10.1000/a"}))
        assert decision.result == "UNMATCHED_SHORT_SEGMENT"
        assert decision.article_doi is None

    def test_no_exact_candidates_falls_back_to_containment(self) -> None:
        long_key = "a segment long enough to pass the containment length floor"
        decision = decide_provenance(long_key, (), frozenset({"10.1000/a"}))
        assert decision.result == "TIER2_SINGLE_DOI_ARTICLE"
        assert decision.granularity == "ARTICLE"
        assert decision.panel_id is None

    def test_exact_unique_wins_and_keeps_panel(self) -> None:
        decision = decide_provenance("unique caption text", (_cand(panel="42"),), frozenset())
        assert decision.result == "TIER1_UNIQUE_PANEL"
        assert decision.panel_id == "42"


class TestNormalizationConservatism:
    def test_unicode_line_separators_collapse_to_single_space(self) -> None:
        assert normalize_caption("a\u2028b\u2029c") == "a b c"

    def test_no_break_space_collapses_like_ascii_whitespace(self) -> None:
        assert normalize_caption("n\u00a0=\u00a06") == "n = 6"

    def test_biological_identifiers_and_symbols_preserved(self) -> None:
        raw = "LXRα and NF-κB in p53−/− mice; β-actin (n = 3, P < 0.05)"  # noqa: RUF001
        assert normalize_caption(raw) == raw

    def test_case_is_never_folded(self) -> None:
        assert normalize_caption("TAC vs tac") == "TAC vs tac"


class TestUnmatchedRemainUnmatched:
    def test_no_evidence_anywhere_keeps_record_unmatched(self) -> None:
        long_key = "a segment that matches nothing anywhere in the upstream corpus"
        decision = decide_provenance(long_key, (), frozenset())
        assert decision.result == "UNMATCHED_NO_EVIDENCE"
        assert decision.granularity == "UNKNOWN"
        assert decision.article_doi is None
        assert decision.fig_id is None
        assert decision.panel_id is None
        assert decision_is_fail_closed(decision)

    def test_article_only_decision_never_reports_panel_provenance(self) -> None:
        decision = decide_provenance(
            "ambiguous caption text", (_cand(panel="1"), _cand(panel="2")), frozenset()
        )
        assert decision.result == "TIER2_SINGLE_DOI_ARTICLE"
        assert decision.granularity == "ARTICLE"
        assert decision.panel_id is None and decision.fig_id is None
        assert decision_is_fail_closed(decision)
