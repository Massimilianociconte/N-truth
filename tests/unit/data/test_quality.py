from __future__ import annotations

import json
from pathlib import Path

from ntruth.data.quality import QualityStatus, audit_common_envelope_jsonl, write_quality_report


def _record(
    record_id: str,
    *,
    split: str = "train",
    group_id: str | None = None,
    text: str = "The experiment measured treatment response in twenty biological samples.",
    labels: list[str] | None = None,
    training_eligible: bool | None = None,
) -> dict[str, object]:
    if training_eligible is None:
        training_eligible = split not in {"test", "trial"}
    return {
        "record_id": record_id,
        "source": {
            "dataset": "fixture",
            "version": "1",
            "commit": "abc123",
            "document_id": f"doc-{record_id}",
            "segment_id": f"segment-{record_id}",
        },
        "split": {
            "name": split,
            "authority": "fixture",
            "group_id": group_id or f"group-{record_id}",
        },
        "eligibility": {
            "training_eligible": training_eligible,
            "evaluation_eligible": split in {"validation", "test"},
            "requires_review": False,
        },
        "provenance": {
            "source_url": "https://example.test/source",
            "sha256": "a" * 64,
            "transform_version": "test-v1",
        },
        "native_annotation_tier": "HUMAN_CURATED_GOLD",
        "ntruth_usage_tier": "SILVER_AUXILIARY",
        "allowed_tasks": ["document_classification"],
        "forbidden_targets": ["causal_claim"],
        "annotation_status": "annotated",
        "task_type": "document_classification",
        "payload": {
            "kind": "document_classification",
            "text": text,
            "labels": labels or ["randomization_reported"],
        },
    }


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _token_record(
    record_id: str, *, tokens: list[str], entity_tags: list[str]
) -> dict[str, object]:
    record = _record(record_id)
    record["allowed_tasks"] = ["token_classification"]
    record["task_type"] = "token_classification"
    record["payload"] = {
        "kind": "token_classification",
        "tokens": tokens,
        "entity_tags": entity_tags,
        "role_tags": ["O"] * len(tokens),
    }
    return record


def test_audit_reports_deterministic_distributions_and_lengths(tmp_path: Path) -> None:
    source = tmp_path / "records.jsonl"
    _write_jsonl(
        source,
        [
            _record("r1", labels=["randomization_reported"]),
            _record(
                "r2",
                split="validation",
                text="The experiment measured a control response in ten independent samples.",
                labels=["randomization_not_reported", "blinding_reported"],
            ),
        ],
    )

    first = audit_common_envelope_jsonl([source])
    second = audit_common_envelope_jsonl([source])

    assert first.status is QualityStatus.PASS
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.records.model_dump() == {
        "physical_records": 2,
        "valid_records": 2,
        "invalid_records": 0,
        "blank_records": 0,
    }
    assert first.split_counts == {"train": 1, "validation": 1}
    assert first.label_histograms["document_labels"] == {
        "blinding_reported": 1,
        "randomization_not_reported": 1,
        "randomization_reported": 1,
    }
    assert first.annotation_tier_counts == {"HUMAN_CURATED_GOLD": 2}
    assert first.eligibility_counts["training_eligible"] == {"false": 0, "true": 2}
    assert first.lengths["text_characters"].count == 2
    assert first.lengths["text_characters"].minimum == 70
    assert first.lengths["text_characters"].maximum == 72
    assert first.blockers == []


