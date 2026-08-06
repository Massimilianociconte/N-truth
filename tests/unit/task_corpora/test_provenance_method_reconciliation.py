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
import io
import json
import os
import subprocess
import sys
import tarfile
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

_BUILD_SPEC = importlib.util.spec_from_file_location(
    "sourcedata_sidecar_build",
    Path(__file__).resolve().parents[3] / "scripts/task_corpora/sourcedata_sidecar_build.py",
)
assert _BUILD_SPEC is not None and _BUILD_SPEC.loader is not None
build = importlib.util.module_from_spec(_BUILD_SPEC)
sys.modules[_BUILD_SPEC.name] = build
_BUILD_SPEC.loader.exec_module(build)

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
        # The hypothesis arithmetic must hold by INDEPENDENT measurement
        # (never by a derived identity that cannot fail):
        hyp = census.hypothesis
        assert hyp["measured_panels_plus_no_panel_equals_total"] is True
        assert (
            hyp["measured_explicit_panels"] + hyp["measured_no_panel_figure_units"]
            == hyp["measured_total_matchable_units"]
        )
        # The no-panel figure count must equal the independently counted
        # figure census statistic, not `total - panels`.
        assert hyp["measured_no_panel_figure_units"] == stats["figures_without_sd_panel"]
        # Independent unit iteration must agree with the census total.
        assert hyp["independent_unit_iteration_count"] == stats["total_matchable_units"]
        # Historical-only arithmetic must not masquerade as a measurement.
        assert "measured_75232_plus_2456_equals_77688" not in hyp
        assert hyp["historical_arithmetic_self_consistent"] is True


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

    def test_complete_decision_table(self) -> None:
        """Every §9 relation is reachable; no dead branch hides a case."""
        fallback_a = self._a(
            provenance_tier="RECORD_FALLBACK",
            granularity="RECORD_FALLBACK",
            article_doi=None,
            figure_id=None,
            panel_id=None,
            match_basis=None,
        )
        article_a = self._a(
            provenance_tier="TIER_2_ARTICLE_ONLY",
            granularity="ARTICLE",
            figure_id=None,
            panel_id=None,
        )
        figure_a = self._a(granularity="FIGURE", panel_id=None)
        article_b = self._b(method_b_tier="AMBIGUOUS_SINGLE_DOI", figure_id=None, panel_id=None)
        figure_b = self._b(panel_id=None)
        table = [
            # A and B agree on article, figure and panel:
            ("IDENTICAL", self._a(), self._b()),
            # Both hold only article-level evidence for the same article:
            ("IDENTICAL", article_a, article_b),
            # A has panel evidence, B fail-closed to single-DOI:
            ("SAME_ARTICLE_DIFFERENT_GRANULARITY", self._a(), article_b),
            # A is article-only, B recovered panel-level evidence:
            ("SAME_ARTICLE_DIFFERENT_GRANULARITY", article_a, self._b()),
            # A figure-level vs B panel-level (same article):
            ("SAME_ARTICLE_DIFFERENT_GRANULARITY", figure_a, self._b()),
            # A panel-level vs B figure-level (same article):
            ("SAME_ARTICLE_DIFFERENT_GRANULARITY", self._a(), figure_b),
            ("METHOD_A_ONLY", self._a(), self._b(method_b_tier="AMBIGUOUS_MULTI_DOI")),
            ("METHOD_B_ONLY", fallback_a, self._b()),
            ("CONFLICTING_ARTICLE", self._a(), self._b(article_doi="10.1000/y")),
            ("CONFLICTING_FIGURE", self._a(), self._b(figure_id="fig9")),
            ("CONFLICTING_PANEL", self._a(), self._b(panel_id="p9")),
            ("BOTH_FALLBACK", fallback_a, self._b(method_b_tier="UNMATCHED_NO_ASSET_TEXT")),
        ]
        outcomes: set[str] = set()
        for relation, a, b in table:
            got = recon.classify_relation(a, b)
            assert got == relation, f"{relation}: got {got}"
            outcomes.add(got)
        assert outcomes == recon.ALLOWED_RELATIONS

    def test_no_dead_granularity_branches(self) -> None:
        # A PANEL row whose B counterpart has no panel id must NOT be
        # IDENTICAL (former unreachable-guard regression).
        assert (
            recon.classify_relation(self._a(), self._b(panel_id=None))
            == "SAME_ARTICLE_DIFFERENT_GRANULARITY"
        )
        # A FIGURE row whose B counterpart names a panel must NOT be IDENTICAL.
        assert (
            recon.classify_relation(self._a(granularity="FIGURE", panel_id=None), self._b())
            == "SAME_ARTICLE_DIFFERENT_GRANULARITY"
        )
        # An A ARTICLE row paired with B panel evidence is a granularity
        # difference, never IDENTICAL.
        article_a = self._a(
            provenance_tier="TIER_2_ARTICLE_ONLY",
            granularity="ARTICLE",
            figure_id=None,
            panel_id=None,
        )
        assert recon.classify_relation(article_a, self._b()) == "SAME_ARTICLE_DIFFERENT_GRANULARITY"

    def test_delta_reason_taxonomy(self) -> None:
        reason = recon._delta_reason(self._a(), self._b(label_assisted=True), "METHOD_B_ONLY")
        assert reason == "label_assisted_tuple"
        assert reason in recon.METHOD_B_ONLY_REASONS
        reason = recon._delta_reason(self._a(), self._b(), "METHOD_B_ONLY")
        assert reason == "caption_parser_difference"
        assert reason in recon.METHOD_B_ONLY_REASONS


