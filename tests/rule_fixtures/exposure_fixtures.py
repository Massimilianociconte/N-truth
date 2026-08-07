"""Fixture theory-conformant per interference/exposure (§7.15 E, Appendice Y).

Le aspettative codificate qui derivano SOLO dal testo normativo PRD v8.0
(§7.15 E, Appendice Y.1, NFR-26), mai dall'output corrente del Rulebook
(regola anti-circolarita §10.9, tests/THEORY_ASSETS.md).

Tre fixture:
- positiva: interference documented (shared bath) -> caveat estimand/scope;
- negativa (PRD P.5 #21): interference NON cambia EU o il suo count;
- coppia controfattuale minimale (§7.13): stessi record, solo lo stato di
  interference differisce (documented vs no_known_path).
"""

from __future__ import annotations

from ntruth.schemas.kernel import (
    ExposureAssessment,
    ExposureContainer,
    ExposurePathway,
    InterferenceStatus,
    KnowledgeState,
    KnowledgeValue,
)

#: Evidence del blocco sintetico _complete_block (USER_CONFIRMATION).
EVIDENCE_ID = "evidence-allocation"
FACTOR_ID = "factor-treatment"


def shared_bath_documented() -> ExposureAssessment:
    """Positiva: bagno condiviso -> interference documented (Appendice Y)."""
    return ExposureAssessment(
        factor_id=FACTOR_ID,
        exposure_pathway=KnowledgeValue(
            knowledge_state=KnowledgeState.PRESENT,
            value=ExposurePathway.SHARED_MEDIUM,
            evidence_ids=(EVIDENCE_ID,),
        ),
        exposure_container=KnowledgeValue(
            knowledge_state=KnowledgeState.PRESENT,
            value=ExposureContainer.BATH,
            evidence_ids=(EVIDENCE_ID,),
        ),
        interference_status=InterferenceStatus.DOCUMENTED,
        shared_environment=KnowledgeValue(
            knowledge_state=KnowledgeState.PRESENT,
            items=("bath_01",),
            evidence_ids=(EVIDENCE_ID,),
        ),
        evidence_ids=(EVIDENCE_ID,),
    )


def no_known_path() -> ExposureAssessment:
    """Controfattuale: nessun percorso noto dichiarato con evidenza."""
    return ExposureAssessment(
        factor_id=FACTOR_ID,
        interference_status=InterferenceStatus.NO_KNOWN_PATH,
        evidence_ids=(EVIDENCE_ID,),
    )


def silent() -> ExposureAssessment:
    """Silenzio: fail-closed su UNKNOWN (NFR-26), nessuna evidenza."""
    return ExposureAssessment(factor_id=FACTOR_ID)
