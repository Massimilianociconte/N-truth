"""Deterministic cluster-aware precision interfaces for PRD v8 §24.9."""

from __future__ import annotations

import hashlib
from decimal import Decimal, localcontext
from enum import StrEnum
from typing import Annotated, Self

from pydantic import Field, model_validator

from ntruth.evaluation_v8.models import EVALUATION_SCIENTIFIC_HOLD_ISSUE_ID
from ntruth.schemas.core import content_checksum
from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.support import ScientificReviewRequirement

CLUSTER_PRECISION_REVIEW_ISSUE_ID = "SRR-V8-CLUSTER-PRECISION"
SUPPORTED_CLUSTER_BOOTSTRAP_METHOD = "cluster-bootstrap-sha256-v1"
SUPPORTED_CLUSTER_ESTIMATOR_ID = "cluster-mean-by-stratum-v1"
SUPPORTED_CLUSTER_ESTIMATOR_CHECKSUM = content_checksum(
    {
        "estimator_id": SUPPORTED_CLUSTER_ESTIMATOR_ID,
        "elementary_aggregation": "arithmetic mean within each declared resampling cluster",
        "resampling_weight": "one equal contribution per resampled cluster",
        "stratification": "resample clusters independently within exact declared strata",
    }
)
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
        if (
            self.cluster_estimator_id != SUPPORTED_CLUSTER_ESTIMATOR_ID
            or self.cluster_estimator_checksum != SUPPORTED_CLUSTER_ESTIMATOR_CHECKSUM
        ):
            raise ValueError("unknown or unreviewed deterministic cluster estimator")
        if len(set(self.stratification_variables)) != len(self.stratification_variables):
            raise ValueError("stratification variables contain duplicates")
        return self


class ClusterMetricEstimate(KernelModel):
    """One pre-aggregated metric contribution per resampling cluster."""

    metric_id: NonBlankStr
    generalization_unit_id: NonBlankStr
    estimate: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    evidence_ids: tuple[NonBlankStr, ...] = Field(min_length=1)
    stratum_values: dict[NonBlankStr, NonBlankStr]


class ClusterMetricObservation(KernelModel):
    metric_id: NonBlankStr
    observation_id: NonBlankStr
    generalization_unit_id: NonBlankStr
    value: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    stratum_values: dict[NonBlankStr, NonBlankStr]
    evidence_ids: tuple[NonBlankStr, ...] = Field(min_length=1)


class ClusterObservationManifest(KernelModel):
    manifest_id: NonBlankStr
    content_checksum: Sha256
    metric_id: NonBlankStr
    estimator_id: NonBlankStr
    estimator_checksum: Sha256
    stratification_variables: tuple[NonBlankStr, ...]
    observations: tuple[ClusterMetricObservation, ...] = Field(min_length=1)
    cluster_estimates: tuple[ClusterMetricEstimate, ...] = Field(min_length=1)
    observation_count: int = Field(ge=1)
    cluster_count: int = Field(ge=1)

    @model_validator(mode="after")
    def _derived_and_content_addressed(self) -> Self:
        observation_ids = [item.observation_id for item in self.observations]
        if len(set(observation_ids)) != len(observation_ids):
            raise ValueError("cluster observation manifest contains duplicate observation IDs")
        cluster_ids = [item.generalization_unit_id for item in self.cluster_estimates]
        if len(set(cluster_ids)) != len(cluster_ids):
            raise ValueError("cluster observation manifest contains duplicate cluster estimates")
        if self.observation_count != len(self.observations) or self.cluster_count != len(
            self.cluster_estimates
        ):
            raise ValueError("cluster observation manifest count mismatch")
        if {item.generalization_unit_id for item in self.observations} != set(cluster_ids):
            raise ValueError("cluster observations and estimates have different cluster membership")
        expected_strata = set(self.stratification_variables)
        if any(set(item.stratum_values) != expected_strata for item in self.observations):
            raise ValueError("cluster observation has incomplete or unexpected strata")
        if any(set(item.stratum_values) != expected_strata for item in self.cluster_estimates):
            raise ValueError("cluster estimate has incomplete or unexpected strata")
        observations_by_cluster = {
            cluster_id: [
                item for item in self.observations if item.generalization_unit_id == cluster_id
            ]
            for cluster_id in cluster_ids
        }
        for estimate in self.cluster_estimates:
            rows = observations_by_cluster[estimate.generalization_unit_id]
            if not rows:
                raise ValueError("cluster estimate has no elementary observations")
            if any(row.metric_id != self.metric_id for row in rows):
                raise ValueError("cluster observation belongs to another metric")
            if any(row.stratum_values != estimate.stratum_values for row in rows):
                raise ValueError("one cluster crosses declared strata")
            expected_estimate = sum((row.value for row in rows), Decimal("0")) / Decimal(len(rows))
            expected_evidence = tuple(
                sorted({evidence_id for row in rows for evidence_id in row.evidence_ids})
            )
            if estimate.estimate != expected_estimate or estimate.evidence_ids != expected_evidence:
                raise ValueError("cluster estimate differs from sealed elementary observations")
        expected = content_checksum(
            self.model_dump(mode="json", exclude={"manifest_id", "content_checksum"})
        )
        if self.content_checksum != expected:
            raise ValueError("cluster observation manifest checksum mismatch")
        if self.manifest_id != f"CLUSTER-OBSERVATIONS-{expected[:20]}":
            raise ValueError("cluster observation manifest ID mismatch")
        return self


