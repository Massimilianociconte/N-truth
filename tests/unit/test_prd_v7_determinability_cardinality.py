"""PRD v7 defines exactly seven DeterminabilityStateV7 members."""

from __future__ import annotations

from ntruth.schemas.determinability_v7 import DeterminabilityStateV7

EXPECTED = {
    "DETERMINATE",
    "CONDITIONALLY_DETERMINATE",
    "MULTIPLE_PLAUSIBLE_GRAPHS",
    "INSUFFICIENT_INFORMATION",
    "CONFLICTING_INFORMATION",
    "INVALID_GRAPH",
    "OUT_OF_SCOPE",
}


def test_exactly_seven_determinability_states() -> None:
    names = {m.name for m in DeterminabilityStateV7}
    assert len(DeterminabilityStateV7) == 7
    assert names == EXPECTED
