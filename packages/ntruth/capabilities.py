"""Capability boundary scientifico per i profili di N-Truth.

Il release profile governa i formati di input. Questo modulo governa invece il
perimetro scientifico: ogni ampliamento richiede una nuova versione esplicita
del capability contract e non puo avvenire come effetto collaterale di un parser.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from ntruth.schemas.experiment import ExperimentBlock
from ntruth.schemas.graph import NodeType, RelationType

CORE_PROFILE_ID = "ntruth-core"
CORE_PROFILE_VERSION = "0.1-D"
CORE_PROFILE_REFERENCE = f"{CORE_PROFILE_ID}@{CORE_PROFILE_VERSION}"


class CapabilityStatus(StrEnum):
    """Esito tri-state del controllo di capacita scientifica."""

    SUPPORTED = "supported"
    INCOMPLETE = "incomplete"
    OUT_OF_SCOPE = "out_of_scope"


class CapabilityReason(StrEnum):
    """Reason code stabili del Core Profile ``0.1-D``."""

    MISSING_PRIMARY_FACTOR = "missing_primary_factor"
    MISSING_FACTOR_KIND = "missing_factor_kind"
    MISSING_PRIMARY_ENDPOINT = "missing_primary_endpoint"
    MISSING_MEASUREMENT_LEVEL = "missing_measurement_level"
    TOO_MANY_FACTORS = "too_many_factors"
    TOO_MANY_ENDPOINTS = "too_many_endpoints"
    TOO_MANY_FACTOR_LEVELS = "too_many_factor_levels"
    UNSUPPORTED_ALLOCATION_LEVEL = "unsupported_allocation_level"
    UNSUPPORTED_APPLICATION_LEVEL = "unsupported_application_level"
    UNSUPPORTED_MEASUREMENT_LEVEL = "unsupported_measurement_level"
    UNSUPPORTED_TARGET_UNIT = "unsupported_target_unit"
    UNSUPPORTED_TOPOLOGY = "unsupported_topology"
    UNSUPPORTED_PROCESS = "unsupported_process"
    MULTIPLE_TIMEPOINTS = "multiple_timepoints"
    UNSUPPORTED_STATISTICAL_MODEL = "unsupported_statistical_model"


@dataclass(frozen=True, slots=True)
class CapabilityDecision:
    """Decisione riproducibile, identificata dal profilo che l'ha prodotta."""

    profile_id: str
    profile_version: str
    status: CapabilityStatus
    reason_codes: tuple[CapabilityReason, ...] = ()
    details: tuple[str, ...] = ()

    @property
    def supported(self) -> bool | None:
        """Adapter tri-state per ``derive_determinability``."""

        if self.status is CapabilityStatus.SUPPORTED:
            return True
        if self.status is CapabilityStatus.OUT_OF_SCOPE:
            return False
        return None

    @property
    def profile_reference(self) -> str:
        return f"{self.profile_id}@{self.profile_version}"


_ALLOWED_ALLOCATION_UNITS = frozenset(
    {
        NodeType.CELL_CULTURE,
        NodeType.PRIMARY_CULTURE,
        NodeType.PLATE,
        NodeType.WELL,
    }
)
_ALLOWED_APPLICATION_UNITS = _ALLOWED_ALLOCATION_UNITS | {NodeType.CELL}
_ALLOWED_MEASUREMENT_UNITS = _ALLOWED_APPLICATION_UNITS
_ALLOWED_TARGET_UNITS = _ALLOWED_APPLICATION_UNITS

# Ogni relazione elencata materializza una topologia che il PRD v6 colloca
# oltre il bootstrap monofattoriale D0. BLOCKED_BY e incluso fail-closed: un
# disegno a blocchi richiede un capability profile successivo e validato.
_UNSUPPORTED_RELATIONS = frozenset(
    {
        RelationType.SPLIT_FROM,
        RelationType.SPLIT_INTO,
        RelationType.POOLED_FROM,
        RelationType.POOLED_INTO,
        RelationType.MEMBER_OF_POOL,
        RelationType.PAIRED_WITH,
        RelationType.MATCHED_WITH,
        RelationType.BLOCKED_BY,
        RelationType.CROSSED_WITH,
        RelationType.REPEATED_MEASURE_OF,
    }
)
_UNSUPPORTED_TOPOLOGY_NODES = frozenset(
    {
        NodeType.BLOCK,
        NodeType.SPLIT_EVENT,
        NodeType.POOL_EVENT,
        NodeType.POOL,
    }
)

