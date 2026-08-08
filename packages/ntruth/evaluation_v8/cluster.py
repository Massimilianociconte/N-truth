"""Deterministic cluster-aware precision interfaces for PRD v8 §24.9."""

from __future__ import annotations

import hashlib
from decimal import Decimal, localcontext
from enum import StrEnum
from typing import Annotated, Self

from pydantic import Field, model_validator

from ntruth.schemas.core import content_checksum
from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.support import ScientificReviewRequirement

CLUSTER_PRECISION_REVIEW_ISSUE_ID = "SRR-V8-CLUSTER-PRECISION"
SUPPORTED_CLUSTER_BOOTSTRAP_METHOD = "cluster-bootstrap-sha256-v1"
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class GeneralizationUnitKind(StrEnum):
    EVIDENCE_SPAN = "EVIDENCE_SPAN"
    CLAIM = "CLAIM"
    DOCUMENT = "DOCUMENT"
    EXPERIMENT_BLOCK = "EXPERIMENT_BLOCK"
    STUDY_FAMILY = "STUDY_FAMILY"
    USER = "USER"
    LABORATORY_OR_FACILITY = "LABORATORY_OR_FACILITY"


class GeneralizationUnit(KernelModel):
    metric_id: NonBlankStr
    generalization_unit_id: NonBlankStr


class ClusterBootstrapProtocol(KernelModel):
    method_id: NonBlankStr
    seed: NonBlankStr
    iterations: int = Field(ge=2)
    confidence_level: Decimal = Field(gt=Decimal("0"), lt=Decimal("1"))

    @model_validator(mode="after")
    def _known_deterministic_method(self) -> Self:
        if self.method_id != SUPPORTED_CLUSTER_BOOTSTRAP_METHOD:
            raise ValueError("unknown or unreviewed deterministic cluster-bootstrap method")
        return self


class MetricGeneralizationContract(KernelModel):
    metric_id: NonBlankStr
    elementary_unit: GeneralizationUnitKind
    resampling_cluster: GeneralizationUnitKind
    stratification_variables: tuple[NonBlankStr, ...] = Field(min_length=1)
    cluster_estimator_id: NonBlankStr
    cluster_estimator_checksum: Sha256
    units: tuple[GeneralizationUnit, ...] = Field(min_length=1)
    bootstrap: ClusterBootstrapProtocol
    small_cluster_caveat: NonBlankStr

    @model_validator(mode="after")
    def _metric_specific_clusters(self) -> Self:
        if any(unit.metric_id != self.metric_id for unit in self.units):
            raise ValueError("generalization-unit IDs are metric-specific")
        unit_ids = [unit.generalization_unit_id for unit in self.units]
        if len(set(unit_ids)) != len(unit_ids):
            raise ValueError("generalization contract contains duplicate unit IDs")
        if self.elementary_unit is self.resampling_cluster:
            raise ValueError("elementary and resampling-cluster units must remain distinct")
        if len(set(self.stratification_variables)) != len(self.stratification_variables):
            raise ValueError("stratification variables contain duplicates")
        return self


class ClusterMetricEstimate(KernelModel):
    """One pre-aggregated metric contribution per resampling cluster."""

    metric_id: NonBlankStr
    generalization_unit_id: NonBlankStr
    estimate: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    evidence_ids: tuple[NonBlankStr, ...] = Field(min_length=1)


class PrecisionInterval(KernelModel):
    method_id: NonBlankStr
    confidence_level: Decimal
    point_estimate: Decimal
    lower: Decimal
    upper: Decimal

    @model_validator(mode="after")
    def _ordered_interval(self) -> Self:
        if not self.lower <= self.point_estimate <= self.upper:
            raise ValueError("cluster interval must contain its point estimate")
        return self


