"""Contratti locali di consenso, licenza e autorizzazione (PRD v3 15, 18.5, 26)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from ntruth.schemas.core import FrozenModel, content_checksum


class GovernanceAction(StrEnum):
    ANALYZE = "analyze"
    ANNOTATE = "annotate"
    TRAIN = "train"
    SHARE = "share"
    REDISTRIBUTE = "redistribute"


class GovernanceStatus(StrEnum):
    APPROVED = "approved"
    PENDING = "pending"
    REJECTED = "rejected"


class ConsentStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    GRANTED = "granted"
    PENDING = "pending"
    WITHDRAWN = "withdrawn"


class AnonymizationStatus(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    REQUIRED = "required"
    VERIFIED = "verified"
    UNKNOWN = "unknown"


class GovernanceRecord(FrozenModel):
    """Record immutabile per asset; ogni uso deve essere autorizzato esplicitamente."""

    record_id: str
    asset_id: str
    asset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: GovernanceStatus = GovernanceStatus.PENDING
    allowed_uses: frozenset[GovernanceAction] = frozenset()
    owner_role: str | None = None
    authorization_reference: str | None = None
    authorization_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    license_manifest_id: str | None = None
    license_manifest_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    consent_status: ConsentStatus = ConsentStatus.PENDING
    anonymization_status: AnonymizationStatus = AnonymizationStatus.UNKNOWN
    public_asset: bool = False
    granted_at: datetime | None = None
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    restrictions: tuple[str, ...] = ()

    @field_validator("granted_at", "expires_at", "revoked_at")
    @classmethod
    def _timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("i timestamp di governance devono includere il fuso orario")
        return value

    @model_validator(mode="after")
    def _validate_record(self) -> GovernanceRecord:
        if (self.license_manifest_id is None) != (self.license_manifest_hash is None):
            raise ValueError("license_manifest_id e license_manifest_hash vanno registrati insieme")
        if self.status is GovernanceStatus.APPROVED:
            if not self.allowed_uses:
                raise ValueError("record approvato senza allowed_uses")
            if not self.authorization_reference or not self.authorization_sha256:
                raise ValueError("record approvato senza prova di autorizzazione")
            if self.granted_at is None:
                raise ValueError("record approvato senza granted_at")
        if (
            self.expires_at is not None
            and self.granted_at is not None
            and self.expires_at <= self.granted_at
        ):
            raise ValueError("expires_at deve essere successivo a granted_at")
        if (
            self.revoked_at is not None
            and self.granted_at is not None
            and self.revoked_at < self.granted_at
        ):
            raise ValueError("revoked_at precedente a granted_at")
        return self

    def governance_hash(self) -> str:
        """Hash stabile incluso nella lineage; comprende revoca e allowed uses."""

        return content_checksum(self.model_dump(mode="json"))


class AuthorizationGrant(FrozenModel):
    """Prova dell'esito del gate, senza ampliare i permessi del record."""

    record_id: str
    asset_id: str
    asset_sha256: str
    action: GovernanceAction
    governance_hash: str
    checked_at: datetime


class GovernanceDenied(PermissionError):
    """Diniego fail-closed con codice stabile e messaggio auditabile."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
