"""PRD v8 §7.8: every scientific conclusion is scoped to one versioned query."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.query import InferentialQuery


def _present(value: str, *, evidence_id: str = "EV-Q-01") -> KnowledgeValue[str]:
    return KnowledgeValue[str](
        knowledge_state=KnowledgeState.PRESENT,
        value=value,
        evidence_ids=(evidence_id,),
    )


def _unknown(*, query_id: str, rationale: str) -> KnowledgeValue[str]:
    return KnowledgeValue[str](
        knowledge_state=KnowledgeState.UNKNOWN,
        rationale=rationale,
        query_scope_id=query_id,
    )


def _query(*, query_id: str, contrast_id: str, timepoint: str) -> InferentialQuery:
    return InferentialQuery(
        id=query_id,
        profile_id="simple_cell_culture",
        factor_id="treatment",
        contrast_id=contrast_id,
        compared_levels=("vehicle", "drug_x"),
        endpoint_id="viability",
        timepoint_id=_present(timepoint),
        effect_measure_or_estimand=_present("mean_difference"),
        inference_population=_unknown(
            query_id=query_id,
            rationale="source population was not stated",
        ),
        inference_level=_present("culture"),
    )


def test_query_identity_is_contrast_and_timepoint_specific() -> None:
    first = _query(query_id="IQ-001", contrast_id="vehicle_vs_drug", timepoint="T24H")
    second = _query(query_id="IQ-002", contrast_id="vehicle_vs_drug", timepoint="T48H")

    assert first.scope_key() != second.scope_key()
    assert first.schema_version == "8.0.0"
    assert second.schema_version == "8.0.0"


def test_query_rejects_duplicate_levels_and_bare_unknown_strings() -> None:
    with pytest.raises(ValidationError, match="distinct"):
        InferentialQuery(
            id="IQ-001",
            profile_id="simple_cell_culture",
            factor_id="treatment",
            contrast_id="vehicle_vs_drug",
            compared_levels=("vehicle", "vehicle"),
            endpoint_id="viability",
            timepoint_id=_present("T48H"),
            effect_measure_or_estimand=_present("mean_difference"),
            inference_population=_unknown(
                query_id="IQ-001",
                rationale="source population was not stated",
            ),
            inference_level=_present("culture"),
        )

    payload = _query(
        query_id="IQ-001",
        contrast_id="vehicle_vs_drug",
        timepoint="T48H",
    ).model_dump(mode="json")
    payload["inference_population"] = "unknown"
    with pytest.raises(ValidationError):
        InferentialQuery.model_validate(payload)


def test_query_rejects_mismatched_unknown_scope() -> None:
    with pytest.raises(ValidationError, match="query_scope_id"):
        InferentialQuery(
            id="IQ-001",
            profile_id="simple_cell_culture",
            factor_id="treatment",
            contrast_id="vehicle_vs_drug",
            compared_levels=("vehicle", "drug_x"),
            endpoint_id="viability",
            timepoint_id=_present("T48H"),
            effect_measure_or_estimand=_present("mean_difference"),
            inference_population=_unknown(
                query_id="IQ-OTHER",
                rationale="source population was not stated",
            ),
            inference_level=_present("culture"),
        )


def test_v8_contracts_are_available_from_public_schema_exports() -> None:
    import ntruth.schemas as public_schemas
    from ntruth.schemas.causal_context import QueryCausalEventAggregate
    from ntruth.schemas.count_registry import CanonicalCountRecord, CountScopeIdentity
    from ntruth.schemas.events import AssignmentEvent
    from ntruth.schemas.graph_v8 import V8ExperimentGraph

    assert public_schemas.InferentialQuery is InferentialQuery
    assert public_schemas.CanonicalCountRecord is CanonicalCountRecord
    assert public_schemas.CountScopeIdentity is CountScopeIdentity
    assert public_schemas.AssignmentEvent is AssignmentEvent
    assert public_schemas.QueryCausalEventAggregate is QueryCausalEventAggregate
    assert public_schemas.V8ExperimentGraph is V8ExperimentGraph
