"""Tests for MeasEval text/txt directory detection, review-required missing TSVs, and trial isolation."""

from __future__ import annotations

from pathlib import Path

import pytest

from ntruth.data.datasets.measeval import (
    TEXT_ONLY_TRAIN_STEMS,
    _build_ntruth_article_family_split,
    _find_text_tsv_dirs,
    _ntruth_split_assignment,
    _parse_tsv_annotations,
)


def test_measeval_text_only_stems():
    assert "S0019103512003995-3420" in TEXT_ONLY_TRAIN_STEMS
    assert "S0019103512004009-2930" in TEXT_ONLY_TRAIN_STEMS
    assert "S0022000014000026-7850" in TEXT_ONLY_TRAIN_STEMS
    assert "S0164121213002641-2930" in TEXT_ONLY_TRAIN_STEMS
    assert "S0167739X12001525-5094" in TEXT_ONLY_TRAIN_STEMS


def test_measeval_find_txt_or_text_dirs(tmp_path: Path):
    split1 = tmp_path / "train"
    (split1 / "text").mkdir(parents=True)
    (split1 / "tsv").mkdir(parents=True)

    text_d, _tsv_d = _find_text_tsv_dirs(split1)
    assert text_d.name == "text"

    split2 = tmp_path / "trial"
    (split2 / "txt").mkdir(parents=True)
    (split2 / "tsv").mkdir(parents=True)

    text_d2, _tsv_d2 = _find_text_tsv_dirs(split2)
    assert text_d2.name == "txt"


def test_measeval_tsv_parser_imports_official_span_relations(tmp_path: Path):
    tsv = tmp_path / "S0016236113008041-3153.tsv"
    document_text = "bed inventory was 13 kg; concentrations were <2 ppm in elements."

    def offsets(span_text: str) -> tuple[int, int]:
        start = document_text.index(span_text)
        return start, start + len(span_text)

    quantity_1 = offsets("13 kg")
    entity = offsets("bed inventory")
    quantity_2 = offsets("<2 ppm")
    prop = offsets("concentrations")
    elements = offsets("elements")
    tsv.write_text(
        "docId\tannotSet\tannotType\tstartOffset\tendOffset\tannotId\ttext\tother\n"
        f"S0016236113008041-3153\t1\tQuantity\t{quantity_1[0]}\t{quantity_1[1]}"
        '\tT1\t13 kg\t{"unit": "kg"}\n'
        f"S0016236113008041-3153\t1\tMeasuredEntity\t{entity[0]}\t{entity[1]}"
        '\tT3\tbed inventory\t{"HasQuantity": "T1"}\n'
        f"S0016236113008041-3153\t2\tQuantity\t{quantity_2[0]}\t{quantity_2[1]}"
        '\tT2\t<2 ppm\t{"mods": ["IsRange"], "unit": "ppm"}\n'
        f"S0016236113008041-3153\t2\tMeasuredProperty\t{prop[0]}\t{prop[1]}"
        '\tT4\tconcentrations\t{"HasQuantity": "T2"}\n'
        f"S0016236113008041-3153\t2\tMeasuredEntity\t{elements[0]}\t{elements[1]}"
        '\tT6\telements\t{"HasProperty": "T4"}\n',
        encoding="utf-8",
    )

    spans, relations = _parse_tsv_annotations(tsv, document_text=document_text)

    assert [span.span_id for span in spans] == ["T1", "T3", "T2", "T4", "T6"]
    assert spans[0].source_metadata == {
        "annotation_set": "1",
        "attributes": {"unit": "kg"},
    }
    assert spans[2].source_metadata == {
        "annotation_set": "2",
        "attributes": {"mods": ["IsRange"], "unit": "ppm"},
    }
    assert spans[3].source_metadata == {
        "annotation_set": "2",
        "attributes": {"HasQuantity": "T2"},
    }
    assert [relation.model_dump() for relation in relations] == [
        {
            "relation_id": "R1",
            "source_span_id": "T3",
            "target_span_id": "T1",
            "relation_type": "HasQuantity",
        },
        {
            "relation_id": "R2",
            "source_span_id": "T4",
            "target_span_id": "T2",
            "relation_type": "HasQuantity",
        },
        {
            "relation_id": "R3",
            "source_span_id": "T6",
            "target_span_id": "T4",
            "relation_type": "HasProperty",
        },
    ]


