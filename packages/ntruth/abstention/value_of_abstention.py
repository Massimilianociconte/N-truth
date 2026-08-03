"""Value-of-Abstention contract (PRD v7 §6.4, §23.2, FR-060…FR-065).

Ogni risultato non DETERMINATE deve esporre gli undici elementi del contratto.
Una risposta vuota "cannot determine" e un output di prodotto NON valido.
"""

from __future__ import annotations

from typing import Self

from pydantic import model_validator

from ntruth.schemas.core import FrozenModel
from ntruth.schemas.determinability_v7 import DeterminabilityStateV7, is_non_determinate


class PlausibleScenario(FrozenModel):
    """Uno scenario plausibile con la propria conseguenza."""

    description: str
    consequence: str


class AbstentionReport(FrozenModel):
    """Contratto completo di astensione (PRD v7 §23.2)."""

    state: DeterminabilityStateV7
    observed_facts: tuple[str, ...]  # 1. cio che e osservato
    author_assertions: tuple[str, ...]  # 2. cio che e assertion
    candidate_model_facts: tuple[str, ...]  # 3. candidati AI (mai verdetti)
    missing_decisive_fact: str  # 4. cio che manca
    plausible_scenarios: tuple[PlausibleScenario, ...]  # 5+6. alternative e impatto
    primary_question: str  # 7. domanda operativa
    reporting_improvement: str  # 8. Methods/sample-sheet improvement
    inference_limit: str  # 9. limite di inferenza
    useful_artefacts: tuple[str, ...]  # 10. artefatti ancora utilizzabili
    recommended_next_action: str  # 11. prossima azione

    @model_validator(mode="after")
    def _contract_complete(self) -> Self:
        if not is_non_determinate(self.state):
            raise ValueError("abstention report ammesso solo per stati non DETERMINATE")
        if not self.missing_decisive_fact.strip():
            raise ValueError("astensione senza fatto decisivo mancante")
        if not self.plausible_scenarios:
            raise ValueError("astensione senza scenari plausibili")
        if any(
            not s.description.strip() or not s.consequence.strip() for s in self.plausible_scenarios
        ):
            raise ValueError("scenario senza descrizione o conseguenza")
        if not self.primary_question.strip():
            raise ValueError("astensione senza domanda primaria")
        if not self.reporting_improvement.strip():
            raise ValueError("astensione senza proposta di reporting improvement")
        if not self.inference_limit.strip():
            raise ValueError("astensione senza limite di inferenza")
        if not self.useful_artefacts:
            raise ValueError("astensione senza artefatti utilizzabili")
        if not self.recommended_next_action.strip():
            raise ValueError("astensione senza prossima azione raccomandata")
        return self

    @property
    def is_empty_abstention(self) -> bool:
        """Un 'cannot determine' vuoto e invalido per contratto."""
        return not self.missing_decisive_fact.strip()


def empty_abstention_is_invalid(state: DeterminabilityStateV7) -> bool:
    """Regola di prodotto: per ogni stato non DETERMINATE serve il contratto pieno."""
    return is_non_determinate(state)