class PrecisionInterval(KernelModel):
    method_id: NonBlankStr
    confidence_level: Decimal
    point_estimate: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    lower: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    upper: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))

    @model_validator(mode="after")
    def _ordered_interval(self) -> Self:
        if not self.lower <= self.point_estimate <= self.upper:
            raise ValueError("cluster interval must contain its point estimate")
        return self


class ClusterPrecisionResult(KernelModel):
    result_id: NonBlankStr
    content_checksum: Sha256
    generalization_contract: MetricGeneralizationContract
    input_manifest: ClusterObservationManifest
    metric_id: NonBlankStr
    elementary_unit: GeneralizationUnitKind
    resampling_cluster: GeneralizationUnitKind
    declared_cluster_count: int = Field(ge=1)
    effective_cluster_count: int = Field(ge=1)
    interval: KnowledgeValue[PrecisionInterval]
    small_cluster_caveat: NonBlankStr
    scientific_use_permitted: bool = False
    blockers: tuple[ScientificReviewRequirement, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _blocked_xor_interval(self) -> Self:
        if (
            self.metric_id != self.generalization_contract.metric_id
            or self.elementary_unit is not self.generalization_contract.elementary_unit
            or self.resampling_cluster is not self.generalization_contract.resampling_cluster
            or self.declared_cluster_count != len(self.generalization_contract.units)
            or self.small_cluster_caveat != self.generalization_contract.small_cluster_caveat
            or self.input_manifest.metric_id != self.metric_id
            or self.input_manifest.estimator_id != self.generalization_contract.cluster_estimator_id
            or self.input_manifest.estimator_checksum
            != self.generalization_contract.cluster_estimator_checksum
            or self.input_manifest.stratification_variables
            != self.generalization_contract.stratification_variables
            or self.effective_cluster_count != self.input_manifest.cluster_count
        ):
            raise ValueError("cluster precision result differs from its pinned metric contract")
        if self.interval.query_scope_id != self.metric_id:
            raise ValueError("cluster precision interval has the wrong metric scope")
        if self.scientific_use_permitted:
            raise ValueError("cluster precision result is not a scientific release authority")
        blocker_ids = {item.issue_id for item in self.blockers}
        if EVALUATION_SCIENTIFIC_HOLD_ISSUE_ID not in blocker_ids:
            raise ValueError("cluster precision result must retain the scientific HOLD")
        if self.interval.knowledge_state is KnowledgeState.PRESENT:
            if CLUSTER_PRECISION_REVIEW_ISSUE_ID in blocker_ids:
                raise ValueError("computed precision cannot carry a missing-cluster blocker")
        elif CLUSTER_PRECISION_REVIEW_ISSUE_ID not in blocker_ids:
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
    input_manifest: ClusterObservationManifest,
    effective_cluster_count: int,
    interval: KnowledgeValue[PrecisionInterval],
    unavailable_blocker: ScientificReviewRequirement | None = None,
) -> ClusterPrecisionResult:
    blockers = (
        ScientificReviewRequirement(
            issue_id=EVALUATION_SCIENTIFIC_HOLD_ISSUE_ID,
            rationale=(
                "A deterministic precision interval is not a release decision; governed metric "
                "provenance, reference stability, burden and a policy-pinned decision remain required."
            ),
        ),
        *((unavailable_blocker,) if unavailable_blocker is not None else ()),
    )
    draft = ClusterPrecisionResult.model_construct(
        result_id="CLUSTER-PRECISION-PENDING",
        content_checksum="0" * 64,
        generalization_contract=contract,
        input_manifest=input_manifest,
        metric_id=contract.metric_id,
        elementary_unit=contract.elementary_unit,
        resampling_cluster=contract.resampling_cluster,
        declared_cluster_count=len(contract.units),
        effective_cluster_count=effective_cluster_count,
        interval=interval,
        small_cluster_caveat=contract.small_cluster_caveat,
        scientific_use_permitted=False,
        blockers=blockers,
    )
    checksum = content_checksum(
        draft.model_dump(mode="json", exclude={"result_id", "content_checksum"})
    )
    return ClusterPrecisionResult(
        result_id=f"CLUSTER-PRECISION-{checksum[:20]}",
        content_checksum=checksum,
        generalization_contract=contract,
        input_manifest=input_manifest,
        metric_id=contract.metric_id,
        elementary_unit=contract.elementary_unit,
        resampling_cluster=contract.resampling_cluster,
        declared_cluster_count=len(contract.units),
        effective_cluster_count=effective_cluster_count,
        interval=interval,
        small_cluster_caveat=contract.small_cluster_caveat,
        scientific_use_permitted=False,
        blockers=blockers,
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


def _build_observation_manifest(
    contract: MetricGeneralizationContract,
    observations: tuple[ClusterMetricObservation, ...],
) -> ClusterObservationManifest:
    by_observation_id: dict[str, ClusterMetricObservation] = {}
    for observation in observations:
        if observation.metric_id != contract.metric_id:
            raise ValueError("cluster observation belongs to another metric")
        if set(observation.stratum_values) != set(contract.stratification_variables):
            raise ValueError("cluster observation has incomplete or unexpected strata")
        previous = by_observation_id.get(observation.observation_id)
        if previous is None:
            by_observation_id[observation.observation_id] = observation
        elif previous != observation:
            raise ValueError("conflicting duplicate cluster observation")
    declared_ids = {unit.generalization_unit_id for unit in contract.units}
    observed_cluster_ids = {
        observation.generalization_unit_id for observation in by_observation_id.values()
    }
    if observed_cluster_ids != declared_ids:
        missing = sorted(declared_ids - observed_cluster_ids)
        unexpected = sorted(observed_cluster_ids - declared_ids)
        raise ValueError(
            f"cluster observations do not close the metric contract; missing={missing}, "
            f"unexpected={unexpected}"
        )
    unit_order = {unit.generalization_unit_id: index for index, unit in enumerate(contract.units)}
    ordered_observations = tuple(
        sorted(
            by_observation_id.values(),
            key=lambda item: (unit_order[item.generalization_unit_id], item.observation_id),
        )
    )
    estimates: list[ClusterMetricEstimate] = []
    for unit in contract.units:
        rows = [
            item
            for item in ordered_observations
            if item.generalization_unit_id == unit.generalization_unit_id
        ]
        stratum_values = rows[0].stratum_values
        if any(row.stratum_values != stratum_values for row in rows):
            raise ValueError("one resampling cluster crosses declared strata")
        estimates.append(
            ClusterMetricEstimate(
                metric_id=contract.metric_id,
                generalization_unit_id=unit.generalization_unit_id,
                estimate=sum((row.value for row in rows), Decimal("0")) / Decimal(len(rows)),
                evidence_ids=tuple(
                    sorted({evidence_id for row in rows for evidence_id in row.evidence_ids})
                ),
                stratum_values=stratum_values,
            )
        )
    cluster_estimates = tuple(estimates)
    draft = ClusterObservationManifest.model_construct(
        manifest_id="CLUSTER-OBSERVATIONS-PENDING",
        content_checksum="0" * 64,
        metric_id=contract.metric_id,
        estimator_id=contract.cluster_estimator_id,
        estimator_checksum=contract.cluster_estimator_checksum,
        stratification_variables=contract.stratification_variables,
        observations=ordered_observations,
        cluster_estimates=cluster_estimates,
        observation_count=len(ordered_observations),
        cluster_count=len(cluster_estimates),
    )
    checksum = content_checksum(
        draft.model_dump(mode="json", exclude={"manifest_id", "content_checksum"})
    )
    return ClusterObservationManifest(
        manifest_id=f"CLUSTER-OBSERVATIONS-{checksum[:20]}",
        content_checksum=checksum,
        metric_id=contract.metric_id,
        estimator_id=contract.cluster_estimator_id,
        estimator_checksum=contract.cluster_estimator_checksum,
        stratification_variables=contract.stratification_variables,
        observations=ordered_observations,
        cluster_estimates=cluster_estimates,
        observation_count=len(ordered_observations),
        cluster_count=len(cluster_estimates),
    )


def cluster_bootstrap_precision(
    contract: MetricGeneralizationContract,
    observations: tuple[ClusterMetricObservation, ...],
) -> ClusterPrecisionResult:
    """Aggregate sealed elementary rows, then resample clusters within exact strata."""

    input_manifest = _build_observation_manifest(contract, observations)
    ordered_estimates = list(input_manifest.cluster_estimates)
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
            input_manifest=input_manifest,
            effective_cluster_count=cluster_count,
            interval=KnowledgeValue[PrecisionInterval](
                knowledge_state=KnowledgeState.UNKNOWN,
                rationale=rationale,
                query_scope_id=contract.metric_id,
            ),
            unavailable_blocker=ScientificReviewRequirement(
                issue_id=CLUSTER_PRECISION_REVIEW_ISSUE_ID,
                rationale=rationale,
            ),
        )
    with localcontext() as context:
        context.prec = 40
        denominator = Decimal(cluster_count)
        point_estimate = sum(values, Decimal("0")) / denominator
        estimates_by_stratum: dict[tuple[str, ...], list[ClusterMetricEstimate]] = {}
        for estimate in ordered_estimates:
            key = tuple(
                estimate.stratum_values[variable] for variable in contract.stratification_variables
            )
            estimates_by_stratum.setdefault(key, []).append(estimate)
        bootstrap_estimates = [
            sum(
                (
                    stratum_estimates[
                        _draw_index(
                            seed=f"{contract.bootstrap.seed}\0{stratum_key!r}",
                            iteration=iteration,
                            draw=draw,
                            cluster_count=len(stratum_estimates),
                        )
                    ].estimate
                    for stratum_key, stratum_estimates in sorted(estimates_by_stratum.items())
                    for draw in range(len(stratum_estimates))
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
        input_manifest=input_manifest,
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
    "SUPPORTED_CLUSTER_ESTIMATOR_CHECKSUM",
    "SUPPORTED_CLUSTER_ESTIMATOR_ID",
    "ClusterBootstrapProtocol",
    "ClusterMetricEstimate",
    "ClusterMetricObservation",
    "ClusterObservationManifest",
    "ClusterPrecisionResult",
    "GeneralizationUnit",
    "GeneralizationUnitKind",
    "MetricGeneralizationContract",
    "PrecisionInterval",
    "cluster_bootstrap_precision",
]
