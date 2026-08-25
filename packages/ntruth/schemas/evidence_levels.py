"""Evidence support levels v7 (PRD v7 §9.5)."""

from __future__ import annotations

from enum import StrEnum

from ntruth.schemas.core import EvidenceType


class EvidenceSupportLevel(StrEnum):
    DIRECT = "DIRECT"
    STRUCTURED_DIRECT = "STRUCTURED_DIRECT"
    AUTHOR_ASSERTED = "AUTHOR_ASSERTED"
    INFERRED_CANDIDATE = "INFERRED_CANDIDATE"
    CONFIRMED = "CONFIRMED"
    ADJUDICATED = "ADJUDICATED"
    CONFLICTING = "CONFLICTING"
    NOT_REPORTED = "NOT_REPORTED"
    UNKNOWN = "UNKNOWN"


NON_CONCLUSIVE_LEVELS: frozenset[EvidenceSupportLevel] = frozenset(
    {
        EvidenceSupportLevel.AUTHOR_ASSERTED,
        EvidenceSupportLevel.INFERRED_CANDIDATE,
        EvidenceSupportLevel.NOT_REPORTED,
        EvidenceSupportLevel.UNKNOWN,
        EvidenceSupportLevel.STRUCTURED_DIRECT,
    }
)

HUMAN_AUTHORED_LEVELS: frozenset[EvidenceSupportLevel] = frozenset(
    {EvidenceSupportLevel.CONFIRMED, EvidenceSupportLevel.ADJUDICATED}
)


def statistical_code_level() -> EvidenceSupportLevel:
    return EvidenceSupportLevel.STRUCTURED_DIRECT


def statistical_code_closes_determinability() -> bool:
    return False


def default_level_for_type(evidence_type: EvidenceType | None) -> EvidenceSupportLevel:
    if evidence_type is None:
        return EvidenceSupportLevel.UNKNOWN
    mapping: dict[EvidenceType, EvidenceSupportLevel] = {
        EvidenceType.STRUCTURAL_FACT: EvidenceSupportLevel.DIRECT,
        EvidenceType.SAMPLE_METADATA: EvidenceSupportLevel.STRUCTURED_DIRECT,
        EvidenceType.AUTHOR_ASSERTION: EvidenceSupportLevel.AUTHOR_ASSERTED,
        EvidenceType.MODEL_INFERENCE: EvidenceSupportLevel.INFERRED_CANDIDATE,
        EvidenceType.CONFLICTING_EVIDENCE: EvidenceSupportLevel.CONFLICTING,
        EvidenceType.USER_CONFIRMATION: EvidenceSupportLevel.INFERRED_CANDIDATE,
        EvidenceType.STATISTICAL_CODE: EvidenceSupportLevel.STRUCTURED_DIRECT,
        EvidenceType.DERIVED_FACT: EvidenceSupportLevel.INFERRED_CANDIDATE,
    }
    return mapping.get(evidence_type, EvidenceSupportLevel.UNKNOWN)
