"""Minimum Viable Train A contracts only (PRD v7 §4.2, Workstream B).

No model download, no training, no weight promotion. These modules define the
stage schema, hard verifier hook, human revision patch, burden recording and
benchmark manifest required before any MVT-A run.
"""

from ntruth.mvt_a.benchmark import BenchmarkManifest, BenchmarkSplitPolicy
from ntruth.mvt_a.revision import (
    BurdenRecord,
    DecisiveCorrection,
    FalseCertaintyRecord,
    HumanRevisionPatch,
)
from ntruth.mvt_a.stage_schema import (
    FORBIDDEN_FINAL_FIELDS,
    AlternativeCandidate,
    EventCandidate,
    GraphCandidate,
    MissingPredicateCandidate,
    MvtAStageOutput,
    MvtAStageOutputV7,
    ParserCandidateBundle,
    RelationCandidate,
    StageCompletionStatus,
    StageCoverage,
    StageErrorCode,
    StageIssue,
    StageProvenance,
    assert_no_final_scientific_fields,
    normalize_candidate_syntax,
)
from ntruth.mvt_a.verifier import (
    HardVerifierResult,
    attach_verifier,
    attach_verifier_v7,
    hard_verify_candidates,
    hard_verify_candidates_v7,
)

__all__ = [
    "FORBIDDEN_FINAL_FIELDS",
    "AlternativeCandidate",
    "BenchmarkManifest",
    "BenchmarkSplitPolicy",
    "BurdenRecord",
    "DecisiveCorrection",
    "EventCandidate",
    "FalseCertaintyRecord",
    "GraphCandidate",
    "HardVerifierResult",
    "HumanRevisionPatch",
    "MissingPredicateCandidate",
    "MvtAStageOutput",
    "MvtAStageOutputV7",
    "ParserCandidateBundle",
    "RelationCandidate",
    "StageCompletionStatus",
    "StageCoverage",
    "StageErrorCode",
    "StageIssue",
    "StageProvenance",
    "assert_no_final_scientific_fields",
    "attach_verifier",
    "attach_verifier_v7",
    "hard_verify_candidates",
    "hard_verify_candidates_v7",
    "normalize_candidate_syntax",
]
