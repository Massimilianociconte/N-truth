"""Canonical task-record schemas for Workstream C corpora."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, model_validator

from ntruth.task_corpora.authority import (
    AuthorityLevel,
    LicenseStatus,
    SupervisionSource,
)


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
    license_status: LicenseStatus
    training_allowed: bool
    redistribution_allowed: bool
    derived_labels_allowed: bool
    decision_basis: str
    reviewed_at: str
    spdx: str | None = None


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
        if self.authority_level == AuthorityLevel.AUXILIARY:
            for ban in (
                "experimental_unit_gold",
                "independent_n_gold",
                "pseudoreplication_verdict_gold",
                "allocation_gold",
                "biological_independence_gold",
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
    transform_version: str
    mapping_version: str
    seed: str
    root: str
    output_dir: str
    record_counts: dict[str, int]
    exclusion_counts: dict[str, int]
    records_sha256: str
    manifest_version: str = "0.1.0"
    synthetic_fraction: float = 0.0
