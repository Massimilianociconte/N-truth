"""PRD v8 Theory-to-Rulebook conformance gate."""

from ntruth.conformance.harness import (
    ConformanceFailure,
    ConformanceFailureCode,
    ConformanceReport,
    evaluate_conformance,
    fixture_set_checksum,
)

__all__ = [
    "ConformanceFailure",
    "ConformanceFailureCode",
    "ConformanceReport",
    "evaluate_conformance",
    "fixture_set_checksum",
]
