"""Tests for the SourceData deterministic provenance sidecar builder.

Written before implementation (TDD). Covers the sidecar key contract, schema
invariants, deterministic dual-build equality, manifest backward compatibility
and fail-closed input verification.
"""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
from pathlib import Path
from typing import ClassVar

import pytest

from ntruth.task_corpora.provenance_join import UpstreamCandidate, decide_provenance
from ntruth.task_corpora.provenance_sidecar import (
    ALGORITHM_VERSION,
    SCHEMA_VERSION,
    SidecarRow,
    SidecarValidationError,
    build_sidecar_rows,
    decision_to_row_fields,
    extract_xml_archive,
    iter_upstream_captions,
    sha256_bytes,
    validate_sidecar_rows,
)
from ntruth.task_corpora.schemas import BuildManifest

XML_ARTICLE = """<article doi="10.15252/embr.202153809">
  <fig id="fig1"><label>Figure 1</label>
    <sd-panel panel_id="A"><sd-tag text="LXR alpha expression in liver."/></sd-panel>
    <sd-panel panel_id="B"><sd-tag text="Western blot of LXR alpha in LV tissue."/></sd-panel>
  </fig>
</article>
"""
XML_DUP = """<article doi="10.1000/dup">
  <fig id="fig2"><label>Figure 2</label>
    <sd-panel panel_id="A"><sd-tag text="Shared caption across panels."/></sd-panel>
    <sd-panel panel_id="B"><sd-tag text="Shared caption across panels."/></sd-panel>
  </fig>
</article>
"""
XML_MULTI_DOI = """<article doi="10.2000/other">
  <fig id="fig3"><label>Figure 3</label>
    <sd-panel panel_id="A"><sd-tag text="Shared caption across panels."/></sd-panel>
  </fig>
</article>
"""


