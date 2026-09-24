"""Freeze meccanismo per risorse di riferimento esterne (SRR-V8-021, lato codice).

Il registro prescrive: snapshot congelati e hashati delle fonti primarie
(DRIVER/ARRIVE/EDA e affini) con mapping esplicito verso le clausole Theory e
diritti registrati. La chiusura dei diritti e la review indipendente restano
ESTERNE: questo modulo fornisce solo il contratto fail-closed che il custode
usera', con registro inizialmente vuoto e blocker SRR-V8-021 permanentemente
pinned. Un freeze senza risorse e valido ma non sblocca alcun gate.
"""

from __future__ import annotations

from datetime import date

from pydantic import Field, model_validator

from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.support import ScientificReviewRequirement

EXTERNAL_REFERENCE_REVIEW_ISSUE_ID = "SRR-V8-021"
_SHA256_ALPHABET = frozenset("0123456789abcdef")


class ExternalReferenceResource(KernelModel):
    """Una risorsa esterna congelata: identita, hash di retrieval, diritti."""

    resource_id: NonBlankStr
    title: NonBlankStr
    canonical_url: NonBlankStr
    retrieval_sha256: NonBlankStr
    retrieved_at: date
    license_note: NonBlankStr
    mapped_clause_ids: tuple[NonBlankStr, ...] = Field(default=())

    @model_validator(mode="after")
    def _hash_shape_and_mapping(self) -> ExternalReferenceResource:
        if len(self.retrieval_sha256) != 64 or not set(self.retrieval_sha256) <= _SHA256_ALPHABET:
            raise ValueError("retrieval_sha256 must be a lowercase 64-char SHA-256")
        if len(set(self.mapped_clause_ids)) != len(self.mapped_clause_ids):
            raise ValueError("mapped_clause_ids contains duplicates")
        return self


class ExternalReferenceFreeze(KernelModel):
    """Freeze versionato delle risorse esterne; vuoto = gate resta bloccato."""

    freeze_id: NonBlankStr
    freeze_version: NonBlankStr
    resources: tuple[ExternalReferenceResource, ...] = Field(default=())
    review_requirement: ScientificReviewRequirement
    declared_checksum: NonBlankStr

    @model_validator(mode="after")
    def _blocked_until_reviewed(self) -> ExternalReferenceFreeze:
        if self.review_requirement.issue_id != EXTERNAL_REFERENCE_REVIEW_ISSUE_ID:
            raise ValueError("external reference freeze must retain blocker SRR-V8-021")
        ids = [item.resource_id for item in self.resources]
        if len(set(ids)) != len(ids):
            raise ValueError("external reference freeze contains duplicate resource IDs")
        return self

    @property
    def is_empty(self) -> bool:
        return not self.resources

    def resources_for_clause(self, clause_id: str) -> tuple[ExternalReferenceResource, ...]:
        return tuple(item for item in self.resources if clause_id in item.mapped_clause_ids)


__all__ = [
    "EXTERNAL_REFERENCE_REVIEW_ISSUE_ID",
    "ExternalReferenceFreeze",
    "ExternalReferenceResource",
]
