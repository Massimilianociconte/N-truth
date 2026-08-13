"""Fail-closed small-model training readiness projected from the root Reality Gate.

The canonical scientific decision remains owned by :mod:`ntruth.reality_gate`.
This module only maps that decision, plus explicit engineering constraints, to
the categories used by a local-training readiness report.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, model_validator

from ntruth.reality_gate import (
    GatePredicateName,
    GateValue,
    RealityGateResult,
    ScientificValidation,
    machine_readable_result,
)
from ntruth.schemas.core import FrozenModel, content_checksum
from ntruth.training.blockers import (
    FD_ISOLATION_BLOCKER_CODE,
    FD_ISOLATION_BLOCKER_DETAIL,
)


class ReadinessStatus(StrEnum):
    PASS = "PASS"
    PARTIAL = "PARTIAL"
    FAIL = "FAIL"


class OverallReadiness(StrEnum):
    READY = "READY"
    READY_WITH_CONDITIONS = "READY_WITH_CONDITIONS"
    NOT_READY = "NOT_READY"


class ModelRole(StrEnum):
    PROVISIONAL_PRIMARY = "PROVISIONAL_PRIMARY"
    CHALLENGER = "CHALLENGER"
    SPECIALIST_BASELINE = "SPECIALIST_BASELINE"


class ReadinessEvidence(FrozenModel):
    code: str
    claim: str
    source_ref: str


class ReadinessBlocker(FrozenModel):
    code: str
    detail: str
    source_ref: str
    resolution_owner: Literal["SCIENTIFIC", "DATA", "ENGINEERING", "GOVERNANCE"]


class ReadinessCategory(FrozenModel):
    status: ReadinessStatus
    evidence: tuple[ReadinessEvidence, ...]
    blockers: tuple[ReadinessBlocker, ...] = ()


class RootRealityGateSnapshot(FrozenModel):
    gate_version: str
    purpose: str
    engineering_readiness: str
    data_readiness: str
    scientific_validation: str
    substantive_training_allowed: bool
    ai_claims_allowed: bool
    checksum: str


class ModelCandidate(FrozenModel):
    model_id: str
    role: ModelRole
    parameter_class: str
    local_method: str
    rationale: str


class SmallModelTrainingReadiness(FrozenModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    normative_target: Literal["PRD_V9"] = "PRD_V9"
    implemented_root_contract: Literal["PRD_V7"] = "PRD_V7"
    v9_schema_conformance: Literal["BLOCKED_PENDING_CANONICAL_REGISTRY"] = (
        "BLOCKED_PENDING_CANONICAL_REGISTRY"
    )
    root_reality_gate: RootRealityGateSnapshot
    scientific: ReadinessCategory
    dataset: ReadinessCategory
    schema_readiness: ReadinessCategory = Field(serialization_alias="schema")
    evaluation: ReadinessCategory
    infrastructure: ReadinessCategory
    apple_silicon_feasibility: ReadinessCategory
    reproducibility: ReadinessCategory
    model_selection_status: ReadinessStatus
    models: tuple[ModelCandidate, ...]
    substantive_training_allowed: bool
    overall: OverallReadiness
    overall_blockers: tuple[ReadinessBlocker, ...]

    @model_validator(mode="after")
    def _fail_closed(self) -> Self:
        assert_training_readiness_invariants(self)
        return self

    def as_machine_readable(self) -> dict[str, object]:
        assert_training_readiness_invariants(self)
        payload = self.model_dump(mode="json", by_alias=True)
        payload["checksum"] = content_checksum(payload)
        return payload


def _evidence(code: str, claim: str, source_ref: str) -> ReadinessEvidence:
    return ReadinessEvidence(code=code, claim=claim, source_ref=source_ref)


def _blocker(
    code: str,
    detail: str,
    source_ref: str,
    owner: Literal["SCIENTIFIC", "DATA", "ENGINEERING", "GOVERNANCE"],
) -> ReadinessBlocker:
    return ReadinessBlocker(
        code=code,
        detail=detail,
        source_ref=source_ref,
        resolution_owner=owner,
    )


def _predicate_value(root_gate: RealityGateResult, name: GatePredicateName) -> GateValue:
    predicates = (
        *root_gate.engineering_readiness.predicates,
        *root_gate.data_readiness.predicates,
    )
    for predicate in predicates:
        if predicate.name is name:
            return predicate.value
    return GateValue.UNKNOWN


def _root_snapshot(root_gate: RealityGateResult) -> RootRealityGateSnapshot:
    machine = machine_readable_result(root_gate)
    return RootRealityGateSnapshot(
        gate_version=root_gate.gate_version,
        purpose=root_gate.purpose.value,
        engineering_readiness=root_gate.engineering_readiness.status,
        data_readiness=root_gate.data_readiness.status,
        scientific_validation=root_gate.scientific_validation.status,
        substantive_training_allowed=root_gate.substantive_training_allowed,
        ai_claims_allowed=root_gate.ai_claims_allowed,
        checksum=str(machine["checksum"]),
    )


def _scientific_category(root_gate: RealityGateResult) -> ReadinessCategory:
    status = root_gate.scientific_validation.status
    evidence = (
        _evidence(
            "ROOT_SCIENTIFIC_VALIDATION",
            f"Canonical Reality Gate reports scientific_validation={status}",
            "ntruth.reality_gate.RealityGateResult.scientific_validation",
        ),
    )
    if (
        status == ScientificValidation.VALIDATED.value
        and not root_gate.scientific_validation.blockers
    ):
        return ReadinessCategory(status=ReadinessStatus.PASS, evidence=evidence)
    readiness = (
        ReadinessStatus.PARTIAL
        if status == ScientificValidation.IN_PROGRESS.value
        else ReadinessStatus.FAIL
    )
    return ReadinessCategory(
        status=readiness,
        evidence=evidence,
        blockers=(
            _blocker(
                "SCIENTIFIC_VALIDATION_NOT_COMPLETE",
                f"Root scientific validation is {status}; no independent validated claim is inferred",
                "ntruth.reality_gate.RealityGateResult.scientific_validation",
                "SCIENTIFIC",
            ),
        ),
    )


def _dataset_category(root_gate: RealityGateResult) -> ReadinessCategory:
    evidence = (
        _evidence(
            "ROOT_DATA_READINESS",
            f"Canonical Reality Gate reports data_readiness={root_gate.data_readiness.status}",
            "ntruth.reality_gate.RealityGateResult.data_readiness",
        ),
    )
    if root_gate.data_readiness.status == "READY":
        return ReadinessCategory(status=ReadinessStatus.PASS, evidence=evidence)
    return ReadinessCategory(
        status=ReadinessStatus.FAIL,
        evidence=evidence,
        blockers=(
            _blocker(
                "ROOT_DATA_READINESS_BLOCKED",
                "Required real-anchor, licence, split or human-review predicates remain blocked",
                "ntruth.reality_gate.RealityGateResult.data_readiness",
                "DATA",
            ),
        ),
    )


def _schema_category(root_gate: RealityGateResult) -> ReadinessCategory:
    root_schema_ready = all(
        _predicate_value(root_gate, name) is GateValue.TRUE
        for name in (
            GatePredicateName.SCHEMA_STABLE_ON_REAL_CASES,
            GatePredicateName.NO_BLOCKING_SCHEMA_GAPS,
        )
    )
    evidence = (
        _evidence(
            "ROOT_SCHEMA_CONTRACT",
            "Implemented root contract is PRD_V7 and remains authoritative",
            "packages/ntruth/reality_gate/gate.py",
        ),
        _evidence(
            "NORMATIVE_SCHEMA_TARGET",
            "Normative target is PRD_V9",
            "PRD_V9",
        ),
    )
    blockers = [
        _blocker(
            "V9_CANONICAL_REGISTRY_PENDING",
            "PRD_V9 schema conformance is blocked pending the canonical registry",
            "BLOCKED_PENDING_CANONICAL_REGISTRY",
            "GOVERNANCE",
        )
    ]
    if not root_schema_ready:
        blockers.append(
            _blocker(
                "ROOT_SCHEMA_PREDICATES_BLOCKED",
                "PRD_V7 root schema predicates are not both TRUE",
                "ntruth.reality_gate.RealityGateResult.engineering_readiness",
                "ENGINEERING",
            )
        )
    return ReadinessCategory(
        status=ReadinessStatus.PARTIAL if root_schema_ready else ReadinessStatus.FAIL,
        evidence=evidence,
        blockers=tuple(blockers),
    )


def _evaluation_category(root_gate: RealityGateResult) -> ReadinessCategory:
    baseline_value = _predicate_value(root_gate, GatePredicateName.REAL_BASELINE_EXECUTED)
    evidence = (
        _evidence(
            "ROOT_REAL_BASELINE_PREDICATE",
            f"Canonical real_baseline_executed predicate is {baseline_value.value}",
            "ntruth.reality_gate.GatePredicateName.REAL_BASELINE_EXECUTED",
        ),
    )
    if baseline_value is GateValue.TRUE:
        return ReadinessCategory(status=ReadinessStatus.PASS, evidence=evidence)
    return ReadinessCategory(
        status=ReadinessStatus.FAIL,
        evidence=evidence,
        blockers=(
            _blocker(
                "REAL_BASELINE_NOT_EXECUTED",
                "Zero-shot, few-shot, retrieval and no-adapter baselines are not canonically closed",
                "ntruth.reality_gate.GatePredicateName.REAL_BASELINE_EXECUTED",
                "SCIENTIFIC",
            ),
        ),
    )


def _infrastructure_category() -> ReadinessCategory:
    from ntruth.training.fd_isolation import fd_isolation_contract_holds

    blockers = []
    if not fd_isolation_contract_holds():
        blockers.append(
            _blocker(
                FD_ISOLATION_BLOCKER_CODE,
                FD_ISOLATION_BLOCKER_DETAIL,
                "ntruth.training.blockers.FD_ISOLATION_BLOCKER_CODE",
                "ENGINEERING",
            )
        )
    blockers.append(
        _blocker(
            "MODEL_SELECTION_BENCHMARK_PENDING",
            "The provisional primary has not defeated both challengers on frozen N-Truth evaluation",
            "models/configs/small-model-readiness-v1",
            "ENGINEERING",
        )
    )
    return ReadinessCategory(
        status=ReadinessStatus.PARTIAL,
        evidence=(
            _evidence(
                "LOCAL_PEF_TRAINING_DESIGN",
                "A 4-bit MLX-LM adapter path is defined for 3B-4B candidates",
                "models/configs",
            ),
        ),
        blockers=tuple(blockers),
    )


def _apple_category() -> ReadinessCategory:
    return ReadinessCategory(
        status=ReadinessStatus.PASS,
        evidence=(
            _evidence(
                "APPLE_SILICON_24_GIB_FEASIBLE",
                "3B-4B 4-bit adapter fine-tuning is technically feasible on the 24 GiB target",
                "hardware://macbook-pro-m5-pro/24-gib",
            ),
            _evidence(
                "FEASIBILITY_NOT_AUTHORIZATION",
                "Hardware feasibility does not authorize substantive training",
                "ntruth.reality_gate.RealityGateResult.substantive_training_allowed",
            ),
        ),
    )


def _reproducibility_category(root_gate: RealityGateResult) -> ReadinessCategory:
    protected_split = _predicate_value(root_gate, GatePredicateName.PROTECTED_SPLIT_FROZEN)
    licence_scope = _predicate_value(root_gate, GatePredicateName.LICENCE_SCOPE_VERIFIED)
    evidence = (
        _evidence(
            "ROOT_PROTECTED_SPLIT",
            f"Canonical protected_split_frozen predicate is {protected_split.value}",
            "ntruth.reality_gate.GatePredicateName.PROTECTED_SPLIT_FROZEN",
        ),
        _evidence(
            "ROOT_LICENCE_SCOPE",
            f"Canonical licence_scope_verified predicate is {licence_scope.value}",
            "ntruth.reality_gate.GatePredicateName.LICENCE_SCOPE_VERIFIED",
        ),
    )
    if protected_split is GateValue.TRUE and licence_scope is GateValue.TRUE:
        return ReadinessCategory(status=ReadinessStatus.PASS, evidence=evidence)
    return ReadinessCategory(
        status=ReadinessStatus.FAIL,
        evidence=evidence,
        blockers=(
            _blocker(
                "FROZEN_REPRODUCIBLE_SNAPSHOT_NOT_AUTHORIZED",
                "Licence scope and protected split must both be canonically TRUE",
                "ntruth.reality_gate.RealityGateResult.data_readiness",
                "GOVERNANCE",
            ),
        ),
    )


def _model_candidates() -> tuple[ModelCandidate, ...]:
    return (
        ModelCandidate(
            model_id="ibm-granite/granite-4.1-3b",
            role=ModelRole.PROVISIONAL_PRIMARY,
            parameter_class="3B",
            local_method="MLX-LM 4-bit QLoRA",
            rationale="Provisional primary only; promotion remains benchmark-gated",
        ),
        ModelCandidate(
            model_id="Qwen/Qwen3-4B-Instruct-2507",
            role=ModelRole.CHALLENGER,
            parameter_class="4B",
            local_method="MLX-LM 4-bit QLoRA",
            rationale="Generative structured-output challenger",
        ),
        ModelCandidate(
            model_id="microsoft/Phi-4-mini-instruct",
            role=ModelRole.CHALLENGER,
            parameter_class="3.8B",
            local_method="MLX-LM 4-bit QLoRA",
            rationale="Compact reasoning challenger",
        ),
        ModelCandidate(
            model_id="answerdotai/ModernBERT-base",
            role=ModelRole.SPECIALIST_BASELINE,
            parameter_class="149M",
            local_method="MPS parameter-efficient extraction baseline",
            rationale="Specialist extraction baseline, not an Experiment Graph generator",
        ),
    )


def _unique_blockers(blockers: tuple[ReadinessBlocker, ...]) -> tuple[ReadinessBlocker, ...]:
    unique: dict[tuple[str, str], ReadinessBlocker] = {}
    for blocker in blockers:
        unique[(blocker.code, blocker.source_ref)] = blocker
    return tuple(unique.values())


def project_small_model_training_readiness(
    root_gate: RealityGateResult,
) -> SmallModelTrainingReadiness:
    scientific = _scientific_category(root_gate)
    dataset = _dataset_category(root_gate)
    schema = _schema_category(root_gate)
    evaluation = _evaluation_category(root_gate)
    infrastructure = _infrastructure_category()
    apple = _apple_category()
    reproducibility = _reproducibility_category(root_gate)
    categories = (
        scientific,
        dataset,
        schema,
        evaluation,
        infrastructure,
        apple,
        reproducibility,
    )
    blockers = tuple(blocker for category in categories for blocker in category.blockers)
    if not root_gate.substantive_training_allowed:
        blockers = (
            _blocker(
                "ROOT_SUBSTANTIVE_TRAINING_BLOCKED",
                "The canonical Reality Gate does not allow substantive training",
                "ntruth.reality_gate.RealityGateResult.substantive_training_allowed",
                "GOVERNANCE",
            ),
            *blockers,
        )
        overall = OverallReadiness.NOT_READY
    elif any(category.status is ReadinessStatus.FAIL for category in categories):
        overall = OverallReadiness.NOT_READY
    elif any(category.status is ReadinessStatus.PARTIAL for category in categories):
        overall = OverallReadiness.READY_WITH_CONDITIONS
    else:
        overall = OverallReadiness.READY
    return SmallModelTrainingReadiness(
        root_reality_gate=_root_snapshot(root_gate),
        scientific=scientific,
        dataset=dataset,
        schema_readiness=schema,
        evaluation=evaluation,
        infrastructure=infrastructure,
        apple_silicon_feasibility=apple,
        reproducibility=reproducibility,
        model_selection_status=ReadinessStatus.PARTIAL,
        models=_model_candidates(),
        substantive_training_allowed=root_gate.substantive_training_allowed,
        overall=overall,
        overall_blockers=_unique_blockers(blockers),
    )


def assert_training_readiness_invariants(projection: SmallModelTrainingReadiness) -> None:
    if (
        projection.substantive_training_allowed
        != projection.root_reality_gate.substantive_training_allowed
    ):
        raise ValueError("training projection cannot override the root Reality Gate")
    if (
        not projection.substantive_training_allowed
        and projection.overall is not OverallReadiness.NOT_READY
    ):
        raise ValueError("root Reality Gate blocks substantive training: overall must be NOT_READY")
    if (
        projection.v9_schema_conformance == "BLOCKED_PENDING_CANONICAL_REGISTRY"
        and projection.schema_readiness.status is ReadinessStatus.PASS
    ):
        raise ValueError("blocked PRD_V9 schema conformance cannot report schema PASS")
    if (
        projection.schema_readiness.status is ReadinessStatus.PARTIAL
        and projection.overall is OverallReadiness.READY
    ):
        raise ValueError("partial schema readiness cannot report overall READY")
    if projection.apple_silicon_feasibility.status is not ReadinessStatus.PASS:
        raise ValueError("the assessed 24 GiB Apple Silicon feasibility must remain explicit")
    if projection.model_selection_status is not ReadinessStatus.PARTIAL:
        raise ValueError("model selection remains PARTIAL until the frozen benchmark closes")
