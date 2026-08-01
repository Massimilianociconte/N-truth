"""Template fail-closed derivati dallo scope reale di una revisione."""

from __future__ import annotations

from ntruth.application import DistributionGovernanceBundle
from ntruth.governance.models import GovernanceRecord
from ntruth.reporting.privacy import ShareReadiness


def pending_distribution_bundle(readiness: ShareReadiness) -> DistributionGovernanceBundle:
    """Crea record strutturalmente validi che non concedono alcun uso.

    Il template copia soltanto asset ID e checksum dallo scope già scansionato. Un
    reviewer deve poi aggiungere prove, licenze e permessi; lo stato ``pending``
    garantisce che ``distribution-check`` continui a negare l'operazione.
    """

    return DistributionGovernanceBundle(
        governance_records=tuple(
            GovernanceRecord(
                record_id=f"pending-{asset.asset_id}",
                asset_id=asset.asset_id,
                asset_sha256=asset.sha256,
                restrictions=(
                    "TEMPLATE ONLY: review ownership, license, privacy and requested use",
                ),
            )
            for asset in readiness.assets
        )
    )
