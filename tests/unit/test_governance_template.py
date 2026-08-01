"""Il template governance deve derivare lo scope reale e restare fail-closed."""

from __future__ import annotations

import pytest

from ntruth.application import evaluate_distribution_readiness
from ntruth.governance import GovernanceDenied
from ntruth.governance.templates import pending_distribution_bundle
from ntruth.reporting import PrivacyAudit, ShareReadiness
from ntruth.reporting.privacy import PrivacyAuditStatus


def test_pending_template_copies_scope_without_granting_permissions() -> None:
    audit = PrivacyAudit(
        document_id="document-1",
        status=PrivacyAuditStatus.CLEAN,
        scanned_fields=0,
        scanned_asset_ids=("asset-1",),
        finding_count=0,
    )
    readiness = ShareReadiness(
        privacy_status=PrivacyAuditStatus.CLEAN,
        assets=(
            {
                "asset_id": "asset-1",
                "sha256": "a" * 64,
            },
        ),
        privacy_audit_checksum=audit.audit_checksum(),
        reasons=("Governance non ancora valutata.",),
    )

    bundle = pending_distribution_bundle(readiness)

    assert len(bundle.governance_records) == 1
    record = bundle.governance_records[0]
    assert record.asset_id == "asset-1"
    assert record.asset_sha256 == "a" * 64
    assert not record.allowed_uses
    with pytest.raises(GovernanceDenied, match="record_not_approved"):
        evaluate_distribution_readiness(readiness, audit, bundle, action="share")