class TestAdjudication:
    DOIS = frozenset({"10.1000/x"})

    def _delta(self, relations: dict[str, int]) -> dict:
        return {"relations": relations, "delta_reasons": {}, "method_b_only_reasons": {}}

    def _b_summary(
        self,
        s4: int = 0,
        *,
        ambiguous_keys: int = 0,
        dois: set[str] | None = None,
        ambiguous_s3: int = 0,
        label_outside_s4: int = 0,
    ) -> dict:
        return {
            "tier_counts": {"S4_UNIQUE_ANNOTATION_TUPLE": s4},
            "ambiguous_unit_keys": ambiguous_keys,
            "assigned_dois": sorted(dois if dois is not None else {"10.1000/x"}),
            "ambiguous_key_records_emitted_s3": ambiguous_s3,
            "label_assisted_rows_outside_s4": label_outside_s4,
        }

    def _adjudicate(
        self,
        relations: dict[str, int],
        *,
        b_summary: dict[str, Any] | None = None,
        dual_run_byte_identical: bool = True,
        census_dois: frozenset[str] | None = None,
        input_bundle_reverified: bool = True,
    ) -> dict:
        return recon.adjudicate(
            self._delta(relations),
            b_summary if b_summary is not None else self._b_summary(),
            dual_run_byte_identical=dual_run_byte_identical,
            census_dois=census_dois if census_dois is not None else self.DOIS,
            input_bundle_reverified=input_bundle_reverified,
        )

    def test_conflicts_force_human_adjudication(self) -> None:
        out = self._adjudicate({"CONFLICTING_ARTICLE": 1})
        assert out["outcome"] == "METHODS_CONFLICT_REQUIRES_HUMAN_ADJUDICATION"

    def test_without_determinism_proof_insufficient(self) -> None:
        out = self._adjudicate({"METHOD_B_ONLY": 5}, dual_run_byte_identical=False)
        assert out["outcome"] == "INSUFFICIENT_EVIDENCE"

    def test_strict_superset_reproduced_zero_identifier_conflicts(self) -> None:
        out = self._adjudicate(
            {"METHOD_B_ONLY": 5, "SAME_ARTICLE_DIFFERENT_GRANULARITY": 2},
            dual_run_byte_identical=True,
        )
        # Evidence-accurate status: reproduced with zero identifier conflicts.
        # It is NOT a production-method confirmation.
        assert out["outcome"] == "METHOD_B_LABEL_INDEPENDENT_REPRODUCED_ZERO_IDENTIFIER_CONFLICTS"
        assert out["sidecar_regenerated"] is False
        assert out["label_policy"]["label_assisted_promotion_allowed"] is False

    def test_both_directions_require_hybrid(self) -> None:
        out = self._adjudicate(
            {"METHOD_A_ONLY": 1, "METHOD_B_ONLY": 1}, dual_run_byte_identical=True
        )
        assert out["outcome"] == "HYBRID_METHOD_REQUIRED"

    def test_full_agreement_confirms_method_a(self) -> None:
        out = self._adjudicate({"IDENTICAL": 10}, dual_run_byte_identical=True)
        assert out["outcome"] == "METHOD_A_CONFIRMED"

    def test_policy_version_and_sha_recorded_and_hash_stable(self) -> None:
        out1 = self._adjudicate({"IDENTICAL": 10}, dual_run_byte_identical=True)
        out2 = self._adjudicate({"IDENTICAL": 10}, dual_run_byte_identical=True)
        policy = out1["policy"]
        assert policy["version"] == recon.ADJUDICATION_POLICY.version
        assert len(policy["sha256"]) == 64
        assert policy["sha256"] == out2["policy"]["sha256"]
        for required in (
            "allowed_conflicting_assignments",
            "label_assisted_treatment",
            "acceptable_fallback_handling",
            "require_determinism",
            "require_official_source_linkage",
            "require_input_bundle_equality",
        ):
            assert required in policy

    def test_measured_conditions_are_actually_measured(self) -> None:
        # A Method B DOI outside the census DOI universe fails the tracing
        # condition and blocks any confirmation outcome.
        out = self._adjudicate(
            {"METHOD_B_ONLY": 1},
            b_summary=self._b_summary(dois={"10.1000/x", "10.9999/foreign"}),
            dual_run_byte_identical=True,
        )
        conds = out["conditions_measured"]
        assert conds["every_additional_assignment_traces_to_official_xml_unit"] is False
        assert out["outcome"] == "INSUFFICIENT_EVIDENCE"
        # Duplicate handling derives from the measured ambiguous-key count.
        out2 = self._adjudicate(
            {"IDENTICAL": 1},
            b_summary=self._b_summary(ambiguous_keys=3),
            dual_run_byte_identical=True,
        )
        assert out2["conditions_measured"]["duplicate_handling_fail_closed"] is True
        # A non-zero ambiguous-key S3 emission breaks the fail-closed gate.
        out4 = self._adjudicate(
            {"IDENTICAL": 1},
            b_summary=self._b_summary(ambiguous_s3=2),
            dual_run_byte_identical=True,
        )
        assert out4["conditions_measured"]["duplicate_handling_fail_closed"] is False
        assert out4["outcome"] == "INSUFFICIENT_EVIDENCE"
        # Canonical inputs must be re-verified after the pass.
        out3 = self._adjudicate(
            {"IDENTICAL": 1}, dual_run_byte_identical=True, input_bundle_reverified=False
        )
        assert out3["conditions_measured"]["no_canonical_record_or_split_modified"] is False
        assert out3["outcome"] == "INSUFFICIENT_EVIDENCE"
        # Construction invariants are reported separately from measurements.
        assert "no_first_match_behaviour" in out3["conditions_by_construction"]

    def test_missing_required_measured_field_fails_closed(self) -> None:
        for field in (
            "assigned_dois",
            "ambiguous_key_records_emitted_s3",
            "label_assisted_rows_outside_s4",
        ):
            summary = self._b_summary()
            del summary[field]
            with pytest.raises(ValueError, match="missing required measured fields"):
                self._adjudicate({"IDENTICAL": 1}, b_summary=summary)

    def test_s4_reconstruction_status_is_partial(self) -> None:
        out = self._adjudicate({"IDENTICAL": 1}, b_summary=self._b_summary(s4=3))
        s4 = out["label_assisted_s4"]
        assert s4["reconstructed"] == 3
        assert s4["historically_reported"] == 14
        assert s4["status"] == "PARTIAL_NOT_HISTORICALLY_REPRODUCIBLE"
        assert s4["production_eligibility"] == "NON_PRODUCTION"


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


