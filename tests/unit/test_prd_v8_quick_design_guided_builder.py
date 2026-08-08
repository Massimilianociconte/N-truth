"""TDD regressions for the guided PRD v8 Quick Design builder."""

from __future__ import annotations

from datetime import UTC, datetime
from importlib import import_module

import pytest

from ntruth.quick_design import QuickDesignScientificReviewRequired
from ntruth.schemas.authority import AuthorityType
from ntruth.schemas.count_registry import (
    CanonicalCountKind,
    CanonicalCountRecord,
    CanonicalCountRegistry,
    CountCompatibility,
    CountLifecyclePhase,
    CountOrigin,
    CountQuantifier,
    CountScope,
    count_compatibility,
)
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.support import EvidenceBasis, EvidenceTypeV8

QUERY_ID = "IQ-GUIDED-001"


def _unknown(rationale: str) -> KnowledgeValue[object]:
    return KnowledgeValue(
        knowledge_state=KnowledgeState.UNKNOWN,
        rationale=rationale,
        evidence_ids=("EV-GUIDED-REVIEW",),
        query_scope_id=QUERY_ID,
    )


def _present(value: object) -> KnowledgeValue[object]:
    return KnowledgeValue(
        knowledge_state=KnowledgeState.PRESENT,
        value=value,
        evidence_ids=("EV-GUIDED-REVIEW",),
        query_scope_id=QUERY_ID,
    )


def _unresolved_count(kind: CanonicalCountKind) -> CanonicalCountRecord:
    return CanonicalCountRecord(
        count_id=f"COUNT-{kind.value}-GUIDED",
        kind=kind,
        value=_unknown("The guided review did not establish this scientific count."),
        quantifier=CountQuantifier.UNKNOWN,
        scope=CountScope(
            query_id=QUERY_ID,
            unit_type=_unknown("The scientific unit type remains unresolved."),
            factor_id=_present("FACTOR-GUIDED"),
            contrast_id=_present("CONTRAST-GUIDED"),
            group_id=_unknown("No scientific count group was established."),
            endpoint_id=_present("ENDPOINT-GUIDED"),
            timepoint_id=_present("T24H"),
            cohort_id=_unknown("No scientific cohort identity was established."),
            lifecycle_phase=_present(CountLifecyclePhase.PLANNED),
            population_scope=_present("declared_population"),
            condition=_unknown("No scientific count condition was established."),
        ),
        source_evidence=("EV-GUIDED-REVIEW",),
        origin=CountOrigin.HUMAN_CONFIRMATION,
    )


def test_unknown_eu_and_source_counts_retain_unresolved_scope_without_collision_claims() -> None:
    """Catches forcing UNKNOWN scientific counts into a falsely resolved scope."""

    eu = _unresolved_count(CanonicalCountKind.EXPERIMENTAL_UNIT_COUNT)
    source = _unresolved_count(CanonicalCountKind.BIOLOGICAL_SOURCE_COUNT)

    registry = CanonicalCountRegistry(records=(eu, source))

    assert registry.records == (eu, source)
    assert all(record.semantic_identity() is None for record in registry.records)
    assert count_compatibility(eu, source) is CountCompatibility.REVIEW_REQUIRED


def test_present_count_with_unresolved_scope_still_fails_closed() -> None:
    """Catches unresolved scope becoming admissible merely because a number is present."""

    unresolved = _unresolved_count(CanonicalCountKind.EXPERIMENTAL_UNIT_COUNT)
    forged_present = unresolved.model_copy(
        update={
            "value": _present(2),
            "quantifier": CountQuantifier.EXACT,
        }
    )

    with pytest.raises(ValueError, match=r"scope|SCIENTIFIC_REVIEW_REQUIRED"):
        CanonicalCountRegistry(records=(forged_present,))


def _guided() -> object:
    return import_module("ntruth.quick_design.guided")


def _answer(module: object, value: str) -> object:
    return module.GuidedTextAnswer(status="PROVIDED", value=value)


def _ids(module: object, *values: str) -> object:
    return module.GuidedIdSetAnswer(status="PROVIDED", values=values)


