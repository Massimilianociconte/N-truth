"""Causal Design Context and four independence dimensions."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ntruth.schemas.bootstrap_core import (
    BootstrapCoreRecord,
    CoreRelation,
    CoreSourceRef,
    CoreUnit,
)
from ntruth.schemas.causal_context import (
    ComparabilityBasis,
    IndependenceProfile,
    InterferenceAssessment,
    InterferenceStatus,
    TriState,
)


def test_silence_is_not_no_interference() -> None:
    with pytest.raises(ValidationError):
        InterferenceAssessment(status=InterferenceStatus.NO_KNOWN_PATH, evidence_ids=())


def test_exchangeable_property_forbidden() -> None:
    basis = ComparabilityBasis()
    with pytest.raises(AttributeError, match="exchangeable"):
        _ = basis.exchangeable


def test_independently_assigned_true_needs_evidence() -> None:
    with pytest.raises(ValidationError):
        IndependenceProfile(independently_assigned=TriState.TRUE, evidence_ids=())


def test_bootstrap_core_minimal_valid() -> None:
    rec = BootstrapCoreRecord(
        experiment_block_id="eb-1",
        sources=(CoreSourceRef(source_id="s1"),),
        units=(
            CoreUnit(id="u1", type="source"),
            CoreUnit(id="u2", type="culture"),
        ),
        relations=(CoreRelation(source="u2", type="derived_from", target="u1"),),
        factor_id="treatment",
        factor_levels=("ctrl", "tx"),
        endpoint_id="viability",
        primary_contrast_id="ctrl_vs_tx",
    )
    assert rec.schema_version == "7.0.0"
    assert rec.independently_assigned == "UNKNOWN"