class ClusterPrecisionResult(KernelModel):
    result_id: NonBlankStr
    content_checksum: Sha256
    generalization_contract: MetricGeneralizationContract
    metric_id: NonBlankStr
    elementary_unit: GeneralizationUnitKind
    resampling_cluster: GeneralizationUnitKind
    declared_cluster_count: int = Field(ge=1)
    effective_cluster_count: int = Field(ge=1)
    interval: KnowledgeValue[PrecisionInterval]
    small_cluster_caveat: NonBlankStr
    blocker: ScientificReviewRequirement | None = None

    @model_validator(mode="after")
    def _blocked_xor_interval(self) -> Self:
        if (
            self.metric_id != self.generalization_contract.metric_id
            or self.elementary_unit is not self.generalization_contract.elementary_unit
            or self.resampling_cluster is not self.generalization_contract.resampling_cluster
            or self.declared_cluster_count != len(self.generalization_contract.units)
            or self.small_cluster_caveat != self.generalization_contract.small_cluster_caveat
        ):
            raise ValueError("cluster precision result differs from its pinned metric contract")
        if self.interval.knowledge_state is KnowledgeState.PRESENT:
            if self.blocker is not None:
                raise ValueError("computed precision cannot carry a missing-cluster blocker")
        elif self.blocker is None or self.blocker.issue_id != CLUSTER_PRECISION_REVIEW_ISSUE_ID:
            raise ValueError("unavailable cluster precision requires its explicit blocker")
        expected = content_checksum(
            self.model_dump(mode="json", exclude={"result_id", "content_checksum"})
        )
        if self.content_checksum != expected:
            raise ValueError("cluster precision result checksum mismatch")
        if self.result_id != f"CLUSTER-PRECISION-{expected[:20]}":
            raise ValueError("cluster precision result ID mismatch")
        return self


def _build_cluster_precision_result(
    contract: MetricGeneralizationContract,
    *,
    effective_cluster_count: int,
    interval: KnowledgeValue[PrecisionInterval],
    blocker: ScientificReviewRequirement | None = None,
) -> ClusterPrecisionResult:
    draft = ClusterPrecisionResult.model_construct(
        result_id="CLUSTER-PRECISION-PENDING",
        content_checksum="0" * 64,
        generalization_contract=contract,
        metric_id=contract.metric_id,
        elementary_unit=contract.elementary_unit,
        resampling_cluster=contract.resampling_cluster,
        declared_cluster_count=len(contract.units),
        effective_cluster_count=effective_cluster_count,
        interval=interval,
        small_cluster_caveat=contract.small_cluster_caveat,
        blocker=blocker,
    )
    checksum = content_checksum(
        draft.model_dump(mode="json", exclude={"result_id", "content_checksum"})
    )
    return ClusterPrecisionResult(
        result_id=f"CLUSTER-PRECISION-{checksum[:20]}",
        content_checksum=checksum,
        generalization_contract=contract,
        metric_id=contract.metric_id,
        elementary_unit=contract.elementary_unit,
        resampling_cluster=contract.resampling_cluster,
        declared_cluster_count=len(contract.units),
        effective_cluster_count=effective_cluster_count,
        interval=interval,
        small_cluster_caveat=contract.small_cluster_caveat,
        blocker=blocker,
    )


def _draw_index(*, seed: str, iteration: int, draw: int, cluster_count: int) -> int:
    payload = f"{seed}\0{iteration}\0{draw}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") % cluster_count


def _quantile(values: list[Decimal], probability: Decimal) -> Decimal:
    """Deterministic linear interpolation on the sorted bootstrap distribution."""

    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    with localcontext() as context:
        context.prec = 40
        position = probability * Decimal(len(ordered) - 1)
        lower_index = int(position)
        upper_index = min(lower_index + 1, len(ordered) - 1)
        weight = position - Decimal(lower_index)
        return ordered[lower_index] + (ordered[upper_index] - ordered[lower_index]) * weight


