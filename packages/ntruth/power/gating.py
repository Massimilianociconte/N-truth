"""Gate deterministici del planner: EU-eligibility + applicabilita.

- EU gate: il piano conta EU indipendenti solo se FactorRole/CONTRAST
  consentono una ExperimentalUnitClaim assegnata e ancorata a un evento
  di assegnazione (mai da solo cluster di esposizione).
- Applicability gate: decide quando la formula chiusa e giustificata
  (CLOSED_FORM), quando serve simulazione gerarchica (SIMULATION_REQUIRED)
  e quando il piano e bloccato (BLOCKED).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ntruth.power.schema import PowerFamily
from ntruth.schemas.factor_role import ContrastType, FactorRole, eu_claim_permitted
from ntruth.scientific.assignment_anchor import reject_eu_from_exposure_only


@dataclass(frozen=True, slots=True)
class EuGateDecision:
    """Esito del gate EU; mai una validazione scientifica."""

    eu_countable: bool
    denial_reason: str | None


def eu_gate(
    role: FactorRole,
    contrast_type: ContrastType,
    assignment_event_id: str | None,
    exposure_cluster: str | None,
) -> EuGateDecision:
    """Permette conteggi EU solo per intervento assegnato + evento registrato."""

    if not eu_claim_permitted(role, contrast_type):
        return EuGateDecision(
            eu_countable=False,
            denial_reason=(
                "Conteggio EU negato: FactorRole/ContrastType "
                f"{role.value}/{contrast_type.value} non consentono una "
                "ExperimentalUnitClaim (serve ASSIGNED_INTERVENTION + "
                "ASSIGNED_INTERVENTION_EFFECT)."
            ),
        )
    try:
        reject_eu_from_exposure_only(assignment_event_id, exposure_cluster)
    except ValueError as exc:
        return EuGateDecision(eu_countable=False, denial_reason=str(exc))
    return EuGateDecision(eu_countable=True, denial_reason=None)


class Applicability(StrEnum):
    """Stati del gate di applicabilita della formula chiusa."""

    CLOSED_FORM = "CLOSED_FORM"
    CLOSED_FORM_WITH_CLUSTER_DIAGNOSTIC = "CLOSED_FORM_WITH_CLUSTER_DIAGNOSTIC"
    SIMULATION_REQUIRED = "SIMULATION_REQUIRED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class ApplicabilityDecision:
    """Esito del gate di applicabilita con motivo ispezionabile."""

    applicability: Applicability
    reason: str
    blocking: bool


# Famiglie con formula chiusa valida anche con misure ripetute semplici.
_REPEATED_SAFE: frozenset[PowerFamily] = frozenset({PowerFamily.T_PAIRED, PowerFamily.MCNEMAR})


def applicability_gate(
    family: PowerFamily,
    *,
    repeated_measures: bool,
    hierarchical_depth: int,
    cluster_icc_known: bool,
    has_clustering: bool,
) -> ApplicabilityDecision:
    """Decide se la formula chiusa e giustificata per la struttura dichiarata."""

    if hierarchical_depth < 1:
        return ApplicabilityDecision(
            applicability=Applicability.BLOCKED,
            reason="hierarchical_depth deve essere >= 1.",
            blocking=True,
        )
    if repeated_measures and family not in _REPEATED_SAFE:
        return ApplicabilityDecision(
            applicability=Applicability.SIMULATION_REQUIRED,
            reason=(
                f"Misure ripetute con famiglia {family.value}: la formula chiusa "
                "non modella correlazione intra-EU arbitraria, missingness o "
                "sbilanciamento. Serve power via simulazione gerarchica su "
                "modello preregistrato (y = beta*Treatmento + effetti casuali)."
            ),
            blocking=True,
        )
    if hierarchical_depth > 2 or (has_clustering and hierarchical_depth > 1):
        if not cluster_icc_known:
            return ApplicabilityDecision(
                applicability=Applicability.BLOCKED,
                reason=(
                    "Struttura gerarchica con ICC ignota: dichiarare ICC "
                    "(o intervallo per sensitivity) oppure passare a power via "
                    "simulazione. Vietato assumere ICC = 0."
                ),
                blocking=True,
            )
        return ApplicabilityDecision(
            applicability=Applicability.CLOSED_FORM_WITH_CLUSTER_DIAGNOSTIC,
            reason=(
                "Formula chiusa sulle EU indipendenti + diagnostica DEFF. "
                "Il design effect aggiusta varianza/potenza e non ridefinisce "
                "mai l'unita sperimentale."
            ),
            blocking=False,
        )
    return ApplicabilityDecision(
        applicability=Applicability.CLOSED_FORM,
        reason="Struttura compatibile con la formula chiusa sulle EU indipendenti.",
        blocking=False,
    )


__all__ = [
    "Applicability",
    "ApplicabilityDecision",
    "EuGateDecision",
    "applicability_gate",
    "eu_gate",
]
