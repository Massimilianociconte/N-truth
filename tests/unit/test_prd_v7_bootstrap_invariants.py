"""Bootstrap Core internal consistency (PRD v7 §8.2A)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ntruth.schemas.bootstrap_core import (
    BootstrapCoreRecord,
    CoreRelation,
    CoreSourceRef,
    CoreUnit,
)
from ntruth.schemas.causal_context import CausalDesignContext, IndependenceProfile, TriState
from ntruth.schemas.inferential_query import InferentialQuery


def _base(**kwargs):
    data = dict(
        experiment_block_id="eb-1",
        sources=(CoreSourceRef(source_id="s1"),),
        units=(
            CoreUnit(id="u1", type="source"),
            CoreUnit(id="u2", type="preparation"),
            CoreUnit(id="u3", type="culture"),
        ),
        relations=(
            CoreRelation(source="u2", type="derived_from", target="u1"),
            CoreRelation(source="u3", type="derived_from", target="u2"),
        ),
        factor_id="treatment",
        factor_levels=("ctrl", "tx"),
        endpoint_id="viability",
        primary_contrast_id="ctrl_vs_tx",
        source_preparation_id="u2",
    )
    data.update(kwargs)
    return BootstrapCoreRecord(**data)


def test_independently_assigned_must_match_nested() -> None:
    with pytest.raises(ValidationError):
        _base(
            independently_assigned="TRUE",
            independence=IndependenceProfile(
                independently_assigned=TriState.FALSE, evidence_ids=("e1",)
            ),
        )


def test_source_preparation_must_reference_unit() -> None:
    with pytest.raises(ValidationError):
        _base(source_preparation_id="missing")


def test_causal_context_factor_must_match() -> None:
    with pytest.raises(ValidationError):
        _base(causal_context=CausalDesignContext(factor_id="other"))


def test_inferential_query_must_align() -> None:
    with pytest.raises(ValidationError):
        _base(
            inferential_query=InferentialQuery(
                id="iq-1",
                factor_id="other",
                compared_levels=("ctrl", "tx"),
                endpoint_id="viability",
            )
        )


def test_relation_type_must_be_registered() -> None:
    with pytest.raises(ValidationError):
        _base(relations=(CoreRelation(source="u2", type="invented_edge", target="u1"),))


def test_determinability_derived_enum_only() -> None:
    with pytest.raises(ValidationError):
        _base(determinability_derived="MAYBE")


def test_reviewed_requires_event() -> None:
    with pytest.raises(ValidationError):
        _base(
            determinability_derived="INSUFFICIENT_INFORMATION",
            determinability_reviewed=True,
        )
    ok = _base(
        determinability_derived="INSUFFICIENT_INFORMATION",
        determinability_reviewed=True,
        determinability_review_event_id="conf-review-1",
    )
    assert ok.determinability_reviewed is True