def _toy_archive(tmp_path: Path, members: dict[str, bytes], name: str = "arc.tar.gz") -> Path:
    """Deterministic toy tar.gz (fixed mtime, sorted members)."""
    arc = tmp_path / name
    with tarfile.open(arc, "w:gz") as tf:
        for member, data in sorted(members.items()):
            info = tarfile.TarInfo(name=member)
            info.size = len(data)
            info.mtime = 0
            tf.addfile(info, io.BytesIO(data))
    return arc


class TestStrictParallelIteration:
    def test_words_labels_length_mismatch_fails_closed(self) -> None:
        with pytest.raises(ValueError, match="words/labels length mismatch"):
            recon._record_entity_span_signature(["a", "b"], ["O"])

    def test_aligned_words_labels_accepted(self) -> None:
        sig = recon._record_entity_span_signature(["eps.", "protX"], ["O", "B-MEASURED_VAR"])
        assert isinstance(sig, str) and len(sig) == 64


class TestFailClosedContracts:
    def test_delta_field_contract_enforced_without_assert(self) -> None:
        # `python -O` strips assert statements, so the delta field contract
        # must fail closed via a real raise, never via `assert`. Behavioral:
        # enforce the contract inside an optimized interpreter and require a
        # ValueError (an `assert` would be silently removed under -O).
        packages = Path(__file__).resolve().parents[3] / "packages"
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(
            [str(packages), *filter(None, env.get("PYTHONPATH", "").split(os.pathsep))]
        )
        code = (
            "import importlib.util, sys\n"
            f"spec = importlib.util.spec_from_file_location('recon', r'{recon.__file__}')\n"
            "m = importlib.util.module_from_spec(spec)\n"
            "sys.modules['recon'] = m\n"
            "spec.loader.exec_module(m)\n"
            "row = dict.fromkeys(m.DELTA_FIELDS, 'x')\n"
            "row['decision_relation'] = 'NOT_A_RELATION'\n"
            "try:\n"
            "    m._enforce_delta_contract(row)\n"
            "except ValueError:\n"
            "    print('RAISED_VALUE_ERROR')\n"
            "else:\n"
            "    print('NO_RAISE')\n"
        )
        proc = subprocess.run(
            [sys.executable, "-O", "-c", code], capture_output=True, text=True, env=env
        )
        assert "RAISED_VALUE_ERROR" in proc.stdout, proc.stderr
        assert "NO_RAISE" not in proc.stdout

    def test_out_of_vocabulary_relation_rejected(self) -> None:
        bad = dict.fromkeys(recon.DELTA_FIELDS, "x")
        bad["decision_relation"] = "NOT_A_RELATION"
        with pytest.raises(ValueError, match="relation"):
            recon._enforce_delta_contract(bad)

    def test_field_contract_violation_rejected(self) -> None:
        bad = {k: "x" for k in list(recon.DELTA_FIELDS)[:-1]}
        with pytest.raises(ValueError, match="delta field contract"):
            recon._enforce_delta_contract(bad)


class TestXmlDirectoryBinding:
    def test_extract_refuses_preexisting_destination(self, tmp_path: Path) -> None:
        arc = _toy_archive(tmp_path, {"a.xml": b'<article doi="10.1000/x"/>'})
        dest = tmp_path / "xml"
        dest.mkdir()
        (dest / "foreign.xml").write_text("<x/>", encoding="utf-8")
        with pytest.raises(Exception, match="already exists"):
            recon.extract_xml_archive(arc, dest, expected_sha256=recon.sha256_file(arc))

    def test_pipeline_rerun_replaces_stale_xml_tree(self, tmp_path: Path) -> None:
        # A second pass into the same work dir must re-extract, never reuse:
        # a stale file planted in the tree must disappear on re-extraction.
        arc = _toy_archive(tmp_path, {"a.xml": b'<article doi="10.1000/x"/>'})
        dest = tmp_path / "xml_v2.0.3"
        recon._fresh_extract_xml(archive=arc, xml_dir=dest, expected_sha256=recon.sha256_file(arc))
        assert (dest / "a.xml").exists()
        (dest / "stale.xml").write_text("<x/>", encoding="utf-8")
        recon._fresh_extract_xml(archive=arc, xml_dir=dest, expected_sha256=recon.sha256_file(arc))
        assert not (dest / "stale.xml").exists()
        assert (dest / "a.xml").exists()

    def test_attestation_binds_tree_to_archive_and_bundle(self, tmp_path: Path) -> None:
        arc = _toy_archive(tmp_path, {"a.xml": b'<article doi="10.1000/x"/>'})
        dest = tmp_path / "xml"
        recon.extract_xml_archive(arc, dest, expected_sha256=recon.sha256_file(arc))
        att = recon.attest_extracted_xml_dir(
            archive=arc, xml_dir=dest, input_bundle_sha256="b" * 64
        )
        assert att["archive_sha256"] == recon.sha256_file(arc)
        assert att["file_count"] == 1
        assert att["members"] == ["a.xml"]
        assert att["input_bundle_sha256"] == "b" * 64
        assert len(att["tree_sha256"]) == 64

    def test_wrong_archive_hash_fails_closed(self, tmp_path: Path) -> None:
        arc = _toy_archive(tmp_path, {"a.xml": b"<article/>"})
        with pytest.raises(Exception, match="sha256 mismatch"):
            recon.extract_xml_archive(arc, tmp_path / "xml", expected_sha256="0" * 64)


class TestExplicitUtf8:
    def test_write_json_emits_utf8_bytes(self, tmp_path: Path) -> None:
        p = tmp_path / "x.json"
        recon._write_json(p, {"k": "prot\u00e9ine \u2013 \u03b1"})
        # Exact UTF-8 bytes of the non-ASCII payload must be on disk:
        assert b"prot\xc3\xa9ine \xe2\x80\x93 \xce\xb1" in p.read_bytes()


