"""Minimum Viable Train A contracts only - no training."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ntruth.mvt_a import (
    BenchmarkManifest,
    BenchmarkSplitPolicy,
    BurdenRecord,
    DecisiveCorrection,
    FalseCertaintyRecord,
    HumanRevisionPatch,
    MvtAStageOutput,
    ParserCandidateBundle,
    assert_no_final_scientific_fields,
    hard_verify_candidates,
)
from ntruth.mvt_a.stage_schema import CountCandidate, EntityCandidate


def test_parser_bundle_forbids_independent_n() -> None:
    with pytest.raises(ValidationError):
        CountCandidate(kind="independent_n", value=6)


def test_assert_no_final_scientific_fields() -> None:
    with pytest.raises(ValueError, match="independent_n"):
        assert_no_final_scientific_fields({"nested": {"independent_n": 3}})


def test_hard_verifier_passes_candidates() -> None:
    bundle = ParserCandidateBundle(
        entities=(EntityCandidate(text="well", entity_type="unit"),),
        counts=(CountCandidate(kind="declared_n", value=3),),
    )
    result = hard_verify_candidates(bundle)
    assert result.passed is True


def test_empty_bundle_without_notes_fails() -> None:
    result = hard_verify_candidates(ParserCandidateBundle())
    assert result.passed is False


def test_stage_output_challenger_role() -> None:
    stage = MvtAStageOutput(
        stage_id="s1",
        candidates=ParserCandidateBundle(notes=("abstain",)),
        model_id="granite-challenger",
        model_role="unqualified_challenger",
    )
    assert stage.model_role == "unqualified_challenger"


def test_revision_patch_counts_decisive() -> None:
    patch = HumanRevisionPatch(
        patch_id="p1",
        stage_id="s1",
        actor_role="annotator",
        created_at=datetime(2026, 8, 3, tzinfo=UTC),
        corrections=(
            DecisiveCorrection(field="allocation", before="unknown", after="well"),
            DecisiveCorrection(field="note", before="a", after="b", affects_determinability=False),
        ),
        false_certainty=(
            FalseCertaintyRecord(
                field="n",
                candidate_value="independent_n=6",
                corrected_value="declared_n=6",
                rationale="parser must not finalise independent_n",
            ),
        ),
        burden=BurdenRecord(minutes_total=12.5, unknown_field_count=2),
    )
    assert patch.decisive_correction_count == 1


def test_benchmark_split_no_leakage() -> None:
    with pytest.raises(ValidationError):
        BenchmarkSplitPolicy(train_ids=("a",), test_ids=("a",))
    manifest = BenchmarkManifest(
        manifest_id="bm-1",
        splits=BenchmarkSplitPolicy(train_ids=("t1",), test_ids=("x1",)),
    )
    assert manifest.real_anchor_required is True
    assert manifest.notes == "HOLD_PENDING_REAL_ANCHOR"
    assert manifest.checksum()
