"""Tests for MeasEval text/txt directory detection, review-required missing TSVs, and trial isolation."""

from __future__ import annotations

from pathlib import Path

from ntruth.data.datasets.measeval import TEXT_ONLY_TRAIN_STEMS, _find_text_tsv_dirs


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
