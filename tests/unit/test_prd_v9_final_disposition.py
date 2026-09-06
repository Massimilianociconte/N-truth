"""Pin the PRD v9 review against the shipped final matrix parser."""

from __future__ import annotations

from pathlib import Path

from ntruth.governance.prd_matrix import (
    EXPECTED_IMPLEMENTED_COUNT,
    EXPECTED_MISSING_COUNT,
    EXPECTED_PARTIAL_COUNT,
    EXPECTED_REQUIREMENT_COUNT,
    MISSING_REQUIREMENT_IDS,
    SCIENTIFIC_STATUS_PIN,
    V9_ONLY_UNSHIPPED_TOKENS,
    disposition_for,
    incomplete_rows_without_blockers,
    load_final_implementation_matrix,
    matrix_status_counts,
    missing_requirement_ids,
    parse_final_matrix,
    v9_only_tokens_claimed_implemented,
)

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "docs" / "audits" / "prd-v8-full-migration" / "FINAL_IMPLEMENTATION_MATRIX.md"
REVIEW = ROOT / "docs" / "audits" / "prd-v8-full-migration" / "PRD_V9_FINAL_SYSTEM_REVIEW.md"
SNAPSHOT = ROOT / "docs" / "status-snapshot.md"


def test_shipped_parser_reads_the_committed_final_matrix() -> None:
    rows = load_final_implementation_matrix(MATRIX)
    counts = matrix_status_counts(rows)
    assert len(rows) == EXPECTED_REQUIREMENT_COUNT
    assert counts["IMPLEMENTED"] == EXPECTED_IMPLEMENTED_COUNT
    assert counts["PARTIAL"] == EXPECTED_PARTIAL_COUNT
    assert counts["MISSING"] == EXPECTED_MISSING_COUNT
    assert missing_requirement_ids(rows) == MISSING_REQUIREMENT_IDS
    assert incomplete_rows_without_blockers(rows) == ()


def test_missing_rows_have_explicit_operational_dispositions() -> None:
    # 2026-08-27 reconciliation: only CROSSWALK and SYNTH-ABLATION remain MISSING;
    # CORPUS and STRATEGY-VALIDATION moved to PARTIAL (contracts implemented,
    # scientific closure still SRR-blocked) and are re-checked below from the
    # matrix itself so the promoted rows cannot silently regress.
    assert disposition_for("V8-CROSSWALK") == "EXTERNAL_EVIDENCE_ONLY"
    assert disposition_for("V8-SYNTH-ABLATION") == "EXTERNAL_EVIDENCE_ONLY"

    rows = load_final_implementation_matrix(MATRIX)
    for requirement_id in ("V8-CORPUS", "V8-STRATEGY-VALIDATION"):
        row = next(r for r in rows if r.requirement_id == requirement_id)
        assert row.status == "PARTIAL"
        assert row.blocker_ids, requirement_id


def test_parse_final_matrix_rejects_unknown_status() -> None:
    try:
        parse_final_matrix("| V8-FAKE | §0 | note | GUESSED | files | HIGH | none | tests |\n")
    except ValueError as exc:
        assert "invalid status" in str(exc)
    else:  # pragma: no cover - explicit failure path
        raise AssertionError("invalid status must fail closed")


def test_v9_only_tokens_are_not_claimed_implemented_in_the_review() -> None:
    review = REVIEW.read_text(encoding="utf-8")
    snapshot = SNAPSHOT.read_text(encoding="utf-8")
    assert v9_only_tokens_claimed_implemented(review) == ()
    assert v9_only_tokens_claimed_implemented(snapshot) == ()
    for token in V9_ONLY_UNSHIPPED_TOKENS:
        assert token in review
    assert v9_only_tokens_claimed_implemented("FactorRole is IMPLEMENTED") == ("FactorRole",)
    assert v9_only_tokens_claimed_implemented("FactorRole is not the shipped kernel") == ()


def test_scientific_pins_remain_hold() -> None:
    review = REVIEW.read_text(encoding="utf-8")
    snapshot = SNAPSHOT.read_text(encoding="utf-8")
    combined = review + "\n" + snapshot
    assert SCIENTIFIC_STATUS_PIN["repository_implementation_status"] in combined
    assert SCIENTIFIC_STATUS_PIN["scientific_validation"] in combined
    assert SCIENTIFIC_STATUS_PIN["training_and_external_challenge"] in combined
    assert "scientific validation remains NOT_STARTED" in review
    assert "training/External Challenge remain HOLD" in review