class TestPhysicalLineSemantics:
    def test_u2028_u2029_inside_strings_do_not_split_rows(self) -> None:
        row1 = json.dumps({"caption": "x\u2028y\u2029z"}, ensure_ascii=False)
        row2 = json.dumps({"caption": "plain"}, ensure_ascii=False)
        blob = (row1 + "\n" + row2 + "\n").encode("utf-8")
        rows = build.parse_jsonl_blob(blob)
        assert len(rows) == 2
        assert rows[0]["caption"] == "x\u2028y\u2029z"

    def test_splitlines_would_corrupt_such_blobs(self) -> None:
        # Documents WHY splitlines() is forbidden for JSONL payloads: it
        # splits on U+2028/U+2029 (and more), fragmenting one row.
        assert len(json.dumps({"c": "x\u2028y"}, ensure_ascii=False).splitlines()) == 2


class TestExporterLineageClassifier:
    def test_no_sources_is_unavailable(self) -> None:
        assert recon.classify_exporter_lineage([]) == "EXPORTER_LINEAGE_UNAVAILABLE"

    def test_all_irrecoverable_is_unavailable(self) -> None:
        rec = {"available": False, "projection": None, "evidence_strength": None}
        assert recon.classify_exporter_lineage([rec]) == "EXPORTER_LINEAGE_UNAVAILABLE"

    def test_decisive_itertext_supports_method_b(self) -> None:
        rec = {"available": True, "projection": "itertext", "evidence_strength": "decisive"}
        assert recon.classify_exporter_lineage([rec]) == "EXPORTER_LINEAGE_SUPPORTS_METHOD_B"

    def test_decisive_attribute_supports_method_a(self) -> None:
        rec = {
            "available": True,
            "projection": "sd_tag_attribute",
            "evidence_strength": "decisive",
        }
        assert recon.classify_exporter_lineage([rec]) == "EXPORTER_LINEAGE_SUPPORTS_METHOD_A"

    def test_conflicting_decisive_sources_require_human(self) -> None:
        recs = [
            {"available": True, "projection": "itertext", "evidence_strength": "decisive"},
            {"available": True, "projection": "sd_tag_attribute", "evidence_strength": "decisive"},
        ]
        assert recon.classify_exporter_lineage(recs) == "METHODS_REQUIRE_HUMAN_ADJUDICATION"

    def test_available_but_inconclusive_requires_human(self) -> None:
        rec = {"available": True, "projection": "other", "evidence_strength": "suggestive"}
        assert recon.classify_exporter_lineage([rec]) == "METHODS_REQUIRE_HUMAN_ADJUDICATION"

    def test_decisive_hybrid_exporter_supports_hybrid(self) -> None:
        rec = {"available": True, "projection": "hybrid", "evidence_strength": "decisive"}
        assert recon.classify_exporter_lineage([rec]) == "EXPORTER_LINEAGE_SUPPORTS_HYBRID"

    def test_outcome_vocabulary_is_closed(self) -> None:
        assert (
            frozenset(
                {
                    "EXPORTER_LINEAGE_SUPPORTS_METHOD_A",
                    "EXPORTER_LINEAGE_SUPPORTS_METHOD_B",
                    "EXPORTER_LINEAGE_SUPPORTS_HYBRID",
                    "EXPORTER_LINEAGE_UNAVAILABLE",
                    "METHODS_REQUIRE_HUMAN_ADJUDICATION",
                }
            )
            == recon.EXPORTER_LINEAGE_OUTCOMES
        )


class TestProjectionEquivalenceFixtures:
    """Locked record text IS the exporter output — it is the reference."""

    LOCKED = frozenset(
        recon.normalize_caption(t) for t in ("(A) eps. protX", "(B) eps. prot-Y", "(C) both equal")
    )

    def test_method_b_supported_fixture(self) -> None:
        unit = {"caption_itertext": "(A) eps. protX", "caption_attribute": "(A) eps. prot\u2013X"}
        cats = recon.projection_equivalence_categories([unit], self.LOCKED)
        assert cats["itertext_matches_exporter"] == 1

    def test_method_a_supported_fixture(self) -> None:
        unit = {"caption_itertext": "(B) eps. prot\u2013Y", "caption_attribute": "(B) eps. prot-Y"}
        cats = recon.projection_equivalence_categories([unit], self.LOCKED)
        assert cats["attribute_matches_exporter"] == 1

    def test_identical_projections_fixture(self) -> None:
        unit = {"caption_itertext": "(C) both equal", "caption_attribute": "(C) both equal"}
        cats = recon.projection_equivalence_categories([unit], self.LOCKED)
        assert cats["projections_identical"] == 1

    def test_both_match_distinct_locked_texts_fixture(self) -> None:
        # Both projections exist in the locked universe as DIFFERENT texts:
        # the only branch of _projection_category that records this case.
        unit = {"caption_itertext": "(A) eps. protX", "caption_attribute": "(B) eps. prot-Y"}
        cats = recon.projection_equivalence_categories([unit], self.LOCKED)
        assert cats["both_match_distinct_locked_texts"] == 1
        assert cats["itertext_matches_exporter"] == 0
        assert cats["attribute_matches_exporter"] == 0

    def test_neither_and_unavailable_categories(self) -> None:
        units = [
            {"caption_itertext": "(D) alien", "caption_attribute": "(D) alien2"},
            {"caption_itertext": "", "caption_attribute": ""},
        ]
        cats = recon.projection_equivalence_categories(units, self.LOCKED)
        assert cats["neither_matches_exporter"] == 1
        assert cats["exporter_unavailable_for_unit"] == 1


TOY_ARTICLE_D = """<article doi="10.1000/toy.d">
<fig id="fig1">
<sd-panel panel_id="p1"><p>(T) tag <sd-tag text="protY" role="component">protX</sd-tag> end.</p></sd-panel>
</fig>
</article>
"""