def test_audit_fails_closed_but_continues_after_invalid_records(tmp_path: Path) -> None:
    source = tmp_path / "records.jsonl"
    duplicate_payload = _record("duplicate", group_id="shared-publication")
    source.write_bytes(
        (json.dumps(duplicate_payload) + "\n").encode()
        + (json.dumps(duplicate_payload) + "\n").encode()
        + (
            json.dumps(
                _record(
                    "test-copy",
                    split="test",
                    group_id="shared-publication",
                    text="An independent held-out experimental description.",
                )
            )
            + "\n"
        ).encode()
        + b'{"record_id":"missing-fields"}\n'
        + b"{not-json}\n"
        + b"\xff\xfe\n"
        + b"\n"
    )

    report = audit_common_envelope_jsonl([source])

    assert report.status is QualityStatus.FAIL
    assert report.records.physical_records == 7
    assert report.records.valid_records == 3
    assert report.records.invalid_records == 3
    assert report.records.blank_records == 1
    assert report.issue_counts["duplicate_record_id"] == 1
    assert report.issue_counts["exact_payload_duplicates"] == 1
    assert report.issue_counts["cross_split_group_leakage"] == 1
    assert report.issue_counts["schema_validation_errors"] == 1
    assert report.issue_counts["missing_required_field_records"] == 1
    assert report.issue_counts["invalid_json_records"] == 1
    assert report.issue_counts["invalid_utf8_records"] == 1
    assert {blocker.code for blocker in report.blockers} >= {
        "INVALID_RECORDS",
        "DUPLICATE_RECORD_ID",
        "CROSS_SPLIT_GROUP_LEAKAGE",
    }


def test_blank_physical_record_is_counted_once(tmp_path: Path) -> None:
    source = tmp_path / "records.jsonl"
    source.write_bytes(b"\n")

    report = audit_common_envelope_jsonl([source])

    assert report.records.physical_records == 1
    assert report.records.blank_records == 1
    assert report.issue_counts["blank_records"] == 1


def test_audit_distinguishes_normalized_and_heuristic_duplicate_candidates(
    tmp_path: Path,
) -> None:
    source = tmp_path / "records.jsonl"
    _write_jsonl(
        source,
        [
            _record(
                "r1",
                text="The laboratory measured 12 biological samples after controlled treatment.",
                labels=["reported"],
            ),
            _record(
                "r2",
                text="  THE laboratory measured 12 biological samples after controlled treatment.  ",
                labels=["not_reported"],
            ),
            _record(
                "r3",
                text="The laboratory measured 13 biological samples after controlled treatment.",
                labels=["reported"],
            ),
            _record(
                "r4",
                text="{{cite needed}} Мы измерили ответ в лаборатории после контролируемого лечения.",
            ),
        ],
    )

    report = audit_common_envelope_jsonl([source])

    assert report.status is QualityStatus.PARTIAL
    assert report.issue_counts["normalized_text_duplicates"] == 1
    assert report.issue_counts["heuristic_near_duplicate_candidates"] == 1
    assert report.issue_counts["citation_artifact_candidates"] == 1
    assert report.issue_counts["language_contamination_candidates"] == 1
    assert not any("semantic" in name for name in report.issue_counts)
    assert report.heuristic_policy == (
        "Conservative lexical and formatting candidates only; no semantic duplicate truth is inferred."
    )


def test_cross_split_normalized_content_is_a_leakage_blocker(tmp_path: Path) -> None:
    train = tmp_path / "train.jsonl"
    test = tmp_path / "test.jsonl"
    text = "Independent animals were assigned to treatment groups before measurement."
    _write_jsonl(train, [_record("train-1", text=text)])
    _write_jsonl(test, [_record("test-1", split="test", text=text.upper())])

    report = audit_common_envelope_jsonl([test, train])

    assert report.status is QualityStatus.FAIL
    assert report.issue_counts["cross_split_normalized_content_leakage"] == 1
    assert any(blocker.code == "CROSS_SPLIT_CONTENT_LEAKAGE" for blocker in report.blockers)


