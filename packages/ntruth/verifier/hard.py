"""Hard verifier sempre attivo, separato dal parser e dalle regole semantiche."""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum

from pydantic import Field

from ntruth.graph.validation import validate_experiment_block
from ntruth.schemas.core import Determinability, FrozenModel, ProvenanceKind
from ntruth.schemas.experiment import (
    CountKind,
    ExperimentBlock,
    LifecycleStatus,
    TriState,
)
from ntruth.schemas.graph import GraphViolation
from ntruth.verifier.output_policy import output_policy_violations


class VerificationStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class HardVerificationResult(FrozenModel):
    """Esito auditabile: nessun errore hard viene convertito in un verdict ML."""

    schema_version: str = "1.0.0"
    status: VerificationStatus
    block_id: str
    violations: tuple[GraphViolation, ...] = ()
    warnings: tuple[GraphViolation, ...] = ()
    checked_invariants: tuple[str, ...] = Field(min_length=1)

    @property
    def valid(self) -> bool:
        return self.status is VerificationStatus.COMPLETE and not self.violations


_LIFECYCLE_BY_KIND = {
    CountKind.PLANNED_N: LifecycleStatus.PLANNED,
    CountKind.ALLOCATED_N: LifecycleStatus.ALLOCATED,
    CountKind.TREATED_N: LifecycleStatus.TREATED,
    CountKind.OBSERVED_N: LifecycleStatus.OBSERVED,
    CountKind.EXCLUDED_N: LifecycleStatus.EXCLUDED,
    CountKind.ANALYSED_N: LifecycleStatus.ANALYSED,
}


def verify_block(
    block: ExperimentBlock,
    *,
    check_output_policy: bool = True,
    additional_violations: Iterable[GraphViolation] = (),
) -> HardVerificationResult:
    """Controlla invarianti strutturali, count, indipendenza e matrice output."""

    violations = [*additional_violations, *validate_experiment_block(block)]
    warnings: list[GraphViolation] = []

    for factor in block.factors:
        if factor.independently_assigned is TriState.TRUE:
            if factor.allocation_level is None:
                violations.append(
                    _violation(
                        "independence_without_allocation_unit",
                        f"factor {factor.id}: TRUE senza allocation_level",
                    )
                )
            if not factor.allocation_event_id and factor.provenance.origin not in {
                ProvenanceKind.USER,
                ProvenanceKind.ADJUDICATION,
            }:
                warnings.append(
                    _warning(
                        "independence_without_allocation_event",
                        f"factor {factor.id}: manca un allocation event esplicito",
                    )
                )
            if not factor.independence_evidence_ids and factor.provenance.origin not in {
                ProvenanceKind.USER,
                ProvenanceKind.ADJUDICATION,
            }:
                violations.append(
                    _violation(
                        "independence_without_evidence",
                        f"factor {factor.id}: TRUE senza evidence dedicata all'indipendenza",
                    )
                )

    for count in block.count_records:
        expected = _LIFECYCLE_BY_KIND.get(count.kind)
        if expected is not None and count.scope.lifecycle is not expected:
            violations.append(
                _violation(
                    "count_lifecycle_mismatch",
                    (
                        f"count {count.count_id}: {count.kind.value} richiede "
                        f"lifecycle={expected.value}"
                    ),
                )
            )
        if count.kind is CountKind.INDEPENDENT_N:
            count_factor = block.factor(count.scope.factor_id or "")
            if count_factor is None or count_factor.independently_assigned is not TriState.TRUE:
                violations.append(
                    _violation(
                        "independent_count_without_operational_independence",
                        f"count {count.count_id}: indipendenza operativa non confermata",
                    )
                )

    for assessment in block.unit_assessments:
        assessment_factor = block.factor(assessment.scope.factor_id or "")
        if assessment.n_independent is not None and (
            assessment_factor is None
            or assessment_factor.independently_assigned is not TriState.TRUE
        ):
            violations.append(
                _violation(
                    "single_n_without_operational_independence",
                    f"assessment {assessment.id}: n indipendente senza tri-state TRUE",
                )
            )

    if check_output_policy:
        for item in output_policy_violations(block):
            violations.append(_violation(item.code, item.message))

    unique_blocking = {
        (item.code, item.message, item.node_ids, item.relation_ids): item
        for item in violations
        if item.blocking
    }
    blocking = tuple(unique_blocking.values())
    nonblocking = tuple(item for item in violations if not item.blocking)
    warnings.extend(nonblocking)
    status = VerificationStatus.COMPLETE
    if blocking:
        status = VerificationStatus.FAILED
    elif warnings:
        status = VerificationStatus.PARTIAL
    if block.determinability is Determinability.INVALID_GRAPH and not blocking:
        warnings.append(
            _warning(
                "invalid_state_without_hard_violation",
                "INVALID_GRAPH dichiarato senza una violazione hard riproducibile",
            )
        )
        status = VerificationStatus.PARTIAL
    unique_warnings = {
        (item.code, item.message, item.node_ids, item.relation_ids): item for item in warnings
    }
    return HardVerificationResult(
        status=status,
        block_id=block.id,
        violations=blocking,
        warnings=tuple(unique_warnings.values()),
        checked_invariants=(
            "graph_referential_integrity",
            "operational_independence",
            "count_scope_and_lifecycle",
            "determinability_output_matrix",
        ),
    )


def _violation(code: str, message: str) -> GraphViolation:
    return GraphViolation(code=code, message=message, blocking=True)


def _warning(code: str, message: str) -> GraphViolation:
    return GraphViolation(code=code, message=message, blocking=False)