class TestUnitAttributeProjection:
    """§5: units must carry BOTH caption projections (itertext + attribute)."""

    def _units(self, tmp_path: Path) -> list[dict[str, Any]]:
        xml = tmp_path / "xml"
        xml.mkdir()
        (xml / "d.xml").write_text(TOY_ARTICLE_D, encoding="utf-8")
        return list(recon._iter_figure_units(xml))

    def test_unit_carries_attribute_projection(self, tmp_path: Path) -> None:
        units = self._units(tmp_path)
        assert len(units) == 1
        unit = units[0]
        assert unit["caption_itertext"] == recon.normalize_caption("(T) tag protX end.")
        assert unit["caption_attribute"] == recon.normalize_caption("(T) tag protY end.")
        assert unit["caption_itertext"] != unit["caption_attribute"]

    def test_attribute_projection_matches_method_a_index(self, tmp_path: Path) -> None:
        units = self._units(tmp_path)
        xml = tmp_path / "xml"
        index = list(recon.iter_upstream_captions(xml))
        assert len(index) == 1
        assert units[0]["caption_attribute"] == recon.normalize_caption(index[0]["caption"])


class TestRunProjectionEquivalence:
    """§5: pipeline-stage analysis over the locked bundle (counts only)."""

    def _run(self, tmp_path: Path) -> tuple[dict[str, Any], Path]:
        xml = tmp_path / "xml"
        xml.mkdir()
        (xml / "a.xml").write_text(TOY_ARTICLE_A, encoding="utf-8")
        (xml / "d.xml").write_text(TOY_ARTICLE_D, encoding="utf-8")
        raw = _toy_raw_dir(
            tmp_path,
            {"train": [_raw_line("(A) alpha."), _raw_line("(T) tag protX end.")]},
        )
        out = tmp_path / "projection_equivalence_rows.jsonl"
        summary = recon.run_projection_equivalence(xml_dir=xml, raw_dir=raw, out_path=out)
        return summary, out

    def test_categories_vocabulary_and_sums(self, tmp_path: Path) -> None:
        summary, _ = self._run(tmp_path)
        cats = summary["categories"]
        assert tuple(cats) == recon.PROJECTION_EQUIVALENCE_CATEGORIES, (
            "category keys must follow the §5 vocabulary order"
        )
        assert sum(cats.values()) == summary["units"]

    def test_rows_are_sanitized_and_attributed(self, tmp_path: Path) -> None:
        summary, out = self._run(tmp_path)
        rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
        assert len(rows) == summary["units"]
        for row in rows:
            # NO corpus text may appear in the rows — identifiers + hashes only.
            for value in row.values():
                if isinstance(value, str):
                    assert "alpha" not in value and "tag" not in value.lower()
            assert row["category"] in recon.PROJECTION_EQUIVALENCE_CATEGORIES
            assert set(row) == {
                "article_doi",
                "fig_id",
                "panel_id",
                "unit_kind",
                "category",
                "itertext_sha256",
                "attribute_sha256",
            }
        assert summary["output_sha256"] == recon.sha256_file(out)

    def test_locked_texts_are_the_raw_exporter_universe(self, tmp_path: Path) -> None:
        summary, _ = self._run(tmp_path)
        assert summary["locked_text_count"] == 2
        # "(A) alpha." exists as locked text and as unit itertext projection.
        assert summary["categories"]["itertext_matches_exporter"] >= 1


