"""Hardening tests for the SourceData provenance sidecar v0.2.0.

Written before implementation (TDD, PR #9 pre-merge hardening). Covers:
  - the corrected four-tier vocabulary (panel vs figure granularity);
  - the exact real-scale count decomposition 69983/175/3914/1091;
  - the strict versioned SidecarRow schema (extra=forbid, hash/enum gates);
  - the typed ProvenanceSidecarManifest model and its invariants;
  - archive extraction hardening (traversal, symlinks, quotas, ...);
  - deterministic dual-build equality and canonical input immutability.
"""

from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

import pytest
from pydantic import ValidationError

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
from ntruth.task_corpora.schemas import BuildManifest, ProvenanceSidecarManifest

EXPECTED_TIER_COUNTS = {
    "TIER_1_PANEL_UNIQUE": 69983,
    "TIER_1_FIGURE_UNIQUE": 175,
    "TIER_2_ARTICLE_ONLY": 3914,
    "RECORD_FALLBACK": 1091,
}
V01_STAGING_SIDECAR = Path(
    "/tmp/ntruth-sourcedata-provenance-sidecar-v1/staging/build-a/sidecar.jsonl"
)

XML_PANELS = """<article doi="10.1000/panels">
  <fig id="fig1"><label>Figure 1</label>
    <sd-panel panel_id="A"><sd-tag text="Panel A caption text."/></sd-panel>
    <sd-panel panel_id="B"><sd-tag text="Panel B caption text."/></sd-panel>
  </fig>
</article>
"""
XML_WHOLE_FIGURE = """<article doi="10.1000/panels">
  <fig id="fig9"><sd-tag text="Whole figure caption without panels."/></fig>
</article>
"""
XML_AMBIG = """<article doi="10.1000/panels">
  <fig id="fig2"><label>Figure 2</label>
    <sd-panel panel_id="A"><sd-tag text="Ambiguous shared caption."/></sd-panel>
    <sd-panel panel_id="B"><sd-tag text="Ambiguous shared caption."/></sd-panel>
  </fig>
</article>
"""

TOY_XML = {"a.xml": XML_PANELS, "b.xml": XML_WHOLE_FIGURE, "c.xml": XML_AMBIG}
TOY_RAW = {
    "train": [
        "Panel A caption text.",
        "Whole figure caption without panels.",
        "Ambiguous shared caption.",
        "Text with no upstream counterpart at all.",
    ],
    "validation": [],
    "test": [],
}


def _toy_index(tmp_path: Path) -> Path:
    xml_dir = tmp_path / "xml"
    xml_dir.mkdir(exist_ok=True)
    for name, content in sorted(TOY_XML.items()):
        (xml_dir / name).write_text(content, encoding="utf-8")
    out = tmp_path / "index.jsonl"
    with out.open("w", encoding="utf-8") as fh:
        for rec in iter_upstream_captions(xml_dir):
            fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
    return out


def _toy_layout(tmp_path: Path) -> dict[str, Path]:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(exist_ok=True)
    canon_dir = tmp_path / "corpus"
    canon_dir.mkdir(exist_ok=True)
    for part in ("train", "validation", "test"):
        texts = TOY_RAW.get(part, [])
        raw_lines = [json.dumps({"text": t, "words": t.split(), "labels": []}) for t in texts]
        (raw_dir / f"{part}.jsonl").write_text(
            "\n".join(raw_lines) + ("\n" if raw_lines else ""), encoding="utf-8"
        )
        canon_lines = [
            json.dumps(
                {
                    "record_id": f"entity_roles:sourcedata:sourcedata:0:{part}:{i}:1",
                    "task_type": "entity_roles",
                    "source": {
                        "dataset": "SourceData",
                        "version": "2.0.3",
                        "commit": "b457c14041b61c56f671c6f966b4324f682855b7",
                        "document_id": "",
                        "segment_id": f"sourcedata:0:{part}:{i}",
                        "source_record_id": f"sourcedata:0:{part}:{i}",
                    },
                    "split": part,
                    "payload": {
                        "kind": "entity_roles",
                        "tokens": [],
                        "entity_labels": [],
                        "role_labels": [],
                        "normalized_text": t,
                    },
                }
            )
            for i, t in enumerate(texts)
        ]
        (canon_dir / f"{part}.jsonl").write_text(
            "\n".join(canon_lines) + ("\n" if canon_lines else ""), encoding="utf-8"
        )
    return {"raw_dir": raw_dir, "canon_dir": canon_dir}


