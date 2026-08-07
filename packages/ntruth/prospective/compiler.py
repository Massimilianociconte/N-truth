"""Compiler prospettico D0: input umano -> blocco canonico verificato.

Il modulo non esegue power analysis e non seleziona test o formule. I dati del
sample sheet dimostrano associazioni e provenance; un ``independent_n`` viene
pubblicato soltanto dopo una conferma operativa esplicita dell'indipendenza.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Iterable
from typing import Literal

from pydantic import ValidationError

from ntruth import GRAPH_VERSION, ONTOLOGY_VERSION, PARSER_VERSION, SCHEMA_VERSION
from ntruth.capabilities import CapabilityStatus, assess_core_profile_capability
from ntruth.design import compile_experiment_block, finalize_experiment_block_compilation
from ntruth.graph.builder import BuildResult
from ntruth.graph.determinability import derive_determinability
from ntruth.rules import (
    DEFAULT_RULESET_ID,
    DEFAULT_RULESET_VERSION,
    RulesetNotFound,
    apply_rules,
    load_ruleset,
)
from ntruth.sample_sheet.schema import (
    OPTIONAL_HEADERS,
    REQUIRED_HEADERS,
    SampleLifecycleStatus,
    SampleSheetRow,
    SampleSheetSpec,
    normalize_factor_column,
)
from ntruth.schemas.core import (
    Confidence,
    Determinability,
    EvidenceSpan,
    EvidenceType,
    Provenance,
    ProvenanceKind,
    content_checksum,
    stable_id,
)
from ntruth.schemas.experiment import (
    ConditionalScenario,
    Contradiction,
    Contrast,
    CountKind,
    CountQuantifier,
    CountRecord,
    CountScope,
    DataSufficiency,
    Endpoint,
    Estimand,
    ExclusionPhase,
    ExclusionRecord,
    ExperimentBlock,
    Factor,
    GraphStatus,
    Hierarchy,
    Inferability,
    InferenceTarget,
    InferenceTargetStatus,
    LifecycleStatus,
    NScope,
    ProcessFact,
    Question,
    RiskLabel,
    TriState,
    UnitAssessment,
    Versions,
)
from ntruth.schemas.graph import (
    GraphNode,
    GraphRelation,
    NodeType,
    RelationType,
    make_node_id,
    make_relation_id,
)
from ntruth.schemas.rules import RuleEvaluation
from ntruth.verifier import (
    apply_output_policy,
    apply_rule_evaluation_output_policy,
    verify_block,
)

from .schema import (
    PROSPECTIVE_D0_CONTRACT_VERSION,
    ProspectiveCapabilityResult,
    ProspectiveD0Compilation,
    ProspectiveD0CompileRequest,
    ProspectiveD0Draft,
    ProspectiveD0Issue,
    ProspectiveD0Row,
    ProspectiveD0RulesetError,
    ProspectiveD0ValidationError,
    ProspectiveIssueSeverity,
)

_PHASE_BY_TOKEN = {
    "pre-allocation": ExclusionPhase.PRE_ALLOCATION,
    "pre_allocation": ExclusionPhase.PRE_ALLOCATION,
    "post-allocation": ExclusionPhase.POST_ALLOCATION,
    "post_allocation": ExclusionPhase.POST_ALLOCATION,
    "post-treatment": ExclusionPhase.POST_TREATMENT,
    "post_treatment": ExclusionPhase.POST_TREATMENT,
    "post-measurement": ExclusionPhase.POST_MEASUREMENT,
    "post_measurement": ExclusionPhase.POST_MEASUREMENT,
    "post-outcome": ExclusionPhase.POST_OUTCOME,
    "post_outcome": ExclusionPhase.POST_OUTCOME,
}
_PHASE_RE = re.compile(
    r"\b(?:pre[-_]allocation|post[-_](?:allocation|treatment|measurement|outcome))\b",
    re.IGNORECASE,
)
_AUTHOR_RE = re.compile(r"\b(?:autore|author)\s*:\s*([^|;]+)", re.IGNORECASE)
_FACTOR_SLUG_RE = re.compile(r"[^a-z0-9_.-]+")
_EXCLUSION_EXTENSION_HEADERS = (
    "ntruth_exclusion_phase",
    "ntruth_exclusion_prespecified",
    "ntruth_exclusion_author_role",
    "ntruth_exclusion_impact",
)
_D0_ALLOCATION_UNITS = frozenset(
    {NodeType.PRIMARY_CULTURE, NodeType.CELL_CULTURE, NodeType.PLATE, NodeType.WELL}
)
_D0_ROW_ADDRESSABLE_UNITS = _D0_ALLOCATION_UNITS
_D0_UNIT_DEPTH = {
    NodeType.PRIMARY_CULTURE: 0,
    NodeType.CELL_CULTURE: 1,
    NodeType.PLATE: 2,
    NodeType.WELL: 3,
    NodeType.CELL: 4,
}
_CONFOUNDING_NODE_TYPES = {
    "source_id": NodeType.BIOLOGICAL_SOURCE,
    "preparation_id": NodeType.PRIMARY_CULTURE,
    "culture_id": NodeType.CELL_CULTURE,
    "plate_id": NodeType.PLATE,
    "batch_id": NodeType.BATCH,
    "day_id": NodeType.BATCH,
    "operator_id": NodeType.UNIT_INSTANCE,
    "incubator_id": NodeType.INSTRUMENT,
}

_LIFECYCLE_KINDS: tuple[tuple[CountKind, LifecycleStatus], ...] = (
    (CountKind.PLANNED_N, LifecycleStatus.PLANNED),
    (CountKind.ALLOCATED_N, LifecycleStatus.ALLOCATED),
    (CountKind.TREATED_N, LifecycleStatus.TREATED),
    (CountKind.OBSERVED_N, LifecycleStatus.OBSERVED),
    (CountKind.EXCLUDED_N, LifecycleStatus.EXCLUDED),
    (CountKind.ANALYSED_N, LifecycleStatus.ANALYSED),
)


def compile_prospective_d0(request: ProspectiveD0CompileRequest) -> ProspectiveD0Compilation:
    """Compila e verifica un draft D0 senza mutare input o scrivere su disco."""

    if (
        request.ruleset_id != DEFAULT_RULESET_ID
        or request.ruleset_version != DEFAULT_RULESET_VERSION
    ):
        raise ProspectiveD0RulesetError(
            "prospective_ruleset_not_allowed",
            (
                "Il compiler D0 accetta soltanto il ruleset canonico "
                f"{DEFAULT_RULESET_ID}@{DEFAULT_RULESET_VERSION}."
            ),
        )
    try:
        ruleset = load_ruleset(DEFAULT_RULESET_ID, DEFAULT_RULESET_VERSION)
    except (RulesetNotFound, OSError, json.JSONDecodeError, ValidationError) as exc:
        raise ProspectiveD0RulesetError(
            "prospective_ruleset_unavailable",
            "Il ruleset canonico D0 locale non e disponibile o non supera la validazione.",
        ) from exc
    factor_column = normalize_factor_column(
        f"factor_level_{_factor_slug(request.draft.factor_name)}"
    )
    sample_sheet, issues = _build_sample_sheet(request, factor_column)
    issues = [*issues, *_cross_row_issues(request, sample_sheet, factor_column)]
    errors = tuple(issue for issue in issues if issue.severity is ProspectiveIssueSeverity.ERROR)
    if errors:
        raise ProspectiveD0ValidationError(errors)

    block = _build_block(request, sample_sheet, factor_column)
    build = _as_build_result(block)
    preflight = verify_block(block, check_output_policy=False)
    evaluations: tuple[RuleEvaluation, ...] = ()
    if preflight.violations:
        block = block.model_copy(
            update={
                "graph_status": GraphStatus.INVALID,
                "determinability": Determinability.INVALID_GRAPH,
            }
        )
    else:
        rule_run = apply_rules(
            block.id,
            build,
            block.unit_assessments,
            ruleset,
            lang=request.language,
            evidence_by_id={item.id: item for item in block.evidence},
        )
        evaluations = rule_run.evaluations
        existing_questions = {item.id: item for item in block.questions}
        for question in rule_run.questions:
            existing_questions.setdefault(question.id, question)
        block = block.model_copy(
            update={
                "alerts": rule_run.alerts,
                "questions": tuple(existing_questions.values()),
                "unit_assessments": rule_run.assessments,
            }
        )
        issues.extend(_warning("rule_unevaluable", warning) for warning in rule_run.warnings)

    capability_decision = assess_core_profile_capability(block)
    preliminary_compilation = compile_experiment_block(block)
    if block.graph_status is not GraphStatus.INVALID:
        determinability = derive_determinability(
            block,
            preliminary_compilation,
            supported_profile=capability_decision.supported,
        )
        if capability_decision.status is CapabilityStatus.INCOMPLETE:
            determinability = Determinability.INSUFFICIENT_INFORMATION
        block = block.model_copy(update={"determinability": determinability})
    block = apply_output_policy(block)
    verification = verify_block(block)
    if verification.violations and block.determinability is not Determinability.INVALID_GRAPH:
        # Un errore tardivo non puo lasciare un output apparentemente determinato.
        block = apply_output_policy(
            block.model_copy(
                update={
                    "graph_status": GraphStatus.INVALID,
                    "determinability": Determinability.INVALID_GRAPH,
                }
            )
        )
        verification = verify_block(block)

    capability = ProspectiveCapabilityResult(
        profile_id=capability_decision.profile_id,
        profile_version=capability_decision.profile_version,
        profile_reference=capability_decision.profile_reference,
        status=capability_decision.status,
        supported=capability_decision.supported,
        reason_codes=capability_decision.reason_codes,
        details=capability_decision.details,
    )
    compilation = finalize_experiment_block_compilation(
        block,
        supported_profile=capability_decision.supported,
        verification_valid=not verification.violations,
    )
    payload_for_id = {
        "contract_version": PROSPECTIVE_D0_CONTRACT_VERSION,
        "block": block.model_dump(mode="json"),
        "sample_sheet": sample_sheet.model_dump(mode="json"),
        "capability": capability.model_dump(mode="json"),
        "ruleset_checksum": ruleset.checksum(),
    }
    ready = (
        block.determinability is Determinability.DETERMINATE
        and capability_decision.supported is True
        and not compilation.abstained
        and not verification.violations
    )
    return ProspectiveD0Compilation(
        compilation_id=stable_id("d0c", content_checksum(payload_for_id)),
        ruleset_checksum=ruleset.checksum(),
        sample_sheet=sample_sheet,
        block=block,
        capability=capability,
        design_compilation=compilation,
        verification=verification,
        rule_evaluations=apply_rule_evaluation_output_policy(block, evaluations),
        issues=tuple(issues),
        determinability=block.determinability,
        ready_for_handoff=ready,
    )


def _build_sample_sheet(
    request: ProspectiveD0CompileRequest,
    factor_column: str,
) -> tuple[SampleSheetSpec, list[ProspectiveD0Issue]]:
    issues: list[ProspectiveD0Issue] = []
    canonical_rows: list[SampleSheetRow] = []
    for index, row in enumerate(request.rows, start=2):
        try:
            factor_levels = _row_factor_levels(row, factor_column)
            canonical_rows.append(
                SampleSheetRow(
                    sample_id=row.sample_id,
                    source_id=row.source_id,
                    preparation_id=row.preparation_id,
                    culture_id=row.culture_id,
                    plate_id=row.plate_id,
                    well_id=row.well_id,
                    factor_levels=factor_levels,
                    batch_id=row.batch_id,
                    timepoint=row.timepoint,
                    endpoint_id=row.endpoint_id,
                    lifecycle_status=row.lifecycle_status,
                    exclusion_reason=row.exclusion_reason,
                    file_ref=row.file_ref,
                    extra_fields=_canonical_extra_fields(row),
                )
            )
        except (ValueError, ValidationError) as exc:
            issues.append(
                _error(
                    "invalid_sample_sheet_row",
                    f"riga {index}: {exc}",
                    row=index,
                )
            )

    if any(item.severity is ProspectiveIssueSeverity.ERROR for item in issues):
        raise ProspectiveD0ValidationError(tuple(issues))

    extra_headers = tuple(sorted({key for row in canonical_rows for key in row.extra_fields}))
    headers = (
        *REQUIRED_HEADERS,
        "culture_id",
        "plate_id",
        "well_id",
        factor_column,
        *(item for item in OPTIONAL_HEADERS if item not in {"culture_id", "plate_id", "well_id"}),
        *extra_headers,
    )
    try:
        spec = SampleSheetSpec(
            headers=headers,
            factor_columns=(factor_column,),
            rows=tuple(canonical_rows),
            source_name="prospective-d0.json",
            content_sha256=content_checksum(
                [row.model_dump(mode="json") for row in canonical_rows]
            ),
        )
    except ValidationError as exc:
        raise ProspectiveD0ValidationError((_error("invalid_sample_sheet", str(exc)),)) from exc
    return spec, issues


def _cross_row_issues(
    request: ProspectiveD0CompileRequest,
    sample_sheet: SampleSheetSpec,
    factor_column: str,
) -> list[ProspectiveD0Issue]:
    draft = request.draft
    issues: list[ProspectiveD0Issue] = []
    levels = {draft.level_a, draft.level_b}
    allocation_level = _known_level(draft.allocation_level)
    application_level = _known_level(draft.application_level)
    measurement_level = _known_level(draft.measured_on)
    target_level = draft.target_biological_unit
    allocation_groups: dict[str, set[str]] = defaultdict(set)
    application_groups: dict[str, set[str]] = defaultdict(set)
    well_rows: dict[str, int] = {}
    physical_rows: dict[tuple[str, str, str, str | None], int] = {}
    preparation_origins: dict[str, set[str | None]] = defaultdict(set)
    culture_origins: dict[str, set[tuple[str | None, str | None]]] = defaultdict(set)
    plate_origins: dict[str, set[tuple[str | None, str | None]]] = defaultdict(set)

    if not sample_sheet.rows:
        issues.append(
            _warning(
                "empty_sample_sheet",
                "nessuna riga: i count restano NOT_REPORTED e il compiler si astiene",
            )
        )
    if draft.target_biological_unit is None:
        issues.append(
            _warning(
                "missing_target_biological_unit",
                "target_biological_unit non dichiarata: l'handoff resta incompleto",
                field="draft.target_biological_unit",
            )
        )
    if draft.estimand is None:
        issues.append(
            _warning(
                "missing_estimand",
                "estimand minimo non dichiarato: il compiler non lo sintetizza",
                field="draft.estimand",
            )
        )
    if allocation_level is None:
        issues.append(
            _warning(
                "unknown_allocation_level",
                "allocation_level UNKNOWN: nessun n indipendente viene derivato",
                field="draft.allocation_level",
            )
        )
    if (
        allocation_level in _D0_UNIT_DEPTH
        and application_level in _D0_UNIT_DEPTH
        and _D0_UNIT_DEPTH[allocation_level] > _D0_UNIT_DEPTH[application_level]
    ):
        issues.append(
            _error(
                "allocation_level_finer_than_application_level",
                (
                    f"allocation_level={allocation_level.value} e piu fine di "
                    f"application_level={application_level.value}; il D0 non puo trattare "
                    "le unita allocate come esposizioni indipendenti"
                ),
                field="draft.application_level",
            )
        )

    reported_timepoints = {
        _normalized_timepoint(row.timepoint)
        for row in sample_sheet.rows
        if row.timepoint is not None
    }
    missing_timepoint_rows = tuple(
        index for index, row in enumerate(sample_sheet.rows, start=2) if row.timepoint is None
    )
    if reported_timepoints and missing_timepoint_rows:
        for index in missing_timepoint_rows:
            issues.append(
                _error(
                    "mixed_reported_and_missing_timepoint",
                    (
                        f"riga {index}: timepoint mancante mentre altre righe del "
                        "blocco D0 lo dichiarano"
                    ),
                    row=index,
                    field="timepoint",
                )
            )
    estimand_timepoint = (
        _normalized_timepoint(draft.estimand.timepoint)
        if draft.estimand is not None and draft.estimand.timepoint is not None
        else None
    )
    if estimand_timepoint is not None and sample_sheet.rows:
        if not reported_timepoints:
            issues.append(
                _error(
                    "missing_row_timepoint_for_estimand",
                    (
                        "estimand.timepoint e dichiarato ma nessuna riga D0 ha un "
                        "timepoint esplicito; il compiler non lo propaga implicitamente"
                    ),
                    field="timepoint",
                )
            )
        elif len(reported_timepoints) == 1 and estimand_timepoint not in reported_timepoints:
            issues.append(
                _error(
                    "row_estimand_timepoint_mismatch",
                    ("l'unico timepoint delle righe non coincide con estimand.timepoint"),
                    field="timepoint",
                )
            )

    uses_cell_population = NodeType.CELL in {
        application_level,
        measurement_level,
        target_level,
    }

    for index, (source_row, row) in enumerate(
        zip(request.rows, sample_sheet.rows, strict=True), start=2
    ):
        level = row.factor_levels[factor_column]
        if uses_cell_population and not (row.plate_id and row.well_id):
            issues.append(
                _error(
                    "missing_cell_population_parent",
                    (
                        f"riga {index}: il piano Cell richiede plate_id e well_id "
                        "per materializzare la popolazione senza inventare istanze"
                    ),
                    row=index,
                    field="cell_population_plan",
                )
            )
        if row.preparation_id:
            preparation_origins[row.preparation_id].add(row.source_id)
        if row.culture_id:
            culture_origins[row.culture_id].add((row.preparation_id, row.source_id))
        if row.plate_id:
            plate_origins[row.plate_id].add((row.culture_id, row.preparation_id))
        if row.plate_id and row.well_id and row.endpoint_id:
            physical_key = (row.plate_id, row.well_id, row.endpoint_id, row.timepoint)
            previous_physical = physical_rows.get(physical_key)
            if previous_physical is not None:
                issues.append(
                    _error(
                        "duplicate_physical_well_row",
                        (
                            f"righe {previous_physical} e {index}: stessa coordinata fisica, "
                            "endpoint e timepoint nel D0"
                        ),
                        row=index,
                        field="well_id",
                    )
                )
            physical_rows[physical_key] = index
        if level not in levels:
            issues.append(
                _error(
                    "factor_level_outside_primary_contrast",
                    f"riga {index}: factor level '{level}' fuori dai due livelli dichiarati",
                    row=index,
                    field=factor_column,
                )
            )
        if row.endpoint_id is None:
            issues.append(
                _error(
                    "missing_row_endpoint",
                    f"riga {index}: endpoint_id richiesto dal compiler prospettico D0",
                    row=index,
                    field="endpoint_id",
                )
            )
        elif row.endpoint_id != draft.endpoint_id:
            issues.append(
                _error(
                    "row_endpoint_mismatch",
                    f"riga {index}: endpoint_id non coincide con l'endpoint primario",
                    row=index,
                    field="endpoint_id",
                )
            )
        if row.source_id is None:
            issues.append(
                _warning(
                    "source_id_not_reported",
                    f"riga {index}: source_id nullo; non viene inventato un identificatore",
                    row=index,
                    field="source_id",
                )
            )
        if row.preparation_id is None:
            issues.append(
                _warning(
                    "preparation_id_not_reported",
                    f"riga {index}: preparation_id nullo; non viene inventato un identificatore",
                    row=index,
                    field="preparation_id",
                )
            )
        if row.culture_id is None:
            issues.append(
                _warning(
                    "culture_id_not_reported",
                    f"riga {index}: culture_id nullo; non viene propagato da altre righe",
                    row=index,
                    field="culture_id",
                )
            )

        allocation_key = (
            _allocation_key(row, allocation_level)
            if allocation_level in _D0_ALLOCATION_UNITS
            else None
        )
        if allocation_level in _D0_ALLOCATION_UNITS and allocation_key is None:
            issues.append(
                _error(
                    "missing_allocation_unit_identifier",
                    (
                        f"riga {index}: identificatore mancante per allocation_level="
                        f"{allocation_level.value}"
                    ),
                    row=index,
                    field="allocation_level",
                )
            )
        elif allocation_key is not None:
            allocation_groups[allocation_key].add(level)

        application_key = (
            _allocation_key(row, application_level)
            if application_level in _D0_ROW_ADDRESSABLE_UNITS
            else None
        )
        if application_key is not None:
            application_groups[application_key].add(level)

        for unit_role, unit_level, field_name in (
            ("application", application_level, "application_level"),
            ("measurement", measurement_level, "measured_on"),
            ("target", target_level, "target_biological_unit"),
        ):
            if unit_level in _D0_ROW_ADDRESSABLE_UNITS and _allocation_key(row, unit_level) is None:
                issues.append(
                    _error(
                        f"missing_{unit_role}_unit_identifier",
                        (
                            f"riga {index}: identificatore mancante per "
                            f"{field_name}={unit_level.value}"
                        ),
                        row=index,
                        field=field_name,
                    )
                )

        if allocation_level is NodeType.WELL and allocation_key is not None:
            previous = well_rows.get(allocation_key)
            if previous is not None:
                issues.append(
                    _error(
                        "duplicate_well_allocation_unit",
                        (
                            f"righe {previous} e {index}: la stessa unita Well compare due volte; "
                            "il D0 a endpoint singolo non la conta due volte"
                        ),
                        row=index,
                        field="well_id",
                    )
                )
            well_rows[allocation_key] = index

        if row.lifecycle_status is SampleLifecycleStatus.EXCLUDED:
            if _physical_row_identity(row) is None:
                issues.append(
                    _error(
                        "missing_exclusion_unit_identifier",
                        f"riga {index}: esclusione senza unita fisica identificabile",
                        row=index,
                        field="sample_id",
                    )
                )
            _, _, criterion = _exclusion_metadata(row)
            if not criterion:
                issues.append(
                    _error(
                        "missing_exclusion_criterion",
                        f"riga {index}: exclusion_reason deve includere un criterio verificabile",
                        row=index,
                        field="exclusion_reason",
                    )
                )
            phase, author_role, _ = _exclusion_metadata(row)
            embedded_phase, embedded_author_role = _embedded_exclusion_metadata(row)
            dedicated_phase = row.extra_fields.get("ntruth_exclusion_phase")
            if (
                dedicated_phase
                and dedicated_phase != ExclusionPhase.UNKNOWN.value
                and embedded_phase is not None
                and ExclusionPhase(dedicated_phase) is not embedded_phase
            ):
                issues.append(
                    _error(
                        "conflicting_exclusion_phase",
                        (
                            f"riga {index}: exclusion_phase strutturata e fase nel "
                            "reason sono discordanti"
                        ),
                        row=index,
                        field="exclusion_phase",
                    )
                )
            dedicated_author_role = row.extra_fields.get("ntruth_exclusion_author_role")
            if (
                dedicated_author_role
                and embedded_author_role
                and dedicated_author_role.casefold() != embedded_author_role.casefold()
            ):
                issues.append(
                    _error(
                        "conflicting_exclusion_author_role",
                        (
                            f"riga {index}: exclusion_author_role strutturato e ruolo "
                            "nel reason sono discordanti"
                        ),
                        row=index,
                        field="exclusion_author_role",
                    )
                )
            if phase is None or phase is ExclusionPhase.UNKNOWN:
                issues.append(
                    _error(
                        "missing_exclusion_phase",
                        f"riga {index}: esclusione senza fase canonica",
                        row=index,
                        field="exclusion_phase",
                    )
                )
            if not author_role:
                issues.append(
                    _error(
                        "missing_exclusion_author_role",
                        f"riga {index}: esclusione senza ruolo autore",
                        row=index,
                        field="exclusion_author_role",
                    )
                )
        elif any(
            (
                source_row.exclusion_reason,
                source_row.exclusion_phase,
                source_row.exclusion_author_role,
                source_row.exclusion_impact,
            )
        ):
            issues.append(
                _error(
                    "exclusion_fields_without_excluded_status",
                    f"riga {index}: metadata di esclusione su lifecycle_status non excluded",
                    row=index,
                    field="lifecycle_status",
                )
            )

    for key, assigned_levels in sorted(allocation_groups.items()):
        if len(assigned_levels) > 1:
            issues.append(
                _error(
                    "allocation_unit_assigned_to_multiple_levels",
                    (
                        f"unita di allocazione '{key}' associata a piu livelli: "
                        f"{sorted(assigned_levels)}"
                    ),
                )
            )
    for key, assigned_levels in sorted(application_groups.items()):
        if len(assigned_levels) > 1:
            issues.append(
                _error(
                    "application_unit_assigned_to_multiple_levels",
                    (
                        f"unita di applicazione '{key}' associata a piu livelli: "
                        f"{sorted(assigned_levels)}"
                    ),
                    field="application_level",
                )
            )
    for preparation_id, preparation_sources in sorted(preparation_origins.items()):
        known_sources = {item for item in preparation_sources if item is not None}
        if len(known_sources) > 1:
            issues.append(
                _error(
                    "preparation_origin_not_functional",
                    (
                        f"preparation_id '{preparation_id}' riferisce piu source_id: "
                        f"{sorted(known_sources)}"
                    ),
                    field="preparation_id",
                )
            )
    for culture_id, culture_sources in sorted(culture_origins.items()):
        known_preparations = {
            preparation_id for preparation_id, _ in culture_sources if preparation_id is not None
        }
        known_sources = {source_id for _, source_id in culture_sources if source_id is not None}
        if len(known_preparations) > 1 or len(known_sources) > 1:
            issues.append(
                _error(
                    "culture_origin_not_functional",
                    f"culture_id '{culture_id}' riferisce piu preparation/source: "
                    f"preparations={sorted(known_preparations)}, "
                    f"sources={sorted(known_sources)}",
                    field="culture_id",
                )
            )
    for plate_id, plate_sources in sorted(plate_origins.items()):
        known_cultures = {culture_id for culture_id, _ in plate_sources if culture_id is not None}
        known_preparations = {
            preparation_id for _, preparation_id in plate_sources if preparation_id is not None
        }
        if len(known_cultures) > 1 or len(known_preparations) > 1:
            issues.append(
                _error(
                    "plate_origin_not_functional",
                    f"plate_id '{plate_id}' riferisce piu culture/preparation: "
                    f"cultures={sorted(known_cultures)}, "
                    f"preparations={sorted(known_preparations)}",
                    field="plate_id",
                )
            )
    represented = {
        row.factor_levels[factor_column]
        for row in sample_sheet.rows
        if row.factor_levels[factor_column] in levels
    }
    for missing_level in sorted(levels - represented):
        issues.append(
            _warning(
                "factor_level_without_rows",
                f"nessuna riga per il livello '{missing_level}': i count restano NOT_REPORTED",
                field=factor_column,
            )
        )
    return issues


def _build_block(
    request: ProspectiveD0CompileRequest,
    sample_sheet: SampleSheetSpec,
    factor_column: str,
) -> ExperimentBlock:
    draft = request.draft
    block_id = draft.experiment_block_id
    document_id = stable_id("doc", "prospective-d0", block_id)
    wizard_file_id = stable_id("src", block_id, "wizard")
    sheet_file_id = stable_id("src", block_id, sample_sheet.content_sha256)
    factor_id = stable_id("fct", block_id, draft.factor_name)
    contrast_id = stable_id(
        "ctr", block_id, factor_id, draft.level_a, draft.level_b, draft.endpoint_id
    )
    target_id = stable_id("itr", block_id, draft.question_text, draft.population_of_inference)
    estimand_id = stable_id("est", block_id, target_id, draft.endpoint_id)

    draft_evidence = _draft_evidence(
        draft,
        block_id=block_id,
        file_id=wizard_file_id,
        factor_id=factor_id,
    )
    row_evidence = tuple(
        _row_evidence(row, index=index, block_id=block_id, file_id=sheet_file_id)
        for index, row in enumerate(sample_sheet.rows, start=2)
    )
    evidence = (*draft_evidence, *row_evidence)
    evidence_by_section = {item.section_id: item.id for item in draft_evidence}
    row_evidence_ids = tuple(item.id for item in row_evidence)
    confounding_dimensions = _perfect_confounding_dimensions(
        request,
        sample_sheet,
        factor_column=factor_column,
    )
    confounding_evidence_ids = row_evidence_ids if confounding_dimensions else ()

    factor_evidence_ids = _merge_evidence_ids(
        (
            evidence_by_section["factor"],
            evidence_by_section["allocation"],
            evidence_by_section["application"],
            evidence_by_section["independence"],
            evidence_by_section["environment"],
        ),
        confounding_evidence_ids,
    )
    factor_provenance = (
        Provenance(
            origin=ProvenanceKind.DERIVED,
            evidence_ids=factor_evidence_ids,
            rule_id="D0-PROSPECTIVE-CONFOUNDING",
            ruleset_version=DEFAULT_RULESET_VERSION,
            actor_role=draft.reviewer_role,
            derivation=(
                "campi del wizard combinati con la coincidenza perfetta visibile nel sample sheet"
            ),
        )
        if confounding_dimensions
        else Provenance(
            origin=ProvenanceKind.USER,
            evidence_ids=factor_evidence_ids,
            actor_role=draft.reviewer_role,
            derivation="campi dichiarati nel wizard prospettico D0",
        )
    )
    allocation_level = _known_level(draft.allocation_level)
    application_level = _known_level(draft.application_level)
    measured_on = _known_level(draft.measured_on)
    factor = Factor(
        id=factor_id,
        name=draft.factor_name,
        kind=draft.factor_kind,
        levels=(draft.level_a, draft.level_b),
        allocation_level=allocation_level,
        application_level=application_level,
        allocation_confidence=1.0 if allocation_level is not None else 0.0,
        application_confidence=1.0 if application_level is not None else 0.0,
        allocation_evidence_ids=(evidence_by_section["allocation"],),
        application_evidence_ids=(evidence_by_section["application"],),
        independence_evidence_ids=(evidence_by_section["independence"],),
        independently_assigned=draft.independently_assigned,
        independence_mechanism=draft.independence_mechanism,
        shared_environment=draft.shared_environment,
        confounded_with=confounding_dimensions,
        evidence_ids=factor_evidence_ids,
        provenance=factor_provenance,
    )
    contrast_evidence = (evidence_by_section["factor"],)
    contrast = Contrast(
        id=contrast_id,
        label=f"{draft.level_a} vs {draft.level_b}",
        factor_ids=(factor_id,),
        compared_levels=(draft.level_a, draft.level_b),
        endpoint_ids=(draft.endpoint_id,),
        evidence_ids=contrast_evidence,
        provenance=Provenance(
            origin=ProvenanceKind.USER,
            evidence_ids=contrast_evidence,
            actor_role=draft.reviewer_role,
        ),
    )
    endpoint_evidence = (evidence_by_section["endpoint"],)
    endpoint = Endpoint(
        id=draft.endpoint_id,
        name=draft.endpoint_name,
        measured_on=measured_on,
        timepoints=tuple(
            dict.fromkeys(row.timepoint for row in sample_sheet.rows if row.timepoint)
        ),
        evidence_ids=endpoint_evidence,
        provenance=Provenance(
            origin=ProvenanceKind.USER,
            evidence_ids=endpoint_evidence,
            actor_role=draft.reviewer_role,
        ),
    )
    target_evidence = (evidence_by_section["target"],)
    target = InferenceTarget(
        id=target_id,
        question_text=draft.question_text,
        population_of_inference=draft.population_of_inference,
        factor_ids=(factor_id,),
        contrast_ids=(contrast_id,),
        endpoint_ids=(draft.endpoint_id,),
        target_biological_unit=draft.target_biological_unit,
        evidence_ids=target_evidence,
        provenance=Provenance(
            origin=ProvenanceKind.USER,
            evidence_ids=target_evidence,
            actor_role=draft.reviewer_role,
        ),
        status=InferenceTargetStatus.USER_CONFIRMED,
    )
    estimands: tuple[Estimand, ...] = ()
    if draft.estimand is not None:
        estimand_evidence = (evidence_by_section["estimand"],)
        estimands = (
            Estimand(
                id=estimand_id,
                endpoint_id=draft.endpoint_id,
                effect_measure=draft.estimand.effect_measure,
                target_population_or_unit=draft.estimand.target_population_or_unit,
                generalization_level=draft.estimand.generalization_level,
                factor_ids=(factor_id,),
                timepoint=draft.estimand.timepoint,
                condition=draft.estimand.condition,
                evidence_ids=estimand_evidence,
                provenance=Provenance(
                    origin=ProvenanceKind.USER,
                    evidence_ids=estimand_evidence,
                    actor_role=draft.reviewer_role,
                ),
            ),
        )

    decisive_evidence_ids = tuple(
        evidence_by_section[section]
        for section in (
            "factor",
            "allocation",
            "application",
            "independence",
            "environment",
            "endpoint",
            "target",
            "estimand",
            "cell_plan",
        )
    )

    counts = _count_records(
        request,
        sample_sheet,
        factor_column=factor_column,
        factor_id=factor_id,
        contrast_id=contrast_id,
        row_evidence_ids=row_evidence_ids,
        design_evidence_ids=decisive_evidence_ids,
    )
    exclusions = _exclusion_records(
        request,
        sample_sheet,
        factor_column=factor_column,
        factor_id=factor_id,
        contrast_id=contrast_id,
        block_id=block_id,
        row_evidence_ids=row_evidence_ids,
    )
    assessments = _unit_assessments(
        request,
        sample_sheet,
        factor_column=factor_column,
        factor_id=factor_id,
        contrast_id=contrast_id,
        target_id=target_id,
        row_evidence_ids=row_evidence_ids,
        design_evidence_ids=decisive_evidence_ids,
        has_perfect_confounding=bool(confounding_dimensions),
    )
    conditional_questions: tuple[Question, ...] = ()
    if any(item.conditional_scenarios for item in assessments):
        conditional_questions = (
            Question(
                id=stable_id("q", block_id, factor_id, "independently-assigned"),
                text=(
                    "Le unita al livello di allocazione sono state assegnate "
                    "indipendentemente mediante un meccanismo operativo documentato?"
                ),
                reason=(
                    "La risposta distingue il ramo che consente di identificare "
                    "unita sperimentale e n indipendente dal ramo che li lascia non determinati."
                ),
                missing_field=f"factors.{factor_id}.independently_assigned",
                priority=100,
                decisive=True,
                impact="experimental_unit_and_independent_n",
            ),
        )
    confounding_processes = tuple(
        ProcessFact(
            id=stable_id("prc", block_id, "perfect-confounding", dimension),
            kind="confounding",
            detail=(
                f"I due livelli del fattore coincidono uno-a-uno con {dimension}; "
                "l'effetto del fattore non e separabile senza replica entro cluster."
            ),
            node_type=_CONFOUNDING_NODE_TYPES[dimension],
            evidence_ids=confounding_evidence_ids,
            provenance=Provenance(
                origin=ProvenanceKind.DERIVED,
                evidence_ids=confounding_evidence_ids,
                rule_id="D0-PROSPECTIVE-CONFOUNDING",
                ruleset_version=DEFAULT_RULESET_VERSION,
                derivation="test funzionale one-cluster-per-factor-level sul sample sheet",
            ),
        )
        for dimension in confounding_dimensions
    )
    contradictions: tuple[Contradiction, ...] = ()
    if confounding_dimensions and draft.independently_assigned is TriState.TRUE:
        conflict_evidence = _merge_evidence_ids(
            (evidence_by_section["independence"],),
            confounding_evidence_ids,
        )
        dimensions = ", ".join(confounding_dimensions)
        contradictions = (
            Contradiction(
                id=stable_id("con", block_id, "perfect-confounding", dimensions),
                description=(
                    "L'indipendenza dichiarata e in conflitto con la coincidenza "
                    f"perfetta del fattore rispetto a: {dimensions}."
                ),
                evidence_ids=conflict_evidence,
                retained_interpretations=(
                    "il meccanismo dichiarato rende le unita indipendenti nonostante la coincidenza",
                    "fattore e cluster osservato non sono separabili nei dati pianificati",
                ),
                provenance=Provenance(
                    origin=ProvenanceKind.DERIVED,
                    evidence_ids=conflict_evidence,
                    rule_id="D0-PROSPECTIVE-CONFOUNDING",
                    ruleset_version=DEFAULT_RULESET_VERSION,
                    derivation=("confronto tra conferma di indipendenza e mapping cluster-livello"),
                ),
            ),
        )
    hierarchy = _hierarchy(
        request,
        sample_sheet,
        block_id=block_id,
        factor=factor,
        contrast=contrast,
        endpoint=endpoint,
        target=target,
        estimands=estimands,
        row_evidence_ids=row_evidence_ids,
        design_evidence_ids=tuple(item.id for item in draft_evidence),
    )
    n_statements = tuple(
        statement for count in counts if (statement := count.to_legacy()) is not None
    )
    return ExperimentBlock(
        id=block_id,
        title=draft.title,
        document_id=document_id,
        source_file_ids=(wizard_file_id, sheet_file_id),
        inference_targets=(target,),
        factors=(factor,),
        contrasts=(contrast,),
        endpoints=(endpoint,),
        estimands=estimands,
        processes=confounding_processes,
        graph_status=GraphStatus.HUMAN_CONFIRMED,
        hierarchy=hierarchy,
        n_statements=n_statements,
        count_records=counts,
        exclusion_records=exclusions,
        unit_assessments=assessments,
        questions=conditional_questions,
        contradictions=contradictions,
        data_sufficiency=DataSufficiency(
            intervention_level=(
                Confidence.HIGH if allocation_level is not None else Confidence.UNKNOWN
            ),
            source_independence=(
                Confidence.HIGH
                if draft.independently_assigned is not TriState.UNKNOWN
                else Confidence.UNKNOWN
            ),
            exclusions=(Confidence.HIGH if exclusions else Confidence.UNKNOWN),
            aggregation=Confidence.UNKNOWN,
            statistical_model=Confidence.UNKNOWN,
        ),
        evidence=evidence,
        determinability=Determinability.INSUFFICIENT_INFORMATION,
        versions=Versions(
            schema_version=SCHEMA_VERSION,
            parser_version=PARSER_VERSION,
            graph_version=GRAPH_VERSION,
            ruleset_id=DEFAULT_RULESET_ID,
            ruleset_version=DEFAULT_RULESET_VERSION,
            ontology_version=ONTOLOGY_VERSION,
        ),
    )


def _count_records(
    request: ProspectiveD0CompileRequest,
    sample_sheet: SampleSheetSpec,
    *,
    factor_column: str,
    factor_id: str,
    contrast_id: str,
    row_evidence_ids: tuple[str, ...],
    design_evidence_ids: tuple[str, ...],
) -> tuple[CountRecord, ...]:
    draft = request.draft
    allocation_level = _known_level(draft.allocation_level)
    rows_with_evidence = tuple(zip(sample_sheet.rows, row_evidence_ids, strict=True))
    timepoints: tuple[str | None, ...] = tuple(
        dict.fromkeys(row.timepoint for row in sample_sheet.rows)
    ) or (None,)
    records: list[CountRecord] = []
    for group in (draft.level_a, draft.level_b):
        for timepoint in timepoints:
            group_rows = tuple(
                (row, evidence_id)
                for row, evidence_id in rows_with_evidence
                if row.factor_levels[factor_column] == group and row.timepoint == timepoint
            )
            for kind, lifecycle in _LIFECYCLE_KINDS:
                selected, quantifier = _lifecycle_rows(kind, group_rows)
                if kind is CountKind.PLANNED_N:
                    value = _unique_allocation_count(selected, allocation_level)
                    unit_type = allocation_level
                else:
                    value, unit_type = _unique_physical_row_count(selected)
                    if not selected:
                        unit_type = _homogeneous_physical_row_unit(group_rows)
                if not selected or value is None:
                    quantifier = CountQuantifier.NOT_REPORTED
                    value = None
                evidence_ids = _merge_evidence_ids(
                    design_evidence_ids if selected else (),
                    tuple(evidence_id for _, evidence_id in selected),
                )
                records.append(
                    _count_record(
                        block_seed=request.draft.experiment_block_id,
                        kind=kind,
                        value=value,
                        quantifier=quantifier,
                        unit_type=unit_type,
                        factor_id=factor_id,
                        contrast_id=contrast_id,
                        group=group,
                        endpoint_id=draft.endpoint_id,
                        timepoint=timepoint,
                        lifecycle=lifecycle,
                        population=draft.population_of_inference,
                        condition=draft.estimand.condition if draft.estimand else None,
                        evidence_ids=evidence_ids,
                    )
                )

            reported_sources = {row.source_id for row, _ in group_rows if row.source_id is not None}
            if not reported_sources:
                source_value = None
                source_quantifier = CountQuantifier.NOT_REPORTED
            elif len(reported_sources) < len(group_rows) and any(
                row.source_id is None for row, _ in group_rows
            ):
                source_value = len(reported_sources)
                source_quantifier = CountQuantifier.LOWER_BOUND
            else:
                source_value = len(reported_sources)
                source_quantifier = CountQuantifier.EXACT
            records.append(
                _count_record(
                    block_seed=request.draft.experiment_block_id,
                    kind=CountKind.BIOLOGICAL_SOURCE_COUNT,
                    value=source_value,
                    quantifier=source_quantifier,
                    unit_type=NodeType.BIOLOGICAL_SOURCE,
                    factor_id=factor_id,
                    contrast_id=contrast_id,
                    group=group,
                    endpoint_id=draft.endpoint_id,
                    timepoint=timepoint,
                    lifecycle=LifecycleStatus.PLANNED,
                    population=draft.population_of_inference,
                    condition=draft.estimand.condition if draft.estimand else None,
                    evidence_ids=_merge_evidence_ids(
                        design_evidence_ids,
                        tuple(evidence_id for _, evidence_id in group_rows),
                    ),
                )
            )

            planned_rows = group_rows
            independent_value = _unique_allocation_count(planned_rows, allocation_level)
            if (
                draft.independently_assigned is TriState.TRUE
                and planned_rows
                and independent_value is not None
            ):
                records.append(
                    _count_record(
                        block_seed=request.draft.experiment_block_id,
                        kind=CountKind.INDEPENDENT_N,
                        value=independent_value,
                        quantifier=CountQuantifier.EXACT,
                        unit_type=allocation_level,
                        factor_id=factor_id,
                        contrast_id=contrast_id,
                        group=group,
                        endpoint_id=draft.endpoint_id,
                        timepoint=timepoint,
                        lifecycle=LifecycleStatus.PLANNED,
                        population=draft.population_of_inference,
                        condition=draft.estimand.condition if draft.estimand else None,
                        evidence_ids=_merge_evidence_ids(
                            design_evidence_ids,
                            tuple(evidence_id for _, evidence_id in planned_rows),
                        ),
                    )
                )
    return tuple(records)


def _lifecycle_rows(
    kind: CountKind,
    group_rows: tuple[tuple[SampleSheetRow, str], ...],
) -> tuple[tuple[tuple[SampleSheetRow, str], ...], CountQuantifier]:
    """Deriva solo quantità difendibili da uno stato corrente per riga.

    ``planned_n`` è esatto perché le righe sono l'inventario prospettico. Gli
    stati intermedi sono lower bound: uno stato corrente non è una cronologia
    completa. Excluded/analysed sono conteggi esatti delle righe esplicitamente
    marcate, mentre l'assenza resta NOT_REPORTED e non diventa zero.
    """

    if kind is CountKind.PLANNED_N:
        return group_rows, CountQuantifier.EXACT
    if kind is CountKind.EXCLUDED_N:
        return (
            tuple(
                item
                for item in group_rows
                if item[0].lifecycle_status is SampleLifecycleStatus.EXCLUDED
            ),
            CountQuantifier.EXACT,
        )
    if kind is CountKind.ANALYSED_N:
        return (
            tuple(
                item
                for item in group_rows
                if item[0].lifecycle_status is SampleLifecycleStatus.ANALYSED
            ),
            CountQuantifier.EXACT,
        )

    status_floor: dict[CountKind, set[SampleLifecycleStatus]] = {
        CountKind.ALLOCATED_N: {
            SampleLifecycleStatus.TREATED,
            SampleLifecycleStatus.OBSERVED,
            SampleLifecycleStatus.ANALYSED,
        },
        CountKind.TREATED_N: {
            SampleLifecycleStatus.TREATED,
            SampleLifecycleStatus.OBSERVED,
            SampleLifecycleStatus.ANALYSED,
        },
        CountKind.OBSERVED_N: {
            SampleLifecycleStatus.OBSERVED,
            SampleLifecycleStatus.ANALYSED,
        },
    }
    selected = [item for item in group_rows if item[0].lifecycle_status in status_floor[kind]]
    # Le esclusioni contribuiscono a un lower bound soltanto quando la fase
    # esplicita dimostra che l'unita aveva già attraversato quel passaggio.
    phase_floor: dict[CountKind, set[ExclusionPhase]] = {
        CountKind.ALLOCATED_N: {
            ExclusionPhase.POST_ALLOCATION,
            ExclusionPhase.POST_TREATMENT,
            ExclusionPhase.POST_MEASUREMENT,
            ExclusionPhase.POST_OUTCOME,
        },
        CountKind.TREATED_N: {
            ExclusionPhase.POST_TREATMENT,
            ExclusionPhase.POST_MEASUREMENT,
            ExclusionPhase.POST_OUTCOME,
        },
        CountKind.OBSERVED_N: {
            ExclusionPhase.POST_MEASUREMENT,
            ExclusionPhase.POST_OUTCOME,
        },
    }
    for item in group_rows:
        if item[0].lifecycle_status is not SampleLifecycleStatus.EXCLUDED:
            continue
        phase, _, _ = _exclusion_metadata(item[0])
        if phase in phase_floor[kind]:
            selected.append(item)
    return tuple(selected), CountQuantifier.LOWER_BOUND


def _count_record(
    *,
    block_seed: str,
    kind: CountKind,
    value: int | None,
    quantifier: CountQuantifier,
    unit_type: NodeType | None,
    factor_id: str,
    contrast_id: str,
    group: str,
    endpoint_id: str,
    timepoint: str | None,
    lifecycle: LifecycleStatus,
    population: str,
    condition: str | None,
    evidence_ids: tuple[str, ...],
) -> CountRecord:
    unknown_reasons: dict[str, str] = {}
    if unit_type is None:
        unknown_reasons["unit_type"] = "allocation_level_not_confirmed"
    if timepoint is None:
        unknown_reasons["timepoint"] = "timepoint_not_reported"
    scope = CountScope(
        unit_type=unit_type,
        factor_id=factor_id,
        contrast_id=contrast_id,
        group_or_level=group,
        endpoint_id=endpoint_id,
        timepoint=timepoint,
        lifecycle=lifecycle,
        population=population,
        condition=condition,
        unknown_reasons=unknown_reasons,
    )
    return CountRecord(
        count_id=stable_id("cnt", block_seed, kind, scope.model_dump(mode="json")),
        kind=kind,
        value=value,
        quantifier=quantifier,
        scope=scope,
        evidence_ids=evidence_ids,
        provenance=Provenance(
            origin=ProvenanceKind.DERIVED,
            evidence_ids=evidence_ids,
            rule_id="D0-PROSPECTIVE-COUNT",
            ruleset_version=DEFAULT_RULESET_VERSION,
            derivation=(
                (
                    "conteggio di unita di allocazione uniche"
                    if kind in {CountKind.PLANNED_N, CountKind.INDEPENDENT_N}
                    else (
                        "conteggio di identificativi di fonte biologica unici"
                        if kind is CountKind.BIOLOGICAL_SOURCE_COUNT
                        else "conteggio di unita fisiche di riga uniche"
                    )
                )
                + "; gli stati intermedi sono lower bound e l'assenza di righe "
                "resta NOT_REPORTED"
            ),
        ),
    )


def _exclusion_records(
    request: ProspectiveD0CompileRequest,
    sample_sheet: SampleSheetSpec,
    *,
    factor_column: str,
    factor_id: str,
    contrast_id: str,
    block_id: str,
    row_evidence_ids: tuple[str, ...],
) -> tuple[ExclusionRecord, ...]:
    records: list[ExclusionRecord] = []
    for row, evidence_id in zip(sample_sheet.rows, row_evidence_ids, strict=True):
        if row.lifecycle_status is not SampleLifecycleStatus.EXCLUDED:
            continue
        phase, author_role, criterion = _exclusion_metadata(row)
        identity = _physical_row_identity(row)
        unit_type = identity[0] if identity is not None else None
        # La cross-validation impedisce di arrivare qui senza unita e metadata.
        if unit_type is None or phase is None or author_role is None or criterion is None:
            continue
        assert identity is not None
        unit_id = make_node_id(block_id, unit_type, identity[1])
        records.append(
            ExclusionRecord(
                id=stable_id("exc", request.draft.question_text, row.sample_id, evidence_id),
                unit_id=unit_id,
                unit_type=unit_type,
                phase=phase,
                prespecified=TriState(
                    row.extra_fields.get("ntruth_exclusion_prespecified") or TriState.UNKNOWN.value
                ),
                endpoint_id=request.draft.endpoint_id,
                factor_id=factor_id,
                contrast_id=contrast_id,
                group=row.factor_levels[factor_column],
                author_role=author_role,
                reason=criterion,
                evidence_ids=(evidence_id,),
                impact=row.extra_fields.get("ntruth_exclusion_impact"),
                unknown_reasons={
                    **(
                        {"prespecified": "not_reported_in_prospective_sample_sheet"}
                        if row.extra_fields.get("ntruth_exclusion_prespecified")
                        in {None, TriState.UNKNOWN.value}
                        else {}
                    ),
                    **(
                        {"impact": "not_reported_in_prospective_sample_sheet"}
                        if row.extra_fields.get("ntruth_exclusion_impact") is None
                        else {}
                    ),
                },
                provenance=Provenance(
                    origin=ProvenanceKind.TABULAR,
                    evidence_ids=(evidence_id,),
                    extraction_method="prospective_d0_sample_sheet",
                    derivation="metadata di esclusione normalizzati senza inferire la fase",
                ),
            )
        )
    return tuple(records)


def _unit_assessments(
    request: ProspectiveD0CompileRequest,
    sample_sheet: SampleSheetSpec,
    *,
    factor_column: str,
    factor_id: str,
    contrast_id: str,
    target_id: str,
    row_evidence_ids: tuple[str, ...],
    design_evidence_ids: tuple[str, ...],
    has_perfect_confounding: bool,
) -> tuple[UnitAssessment, ...]:
    draft = request.draft
    allocation_level = _known_level(draft.allocation_level)
    measured_on = _known_level(draft.measured_on)
    rows_with_evidence = tuple(zip(sample_sheet.rows, row_evidence_ids, strict=True))
    timepoints: tuple[str | None, ...] = tuple(
        dict.fromkeys(row.timepoint for row in sample_sheet.rows)
    ) or (None,)
    assessments: list[UnitAssessment] = []
    for group in (draft.level_a, draft.level_b):
        for timepoint in timepoints:
            group_rows = tuple(
                item
                for item in rows_with_evidence
                if item[0].factor_levels[factor_column] == group and item[0].timepoint == timepoint
            )
            planned_n = _unique_allocation_count(group_rows, allocation_level)
            biological_source_count = (
                len({row.source_id for row, _ in group_rows if row.source_id is not None})
                if group_rows and all(row.source_id is not None for row, _ in group_rows)
                else None
            )
            can_publish = (
                draft.independently_assigned is TriState.TRUE
                and allocation_level is not None
                and bool(group_rows)
                and planned_n is not None
            )
            can_branch = (
                draft.independently_assigned is TriState.UNKNOWN
                and allocation_level is not None
                and draft.target_biological_unit is not None
                and draft.estimand is not None
                and bool(group_rows)
                and planned_n is not None
                and not has_perfect_confounding
            )
            evidence_ids = _merge_evidence_ids(
                design_evidence_ids,
                tuple(item[1] for item in group_rows),
            )
            conditional_scenarios: tuple[ConditionalScenario, ...] = ()
            if can_branch:
                assert allocation_level is not None
                assert planned_n is not None
                conditional_scenarios = (
                    ConditionalScenario(
                        conditional_on=(
                            f"factor:{factor_id}:independently_assigned_at_{allocation_level.value}"
                        ),
                        if_confirmed={"n_independent": planned_n},
                        if_rejected={"n_independent": None},
                        question=(
                            "Le unita di allocazione sono state assegnate "
                            "indipendentemente mediante un meccanismo documentato?"
                        ),
                        rule_id="D0-PROSPECTIVE-INDEPENDENCE",
                        evidence_ids=evidence_ids,
                    ),
                )
            assessments.append(
                UnitAssessment(
                    id=stable_id("uas", request.draft.question_text, factor_id, group, timepoint),
                    scope=NScope(
                        factor_id=factor_id,
                        contrast_id=contrast_id,
                        endpoint_id=draft.endpoint_id,
                        group=group,
                        timepoint=timepoint,
                        inference_target_id=target_id,
                        unit_type=allocation_level,
                        lifecycle=LifecycleStatus.PLANNED,
                        population=draft.population_of_inference,
                    ),
                    biological_unit=draft.target_biological_unit,
                    allocation_unit_candidate=allocation_level,
                    experimental_unit=allocation_level if can_publish else None,
                    observational_unit=measured_on,
                    analytical_unit=None,
                    n_planned=planned_n if group_rows else None,
                    biological_source_count=biological_source_count,
                    n_independent=planned_n if can_publish else None,
                    independent_entity_type=(
                        allocation_level.value
                        if allocation_level is not None and can_publish
                        else None
                    ),
                    inferability=(
                        Inferability.INFERABLE
                        if can_publish
                        else (
                            Inferability.CONDITIONAL if can_branch else Inferability.NOT_INFERABLE
                        )
                    ),
                    conditional_scenarios=conditional_scenarios,
                    risk=RiskLabel.INSUFFICIENT,
                    data_sufficiency=DataSufficiency(
                        intervention_level=(
                            Confidence.HIGH if allocation_level is not None else Confidence.UNKNOWN
                        ),
                        source_independence=(
                            Confidence.HIGH
                            if draft.independently_assigned is not TriState.UNKNOWN
                            else Confidence.UNKNOWN
                        ),
                    ),
                    rationale=(
                        "independent_n coincide con le unita di allocazione uniche soltanto "
                        "quando il ricercatore conferma un meccanismo operativo; in caso "
                        "di risposta UNKNOWN entrambi i rami restano espliciti"
                    ),
                    evidence_ids=evidence_ids,
                    provenance=Provenance(
                        origin=ProvenanceKind.DERIVED,
                        evidence_ids=evidence_ids,
                        rule_id="D0-PROSPECTIVE-UNIT",
                        ruleset_version=DEFAULT_RULESET_VERSION,
                        derivation="assessment scope-aware dal draft e dal sample sheet",
                    ),
                )
            )
    return tuple(assessments)


def _hierarchy(
    request: ProspectiveD0CompileRequest,
    sample_sheet: SampleSheetSpec,
    *,
    block_id: str,
    factor: Factor,
    contrast: Contrast,
    endpoint: Endpoint,
    target: InferenceTarget,
    estimands: tuple[Estimand, ...],
    row_evidence_ids: tuple[str, ...],
    design_evidence_ids: tuple[str, ...],
) -> Hierarchy:
    design_provenance = Provenance(
        origin=ProvenanceKind.DERIVED,
        evidence_ids=design_evidence_ids,
        extraction_method="prospective_d0_graph_materialization",
        derivation="materializzazione deterministica dei fatti confermati nel wizard",
    )
    nodes: dict[str, GraphNode] = {}
    relations: dict[str, GraphRelation] = {}

    def add_node(
        node_type: NodeType,
        label: str,
        *,
        evidence_ids: tuple[str, ...],
        provenance: Provenance,
        identifier: str | None = None,
    ) -> str:
        node_id = identifier or make_node_id(block_id, node_type, label)
        nodes.setdefault(
            node_id,
            GraphNode(
                id=node_id,
                type=node_type,
                label=label,
                evidence_ids=evidence_ids,
                provenance=provenance,
            ),
        )
        return node_id

    def add_relation(
        relation_type: RelationType,
        source: str,
        target_id: str,
        *,
        evidence_ids: tuple[str, ...],
        provenance: Provenance,
    ) -> None:
        relation_id = make_relation_id(relation_type, source, target_id)
        relations.setdefault(
            relation_id,
            GraphRelation(
                id=relation_id,
                type=relation_type,
                source=source,
                target=target_id,
                evidence_ids=evidence_ids,
                provenance=provenance,
            ),
        )

    block_node = add_node(
        NodeType.EXPERIMENT_BLOCK,
        request.draft.title,
        evidence_ids=design_evidence_ids,
        provenance=design_provenance,
        identifier=block_id,
    )
    factor_node = add_node(
        NodeType.FACTOR,
        factor.name,
        evidence_ids=factor.evidence_ids,
        provenance=_graph_provenance(factor.evidence_ids),
        identifier=factor.id,
    )
    contrast_node = add_node(
        NodeType.CONTRAST,
        contrast.label,
        evidence_ids=contrast.evidence_ids,
        provenance=_graph_provenance(contrast.evidence_ids),
        identifier=contrast.id,
    )
    endpoint_node = add_node(
        NodeType.ENDPOINT,
        endpoint.name,
        evidence_ids=endpoint.evidence_ids,
        provenance=_graph_provenance(endpoint.evidence_ids),
        identifier=endpoint.id,
    )
    target_node = add_node(
        NodeType.INFERENCE_TARGET,
        target.question_text,
        evidence_ids=target.evidence_ids,
        provenance=_graph_provenance(target.evidence_ids),
        identifier=target.id,
    )
    add_relation(
        RelationType.HAS_FACTOR,
        block_node,
        factor_node,
        evidence_ids=factor.evidence_ids,
        provenance=_graph_provenance(factor.evidence_ids),
    )
    add_relation(
        RelationType.DEFINES_CONTRAST,
        factor_node,
        contrast_node,
        evidence_ids=contrast.evidence_ids,
        provenance=_graph_provenance(contrast.evidence_ids),
    )
    add_relation(
        RelationType.HAS_ENDPOINT,
        block_node,
        endpoint_node,
        evidence_ids=endpoint.evidence_ids,
        provenance=_graph_provenance(endpoint.evidence_ids),
    )
    add_relation(
        RelationType.SUPPORTS,
        block_node,
        target_node,
        evidence_ids=target.evidence_ids,
        provenance=_graph_provenance(target.evidence_ids),
    )
    for estimand in estimands:
        estimand_node = add_node(
            NodeType.ESTIMAND,
            estimand.effect_measure,
            evidence_ids=estimand.evidence_ids,
            provenance=_graph_provenance(estimand.evidence_ids),
            identifier=estimand.id,
        )
        add_relation(
            RelationType.SUPPORTS,
            estimand_node,
            target_node,
            evidence_ids=estimand.evidence_ids,
            provenance=_graph_provenance(estimand.evidence_ids),
        )

    for row, evidence_id in zip(sample_sheet.rows, row_evidence_ids, strict=True):
        row_provenance = Provenance(
            origin=ProvenanceKind.TABULAR,
            evidence_ids=(evidence_id,),
            extraction_method="prospective_d0_sample_sheet",
        )
        chain: list[tuple[NodeType, str]] = []
        if row.source_id:
            chain.append((NodeType.BIOLOGICAL_SOURCE, row.source_id))
        if row.preparation_id:
            chain.append((NodeType.PRIMARY_CULTURE, row.preparation_id))
        if row.culture_id:
            chain.append((NodeType.CELL_CULTURE, row.culture_id))
        if row.plate_id:
            chain.append((NodeType.PLATE, row.plate_id))
        if row.well_id:
            well_label = f"{row.plate_id}:{row.well_id}" if row.plate_id else row.well_id
            chain.append((NodeType.WELL, well_label))
            if request.draft.cell_population_plan:
                chain.append((NodeType.CELL, f"{well_label}:planned-cell-population"))
        chain_ids = [
            add_node(
                node_type,
                label,
                evidence_ids=(evidence_id,),
                provenance=row_provenance,
            )
            for node_type, label in chain
        ]
        for (parent_type, _), (child_type, _), parent_id, child_id in zip(
            chain,
            chain[1:],
            chain_ids,
            chain_ids[1:],
            strict=False,
        ):
            relation_type = (
                RelationType.NESTED_IN
                if (
                    parent_type in {NodeType.CELL_CULTURE, NodeType.PLATE}
                    and child_type in {NodeType.PLATE, NodeType.WELL}
                )
                or (parent_type is NodeType.WELL and child_type is NodeType.CELL)
                else RelationType.DERIVED_FROM
            )
            add_relation(
                relation_type,
                child_id,
                parent_id,
                evidence_ids=(evidence_id,),
                provenance=row_provenance,
            )
        if row.batch_id:
            batch_node = add_node(
                NodeType.BATCH,
                row.batch_id,
                evidence_ids=(evidence_id,),
                provenance=row_provenance,
            )
            if chain_ids:
                add_relation(
                    RelationType.PROCESSED_IN_BATCH,
                    chain_ids[-1],
                    batch_node,
                    evidence_ids=(evidence_id,),
                    provenance=row_provenance,
                )

    return Hierarchy(nodes=tuple(nodes.values()), relations=tuple(relations.values()))


def _draft_evidence(
    draft: ProspectiveD0Draft,
    *,
    block_id: str,
    file_id: str,
    factor_id: str,
) -> tuple[EvidenceSpan, ...]:
    estimand_text = "estimand=NOT_REPORTED"
    if draft.estimand is not None:
        estimand_text = (
            f"effect_measure={draft.estimand.effect_measure}; "
            f"target_population_or_unit={draft.estimand.target_population_or_unit}; "
            f"generalization_level={draft.estimand.generalization_level}; "
            f"timepoint={draft.estimand.timepoint or 'NOT_REPORTED'}; "
            f"condition={draft.estimand.condition or 'NOT_REPORTED'}"
        )
    sections = (
        (
            "block",
            f"experiment_block_id={block_id}; title={draft.title}",
        ),
        (
            "target",
            (
                f"question={draft.question_text}; "
                f"population_of_inference={draft.population_of_inference}; "
                "target_biological_unit="
                f"{draft.target_biological_unit.value if draft.target_biological_unit else 'NOT_REPORTED'}"
            ),
        ),
        (
            "factor",
            (
                f"factor_name={draft.factor_name}; factor_kind={draft.factor_kind}; "
                f"levels={draft.level_a}|{draft.level_b}"
            ),
        ),
        ("allocation", f"allocation_level={draft.allocation_level}"),
        ("application", f"application_level={draft.application_level}"),
        (
            "independence",
            (
                f"independently_assigned={draft.independently_assigned}; "
                f"mechanism={draft.independence_mechanism or 'NOT_REPORTED'}"
            ),
        ),
        (
            "environment",
            "shared_environment="
            + (
                json.dumps(draft.shared_environment) if draft.shared_environment else "NOT_REPORTED"
            ),
        ),
        (
            "endpoint",
            f"{draft.endpoint_id}: {draft.endpoint_name}; measured_on={draft.measured_on}",
        ),
        ("estimand", estimand_text),
        (
            "cell_plan",
            "cell_population_plan=" + (draft.cell_population_plan or "NOT_REPORTED"),
        ),
    )
    return tuple(
        EvidenceSpan(
            id=stable_id("ev", block_id, factor_id, section, text),
            file_id=file_id,
            section_id=section,
            section_title=f"D0 wizard: {section}",
            text=text,
            parser_version=PARSER_VERSION,
            evidence_type=EvidenceType.USER_CONFIRMATION,
            extraction_method="prospective_d0_wizard",
            confidence=1.0,
        )
        for section, text in sections
    )


def _row_evidence(
    row: SampleSheetRow,
    *,
    index: int,
    block_id: str,
    file_id: str,
) -> EvidenceSpan:
    # ``section_id`` è un locator virtuale stabile per l'export JSON; la
    # sorgente non viene spacciata per un documento con offset inesistenti.
    return EvidenceSpan(
        id=stable_id("ev", block_id, "sample-sheet-row", index, row.model_dump(mode="json")),
        file_id=file_id,
        section_id=f"SampleSheetSpec.rows[{index - 2}]",
        section_title=f"SampleSheet D0 row {index}",
        text=str(row.model_dump(mode="json")),
        parser_version=PARSER_VERSION,
        evidence_type=EvidenceType.SAMPLE_METADATA,
        extraction_method="prospective_d0_sample_sheet",
        confidence=1.0,
    )


def _as_build_result(block: ExperimentBlock) -> BuildResult:
    return BuildResult(
        hierarchy=block.hierarchy,
        factors=block.factors,
        contrasts=block.contrasts,
        endpoints=block.endpoints,
        inference_targets=block.inference_targets,
        estimands=block.estimands,
        n_statements=block.n_statements,
        contradictions=block.contradictions,
        questions=block.questions,
        models=block.models,
        processes=block.processes,
    )


def _graph_provenance(evidence_ids: tuple[str, ...]) -> Provenance:
    """Il grafo è una proiezione del fatto umano, non una nuova correzione umana."""

    return Provenance(
        origin=ProvenanceKind.DERIVED,
        evidence_ids=evidence_ids,
        extraction_method="prospective_d0_graph_materialization",
        derivation="materializzazione deterministica di un fatto confermato nel wizard",
    )


def _row_factor_levels(row: ProspectiveD0Row, expected_column: str) -> dict[str, str]:
    if row.factor_level is not None:
        return {expected_column: row.factor_level}
    assert row.factor_levels is not None
    normalized = {
        normalize_factor_column(name): value.strip() for name, value in row.factor_levels.items()
    }
    if set(normalized) != {expected_column}:
        raise ValueError(
            f"factor_levels deve contenere soltanto '{expected_column}', trovato {sorted(normalized)}"
        )
    return normalized


def _canonical_extra_fields(row: ProspectiveD0Row) -> dict[str, str | None]:
    collisions = sorted(set(row.extra_fields) & set(_EXCLUSION_EXTENSION_HEADERS))
    if collisions:
        raise ValueError(
            "extra_fields non puo ridefinire le estensioni di esclusione: " + ", ".join(collisions)
        )
    extensions: dict[str, str | None] = {}
    if row.lifecycle_status is SampleLifecycleStatus.EXCLUDED or any(
        (
            row.exclusion_phase,
            row.exclusion_author_role,
            row.exclusion_impact,
            row.exclusion_prespecified is not TriState.UNKNOWN,
        )
    ):
        extensions = {
            "ntruth_exclusion_phase": (
                row.exclusion_phase.value if row.exclusion_phase is not None else None
            ),
            "ntruth_exclusion_prespecified": row.exclusion_prespecified.value,
            "ntruth_exclusion_author_role": row.exclusion_author_role,
            "ntruth_exclusion_impact": row.exclusion_impact,
        }
    return {**row.extra_fields, **extensions}


def _factor_slug(value: str) -> str:
    normalized = _FACTOR_SLUG_RE.sub("_", value.casefold()).strip("_.-")
    return normalized or "primary"


def _normalized_timepoint(value: str) -> str:
    return " ".join(value.casefold().split())


def _known_level(value: NodeType | Literal["UNKNOWN"]) -> NodeType | None:
    return value if isinstance(value, NodeType) else None


def _allocation_key(row: SampleSheetRow, level: NodeType | None) -> str | None:
    if level is NodeType.WELL and row.plate_id and row.well_id:
        return f"{row.plate_id}::{row.well_id}"
    if level is NodeType.PLATE and row.plate_id:
        return row.plate_id
    if level is NodeType.CELL_CULTURE and row.culture_id:
        return row.culture_id
    if level is NodeType.PRIMARY_CULTURE and row.preparation_id:
        return row.preparation_id
    return None


def _physical_row_identity(row: SampleSheetRow) -> tuple[NodeType, str] | None:
    """Restituisce l'unita fisica piu specifica realmente identificata dalla riga."""

    if row.well_id:
        label = f"{row.plate_id}:{row.well_id}" if row.plate_id else row.well_id
        return NodeType.WELL, label
    if row.plate_id:
        return NodeType.PLATE, row.plate_id
    if row.culture_id:
        return NodeType.CELL_CULTURE, row.culture_id
    if row.preparation_id:
        return NodeType.PRIMARY_CULTURE, row.preparation_id
    if row.source_id:
        return NodeType.BIOLOGICAL_SOURCE, row.source_id
    return None


