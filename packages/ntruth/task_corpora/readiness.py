"""Dataset readiness projection onto canonical PRD-v7 Reality Gate contracts.

This module does **not** re-implement scientific validation. It projects
dataset-side facts (licence, provenance, auxiliary authority, model-use)
into a narrow, fail-closed view that consumers can report without claiming
the full Reality Gate is open.

Canonical ownership:
  packages/ntruth/reality_gate/  (root)
  packages/ntruth/cross_domain/  (root)

Serialized SourceData JSONL task records are not modified by this module.
"""

from __future__ import annotations

from typing import Final, Literal, Self

from pydantic import model_validator

from ntruth.reality_gate.gate import (
    EXPECTED_CURRENT_STATE,
    DataReadiness,
    EngineeringReadiness,
    GatePurpose,
    ScientificValidation,
)
from ntruth.reality_gate.predicates import GatePredicateName, GateValue
from ntruth.schemas.core import FrozenModel

# Dataset engineering is component-verified for C0/C1 adapters only.
# It must never be collapsed into root EngineeringReadiness.READY.
DatasetEngineeringStatus = Literal[
    "VERIFIED_FOR_C0_C1",
    "PARTIAL",
    "NOT_STARTED",
]

CANONICAL_FORBIDDEN_GOLD_USES: Final[tuple[str, ...]] = (
    "experimental_unit_gold",
    "independent_n_gold",
    "pseudoreplication_verdict_gold",
    "allocation_gold",
    "biological_independence_gold",
    "interference_gold",
    "estimand_gold",
)

ROOT_CONTRACT_MERGE_SHA: Final[str] = "f2faace471788bdc4255e42fa88d5868f906e732"
ROOT_MAIN_BASELINE_SHA: Final[str] = "a2afde309e6f529dcf5437c1b297bfbf130a0d05"

# Immutable contract pin (not the tip of branch main).
ROOT_REALITY_GATE_CONTRACT_REF: Final[str] = f"reality_gate@commit:{ROOT_CONTRACT_MERGE_SHA[:12]}"


class DatasetReadinessProjection(FrozenModel):
    """Facts-only projection for dataset manifests and governance reports.

    Intrinsically fail-closed: forbidden scientific-readiness claims cannot be
    constructed or serialized via as_manifest_fields().
    """

    projection_version: str = "1.0.0"
    root_gate_contract_ref: str = ROOT_REALITY_GATE_CONTRACT_REF
    purpose: GatePurpose = GatePurpose.MVT_A_EXPLORATORY

    engineering_component_status: DatasetEngineeringStatus = "VERIFIED_FOR_C0_C1"
    engineering_readiness: EngineeringReadiness = (
        EngineeringReadiness.PARTIAL_OR_VERIFIED_BY_COMPONENT
    )

    licence_scope_status: GateValue = GateValue.UNKNOWN
    provenance_status: GateValue = GateValue.UNKNOWN
    split_protection_status: GateValue = GateValue.FALSE
    auxiliary_authority: bool = True
    model_use_status: str = "BLOCKED"

    data_readiness: DataReadiness = DataReadiness.BLOCKED
    scientific_validation: ScientificValidation = ScientificValidation.NOT_STARTED
    reality_gate_status: str = "BLOCKED"
    substantive_training_allowed: bool = False
    ai_claims_allowed: bool = False

    real_anchor_available: GateValue = GateValue.FALSE
    reality_gate_satisfied_by_public_corpora: bool = False
    reality_gate_satisfied_by_silver_adapter: bool = False

    leakage_group_granularity: str = "RECORD_LEVEL_FALLBACK"
    paper_level_leakage_claim_allowed: bool = False

    blockers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _fail_closed_scientific_claims(self) -> Self:
        assert_projection_cannot_claim_scientific_readiness(self)
        return self

    def as_manifest_fields(self) -> dict[str, object]:
        """Stable subset written into BuildManifest (manifest-only).

        Re-runs fail-closed invariants so model_copy(update=...) cannot smuggle
        READY/VALIDATED into serialized manifests without validation.
        """
        assert_projection_cannot_claim_scientific_readiness(self)
        return {
            "engineering_readiness": self.engineering_component_status,
            "data_readiness": self.data_readiness.value,
            "scientific_validation": self.scientific_validation.value,
            "reality_gate_status": self.reality_gate_status,
            "reality_gate_ref": self.root_gate_contract_ref,
            "reality_gate_satisfied_by_public_corpora": (
                self.reality_gate_satisfied_by_public_corpora
            ),
            "reality_gate_satisfied_by_silver_adapter": (
                self.reality_gate_satisfied_by_silver_adapter
            ),
            "model_use_status": self.model_use_status,
            "dataset_readiness_projection": self.model_dump(mode="json"),
        }