def _draft(*, planned_unit_available: bool = True) -> object:
    module = _guided()

    def provided(value: str) -> object:
        return _answer(module, value)

    def unavailable(rationale: str) -> object:
        return module.GuidedTextAnswer(
            status="NOT_AVAILABLE",
            rationale=rationale,
        )

    def unavailable_ids(rationale: str) -> object:
        return module.GuidedIdSetAnswer(
            status="NOT_AVAILABLE",
            rationale=rationale,
        )

    return module.GuidedQuickDesignDraft(
        template_id="simple_cell_culture",
        block_title="Dose response in cultured cells",
        source_description=provided("Primary fibroblast cultures"),
        preparation_description=provided("One culture preparation per donor"),
        biological_source_unit_type=provided("culture_preparation"),
        candidate_unit_type=provided("well"),
        factor_id="treatment",
        factor_levels=("vehicle", "drug"),
        contrast_id="vehicle_vs_drug",
        endpoint_id="viability",
        timepoint_id="T24H",
        estimand="mean_difference",
        population_scope="cultures_under_protocol_x",
        inference_level="culture",
        assignment_unit_type=provided("well"),
        assignment_unit_ids=_ids(module, "assign-well-01", "assign-well-02"),
        application_unit_type=provided("well"),
        application_unit_ids=_ids(module, "application-well-a", "application-well-b"),
        intervention_id=provided("drug-batch-2026-08"),
        effective_exposure_unit_type=unavailable(
            "The effective exposure unit has not been established in the plan."
        ),
        exposed_unit_ids=unavailable_ids(
            "The planned exposure-unit identities have not been established."
        ),
        exposure_pathway=provided("direct_medium_addition"),
        exposure_container=provided("plate-01"),
        interference=module.GuidedInterferenceAnswer(
            status="POSSIBLE",
            rationale="A shared plate environment could connect wells.",
        ),
        assignment_to_application_timing=module.GuidedTimingAnswer(
            status="PROVIDED",
            relation="BEFORE",
        ),
        planned_unit_type=(
            provided("well")
            if planned_unit_available
            else unavailable("The planned unit type was not provided for review.")
        ),
        planned_groups=(
            module.GuidedPlannedGroup(
                group_id="vehicle",
                factor_level="vehicle",
                planned_count=2,
            ),
            module.GuidedPlannedGroup(
                group_id="drug",
                factor_level="drug",
                planned_count=2,
            ),
        ),
    )


def _preview(draft: object | None = None) -> object:
    module = _guided()
    return module.build_guided_quick_design(
        module.GuidedQuickDesignBuildRequest(
            action="PREVIEW",
            draft=draft or _draft(),
        )
    )


def _confirm(preview: object, draft: object | None = None) -> object:
    module = _guided()
    primary = preview.visible_questions[0]
    return module.build_guided_quick_design(
        module.GuidedQuickDesignBuildRequest(
            action="CONFIRM",
            draft=draft or _draft(),
            confirmation=module.GuidedQuickDesignConfirmation(
                preview_checksum=preview.preview_checksum,
                primary_predicate_id=primary.predicate_id,
                actor_role="researcher",
                confirmed_at=datetime(2026, 8, 9, 8, 30, tzinfo=UTC),
            ),
        )
    )


def test_guided_preview_is_deterministic_and_retains_the_full_theory_question_queue() -> None:
    """Catches replacing the guided draft with free-form JSON or truncating scenarios."""

    first = _preview()
    second = _preview()

    assert first == second
    assert first.submission.knowledge_state is KnowledgeState.UNKNOWN
    assert len(first.visible_questions) == 3
    assert len(first.question_queue) > len(first.visible_questions)
    assert first.visible_questions == first.question_queue[:3]
    assert all(question.theory_clause_ids for question in first.question_queue)
    assert len(first.artifact_previews) == 3
    assert {artifact.kind.value for artifact in first.artifact_previews} == {
        "SAMPLE_SHEET",
        "METHODS_DRAFT",
        "ID_CONVENTION",
    }
    assert first.summary.scenario_coverage_status == "NON_EXHAUSTIVE"
    assert first.summary.strategy_module_status == "HANDOFF_ONLY"
    assert first.contract_code == "NTRUTH_QUICK_DESIGN_GUIDED_V8"
    assert first.contract_version == "8.0.0"
    assert first.state == "REVIEW_REQUIRED"
    assert first.next_endpoint == "/v8/quick-design"
    assert all(question.required_predicate_rationales for question in first.question_queue)
    assert all(
        question.text == " ".join(question.required_predicate_rationales)
        for question in first.question_queue
    )