# I process kind sono un vocabolario interno, non testo libero. I marker
# consentono di fallire chiuso anche su future varianti come ``complex_pooling``
# senza confondere l'assenza di un processo con una prova di supporto.
_UNSUPPORTED_PROCESS_STEMS = (
    "longitud",
    "pair",
    "match",
    "cross",
    "split",
    "pool",
)

# Il parser deterministico materializza ``simple`` o ``mixed``. Qualunque nuovo
# kind resta fuori profilo finche non viene aggiunto a una versione successiva
# della matrice, evitando che un'estensione del parser ampli D0 silenziosamente.
_ALLOWED_MODEL_KINDS = frozenset({"simple"})
_UNSUPPORTED_SIMPLE_MODEL_TEXT = re.compile(
    r"\b(?:paired|wilcoxon|two[- ]way|repeated[- ]measure(?:s)?|longitudinal|"
    r"mixed[- ]effect(?:s)?|hierarchical|multilevel|lmm|glmm|gee|split[- ]plot|"
    r"matched|crossed)\b",
    re.IGNORECASE,
)


def assess_core_profile_capability(block: ExperimentBlock) -> CapabilityDecision:
    """Valuta ``block`` contro il capability contract Core ``0.1-D``.

    Il controllo usa soltanto fatti strutturati gia presenti nel blocco. Un
    segnale esplicito fuori profilo prevale sui campi mancanti; in sua assenza,
    fattore o endpoint mancanti producono ``INCOMPLETE`` e non ``SUPPORTED``.
    """

    reason_codes: list[CapabilityReason] = []
    details: list[str] = []

    def reject(reason: CapabilityReason, detail: str) -> None:
        if reason not in reason_codes:
            reason_codes.append(reason)
        details.append(detail)

    if len(block.factors) > 1:
        reject(CapabilityReason.TOO_MANY_FACTORS, f"factor_count={len(block.factors)}")
    if len(block.endpoints) > 1:
        reject(CapabilityReason.TOO_MANY_ENDPOINTS, f"endpoint_count={len(block.endpoints)}")

    for factor in block.factors:
        if len(factor.levels) > 2:
            reject(
                CapabilityReason.TOO_MANY_FACTOR_LEVELS,
                f"factor={factor.id}:level_count={len(factor.levels)}",
            )
        if (
            factor.allocation_level is not None
            and factor.allocation_level not in _ALLOWED_ALLOCATION_UNITS
        ):
            reject(
                CapabilityReason.UNSUPPORTED_ALLOCATION_LEVEL,
                f"factor={factor.id}:allocation_level={factor.allocation_level.value}",
            )
        if (
            factor.application_level is not None
            and factor.application_level not in _ALLOWED_APPLICATION_UNITS
        ):
            reject(
                CapabilityReason.UNSUPPORTED_APPLICATION_LEVEL,
                f"factor={factor.id}:application_level={factor.application_level.value}",
            )

    for endpoint in block.endpoints:
        if (
            endpoint.measured_on is not None
            and endpoint.measured_on not in _ALLOWED_MEASUREMENT_UNITS
        ):
            reject(
                CapabilityReason.UNSUPPORTED_MEASUREMENT_LEVEL,
                f"endpoint={endpoint.id}:measured_on={endpoint.measured_on.value}",
            )

    for target in block.inference_targets:
        if (
            target.target_biological_unit is not None
            and target.target_biological_unit not in _ALLOWED_TARGET_UNITS
        ):
            reject(
                CapabilityReason.UNSUPPORTED_TARGET_UNIT,
                (
                    f"inference_target={target.id}:"
                    f"target_biological_unit={target.target_biological_unit.value}"
                ),
            )

    unsupported_relation_types = sorted(
        {
            relation.type
            for relation in block.hierarchy.relations
            if relation.type in _UNSUPPORTED_RELATIONS
        },
        key=lambda item: item.value,
    )
    for relation_type in unsupported_relation_types:
        reject(CapabilityReason.UNSUPPORTED_TOPOLOGY, f"relation={relation_type.value}")

    unsupported_node_types = sorted(
        {node.type for node in block.hierarchy.nodes if node.type in _UNSUPPORTED_TOPOLOGY_NODES},
        key=lambda item: item.value,
    )
    for node_type in unsupported_node_types:
        reject(CapabilityReason.UNSUPPORTED_TOPOLOGY, f"node_type={node_type.value}")

    for process in block.processes:
        normalized_kind = _normalize_kind(process.kind)
        if _unsupported_process_kind(normalized_kind):
            reject(
                CapabilityReason.UNSUPPORTED_PROCESS,
                f"process={process.id}:kind={normalized_kind or '<empty>'}",
            )

    timepoints = _declared_timepoints(block)
    if len(timepoints) > 1:
        reject(
            CapabilityReason.MULTIPLE_TIMEPOINTS,
            "timepoints=" + ",".join(sorted(timepoints)),
        )

    for model in block.models:
        normalized_kind = _normalize_kind(model.kind)
        outside_model_matrix = normalized_kind not in _ALLOWED_MODEL_KINDS
        declares_clustering = bool(model.declared_clustering)
        unsupported_simple_text = bool(_UNSUPPORTED_SIMPLE_MODEL_TEXT.search(model.raw_text))
        if outside_model_matrix or declares_clustering or unsupported_simple_text:
            qualifiers = [f"kind={normalized_kind or '<empty>'}"]
            if declares_clustering:
                qualifiers.append("declared_clustering=true")
            if unsupported_simple_text:
                qualifiers.append("outside_core_topology=true")
            reject(
                CapabilityReason.UNSUPPORTED_STATISTICAL_MODEL,
                f"model={model.id}:" + ":".join(qualifiers),
            )

    if reason_codes:
        return CapabilityDecision(
            profile_id=CORE_PROFILE_ID,
            profile_version=CORE_PROFILE_VERSION,
            status=CapabilityStatus.OUT_OF_SCOPE,
            reason_codes=tuple(reason_codes),
            details=tuple(details),
        )

    incomplete_reasons: list[CapabilityReason] = []
    incomplete_details: list[str] = []
    if not block.factors:
        incomplete_reasons.append(CapabilityReason.MISSING_PRIMARY_FACTOR)
        incomplete_details.append("factor_count=0")
    elif any(factor.kind == "unknown" for factor in block.factors):
        incomplete_reasons.append(CapabilityReason.MISSING_FACTOR_KIND)
        incomplete_details.extend(
            f"factor={factor.id}:kind=missing"
            for factor in block.factors
            if factor.kind == "unknown"
        )
    if not block.endpoints:
        incomplete_reasons.append(CapabilityReason.MISSING_PRIMARY_ENDPOINT)
        incomplete_details.append("endpoint_count=0")
    elif any(endpoint.measured_on is None for endpoint in block.endpoints):
        incomplete_reasons.append(CapabilityReason.MISSING_MEASUREMENT_LEVEL)
        incomplete_details.extend(
            f"endpoint={endpoint.id}:measured_on=missing"
            for endpoint in block.endpoints
            if endpoint.measured_on is None
        )
    if incomplete_reasons:
        return CapabilityDecision(
            profile_id=CORE_PROFILE_ID,
            profile_version=CORE_PROFILE_VERSION,
            status=CapabilityStatus.INCOMPLETE,
            reason_codes=tuple(incomplete_reasons),
            details=tuple(incomplete_details),
        )

    return CapabilityDecision(
        profile_id=CORE_PROFILE_ID,
        profile_version=CORE_PROFILE_VERSION,
        status=CapabilityStatus.SUPPORTED,
    )