class TestMethodBOnlyRecordAnalysis:
    """§5: per-record analysis of METHOD_B_ONLY rows (sanitized fields only)."""

    def _scenario(self, tmp_path: Path) -> tuple[Path, Path, Path]:
        xml = tmp_path / "xml"
        xml.mkdir()
        (xml / "d.xml").write_text(TOY_ARTICLE_D, encoding="utf-8")
        raw = _toy_raw_dir(
            tmp_path,
            {
                "train": [
                    _raw_line(
                        "(T) tag protX end.",
                        words=["(T)", "tag", "protX", "end", "."],
                        labels=["O", "O", "B-GENEPROD", "O", "O"],
                    )
                ]
            },
        )
        rec_text = "(T) tag protX end."
        delta = tmp_path / "delta_rows.jsonl"
        row = {field: None for field in recon.DELTA_FIELDS}
        row.update(
            {
                "canonical_record_id": "rec-toy-1",
                "partition": "train",
                "source_row_index": 0,
                "exact_source_text_sha256": recon.sha256_bytes(rec_text.encode("utf-8")),
                "method_a_tier": "RECORD_FALLBACK",
                "method_b_tier": "S3_UNIQUE_UNIT",
                "method_b_doi": "10.1000/toy.d",
                "method_b_figure_id": "fig1",
                "method_b_panel_id": "p1",
                "method_b_match_basis": "exact_canonical_text_unique_unit",
                "method_b_label_assisted": False,
                "decision_relation": "METHOD_B_ONLY",
                "delta_reason": "caption_parser_difference",
            }
        )
        delta.write_text(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
        )
        return xml, raw, delta

    def test_method_b_only_root_cause_measurement(self, tmp_path: Path) -> None:
        xml, raw, delta = self._scenario(tmp_path)
        out = tmp_path / "method_b_only_rows.jsonl"
        summary = recon.analyze_method_b_only_records(
            delta_path=delta, xml_dir=xml, raw_dir=raw, out_path=out
        )
        assert summary["records_analyzed"] == 1
        assert summary["itertext_equals_locked"] == 1
        assert summary["attribute_differs_from_locked"] == 1
        assert summary["entity_span_signature_matches"] == 0
        rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
        assert len(rows) == 1
        row = rows[0]
        assert row["canonical_record_id"] == "rec-toy-1"
        # Attribute differs from locked only by one same-width token char:
        # exact zero deltas prove the length/token measurements are correct.
        assert row["char_len_diff"] == 0
        assert row["token_count_diff"] == 0
        assert row["attribute_equals_other_locked_text"] is False
        # No corpus text in the emitted rows.
        for value in row.values():
            if isinstance(value, str):
                assert "protX" not in value

    def test_ignores_non_method_b_only_rows(self, tmp_path: Path) -> None:
        xml, raw, delta = self._scenario(tmp_path)
        lines = delta.read_text(encoding="utf-8").splitlines()
        other = json.loads(lines[0])
        other["decision_relation"] = "IDENTICAL"
        delta.write_text(
            json.dumps(other, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        summary = recon.analyze_method_b_only_records(
            delta_path=delta,
            xml_dir=xml,
            raw_dir=raw,
            out_path=tmp_path / "rows.jsonl",
        )
        assert summary["records_analyzed"] == 0

    def test_unlocatable_unit_fails_closed(self, tmp_path: Path) -> None:
        xml, raw, delta = self._scenario(tmp_path)
        lines = delta.read_text(encoding="utf-8").splitlines()
        broken = json.loads(lines[0])
        broken["method_b_panel_id"] = "does-not-exist"
        delta.write_text(
            json.dumps(broken, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="METHOD_B_ONLY"):
            recon.analyze_method_b_only_records(
                delta_path=delta,
                xml_dir=xml,
                raw_dir=raw,
                out_path=tmp_path / "rows.jsonl",
            )

    def test_doi_collapse_row_measured_against_candidate_set(self, tmp_path: Path) -> None:
        xml = tmp_path / "xml"
        xml.mkdir()
        # Two panels sharing one caption, in one article: DOI-collapse match.
        (xml / "e.xml").write_text(
            """<article doi="10.1000/toy.e">
<fig id="fig1">
<sd-panel panel_id="p1"><p>(U) dup <sd-tag text="protY" role="component">protX</sd-tag></p></sd-panel>
<sd-panel panel_id="p2"><p>(U) dup <sd-tag text="protY" role="component">protX</sd-tag></p></sd-panel>
</fig>
</article>
""",
            encoding="utf-8",
        )
        raw = _toy_raw_dir(tmp_path, {"train": [_raw_line("(U) dup protX")]})
        rec_text = "(U) dup protX"
        row = {field: None for field in recon.DELTA_FIELDS}
        row.update(
            {
                "canonical_record_id": "rec-toy-2",
                "partition": "train",
                "source_row_index": 0,
                "exact_source_text_sha256": recon.sha256_bytes(rec_text.encode("utf-8")),
                "method_a_tier": "RECORD_FALLBACK",
                "method_b_tier": "AMBIGUOUS_SINGLE_DOI",
                "method_b_doi": "10.1000/toy.e",
                "method_b_match_basis": "doi_collapse_single_article",
                "method_b_label_assisted": False,
                "decision_relation": "METHOD_B_ONLY",
                "delta_reason": "caption_parser_difference",
            }
        )
        delta = tmp_path / "delta_rows.jsonl"
        delta.write_text(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        out = tmp_path / "rows.jsonl"
        summary = recon.analyze_method_b_only_records(
            delta_path=delta, xml_dir=xml, raw_dir=raw, out_path=out
        )
        assert summary["records_analyzed"] == 1
        assert summary["ambiguous_unit_set"] == 1
        assert summary["itertext_equals_locked"] == 1
        assert summary["attribute_differs_from_locked"] == 1
        emitted = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
        assert emitted["ambiguous_unit_set"] is True
        assert emitted["candidate_unit_count"] == 2
        assert emitted["char_len_diff"] == -1  # no single unit → not measured

    def test_panels_without_panel_id_share_a_location(self, tmp_path: Path) -> None:
        xml = tmp_path / "xml"
        xml.mkdir()
        # Real-data quirk (e.g. 10.15252/emmm.202012109): several panels in
        # one figure lack panel_id attributes and therefore share the
        # (doi, fig, "") location — attribution must stay set-based.
        (xml / "f.xml").write_text(
            """<article doi="10.1000/toy.f">
<fig id="fig1">
<sd-panel><p>(V) noid <sd-tag text="protY" role="component">protX</sd-tag></p></sd-panel>
<sd-panel><p>(V2) other caption entirely.</p></sd-panel>
</fig>
</article>
""",
            encoding="utf-8",
        )
        raw = _toy_raw_dir(tmp_path, {"train": [_raw_line("(V) noid protX")]})
        rec_text = "(V) noid protX"
        row = {field: None for field in recon.DELTA_FIELDS}
        row.update(
            {
                "canonical_record_id": "rec-toy-4",
                "partition": "train",
                "source_row_index": 0,
                "exact_source_text_sha256": recon.sha256_bytes(rec_text.encode("utf-8")),
                "method_a_tier": "RECORD_FALLBACK",
                "method_b_tier": "S3_UNIQUE_UNIT",
                "method_b_doi": "10.1000/toy.f",
                "method_b_figure_id": "fig1",
                "method_b_match_basis": "exact_canonical_text_unique_unit",
                "method_b_label_assisted": False,
                "decision_relation": "METHOD_B_ONLY",
                "delta_reason": "caption_parser_difference",
            }
        )
        delta = tmp_path / "delta_rows.jsonl"
        delta.write_text(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        out = tmp_path / "rows.jsonl"
        summary = recon.analyze_method_b_only_records(
            delta_path=delta, xml_dir=xml, raw_dir=raw, out_path=out
        )
        assert summary["records_analyzed"] == 1
        assert summary["ambiguous_unit_set"] == 1
        emitted = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
        assert emitted["candidate_unit_count"] == 1  # by caption key
        assert emitted["itertext_equals_locked"] is True

    def test_doi_collapse_row_without_candidates_fails_closed(self, tmp_path: Path) -> None:
        xml = tmp_path / "xml"
        xml.mkdir()
        (xml / "e.xml").write_text(TOY_ARTICLE_D, encoding="utf-8")
        raw = _toy_raw_dir(tmp_path, {"train": [_raw_line("(Z) nowhere")]})
        row = {field: None for field in recon.DELTA_FIELDS}
        row.update(
            {
                "canonical_record_id": "rec-toy-3",
                "partition": "train",
                "source_row_index": 0,
                "exact_source_text_sha256": recon.sha256_bytes(b"(Z) nowhere"),
                "method_a_tier": "RECORD_FALLBACK",
                "method_b_tier": "AMBIGUOUS_SINGLE_DOI",
                "method_b_doi": "10.1000/toy.d",
                "method_b_match_basis": "doi_collapse_single_article",
                "method_b_label_assisted": False,
                "decision_relation": "METHOD_B_ONLY",
                "delta_reason": "caption_parser_difference",
            }
        )
        delta = tmp_path / "delta_rows.jsonl"
        delta.write_text(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="candidate upstream unit"):
            recon.analyze_method_b_only_records(
                delta_path=delta,
                xml_dir=xml,
                raw_dir=raw,
                out_path=tmp_path / "rows.jsonl",
            )


def _toy_delta_row(
    *,
    record_id: str,
    relation: str,
    reason: str,
    partition: str = "train",
    row_index: int = 0,
    a_tier: str = "TIER_1_PANEL_UNIQUE",
    b_tier: str = "S3_UNIQUE_UNIT",
    b_label_assisted: bool = False,
    doi: str = "10.1000/toy.a",
) -> dict[str, Any]:
    row = {field: None for field in recon.DELTA_FIELDS}
    row.update(
        {
            "canonical_record_id": record_id,
            "partition": partition,
            "source_row_index": row_index,
            "exact_source_text_sha256": recon.sha256_bytes(record_id.encode("utf-8")),
            "method_a_tier": a_tier,
            "method_b_tier": b_tier,
            "method_b_label_assisted": b_label_assisted,
            "decision_relation": relation,
            "delta_reason": reason,
        }
    )
    if a_tier != "RECORD_FALLBACK":
        row["method_a_doi"] = doi
    if b_tier not in ("UNMATCHED_NO_ASSET_TEXT",):
        row["method_b_doi"] = doi
    return row


def _toy_dossier_run_dir(tmp_path: Path) -> Path:
    run = tmp_path / "run"
    run.mkdir()

    def _write(name: str, rows: list[dict[str, Any]]) -> None:
        (run / name).write_text(
            "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows),
            encoding="utf-8",
        )

    _write(
        "delta_rows.jsonl",
        [
            _toy_delta_row(record_id="rec-0", relation="IDENTICAL", reason="none"),
            _toy_delta_row(
                record_id="rec-1",
                relation="METHOD_B_ONLY",
                reason="caption_parser_difference",
                a_tier="RECORD_FALLBACK",
            ),
            _toy_delta_row(
                record_id="rec-2",
                relation="SAME_ARTICLE_DIFFERENT_GRANULARITY",
                reason="doi_collapse_difference",
                a_tier="TIER_2_ARTICLE_ONLY",
                b_tier="AMBIGUOUS_SINGLE_DOI",
            ),
            _toy_delta_row(
                record_id="rec-3",
                relation="BOTH_FALLBACK",
                reason="both_methods_fail_closed_on_this_record",
                a_tier="RECORD_FALLBACK",
                b_tier="UNMATCHED_NO_ASSET_TEXT",
            ),
        ],
    )
    _write(
        "method_b_only_rows.jsonl",
        [
            {
                "canonical_record_id": "rec-1",
                "partition": "train",
                "source_row_index": 1,
                "exact_source_text_sha256": recon.sha256_bytes(b"rec-1"),
                "article_doi": "10.1000/toy.a",
                "fig_id": "fig1",
                "panel_id": "p1",
                "method_b_tier": "S3_UNIQUE_UNIT",
                "itertext_equals_locked": True,
                "attribute_differs_from_locked": True,
                "attribute_equals_other_locked_text": False,
                "entity_span_signature_matches": False,
                "ambiguous_unit_set": False,
                "candidate_unit_count": 1,
                "char_len_diff": 4,
                "token_count_diff": 0,
            }
        ],
    )
    _write(
        "method_b_rows.jsonl",
        [
            {
                "canonical_record_id": "rec-0",
                "partition": "train",
                "source_row_index": 0,
                "exact_source_text_sha256": recon.sha256_bytes(b"rec-0"),
                "article_doi": "10.1000/toy.a",
                "figure_id": "fig1",
                "panel_id": "p1",
                "method_b_tier": "S3_UNIQUE_UNIT",
                "label_assisted": False,
                "match_basis": "exact_canonical_text_unique_unit",
            },
            {
                "canonical_record_id": "rec-s4",
                "partition": "train",
                "source_row_index": 4,
                "exact_source_text_sha256": recon.sha256_bytes(b"rec-s4"),
                "article_doi": "10.1000/toy.b",
                "figure_id": "fig1",
                "panel_id": "p1",
                "method_b_tier": "S4_UNIQUE_ANNOTATION_TUPLE",
                "label_assisted": True,
                "match_basis": "entity_span_tuple_unique",
            },
        ],
    )
    _write(
        "projection_equivalence_rows.jsonl",
        [
            {
                "article_doi": "10.1000/toy.a",
                "fig_id": "fig1",
                "panel_id": "p1",
                "unit_kind": "PANEL",
                "category": "itertext_matches_exporter",
                "itertext_sha256": "a" * 64,
                "attribute_sha256": "b" * 64,
            },
            {
                "article_doi": "10.1000/toy.a",
                "fig_id": "fig1",
                "panel_id": "p2",
                "unit_kind": "PANEL",
                "category": "projections_identical",
                "itertext_sha256": "c" * 64,
                "attribute_sha256": "c" * 64,
            },
            {
                "article_doi": "10.1000/toy.a",
                "fig_id": "fig2",
                "panel_id": "",
                "unit_kind": "FIGURE",
                "category": "neither_matches_exporter",
                "itertext_sha256": "d" * 64,
                "attribute_sha256": "e" * 64,
            },
        ],
    )
    (run / "delta_summary.json").write_text(
        json.dumps({"relations": {"IDENTICAL": 1, "METHOD_B_ONLY": 1}}, sort_keys=True),
        encoding="utf-8",
    )
    (run / "method_b_only_summary.json").write_text(
        json.dumps(
            {
                "records_analyzed": 1,
                "itertext_equals_locked": 1,
                "attribute_differs_from_locked": 1,
                "attribute_equals_other_locked_text": 0,
                "entity_span_signature_matches": 0,
                "ambiguous_unit_set": 0,
                "output_sha256": "f" * 64,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (run / "projection_equivalence.json").write_text(
        json.dumps(
            {"categories": {"itertext_matches_exporter": 1, "projections_identical": 1}},
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    (run / "adjudication.json").write_text(
        json.dumps(
            {
                "outcome": "METHOD_B_LABEL_INDEPENDENT_REPRODUCED_ZERO_IDENTIFIER_CONFLICTS",
                "exporter_lineage": "EXPORTER_LINEAGE_SUPPORTS_METHOD_B",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return run


#: Corpus-bearing field names that must NEVER appear in any dossier artifact.
CORPUS_TEXT_FIELDS = {"text", "words", "labels", "caption", "caption_itertext", "caption_attribute"}


class TestAdjudicationDossier:
    """§8: the dossier is a review packet — identifiers and hashes only."""

    def test_dossier_files_and_counts(self, tmp_path: Path) -> None:
        run = _toy_dossier_run_dir(tmp_path)
        summary = recon.build_adjudication_dossier(run_dir=run)
        dossier = run / "adjudication_dossier"
        lines = lambda name: (  # noqa: E731
            (dossier / name).read_text(encoding="utf-8").splitlines()
        )
        assert len(lines("method_b_only_records.jsonl")) == 1
        assert len(lines("same_article_different_granularity_records.jsonl")) == 1
        assert len(lines("both_fallback_records.jsonl")) == 1
        assert len(lines("label_assisted_s4_records.jsonl")) == 1
        # Disagreement = categories where the two projections diverge on
        # exporter membership (itertext-matches here; neither-matches does
        # not pit the projections against each other).
        rows = [json.loads(line) for line in lines("exporter_projection_disagreements.jsonl")]
        assert len(rows) == 1
        assert rows[0]["category"] == "itertext_matches_exporter"
        assert summary["counts"]["method_b_only_records"] == 1
        assert summary["counts"]["same_article_different_granularity_records"] == 1
        assert summary["counts"]["both_fallback_records"] == 1
        assert summary["counts"]["label_assisted_s4_records"] == 1
        assert summary["counts"]["exporter_projection_disagreements"] == 1
        # Every file hash is recorded for the review packet attestation.
        for name, digest in summary["file_sha256"].items():
            assert digest == recon.sha256_file(dossier / name)

    def test_dossier_contains_no_corpus_text_fields(self, tmp_path: Path) -> None:
        run = _toy_dossier_run_dir(tmp_path)
        recon.build_adjudication_dossier(run_dir=run)
        dossier = run / "adjudication_dossier"
        for path in dossier.iterdir():
            if path.suffix != ".jsonl":
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                assert not (CORPUS_TEXT_FIELDS & set(row)), path.name

    def test_stratified_sample_external_text_references(self, tmp_path: Path) -> None:
        run = _toy_dossier_run_dir(tmp_path)
        recon.build_adjudication_dossier(run_dir=run)
        rows = [
            json.loads(line)
            for line in (run / "adjudication_dossier" / "human_inspection_sample.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        # Every mandatory category is represented in the packet sample.
        categories = {row["dossier_category"] for row in rows}
        assert categories == {
            "METHOD_B_ONLY",
            "SAME_ARTICLE_DIFFERENT_GRANULARITY",
            "BOTH_FALLBACK",
            "S4_LABEL_ASSISTED",
        }
        b_only = next(row for row in rows if row["dossier_category"] == "METHOD_B_ONLY")
        # External text reference = locked file + 1-based physical line.
        assert b_only["canonical_reference"].endswith("train.jsonl")
        assert b_only["canonical_line"] == 2
        assert "10.1000/toy.a" in b_only["upstream_xml_reference"]

    def test_categories_adjudication_contract(self, tmp_path: Path) -> None:
        run = _toy_dossier_run_dir(tmp_path)
        recon.build_adjudication_dossier(run_dir=run)
        categories = json.loads(
            (run / "adjudication_dossier" / "categories.json").read_text(encoding="utf-8")
        )
        required = {
            "METHOD_B_ONLY",
            "SAME_ARTICLE_DIFFERENT_GRANULARITY",
            "BOTH_FALLBACK",
            "S4_LABEL_ASSISTED",
            "EXPORTER_PROJECTION_DISAGREEMENT",
            "HUMAN_INSPECTION_SAMPLE",
        }
        assert set(categories) == required
        for entry in categories.values():
            assert set(entry) == {
                "question",
                "evidence",
                "recommended_interpretation",
                "confidence",
                "human_decision_required",
            }
            assert entry["confidence"] in {"high", "medium", "low"}
            # This packet exists BECAUSE a human decision remains necessary.
            assert entry["human_decision_required"] is True

    def test_dossier_artifacts_are_determinism_artifacts(self) -> None:
        for name in recon.DOSSIER_ARTIFACTS:
            assert f"adjudication_dossier/{name}" in recon.DETERMINISM_ARTIFACTS


@pytest.mark.skipif(not REAL_AVAILABLE, reason="requires the FLASH128 dataset volume")
class TestRealScaleReportOrdering:
    def test_no_final_adjudication_when_reruns_diverge(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real_sha = recon.sha256_file

        def tamper(path: Path) -> str:
            digest = real_sha(path)
            if "/run-2/" in str(path) and Path(path).name == "census.json":
                return "f" * 64
            return digest

        monkeypatch.setattr(recon, "sha256_file", tamper)
        with pytest.raises(ValueError, match="not byte-deterministic"):
            recon.run_all_twice(
                work_dir=tmp_path,
                canon_dir=REAL_CANON,
                raw_dir=REAL_RAW,
                archive=REAL_ARCHIVE,
                upstream_reference=recon.DEFAULT_UPSTREAM_REFERENCE,
            )
        # A divergent rerun must never publish a final adjudication.
        assert not (tmp_path / "adjudication.json").exists()
