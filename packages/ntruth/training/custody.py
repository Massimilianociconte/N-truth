"""Task-5 custody dependency pins; authority remains owned by Task 7."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, model_validator

from ntruth.schemas.core import FrozenModel


class ArtifactReference(FrozenModel):
    artifact_id: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _non_blank(self) -> Self:
        if not self.artifact_id.strip():
            raise ValueError("artifact reference id must not be blank")
        return self


class ExternalChallengeDependency(FrozenModel):
    """Unresolved references only; this object can never authorize evaluation."""

    review_status: Literal["SCIENTIFIC_REVIEW_REQUIRED"]
    task7_contamination_attestation_reference: ArtifactReference
    custody_reference: ArtifactReference
    family_evidence_references: tuple[ArtifactReference, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_family_evidence(self) -> Self:
        ids = tuple(item.artifact_id for item in self.family_evidence_references)
        if len(ids) != len(set(ids)):
            raise ValueError("family evidence references must be unique")
        return self