def _toy_build(tmp_path: Path) -> list[SidecarRow]:
    paths = _toy_layout(tmp_path)
    return build_sidecar_rows(
        index_path=_toy_index(tmp_path),
        raw_dir=paths["raw_dir"],
        canon_dir=paths["canon_dir"],
        upstream_asset_sha256="0" * 64,
        upstream_reference="ref",
    )


def _row_dict(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "schema_version": "0.2.0",
        "dataset_id": "SourceData",
        "dataset_version": "2.0.3",
        "task_corpus": "entity_roles",
        "partition": "train",
        "source_row_index": 0,
        "canonical_record_id": "rec:1",
        "exact_source_text_sha256": "a" * 64,
        "provenance_tier": "TIER_1_PANEL_UNIQUE",
        "granularity": "PANEL",
        "match_basis": "deterministic exact unique-panel assignment",
        "article_doi": "10.1000/a",
        "figure_id": "fig1",
        "panel_id": "A",
        "ambiguity_reason": None,
        "upstream_asset_sha256": "b" * 64,
        "upstream_reference": "ref",
        "matching_algorithm_version": "0.2.0",
    }
    base.update(overrides)
    return base


def _manifest_dict(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "status": "PARTIAL_DETERMINISTIC",
        "rows": 75163,
        "panel_unique": 69983,
        "figure_unique": 175,
        "article_only": 3914,
        "record_fallback": 1091,
        "map_sha256": "c" * 64,
        "schema_version": "0.2.0",
        "algorithm_version": "0.2.0",
        "upstream_xml_sha256": "d" * 64,
        "matched_subset_records": 74072,
        "matched_subset_articles": 3392,
        "matched_subset_articles_crossing_existing_splits": 0,
        "fallback_records_excluded_from_diagnostic": 1091,
        "embedded_document_id_present": 0,
        "global_paper_level_leakage_claim_allowed": False,
    }
    base.update(overrides)
    return base


class TestVersions:
    def test_schema_and_algorithm_versions_are_0_2_0(self) -> None:
        assert SCHEMA_VERSION == "0.2.0"
        assert ALGORITHM_VERSION == "0.2.0"