def test_token_fingerprints_and_tag_histograms_are_audited(tmp_path: Path) -> None:
    source = tmp_path / "tokens.jsonl"
    _write_jsonl(
        source,
        [
            _token_record(
                "token-1",
                tokens=["Independent", "animals"],
                entity_tags=["B-SAMPLE", "I-SAMPLE"],
            ),
            _token_record(
                "token-2",
                tokens=["INDEPENDENT", "animals"],
                entity_tags=["O", "B-SAMPLE"],
            ),
        ],
    )

    report = audit_common_envelope_jsonl([source])

    assert report.issue_counts["normalized_token_duplicates"] == 1
    assert report.label_histograms["entity_tags"] == {
        "B-SAMPLE": 2,
        "I-SAMPLE": 1,
        "O": 1,
    }
    assert report.label_histograms["role_tags"] == {"O": 4}
    assert report.lengths["tokens"].model_dump() == {
        "count": 2,
        "minimum": 2,
        "maximum": 2,
        "p50": 2,
        "p90": 2,
        "p95": 2,
        "p99": 2,
    }


def test_empty_snapshot_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "empty.jsonl"
    source.write_bytes(b"")

    report = audit_common_envelope_jsonl([source])

    assert report.status is QualityStatus.FAIL
    assert report.issue_counts["no_valid_records"] == 1
    assert [blocker.code for blocker in report.blockers] == ["NO_VALID_RECORDS"]


def test_semantically_missing_required_values_are_blockers(tmp_path: Path) -> None:
    source = tmp_path / "missing-values.jsonl"
    record = _record("r1")
    record["source"]["document_id"] = ""  # type: ignore[index]
    record["provenance"]["sha256"] = "not-a-digest"  # type: ignore[index]
    record["allowed_tasks"] = []
    _write_jsonl(source, [record])

    report = audit_common_envelope_jsonl([source])

    assert report.status is QualityStatus.FAIL
    assert report.issue_counts["missing_required_value_records"] == 1
    assert report.issue_counts["invalid_provenance_sha256_records"] == 1
    assert {blocker.code for blocker in report.blockers} == {
        "INVALID_PROVENANCE_SHA256",
        "MISSING_REQUIRED_VALUES",
    }


def test_task_payload_and_missing_annotation_eligibility_contradictions_fail(
    tmp_path: Path,
) -> None:
    source = tmp_path / "contradictions.jsonl"
    task_mismatch = _record("mismatch")
    task_mismatch["task_type"] = "span_relation"
    missing_annotation = _record("missing")
    missing_annotation["annotation_status"] = "missing_annotation_file"
    missing_annotation["native_annotation_tier"] = "MISSING_ANNOTATION"
    _write_jsonl(source, [task_mismatch, missing_annotation])

    report = audit_common_envelope_jsonl([source])

    assert report.status is QualityStatus.FAIL
    assert report.issue_counts["task_payload_mismatch_records"] == 1
    assert report.issue_counts["missing_annotation_eligible_records"] == 1
    assert {blocker.code for blocker in report.blockers} == {
        "MISSING_ANNOTATION_ELIGIBLE",
        "TASK_PAYLOAD_MISMATCH",
    }


def test_ocr_heuristic_does_not_flag_biomedical_alphanumeric_identifiers(
    tmp_path: Path,
) -> None:
    source = tmp_path / "ocr.jsonl"
    _write_jsonl(
        source,
        [
            _record("identifier", text="S2E expression was measured in the treatment group."),
            _record("artifact", text="Adominant|arecessive was copied from a damaged OCR table."),
        ],
    )

    report = audit_common_envelope_jsonl([source])

    assert report.issue_counts["ocr_noise_candidates"] == 1


def test_write_quality_report_emits_stable_machine_readable_json(tmp_path: Path) -> None:
    source = tmp_path / "records.jsonl"
    destination = tmp_path / "quality.json"
    _write_jsonl(source, [_record("r1")])

    report = audit_common_envelope_jsonl([source])
    write_quality_report(report, destination)

    encoded = destination.read_text(encoding="utf-8")
    assert encoded.endswith("\n")
    assert json.loads(encoded) == report.model_dump(mode="json")