def project_sourcedata_c0_c1(
    *,
    licence_verified: bool = False,
    paper_level_provenance: bool = False,
    ntruth_partition_approved: bool = False,
    engineering_component_status: DatasetEngineeringStatus = "VERIFIED_FOR_C0_C1",
    leakage_group_granularity: str = "RECORD_LEVEL_FALLBACK",
) -> DatasetReadinessProjection:
    """Canonical projection for SourceData C0-C1 silver entity_roles.

    Public/silver engineering success cannot open data readiness or scientific
    validation (PRD v7 §0.7, §14.1).
    """
    blockers: list[str] = [
        f"{GatePredicateName.REAL_ANCHOR_AVAILABLE.value}: FALSE "
        "(public/silver corpora are not real anchors)",
        f"{GatePredicateName.PROTECTED_SPLIT_FROZEN.value}: FALSE "
        "(upstream partitions preserved; ntruth_partition_approved=false)",
        f"{GatePredicateName.HUMAN_SECOND_REVIEW_COMPLETED.value}: FALSE",
        f"{GatePredicateName.DECISIVE_FIELDS_REVIEWED.value}: FALSE",
        f"{GatePredicateName.REAL_BASELINE_EXECUTED.value}: FALSE",
    ]
    licence_status = GateValue.TRUE if licence_verified else GateValue.UNKNOWN
    if licence_status is not GateValue.TRUE:
        blockers.append(f"{GatePredicateName.LICENCE_SCOPE_VERIFIED.value}: {licence_status.value}")
    provenance_status = GateValue.TRUE if paper_level_provenance else GateValue.UNKNOWN
    if provenance_status is not GateValue.TRUE:
        blockers.append(
            f"provenance_status: {provenance_status.value} "
            f"(leakage_group_granularity={leakage_group_granularity})"
        )
    if leakage_group_granularity == "RECORD_LEVEL_FALLBACK":
        blockers.append(
            "RECORD_LEVEL_FALLBACK: groups_crossing_splits=0 is not paper-level isolation"
        )
    if not ntruth_partition_approved:
        blockers.append("ntruth_partition_approved: false")

    return DatasetReadinessProjection(
        purpose=GatePurpose.MVT_A_EXPLORATORY,
        engineering_component_status=engineering_component_status,
        engineering_readiness=EngineeringReadiness.PARTIAL_OR_VERIFIED_BY_COMPONENT,
        licence_scope_status=licence_status,
        provenance_status=provenance_status,
        split_protection_status=(GateValue.TRUE if ntruth_partition_approved else GateValue.FALSE),
        auxiliary_authority=True,
        model_use_status="BLOCKED",
        data_readiness=DataReadiness.BLOCKED,
        scientific_validation=ScientificValidation.NOT_STARTED,
        reality_gate_status="BLOCKED",
        substantive_training_allowed=False,
        ai_claims_allowed=False,
        real_anchor_available=GateValue.FALSE,
        reality_gate_satisfied_by_public_corpora=False,
        reality_gate_satisfied_by_silver_adapter=False,
        leakage_group_granularity=leakage_group_granularity,
        paper_level_leakage_claim_allowed=False,
        blockers=tuple(blockers),
    )


def assert_projection_cannot_claim_scientific_readiness(
    projection: DatasetReadinessProjection,
) -> None:
    """Hard invariant: construction and manifest serialization both call this."""
    if projection.data_readiness is DataReadiness.READY:
        raise ValueError("dataset projection must not set data_readiness READY without real anchor")
    if projection.scientific_validation is ScientificValidation.VALIDATED:
        raise ValueError("dataset projection must not set scientific_validation VALIDATED")
    if projection.reality_gate_satisfied_by_public_corpora:
        raise ValueError("public corpora cannot satisfy Reality Gate")
    if projection.reality_gate_satisfied_by_silver_adapter:
        raise ValueError("silver adapter cannot satisfy Reality Gate")
    if projection.substantive_training_allowed or projection.ai_claims_allowed:
        raise ValueError("dataset projection cannot allow training or AI claims")
    if projection.real_anchor_available is GateValue.TRUE and projection.auxiliary_authority:
        raise ValueError("auxiliary silver cannot claim real_anchor_available=TRUE")
    if (
        projection.leakage_group_granularity == "RECORD_LEVEL_FALLBACK"
        and projection.paper_level_leakage_claim_allowed
    ):
        raise ValueError(
            "RECORD_LEVEL_FALLBACK cannot allow paper_level_leakage_claim_allowed=true"
        )


def forbidden_gold_uses_are_canonical_superset(dataset_bans: tuple[str, ...] | list[str]) -> bool:
    """True iff dataset bans cover every canonical gold ban."""
    return set(CANONICAL_FORBIDDEN_GOLD_USES).issubset(set(dataset_bans))


def root_expected_current_state() -> dict[str, str]:
    """Re-export for dataset docs; identical to root EXPECTED_CURRENT_STATE."""
    return dict(EXPECTED_CURRENT_STATE)


def role_decision_pending_model_use_allowed() -> bool:
    """ROLE_DECISION_PENDING is never model-use eligible."""
    return False
