"""Tests-first for the PR #9 CodeRabbit remediation (findings A-G) and the
§5 root/volume compatibility regression test.

All tests are written against the REMEDIATED contract; they fail against the
pre-remediation implementation (ImportError / ValidationError gaps).
"""

from __future__ import annotations

import json
import tarfile
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from ntruth.task_corpora.provenance_sidecar import (
    ArchiveExtractionError,
    ProvenanceBuildInputs,
    SidecarValidationError,
    abort_build_report,
    extract_xml_archive,
    publish_build_report,
    sha256_bytes,
    sha256_file,
    verify_provenance_build_inputs,
)
from ntruth.task_corpora.schemas import BuildManifest, ProvenanceSidecarManifest

ZERO_SHA = "0" * 64

ATTESTED = {
    "canonical_records_sha256": ZERO_SHA,
    "canonical_train_sha256": "a" * 64,
    "canonical_validation_sha256": "b" * 64,
    "canonical_test_sha256": "c" * 64,
    "raw_roles_train_sha256": "d" * 64,
    "raw_roles_validation_sha256": "e" * 64,
    "raw_roles_test_sha256": "f" * 64,
    "leakage_audit_sha256": "1" * 64,
    "upstream_xml_sha256": "2" * 64,
    "resolvable_upstream_reference": "https://huggingface.co/datasets/EMBO/SourceData/tree/x",
    "dataset_version": "2.0.3",
    "sidecar_schema_version": "0.2.0",
    "matching_algorithm_version": "0.2.0",
}


def _bundle(**overrides: object) -> ProvenanceBuildInputs:
    payload = dict(ATTESTED)
    payload.update(overrides)
    return ProvenanceBuildInputs.model_validate(payload)


class TestFindingBInputBundleContract:
    def test_all_thirteen_attested_fields_required(self) -> None:
        bundle = _bundle()
        for field in ATTESTED:
            assert field in bundle.model_fields
        assert len(bundle.model_dump()) == 13

    def test_unknown_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _bundle(unexpected_field="x")

    def test_missing_field_rejected(self) -> None:
        payload = dict(ATTESTED)
        del payload["leakage_audit_sha256"]
        with pytest.raises(ValidationError):
            ProvenanceBuildInputs.model_validate(payload)

    @pytest.mark.parametrize(
        "field",
        [
            "canonical_records_sha256",
            "canonical_train_sha256",
            "raw_roles_test_sha256",
            "leakage_audit_sha256",
            "upstream_xml_sha256",
        ],
    )
    def test_invalid_sha_rejected(self, field: str) -> None:
        for bad in ("", "xyz", "A" * 64, "0" * 63, "0" * 65):
            with pytest.raises(ValidationError):
                _bundle(**{field: bad})

    def test_reference_must_be_resolvable_https(self) -> None:
        for bad in ("", "ftp://example.org", "http://example.org", "not-a-url"):
            with pytest.raises(ValidationError):
                _bundle(resolvable_upstream_reference=bad)

    def test_version_literals_pinned(self) -> None:
        with pytest.raises(ValidationError):
            _bundle(dataset_version="2.0.2")
        with pytest.raises(ValidationError):
            _bundle(sidecar_schema_version="0.1.0")
        with pytest.raises(ValidationError):
            _bundle(matching_algorithm_version="0.1.0")

    def test_bundle_sha_is_deterministic_and_field_sensitive(self) -> None:
        assert _bundle().bundle_sha256() == _bundle().bundle_sha256()
        literal_fields = {
            "dataset_version": "2.0.2",
            "sidecar_schema_version": "0.1.0",
            "matching_algorithm_version": "0.1.0",
        }
        for field, value in ATTESTED.items():
            if field in literal_fields:
                with pytest.raises(ValidationError):
                    _bundle(**{field: literal_fields[field]})
                continue
            assert isinstance(value, str)
            flipped = value[:-1] + ("0" if value[-1] != "0" else "1")
            assert _bundle(**{field: flipped}).bundle_sha256() != _bundle().bundle_sha256()