def cluster_bootstrap_precision(
    contract: MetricGeneralizationContract,
    estimates: tuple[ClusterMetricEstimate, ...],
) -> ClusterPrecisionResult:
    """Resample cluster estimates, ignoring exact duplicate rows by cluster ID.

    The interface deliberately accepts pre-aggregated cluster contributions.
    Repeating item rows inside a cluster therefore cannot increase the effective
    sample size or narrow the resulting interval.
    """

    by_cluster: dict[str, ClusterMetricEstimate] = {}
    for estimate in estimates:
        if estimate.metric_id != contract.metric_id:
            raise ValueError("cluster estimate belongs to another metric")
        previous = by_cluster.get(estimate.generalization_unit_id)
        if previous is None:
            by_cluster[estimate.generalization_unit_id] = estimate
        elif previous != estimate:
            raise ValueError("conflicting duplicate cluster estimate")
    declared_ids = {unit.generalization_unit_id for unit in contract.units}
    if set(by_cluster) != declared_ids:
        missing = sorted(declared_ids - set(by_cluster))
        unexpected = sorted(set(by_cluster) - declared_ids)
        raise ValueError(
            f"cluster estimates do not close the metric contract; missing={missing}, "
            f"unexpected={unexpected}"
        )
    ordered_estimates = [by_cluster[unit.generalization_unit_id] for unit in contract.units]
    values = [estimate.estimate for estimate in ordered_estimates]
    evidence_ids = tuple(
        sorted(
            {evidence_id for estimate in ordered_estimates for evidence_id in estimate.evidence_ids}
        )
    )
    cluster_count = len(values)
    if cluster_count < 2:
        rationale = (
            "A single resampling cluster has no empirical between-cluster distribution; "
            "precision and generalization remain unestimated."
        )
        return _build_cluster_precision_result(
            contract,
            effective_cluster_count=cluster_count,
            interval=KnowledgeValue[PrecisionInterval](
                knowledge_state=KnowledgeState.UNKNOWN,
                rationale=rationale,
                query_scope_id=contract.metric_id,
            ),
            blocker=ScientificReviewRequirement(
                issue_id=CLUSTER_PRECISION_REVIEW_ISSUE_ID,
                rationale=rationale,
            ),
        )
    with localcontext() as context:
        context.prec = 40
        denominator = Decimal(cluster_count)
        point_estimate = sum(values, Decimal("0")) / denominator
        bootstrap_estimates = [
            sum(
                (
                    values[
                        _draw_index(
                            seed=contract.bootstrap.seed,
                            iteration=iteration,
                            draw=draw,
                            cluster_count=cluster_count,
                        )
                    ]
                    for draw in range(cluster_count)
                ),
                Decimal("0"),
            )
            / denominator
            for iteration in range(contract.bootstrap.iterations)
        ]
        alpha = (Decimal("1") - contract.bootstrap.confidence_level) / Decimal("2")
        lower = _quantile(bootstrap_estimates, alpha)
        upper = _quantile(bootstrap_estimates, Decimal("1") - alpha)
        # Finite deterministic bootstrap draws need not bracket the exact sample mean.
        lower = min(lower, point_estimate)
        upper = max(upper, point_estimate)
    interval = PrecisionInterval(
        method_id=contract.bootstrap.method_id,
        confidence_level=contract.bootstrap.confidence_level,
        point_estimate=point_estimate,
        lower=lower,
        upper=upper,
    )
    return _build_cluster_precision_result(
        contract,
        effective_cluster_count=cluster_count,
        interval=KnowledgeValue[PrecisionInterval](
            knowledge_state=KnowledgeState.PRESENT,
            value=interval,
            evidence_ids=evidence_ids,
            query_scope_id=contract.metric_id,
        ),
    )


__all__ = [
    "CLUSTER_PRECISION_REVIEW_ISSUE_ID",
    "SUPPORTED_CLUSTER_BOOTSTRAP_METHOD",
    "ClusterBootstrapProtocol",
    "ClusterMetricEstimate",
    "ClusterPrecisionResult",
    "GeneralizationUnit",
    "GeneralizationUnitKind",
    "MetricGeneralizationContract",
    "PrecisionInterval",
    "cluster_bootstrap_precision",
]
