"""Anti-leakage split invariants: same identity never spans two splits.

Engineering-only regression tests for the group-aware splitter. They prove
nothing about scientific validity. Direct coverage for
assign_group_aware_splits / validate_no_group_leakage, which previously had
no dedicated tests.
"""

from __future__ import annotations

import hashlib

from ntruth.governance.lineage import CorpusSplit
from ntruth.parser_ai.contract import GoldParserTarget, ParserCandidateOutput
from ntruth.training import AnnotationStatus, SupervisedRecord, SupervisionProvenance
from ntruth.training.records import SplitRatios, normalize_record
from ntruth.training.splits import (
    SplitAssignment,
    assign_group_aware_splits,
    validate_no_group_leakage,
)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _record(record_id: str, text: str, *, source: str) -> SupervisedRecord:
    return SupervisedRecord(
        record_id=record_id,
        task="parser_candidate_v8",
        language="en",
        domain="split-leakage-regression",
        input_text=text,
        target=GoldParserTarget(
            candidate_target=ParserCandidateOutput.model_validate(
                {
                    "coverage": {
                        "status": "PARTIAL",
                        "missing_artifact_ids": ["not-reported"],
                        "rationale": record_id,
                    },
                    "model_metadata": {
                        "adapter_name": "split-fixture",
                        "model_name": "adjudication",
                        "model_version": "1",
                        "prompt_template_version": "candidate-v8-test",
                    },
                }
            ),
            adjudication_id="gold-fixture",
            reviewer_ids=("wet-lab", "biostatistics"),
            adjudication_rationale="Fixture for split leakage invariants.",
            submission_references=(
                {
                    "submission_id": "submission-wet-lab",
                    "submission_sha256": "a" * 64,
                    "reviewer_id": "wet-lab",
                    "reviewer_role": "wet-lab",
                },
                {
                    "submission_id": "submission-biostatistics",
                    "submission_sha256": "b" * 64,
                    "reviewer_id": "biostatistics",
                    "reviewer_role": "biostatistics",
                },
            ),
            comparison_status="AGREED",
            material_differences=(),
        ),
        provenance=SupervisionProvenance(
            source_id=f"source-{source}",
            source_asset_id=f"asset-{source}",
            source_sha256=_digest(f"source:{source}"),
            governance_hash=_digest(f"governance:{source}"),
            laboratory_id=None,
            license_or_authorization_id=f"authorization-{source}",
            guideline_version="test-v1",
            reviewer_count=2,
            reviewer_ids=("wet-lab", "biostatistics"),
            reviewer_roles=("wet-lab", "biostatistics"),
            adjudication_id="gold-fixture",
            study_family_id=None,
            document_lineage_id=None,
            external_challenge_dependency=None,
        ),
        annotation_status=AnnotationStatus.ADJUDICATED,
        training_eligible=True,
        evaluation_eligible=False,
        model_selection_eligible=True,
        split=CorpusSplit.UNASSIGNED,
    )


def _normalized(*specs: tuple[str, str, str]):
    return tuple(
        normalize_record(_record(record_id, text, source=source), shingle_size=5)
        for record_id, text, source in specs
    )


def test_same_source_records_share_one_split() -> None:
    records = _normalized(
        ("r1", "first distinct methods paragraph alpha", "paper-a"),
        ("r2", "second distinct methods paragraph beta", "paper-a"),
        ("r3", "third distinct methods paragraph gamma", "paper-a"),
        ("r4", "first distinct methods paragraph delta", "paper-b"),
        ("r5", "second distinct methods paragraph epsilon", "paper-b"),
        ("r6", "third distinct methods paragraph zeta", "paper-b"),
    )
    result = assign_group_aware_splits(records, ratios=SplitRatios(), seed="leakage-seed-1")
    assert result.leakage_group_count == 2
    by_id = {a.record_id: a for a in result.assignments}
    assert {by_id["r1"].split, by_id["r2"].split, by_id["r3"].split} == {by_id["r1"].split}
    assert {by_id["r4"].split, by_id["r5"].split, by_id["r6"].split} == {by_id["r4"].split}
    assert by_id["r1"].leakage_group_id == by_id["r2"].leakage_group_id
    assert by_id["r1"].leakage_group_id != by_id["r4"].leakage_group_id
    assert [i for i in result.issues if i.code == "cross_split_leakage"] == []


def test_hand_split_leakage_is_flagged_as_error() -> None:
    records = _normalized(
        ("r1", "first distinct methods paragraph alpha", "paper-a"),
        ("r2", "second distinct methods paragraph beta", "paper-a"),
    )
    assignments = (
        SplitAssignment(record_id="r1", leakage_group_id="g1", split=CorpusSplit.TRAIN),
        SplitAssignment(record_id="r2", leakage_group_id="g1", split=CorpusSplit.TEST),
    )
    issues = validate_no_group_leakage(records, assignments)
    flagged = [i for i in issues if i.code == "cross_split_leakage"]
    assert len(flagged) >= 1
    assert set(flagged[0].record_ids) == {"r1", "r2"}


def test_related_pairs_across_splits_are_flagged() -> None:
    records = _normalized(
        ("r1", "first distinct methods paragraph alpha", "paper-a"),
        ("r2", "second distinct methods paragraph epsilon", "paper-b"),
    )
    assignments = (
        SplitAssignment(record_id="r1", leakage_group_id="g1", split=CorpusSplit.TRAIN),
        SplitAssignment(record_id="r2", leakage_group_id="g2", split=CorpusSplit.VALIDATION),
    )
    issues = validate_no_group_leakage(records, assignments, related_record_pairs=(("r1", "r2"),))
    assert [i for i in issues if i.code == "cross_split_near_duplicate"] != []


def test_assignments_are_deterministic_across_runs() -> None:
    records = _normalized(
        ("r1", "first distinct methods paragraph alpha", "paper-a"),
        ("r2", "second distinct methods paragraph beta", "paper-a"),
        ("r3", "third distinct methods paragraph gamma", "paper-b"),
        ("r4", "fourth distinct methods paragraph delta", "paper-c"),
    )
    first = assign_group_aware_splits(records, ratios=SplitRatios(), seed="leakage-seed-9")
    second = assign_group_aware_splits(records, ratios=SplitRatios(), seed="leakage-seed-9")
    assert first.assignments == second.assignments