def test_guided_confirmation_builds_only_user_supported_canonical_facts() -> None:
    """Catches server-side invention of EU, counts, interference or adequacy facts."""

    module = _guided()
    preview = _preview()
    confirmed = _confirm(preview)
    submission = confirmed.submission.value
    assert submission is not None

    assert confirmed.submission.knowledge_state is KnowledgeState.PRESENT
    assert confirmed.preview_checksum == preview.preview_checksum
    assert confirmed.state == "BUILT"
    assert confirmed.artifact_previews == submission.input_ledger.artifacts
    assert all(
        descriptor.authority_type is AuthorityType.USER_CONFIRMATION
        and descriptor.evidence_basis is EvidenceBasis.AUTHOR_ASSERTED
        and descriptor.support_grade.token == "ASSERTION_ONLY"
        for descriptor in submission.pipeline_request.support_by_clause.values()
    )
    assert {record.evidence_type for record in submission.input_ledger.evidence_records} == {
        EvidenceTypeV8.USER_CONFIRMATION
    }

    predicates = submission.pipeline_request.predicate_values
    must_remain_unknown = {
        "assignment_separability_support",
        "assignment_separability",
        "realized_exposure_separability",
        "experimental_unit_instances",
        "confirmed_biological_provenance",
        "biological_source_instances",
        "claim_no_interference_dependency",
        "analytical_grouping",
        "repeated_measure_status",
        "measurement_process",
        "source_diversity",
        "protocol_scope",
        "external_replication",
        "exposure_interference",
        "profile_coverage",
        "realized_treatment_application_or_exposure",
        "biological_source_independence",
    }
    assert must_remain_unknown <= predicates.keys()
    assert all(
        predicates[predicate_id].knowledge_state is KnowledgeState.UNKNOWN
        for predicate_id in must_remain_unknown
    )
    assert (
        submission.pipeline_request.causal_aggregate.causal_context.experimental_unit_type.knowledge_state
        is (KnowledgeState.UNKNOWN)
    )
    count_by_kind = {
        record.kind: record for record in submission.pipeline_request.count_registry.records
    }
    assert count_by_kind[CanonicalCountKind.EXPERIMENTAL_UNIT_COUNT].value.knowledge_state is (
        KnowledgeState.UNKNOWN
    )
    assert count_by_kind[CanonicalCountKind.BIOLOGICAL_SOURCE_COUNT].value.knowledge_state is (
        KnowledgeState.UNKNOWN
    )
    assert all(
        count.value.knowledge_state is KnowledgeState.PRESENT
        for count in submission.planned_unit_counts
    )
    assert [count.value.value for count in submission.planned_unit_counts] == [2, 2]
    assert submission.pipeline_request.scenario_coverages[0].status.value == "NON_EXHAUSTIVE"
    assert submission.ai_candidates.knowledge_state is KnowledgeState.NOT_APPLICABLE
    assert submission.conflicts.knowledge_state is KnowledgeState.NOT_REPORTED
    assert submission.sensitivities.knowledge_state is KnowledgeState.UNKNOWN
    assert submission.statistical_handoff.strategy_module_status.value == "HANDOFF_ONLY"

    assignment, application, exposure = submission.planned_event_registry.events
    assert assignment.assigned_unit_ids.value == ("assign-well-01", "assign-well-02")
    assert application.application_unit_ids.value == (
        "application-well-a",
        "application-well-b",
    )
    assert assignment.assigned_unit_ids.value != application.application_unit_ids.value
    assert application.intervention_id.value == "drug-batch-2026-08"
    assert exposure.exposed_unit_ids.knowledge_state is KnowledgeState.UNKNOWN
    assert exposure.exposure_pathway.value == "direct_medium_addition"
    assert exposure.exposure_container.value == "plate-01"

    # Explicit planned facts do not become scientific consequences by proxy.
    assert predicates["realized_treatment_application_or_exposure"].knowledge_state is (
        KnowledgeState.UNKNOWN
    )
    assert predicates["experimental_unit_instances"].knowledge_state is KnowledgeState.UNKNOWN
    assert predicates["biological_source_instances"].knowledge_state is KnowledgeState.UNKNOWN
    assert predicates["biological_source_independence"].knowledge_state is (KnowledgeState.UNKNOWN)
    assert (
        submission.pipeline_request.causal_aggregate.causal_context.interference_status.value.value
        == ("possible")
    )
    assert (
        submission.pipeline_request.causal_aggregate.causal_context.experimental_unit_type.knowledge_state
        is (KnowledgeState.UNKNOWN)
    )

    result = module.run_confirmed_guided_quick_design(confirmed)
    assert result.report_bundle.strategy_module_status.value == "HANDOFF_ONLY"


