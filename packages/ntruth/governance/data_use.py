"""Granular data-use grants (PRD v9 section 14.8 and Appendix E).

A grant records the permission scope for one source family without importing
the pinned knowledge contracts: retention uses a local minimal
PRESENT/UNKNOWN wrapper.  Every decision helper is fail-closed: an unlisted
use is denied, not defaulted.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Self

from pydantic import model_validator

from ntruth.schemas.core import FrozenModel
from ntruth.schemas.kernel import NonBlankStr


class TypedKnowledgeState(StrEnum):
    PRESENT = "PRESENT"
    UNKNOWN = "UNKNOWN"


class TypedKnowledgeValue[T](FrozenModel):
    """Minimal open-world wrapper; deliberately independent from schemas.knowledge."""

    knowledge_state: TypedKnowledgeState = TypedKnowledgeState.UNKNOWN
    value: T | None = None

    @model_validator(mode="after")
    def _state_and_value_agree(self) -> Self:
        if self.knowledge_state is TypedKnowledgeState.PRESENT and self.value is None:
            raise ValueError("a PRESENT typed knowledge value requires a value")
        if self.knowledge_state is TypedKnowledgeState.UNKNOWN and self.value is not None:
            raise ValueError("an UNKNOWN typed knowledge value cannot carry a value")
        return self


class DataUseKind(StrEnum):
    ANNOTATION = "ANNOTATION"
    PARSER_TRAINING = "PARSER_TRAINING"
    THEORY_REFERENCE = "THEORY_REFERENCE"
    EXTERNAL_EVALUATION = "EXTERNAL_EVALUATION"
    REDISTRIBUTION = "REDISTRIBUTION"
    FACSIMILE_RENDERING = "FACSIMILE_RENDERING"


class RevocationPolicy(StrEnum):
    FUTURE_VERSIONS_ONLY = "FUTURE_VERSIONS_ONLY"
    IMMEDIATE = "IMMEDIATE"
    NOT_REVOCABLE = "NOT_REVOCABLE"


class DerivativeArtifactPolicy(StrEnum):
    ALLOWED_WITH_LINEAGE = "ALLOWED_WITH_LINEAGE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    PROHIBITED = "PROHIBITED"


class PermittedUses(FrozenModel):
    annotation: bool = False
    parser_training: bool = False
    theory_reference: bool = False
    external_evaluation: bool = False
    redistribution: bool = False
    facsimile_rendering: bool = False


_USE_FLAG_NAMES: dict[DataUseKind, str] = {
    DataUseKind.ANNOTATION: "annotation",
    DataUseKind.PARSER_TRAINING: "parser_training",
    DataUseKind.THEORY_REFERENCE: "theory_reference",
    DataUseKind.EXTERNAL_EVALUATION: "external_evaluation",
    DataUseKind.REDISTRIBUTION: "redistribution",
    DataUseKind.FACSIMILE_RENDERING: "facsimile_rendering",
}


class DataUseGrant(FrozenModel):
    """Permission scope for one source family, verified by a named reviewer."""

    grant_id: NonBlankStr
    source_family_id: NonBlankStr
    contributor_actor_id: NonBlankStr
    custodian_actor_id: NonBlankStr
    permission_basis: NonBlankStr
    permitted_uses: PermittedUses = PermittedUses()
    retention_until: TypedKnowledgeValue[date]
    revocation_policy: RevocationPolicy
    derivative_artifact_policy: DerivativeArtifactPolicy
    cloud_use_allowed: bool = False
    verified_by: NonBlankStr


def authorize_use(
    grant: DataUseGrant,
    use: DataUseKind,
    *,
    as_of: date | None = None,
) -> bool:
    """Return True only for explicitly listed uses inside the retention window."""
    if _USE_FLAG_NAMES.get(use) is None:
        return False
    if getattr(grant.permitted_uses, _USE_FLAG_NAMES[use], False) is not True:
        return False
    if as_of is not None:
        retention = grant.retention_until
        if (
            retention.knowledge_state is TypedKnowledgeState.PRESENT
            and retention.value is not None
            and as_of > retention.value
        ):
            return False
    return True


def retention_expired(grant: DataUseGrant, as_of: date) -> bool | None:
    """True/False when retention is known; None when it stays UNKNOWN."""
    retention = grant.retention_until
    if retention.knowledge_state is not TypedKnowledgeState.PRESENT or retention.value is None:
        return None
    return as_of > retention.value


__all__ = [
    "DataUseGrant",
    "DataUseKind",
    "DerivativeArtifactPolicy",
    "PermittedUses",
    "RevocationPolicy",
    "TypedKnowledgeState",
    "TypedKnowledgeValue",
    "authorize_use",
    "retention_expired",
]