def test_measeval_tsv_parser_rejects_dangling_official_relation(tmp_path: Path):
    tsv = tmp_path / "dangling.tsv"
    tsv.write_text(
        "docId\tannotSet\tannotType\tstartOffset\tendOffset\tannotId\ttext\tother\n"
        "doc\t1\tMeasuredEntity\t0\t6\tT2\tsample\t"
        '{"HasQuantity": "T-missing"}\n',
        encoding="utf-8",
    )

    try:
        _parse_tsv_annotations(tsv, document_text="sample")
    except RuntimeError as exc:
        assert "unknown target span" in str(exc)
    else:
        raise AssertionError("dangling official relation must fail closed")


@pytest.mark.parametrize(
    ("start", "end", "annotated_text", "document_text", "error"),
    [
        (-1, 5, "sample", "sample", "invalid span offsets"),
        (0, 7, "sample", "sample", "invalid span offsets"),
        (0, 6, "samples", "sample", "does not match document text"),
    ],
)
def test_measeval_tsv_parser_rejects_invalid_or_inconsistent_spans(
    tmp_path: Path,
    start: int,
    end: int,
    annotated_text: str,
    document_text: str,
    error: str,
):
    tsv = tmp_path / "invalid-span.tsv"
    tsv.write_text(
        "docId\tannotSet\tannotType\tstartOffset\tendOffset\tannotId\ttext\tother\n"
        f"doc\t1\tMeasuredEntity\t{start}\t{end}\tT1\t{annotated_text}\t{{}}\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match=error):
        _parse_tsv_annotations(tsv, document_text=document_text)


def test_measeval_article_family_split_protects_eval_and_trial_families():
    split_map, reconciliation = _build_ntruth_article_family_split(
        train_stems={
            "shared-eval-100",
            "shared-trial-100",
            "development-a-100",
            "development-b-100",
        },
        eval_stems={"shared-eval-200", "eval-only-100"},
        trial_stems={"shared-trial-200", "trial-only-100"},
    )

    assert split_map["shared-eval"] == "test"
    assert split_map["shared-trial"] == "test"
    assert split_map["eval-only"] == "test"
    assert split_map["trial-only"] == "test"
    assert split_map["development-a"] in {"train", "validation"}
    assert split_map["development-b"] in {"train", "validation"}
    assert reconciliation["authority"] == "ntruth_measeval_article_family_v1"
    assert reconciliation["protected_test_policy"] == {
        "official_eval_families": True,
        "upstream_trial_families": True,
        "trial_records_format_smoke_only": True,
    }
    assert reconciliation["trial_format_smoke_only_record_count"] == 2
    assert reconciliation["trial_model_eligible_record_count"] == 0
    assert reconciliation["upstream_article_overlap"]["has_overlap"] is True
    assert reconciliation["upstream_article_overlap"]["cross_partition_family_count"] == 2
    assert reconciliation["ntruth_split_article_family_counts"] == {
        "train": 2,
        "validation": 0,
        "test": 4,
    }
    assert reconciliation["model_development_group_leakage_count"] == 0


@pytest.mark.parametrize("source_partition", ["train", "eval", "trial"])
def test_measeval_records_use_ntruth_family_split_authority(source_partition: str):
    assignment = _ntruth_split_assignment("test", f"family-from-{source_partition}")

    assert assignment.authority == "ntruth_measeval_article_family_v1"
    assert assignment.name == "test"
    assert assignment.group_id == f"family-from-{source_partition}"