def _homogeneous_physical_row_unit(
    rows: Iterable[tuple[SampleSheetRow, str]],
) -> NodeType | None:
    identities = tuple(_physical_row_identity(row) for row, _ in rows)
    if not identities or any(item is None for item in identities):
        return None
    unit_types = {item[0] for item in identities if item is not None}
    return next(iter(unit_types)) if len(unit_types) == 1 else None


def _unique_physical_row_count(
    rows: Iterable[tuple[SampleSheetRow, str]],
) -> tuple[int | None, NodeType | None]:
    materialized = tuple(rows)
    unit_type = _homogeneous_physical_row_unit(materialized)
    if unit_type is None:
        return None, None
    identities = {
        identity[1]
        for row, _ in materialized
        if (identity := _physical_row_identity(row)) is not None
    }
    return (len(identities), unit_type) if identities else (None, unit_type)


def _unique_allocation_count(
    rows: Iterable[tuple[SampleSheetRow, str]],
    allocation_level: NodeType | None,
) -> int | None:
    keys = {key for row, _ in rows if (key := _allocation_key(row, allocation_level)) is not None}
    return len(keys) if keys else None


def _perfect_confounding_dimensions(
    request: ProspectiveD0CompileRequest,
    sample_sheet: SampleSheetSpec,
    *,
    factor_column: str,
) -> tuple[str, ...]:
    """Rileva solo la coincidenza perfetta osservabile nel D0.

    Tutte le righe devono dichiarare la dimensione. Il controllo scatta quando
    gli insiemi di cluster dei due livelli sono non vuoti e disgiunti e almeno
    un cluster contiene piu unita di allocazione. La condizione di clustering
    evita di classificare come confondimento una mera chiave uno-a-uno della riga.
    """

    allocation_level = _known_level(request.draft.allocation_level)
    if allocation_level is None:
        return ()
    allocation_depth = _D0_UNIT_DEPTH.get(allocation_level)
    if allocation_depth is None:
        return ()
    candidates: tuple[tuple[str, int | None], ...] = (
        ("source_id", -1),
        ("preparation_id", _D0_UNIT_DEPTH[NodeType.PRIMARY_CULTURE]),
        ("culture_id", _D0_UNIT_DEPTH[NodeType.CELL_CULTURE]),
        ("plate_id", _D0_UNIT_DEPTH[NodeType.PLATE]),
        ("batch_id", None),
        ("day_id", None),
        ("operator_id", None),
        ("incubator_id", None),
    )
    dimensions: list[str] = []
    levels = (request.draft.level_a, request.draft.level_b)
    for field_name, depth in candidates:
        if depth is not None and depth >= allocation_depth:
            continue
        values_by_level: dict[str, set[str]] = {level: set() for level in levels}
        allocations_by_cluster: dict[str, set[str]] = defaultdict(set)
        complete = True
        for row in sample_sheet.rows:
            raw_value = _confounding_value(row, field_name)
            allocation_key = _allocation_key(row, allocation_level)
            if raw_value is None or allocation_key is None:
                complete = False
                break
            values_by_level[row.factor_levels[factor_column]].add(raw_value)
            allocations_by_cluster[raw_value].add(allocation_key)
        if not complete or any(not values_by_level[level] for level in levels):
            continue
        left = values_by_level[levels[0]]
        right = values_by_level[levels[1]]
        genuinely_clustered = any(len(keys) > 1 for keys in allocations_by_cluster.values())
        if left.isdisjoint(right) and genuinely_clustered:
            dimensions.append(field_name)
    return tuple(dimensions)


