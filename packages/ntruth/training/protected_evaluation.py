"""Custodial TEST/EXTERNAL_CHALLENGE snapshot contract (PRD v8 sections 24-25).

This is deliberately separate from the physical training snapshot.  Task 5
validates custody and lineage pins but cannot authorize External Challenge use;
that decision remains blocked on Task 7's reviewed ContaminationAttestation.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal, Protocol, Self, runtime_checkable

from pydantic import Field, model_validator

from ntruth.governance.contamination import ExternalChallengeUseEvaluationV8
from ntruth.schemas.core import FrozenModel, content_checksum
from ntruth.training.custody import ExternalChallengeDependency
from ntruth.training.mlx_runtime import MLXPipelineError, sha256_file
from ntruth.training.records import DatasetManifest


class ProtectedEvaluationLineage(FrozenModel):
    source_manifest_id: str
    source_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    planned_design_artifact_id: str
    planned_design_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    executed_design_artifact_id: str
    executed_design_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    custody_reference_id: str
    custody_reference_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _ids_are_explicit(self) -> Self:
        identifiers = (
            self.source_manifest_id,
            self.planned_design_artifact_id,
            self.executed_design_artifact_id,
            self.custody_reference_id,
        )
        if any(not value.strip() for value in identifiers):
            raise ValueError("protected evaluation lineage ids must not be blank")
        return self


class ProtectedEvaluationSnapshotManifest(FrozenModel):
    schema_version: Literal["8.0.0"] = "8.0.0"
    snapshot_id: str = ""
    snapshot_sha256: str = ""
    split: Literal["TEST", "EXTERNAL_CHALLENGE"]
    purpose: Literal["CUSTODIAL_EVALUATION"]
    payload_file: Literal["test.jsonl", "external-challenge.jsonl"]
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload_size_bytes: int = Field(ge=0)
    record_count: int = Field(ge=1)
    record_ids_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    lineage: ProtectedEvaluationLineage
    external_challenge_dependency: ExternalChallengeDependency | None = None

    def identity_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"snapshot_id", "snapshot_sha256"})

    @model_validator(mode="after")
    def _content_addressed_and_scoped(self) -> Self:
        expected_file = "test.jsonl" if self.split == "TEST" else "external-challenge.jsonl"
        if self.payload_file != expected_file:
            raise ValueError("protected evaluation split/file mismatch")
        if self.split == "TEST" and self.external_challenge_dependency is not None:
            raise ValueError("TEST snapshot cannot carry an External Challenge dependency")
        if self.split == "EXTERNAL_CHALLENGE" and self.external_challenge_dependency is None:
            raise ValueError("EXTERNAL_CHALLENGE requires Task 7 dependency pins")
        checksum = content_checksum(self.identity_payload())
        expected_id = f"protected-evaluation-{checksum[:20]}"
        if self.snapshot_sha256 and self.snapshot_sha256 != checksum:
            raise ValueError("protected evaluation snapshot checksum mismatch")
        if self.snapshot_id and self.snapshot_id != expected_id:
            raise ValueError("protected evaluation snapshot id mismatch")
        object.__setattr__(self, "snapshot_sha256", checksum)
        object.__setattr__(self, "snapshot_id", expected_id)
        return self


class ProtectedEvaluationReviewRequired(MLXPipelineError):
    """An authoritative custodial dependency is missing or unresolved."""


class ExternalChallengeReviewRequired(ProtectedEvaluationReviewRequired):
    """Task 7 authority/custody review is a mandatory unresolved dependency."""


@runtime_checkable
class ExternalChallengeUseAuthorityV8Protocol(Protocol):
    """Read-only resolver configured outside the custodial payload directory."""

    def resolve_external_challenge_use(
        self, manifest: ProtectedEvaluationSnapshotManifest
    ) -> ExternalChallengeUseEvaluationV8 | Mapping[str, Any]: ...


def _require_external_challenge_authority_before_payload(
    manifest: ProtectedEvaluationSnapshotManifest,
    authority: ExternalChallengeUseAuthorityV8Protocol | None,
) -> None:
    if authority is None or not isinstance(authority, ExternalChallengeUseAuthorityV8Protocol):
        raise ExternalChallengeReviewRequired(
            "SCIENTIFIC_REVIEW_REQUIRED: external Task 7 use authority is absent"
        )
    try:
        evaluation = ExternalChallengeUseEvaluationV8.model_validate(
            authority.resolve_external_challenge_use(manifest)
        )
    except (TypeError, ValueError) as exc:
        raise ExternalChallengeReviewRequired(
            f"SCIENTIFIC_REVIEW_REQUIRED: external Task 7 use authority invalid: {exc}"
        ) from exc
    dependency = manifest.external_challenge_dependency
    if dependency is None:
        raise ExternalChallengeReviewRequired(
            "SCIENTIFIC_REVIEW_REQUIRED: External Challenge dependency pins are absent"
        )
    expected = {
        "snapshot_id": manifest.snapshot_id,
        "snapshot_sha256": manifest.snapshot_sha256,
        "source_manifest_id": manifest.lineage.source_manifest_id,
        "source_manifest_sha256": manifest.lineage.source_manifest_sha256,
        "record_ids_checksum": manifest.record_ids_checksum,
        "attestation_id": dependency.task7_contamination_attestation_reference.artifact_id,
        "attestation_sha256": dependency.task7_contamination_attestation_reference.sha256,
        "access_ledger_id": dependency.custody_reference.artifact_id,
        "access_ledger_sha256": dependency.custody_reference.sha256,
    }
    mismatches = tuple(
        field_name
        for field_name, expected_value in expected.items()
        if getattr(evaluation, field_name) != expected_value
    )
    if mismatches:
        raise ExternalChallengeReviewRequired(
            "SCIENTIFIC_REVIEW_REQUIRED: External Challenge authority pin mismatch: "
            + repr(mismatches)
        )
    # The v8 contract deliberately has no repository-local grant capability.
    if not evaluation.use_authorized:
        raise ExternalChallengeReviewRequired(
            "SCIENTIFIC_REVIEW_REQUIRED: External Challenge use remains HOLD"
        )
    raise ExternalChallengeReviewRequired(
        "SCIENTIFIC_REVIEW_REQUIRED: repository-local External Challenge grants are forbidden"
    )


def validate_protected_source_manifest(
    source_manifest_path: Path,
    manifest: ProtectedEvaluationSnapshotManifest,
) -> DatasetManifest:
    """Resolve the independently content-addressed source DatasetManifest."""

    source_manifest_path = source_manifest_path.resolve()
    if source_manifest_path.is_symlink() or not source_manifest_path.is_file():
        raise MLXPipelineError("protected evaluation source DatasetManifest is absent")
    if sha256_file(source_manifest_path) != manifest.lineage.source_manifest_sha256:
        raise MLXPipelineError("protected evaluation source DatasetManifest checksum mismatch")
    try:
        source_manifest = DatasetManifest.model_validate_json(
            source_manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        raise MLXPipelineError(
            f"protected evaluation source DatasetManifest invalid: {exc}"
        ) from exc
    if source_manifest.dataset_id != manifest.lineage.source_manifest_id:
        raise MLXPipelineError("protected evaluation source DatasetManifest identity mismatch")
    return source_manifest


def validate_protected_evaluation_snapshot(
    data_dir: Path,
    *,
    declared_split: str,
    source_manifest_path: Path | None = None,
    external_challenge_authority: ExternalChallengeUseAuthorityV8Protocol | None = None,
) -> ProtectedEvaluationSnapshotManifest:
    root = data_dir.resolve()
    manifest_path = root / "protected-evaluation-manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise MLXPipelineError("protected evaluation manifest absent or symlink not allowed")
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = ProtectedEvaluationSnapshotManifest.model_validate(raw)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise MLXPipelineError(f"protected evaluation manifest invalid: {exc}") from exc
    canonical_split = declared_split.upper()
    if canonical_split != manifest.split:
        raise MLXPipelineError("protected evaluation declared split mismatch")
    if manifest.split == "EXTERNAL_CHALLENGE":
        _require_external_challenge_authority_before_payload(manifest, external_challenge_authority)
    expected_names = {"protected-evaluation-manifest.json", manifest.payload_file}
    entries = tuple(root.iterdir())
    if {entry.name for entry in entries} != expected_names:
        raise MLXPipelineError("protected evaluation physical allowlist mismatch")
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise MLXPipelineError("protected evaluation entries must be regular files")
    payload_path = root / manifest.payload_file
    if payload_path.stat().st_size != manifest.payload_size_bytes:
        raise MLXPipelineError("protected evaluation payload size mismatch")
    if sha256_file(payload_path) != manifest.payload_sha256:
        raise MLXPipelineError("protected evaluation payload checksum mismatch")
    if source_manifest_path is None:
        raise ProtectedEvaluationReviewRequired(
            "SCIENTIFIC_REVIEW_REQUIRED: authoritative source DatasetManifest path is required"
        )
    resolved_source = source_manifest_path.resolve()
    if resolved_source.is_relative_to(root):
        raise ProtectedEvaluationReviewRequired(
            "SCIENTIFIC_REVIEW_REQUIRED: source DatasetManifest must be resolved "
            "independently from the custodial payload directory"
        )
    source_manifest = validate_protected_source_manifest(resolved_source, manifest)
    record_ids: list[str] = []
    try:
        for line_number, line in enumerate(
            payload_path.read_text(encoding="utf-8").splitlines(), 1
        ):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict) or not isinstance(row.get("record_id"), str):
                raise ValueError(f"row {line_number} has no record_id")
            record_ids.append(row["record_id"])
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise MLXPipelineError(f"protected evaluation payload invalid: {exc}") from exc
    if len(record_ids) != manifest.record_count or len(record_ids) != len(set(record_ids)):
        raise MLXPipelineError("protected evaluation record count/identity mismatch")
    if content_checksum(sorted(record_ids)) != manifest.record_ids_checksum:
        raise MLXPipelineError("protected evaluation record ids checksum mismatch")
    source_members = tuple(
        record for record in source_manifest.records if record.split.value == manifest.split
    )
    source_record_ids = {record.record_id for record in source_members}
    if source_record_ids != set(record_ids):
        raise MLXPipelineError(
            "protected evaluation membership does not exactly match source DatasetManifest"
        )
    if any(record.training_eligible for record in source_members):
        raise MLXPipelineError("protected evaluation source membership is training-eligible")
    if any(record.model_selection_eligible for record in source_members):
        raise MLXPipelineError("protected evaluation source membership can select a model")
    if any(not record.evaluation_eligible for record in source_members):
        raise MLXPipelineError("protected evaluation source membership is not evaluation-eligible")
    return manifest


__all__ = [
    "ExternalChallengeReviewRequired",
    "ExternalChallengeUseAuthorityV8Protocol",
    "ProtectedEvaluationLineage",
    "ProtectedEvaluationReviewRequired",
    "ProtectedEvaluationSnapshotManifest",
    "validate_protected_evaluation_snapshot",
    "validate_protected_source_manifest",
]
