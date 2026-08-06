"""Canonical task-record schemas for Workstream C corpora."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ntruth.task_corpora.authority import (
    AuthorityLevel,
    LicenseStatus,
    SupervisionSource,
)

# Tri-state permission: True | False | "unknown". Unknown must fail closed for the use.
PermissionFlag = bool | Literal["unknown"]

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}\Z")

# Audited canonical SourceData v2.0.3 task-corpus population.
SIDECAR_EXPECTED_ROWS = 75_163


def _lowercase_sha256(value: str, field: str) -> str:
    if not _SHA256_HEX.match(value):
        raise ValueError(f"{field} must be lowercase 64-char hex SHA-256")
    return value


class ProvenanceSidecarManifest(BaseModel):
    """Typed manifest block for the external provenance sidecar (strict).

    Additive in manifest_version 0.3.0. Every field is required and typed;
    unknown fields are rejected. Fail-closed leakage posture is encoded as
    invariants, not conventions: the paper-level leakage claim can never be
    promoted through this block, and the diagnostic always excludes the
    RECORD_FALLBACK population.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["PARTIAL_DETERMINISTIC"]
    rows: int
    panel_unique: int
    figure_unique: int
    article_only: int
    record_fallback: int
    map_sha256: str
    schema_version: str
    algorithm_version: str
    upstream_xml_sha256: str
    matched_subset_records: int
    matched_subset_articles: int
    matched_subset_articles_crossing_existing_splits: int
    fallback_records_excluded_from_diagnostic: int
    embedded_document_id_present: int
    global_paper_level_leakage_claim_allowed: bool

    @field_validator("map_sha256")
    @classmethod
    def valid_map_sha256(cls, value: str) -> str:
        return _lowercase_sha256(value, "map_sha256")

    @field_validator("upstream_xml_sha256")
    @classmethod
    def valid_upstream_xml_sha256(cls, value: str) -> str:
        return _lowercase_sha256(value, "upstream_xml_sha256")

    @model_validator(mode="after")
    def invariants(self) -> ProvenanceSidecarManifest:
        total = self.panel_unique + self.figure_unique + self.article_only + self.record_fallback
        if total != self.rows:
            raise ValueError(f"tier counts sum {total} != rows {self.rows}")
        if self.rows != SIDECAR_EXPECTED_ROWS:
            raise ValueError(
                f"rows must equal the audited corpus population {SIDECAR_EXPECTED_ROWS}"
            )
        matched = self.panel_unique + self.figure_unique + self.article_only
        if self.matched_subset_records != matched:
            raise ValueError(
                f"matched_subset_records {self.matched_subset_records} != matched tiers {matched}"
            )
        if self.fallback_records_excluded_from_diagnostic != self.record_fallback:
            raise ValueError("fallback_records_excluded_from_diagnostic must equal record_fallback")
        if self.embedded_document_id_present != 0:
            raise ValueError("the sidecar never replaces embedded document provenance")
        if self.global_paper_level_leakage_claim_allowed:
            raise ValueError("paper-level leakage claim stays fail-closed (false)")
        if self.matched_subset_articles_crossing_existing_splits < 0:
            raise ValueError("matched_subset_articles_crossing_existing_splits must be >= 0")
        if self.matched_subset_articles < 0:
            raise ValueError("matched_subset_articles must be >= 0")
        return self


class SourceIdentity(BaseModel):
    dataset: str
    version: str
    commit: str
    document_id: str
    segment_id: str
    source_record_id: str | None = None


class TransformLineage(BaseModel):
    adapter: str
    transform_version: str
    parent_path: str
    parent_checksum: str
    mapping_version: str


class LicenseUseDecision(BaseModel):
    """Machine-readable licence + granular use decision.

    Coarse flags (training_allowed, redistribution_allowed, derived_labels_allowed)
    remain for compatibility. Granular use_decision fields must not be inferred:
    ``unknown`` fails closed for that capability.
    """

    license_status: LicenseStatus
    training_allowed: bool
    redistribution_allowed: bool
    derived_labels_allowed: bool
    decision_basis: str
    reviewed_at: str
    spdx: str | None = None
    # Granular use decision (normative for B0 / metrics / redistribution).
    adapter_build_allowed: bool = True
    local_format_validation_allowed: bool = True
    development_allowed: PermissionFlag = False
    evaluation_allowed: PermissionFlag = "unknown"
    benchmark_metrics_publication_allowed: PermissionFlag = "unknown"
    derived_records_redistribution_allowed: bool = False
    model_weights_redistribution_allowed: bool = False


class EntityRolesPayload(BaseModel):
    kind: Literal["entity_roles"] = "entity_roles"
    tokens: list[str]
    entity_labels: list[str]
    role_labels: list[str]
    token_offsets: list[tuple[int, int]] | None = None
    normalized_text: str | None = None

    @model_validator(mode="after")
    def lengths(self) -> EntityRolesPayload:
        n = len(self.tokens)
        if len(self.entity_labels) != n:
            raise ValueError(f"entity_labels length {len(self.entity_labels)} != tokens {n}")
        if len(self.role_labels) != n:
            raise ValueError(f"role_labels length {len(self.role_labels)} != tokens {n}")
        if self.token_offsets is not None and len(self.token_offsets) != n:
            raise ValueError("token_offsets length mismatch")
        return self


