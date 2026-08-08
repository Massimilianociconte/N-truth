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


class ClusterEvidenceRecord(KernelModel):
    """Content and custody address for one independently resolved evidence record."""

    evidence_record_id: NonBlankStr
    evidence_content_checksum: Sha256
    custody_record_id: NonBlankStr
    custody_record_checksum: Sha256
    record_checksum: Sha256

    @model_validator(mode="after")
    def _content_addressed(self) -> Self:
        expected = content_checksum(self.model_dump(mode="json", exclude={"record_checksum"}))
        if self.record_checksum != expected:
            raise ValueError("cluster evidence record checksum mismatch")
        return self


class ClusterEvidenceReference(KernelModel):
    evidence_record_id: NonBlankStr
    record_checksum: Sha256


class ClusterEvidenceLedger(KernelModel):
    ledger_id: NonBlankStr
    content_checksum: Sha256
    records: tuple[ClusterEvidenceRecord, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _content_addressed(self) -> Self:
        record_ids = tuple(item.evidence_record_id for item in self.records)
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("cluster evidence ledger contains duplicate record IDs")
        expected = content_checksum(
            self.model_dump(mode="json", exclude={"ledger_id", "content_checksum"})
        )
        if self.content_checksum != expected:
            raise ValueError("cluster evidence ledger checksum mismatch")
        if self.ledger_id != f"CLUSTER-EVIDENCE-{expected[:20]}":
            raise ValueError("cluster evidence ledger ID mismatch")
        return self


class ClusterStratumAssignment(KernelModel):
    generalization_unit_id: NonBlankStr
    stratum_values: dict[NonBlankStr, NonBlankStr]


class MetricGeneralizationContractArtifact(KernelModel):
    """Separately reviewed and content-addressed metric preregistration artifact."""

    artifact_id: NonBlankStr
    content_checksum: Sha256
    contract: MetricGeneralizationContract
    cluster_strata: tuple[ClusterStratumAssignment, ...] = Field(min_length=1)
    preregistration_evidence_records: tuple[ClusterEvidenceReference, ...] = Field(min_length=1)
    custody_evidence_records: tuple[ClusterEvidenceReference, ...] = Field(min_length=1)
    review_evidence_records: tuple[ClusterEvidenceReference, ...] = Field(min_length=1)
    reviewer_actor_ids: tuple[NonBlankStr, ...] = Field(min_length=2)
    review_scope_id: NonBlankStr

    @model_validator(mode="after")
    def _reviewed_and_content_addressed(self) -> Self:
        reviewer_ids = tuple(self.reviewer_actor_ids)
        if len(reviewer_ids) != len(set(reviewer_ids)):
            raise ValueError("cluster contract reviewers must be distinct")
        expected_cluster_ids = tuple(unit.generalization_unit_id for unit in self.contract.units)
        actual_cluster_ids = tuple(item.generalization_unit_id for item in self.cluster_strata)
        if actual_cluster_ids != expected_cluster_ids:
            raise ValueError("cluster strata differ from the declared contract unit order")
        expected_variables = set(self.contract.stratification_variables)
        if any(set(item.stratum_values) != expected_variables for item in self.cluster_strata):
            raise ValueError("cluster stratum assignment differs from declared variables")
        all_references = (
            *self.preregistration_evidence_records,
            *self.custody_evidence_records,
            *self.review_evidence_records,
        )
        reference_keys = tuple(
            (item.evidence_record_id, item.record_checksum) for item in all_references
        )
        if len(reference_keys) != len(set(reference_keys)):
            raise ValueError("cluster contract authority evidence references must be distinct")
        expected = content_checksum(
            self.model_dump(mode="json", exclude={"artifact_id", "content_checksum"})
        )
        if self.content_checksum != expected:
            raise ValueError("cluster metric contract artifact checksum mismatch")
        if self.artifact_id != f"CLUSTER-CONTRACT-{expected[:20]}":
            raise ValueError("cluster metric contract artifact ID mismatch")
        return self


class ClusterElementarySourceRecord(KernelModel):
    """Reviewed elementary row resolved independently of a metric observation."""

    source_record_id: NonBlankStr
    content_checksum: Sha256
    metric_id: NonBlankStr
    generalization_unit_id: NonBlankStr
    value: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    stratum_values: dict[NonBlankStr, NonBlankStr]
    evidence_records: tuple[ClusterEvidenceReference, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _content_addressed(self) -> Self:
        evidence_keys = tuple(
            (item.evidence_record_id, item.record_checksum) for item in self.evidence_records
        )
        if len(evidence_keys) != len(set(evidence_keys)):
            raise ValueError("cluster elementary source contains duplicate evidence references")
        expected = cluster_elementary_source_checksum(
            metric_id=self.metric_id,
            elementary_source_id=self.source_record_id,
            generalization_unit_id=self.generalization_unit_id,
            value=self.value,
            stratum_values=self.stratum_values,
        )
        if self.content_checksum != expected:
            raise ValueError("cluster elementary source record checksum mismatch")
        return self


class ClusterElementarySourceLedger(KernelModel):
    ledger_id: NonBlankStr
    content_checksum: Sha256
    contract_artifact_id: NonBlankStr
    contract_artifact_checksum: Sha256
    records: tuple[ClusterElementarySourceRecord, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _content_addressed(self) -> Self:
        source_ids = tuple(item.source_record_id for item in self.records)
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("cluster source ledger contains duplicate source records")
        expected = content_checksum(
            self.model_dump(mode="json", exclude={"ledger_id", "content_checksum"})
        )
        if self.content_checksum != expected:
            raise ValueError("cluster source ledger checksum mismatch")
        if self.ledger_id != f"CLUSTER-SOURCES-{expected[:20]}":
            raise ValueError("cluster source ledger ID mismatch")
        return self


class ClusterPrecisionAuthorityRegistry(KernelModel):
    registry_id: NonBlankStr
    content_checksum: Sha256
    contract_artifact: MetricGeneralizationContractArtifact
    source_ledger: ClusterElementarySourceLedger
    evidence_ledger: ClusterEvidenceLedger

    @model_validator(mode="after")
    def _closed_and_content_addressed(self) -> Self:
        artifact = self.contract_artifact
        if (
            self.source_ledger.contract_artifact_id != artifact.artifact_id
            or self.source_ledger.contract_artifact_checksum != artifact.content_checksum
        ):
            raise ValueError("cluster source ledger differs from its contract artifact")
        strata_by_cluster = {
            item.generalization_unit_id: item.stratum_values for item in artifact.cluster_strata
        }
        source_cluster_ids = {item.generalization_unit_id for item in self.source_ledger.records}
        if source_cluster_ids != set(strata_by_cluster):
            raise ValueError("cluster source ledger does not cover the declared contract units")
        for source in self.source_ledger.records:
            if source.metric_id != artifact.contract.metric_id:
                raise ValueError("cluster source ledger contains a different metric")
            if source.stratum_values != strata_by_cluster.get(source.generalization_unit_id):
                raise ValueError("cluster source ledger differs from preregistered strata")
        evidence_by_id = {item.evidence_record_id: item for item in self.evidence_ledger.records}
        required_references = (
            *artifact.preregistration_evidence_records,
            *artifact.custody_evidence_records,
            *artifact.review_evidence_records,
            *(
                reference
                for source in self.source_ledger.records
                for reference in source.evidence_records
            ),
        )
        required_ids = {item.evidence_record_id for item in required_references}
        if required_ids != set(evidence_by_id):
            raise ValueError("cluster authority evidence ledger is not exactly closed")
        for reference in required_references:
            resolved = evidence_by_id.get(reference.evidence_record_id)
            if resolved is None or resolved.record_checksum != reference.record_checksum:
                raise ValueError("cluster authority evidence checksum cannot be resolved")
        expected = content_checksum(
            self.model_dump(mode="json", exclude={"registry_id", "content_checksum"})
        )
        if self.content_checksum != expected:
            raise ValueError("cluster precision authority registry checksum mismatch")
        if self.registry_id != f"CLUSTER-AUTHORITY-{expected[:20]}":
            raise ValueError("cluster precision authority registry ID mismatch")
        return self


class ClusterPrecisionAuthorityPin(KernelModel):
    """Pin supplied by the governed configuration, separately from the registry."""

    registry_id: NonBlankStr
    registry_checksum: Sha256


class ClusterPrecisionAuthorityResolution(KernelModel):
    resolution_id: NonBlankStr
    content_checksum: Sha256
    registry: ClusterPrecisionAuthorityRegistry
    pin: ClusterPrecisionAuthorityPin

    @model_validator(mode="after")
    def _pinned_and_content_addressed(self) -> Self:
        if (
            self.pin.registry_id != self.registry.registry_id
            or self.pin.registry_checksum != self.registry.content_checksum
        ):
            raise ValueError("cluster authority registry differs from its external pin")
        expected = content_checksum(
            self.model_dump(mode="json", exclude={"resolution_id", "content_checksum"})
        )
        if self.content_checksum != expected:
            raise ValueError("cluster authority resolution checksum mismatch")
        if self.resolution_id != f"CLUSTER-AUTHORITY-RESOLUTION-{expected[:20]}":
            raise ValueError("cluster authority resolution ID mismatch")
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
    elementary_source_id: NonBlankStr
    elementary_source_checksum: Sha256
    generalization_unit_id: NonBlankStr
    value: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    stratum_values: dict[NonBlankStr, NonBlankStr]
    evidence_ids: tuple[NonBlankStr, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _locally_content_addressed_observation_declaration(self) -> Self:
        expected = cluster_elementary_source_checksum(
            metric_id=self.metric_id,
            elementary_source_id=self.elementary_source_id,
            generalization_unit_id=self.generalization_unit_id,
            value=self.value,
            stratum_values=self.stratum_values,
        )
        if self.elementary_source_checksum != expected:
            raise ValueError("cluster elementary source checksum mismatch")
        if self.observation_id != f"CLUSTER-OBSERVATION-{expected[:20]}":
            raise ValueError("cluster observation ID differs from its elementary source")
        return self


class ClusterObservationManifest(KernelModel):
    manifest_id: NonBlankStr
    content_checksum: Sha256
    metric_id: NonBlankStr
    estimator_id: NonBlankStr
    estimator_checksum: Sha256
    stratification_variables: tuple[NonBlankStr, ...]
    evidence_ids: tuple[NonBlankStr, ...] = Field(min_length=1)
    observations: tuple[ClusterMetricObservation, ...] = Field(min_length=1)
    cluster_estimates: tuple[ClusterMetricEstimate, ...] = Field(min_length=1)
    observation_count: int = Field(ge=1)
    cluster_count: int = Field(ge=1)

    @model_validator(mode="after")
    def _derived_and_content_addressed(self) -> Self:
        observation_ids = [item.observation_id for item in self.observations]
        if len(set(observation_ids)) != len(observation_ids):
            raise ValueError("cluster observation manifest contains duplicate observation IDs")
        source_ids = [item.elementary_source_id for item in self.observations]
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("cluster observation manifest contains a semantic duplicate source")
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
        expected_evidence = tuple(
            sorted(
                {
                    evidence_id
                    for observation in self.observations
                    for evidence_id in observation.evidence_ids
                }
            )
        )
        if self.evidence_ids != expected_evidence:
            raise ValueError("cluster manifest evidence inputs are not exactly closed")
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
            if estimate.metric_id != self.metric_id:
                raise ValueError("cluster estimate belongs to another metric")
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
    authority_resolution: KnowledgeValue[ClusterPrecisionAuthorityResolution]
    interval: KnowledgeValue[PrecisionInterval]
    small_cluster_caveat: NonBlankStr
    scientific_use_permitted: bool = False
    blockers: tuple[ScientificReviewRequirement, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _blocked_xor_interval(self) -> Self:
        declared_cluster_ids = tuple(
            unit.generalization_unit_id for unit in self.generalization_contract.units
        )
        manifest_cluster_ids = tuple(
            estimate.generalization_unit_id for estimate in self.input_manifest.cluster_estimates
        )
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
            or manifest_cluster_ids != declared_cluster_ids
        ):
            raise ValueError("cluster precision result differs from its pinned metric contract")
        if self.interval.query_scope_id != self.metric_id:
            raise ValueError("cluster precision interval has the wrong metric scope")
        if self.authority_resolution.query_scope_id != self.metric_id:
            raise ValueError("cluster precision authority has the wrong metric scope")
        if self.authority_resolution.knowledge_state is KnowledgeState.PRESENT:
            resolution = self.authority_resolution.value
            if resolution is None:
                raise ValueError("PRESENT cluster authority has no resolved value")
            _validate_resolved_authority(
                self.generalization_contract,
                self.input_manifest,
                resolution,
            )
            expected_interval = _expected_interval(
                self.generalization_contract,
                self.input_manifest,
            )
        elif self.authority_resolution.knowledge_state is KnowledgeState.UNKNOWN:
            if self.authority_resolution != _unresolved_authority_value(self.metric_id):
                raise ValueError("unresolved cluster authority must retain canonical semantics")
            expected_interval = _unresolved_authority_interval(self.metric_id)
        else:
            raise ValueError("cluster precision authority must be PRESENT or UNKNOWN")
        if self.interval != expected_interval:
            raise ValueError("cluster precision interval differs from sealed inputs")
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
    authority_resolution: KnowledgeValue[ClusterPrecisionAuthorityResolution],
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
        authority_resolution=authority_resolution,
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
        authority_resolution=authority_resolution,
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
        observation = ClusterMetricObservation.model_validate(observation.model_dump(mode="python"))
        if observation.metric_id != contract.metric_id:
            raise ValueError("cluster observation belongs to another metric")
        if set(observation.stratum_values) != set(contract.stratification_variables):
            raise ValueError("cluster observation has incomplete or unexpected strata")
        previous = by_observation_id.get(observation.observation_id)
        if previous is None:
            by_observation_id[observation.observation_id] = observation
        elif previous != observation:
            raise ValueError("conflicting duplicate cluster observation")
    by_elementary_source: dict[str, ClusterMetricObservation] = {}
    for observation in by_observation_id.values():
        previous = by_elementary_source.get(observation.elementary_source_id)
        if previous is not None and previous != observation:
            raise ValueError("conflicting duplicate cluster elementary source")
        by_elementary_source[observation.elementary_source_id] = observation
    canonical_observations = tuple(by_elementary_source.values())
    declared_ids = {unit.generalization_unit_id for unit in contract.units}
    observed_cluster_ids = {
        observation.generalization_unit_id for observation in canonical_observations
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
            canonical_observations,
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
        evidence_ids=tuple(
            sorted(
                {
                    evidence_id
                    for observation in ordered_observations
                    for evidence_id in observation.evidence_ids
                }
            )
        ),
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
        evidence_ids=tuple(
            sorted(
                {
                    evidence_id
                    for observation in ordered_observations
                    for evidence_id in observation.evidence_ids
                }
            )
        ),
        observations=ordered_observations,
        cluster_estimates=cluster_estimates,
        observation_count=len(ordered_observations),
        cluster_count=len(cluster_estimates),
    )


def _unresolved_authority_interval(metric_id: str) -> KnowledgeValue[PrecisionInterval]:
    return KnowledgeValue[PrecisionInterval](
        knowledge_state=KnowledgeState.UNKNOWN,
        rationale=(
            "Cluster precision requires a separately pinned, independently reviewed metric "
            "contract plus exact source and evidence ledgers. Caller-authored observations "
            "cannot establish those identities."
        ),
        query_scope_id=metric_id,
    )


def _unresolved_authority_value(
    metric_id: str,
) -> KnowledgeValue[ClusterPrecisionAuthorityResolution]:
    return KnowledgeValue[ClusterPrecisionAuthorityResolution](
        knowledge_state=KnowledgeState.UNKNOWN,
        rationale=(
            "No externally pinned cluster-precision authority registry was resolved for this "
            "metric."
        ),
        query_scope_id=metric_id,
    )


def _authority_evidence_ids(
    resolution: ClusterPrecisionAuthorityResolution,
) -> tuple[str, ...]:
    artifact = resolution.registry.contract_artifact
    return tuple(
        sorted(
            {
                item.evidence_record_id
                for item in (
                    *artifact.preregistration_evidence_records,
                    *artifact.custody_evidence_records,
                    *artifact.review_evidence_records,
                )
            }
        )
    )


def _validate_resolved_authority(
    contract: MetricGeneralizationContract,
    manifest: ClusterObservationManifest,
    resolution: ClusterPrecisionAuthorityResolution,
) -> None:
    checked = ClusterPrecisionAuthorityResolution.model_validate(
        resolution.model_dump(mode="python")
    )
    registry = checked.registry
    artifact = registry.contract_artifact
    if artifact.contract != contract:
        raise ValueError("metric contract differs from the resolved contract artifact")

    resolved_sources = {item.source_record_id: item for item in registry.source_ledger.records}
    observed_sources = {item.elementary_source_id: item for item in manifest.observations}
    if set(resolved_sources) != set(observed_sources):
        raise ValueError("cluster observations do not exactly close the resolved source ledger")

    evidence_by_id = {item.evidence_record_id: item for item in registry.evidence_ledger.records}
    strata_by_cluster = {
        item.generalization_unit_id: item.stratum_values for item in artifact.cluster_strata
    }
    for source_id, observation in observed_sources.items():
        source = resolved_sources[source_id]
        if (
            observation.elementary_source_checksum != source.content_checksum
            or observation.metric_id != source.metric_id
            or observation.generalization_unit_id != source.generalization_unit_id
            or observation.value != source.value
            or observation.stratum_values != source.stratum_values
            or observation.stratum_values
            != strata_by_cluster.get(observation.generalization_unit_id)
        ):
            raise ValueError("cluster observation differs from its resolved source record")
        source_evidence = {
            item.evidence_record_id: item.record_checksum for item in source.evidence_records
        }
        if set(observation.evidence_ids) != set(source_evidence):
            raise ValueError("cluster observation evidence differs from the resolved source ledger")
        for evidence_id, record_checksum in source_evidence.items():
            resolved = evidence_by_id.get(evidence_id)
            if resolved is None or resolved.record_checksum != record_checksum:
                raise ValueError("cluster observation evidence cannot be resolved in the ledger")


def _expected_interval(
    contract: MetricGeneralizationContract,
    input_manifest: ClusterObservationManifest,
) -> KnowledgeValue[PrecisionInterval]:
    """Recompute the exact deterministic interval from the sealed elementary manifest."""

    ordered_estimates = list(input_manifest.cluster_estimates)
    values = [estimate.estimate for estimate in ordered_estimates]
    evidence_ids = tuple(
        sorted(
            {evidence_id for estimate in ordered_estimates for evidence_id in estimate.evidence_ids}
        )
    )
    cluster_count = len(values)
    if cluster_count < 2:
        return KnowledgeValue[PrecisionInterval](
            knowledge_state=KnowledgeState.UNKNOWN,
            rationale=(
                "A single resampling cluster has no empirical between-cluster distribution; "
                "precision and generalization remain unestimated."
            ),
            query_scope_id=contract.metric_id,
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
        lower = min(lower, point_estimate)
        upper = max(upper, point_estimate)
    return KnowledgeValue[PrecisionInterval](
        knowledge_state=KnowledgeState.PRESENT,
        value=PrecisionInterval(
            method_id=contract.bootstrap.method_id,
            confidence_level=contract.bootstrap.confidence_level,
            point_estimate=point_estimate,
            lower=lower,
            upper=upper,
        ),
        evidence_ids=evidence_ids,
        query_scope_id=contract.metric_id,
    )


def cluster_bootstrap_precision(
    contract: MetricGeneralizationContract,
    observations: tuple[ClusterMetricObservation, ...],
    *,
    authority_resolution: ClusterPrecisionAuthorityResolution | None = None,
) -> ClusterPrecisionResult:
    """Resolve governed rows, then resample clusters within preregistered strata."""

    input_manifest = _build_observation_manifest(contract, observations)
    cluster_count = input_manifest.cluster_count
    if authority_resolution is None:
        authority_value = _unresolved_authority_value(contract.metric_id)
        interval_value = _unresolved_authority_interval(contract.metric_id)
        return _build_cluster_precision_result(
            contract,
            input_manifest=input_manifest,
            effective_cluster_count=cluster_count,
            authority_resolution=authority_value,
            interval=interval_value,
            unavailable_blocker=ScientificReviewRequirement(
                issue_id=CLUSTER_PRECISION_REVIEW_ISSUE_ID,
                rationale=interval_value.rationale
                or "Cluster precision authority remains unresolved.",
            ),
        )

    checked_authority = ClusterPrecisionAuthorityResolution.model_validate(
        authority_resolution.model_dump(mode="python")
    )
    _validate_resolved_authority(contract, input_manifest, checked_authority)
    authority_value = KnowledgeValue[ClusterPrecisionAuthorityResolution](
        knowledge_state=KnowledgeState.PRESENT,
        value=checked_authority,
        evidence_ids=_authority_evidence_ids(checked_authority),
        query_scope_id=contract.metric_id,
    )
    interval_value = _expected_interval(contract, input_manifest)
    if cluster_count < 2:
        rationale = interval_value.rationale or "Cluster precision remains unavailable."
        return _build_cluster_precision_result(
            contract,
            input_manifest=input_manifest,
            effective_cluster_count=cluster_count,
            authority_resolution=authority_value,
            interval=interval_value,
            unavailable_blocker=ScientificReviewRequirement(
                issue_id=CLUSTER_PRECISION_REVIEW_ISSUE_ID,
                rationale=rationale,
            ),
        )
    return _build_cluster_precision_result(
        contract,
        input_manifest=input_manifest,
        effective_cluster_count=cluster_count,
        authority_resolution=authority_value,
        interval=interval_value,
    )


def build_cluster_evidence_record(
    *,
    evidence_record_id: str,
    evidence_content_checksum: str,
    custody_record_id: str,
    custody_record_checksum: str,
) -> ClusterEvidenceRecord:
    draft = ClusterEvidenceRecord.model_construct(
        evidence_record_id=evidence_record_id,
        evidence_content_checksum=evidence_content_checksum,
        custody_record_id=custody_record_id,
        custody_record_checksum=custody_record_checksum,
        record_checksum="0" * 64,
    )
    checksum = content_checksum(draft.model_dump(mode="json", exclude={"record_checksum"}))
    return ClusterEvidenceRecord(
        evidence_record_id=evidence_record_id,
        evidence_content_checksum=evidence_content_checksum,
        custody_record_id=custody_record_id,
        custody_record_checksum=custody_record_checksum,
        record_checksum=checksum,
    )


def _evidence_reference(record: ClusterEvidenceRecord) -> ClusterEvidenceReference:
    checked = ClusterEvidenceRecord.model_validate(record.model_dump(mode="python"))
    return ClusterEvidenceReference(
        evidence_record_id=checked.evidence_record_id,
        record_checksum=checked.record_checksum,
    )


def build_cluster_evidence_ledger(
    *,
    records: tuple[ClusterEvidenceRecord, ...],
) -> ClusterEvidenceLedger:
    checked_records = tuple(
        sorted(
            (
                ClusterEvidenceRecord.model_validate(item.model_dump(mode="python"))
                for item in records
            ),
            key=lambda item: item.evidence_record_id,
        )
    )
    draft = ClusterEvidenceLedger.model_construct(
        ledger_id="CLUSTER-EVIDENCE-PENDING",
        content_checksum="0" * 64,
        records=checked_records,
    )
    checksum = content_checksum(
        draft.model_dump(mode="json", exclude={"ledger_id", "content_checksum"})
    )
    return ClusterEvidenceLedger(
        ledger_id=f"CLUSTER-EVIDENCE-{checksum[:20]}",
        content_checksum=checksum,
        records=checked_records,
    )


def build_metric_generalization_contract_artifact(
    *,
    contract: MetricGeneralizationContract,
    cluster_strata: tuple[ClusterStratumAssignment, ...],
    preregistration_evidence_records: tuple[ClusterEvidenceRecord, ...],
    custody_evidence_records: tuple[ClusterEvidenceRecord, ...],
    review_evidence_records: tuple[ClusterEvidenceRecord, ...],
    reviewer_actor_ids: tuple[str, ...],
    review_scope_id: str,
) -> MetricGeneralizationContractArtifact:
    checked_contract = MetricGeneralizationContract.model_validate(
        contract.model_dump(mode="python")
    )
    preregistration_references = tuple(
        _evidence_reference(item) for item in preregistration_evidence_records
    )
    custody_references = tuple(_evidence_reference(item) for item in custody_evidence_records)
    review_references = tuple(_evidence_reference(item) for item in review_evidence_records)
    draft = MetricGeneralizationContractArtifact.model_construct(
        artifact_id="CLUSTER-CONTRACT-PENDING",
        content_checksum="0" * 64,
        contract=checked_contract,
        cluster_strata=cluster_strata,
        preregistration_evidence_records=preregistration_references,
        custody_evidence_records=custody_references,
        review_evidence_records=review_references,
        reviewer_actor_ids=reviewer_actor_ids,
        review_scope_id=review_scope_id,
    )
    checksum = content_checksum(
        draft.model_dump(mode="json", exclude={"artifact_id", "content_checksum"})
    )
    return MetricGeneralizationContractArtifact(
        artifact_id=f"CLUSTER-CONTRACT-{checksum[:20]}",
        content_checksum=checksum,
        contract=checked_contract,
        cluster_strata=cluster_strata,
        preregistration_evidence_records=preregistration_references,
        custody_evidence_records=custody_references,
        review_evidence_records=review_references,
        reviewer_actor_ids=reviewer_actor_ids,
        review_scope_id=review_scope_id,
    )


def build_cluster_elementary_source_record(
    *,
    source_record_id: str,
    metric_id: str,
    generalization_unit_id: str,
    value: Decimal,
    stratum_values: dict[str, str],
    evidence_records: tuple[ClusterEvidenceRecord, ...],
) -> ClusterElementarySourceRecord:
    checksum = cluster_elementary_source_checksum(
        metric_id=metric_id,
        elementary_source_id=source_record_id,
        generalization_unit_id=generalization_unit_id,
        value=value,
        stratum_values=stratum_values,
    )
    return ClusterElementarySourceRecord(
        source_record_id=source_record_id,
        content_checksum=checksum,
        metric_id=metric_id,
        generalization_unit_id=generalization_unit_id,
        value=value,
        stratum_values=stratum_values,
        evidence_records=tuple(
            sorted(
                (_evidence_reference(item) for item in evidence_records),
                key=lambda item: item.evidence_record_id,
            )
        ),
    )


def build_cluster_elementary_source_ledger(
    *,
    contract_artifact: MetricGeneralizationContractArtifact,
    records: tuple[ClusterElementarySourceRecord, ...],
) -> ClusterElementarySourceLedger:
    checked_artifact = MetricGeneralizationContractArtifact.model_validate(
        contract_artifact.model_dump(mode="python")
    )
    unit_order = {
        unit.generalization_unit_id: index
        for index, unit in enumerate(checked_artifact.contract.units)
    }
    checked_records = tuple(
        sorted(
            (
                ClusterElementarySourceRecord.model_validate(item.model_dump(mode="python"))
                for item in records
            ),
            key=lambda item: (
                unit_order.get(item.generalization_unit_id, len(unit_order)),
                item.source_record_id,
            ),
        )
    )
    draft = ClusterElementarySourceLedger.model_construct(
        ledger_id="CLUSTER-SOURCES-PENDING",
        content_checksum="0" * 64,
        contract_artifact_id=checked_artifact.artifact_id,
        contract_artifact_checksum=checked_artifact.content_checksum,
        records=checked_records,
    )
    checksum = content_checksum(
        draft.model_dump(mode="json", exclude={"ledger_id", "content_checksum"})
    )
    return ClusterElementarySourceLedger(
        ledger_id=f"CLUSTER-SOURCES-{checksum[:20]}",
        content_checksum=checksum,
        contract_artifact_id=checked_artifact.artifact_id,
        contract_artifact_checksum=checked_artifact.content_checksum,
        records=checked_records,
    )


def build_cluster_precision_authority_registry(
    *,
    contract_artifact: MetricGeneralizationContractArtifact,
    source_ledger: ClusterElementarySourceLedger,
    evidence_ledger: ClusterEvidenceLedger,
) -> ClusterPrecisionAuthorityRegistry:
    checked_artifact = MetricGeneralizationContractArtifact.model_validate(
        contract_artifact.model_dump(mode="python")
    )
    checked_source_ledger = ClusterElementarySourceLedger.model_validate(
        source_ledger.model_dump(mode="python")
    )
    checked_evidence_ledger = ClusterEvidenceLedger.model_validate(
        evidence_ledger.model_dump(mode="python")
    )
    draft = ClusterPrecisionAuthorityRegistry.model_construct(
        registry_id="CLUSTER-AUTHORITY-PENDING",
        content_checksum="0" * 64,
        contract_artifact=checked_artifact,
        source_ledger=checked_source_ledger,
        evidence_ledger=checked_evidence_ledger,
    )
    checksum = content_checksum(
        draft.model_dump(mode="json", exclude={"registry_id", "content_checksum"})
    )
    return ClusterPrecisionAuthorityRegistry(
        registry_id=f"CLUSTER-AUTHORITY-{checksum[:20]}",
        content_checksum=checksum,
        contract_artifact=checked_artifact,
        source_ledger=checked_source_ledger,
        evidence_ledger=checked_evidence_ledger,
    )


def resolve_cluster_precision_authority(
    *,
    registry: ClusterPrecisionAuthorityRegistry,
    pin: ClusterPrecisionAuthorityPin,
) -> ClusterPrecisionAuthorityResolution:
    checked_registry = ClusterPrecisionAuthorityRegistry.model_validate(
        registry.model_dump(mode="python")
    )
    checked_pin = ClusterPrecisionAuthorityPin.model_validate(pin.model_dump(mode="python"))
    draft = ClusterPrecisionAuthorityResolution.model_construct(
        resolution_id="CLUSTER-AUTHORITY-RESOLUTION-PENDING",
        content_checksum="0" * 64,
        registry=checked_registry,
        pin=checked_pin,
    )
    checksum = content_checksum(
        draft.model_dump(mode="json", exclude={"resolution_id", "content_checksum"})
    )
    return ClusterPrecisionAuthorityResolution(
        resolution_id=f"CLUSTER-AUTHORITY-RESOLUTION-{checksum[:20]}",
        content_checksum=checksum,
        registry=checked_registry,
        pin=checked_pin,
    )


def build_cluster_metric_observation(
    *,
    metric_id: str,
    elementary_source_id: str,
    generalization_unit_id: str,
    value: Decimal,
    stratum_values: dict[str, str],
    evidence_ids: tuple[str, ...],
) -> ClusterMetricObservation:
    """Create one content-addressed elementary observation."""

    checksum = cluster_elementary_source_checksum(
        metric_id=metric_id,
        elementary_source_id=elementary_source_id,
        generalization_unit_id=generalization_unit_id,
        value=value,
        stratum_values=stratum_values,
    )
    return ClusterMetricObservation(
        metric_id=metric_id,
        observation_id=f"CLUSTER-OBSERVATION-{checksum[:20]}",
        elementary_source_id=elementary_source_id,
        elementary_source_checksum=checksum,
        generalization_unit_id=generalization_unit_id,
        value=value,
        stratum_values=stratum_values,
        evidence_ids=evidence_ids,
    )


def cluster_elementary_source_checksum(
    *,
    metric_id: str,
    elementary_source_id: str,
    generalization_unit_id: str,
    value: Decimal,
    stratum_values: dict[str, str],
) -> str:
    """Address one local row declaration; governed identity still requires its pinned ledger."""

    return content_checksum(
        {
            "metric_id": metric_id,
            "elementary_source_id": elementary_source_id,
            "generalization_unit_id": generalization_unit_id,
            "value": value,
            "stratum_values": stratum_values,
        }
    )


__all__ = [
    "CLUSTER_PRECISION_REVIEW_ISSUE_ID",
    "SUPPORTED_CLUSTER_BOOTSTRAP_METHOD",
    "SUPPORTED_CLUSTER_ESTIMATOR_CHECKSUM",
    "SUPPORTED_CLUSTER_ESTIMATOR_ID",
    "ClusterBootstrapProtocol",
    "ClusterElementarySourceLedger",
    "ClusterElementarySourceRecord",
    "ClusterEvidenceLedger",
    "ClusterEvidenceRecord",
    "ClusterEvidenceReference",
    "ClusterMetricEstimate",
    "ClusterMetricObservation",
    "ClusterObservationManifest",
    "ClusterPrecisionAuthorityPin",
    "ClusterPrecisionAuthorityRegistry",
    "ClusterPrecisionAuthorityResolution",
    "ClusterPrecisionResult",
    "ClusterStratumAssignment",
    "GeneralizationUnit",
    "GeneralizationUnitKind",
    "MetricGeneralizationContract",
    "MetricGeneralizationContractArtifact",
    "PrecisionInterval",
    "build_cluster_elementary_source_ledger",
    "build_cluster_elementary_source_record",
    "build_cluster_evidence_ledger",
    "build_cluster_evidence_record",
    "build_cluster_metric_observation",
    "build_cluster_precision_authority_registry",
    "build_metric_generalization_contract_artifact",
    "cluster_bootstrap_precision",
    "cluster_elementary_source_checksum",
    "resolve_cluster_precision_authority",
]