class TestCorrectedTierSemantics:
    def test_panel_tier_rejects_panel_id_null(self) -> None:
        with pytest.raises(ValidationError):
            SidecarRow(**_row_dict(panel_id=None))

    def test_figure_tier_requires_figure_id(self) -> None:
        with pytest.raises(ValidationError):
            SidecarRow(
                **_row_dict(
                    provenance_tier="TIER_1_FIGURE_UNIQUE",
                    granularity="FIGURE",
                    match_basis="deterministic exact unique-figure assignment",
                    figure_id=None,
                    panel_id=None,
                )
            )

    def test_figure_tier_requires_panel_id_null(self) -> None:
        with pytest.raises(ValidationError):
            SidecarRow(
                **_row_dict(
                    provenance_tier="TIER_1_FIGURE_UNIQUE",
                    granularity="FIGURE",
                    match_basis="deterministic exact unique-figure assignment",
                    figure_id="fig9",
                    panel_id="A",
                )
            )

    def test_figure_tier_rejected_when_official_panel_exists(self) -> None:
        cand = UpstreamCandidate("10.1000/a", "fig1", "A", "cap")
        d = decide_provenance("cap", (cand,), frozenset())
        fields = decision_to_row_fields(d)
        assert fields["provenance_tier"] == "TIER_1_PANEL_UNIQUE"
        assert fields["granularity"] == "PANEL"
        assert fields["panel_id"] == "A"

    def test_whole_figure_unit_maps_to_figure_tier(self) -> None:
        cand = UpstreamCandidate("10.1000/a", "fig9", "", "whole figure caption")
        d = decide_provenance("whole figure caption", (cand,), frozenset())
        fields = decision_to_row_fields(d)
        assert fields["provenance_tier"] == "TIER_1_FIGURE_UNIQUE"
        assert fields["granularity"] == "FIGURE"
        assert fields["figure_id"] == "fig9"
        assert fields["panel_id"] is None

    def test_article_tier_rejects_figure_id_and_panel_id(self) -> None:
        with pytest.raises(ValidationError):
            SidecarRow(
                **_row_dict(
                    provenance_tier="TIER_2_ARTICLE_ONLY",
                    granularity="ARTICLE",
                    match_basis="EXACT_SINGLE_ARTICLE_AMBIGUOUS_PANEL",
                    figure_id="fig1",
                    panel_id=None,
                )
            )
        with pytest.raises(ValidationError):
            SidecarRow(
                **_row_dict(
                    provenance_tier="TIER_2_ARTICLE_ONLY",
                    granularity="ARTICLE",
                    match_basis="EXACT_SINGLE_ARTICLE_AMBIGUOUS_PANEL",
                    figure_id=None,
                    panel_id="A",
                )
            )

    def test_fallback_rejects_every_upstream_identifier(self) -> None:
        for bad_key, bad_val in (
            ("article_doi", "10.1000/a"),
            ("figure_id", "fig1"),
            ("panel_id", "A"),
        ):
            entry = _row_dict(
                provenance_tier="RECORD_FALLBACK",
                granularity="RECORD_FALLBACK",
                match_basis=None,
                ambiguity_reason="UNMATCHED_NO_EVIDENCE",
                article_doi=None,
                figure_id=None,
                panel_id=None,
            )
            entry[bad_key] = bad_val
            with pytest.raises(ValidationError):
                SidecarRow(**entry)

    def test_toy_build_tier_assignment(self, tmp_path: Path) -> None:
        rows = _toy_build(tmp_path)
        tiers = [r.provenance_tier for r in rows]
        assert tiers == [
            "TIER_1_PANEL_UNIQUE",
            "TIER_1_FIGURE_UNIQUE",
            "TIER_2_ARTICLE_ONLY",
            "RECORD_FALLBACK",
        ]
        fig = rows[1]
        assert fig.granularity == "FIGURE"
        assert fig.figure_id == "fig9"
        assert fig.panel_id is None
        assert rows[0].granularity == "PANEL"
        assert rows[2].granularity == "ARTICLE"
        assert rows[3].granularity == "RECORD_FALLBACK"

    @pytest.mark.skipif(
        not V01_STAGING_SIDECAR.exists(),
        reason="requires the locally staged v0.1 real-scale sidecar (audit-only)",
    )
    def test_exact_real_scale_count_decomposition(self) -> None:
        """v0.1 payload decomposes exactly into the corrected four tiers."""
        rows = [json.loads(line) for line in V01_STAGING_SIDECAR.read_text().splitlines()]
        counts = {tier: 0 for tier in EXPECTED_TIER_COUNTS}
        for r in rows:
            tier = r["provenance_tier"]
            if tier == "TIER_1_PANEL_UNIQUE" and not r["panel_id"]:
                tier = "TIER_1_FIGURE_UNIQUE"
            counts[tier] += 1
        assert counts == EXPECTED_TIER_COUNTS
        assert sum(counts.values()) == 75163

    def test_validator_requires_four_tier_counts(self, tmp_path: Path) -> None:
        rows = _toy_build(tmp_path)
        payload = [json.loads(r.to_jsonl_bytes()) for r in rows]
        canon_ids = {r.canonical_record_id for r in rows}
        result = validate_sidecar_rows(payload, canonical_record_ids=canon_ids)
        assert set(result["tier_counts"]) == set(EXPECTED_TIER_COUNTS)


