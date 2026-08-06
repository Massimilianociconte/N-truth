"""Tests for the SourceData provenance method reconciliation harness.

Toy-scale tests exercise the census, Method B classification, delta
relations, audit selection and adjudication logic deterministically.
Real-scale tests are guarded behind the external dataset volume and assert
ONLY internal consistency (sums, vocabularies, field contracts) — never
historical report figures, which the reconciliation is forbidden to use as
expected constants.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "sourcedata_provenance_method_reconciliation",
    Path(__file__).resolve().parents[3]
    / "scripts/task_corpora/sourcedata_provenance_method_reconciliation.py",
)
assert _SPEC is not None and _SPEC.loader is not None
recon = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = recon  # dataclass introspection needs sys.modules entry
_SPEC.loader.exec_module(recon)

REAL_CANON = Path("/Volumes/FLASH128/N-Truth-Datasets/task_corpora/entity_roles/sourcedata/v2.0.3")
REAL_RAW = Path("/Volumes/FLASH128/N-Truth-Datasets/raw/sourcedata/v2.0.3/roles_multi")
REAL_ARCHIVE = REAL_CANON / "provenance" / "source_data_xml_v2.0.3.tar.gz"
REAL_AVAILABLE = REAL_ARCHIVE.exists() and (REAL_CANON / "train.jsonl").exists()

TOY_ARTICLE_A = """<article doi="10.1000/toy.a">
<fig id="fig1"><label>Figure 1</label>
<sd-panel panel_id="p1"><p>(A) alpha.</p></sd-panel>
<sd-panel panel_id="p2"><p>(B) beta.</p></sd-panel>
</fig>
<fig id="fig2"><p>(C) gamma.</p></fig>
<fig id="fig3">
<sd-panel panel_id="p3"><p>(E) eps. <sd-tag text="protX" role="component">protX</sd-tag></p></sd-panel>
<sd-panel panel_id="p4"><p>(E) eps. <sd-tag text="pro" role="intervention">pro</sd-tag><sd-tag text="tX" role="intervention">tX</sd-tag></p></sd-panel>
</fig>
</article>
"""

TOY_ARTICLE_B = """<article doi="10.1000/toy.b">
<fig id="fig1"><sd-panel panel_id="p1"><p>(A) alpha.</p></sd-panel></fig>
</article>
"""

TOY_ARTICLE_C = """<article doi="10.1000/toy.c">
<fig id="fig1">
<sd-panel panel_id="p1"><p>(D) delta.</p></sd-panel>
<sd-panel panel_id="p2"><p>(D) delta.</p></sd-panel>
</fig>
</article>
"""


def _toy_xml_dir(tmp_path: Path) -> Path:
    xml = tmp_path / "xml"
    xml.mkdir()
    (xml / "a.xml").write_text(TOY_ARTICLE_A, encoding="utf-8")
    (xml / "b.xml").write_text(TOY_ARTICLE_B, encoding="utf-8")
    (xml / "c.xml").write_text(TOY_ARTICLE_C, encoding="utf-8")
    return xml


def _raw_line(text: str, words: list[str] | None = None, labels: list[str] | None = None) -> str:
    n = len(words) if words else 1
    return json.dumps(
        {
            "words": words or [text],
            "labels": labels or ["O"] * n,
            "is_category": [False] * n,
            "text": text,
        }
    )


def _toy_raw_dir(tmp_path: Path, rows: dict[str, list[str]]) -> Path:
    raw = tmp_path / "raw"
    raw.mkdir()
    for part in ("train", "validation", "test"):
        (raw / f"{part}.jsonl").write_text(
            "".join(line + "\n" for line in rows.get(part, [])), encoding="utf-8"
        )
    return raw


class TestCensus:
    def test_toy_census_statistics_and_hypothesis_arithmetic(self, tmp_path: Path) -> None:
        census = recon.run_census(_toy_xml_dir(tmp_path))
        stats = census.stats
        assert stats["xml_file_count"] == 3
        assert stats["valid_article_doi_count"] == 3
        assert stats["figure_count"] == 5
        assert stats["figures_with_sd_panel"] == 4
        assert stats["figures_without_sd_panel"] == 1
        assert stats["explicit_sd_panel_count"] == 7
        assert stats["total_matchable_units"] == 8
        assert stats["duplicate_normalized_caption_keys"] == 3  # alpha, delta, eps
        # The hypothesis arithmetic must hold by construction, measured:
        hyp = census.hypothesis
        assert hyp["measured_panels_plus_no_panel_equals_total"] is True
        assert (
            hyp["measured_explicit_panels"] + hyp["measured_no_panel_figure_units"]
            == hyp["measured_total_matchable_units"]
        )


class TestMethodBReconstruction:
    def test_toy_classification_buckets(self, tmp_path: Path) -> None:
        raw = _toy_raw_dir(
            tmp_path,
            {
                "train": [
                    _raw_line("(A) alpha."),  # ambiguous multi-DOI (a + b)
                    _raw_line("(B) beta."),  # S3 unique panel
                    _raw_line("(C) gamma."),  # S3 unique figure unit
                    _raw_line("(D) delta."),  # ambiguous single DOI
                    _raw_line("no counterpart anywhere"),  # unmatched
                    _raw_line(
                        "(E) eps. protX",
                        words=["(E)", "eps.", "protX"],
                        labels=["O", "O", "B-MEASURED_VAR"],
                    ),  # S4 tuple disambiguates panel p3
                ],
            },
        )
        out = tmp_path / "method_b.jsonl"
        summary = recon.run_method_b(xml_dir=_toy_xml_dir(tmp_path), raw_dir=raw, out_path=out)
        tiers = summary["tier_counts"]
        assert tiers["S3_UNIQUE_UNIT"] == 2
        assert tiers["AMBIGUOUS_SINGLE_DOI"] == 1
        assert tiers["AMBIGUOUS_MULTI_DOI"] == 1
        assert tiers["UNMATCHED_NO_ASSET_TEXT"] == 1
        assert tiers["S4_UNIQUE_ANNOTATION_TUPLE"] == 1
        assert summary["rows"] == 6
        rows = {r["source_row_index"]: r for r in map(json.loads, out.read_text().splitlines())}
        assert rows[1]["panel_id"] == "p2"
        assert rows[2]["panel_id"] is None  # figure unit: no invented panel
        assert rows[3]["article_doi"] == "10.1000/toy.c"
        assert rows[3]["panel_id"] is None
        assert rows[5]["label_assisted"] is True
        assert rows[5]["panel_id"] == "p3"

    def test_record_side_uniqueness_is_enforced(self, tmp_path: Path) -> None:
        raw = _toy_raw_dir(
            tmp_path,
            {"train": [_raw_line("(B) beta."), _raw_line("(B) beta.")]},
        )
        out = tmp_path / "method_b.jsonl"
        summary = recon.run_method_b(xml_dir=_toy_xml_dir(tmp_path), raw_dir=raw, out_path=out)
        # Two records share one unique-unit key: neither may be emitted as S3.
        assert summary["tier_counts"].get("S3_UNIQUE_UNIT", 0) == 0
        assert summary["tier_counts"]["AMBIGUOUS_SINGLE_DOI"] == 2


class TestDeltaRelations:
    def _a(self, **over: Any) -> dict:
        base = {
            "provenance_tier": "TIER_1_PANEL_UNIQUE",
            "granularity": "PANEL",
            "article_doi": "10.1000/x",
            "figure_id": "fig1",
            "panel_id": "p1",
            "match_basis": "deterministic exact unique-panel assignment",
        }
        base.update(over)
        return base

    def _b(self, **over: Any) -> dict:
        base = {
            "method_b_tier": "S3_UNIQUE_UNIT",
            "article_doi": "10.1000/x",
            "figure_id": "fig1",
            "panel_id": "p1",
            "match_basis": "exact_canonical_text_unique_unit",
            "label_assisted": False,
        }
        base.update(over)
        return base

    def test_relation_vocabulary_is_closed(self) -> None:
        assert recon.classify_relation(self._a(), self._b()) == "IDENTICAL"
        assert {
            "IDENTICAL",
            "SAME_ARTICLE_DIFFERENT_GRANULARITY",
            "METHOD_A_ONLY",
            "METHOD_B_ONLY",
            "CONFLICTING_ARTICLE",
            "CONFLICTING_FIGURE",
            "CONFLICTING_PANEL",
            "BOTH_FALLBACK",
        } == recon.ALLOWED_RELATIONS

    def test_conflicts_detected(self) -> None:
        assert (
            recon.classify_relation(self._a(), self._b(article_doi="10.1000/y"))
            == "CONFLICTING_ARTICLE"
        )
        assert recon.classify_relation(self._a(), self._b(figure_id="fig9")) == "CONFLICTING_FIGURE"
        assert recon.classify_relation(self._a(), self._b(panel_id="p9")) == "CONFLICTING_PANEL"

    def test_one_sided_and_fallback_relations(self) -> None:
        fallback_a = self._a(
            provenance_tier="RECORD_FALLBACK",
            granularity="RECORD_FALLBACK",
            article_doi=None,
            figure_id=None,
            panel_id=None,
            match_basis=None,
        )
        assert recon.classify_relation(fallback_a, self._b()) == "METHOD_B_ONLY"
        assert (
            recon.classify_relation(self._a(), self._b(method_b_tier="UNMATCHED_NO_ASSET_TEXT"))
            == "METHOD_A_ONLY"
        )
        assert (
            recon.classify_relation(fallback_a, self._b(method_b_tier="UNMATCHED_NO_ASSET_TEXT"))
            == "BOTH_FALLBACK"
        )

    def test_granularity_delta_same_article(self) -> None:
        article_b = self._b(method_b_tier="AMBIGUOUS_SINGLE_DOI", panel_id=None, figure_id=None)
        assert recon.classify_relation(self._a(), article_b) == "SAME_ARTICLE_DIFFERENT_GRANULARITY"

    def test_delta_reason_taxonomy(self) -> None:
        reason = recon._delta_reason(self._a(), self._b(label_assisted=True), "METHOD_B_ONLY")
        assert reason == "label_assisted_tuple"
        assert reason in recon.METHOD_B_ONLY_REASONS
        reason = recon._delta_reason(self._a(), self._b(), "METHOD_B_ONLY")
        assert reason == "caption_parser_difference"
        assert reason in recon.METHOD_B_ONLY_REASONS


class TestAdjudication:
    def _delta(self, relations: dict[str, int]) -> dict:
        return {"relations": relations, "delta_reasons": {}, "method_b_only_reasons": {}}

    def _b_summary(self, s4: int = 0) -> dict:
        return {"tier_counts": {"S4_UNIQUE_ANNOTATION_TUPLE": s4}}

    def test_conflicts_force_human_adjudication(self) -> None:
        out = recon.adjudicate(
            self._delta({"CONFLICTING_ARTICLE": 1}),
            self._b_summary(),
            dual_run_byte_identical=True,
        )
        assert out["outcome"] == "METHODS_CONFLICT_REQUIRES_HUMAN_ADJUDICATION"

    def test_without_determinism_proof_insufficient(self) -> None:
        out = recon.adjudicate(
            self._delta({"METHOD_B_ONLY": 5}), self._b_summary(), dual_run_byte_identical=False
        )
        assert out["outcome"] == "INSUFFICIENT_EVIDENCE"

    def test_strict_superset_confirms_label_independent_b(self) -> None:
        out = recon.adjudicate(
            self._delta({"METHOD_B_ONLY": 5, "SAME_ARTICLE_DIFFERENT_GRANULARITY": 2}),
            self._b_summary(),
            dual_run_byte_identical=True,
        )
        assert out["outcome"] == "METHOD_B_LABEL_INDEPENDENT_CONFIRMED"
        assert out["sidecar_regenerated"] is False
        assert out["label_policy"]["label_assisted_promotion_allowed"] is False

    def test_both_directions_require_hybrid(self) -> None:
        out = recon.adjudicate(
            self._delta({"METHOD_A_ONLY": 1, "METHOD_B_ONLY": 1}),
            self._b_summary(),
            dual_run_byte_identical=True,
        )
        assert out["outcome"] == "HYBRID_METHOD_REQUIRED"

    def test_full_agreement_confirms_method_a(self) -> None:
        out = recon.adjudicate(
            self._delta({"IDENTICAL": 10}), self._b_summary(), dual_run_byte_identical=True
        )
        assert out["outcome"] == "METHOD_A_CONFIRMED"


class TestAuditSelection:
    def test_mandatory_categories_always_included(self, tmp_path: Path) -> None:
        delta = tmp_path / "delta.jsonl"
        rows = []
        for i in range(150):
            rows.append(
                {
                    "canonical_record_id": f"r{i}",
                    "partition": "train",
                    "source_row_index": i,
                    "exact_source_text_sha256": "a" * 64,
                    "method_a_tier": "TIER_1_PANEL_UNIQUE",
                    "method_a_doi": "10.1000/x",
                    "method_a_figure_id": "f",
                    "method_a_panel_id": "p",
                    "method_a_match_basis": "m",
                    "method_b_tier": "S3_UNIQUE_UNIT",
                    "method_b_doi": "10.1000/x",
                    "method_b_figure_id": "f",
                    "method_b_panel_id": "p",
                    "method_b_match_basis": "m",
                    "method_b_label_assisted": False,
                    "decision_relation": "IDENTICAL" if i % 2 else "METHOD_B_ONLY",
                    "delta_reason": "x",
                }
            )
        rows[7]["decision_relation"] = "CONFLICTING_PANEL"
        rows[9]["method_b_label_assisted"] = True
        delta.write_text(
            "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8"
        )
        audit = recon._build_audit_set(delta)
        ids = {r["canonical_record_id"] for r in audit}
        assert "r7" in ids  # conflict mandatory
        assert "r9" in ids  # label-assisted mandatory
        # Toy scale: 2 mandatory + all 75 remaining non-IDENTICAL rows (the
        # >=100 stratified floor binds only when enough delta rows exist).
        assert len(audit) == 77


class TestLockedBundleFailClosed:
    def test_toy_inputs_never_satisfy_attested_hashes(self, tmp_path: Path) -> None:
        canon = tmp_path / "canon"
        raw = tmp_path / "raw"
        canon.mkdir()
        for part in ("train", "validation", "test"):
            (canon / f"{part}.jsonl").write_text("", encoding="utf-8")
        (canon / "leakage_audit.json").write_text("{}", encoding="utf-8")
        archive = tmp_path / "archive.tar.gz"
        archive.write_bytes(b"not-an-archive")
        with pytest.raises(ValueError, match="sha256 mismatch"):
            recon.lock_input_bundle(canon_dir=canon, raw_dir=raw, archive=archive)


@pytest.mark.skipif(not REAL_AVAILABLE, reason="requires the FLASH128 dataset volume")
class TestRealScaleConsistency:
    """Consistency-only assertions; historical figures are NOT expected values."""

    @pytest.fixture(scope="class")
    def summary(self, tmp_path_factory: pytest.TempPathFactory) -> dict:
        work = tmp_path_factory.mktemp("reconciliation")
        return recon.run_pipeline(
            work_dir=work,
            canon_dir=REAL_CANON,
            raw_dir=REAL_RAW,
            archive=REAL_ARCHIVE,
            upstream_reference=recon.DEFAULT_UPSTREAM_REFERENCE,
        )

    def test_every_record_gets_exactly_one_delta_row(self, summary: dict) -> None:
        total = summary["lock"]["total_derived"]
        assert summary["method_a"]["rows"] == total
        assert summary["method_b"]["rows"] == total
        assert summary["delta"]["delta_rows"] == total

    def test_relations_within_allowed_vocabulary(self, summary: dict) -> None:
        assert set(summary["delta"]["relations"]) <= recon.ALLOWED_RELATIONS

    def test_method_b_buckets_partition_the_corpus(self, summary: dict) -> None:
        assert sum(summary["method_b"]["tier_counts"].values()) == summary["lock"]["total_derived"]

    def test_census_units_decompose(self, summary: dict) -> None:
        stats = summary["census"]["stats"]
        assert (
            stats["explicit_sd_panel_count"] + stats["figures_without_sd_panel"]
            == stats["total_matchable_units"]
        )