class TestFindingAMandatoryLeakageAuditPreflight:
    @staticmethod
    def _materialize(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
        canon = tmp_path / "canon"
        raw = tmp_path / "raw"
        canon.mkdir()
        raw.mkdir()
        shas: dict[str, str] = {}
        for name in ("train", "validation", "test"):
            (canon / f"{name}.jsonl").write_text(f'{{"partition": "{name}"}}\n', encoding="utf-8")
            (raw / f"{name}.jsonl").write_text(f'{{"text": "{name}"}}\n', encoding="utf-8")
            shas[f"canonical_{name}_sha256"] = sha256_file(canon / f"{name}.jsonl")
            shas[f"raw_roles_{name}_sha256"] = sha256_file(raw / f"{name}.jsonl")
        (canon / "leakage_audit.json").write_text("{}", encoding="utf-8")
        shas["leakage_audit_sha256"] = sha256_file(canon / "leakage_audit.json")
        return canon, raw, shas

    def _attested_bundle(self, shas: dict[str, str]) -> ProvenanceBuildInputs:
        return _bundle(**shas)

    def test_full_verification_passes(self, tmp_path: Path) -> None:
        canon, raw, shas = self._materialize(tmp_path)
        verify_provenance_build_inputs(self._attested_bundle(shas), canon_dir=canon, raw_dir=raw)

    def test_missing_leakage_audit_stops_preflight(self, tmp_path: Path) -> None:
        canon, raw, shas = self._materialize(tmp_path)
        (canon / "leakage_audit.json").unlink()
        with pytest.raises(SidecarValidationError, match="leakage_audit"):
            verify_provenance_build_inputs(
                self._attested_bundle(shas), canon_dir=canon, raw_dir=raw
            )

    def test_mismatched_leakage_audit_stops_preflight(self, tmp_path: Path) -> None:
        canon, raw, shas = self._materialize(tmp_path)
        (canon / "leakage_audit.json").write_text('{"tampered": true}', encoding="utf-8")
        with pytest.raises(SidecarValidationError, match="leakage_audit"):
            verify_provenance_build_inputs(
                self._attested_bundle(shas), canon_dir=canon, raw_dir=raw
            )

    def test_missing_canonical_file_stops_preflight(self, tmp_path: Path) -> None:
        canon, raw, shas = self._materialize(tmp_path)
        (canon / "test.jsonl").unlink()
        with pytest.raises(SidecarValidationError):
            verify_provenance_build_inputs(
                self._attested_bundle(shas), canon_dir=canon, raw_dir=raw
            )

    def test_missing_raw_partition_stops_preflight(self, tmp_path: Path) -> None:
        canon, raw, shas = self._materialize(tmp_path)
        (raw / "validation.jsonl").unlink()
        with pytest.raises(SidecarValidationError):
            verify_provenance_build_inputs(
                self._attested_bundle(shas), canon_dir=canon, raw_dir=raw
            )


class TestFindingCNegativeCountProtection:
    @staticmethod
    def _manifest(**overrides: object) -> dict[str, object]:
        payload: dict[str, object] = {
            "status": "PARTIAL_DETERMINISTIC",
            "rows": 75163,
            "panel_unique": 69983,
            "figure_unique": 175,
            "article_only": 3914,
            "record_fallback": 1091,
            "map_sha256": ZERO_SHA,
            "schema_version": "0.2.0",
            "algorithm_version": "0.2.0",
            "upstream_xml_sha256": ZERO_SHA,
            "matched_subset_records": 74072,
            "matched_subset_articles": 3508,
            "matched_subset_articles_crossing_existing_splits": 0,
            "fallback_records_excluded_from_diagnostic": 1091,
            "embedded_document_id_present": 0,
            "global_paper_level_leakage_claim_allowed": False,
        }
        payload.update(overrides)
        return payload

    def test_valid_manifest_accepted(self) -> None:
        ProvenanceSidecarManifest.model_validate(self._manifest())

    def test_negative_counts_rejected(self) -> None:
        # Physically impossible decomposition that still satisfies the sums.
        with pytest.raises(ValidationError):
            ProvenanceSidecarManifest.model_validate(
                self._manifest(panel_unique=-5, article_only=3914 + 5)
            )
        with pytest.raises(ValidationError):
            ProvenanceSidecarManifest.model_validate(self._manifest(matched_subset_articles=-1))

    def test_booleans_rejected_as_integers(self) -> None:
        with pytest.raises(ValidationError):
            ProvenanceSidecarManifest.model_validate(self._manifest(figure_unique=True))

    def test_floats_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ProvenanceSidecarManifest.model_validate(self._manifest(record_fallback=1091.0))

    def test_numeric_strings_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ProvenanceSidecarManifest.model_validate(self._manifest(article_only="3914"))


class TestFindingDReportPersistenceOrdering:
    def _success_report(self) -> dict[str, object]:
        return {
            "status": "SUCCESS",
            "sidecar_sha256": ZERO_SHA,
            "input_bundle_sha256": ZERO_SHA,
            "validation": {"rows": 0},
            "tier_counts": {},
            "dual_build_byte_identical": True,
            "canonical_input_reverification": "PASSED",
            "final_verification_complete": True,
        }

    def test_success_report_published_only_after_final_verification(self, tmp_path: Path) -> None:
        path = publish_build_report(tmp_path, self._success_report())
        assert path.name == "build_report.json"
        assert json.loads(path.read_text())["status"] == "SUCCESS"

    @pytest.mark.parametrize(
        "missing_key",
        [
            "final_verification_complete",
            "canonical_input_reverification",
            "input_bundle_sha256",
            "validation",
        ],
    )
    def test_success_report_refused_without_verification_markers(
        self, tmp_path: Path, missing_key: str
    ) -> None:
        report = self._success_report()
        del report[missing_key]
        with pytest.raises(SidecarValidationError):
            publish_build_report(tmp_path, report)

    def test_success_report_refused_when_verification_flag_false(self, tmp_path: Path) -> None:
        report = self._success_report()
        report["final_verification_complete"] = False
        with pytest.raises(SidecarValidationError):
            publish_build_report(tmp_path, report)

    def test_written_sidecar_requires_post_rename_hash(self, tmp_path: Path) -> None:
        report = self._success_report()
        report["written_path"] = "/some/external/sidecar.jsonl"
        with pytest.raises(SidecarValidationError):
            publish_build_report(tmp_path, report)
        report["post_rename_sha256"] = ZERO_SHA
        publish_build_report(tmp_path, report)

    def test_post_rename_hash_must_match_sidecar_hash(self, tmp_path: Path) -> None:
        report = self._success_report()
        report["written_path"] = "/some/external/sidecar.jsonl"
        report["post_rename_sha256"] = "f" * 64
        with pytest.raises(SidecarValidationError):
            publish_build_report(tmp_path, report)

    def test_failed_and_aborted_reports_always_publishable(self, tmp_path: Path) -> None:
        failed = abort_build_report(tmp_path, stage="dual_build", error="boom", status="FAILED")
        doc = json.loads(failed.read_text())
        assert doc["status"] == "FAILED"
        assert doc["error"] == "boom"
        aborted = abort_build_report(tmp_path, stage="write", error="interrupted", status="ABORTED")
        assert json.loads(aborted.read_text())["status"] == "ABORTED"

    def test_unknown_report_status_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(SidecarValidationError):
            publish_build_report(tmp_path, {"status": "PARTIAL", "anything": 1})


class TestFindingECorruptArchiveAfterShaGate:
    def test_sha_matching_but_unreadable_archive_fails_at_tar_read(self, tmp_path: Path) -> None:
        """Bytes hash-match the expected SHA yet the tar/gzip structure is garbage.

        This exercises the parsing failure AFTER the SHA gate, not the hash
        mismatch path.
        """
        garbage = b"this matches its own sha but is not a gzip/tar stream" * 3
        archive = tmp_path / "attested-but-corrupt.tar.gz"
        archive.write_bytes(garbage)
        dest = tmp_path / "out"
        with pytest.raises(ArchiveExtractionError, match="unreadable provenance archive"):
            extract_xml_archive(archive, dest, expected_sha256=sha256_bytes(garbage))
        assert not dest.exists()

    def test_truncated_gzip_with_matching_sha_fails_at_tar_read(self, tmp_path: Path) -> None:
        good = tmp_path / "src" / "a.xml"
        good.parent.mkdir(parents=True)
        good.write_text("<article/>", encoding="utf-8")
        full = tmp_path / "full.tar.gz"
        with tarfile.open(full, "w:gz") as tar:
            tar.add(good, arcname="a.xml")
        blob = full.read_bytes()
        truncated = blob[: max(1, len(blob) // 2)]
        archive = tmp_path / "truncated.tar.gz"
        archive.write_bytes(truncated)
        dest = tmp_path / "out"
        with pytest.raises(ArchiveExtractionError, match="unreadable provenance archive"):
            extract_xml_archive(archive, dest, expected_sha256=sha256_bytes(truncated))
        assert not dest.exists()

    def test_hash_mismatch_still_refused_before_any_tar_read(self, tmp_path: Path) -> None:
        archive = tmp_path / "x.tar.gz"
        archive.write_bytes(b"whatever")
        dest = tmp_path / "out"
        with pytest.raises(ArchiveExtractionError, match="sha256 mismatch"):
            extract_xml_archive(archive, dest, expected_sha256=ZERO_SHA)
        assert not dest.exists()


class TestSection5CompatibilityRegression:
    """Permissive parsing is NOT semantic validation.

    main@fe089ef predates the ``provenance_sidecar`` field; a manifest model
    with no typed field silently ignores the block. Only the corrected strict
    schema can detect an invalid sidecar block.
    """

    class MainLikeManifest(BaseModel):
        """Shape-equivalent to main@fe089ef's BuildManifest (no sidecar field)."""

        manifest_version: str = "0.2.2"
        records_sha256: str = ""

    @staticmethod
    def _full_manifest(block: dict[str, object]) -> dict[str, object]:
        return {
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
            "records_sha256": ZERO_SHA,
            "groups_crossing_splits": 0,
            "manifest_version": "0.3.0",
            "provenance_sidecar": block,
        }

    def test_main_like_model_parses_but_cannot_validate_semantics(self) -> None:
        invalid_block = {
            "status": "PARTIAL_DETERMINISTIC",
            "rows": 75163,
            "panel_unique": -5,  # physically impossible, sums still match
            "figure_unique": 175,
            "article_only": 3914 + 5,
            "record_fallback": 1091,
            "map_sha256": ZERO_SHA,
            "schema_version": "0.2.0",
            "algorithm_version": "0.2.0",
            "upstream_xml_sha256": ZERO_SHA,
            "matched_subset_records": 74072,
            "matched_subset_articles": 3508,
            "matched_subset_articles_crossing_existing_splits": 0,
            "fallback_records_excluded_from_diagnostic": 1091,
            "embedded_document_id_present": 0,
            "global_paper_level_leakage_claim_allowed": False,
        }
        doc = self._full_manifest(invalid_block)
        # MAIN_CAN_PARSE_MANIFEST_BUT_CANNOT_VALIDATE_SIDECAR_SEMANTICS:
        parsed = self.MainLikeManifest.model_validate(doc)
        assert not hasattr(parsed, "provenance_sidecar") or getattr(
            parsed, "provenance_sidecar", None
        ) in (None, {})
        # PR9_HEAD_CAN_STRICTLY_VALIDATE_SIDECAR_SEMANTICS:
        with pytest.raises(ValidationError):
            BuildManifest.model_validate(doc)

    def test_strict_head_accepts_valid_block(self) -> None:
        valid_block = {
            "status": "PARTIAL_DETERMINISTIC",
            "rows": 75163,
            "panel_unique": 69983,
            "figure_unique": 175,
            "article_only": 3914,
            "record_fallback": 1091,
            "map_sha256": ZERO_SHA,
            "schema_version": "0.2.0",
            "algorithm_version": "0.2.0",
            "upstream_xml_sha256": ZERO_SHA,
            "matched_subset_records": 74072,
            "matched_subset_articles": 3508,
            "matched_subset_articles_crossing_existing_splits": 0,
            "fallback_records_excluded_from_diagnostic": 1091,
            "embedded_document_id_present": 0,
            "global_paper_level_leakage_claim_allowed": False,
        }
        manifest = BuildManifest.model_validate(self._full_manifest(valid_block))
        assert manifest.provenance_sidecar is not None
        assert manifest.provenance_sidecar.rows == 75163