def _confounding_value(row: SampleSheetRow, field_name: str) -> str | None:
    if field_name in {"day_id", "operator_id", "incubator_id"}:
        return row.extra_fields.get(field_name)
    value = getattr(row, field_name)
    return value if isinstance(value, str) else None


def _merge_evidence_ids(*groups: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item for group in groups for item in group))


def _exclusion_metadata(
    row: SampleSheetRow,
) -> tuple[ExclusionPhase | None, str | None, str | None]:
    reason = row.exclusion_reason or ""
    raw_phase = row.extra_fields.get("ntruth_exclusion_phase")
    phase = ExclusionPhase(raw_phase) if raw_phase else None
    phase_match = _PHASE_RE.search(reason)
    if phase is None and phase_match is not None:
        phase = _PHASE_BY_TOKEN[phase_match.group(0).casefold()]
    author_role = row.extra_fields.get("ntruth_exclusion_author_role")
    author_match = _AUTHOR_RE.search(reason)
    if author_role is None and author_match is not None:
        author_role = author_match.group(1).strip()

    criterion = reason
    if phase_match is not None:
        criterion = criterion.replace(phase_match.group(0), " ", 1)
    if author_match is not None:
        criterion = criterion.replace(author_match.group(0), " ", 1)
    criterion = re.sub(r"[|;:,\s]+", " ", criterion).strip()
    return phase, author_role, criterion or None


def _embedded_exclusion_metadata(
    row: SampleSheetRow,
) -> tuple[ExclusionPhase | None, str | None]:
    reason = row.exclusion_reason or ""
    phase_match = _PHASE_RE.search(reason)
    phase = _PHASE_BY_TOKEN[phase_match.group(0).casefold()] if phase_match is not None else None
    author_match = _AUTHOR_RE.search(reason)
    author_role = author_match.group(1).strip() if author_match is not None else None
    return phase, author_role


def _error(
    code: str,
    message: str,
    *,
    row: int | None = None,
    field: str | None = None,
) -> ProspectiveD0Issue:
    return ProspectiveD0Issue(
        code=code,
        message=message,
        severity=ProspectiveIssueSeverity.ERROR,
        row=row,
        field=field,
    )


def _warning(
    code: str,
    message: str,
    *,
    row: int | None = None,
    field: str | None = None,
) -> ProspectiveD0Issue:
    return ProspectiveD0Issue(
        code=code,
        message=message,
        severity=ProspectiveIssueSeverity.WARNING,
        row=row,
        field=field,
    )
