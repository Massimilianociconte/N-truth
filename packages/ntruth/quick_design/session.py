"""Quick Design Session service for simple_cell_culture (PRD v7 §6.1).

Independence dimensions stay distinct: biological-source independence is never
used as a proxy for assignment independence. Sample-sheet IDs are non-semantic
placeholders unless the user supplies structure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ntruth.graph.determinability_v7 import V7GraphFacts, derive_determinability_v7
from ntruth.quick_design.templates import (
    build_id_convention,
    build_methods_draft,
    build_sample_sheet,
)
from ntruth.schemas.bootstrap_core import (
    BootstrapCoreRecord,
    CoreRelation,
    CoreSourceRef,
    CoreUnit,
    MissingDecisiveFact,
    make_block_id,
)
from ntruth.schemas.causal_context import (
    AssignmentLevel,
    AssignmentMechanism,
    AssignmentMethod,
    CausalDesignContext,
    IndependenceProfile,
    InterferenceAssessment,
    InterferenceStatus,
    SplitTiming,
    TriState,
)
from ntruth.schemas.counts import CountKind, CountOrigin, CountRecord, Quantifier, make_count_id
from ntruth.schemas.determinability_v7 import DeterminabilityStateV7
from ntruth.schemas.inferential_query import InferentialQuery, make_query_id

ProfileId = Literal["simple_cell_culture"]
VALID_ALLOCATION_LEVELS = frozenset({"well", "culture", "plate", "animal", "unknown"})
VALID_TRI = frozenset({"TRUE", "FALSE", "UNKNOWN"})
RANDOM_METHODS = frozenset({"random", "blocked_random"})


@dataclass(frozen=True)
class QuickDesignAnswers:
    source_description: str
    preparation_description: str = "unknown"
    unit_hierarchy: tuple[str, ...] = ("source", "culture", "well")
    factor_id: str = "treatment"
    levels: tuple[str, str] = ("control", "treated")
    endpoint_id: str = "viability"
    contrast_id: str = "control_vs_treated"
    allocation_level: str = "unknown"
    application_level: str | None = "unknown"
    assignment_timing: str = "unknown"
    assignment_method: str = "unknown"
    randomization_unit: str | None = None
    independently_assigned: str = "UNKNOWN"
    biological_source_independence: str = "UNKNOWN"
    interference_status: str = "UNKNOWN"
    exposure_unit: str | None = None
    shared_environment: tuple[str, ...] = ()
    planned_unit_type: str = "unknown"
    planned_units_per_level: int | None = None
    source_ids: tuple[str, ...] = ()
    preparation_ids: tuple[str, ...] = ()
    primary_question: str = ""
    block_label: str = "qd_session"
    assignment_confirmation_event_id: str | None = None


@dataclass(frozen=True)
class QuickDesignResult:
    bootstrap: BootstrapCoreRecord
    determinability: DeterminabilityStateV7
    sample_sheet_csv: str
    id_convention: str
    methods_draft: str
    primary_question: str
    plan_frozen: bool = False
    export_payload: dict[str, object] | None = None
    user_confirmation_scopes: tuple[str, ...] = ()


def _tri(value: str) -> TriState:
    key = value.strip().upper()
    if key not in VALID_TRI:
        return TriState.UNKNOWN
    return TriState(key)


def _interference(value: str) -> InterferenceStatus:
    mapping = {
        "UNKNOWN": InterferenceStatus.UNKNOWN,
        "NO_KNOWN_PATH": InterferenceStatus.NO_KNOWN_PATH,
        "POSSIBLE": InterferenceStatus.POSSIBLE,
        "DOCUMENTED": InterferenceStatus.DOCUMENTED,
    }
    return mapping.get(value.upper(), InterferenceStatus.UNKNOWN)


def _split_timing(value: str) -> SplitTiming:
    mapping = {
        "before": SplitTiming.BEFORE,
        "after": SplitTiming.AFTER,
        "same_event": SplitTiming.SAME_EVENT,
        "unknown": SplitTiming.UNKNOWN,
    }
    return mapping.get(value.lower(), SplitTiming.UNKNOWN)


def _assignment_method(value: str) -> AssignmentMethod:
    try:
        return AssignmentMethod(value.lower())
    except ValueError:
        return AssignmentMethod.UNKNOWN


def _assignment_level(value: str) -> AssignmentLevel:
    key = value.lower().strip()
    if key not in VALID_ALLOCATION_LEVELS:
        return AssignmentLevel.UNKNOWN
    try:
        return AssignmentLevel(key)
    except ValueError:
        return AssignmentLevel.UNKNOWN


def run_quick_design_session(answers: QuickDesignAnswers) -> QuickDesignResult:
    if answers.planned_units_per_level is not None and answers.planned_units_per_level <= 0:
        raise ValueError("planned_units_per_level must be positive when provided")
    if len(answers.unit_hierarchy) < 2:
        raise ValueError("unit_hierarchy requires at least two levels for simple_cell_culture")

    block_id = make_block_id("simple_cell_culture", answers.block_label)
    source_id, prep_id, culture_id, well_id = "U_source", "U_prep", "U_culture", "U_well"
    units = (
        CoreUnit(id=source_id, type="source", label=answers.source_description),
        CoreUnit(id=prep_id, type="preparation", label=answers.preparation_description),
        CoreUnit(id=culture_id, type="culture", label="culture"),
        CoreUnit(id=well_id, type="well", label="well"),
    )
    relations = (
        CoreRelation(source=prep_id, type="derived_from", target=source_id),
        CoreRelation(source=culture_id, type="derived_from", target=prep_id),
        CoreRelation(source=well_id, type="nested_in", target=culture_id),
    )

    allocation_level = answers.allocation_level.lower().strip()
    if allocation_level not in VALID_ALLOCATION_LEVELS:
        allocation_level = "unknown"
    allocation_known = allocation_level != "unknown"

    assign_method = _assignment_method(answers.assignment_method)
    randomization_unit: str | None = None
    if assign_method.value in RANDOM_METHODS:
        if answers.randomization_unit:
            randomization_unit = answers.randomization_unit
        elif allocation_known:
            randomization_unit = allocation_level

    bio_ind = _tri(answers.biological_source_independence)
    assign_ind = _tri(answers.independently_assigned)
    interf = _interference(answers.interference_status)

    if interf is InterferenceStatus.NO_KNOWN_PATH:
        if not answers.assignment_confirmation_event_id and not answers.shared_environment:
            interf = InterferenceStatus.UNKNOWN
            interference_assessment = InterferenceAssessment(status=InterferenceStatus.UNKNOWN)
        else:
            evidence = (
                (answers.assignment_confirmation_event_id,)
                if answers.assignment_confirmation_event_id
                else ("user_declared_no_known_path",)
            )
            interference_assessment = InterferenceAssessment(
                status=InterferenceStatus.NO_KNOWN_PATH,
                exposure_unit=answers.exposure_unit,
                shared_environment=answers.shared_environment,
                evidence_ids=evidence,
            )
    else:
        interference_assessment = InterferenceAssessment(
            status=interf,
            exposure_unit=answers.exposure_unit,
            shared_environment=answers.shared_environment,
        )

    assignment = AssignmentMechanism(
        level=_assignment_level(allocation_level),
        method=assign_method,
        timing_relative_to_split=_split_timing(answers.assignment_timing),
        randomization_unit=randomization_unit,
    )
    causal = CausalDesignContext(
        factor_id=answers.factor_id,
        assignment_mechanism=assignment,
        interference_assessment=interference_assessment,
    )

    assign_evidence: tuple[str, ...] = ()
    if assign_ind is TriState.TRUE:
        if answers.assignment_confirmation_event_id:
            assign_evidence = (answers.assignment_confirmation_event_id,)
        else:
            assign_ind = TriState.UNKNOWN

    independence = IndependenceProfile(
        independently_assigned=assign_ind,
        biological_source_independence=bio_ind,
        interference_status=interference_assessment.status,
        analytical_grouping=(),
        evidence_ids=assign_evidence,
    )

    planned_unit_type = answers.planned_unit_type.strip() or "unknown"
    counts: tuple[CountRecord, ...] = ()
    if answers.planned_units_per_level is not None:
        unit_type = planned_unit_type if planned_unit_type != "unknown" else None
        cid = make_count_id(CountKind.DECLARED_N, f"{answers.factor_id}|{answers.endpoint_id}")
        counts = (
            CountRecord(
                id=cid,
                kind=CountKind.DECLARED_N,
                value=answers.planned_units_per_level,
                unit_type=unit_type,
                factor_id=answers.factor_id,
                contrast_id=answers.contrast_id,
                endpoint_id=answers.endpoint_id,
                quantifier=Quantifier.EXACT,
                origin=CountOrigin.SAMPLE_SHEET,
            ),
        )

    levels = answers.levels
    query = InferentialQuery(
        id=make_query_id(answers.factor_id, answers.endpoint_id, levels),
        factor_id=answers.factor_id,
        compared_levels=levels,
        endpoint_id=answers.endpoint_id,
        effect_measure_or_estimand="unknown",
        inference_population="unknown",
        inference_level="unknown",
    )

    assignment_independence_known = assign_ind is not TriState.UNKNOWN
    bio_known = bio_ind is not TriState.UNKNOWN
    interference_unknown = interference_assessment.status is InterferenceStatus.UNKNOWN

    missing: MissingDecisiveFact | None = None
    primary_q = answers.primary_question.strip()
    if not allocation_known:
        missing = MissingDecisiveFact(
            predicate="allocation_level", rationale="required-or-UNKNOWN bootstrap field"
        )
        primary_q = primary_q or (
            f"At which unit level was {answers.factor_id} allocated "
            f"(well, culture, plate, or other)?"
        )
    elif not assignment_independence_known:
        missing = MissingDecisiveFact(
            predicate="independently_assigned",
            rationale="assignment independence distinct from biological-source independence",
        )
        primary_q = primary_q or (
            f"Were {answers.factor_id} levels assigned independently across experimental units?"
        )
    elif interference_unknown:
        missing = MissingDecisiveFact(
            predicate="interference_assessment",
            rationale="silence is UNKNOWN, never absence of interference",
        )
        primary_q = primary_q or (
            "Is there shared exposure or interference between experimental units?"
        )

    facts = V7GraphFacts(
        allocation_known=allocation_known,
        operational_independence_known=assignment_independence_known,
        contrast_defined=True,
        endpoint_defined=bool(answers.endpoint_id.strip()),
        counts_sufficient=answers.planned_units_per_level is not None,
        interference_unknown=interference_unknown,
        graph_invariants_ok=True,
        in_scope=True,
        alternative_graph_count=0,
        missing_predicate=missing.predicate if missing else None,
        enumerable_branches=False,
        assertion_only=False,
        decisive_fields=frozenset({"allocation_level", "independently_assigned", "interference"}),
    )
    state = derive_determinability_v7(facts)

    user_scopes: list[str] = []
    if allocation_known:
        user_scopes.append("allocation_level")
    if assignment_independence_known:
        user_scopes.append("independently_assigned")
    if bio_known:
        user_scopes.append("biological_source_independence")
    if not interference_unknown:
        user_scopes.append("interference_assessment")

    bootstrap = BootstrapCoreRecord(
        experiment_block_id=block_id,
        domain="simple_cell_culture",
        sources=(CoreSourceRef(source_id="user_session", evidence_ids=(), license_status="n/a"),),
        units=units,
        relations=relations,
        factor_id=answers.factor_id,
        factor_levels=levels,
        endpoint_id=answers.endpoint_id,
        primary_contrast_id=answers.contrast_id,
        allocation_level=allocation_level,
        application_level=answers.application_level if answers.application_level else "unknown",
        independently_assigned=assign_ind.value,
        source_preparation_id=prep_id,
        independence=independence,
        causal_context=causal,
        counts=counts,
        missing_decisive_fact=missing,
        primary_question=primary_q,
        inferential_query=query,
        determinability_derived=state,
        determinability_reviewed=False,
    )

    n_rows = answers.planned_units_per_level if answers.planned_units_per_level is not None else 1
    rows: list[dict[str, str]] = []
    row_idx = 0
    for level in levels:
        for _ in range(n_rows):
            row_idx += 1
            source_ref = (
                answers.source_ids[(row_idx - 1) % len(answers.source_ids)]
                if answers.source_ids
                else ""
            )
            prep_ref = (
                answers.preparation_ids[(row_idx - 1) % len(answers.preparation_ids)]
                if answers.preparation_ids
                else ""
            )
            rows.append(
                {
                    "sample_id": f"ROW{row_idx:04d}",
                    "source_id": source_ref,
                    "preparation_id": prep_ref,
                    "culture_id": "",
                    "plate_id": "",
                    "well_id": "",
                    "factor_level": level,
                    "batch_id": "",
                    "timepoint": "",
                    "endpoint_id": answers.endpoint_id,
                    "lifecycle_status": "planned",
                    "exclusion_reason": "",
                    "file_ref": "",
                }
            )
    sample_csv = build_sample_sheet(rows=tuple(rows))
    id_conv = build_id_convention(block_label=answers.block_label, factor_id=answers.factor_id)
    methods = build_methods_draft(
        source_description=answers.source_description,
        factor_id=answers.factor_id,
        levels=levels,
        endpoint_id=answers.endpoint_id,
        allocation_level=allocation_level,
        assignment_timing=answers.assignment_timing,
    )
    return QuickDesignResult(
        bootstrap=bootstrap,
        determinability=state,
        sample_sheet_csv=sample_csv,
        id_convention=id_conv,
        methods_draft=methods,
        primary_question=primary_q,
        plan_frozen=False,
        export_payload=None,
        user_confirmation_scopes=tuple(user_scopes),
    )