def _declared_timepoints(block: ExperimentBlock) -> set[str]:
    values = {
        normalized
        for endpoint in block.endpoints
        for value in endpoint.timepoints
        if (normalized := _normalize_timepoint(value))
    }
    values.update(
        normalized
        for factor in block.factors
        if factor.kind == "time"
        for value in factor.levels
        if (normalized := _normalize_timepoint(value))
    )
    values.update(
        normalized
        for estimand in block.estimands
        if (normalized := _normalize_timepoint(estimand.timepoint))
    )
    values.update(
        normalized
        for statement in block.n_statements
        if (normalized := _normalize_timepoint(statement.scope.timepoint))
    )
    values.update(
        normalized
        for record in block.count_records
        if (normalized := _normalize_timepoint(record.scope.timepoint))
    )
    values.update(
        normalized
        for assessment in block.unit_assessments
        if (normalized := _normalize_timepoint(assessment.scope.timepoint))
    )
    return values


def _normalize_kind(value: str) -> str:
    return "_".join(part for part in re.split(r"[^a-z0-9]+", value.casefold()) if part)


def _unsupported_process_kind(normalized_kind: str) -> bool:
    if normalized_kind.startswith(("repeated_measure", "repeatedmeasure")):
        return True
    return any(part.startswith(_UNSUPPORTED_PROCESS_STEMS) for part in normalized_kind.split("_"))


def _normalize_timepoint(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(value.casefold().split())