def _make_archive(articles: dict[str, str], *, corrupt: bool = False) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, content in sorted(articles.items()):
            data = content.encode("utf-8")
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    blob = buf.getvalue()
    return blob[: len(blob) // 2] if corrupt else blob


ARCHIVE = _make_archive({"a.xml": XML_ARTICLE, "b.xml": XML_DUP, "c.xml": XML_MULTI_DOI})
ARCHIVE_SHA = sha256_bytes(ARCHIVE)


def _raw_line(text: str) -> str:
    return json.dumps({"text": text, "words": text.split(), "labels": []})


def _canonical_line(part: str, idx: int, text_norm: str) -> str:
    rec = {
        "record_id": f"entity_roles:sourcedata:sourcedata:0:{part}:{idx}:1",
        "task_type": "entity_roles",
        "source": {
            "dataset": "SourceData",
            "version": "2.0.3",
            "commit": "b457c14041b61c56f671c6f966b4324f682855b7",
            "document_id": "",
            "segment_id": f"sourcedata:0:{part}:{idx}",
            "source_record_id": f"sourcedata:0:{part}:{idx}",
        },
        "split": part,
        "payload": {
            "kind": "entity_roles",
            "tokens": [],
            "entity_labels": [],
            "role_labels": [],
            "normalized_text": text_norm,
        },
    }
    return json.dumps(rec)


def _layout(tmp_path: Path, raw_texts: dict[str, list[str]]) -> dict[str, Path]:
    """Create raw roles_multi + canonical corpus files for a build."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(exist_ok=True)
    canon_dir = tmp_path / "corpus"
    canon_dir.mkdir(exist_ok=True)
    for part in ("train", "validation", "test"):
        texts = raw_texts.get(part, [])
        (raw_dir / f"{part}.jsonl").write_text(
            "\n".join(_raw_line(t) for t in texts) + ("\n" if texts else ""),
            encoding="utf-8",
        )
        (canon_dir / f"{part}.jsonl").write_text(
            "\n".join(_canonical_line(part, i, t) for i, t in enumerate(texts))
            + ("\n" if texts else ""),
            encoding="utf-8",
        )
    return {"raw_dir": raw_dir, "canon_dir": canon_dir}


RAW_TEXTS = {
    "train": [
        "LXR alpha expression in liver.",
        "Shared caption across panels.",
        "Unique sentence with no upstream counterpart anywhere.",
    ],
    "validation": ["Short."],
    "test": ["Western blot of LXR alpha in LV tissue."],
}


def _write_index(tmp_path: Path) -> Path:
    xml_dir = tmp_path / "xml"
    xml_dir.mkdir(exist_ok=True)
    for name, content in (("a.xml", XML_ARTICLE), ("b.xml", XML_DUP), ("c.xml", XML_MULTI_DOI)):
        (xml_dir / name).write_text(content, encoding="utf-8")
    out = tmp_path / "index.jsonl"
    with out.open("w", encoding="utf-8") as fh:
        for rec in iter_upstream_captions(xml_dir):
            fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    return out


def _build(tmp_path: Path):
    paths = _layout(tmp_path, RAW_TEXTS)
    index = _write_index(tmp_path)
    rows = build_sidecar_rows(
        index_path=index,
        raw_dir=paths["raw_dir"],
        canon_dir=paths["canon_dir"],
        upstream_asset_sha256=ARCHIVE_SHA,
        upstream_reference="https://huggingface.co/datasets/EMBO/SourceData@04333ae2",
    )
    return paths, rows


class TestArchiveExtraction:
    def test_extract_round_trip(self, tmp_path: Path) -> None:
        archive = tmp_path / "a.tar.gz"
        archive.write_bytes(ARCHIVE)
        dest = tmp_path / "xml"
        extract_xml_archive(archive, dest, expected_sha256=ARCHIVE_SHA)
        assert sorted(p.name for p in dest.glob("*.xml")) == ["a.xml", "b.xml", "c.xml"]

    def test_corrupted_archive_fails(self, tmp_path: Path) -> None:
        archive = tmp_path / "bad.tar.gz"
        archive.write_bytes(_make_archive({"a.xml": XML_ARTICLE}, corrupt=True))
        with pytest.raises(ValueError):
            extract_xml_archive(archive, tmp_path / "xml", expected_sha256=ARCHIVE_SHA)

    def test_hash_mismatch_fails(self, tmp_path: Path) -> None:
        archive = tmp_path / "a.tar.gz"
        archive.write_bytes(ARCHIVE)
        with pytest.raises(ValueError, match="sha256"):
            extract_xml_archive(archive, tmp_path / "xml", expected_sha256="0" * 64)


class TestKeyContract:
    def test_one_row_per_canonical_record_unique_keys(self, tmp_path: Path) -> None:
        _, rows = _build(tmp_path)
        assert len(rows) == 5
        keys = [r.canonical_record_id for r in rows]
        assert len(set(keys)) == 5

    def test_exact_text_hash_is_original_not_normalized(self, tmp_path: Path) -> None:
        _, rows = _build(tmp_path)
        expected = hashlib.sha256(b"LXR alpha expression in liver.").hexdigest()
        assert rows[0].exact_source_text_sha256 == expected

    def test_exact_text_hash_stable_across_rebuilds(self, tmp_path: Path) -> None:
        _, rows_a = _build(tmp_path)
        _, rows_b = _build(tmp_path)
        assert [r.exact_source_text_sha256 for r in rows_a] == [
            r.exact_source_text_sha256 for r in rows_b
        ]

    def test_row_never_keyed_by_bare_row_number(self, tmp_path: Path) -> None:
        _, rows = _build(tmp_path)
        for r in rows:
            assert r.dataset_id == "SourceData"
            assert r.dataset_version == "2.0.3"
            assert r.partition in {"train", "validation", "test"}
            assert r.source_row_index >= 0


class TestTierInvariants:
    def test_tier1_full_identifiers(self, tmp_path: Path) -> None:
        _, rows = _build(tmp_path)
        r = rows[0]
        assert r.provenance_tier == "TIER_1_PANEL_UNIQUE"
        assert r.article_doi == "10.15252/embr.202153809"
        assert r.figure_id == "fig1"
        assert r.panel_id == "A"
        assert r.match_basis == "deterministic exact unique-panel assignment"
        assert r.ambiguity_reason is None

    def test_article_only_never_serialized_as_panel(self, tmp_path: Path) -> None:
        _, rows = _build(tmp_path)
        for row in rows:
            if row.provenance_tier == "TIER_2_ARTICLE_ONLY":
                assert row.panel_id is None
                assert row.match_basis in {
                    "EXACT_SINGLE_ARTICLE_AMBIGUOUS_PANEL",
                    "CONTAINMENT_SINGLE_ARTICLE",
                }

    def test_fallback_rows_have_no_upstream_identifiers(self, tmp_path: Path) -> None:
        _, rows = _build(tmp_path)
        for row in rows:
            if row.provenance_tier == "RECORD_FALLBACK":
                assert row.article_doi is None
                assert row.figure_id is None
                assert row.panel_id is None
                assert row.ambiguity_reason

    def test_tier2_ambiguous_panel_within_single_article(self, tmp_path: Path) -> None:
        # Remove the multi-DOI duplicate so the shared caption is single-article ambiguous.
        texts = dict(RAW_TEXTS)
        paths = _layout(tmp_path, texts)
        xml_dir = tmp_path / "xml"
        xml_dir.mkdir(exist_ok=True)
        (xml_dir / "b.xml").write_text(XML_DUP, encoding="utf-8")
        index = tmp_path / "index.jsonl"
        with index.open("w", encoding="utf-8") as fh:
            for rec in iter_upstream_captions(xml_dir):
                fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
        rows = build_sidecar_rows(
            index_path=index,
            raw_dir=paths["raw_dir"],
            canon_dir=paths["canon_dir"],
            upstream_asset_sha256=ARCHIVE_SHA,
            upstream_reference="ref",
        )
        r = next(r for r in rows if r.source_row_index == 1 and r.partition == "train")
        assert r.provenance_tier == "TIER_2_ARTICLE_ONLY"
        assert r.match_basis == "EXACT_SINGLE_ARTICLE_AMBIGUOUS_PANEL"
        assert r.panel_id is None

    def test_multi_doi_caption_remains_fallback(self, tmp_path: Path) -> None:
        _, rows = _build(tmp_path)
        r = rows[1]
        assert r.provenance_tier == "RECORD_FALLBACK"
        assert r.ambiguity_reason == "UNMATCHED_MULTI_DOI"


class TestDeterminism:
    def test_dual_build_byte_identical(self, tmp_path: Path) -> None:
        _, rows_a = _build(tmp_path)
        _, rows_b = _build(tmp_path)
        bytes_a = b"".join(r.to_jsonl_bytes() for r in rows_a)
        bytes_b = b"".join(r.to_jsonl_bytes() for r in rows_b)
        assert bytes_a == bytes_b
        assert sha256_bytes(bytes_a) == sha256_bytes(bytes_b)

    def test_ordering_is_partition_then_row_index(self, tmp_path: Path) -> None:
        _, rows = _build(tmp_path)
        partitions = [r.partition for r in rows]
        assert partitions == ["train"] * 3 + ["validation"] + ["test"]
        for part in ("train", "validation", "test"):
            idx = [r.source_row_index for r in rows if r.partition == part]
            assert idx == sorted(idx)


class TestInputVerification:
    def test_input_records_hash_mismatch_fails(self, tmp_path: Path) -> None:
        paths = _layout(tmp_path, RAW_TEXTS)
        index = _write_index(tmp_path)
        with pytest.raises(ValueError, match="records_sha256"):
            build_sidecar_rows(
                index_path=index,
                raw_dir=paths["raw_dir"],
                canon_dir=paths["canon_dir"],
                upstream_asset_sha256=ARCHIVE_SHA,
                upstream_reference="ref",
                expected_records_sha256="f" * 64,
            )

    def test_raw_text_hash_mismatch_fails(self, tmp_path: Path) -> None:
        paths = _layout(tmp_path, RAW_TEXTS)
        index = _write_index(tmp_path)
        with pytest.raises(ValueError, match="raw"):
            build_sidecar_rows(
                index_path=index,
                raw_dir=paths["raw_dir"],
                canon_dir=paths["canon_dir"],
                upstream_asset_sha256=ARCHIVE_SHA,
                upstream_reference="ref",
                expected_raw_sha256={"train": "0" * 64},
            )


class TestSidecarValidation:
    def test_validate_round_trip(self, tmp_path: Path) -> None:
        _, rows = _build(tmp_path)
        payload = [json.loads(line) for r in rows for line in [r.to_jsonl_bytes().decode()]]
        canon_ids = {r.canonical_record_id for r in rows}
        validated = validate_sidecar_rows(payload, canonical_record_ids=canon_ids)
        assert validated["rows"] == 5
        assert validated["duplicate_keys"] == 0

    def test_validate_rejects_invented_panel_on_article_only(self) -> None:
        row = SidecarRow(
            schema_version=SCHEMA_VERSION,
            dataset_id="SourceData",
            dataset_version="2.0.3",
            task_corpus="entity_roles",
            partition="train",
            source_row_index=0,
            canonical_record_id="x",
            exact_source_text_sha256="0" * 64,
            provenance_tier="TIER_2_ARTICLE_ONLY",
            match_basis="EXACT_SINGLE_ARTICLE_AMBIGUOUS_PANEL",
            article_doi="10.1000/a",
            figure_id=None,
            panel_id="A",
            ambiguity_reason=None,
            upstream_asset_sha256="0" * 64,
            upstream_reference="ref",
            matching_algorithm_version=ALGORITHM_VERSION,
        )
        with pytest.raises(SidecarValidationError):
            validate_sidecar_rows([row.model_dump()], canonical_record_ids={"x"})

    def test_validate_rejects_fallback_with_doi(self) -> None:
        row = SidecarRow(
            schema_version=SCHEMA_VERSION,
            dataset_id="SourceData",
            dataset_version="2.0.3",
            task_corpus="entity_roles",
            partition="train",
            source_row_index=0,
            canonical_record_id="x",
            exact_source_text_sha256="0" * 64,
            provenance_tier="RECORD_FALLBACK",
            match_basis=None,
            article_doi="10.1000/a",
            figure_id=None,
            panel_id=None,
            ambiguity_reason="UNMATCHED_NO_EVIDENCE",
            upstream_asset_sha256="0" * 64,
            upstream_reference="ref",
            matching_algorithm_version=ALGORITHM_VERSION,
        )
        with pytest.raises(SidecarValidationError):
            validate_sidecar_rows([row.model_dump()], canonical_record_ids={"x"})


class TestManifestBackwardCompatibility:
    BASE: ClassVar[dict[str, object]] = {
        "task_type": "entity_roles",
        "source_dataset": "SourceData",
        "source_version": "2.0.3",
        "adapter": "sourcedata_entity_roles",
        "schema_version": "0.2.0",
        "transform_version": "0.2.0",
        "mapping_version": "0.1.0",
        "seed": "20260803",
        "root": "/tmp/x",
        "output_dir": "task_corpora/entity_roles/sourcedata/v2.0.3",
        "record_counts": {"train": 1, "validation": 1, "test": 1},
        "exclusion_counts": {},
        "records_sha256": "0" * 64,
        "groups_crossing_splits": 0,
    }

    def test_old_manifest_still_parses(self) -> None:
        m = BuildManifest(**self.BASE)
        assert m.provenance_sidecar is None
        assert m.manifest_version == "0.2.2"

    def test_sidecar_block_parses_additively(self) -> None:
        m = BuildManifest(
            **self.BASE,
            manifest_version="0.3.0",
            provenance_sidecar={
                "provenance_sidecar_status": "PARTIAL_DETERMINISTIC",
                "provenance_sidecar_rows": 75163,
                "provenance_panel_unique": 70158,
                "provenance_article_only": 3914,
                "provenance_record_fallback": 1091,
                "provenance_map_sha256": "a" * 64,
                "provenance_schema_version": SCHEMA_VERSION,
                "provenance_algorithm_version": ALGORITHM_VERSION,
                "upstream_xml_sha256": "b" * 64,
                "matched_subset_articles_crossing_existing_splits": 0,
                "fallback_records_excluded_from_diagnostic": 1091,
            },
        )
        assert m.provenance_sidecar is not None
        assert m.provenance_sidecar["provenance_sidecar_rows"] == 75163

    def test_paper_level_claim_stays_false(self) -> None:
        m = BuildManifest(**self.BASE, paper_level_leakage_claim_allowed=False)
        assert m.paper_level_leakage_claim_allowed is False


class TestDecisionMapping:
    def test_exact_precedence_over_containment(self) -> None:
        cand = UpstreamCandidate("10.1000/a", "fig1", "A", "cap")
        d = decide_provenance("cap", (cand,), frozenset({"10.2000/b"}))
        fields = decision_to_row_fields(d)
        assert fields["provenance_tier"] == "TIER_1_PANEL_UNIQUE"

    def test_malformed_doi_rejected(self) -> None:
        cand = UpstreamCandidate("not-a-doi", "fig1", "A", "cap")
        d = decide_provenance("cap", (cand,), frozenset())
        fields = decision_to_row_fields(d)
        assert fields["provenance_tier"] == "RECORD_FALLBACK"
        assert fields["article_doi"] is None

    def test_unique_figure_unit_keeps_tier1_without_invented_panel(self) -> None:
        # Upstream figures without sd-panel elements are whole-figure units:
        # unique provenance is kept, but no panel identifier is invented.
        cand = UpstreamCandidate("10.1000/a", "fig7", "", "whole figure caption")
        d = decide_provenance("whole figure caption", (cand,), frozenset())
        fields = decision_to_row_fields(d)
        assert fields["provenance_tier"] == "TIER_1_PANEL_UNIQUE"
        assert fields["figure_id"] == "fig7"
        assert fields["panel_id"] is None

    def test_validate_accepts_figure_unit_tier1_row(self) -> None:
        row = SidecarRow(
            schema_version=SCHEMA_VERSION,
            dataset_id="SourceData",
            dataset_version="2.0.3",
            task_corpus="entity_roles",
            partition="train",
            source_row_index=0,
            canonical_record_id="x",
            exact_source_text_sha256="0" * 64,
            provenance_tier="TIER_1_PANEL_UNIQUE",
            match_basis="deterministic exact unique-panel assignment",
            article_doi="10.1000/a",
            figure_id="fig7",
            panel_id=None,
            ambiguity_reason=None,
            upstream_asset_sha256="0" * 64,
            upstream_reference="ref",
            matching_algorithm_version=ALGORITHM_VERSION,
        )
        result = validate_sidecar_rows([row.model_dump()], canonical_record_ids={"x"})
        assert result["rows"] == 1

    def test_validate_rejects_tier1_without_any_official_unit(self) -> None:
        row = SidecarRow(
            schema_version=SCHEMA_VERSION,
            dataset_id="SourceData",
            dataset_version="2.0.3",
            task_corpus="entity_roles",
            partition="train",
            source_row_index=0,
            canonical_record_id="x",
            exact_source_text_sha256="0" * 64,
            provenance_tier="TIER_1_PANEL_UNIQUE",
            match_basis="deterministic exact unique-panel assignment",
            article_doi="10.1000/a",
            figure_id=None,
            panel_id=None,
            ambiguity_reason=None,
            upstream_asset_sha256="0" * 64,
            upstream_reference="ref",
            matching_algorithm_version=ALGORITHM_VERSION,
        )
        with pytest.raises(SidecarValidationError):
            validate_sidecar_rows([row.model_dump()], canonical_record_ids={"x"})


class TestRecordSerializationUntouched:
    def test_build_does_not_rewrite_inputs(self, tmp_path: Path) -> None:
        paths, _ = _build(tmp_path)
        before = (paths["canon_dir"] / "train.jsonl").read_bytes()
        paths2, _ = _build(tmp_path)
        assert (paths2["canon_dir"] / "train.jsonl").read_bytes() == before
