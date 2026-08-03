"""Modello di autorita umana e conflitto (PRD v7 §0.3, §0.4, §8.6, NFR-25).

Una fonte di livello superiore NON cancella una fonte incompatibile: genera o
aggiorna un ConflictRecord. Gli eventi di autorita sono append-only e immutabili.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from ntruth.schemas.core import FrozenModel, content_checksum, stable_id


class AuthorityType(StrEnum):
    """Tipi di autorita (PRD v7 §0.4)."""

    SYSTEM_INFERENCE = "SYSTEM_INFERENCE"
    ANNOTATOR_CONFIRMATION = "ANNOTATOR_CONFIRMATION"
    USER_CONFIRMATION = "USER_CONFIRMATION"
    AUTHOR_CLARIFICATION = "AUTHOR_CLARIFICATION"
    DOMAIN_EXPERT_REVIEW = "DOMAIN_EXPERT_REVIEW"
    EXPERT_ADJUDICATION = "EXPERT_ADJUDICATION"
    RULE_DERIVATION = "RULE_DERIVATION"


#: Ordine di precedenza tra tipi di autorita (PRD v7 §0.3, livelli 2-6).
#: Le regole scientifiche approvate precedono tutto e vivono nel ruleset, non qui.
#: Indice minore = precedenza maggiore. SYSTEM_INFERENCE e RULE_DERIVATION non
#: sono fonti di verita e restano fuori classifica.
AUTHORITY_PRECEDENCE: tuple[AuthorityType, ...] = (
    AuthorityType.EXPERT_ADJUDICATION,
    AuthorityType.AUTHOR_CLARIFICATION,
    AuthorityType.DOMAIN_EXPERT_REVIEW,
    AuthorityType.ANNOTATOR_CONFIRMATION,
    AuthorityType.USER_CONFIRMATION,
)

ConflictStatus = Literal["unresolved", "resolved_with_rationale"]


class ConfirmationEvent(FrozenModel):
    """Evento append-only di conferma o chiarimento autorevole (PRD v7 §8.6).

    ``source_ref`` deve essere un riferimento opaco (es. ``email_2026_08_03``):
    il contenuto della corrispondenza privata non entra mai nel record pubblico.
    """

    id: str
    authority_type: AuthorityType
    actor_role: str  # ruolo, mai identita personale (convenzione Provenance)
    scope: str  # campo, relazione o evento interessato
    statement: str
    source_ref: str | None = None
    rationale: str = ""
    evidence_ids: tuple[str, ...] = ()
    affects_decisive_field: bool = False
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def _timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at deve includere il fuso orario")
        return value

    @model_validator(mode="after")
    def _authority_constraints(self) -> Self:
        if self.authority_type is AuthorityType.RULE_DERIVATION:
            raise ValueError(
                "RULE_DERIVATION e una conseguenza del ruleset, mai una fonte di evidenza"
            )
        if not self.scope.strip():
            raise ValueError("evento di autorita senza scope dichiarato")
        if not self.statement.strip():
            raise ValueError("evento di autorita senza statement")
        if self.authority_type is AuthorityType.EXPERT_ADJUDICATION and not self.rationale.strip():
            raise ValueError("EXPERT_ADJUDICATION richiede rationale esplicita")
        return self

    def event_hash(self) -> str:
        return content_checksum(self.model_dump(mode="json"))


class ConflictRecord(FrozenModel):
    """Conflitto tra fonti: resta registrato anche dopo la risoluzione (PRD v7 §0.3)."""

    id: str
    field: str
    sources: tuple[str, ...] = Field(min_length=2)
    authority_types: tuple[AuthorityType, ...] = ()
    scope: str = ""
    decision: str = ""
    rationale: str = ""
    status: ConflictStatus = "unresolved"
    resolution_event_id: str | None = None
    determinability_impact: str = ""
    requires_new_evidence: bool = False

    @model_validator(mode="after")
    def _resolution_requires_rationale(self) -> Self:
        if len(set(self.sources)) != len(self.sources):
            raise ValueError("conflict sources duplicate")
        if self.status == "resolved_with_rationale":
            if self.resolution_event_id is None:
                raise ValueError("conflitto risolto senza resolution_event")
            if not self.rationale.strip():
                raise ValueError("conflitto risolto senza rationale")
            if not self.decision.strip():
                raise ValueError("conflitto risolto senza decisione adottata")
        if self.status == "unresolved" and self.resolution_event_id is not None:
            raise ValueError("conflitto irrisolto non puo referenziare un resolution_event")
        return self


class AuthorityLedger(FrozenModel):
    """Registro append-only di eventi e conflitti.

    Ogni modifica restituisce un nuovo ledger: nessun evento puo essere rimosso
    o sovrascritto (NFR-25). Un'autorita superiore non elimina l'evidenza
    incompatibile: aggiunge eventi e, se necessario, conflitti risolti.
    """

    ledger_id: str
    confirmations: tuple[ConfirmationEvent, ...] = ()
    conflicts: tuple[ConflictRecord, ...] = ()

    def append_confirmation(self, event: ConfirmationEvent) -> AuthorityLedger:
        if any(existing.id == event.id for existing in self.confirmations):
            raise ValueError(f"evento {event.id} gia presente: append-only")
        return AuthorityLedger(
            ledger_id=self.ledger_id,
            confirmations=(*self.confirmations, event),
            conflicts=self.conflicts,
        )

    def append_conflict(self, conflict: ConflictRecord) -> AuthorityLedger:
        if any(existing.id == conflict.id for existing in self.conflicts):
            raise ValueError(f"conflitto {conflict.id} gia presente: append-only")
        return AuthorityLedger(
            ledger_id=self.ledger_id,
            confirmations=self.confirmations,
            conflicts=(*self.conflicts, conflict),
        )

    def resolve_conflict(
        self, conflict_id: str, resolution_event: ConfirmationEvent, decision: str, rationale: str
    ) -> AuthorityLedger:
        """Risolve un conflitto conservandolo: nessuna cancellazione silenziosa."""
        target = next((c for c in self.conflicts if c.id == conflict_id), None)
        if target is None:
            raise ValueError(f"conflitto {conflict_id} non registrato")
        if target.status == "resolved_with_rationale":
            raise ValueError(f"conflitto {conflict_id} gia risolto: append-only")
        resolved = ConflictRecord(
            id=target.id,
            field=target.field,
            sources=target.sources,
            authority_types=target.authority_types,
            scope=target.scope,
            decision=decision,
            rationale=rationale,
            status="resolved_with_rationale",
            resolution_event_id=resolution_event.id,
            determinability_impact=target.determinability_impact,
            requires_new_evidence=target.requires_new_evidence,
        )
        ledger = self.append_confirmation(resolution_event)
        return AuthorityLedger(
            ledger_id=self.ledger_id,
            confirmations=ledger.confirmations,
            conflicts=tuple(resolved if c.id == conflict_id else c for c in ledger.conflicts),
        )

    def unresolved_conflicts(self, fields: frozenset[str] | None = None) -> tuple[ConflictRecord, ...]:
        return tuple(
            c
            for c in self.conflicts
            if c.status == "unresolved" and (fields is None or c.field in fields)
        )

    def blocks_determinate(self, decisive_fields: frozenset[str]) -> bool:
        """Un conflitto irrisolto su un campo decisivo blocca DETERMINATE (PRD v7 §10.9)."""
        return any(c.field in decisive_fields for c in self.unresolved_conflicts())


def make_confirmation_id(scope: str, authority: AuthorityType, actor_role: str, statement: str) -> str:
    return stable_id("conf", scope, str(authority), actor_role, statement.strip().lower())


def make_conflict_id(field: str, sources: tuple[str, ...]) -> str:
    return stable_id("cnf", field, *sorted(sources))


def authority_rank(authority: AuthorityType) -> int | None:
    """Precedenza (minore = piu autorevole); None per non-fonti (SYSTEM_INFERENCE, RULE_DERIVATION)."""
    if authority in AUTHORITY_PRECEDENCE:
        return AUTHORITY_PRECEDENCE.index(authority)
    return None


def higher_authority_wins(
    first: AuthorityType, second: AuthorityType
) -> AuthorityType | None:
    """Fonte prevalente secondo §0.3; None se nessuna delle due e una fonte di verita."""
    rank_first = authority_rank(first)
    rank_second = authority_rank(second)
    if rank_first is None and rank_second is None:
        return None
    if rank_first is None:
        return second
    if rank_second is None:
        return first
    return first if rank_first <= rank_second else second
