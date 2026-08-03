"""Evidence support levels v7 (PRD v7 §9.5) sopra gli EvidenceSpan esistenti.

Gli span v3 (``EvidenceType``) restano la classificazione di origine; il livello
di supporto descrive quanta autorita ha quel fatto rispetto alla decisione.
"""

from __future__ import annotations

from enum import StrEnum

from ntruth.schemas.core import EvidenceType


class EvidenceSupportLevel(StrEnum):
    """Nove livelli di supporto (PRD v7 §9.5)."""

    DIRECT = "DIRECT"
    STRUCTURED_DIRECT = "STRUCTURED_DIRECT"
    AUTHOR_ASSERTED = "AUTHOR_ASSERTED"
    INFERRED_CANDIDATE = "INFERRED_CANDIDATE"
    CONFIRMED = "CONFIRMED"
    ADJUDICATED = "ADJUDICATED"
    CONFLICTING = "CONFLICTING"
    NOT_REPORTED = "NOT_REPORTED"
    UNKNOWN = "UNKNOWN"


#: Livelli che non possono mai chiudere DETERMINATE da soli.
NON_CONCLUSIVE_LEVELS: frozenset[EvidenceSupportLevel] = frozenset(
    {
        EvidenceSupportLevel.AUTHOR_ASSERTED,
        EvidenceSupportLevel.INFERRED_CANDIDATE,
        EvidenceSupportLevel.NOT_REPORTED,
        EvidenceSupportLevel.UNKNOWN,
    }
)

#: Livelli che richiedono una conferma umana registrata (authority event).
HUMAN_AUTHORED_LEVELS: frozenset[EvidenceSupportLevel] = frozenset(
    {
        EvidenceSupportLevel.CONFIRMED,
        EvidenceSupportLevel.ADJUDICATED,
    }
)


def default_level_for_type(evidence_type: EvidenceType | None) -> EvidenceSupportLevel:
    """Mapping iniziale tipo -> livello; resta conservativo (fail-closed)."""
    if evidence_type is None:
        return EvidenceSupportLevel.UNKNOWN
    mapping: dict[EvidenceType, EvidenceSupportLevel] = {
        EvidenceType.STRUCTURAL_FACT: EvidenceSupportLevel.DIRECT,
        EvidenceType.SAMPLE_METADATA: EvidenceSupportLevel.STRUCTURED_DIRECT,
        EvidenceType.AUTHOR_ASSERTION: EvidenceSupportLevel.AUTHOR_ASSERTED,
        EvidenceType.MODEL_INFERENCE: EvidenceSupportLevel.INFERRED_CANDIDATE,
        EvidenceType.CONFLICTING_EVIDENCE: EvidenceSupportLevel.CONFLICTING,
        EvidenceType.USER_CONFIRMATION: EvidenceSupportLevel.CONFIRMED,
        EvidenceType.STATISTICAL_CODE: EvidenceSupportLevel.STRUCTURED_DIRECT,
        EvidenceType.DERIVED_FACT: EvidenceSupportLevel.DIRECT,
    }
    return mapping.get(evidence_type, EvidenceSupportLevel.UNKNOWN)