def test_guided_confirmation_recomputes_checksum_and_primary_question() -> None:
    """Catches confirming a stale preview or a non-Theory primary predicate."""

    module = _guided()
    preview = _preview()
    for checksum, predicate_id, match in (
        ("0" * 64, preview.visible_questions[0].predicate_id, "checksum"),
        (preview.preview_checksum, "not-a-theory-predicate", "primary"),
    ):
        with pytest.raises(ValueError, match=match):
            module.build_guided_quick_design(
                module.GuidedQuickDesignBuildRequest(
                    action="CONFIRM",
                    draft=_draft(),
                    confirmation=module.GuidedQuickDesignConfirmation(
                        preview_checksum=checksum,
                        primary_predicate_id=predicate_id,
                        actor_role="researcher",
                        confirmed_at=datetime(2026, 8, 9, 8, 30, tzinfo=UTC),
                    ),
                )
            )


def test_guided_confirmation_requires_timezone_aware_review_time() -> None:
    """Catches an unauditable local timestamp entering the confirmation ledger."""

    module = _guided()
    preview = _preview()
    with pytest.raises(ValueError, match=r"timezone|fuso|offset"):
        module.GuidedQuickDesignConfirmation(
            preview_checksum=preview.preview_checksum,
            primary_predicate_id=preview.visible_questions[0].predicate_id,
            actor_role="researcher",
            confirmed_at=datetime(2026, 8, 9, 8, 30),
        )


def test_guided_planned_count_with_unresolved_unit_scope_fails_closed() -> None:
    """Catches a planned number being promoted without its user-declared unit scope."""

    preview = _preview(_draft(planned_unit_available=False))

    with pytest.raises(QuickDesignScientificReviewRequired, match="planned_unit_count"):
        _confirm(preview, _draft(planned_unit_available=False))


def test_guided_event_unit_sets_are_not_copied_between_causal_axes() -> None:
    """Catches collapsing assignment, application and effective exposure into one axis."""

    module = _guided()
    base = _draft()
    missing_application_ids = module.GuidedQuickDesignDraft.model_validate(
        {
            **base.model_dump(mode="python"),
            "application_unit_ids": {
                "status": "NOT_AVAILABLE",
                "rationale": "Application membership has not been listed.",
            },
        }
    )
    confirmed = _confirm(_preview(missing_application_ids), missing_application_ids)
    submission = confirmed.submission.value
    assert submission is not None
    assignment, application, exposure = submission.planned_event_registry.events

    assert assignment.assigned_unit_ids.knowledge_state is KnowledgeState.PRESENT
    assert application.application_unit_ids.knowledge_state is KnowledgeState.UNKNOWN
    assert exposure.exposed_unit_ids.knowledge_state is KnowledgeState.UNKNOWN
