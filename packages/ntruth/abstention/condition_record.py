"""ConditionRecord bilingue per output condizionali (PRD v7 §10.8).

Estende il contratto v3 ``ConditionalScenario`` con: predicate nominato, testo
IT/EN, evidenza richiesta, effetti if-true/if-false e domanda primaria. Il
limite di una domanda primaria + massimo due secondarie e un target UX
PROVISIONAL, non una regola scientifica.
"""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from ntruth.schemas.core import FrozenModel, stable_id


class BilingualText(FrozenModel):
    """Testo leggibile in italiano e inglese (PRD v7 §10.3: comprensibile a un biologo)."""

    it: str
    en: str

    @model_validator(mode="after")
    def _non_empty(self) -> Self:
        if not self.it.strip() or not self.en.strip():
            raise ValueError("testo bilingue incompleto")
        return self


class ConditionRecord(FrozenModel):
    """Predicato decisivo mancante con conseguenze esplicite (PRD v7 §10.8)."""

    id: str
    predicate: str
    human_readable: BilingualText
    evidence_required: tuple[str, ...] = ()
    if_true_effect: str
    if_false_effect: str
    primary_question_id: str
    rule_id: str = ""
    rationale: str = ""

    @model_validator(mode="after")
    def _complete(self) -> Self:
        if not self.predicate.strip():
            raise ValueError("condition record senza predicate")
        if not self.if_true_effect.strip() or not self.if_false_effect.strip():
            raise ValueError("condition record senza effetti if-true/if-false")
        if not self.primary_question_id.strip():
            raise ValueError("condition record senza domanda primaria")
        return self


class QuestionPriority(FrozenModel):
    """Limite PROVISIONAL: 1 primaria + <=2 secondarie (PRD v7 §10.8)."""

    primary: ConditionRecord
    secondary: tuple[ConditionRecord, ...] = Field(default=(), max_length=2)

    @model_validator(mode="after")
    def _distinct_predicates(self) -> Self:
        predicates = [self.primary.predicate, *(c.predicate for c in self.secondary)]
        if len(set(predicates)) != len(predicates):
            raise ValueError("domande secondarie duplicano il predicato primario")
        return self


def make_condition_id(predicate: str, block_id: str) -> str:
    return stable_id("cond", block_id, predicate)