class TestStrictRowSchema:
    def test_rejects_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            SidecarRow(**_row_dict(unexpected_field="x"))

    def test_rejects_malformed_source_text_hash(self) -> None:
        for bad in ("A" * 64, "g" * 64, "a" * 63, "a" * 65, ""):
            with pytest.raises(ValidationError):
                SidecarRow(**_row_dict(exact_source_text_sha256=bad))

    def test_rejects_malformed_upstream_asset_hash(self) -> None:
        with pytest.raises(ValidationError):
            SidecarRow(**_row_dict(upstream_asset_sha256="B" * 64))

    def test_rejects_unsupported_schema_version(self) -> None:
        for bad in ("0.1.0", "0.2.1", "1.0.0", ""):
            with pytest.raises(ValidationError):
                SidecarRow(**_row_dict(schema_version=bad))

    def test_rejects_unsupported_algorithm_version(self) -> None:
        with pytest.raises(ValidationError):
            SidecarRow(**_row_dict(matching_algorithm_version="0.1.0"))

    def test_rejects_unknown_partition(self) -> None:
        with pytest.raises(ValidationError):
            SidecarRow(**_row_dict(partition="trial"))

    def test_rejects_negative_row_index(self) -> None:
        with pytest.raises(ValidationError):
            SidecarRow(**_row_dict(source_row_index=-1))

    def test_rejects_empty_canonical_record_id(self) -> None:
        with pytest.raises(ValidationError):
            SidecarRow(**_row_dict(canonical_record_id=""))

    def test_rejects_wrong_dataset_identity(self) -> None:
        with pytest.raises(ValidationError):
            SidecarRow(**_row_dict(dataset_id="Other"))
        with pytest.raises(ValidationError):
            SidecarRow(**_row_dict(dataset_version="2.0.2"))
        with pytest.raises(ValidationError):
            SidecarRow(**_row_dict(task_corpus="other_corpus"))

    def test_rejects_unknown_tier(self) -> None:
        with pytest.raises(ValidationError):
            SidecarRow(**_row_dict(provenance_tier="TIER_1_WHOLE_FIGURE"))

    def test_rejects_wrong_granularity_for_tier(self) -> None:
        with pytest.raises(ValidationError):
            SidecarRow(**_row_dict(granularity="FIGURE"))


