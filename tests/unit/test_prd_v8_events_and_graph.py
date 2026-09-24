"""PRD v8 §§7.2, 7.7, 8.4-8.5 and Appendix Y event contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ntruth.schemas.causal_context import InterferenceStatus, QueryCausalContext
from ntruth.schemas.events import (
    ApplicationEvent,
    AssignmentEvent,
    EventRegistry,
    ExposureEvent,
    ObservationEvent,
    PoolEvent,
    RelativeTiming,
    SplitEvent,
    TemporalRelation,
)
from ntruth.schemas.graph import NodeType, RelationType
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue


def _present[T](value: T, *, evidence_id: str = "EV-EVENT-01") -> KnowledgeValue[T]:
    return KnowledgeValue[T](
        knowledge_state=KnowledgeState.PRESENT,
        value=value,
        evidence_ids=(evidence_id,),
    )


def _events() -> tuple[
    AssignmentEvent,
    SplitEvent,
    ApplicationEvent,
    ExposureEvent,
    PoolEvent,
    ObservationEvent,
]:
    assignment = AssignmentEvent(
        event_id="EVT-ASSIGN-01",
        experiment_block_id="EB-01",
        factor_id="treatment",
        assigned_unit_type=_present("culture"),
        assigned_unit_ids=_present(("culture_01", "culture_02")),
        evidence_refs=("EV-EVENT-01",),
    )
    split = SplitEvent(
        event_id="EVT-SPLIT-02",
        experiment_block_id="EB-01",
        source_unit_ids=_present(("culture_01", "culture_02")),
        resulting_unit_ids=_present(("well_A", "well_B")),
        evidence_refs=("EV-EVENT-02",),
    )
    application = ApplicationEvent(
        event_id="EVT-APPLY-01",
        experiment_block_id="EB-01",
        factor_id="treatment",
        intervention_id=_present("drug_x"),
        application_unit_type=_present("well"),
        application_unit_ids=_present(("well_A", "well_B")),
        evidence_refs=("EV-EVENT-03",),
    )
    exposure = ExposureEvent(
        event_id="EVT-EXPOSURE-01",
        experiment_block_id="EB-01",
        exposure_pathway=_present("shared_medium"),
        exposure_container=_present("plate"),
        effective_exposure_unit=_present("plate_01"),
        exposed_unit_ids=_present(("well_A", "well_B")),
        evidence_refs=("EV-EVENT-04",),
    )
    pool = PoolEvent(
        event_id="EVT-POOL-01",
        experiment_block_id="EB-01",
        source_unit_ids=_present(("well_A", "well_B")),
        pooled_unit_id=_present("pool_01"),
        evidence_refs=("EV-EVENT-05",),
    )
    observation = ObservationEvent(
        event_id="EVT-OBSERVE-01",
        experiment_block_id="EB-01",
        endpoint_id="viability",
        measured_on_unit_ids=_present(("well_A", "well_B")),
        timepoint_id=_present("T48H"),
        evidence_refs=("EV-EVENT-06",),
    )
    return assignment, split, application, exposure, pool, observation


def _causal_context() -> QueryCausalContext:
    return QueryCausalContext(
        inferential_query_id="IQ-001",
        assignment_event_id=_present("EVT-ASSIGN-01"),
        application_event_id=_present("EVT-APPLY-01"),
        exposure_event_id=_present("EVT-EXPOSURE-01"),
        assignment_unit_type=_present("culture"),
        application_unit_type=_present("well"),
        effective_exposure_unit_type=_present("plate"),
        experimental_unit_type=_present("culture"),
        biological_source_unit_type=_present("donor"),
        interference_status=_present(InterferenceStatus.DOCUMENTED),
    )


def test_event_referenced_timing_requires_existing_event_ids() -> None:
    events = _events()
    timing = RelativeTiming(
        subject_event_id="EVT-APPLY-01",
        reference_event_id="EVT-SPLIT-02",
        relation=TemporalRelation.AFTER,
        evidence_refs=("EV-EVENT-07",),
    )
    registry = EventRegistry(events=events, relative_timings=(timing,))
    assert registry.event("EVT-APPLY-01") == events[2]

    bad = timing.model_copy(update={"reference_event_id": "EVT-INVENTED"})
    with pytest.raises(ValidationError, match="unknown reference_event_id"):
        EventRegistry(events=events, relative_timings=(bad,))


def test_unknown_timing_is_explicit_and_needs_rationale() -> None:
    with pytest.raises(ValidationError, match="UNKNOWN timing requires rationale"):
        RelativeTiming(
            subject_event_id="EVT-APPLY-01",
            reference_event_id="EVT-SPLIT-02",
            relation=TemporalRelation.UNKNOWN,
        )

    timing = RelativeTiming(
        subject_event_id="EVT-APPLY-01",
        reference_event_id="EVT-SPLIT-02",
        relation=TemporalRelation.UNKNOWN,
        rationale="the source does not order the two events",
    )
    assert timing.relation is TemporalRelation.UNKNOWN


def test_causal_unit_roles_remain_distinct_without_resolver_side_effects() -> None:
    context = _causal_context()

    assert context.effective_exposure_unit_type.value == "plate"
    assert context.experimental_unit_type.value == "culture"
    assert context.biological_source_unit_type.value == "donor"


def test_causal_event_aggregate_resolves_valid_typed_references() -> None:
    from ntruth.schemas.causal_context import QueryCausalEventAggregate

    context = _causal_context()
    aggregate = QueryCausalEventAggregate(
        experiment_block_id="EB-01",
        event_registry=EventRegistry(events=_events()),
        causal_context=context,
    )
    assert aggregate.causal_context == context


def test_causal_event_aggregate_rejects_dangling_reference() -> None:
    from ntruth.schemas.causal_context import QueryCausalEventAggregate

    context = _causal_context().model_copy(update={"assignment_event_id": _present("EVT-MISSING")})
    with pytest.raises(ValidationError, match="dangling assignment_event_id"):
        QueryCausalEventAggregate(
            experiment_block_id="EB-01",
            event_registry=EventRegistry(events=_events()),
            causal_context=context,
        )


def test_causal_event_aggregate_rejects_wrong_event_type() -> None:
    from ntruth.schemas.causal_context import QueryCausalEventAggregate

    context = _causal_context().model_copy(update={"assignment_event_id": _present("EVT-APPLY-01")})
    with pytest.raises(ValidationError, match="assignment_event_id requires AssignmentEvent"):
        QueryCausalEventAggregate(
            experiment_block_id="EB-01",
            event_registry=EventRegistry(events=_events()),
            causal_context=context,
        )


def test_causal_event_aggregate_rejects_cross_block_reference() -> None:
    from ntruth.schemas.causal_context import QueryCausalEventAggregate

    events = list(_events())
    events[0] = events[0].model_copy(update={"experiment_block_id": "EB-OTHER"})
    with pytest.raises(
        ValidationError,
        match="every event registry entry must share the aggregate Experiment Block",
    ):
        QueryCausalEventAggregate(
            experiment_block_id="EB-01",
            event_registry=EventRegistry(events=tuple(events)),
            causal_context=_causal_context(),
        )


def test_v7_graph_vocabulary_rejects_v8_only_tokens() -> None:
    with pytest.raises(ValueError):
        NodeType("AssignmentEvent")
    with pytest.raises(ValueError):
        RelationType("contained_in")
