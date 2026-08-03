"""Quick Design Session service for simple_cell_culture (PRD v7 §6.1).

Vertical slice: domain service + deterministic fixtures + report/export.
No large UI. Targets <10 min / <=3 questions are PROVISIONAL product hypotheses.
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


@dataclass(frozen=True)
class QuickDesignAnswers:
    """User-supplied answers for the minimal vertical slice.

    Unknowns stay UNKNOWN; the session never invents independence or interference.
    """

    source_description: str
    preparation_description: str = "unknown"
    unit_hierarchy: tuple[str, ...] = ("source", "culture", "well")
    factor_id: str = "treatment"
    levels: tuple[str, str] = ("control", "treated")
    endpoint_id: str = "viability"
    contrast_id: str = "control_vs_treated"
    allocation_level: str = "unknown"
    application_level: str | None = "unknown"
    assignment_timing: str = "unknown"  # before|after|same_event|unknown
    assignment_method: str = "unknown"
    biological_source_independence: str = "UNKNOWN"  # TRUE|FALSE|UNKNOWN
    interference_status: str = "UNKNOWN"  # maps to InterferenceStatus or UNKNOWN
    n_per_level: int | None = None
    primary_question: str = ""
    block_label: str = "qd_session"


@dataclass(frozen=True)
class QuickDesignResult:
    """Outcome of one Quick Design session (not a scientific validation)."""

    bootstrap: BootstrapCoreRecord
    determinability: DeterminabilityStateV7
    sample_sheet_csv: str
    id_convention: str
    methods_draft: str
    primary_question: str
    plan_frozen: bool = False
    export_payload: dict[str, object] | None = None


def _tri(value: str) -> TriState:
    try:
        return TriState(value.upper())
    except ValueError:
        return TriState.UNKNOWN


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
    try:
        return AssignmentLevel(value.lower())
    except ValueError:
        return AssignmentLevel.UNKNOWN


def run_quick_design_session(answers: QuickDesignAnswers) -> QuickDesignResult:
    """Build Bootstrap Core + artefacts for simple_cell_culture.

    Fail-closed: missing decisive assignment/interference facts produce
    INSUFFICIENT_INFORMATION and a primary decisive question.
    """
    if answers.unit_hierarchy != ("source", "culture", "well") and len(answers.unit_hierarchy) < 2:
        raise ValueError("unit_hierarchy requires at least two levels for simple_cell_culture")

    block_id = make_block_id("simple_cell_culture", answers.block_label)
    source_id = "U_source"
    prep_id = "U_prep"
    culture_id = "U_culture"
    well_id = "U_well"

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

    bio_ind = _tri(answers.biological_source_independence)
    interf = _interference(answers.interference_status)
    # no_known_path without evidence is rejected by the schema; keep UNKNOWN if silent
    interference_assessment = InterferenceAssessment(status=interf)
    if interf is InterferenceStatus.NO_KNOWN_PATH:
        # require explicit evidence path - vertical slice defaults fail-closed to UNKNOWN
        interference_assessment = InterferenceAssessment(status=InterferenceStatus.UNKNOWN)

    assignment = AssignmentMechanism(
        level=_assignment_level(answers.allocation_level),
        method=_assignment_method(answers.assignment_method),
        timing_relative_to_split=_split_timing(answers.assignment_timing),
        randomization_unit=answers.allocation_level
        if answers.allocation_level != "unknown"
        else None,
    )
    causal = CausalDesignContext(
        factor_id=answers.factor_id,
        assignment_mechanism=assignment,
        interference_assessment=interference_assessment,
    )

    independence = IndependenceProfile(
        independently_assigned=_tri(
            "TRUE"
            if answers.assignment_method not in ("unknown", "")
            and answers.allocation_level != "unknown"
            else "UNKNOWN"
        ),
        biological_source_independence=bio_ind,
        interference_status=interference_assessment.status,
        analytical_grouping=(),
        evidence_ids=(),
    )
    # if independently_assigned TRUE needs evidence - force UNKNOWN without evidence
    if independence.independently_assigned is TriState.TRUE:
        independence = IndependenceProfile(
            independently_assigned=TriState.UNKNOWN,
            biological_source_independence=bio_ind,
            interference_status=interference_assessment.status,
            analytical_grouping=(),
            evidence_ids=(),
        )

    counts: tuple[CountRecord, ...] = ()
    if answers.n_per_level is not None:
        cid = make_count_id(CountKind.DECLARED_N, f"{answers.factor_id}|{answers.endpoint_id}")
        counts = (
            CountRecord(
                id=cid,
                kind=CountKind.DECLARED_N,
                value=answers.n_per_level,
                unit_type="well",
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

    missing: MissingDecisiveFact | None = None
    primary_q = answers.primary_question.strip()
    allocation_known = answers.allocation_level != "unknown"
    independence_known = bio_ind is not TriState.UNKNOWN
    interference_unknown = interference_assessment.status is InterferenceStatus.UNKNOWN

    if not allocation_known or interference_unknown or not independence_known:
        if not allocation_known:
            pred = "allocation_level"
            primary_q = primary_q or (
                f"At which unit level was {answers.factor_id} allocated "
                f"(well, culture, plate, or other)?"
            )
        elif not independence_known:
            pred = "biological_source_independence"
            primary_q = primary_q or (
                "Are the biological sources independent across experimental groups?"
            )
        else:
            pred = "interference_assessment"
            primary_q = primary_q or (
                "Is there shared exposure or interference between experimental units?"
            )
        missing = MissingDecisiveFact(
            predicate=pred, rationale="required-or-UNKNOWN bootstrap field"
        )

    facts = V7GraphFacts(
        allocation_known=allocation_known,
        operational_independence_known=independence_known,
        contrast_defined=True,
        endpoint_defined=bool(answers.endpoint_id.strip()),
        counts_sufficient=answers.n_per_level is not None,
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
        allocation_level=answers.allocation_level,
        application_level=answers.application_level,
        independently_assigned="UNKNOWN",
        source_preparation_id=prep_id,
        independence=independence,
        causal_context=causal,
        counts=counts,
        missing_decisive_fact=missing,
        primary_question=primary_q,
        inferential_query=query,
        determinability_derived=state.value,
        determinability_reviewed=False,
    )

    # deterministic sample sheet: 2 levels x n (default 1 row each if n missing)
    n_rows = answers.n_per_level if answers.n_per_level is not None else 1
    rows: list[dict[str, str]] = []
    for level_idx, level in enumerate(levels, start=1):
        for i in range(1, n_rows + 1):
            rows.append(
                {
                    "sample_id": f"S{level_idx:02d}_{i:03d}",
                    "source_id": f"SRC{i:03d}",
                    "preparation_id": f"P{i:03d}",
                    "culture_id": f"C{i:03d}",
                    "plate_id": "PL01",
                    "well_id": f"PL01_W{level_idx}{i:02d}",
                    "factor_level": level,
                    "batch_id": "B01",
                    "timepoint": "t0",
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
        allocation_level=answers.allocation_level,
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
    )