class TestTypedManifestModel:
    def test_valid_manifest_parses(self) -> None:
        m = ProvenanceSidecarManifest(**_manifest_dict())
        assert m.rows == 75163
        assert m.matched_subset_records == 74072

    def test_rejects_missing_fields(self) -> None:
        d = _manifest_dict()
        for key in list(d):
            partial = {k: v for k, v in d.items() if k != key}
            with pytest.raises(ValidationError):
                ProvenanceSidecarManifest(**partial)

    def test_rejects_unknown_fields(self) -> None:
        with pytest.raises(ValidationError):
            ProvenanceSidecarManifest(**_manifest_dict(extra_key=1))

    def test_rejects_inconsistent_totals(self) -> None:
        with pytest.raises(ValidationError):
            ProvenanceSidecarManifest(**_manifest_dict(panel_unique=69982))

    def test_rejects_wrong_row_total(self) -> None:
        with pytest.raises(ValidationError):
            ProvenanceSidecarManifest(**_manifest_dict(rows=75164))

    def test_rejects_inconsistent_matched_subset(self) -> None:
        with pytest.raises(ValidationError):
            ProvenanceSidecarManifest(**_manifest_dict(matched_subset_records=74071))

    def test_rejects_inconsistent_fallback_exclusion(self) -> None:
        with pytest.raises(ValidationError):
            ProvenanceSidecarManifest(
                **_manifest_dict(fallback_records_excluded_from_diagnostic=1090)
            )

    def test_rejects_paper_level_claim_true(self) -> None:
        with pytest.raises(ValidationError):
            ProvenanceSidecarManifest(
                **_manifest_dict(global_paper_level_leakage_claim_allowed=True)
            )

    def test_rejects_embedded_document_id_present_nonzero(self) -> None:
        with pytest.raises(ValidationError):
            ProvenanceSidecarManifest(**_manifest_dict(embedded_document_id_present=74072))

    def test_rejects_wrong_status(self) -> None:
        with pytest.raises(ValidationError):
            ProvenanceSidecarManifest(**_manifest_dict(status="FULL_DETERMINISTIC"))

    def test_rejects_malformed_sha_fields(self) -> None:
        with pytest.raises(ValidationError):
            ProvenanceSidecarManifest(**_manifest_dict(map_sha256="X" * 64))
        with pytest.raises(ValidationError):
            ProvenanceSidecarManifest(**_manifest_dict(upstream_xml_sha256="y" * 63))

    def test_build_manifest_uses_typed_model(self) -> None:
        base = {
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
        m = BuildManifest(**base, manifest_version="0.3.0", provenance_sidecar=_manifest_dict())
        assert isinstance(m.provenance_sidecar, ProvenanceSidecarManifest)
        old = BuildManifest(**base)
        assert old.provenance_sidecar is None
        assert old.manifest_version == "0.2.2"
        with pytest.raises(ValidationError):
            BuildManifest(
                **base,
                manifest_version="0.3.0",
                provenance_sidecar=_manifest_dict(rows=1),
            )


def _tar_bytes(make: object) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        make(tar)
    return buf.getvalue()


def _add_file(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name=name)
    info.size = len(data)
    tar.addfile(info, io.BytesIO(data))


class TestExtractionHardening:
    def _extract(self, tmp_path: Path, blob: bytes, **kw: object) -> Path:
        archive = tmp_path / "a.tar.gz"
        archive.write_bytes(blob)
        dest = tmp_path / "xml"
        extract_xml_archive(archive, dest, expected_sha256=sha256_bytes(blob), **kw)
        return dest

    def test_valid_archive_extracts(self, tmp_path: Path) -> None:
        blob = _tar_bytes(lambda t: _add_file(t, "a.xml", b"<article/>"))
        dest = self._extract(tmp_path, blob)
        assert (dest / "a.xml").read_bytes() == b"<article/>"

    def test_corrupt_archive_fails_at_tar_read_after_sha_gate(self, tmp_path: Path) -> None:
        """Truncated bytes hash-match their own expected SHA: the failure must
        come from the tar/gzip read AFTER the hash gate, not from a mismatch."""
        blob = _tar_bytes(lambda t: _add_file(t, "a.xml", b"<article/>"))
        truncated = blob[: len(blob) // 2]
        archive = tmp_path / "bad.tar.gz"
        archive.write_bytes(truncated)
        with pytest.raises(ValueError, match="unreadable provenance archive"):
            extract_xml_archive(archive, tmp_path / "xml", expected_sha256=sha256_bytes(truncated))
        assert not (tmp_path / "xml").exists()

    def test_sha_mismatch_refused_before_tar_read(self, tmp_path: Path) -> None:
        blob = _tar_bytes(lambda t: _add_file(t, "a.xml", b"<article/>"))
        archive = tmp_path / "bad.tar.gz"
        archive.write_bytes(blob[: len(blob) // 2])
        with pytest.raises(ValueError, match="sha256 mismatch"):
            extract_xml_archive(archive, tmp_path / "xml", expected_sha256=sha256_bytes(blob))

    def test_stale_destination_refused(self, tmp_path: Path) -> None:
        blob = _tar_bytes(lambda t: _add_file(t, "a.xml", b"<article/>"))
        dest = tmp_path / "xml"
        dest.mkdir()
        (dest / "stale.txt").write_text("old")
        archive = tmp_path / "a.tar.gz"
        archive.write_bytes(blob)
        with pytest.raises(ValueError, match=r"[Ss]tale|populated|exists"):
            extract_xml_archive(archive, dest, expected_sha256=sha256_bytes(blob))
        assert (dest / "stale.txt").exists(), "stale destination must not be mutated"

    def test_traversal_rejected(self, tmp_path: Path) -> None:
        def make(t: tarfile.TarFile) -> None:
            _add_file(t, "../evil.xml", b"<article/>")

        blob = _tar_bytes(make)
        archive = tmp_path / "a.tar.gz"
        archive.write_bytes(blob)
        with pytest.raises(ValueError):
            extract_xml_archive(archive, tmp_path / "xml", expected_sha256=sha256_bytes(blob))
        assert not (tmp_path / "evil.xml").exists()

    def test_absolute_path_rejected(self, tmp_path: Path) -> None:
        def make(t: tarfile.TarFile) -> None:
            _add_file(t, "/tmp/evil.xml", b"<article/>")

        blob = _tar_bytes(make)
        archive = tmp_path / "a.tar.gz"
        archive.write_bytes(blob)
        with pytest.raises(ValueError):
            extract_xml_archive(archive, tmp_path / "xml", expected_sha256=sha256_bytes(blob))

    def test_symlink_rejected(self, tmp_path: Path) -> None:
        def make(t: tarfile.TarFile) -> None:
            info = tarfile.TarInfo(name="link.xml")
            info.type = tarfile.SYMTYPE
            info.linkname = "/etc/passwd"
            t.addfile(info)

        blob = _tar_bytes(make)
        archive = tmp_path / "a.tar.gz"
        archive.write_bytes(blob)
        with pytest.raises(ValueError):
            extract_xml_archive(archive, tmp_path / "xml", expected_sha256=sha256_bytes(blob))

    def test_hardlink_rejected(self, tmp_path: Path) -> None:
        def make(t: tarfile.TarFile) -> None:
            _add_file(t, "a.xml", b"<article/>")
            info = tarfile.TarInfo(name="b.xml")
            info.type = tarfile.LNKTYPE
            info.linkname = "a.xml"
            t.addfile(info)

        blob = _tar_bytes(make)
        archive = tmp_path / "a.tar.gz"
        archive.write_bytes(blob)
        with pytest.raises(ValueError):
            extract_xml_archive(archive, tmp_path / "xml", expected_sha256=sha256_bytes(blob))

    def test_duplicate_basename_rejected(self, tmp_path: Path) -> None:
        def make(t: tarfile.TarFile) -> None:
            _add_file(t, "x/a.xml", b"<article/>")
            _add_file(t, "y/a.xml", b"<article/>")

        blob = _tar_bytes(make)
        archive = tmp_path / "a.tar.gz"
        archive.write_bytes(blob)
        with pytest.raises(ValueError):
            extract_xml_archive(archive, tmp_path / "xml", expected_sha256=sha256_bytes(blob))

    def test_oversized_file_rejected(self, tmp_path: Path) -> None:
        blob = _tar_bytes(lambda t: _add_file(t, "big.xml", b"x" * 2048))
        archive = tmp_path / "a.tar.gz"
        archive.write_bytes(blob)
        with pytest.raises(ValueError):
            extract_xml_archive(
                archive,
                tmp_path / "xml",
                expected_sha256=sha256_bytes(blob),
                max_file_bytes=1024,
            )

    def test_excessive_total_rejected(self, tmp_path: Path) -> None:
        def make(t: tarfile.TarFile) -> None:
            _add_file(t, "a.xml", b"x" * 900)
            _add_file(t, "b.xml", b"x" * 900)

        blob = _tar_bytes(make)
        archive = tmp_path / "a.tar.gz"
        archive.write_bytes(blob)
        with pytest.raises(ValueError):
            extract_xml_archive(
                archive,
                tmp_path / "xml",
                expected_sha256=sha256_bytes(blob),
                max_total_bytes=1000,
            )

    def test_excessive_file_count_rejected(self, tmp_path: Path) -> None:
        def make(t: tarfile.TarFile) -> None:
            for i in range(3):
                _add_file(t, f"f{i}.xml", b"<article/>")

        blob = _tar_bytes(make)
        archive = tmp_path / "a.tar.gz"
        archive.write_bytes(blob)
        with pytest.raises(ValueError):
            extract_xml_archive(
                archive,
                tmp_path / "xml",
                expected_sha256=sha256_bytes(blob),
                max_files=2,
            )

    def test_non_xml_payload_ignored(self, tmp_path: Path) -> None:
        # The official archive carries benign non-XML payloads (jsonl exports
        # under sibling directories); they are fail-closed IGNORED, never
        # extracted, while every hostile member class stays rejected.
        def make(t: tarfile.TarFile) -> None:
            _add_file(t, "a.xml", b"<article/>")
            _add_file(t, "other/payload.jsonl", b"{}")

        blob = _tar_bytes(make)
        dest = self._extract(tmp_path, blob)
        assert sorted(p.name for p in dest.iterdir()) == ["a.xml"]

    def test_directory_member_tolerated(self, tmp_path: Path) -> None:
        # The official archive carries a directory member; benign directory
        # entries are tolerated while every hostile member class stays
        # rejected.
        def make(t: tarfile.TarFile) -> None:
            info = tarfile.TarInfo(name="sub/")
            info.type = tarfile.DIRTYPE
            t.addfile(info)
            _add_file(t, "sub/a.xml", b"<article/>")

        blob = _tar_bytes(make)
        dest = self._extract(tmp_path, blob)
        assert (dest / "a.xml").read_bytes() == b"<article/>"

    def test_partial_output_removed_on_failure(self, tmp_path: Path) -> None:
        def make(t: tarfile.TarFile) -> None:
            _add_file(t, "a.xml", b"<article/>")
            _add_file(t, "bad.xml", b"x" * 4096)

        blob = _tar_bytes(make)
        archive = tmp_path / "a.tar.gz"
        archive.write_bytes(blob)
        with pytest.raises(ValueError):
            extract_xml_archive(
                archive,
                tmp_path / "xml",
                expected_sha256=sha256_bytes(blob),
                max_file_bytes=1024,
            )
        assert not (tmp_path / "xml").exists(), "failed extraction must leave no output"
        leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".xml")]
        assert leftovers == []


class TestHardeningDeterminism:
    def test_dual_build_byte_identical(self, tmp_path: Path) -> None:
        rows_a = _toy_build(tmp_path)
        rows_b = _toy_build(tmp_path)
        assert b"".join(r.to_jsonl_bytes() for r in rows_a) == b"".join(
            r.to_jsonl_bytes() for r in rows_b
        )

    def test_canonical_inputs_untouched(self, tmp_path: Path) -> None:
        paths = _toy_layout(tmp_path)
        before = (paths["canon_dir"] / "train.jsonl").read_bytes()
        _toy_build(tmp_path)
        assert (paths["canon_dir"] / "train.jsonl").read_bytes() == before


class TestSidecarRejectionOfV01Rows:
    def test_v01_schema_version_rejected_by_strict_row(self) -> None:
        with pytest.raises(ValidationError):
            SidecarRow(**_row_dict(schema_version="0.1.0"))

    def test_validator_rejects_figure_row_labelled_panel_tier(self) -> None:
        # A whole-figure unit labelled TIER_1_PANEL_UNIQUE without panel_id was
        # legal under v0.1 semantics and must now be rejected.
        entry = _row_dict(
            provenance_tier="TIER_1_PANEL_UNIQUE",
            granularity="PANEL",
            panel_id=None,
        )
        with pytest.raises((ValidationError, SidecarValidationError)):
            validate_sidecar_rows([dict(entry)], canonical_record_ids={"rec:1"})
