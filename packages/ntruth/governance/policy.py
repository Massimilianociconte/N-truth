"""Gate centralizzato per ogni azione sui dati; nessun default permissivo."""

from __future__ import annotations

from datetime import UTC, datetime

from ntruth.governance.models import (
    AuthorizationGrant,
    ConsentStatus,
    GovernanceAction,
    GovernanceDenied,
    GovernanceRecord,
    GovernanceStatus,
)
from ntruth.schemas.manifest import LicenseManifest


def authorize(
    record: GovernanceRecord | None,
    action: GovernanceAction | str,
    *,
    at: datetime | None = None,
    expected_asset_id: str | None = None,
    expected_asset_sha256: str | None = None,
    expected_governance_hash: str | None = None,
    license_manifest: LicenseManifest | None = None,
) -> AuthorizationGrant:
    """Autorizza un uso soltanto se tutte le condizioni sono vere ora.

    La funzione deve essere richiamata immediatamente prima dell'azione per
    evitare che revoca o scadenza vengano controllate solo all'ingestione.
    """

    try:
        requested = GovernanceAction(action)
    except ValueError as exc:
        raise GovernanceDenied("unknown_action", f"azione non riconosciuta: {action}") from exc
    if record is None:
        raise GovernanceDenied("missing_record", "governance record assente")
    now = at or datetime.now(UTC)
    if now.tzinfo is None:
        raise GovernanceDenied("naive_time", "il controllo richiede un datetime timezone-aware")
    if record.status is not GovernanceStatus.APPROVED:
        raise GovernanceDenied("record_not_approved", f"stato record: {record.status}")
    if record.revoked_at is not None and record.revoked_at <= now:
        raise GovernanceDenied("record_revoked", "autorizzazione revocata")
    if record.expires_at is not None and record.expires_at <= now:
        raise GovernanceDenied("record_expired", "autorizzazione scaduta")
    if record.consent_status in {ConsentStatus.PENDING, ConsentStatus.WITHDRAWN}:
        raise GovernanceDenied("consent_not_valid", f"stato consenso: {record.consent_status}")
    if requested not in record.allowed_uses:
        raise GovernanceDenied("use_not_allowed", f"uso non autorizzato: {requested}")
    if expected_asset_id is not None and record.asset_id != expected_asset_id:
        raise GovernanceDenied("asset_mismatch", "asset_id diverso dal record autorizzato")
    if expected_asset_sha256 is not None and record.asset_sha256 != expected_asset_sha256:
        raise GovernanceDenied("checksum_mismatch", "checksum asset diverso dal record")
    governance_hash = record.governance_hash()
    if expected_governance_hash is not None and governance_hash != expected_governance_hash:
        raise GovernanceDenied("governance_changed", "governance record modificato")
    if (
        record.public_asset
        and requested
        in {GovernanceAction.TRAIN, GovernanceAction.SHARE, GovernanceAction.REDISTRIBUTE}
        and record.license_manifest_id is None
    ):
        raise GovernanceDenied(
            "missing_license_reference",
            "asset pubblico senza manifest licenza versionato",
        )
    if record.license_manifest_id is not None:
        if license_manifest is None:
            raise GovernanceDenied("missing_license_manifest", "manifest licenza richiesto")
        if license_manifest.asset_id != record.asset_id:
            raise GovernanceDenied(
                "license_asset_mismatch", "manifest licenza riferito a un altro asset"
            )
        if license_manifest.asset_id != record.license_manifest_id:
            raise GovernanceDenied("license_id_mismatch", "license_manifest_id non coerente")
        assert record.license_manifest_hash is not None
        if license_manifest.manifest_hash() != record.license_manifest_hash:
            raise GovernanceDenied("license_changed", "manifest licenza modificato")
        automated_release = requested in {
            GovernanceAction.TRAIN,
            GovernanceAction.SHARE,
            GovernanceAction.REDISTRIBUTE,
        }
        if not license_manifest.permits(requested.value, automated_release=automated_release):
            raise GovernanceDenied("license_use_not_allowed", f"licenza non valida per {requested}")
    return AuthorizationGrant(
        record_id=record.record_id,
        asset_id=record.asset_id,
        asset_sha256=record.asset_sha256,
        action=requested,
        governance_hash=governance_hash,
        checked_at=now,
    )