class TaskRecord(BaseModel):
    """Canonical task record written as one JSONL line."""

    record_id: str
    task_type: str
    source: SourceIdentity
    split: Literal["train", "validation", "test", "trial"]
    split_authority: str
    leakage_group: str
    supervision_source: SupervisionSource
    authority_level: AuthorityLevel
    allowed_uses: list[str]
    forbidden_uses: list[str]
    licence: LicenseUseDecision
    training_eligible: bool
    evaluation_eligible: bool
    requires_review: bool
    transform_lineage: TransformLineage
    checksum: str
    payload: EntityRolesPayload

    @model_validator(mode="after")
    def invariants(self) -> TaskRecord:
        if not self.leakage_group.strip():
            raise ValueError("leakage_group required")
        if not self.source.dataset:
            raise ValueError("missing source identity")
        if (
            not self.source.document_id
            and not self.source.segment_id
            and not self.source.source_record_id
        ):
            raise ValueError("missing source identity")
        if self.split in {"test", "trial"} and self.training_eligible:
            raise ValueError("TEST/trial cannot be training_eligible")
        if self.authority_level == AuthorityLevel.NTRUTH_GOLD:
            raise ValueError("public adapters must not emit NTRUTH_GOLD")
        if self.supervision_source == SupervisionSource.SYNTHETIC:
            # C0-C1: synthetic forbidden at 0%
            raise ValueError("SYNTHETIC records forbidden in C0-C1")
        if self.licence.license_status == LicenseStatus.UNKNOWN and self.training_eligible:
            raise ValueError("UNKNOWN licence cannot be training_eligible")
        if not self.licence.training_allowed and self.training_eligible:
            raise ValueError("training_eligible requires licence.training_allowed")
        if self.evaluation_eligible and self.licence.evaluation_allowed is not True:
            raise ValueError(
                "evaluation_eligible requires licence.evaluation_allowed=true "
                "(unknown/false fail closed)"
            )
        if self.training_eligible and self.licence.development_allowed is not True:
            # Weight updates and iterative development both require explicit development.
            raise ValueError(
                "training_eligible requires licence.development_allowed=true "
                "(unknown/false fail closed)"
            )
        if self.authority_level == AuthorityLevel.AUXILIARY:
            for ban in (
                "experimental_unit_gold",
                "independent_n_gold",
                "pseudoreplication_verdict_gold",
                "allocation_gold",
                "biological_independence_gold",
                "interference_gold",
                "estimand_gold",
            ):
                if ban not in self.forbidden_uses:
                    raise ValueError(f"AUXILIARY records must forbid {ban}")
        return self


class ExclusionRecord(BaseModel):
    source_path: str
    source_record_id: str | None = None
    reason: str
    detail: str = ""
    split: str | None = None
    leakage_group: str | None = None


class BuildManifest(BaseModel):
    task_type: str
    source_dataset: str
    source_version: str
    adapter: str
    schema_version: str
    transform_version: str
    mapping_version: str
    seed: str
    root: str
    output_dir: str
    record_counts: dict[str, int]
    exclusion_counts: dict[str, int]
    records_sha256: str
    previous_records_sha256: str | None = None
    change_reason: str | None = None
    content_lineage: list[dict[str, str]] = Field(default_factory=list)
    groups_crossing_splits: int = Field(
        ...,
        description="Count of leakage_group values that appear in more than one split",
    )
    # Upstream SourceData partitions are preserved but not approved N-Truth model-use splits.
    partition_origin: str = "UPSTREAM_SOURCEDATA"
    partition_preserved: bool = True
    ntruth_partition_approved: bool = False
    model_use_status: str = "BLOCKED"
    # PRD v7 readiness triad (dataset-side provisional; full Reality Gate is root-owned).
    engineering_readiness: str = "VERIFIED_FOR_C0_C1"
    data_readiness: str = "BLOCKED"
    scientific_validation: str = "NOT_STARTED"
    reality_gate_status: str = "BLOCKED"
    reality_gate_ref: str = "prd_v7_section_0.7_provisional_dataset_manifest"
    # Explicit: public/silver engineering success does not satisfy Reality Gate.
    reality_gate_satisfied_by_public_corpora: bool = False
    reality_gate_satisfied_by_silver_adapter: bool = False
    # Optional projection dump from DatasetReadinessProjection (manifest-only metadata).
    dataset_readiness_projection: dict[str, object] | None = None
    leakage_group_granularity: str = "RECORD_LEVEL_FALLBACK"
    paper_level_leakage_claim_allowed: bool = False
    manifest_version: str = "0.2.2"
    synthetic_fraction: float = 0.0
    # Additive in 0.3.0: typed external provenance sidecar block. Absence
    # means no sidecar exists (backward compatible); presence requires
    # manifest_version >= 0.3.0 and satisfies every ProvenanceSidecarManifest
    # invariant. Permissive dict payloads are rejected.
    provenance_sidecar: ProvenanceSidecarManifest | None = None

    @model_validator(mode="after")
    def sidecar_block_requires_version_bump(self) -> BuildManifest:
        if self.provenance_sidecar is not None:
            parts = [int(x) for x in self.manifest_version.split(".") if x.isdigit()]
            if parts < [0, 3, 0]:
                raise ValueError("provenance_sidecar requires manifest_version >= 0.3.0")
        return self
