"""PRD v3: gate dati, Experiment Bundle, lineage e privacy locale."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from ntruth.governance import (
    AnonymizationStatus,
    ConsentStatus,
    CorpusAsset,
    CorpusSnapshotManifest,
    CorpusSplit,
    GovernanceAction,
    GovernanceDenied,
    GovernanceRecord,
    GovernanceStatus,
    IdentifierKind,
    LeakageGroup,
    LeakageGroupKind,
    ModelRunLineage,
    PrivacyBlocked,
    PrivacyPolicy,
    RunPurpose,
    authorize,
    enforce_privacy,
    make_redacted_copy,
    scan_text,
)
from ntruth.schemas.manifest import (
    AssetStatus,
    BundleFileReference,
    BundleFileRole,
    ExperimentBundleManifest,
    FileToSampleMapping,
    LicenseManifest,
    LicenseTier,
    ProjectFile,
    ProjectManifest,
)

ASSET_SHA = "a" * 64
AUTH_SHA = "b" * 64
GOV_SHA = "c" * 64
OTHER_SHA = "d" * 64
NOW = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)


def _record(
    *,
    allowed: frozenset[GovernanceAction] | None = None,
    status: GovernanceStatus = GovernanceStatus.APPROVED,
    consent: ConsentStatus = ConsentStatus.GRANTED,
    expires_at: datetime | None = None,
    revoked_at: datetime | None = None,
) -> GovernanceRecord:
    return GovernanceRecord(
        record_id="gov-1",
        asset_id="asset-1",
        asset_sha256=ASSET_SHA,
        status=status,
        allowed_uses=allowed or frozenset(GovernanceAction),
        owner_role="data_owner",
        authorization_reference="local://authorization/record-1",
        authorization_sha256=AUTH_SHA,
        consent_status=consent,
        anonymization_status=AnonymizationStatus.VERIFIED,
        granted_at=NOW - timedelta(days=2),
        expires_at=expires_at,
        revoked_at=revoked_at,
    )


@pytest.mark.parametrize("action", list(GovernanceAction))
def test_governance_authorizes_only_explicit_current_uses(action: GovernanceAction) -> None:
    grant = authorize(
        _record(),
        action,
        at=NOW,
        expected_asset_id="asset-1",
        expected_asset_sha256=ASSET_SHA,
    )

    assert grant.action is action
    assert grant.asset_sha256 == ASSET_SHA
    assert grant.governance_hash == _record().governance_hash()


@pytest.mark.parametrize(
    ("record", "action", "code"),
    [
        (None, GovernanceAction.ANALYZE, "missing_record"),
        (
            _record(status=GovernanceStatus.PENDING),
            GovernanceAction.ANALYZE,
            "record_not_approved",
        ),
        (
            _record(allowed=frozenset({GovernanceAction.ANALYZE})),
            GovernanceAction.SHARE,
            "use_not_allowed",
        ),
        (
            _record(consent=ConsentStatus.WITHDRAWN),
            GovernanceAction.ANALYZE,
            "consent_not_valid",
        ),
        (
            _record(expires_at=NOW - timedelta(seconds=1)),
            GovernanceAction.ANALYZE,
            "record_expired",
        ),
        (
            _record(revoked_at=NOW - timedelta(seconds=1)),
            GovernanceAction.ANALYZE,
            "record_revoked",
        ),
    ],
)
def test_governance_is_fail_closed(
    record: GovernanceRecord | None,
    action: GovernanceAction,
    code: str,
) -> None:
    with pytest.raises(GovernanceDenied) as exc_info:
        authorize(record, action, at=NOW)
    assert exc_info.value.code == code


def test_governance_detects_asset_and_record_changes() -> None:
    record = _record()
    with pytest.raises(GovernanceDenied, match="checksum_mismatch"):
        authorize(record, GovernanceAction.ANALYZE, at=NOW, expected_asset_sha256=OTHER_SHA)
    with pytest.raises(GovernanceDenied, match="governance_changed"):
        authorize(record, GovernanceAction.ANALYZE, at=NOW, expected_governance_hash=OTHER_SHA)
    reduced = _record(allowed=frozenset({GovernanceAction.ANALYZE}))
    assert reduced.governance_hash() != record.governance_hash()


def test_license_manifest_is_bound_and_checked_for_automated_uses() -> None:
    license_manifest = LicenseManifest(
        asset_id="asset-1",
        asset_type="article",
        license_spdx_or_uri="CC-BY-4.0",
        license_evidence_url="https://example.invalid/license-evidence",
        retrieved_at="2026-08-01",
        sha256=ASSET_SHA,
        allowed_uses=("analysis", "training", "share", "redistribution"),
        attribution_text="Example authors, CC BY 4.0",
        tier=LicenseTier.A,
        status=AssetStatus.APPROVED_TIER_A,
    )
    record = GovernanceRecord(
        **{
            **_record().model_dump(),
            "license_manifest_id": license_manifest.asset_id,
            "license_manifest_hash": license_manifest.manifest_hash(),
        }
    )

    with pytest.raises(GovernanceDenied, match="missing_license_manifest"):
        authorize(record, GovernanceAction.TRAIN, at=NOW)
    grant = authorize(
        record,
        GovernanceAction.TRAIN,
        at=NOW,
        license_manifest=license_manifest,
    )
    assert grant.action is GovernanceAction.TRAIN

    incompatible = license_manifest.model_copy(update={"license_spdx_or_uri": "CC-BY-NC-4.0"})
    incompatible_record = GovernanceRecord(
        **{
            **_record().model_dump(),
            "license_manifest_id": incompatible.asset_id,
            "license_manifest_hash": incompatible.manifest_hash(),
        }
    )
    with pytest.raises(GovernanceDenied, match="license_use_not_allowed"):
        authorize(
            incompatible_record,
            GovernanceAction.SHARE,
            at=NOW,
            license_manifest=incompatible,
        )


def test_experiment_bundle_requires_explicit_valid_file_roles() -> None:
    bundle = ExperimentBundleManifest(
        bundle_id="bundle-1",
        title="Experiment 1",
        files=(
            BundleFileReference(file_id="methods", role=BundleFileRole.METHODS),
            BundleFileReference(file_id="samples", role=BundleFileRole.SAMPLE_SHEET),
            BundleFileReference(file_id="model", role=BundleFileRole.STATISTICAL_CODE),
        ),
        file_to_sample=(
            FileToSampleMapping(
                data_file_id="methods",
                sample_id="sample-key-1",
                sample_sheet_file_id="samples",
            ),
        ),
        governance_record_id="gov-1",
        governance_record_hash=GOV_SHA,
    )

    assert bundle.files[2].role is BundleFileRole.STATISTICAL_CODE
    assert len(bundle.checksum()) == 64

    with pytest.raises(ValidationError, match="sample_sheet_file_id"):
        ExperimentBundleManifest(
            bundle_id="bad",
            title="Bad",
            files=(BundleFileReference(file_id="methods", role=BundleFileRole.METHODS),),
            file_to_sample=(
                FileToSampleMapping(
                    data_file_id="methods",
                    sample_id="s1",
                    sample_sheet_file_id="methods",
                ),
            ),
        )


def test_project_manifest_rejects_bundle_with_unknown_file_and_hashes_license() -> None:
    license_manifest = LicenseManifest(
        asset_id="methods",
        asset_type="document",
        allowed_uses=("analysis",),
    )
    project_file = ProjectFile(
        file_id="methods",
        filename="methods.md",
        relative_path="sources/methods.md",
        media_type="text/markdown",
        size_bytes=10,
        sha256=ASSET_SHA,
        license_manifest=license_manifest,
        governance_record_id="gov-1",
        governance_record_hash=GOV_SHA,
    )
    base = ProjectManifest(
        project_id="project-1",
        name="P",
        schema_version="3.0",
        files=(project_file,),
    )
    changed_license = license_manifest.model_copy(update={"allowed_uses": ("analysis", "share")})
    changed = base.model_copy(
        update={"files": (project_file.model_copy(update={"license_manifest": changed_license}),)}
    )
    assert base.checksum() != changed.checksum()

    with pytest.raises(ValidationError, match="file sconosciuti"):
        ProjectManifest(
            project_id="project-1",
            name="P",
            schema_version="3.0",
            files=(project_file,),
            experiment_bundles=(
                ExperimentBundleManifest(
                    bundle_id="bundle-unknown",
                    title="Unknown",
                    files=(BundleFileReference(file_id="missing", role=BundleFileRole.METHODS),),
                ),
            ),
        )


def _snapshot(*, second_split: CorpusSplit = CorpusSplit.TRAIN) -> CorpusSnapshotManifest:
    assets = (
        CorpusAsset(
            asset_id="a1",
            sha256=ASSET_SHA,
            governance_hash=GOV_SHA,
            bundle_id="b1",
            bundle_checksum=AUTH_SHA,
            split=CorpusSplit.TRAIN,
            leakage_group_ids=("article-1",),
        ),
        CorpusAsset(
            asset_id="a2",
            sha256=OTHER_SHA,
            governance_hash=GOV_SHA,
            bundle_id="b2",
            bundle_checksum=AUTH_SHA,
            split=second_split,
            leakage_group_ids=("article-1",),
        ),
    )
    return CorpusSnapshotManifest(
        schema_version="3.0",
        parser_contract_version="1.0.0",
        guideline_version="3.0",
        ontology_version="3.0",
        assets=assets,
        leakage_groups=(
            LeakageGroup(
                group_id="article-1",
                kind=LeakageGroupKind.ARTICLE_FAMILY,
                asset_ids=("a1", "a2"),
            ),
        ),
    )


def test_corpus_snapshot_id_is_deterministic_and_governance_sensitive() -> None:
    first = _snapshot()
    second = CorpusSnapshotManifest(
        schema_version=first.schema_version,
        parser_contract_version=first.parser_contract_version,
        guideline_version=first.guideline_version,
        ontology_version=first.ontology_version,
        assets=tuple(reversed(first.assets)),
        leakage_groups=first.leakage_groups,
    )
    changed_asset = first.assets[0].model_copy(update={"governance_hash": OTHER_SHA})
    changed = CorpusSnapshotManifest(
        schema_version=first.schema_version,
        parser_contract_version=first.parser_contract_version,
        guideline_version=first.guideline_version,
        ontology_version=first.ontology_version,
        assets=(changed_asset, first.assets[1]),
        leakage_groups=first.leakage_groups,
    )

    assert first.snapshot_id == second.snapshot_id
    assert first.snapshot_id != changed.snapshot_id
    assert first.snapshot_id.startswith("corpus-")


def test_corpus_snapshot_blocks_leakage_and_synthetic_test_assets() -> None:
    with pytest.raises(ValidationError, match="data leakage"):
        _snapshot(second_split=CorpusSplit.TEST)

    synthetic = CorpusAsset(
        asset_id="synthetic",
        sha256=ASSET_SHA,
        governance_hash=GOV_SHA,
        bundle_id="synthetic-bundle",
        bundle_checksum=AUTH_SHA,
        split=CorpusSplit.TEST,
        leakage_group_ids=("template-1",),
        synthetic=True,
    )
    with pytest.raises(ValidationError, match="soltanto nello split train"):
        CorpusSnapshotManifest(
            schema_version="3.0",
            parser_contract_version="1.0.0",
            guideline_version="3.0",
            ontology_version="3.0",
            assets=(synthetic,),
            leakage_groups=(
                LeakageGroup(
                    group_id="template-1",
                    kind=LeakageGroupKind.SYNTHETIC_TEMPLATE,
                    asset_ids=("synthetic",),
                ),
            ),
        )


def test_model_run_lineage_is_declarative_and_content_addressable() -> None:
    snapshot = _snapshot()
    lineage = ModelRunLineage(
        run_id="run-1",
        purpose=RunPurpose.EVALUATION,
        parser_contract_version="1.0.0",
        model_name="local-parser",
        model_version="not-trained-here",
        model_config_checksum=ASSET_SHA,
        corpus_snapshot_id=snapshot.snapshot_id,
        corpus_snapshot_checksum=snapshot.snapshot_checksum(),
        input_splits=(CorpusSplit.TEST,),
        schema_version="3.0",
        guideline_version="3.0",
        ontology_version="3.0",
        code_lock_checksum=OTHER_SHA,
        seed=7,
    )

    assert len(lineage.lineage_checksum()) == 64


def test_privacy_scan_is_stand_off_and_redaction_creates_a_derivative() -> None:
    original = (
        "email=alice@example.org\n"
        "path=/Users/alice/private/sample.csv\n"
        "sample_id=SUBJ-009\n"
        "name: Alice Rossi\n"
    )
    scan = scan_text(original, artifact_id="asset-1", field_path="table.sample")
    kinds = {finding.kind for finding in scan.findings}

    assert kinds == {
        IdentifierKind.EMAIL,
        IdentifierKind.LOCAL_PATH,
        IdentifierKind.SAMPLE_ID,
        IdentifierKind.NAME_LIKE,
    }
    serialized = scan.model_dump_json()
    for raw_value in (
        "alice@example.org",
        "/Users/alice/private/sample.csv",
        "SUBJ-009",
        "Alice Rossi",
    ):
        assert raw_value not in serialized
    with pytest.raises(PrivacyBlocked):
        enforce_privacy(scan, PrivacyPolicy.BLOCKED)

    redacted, manifest = make_redacted_copy(original, scan)

    assert original.endswith("Alice Rossi\n")  # la fonte non viene mutata
    assert "alice@example.org" not in redacted
    assert "SUBJ-009" not in redacted
    decision = enforce_privacy(
        scan,
        PrivacyPolicy.REDACTED_COPY,
        redaction_manifest=manifest,
    )
    assert decision.allowed
    acknowledged = enforce_privacy(
        scan,
        PrivacyPolicy.ACKNOWLEDGED,
        acknowledgement_reference="local://review/privacy-1",
    )
    assert acknowledged.allowed


def test_privacy_scan_detects_email_before_sentence_punctuation() -> None:
    scan = scan_text(
        "Contact: alice@example.org. Next sentence.",
        artifact_id="asset-email",
    )

    email = next(finding for finding in scan.findings if finding.kind is IdentifierKind.EMAIL)
    assert email.start == len("Contact: ")
    assert email.end == len("Contact: alice@example.org")
