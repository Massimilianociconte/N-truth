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
    MvtAStageOutput,
    ParserCandidateBundle,
    assert_no_final_scientific_fields,
)
from ntruth.mvt_a.verifier import HardVerifierResult, hard_verify_candidates

__all__ = [
    "FORBIDDEN_FINAL_FIELDS",
    "BenchmarkManifest",
    "BenchmarkSplitPolicy",
    "BurdenRecord",
    "DecisiveCorrection",
    "FalseCertaintyRecord",
    "HardVerifierResult",
    "HumanRevisionPatch",
    "MvtAStageOutput",
    "ParserCandidateBundle",
    "assert_no_final_scientific_fields",
    "hard_verify_candidates",
]
