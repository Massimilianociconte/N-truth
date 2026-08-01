"""Caso d'uso condiviso da CLI e API per garantire parity (PRD FR-029)."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from ntruth.artifacts import remap_artifact_paths, staged_directory, unique_run_path
from ntruth.governance import (
    AuthorizationGrant,
    GovernanceAction,
    GovernanceDenied,
    GovernanceRecord,
    PrivacyBlocked,
    PrivacyDecision,
    PrivacyPolicy,
    RedactionManifest,
    authorize,
    enforce_privacy,
    scan_text,
)
from ntruth.ingest.project import IngestResult, Project
from ntruth.pipeline import AnalysisResult, analyze_project
from ntruth.reporting import PrivacyAudit, ShareReadiness, write_all
from ntruth.reporting.privacy import build_privacy_audit, build_share_readiness
from ntruth.rules.loader import (
    DEFAULT_RULESET_ID,
    DEFAULT_RULESET_VERSION,
    load_ruleset,
)
from ntruth.schemas.core import NTruthModel
from ntruth.schemas.manifest import LicenseManifest
from ntruth.schemas.report import DomainTransparency
from ntruth.transparency import assess_domain


class NoUsableFilesError(RuntimeError):
    """L'ingestione non ha lasciato alcuna fonte analizzabile nel progetto."""

    def __init__(self, ingest: IngestResult) -> None:
        self.ingest = ingest
        super().__init__("Nessun file utilizzabile. " + ingest.summary())


class DomainAcknowledgementRequired(RuntimeError):
    """Il dominio effettivo del progetto richiede conferma prima dell'analisi."""

    def __init__(self, transparency: DomainTransparency) -> None:
        self.transparency = transparency
        super().__init__(transparency.warning)


@dataclass(frozen=True)
class AnalysisExecution:
    """Esito applicativo identico per CLI e FastAPI."""

    result: AnalysisResult
    ingest: IngestResult
    written: dict[str, Path]
    transparency: DomainTransparency
    run_id: str
    run_dir: Path
    privacy_audit: PrivacyAudit
    share_readiness: ShareReadiness
    revision: int = 0


class RedactedDerivativeMaterial(NTruthModel):
    """Contenuto locale effettivo usato soltanto per verificare il gate.

    Il contenuto non viene copiato nell'esito e non viene trasferito. La chiave
    include il campo per evitare che una derivata valida per una stringa venga
    riutilizzata implicitamente per un'altra porzione dell'artefatto.
    """

    artifact_id: str
    field_path: str
    original_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    content: str


class DistributionGovernanceBundle(NTruthModel):
    """Materiale esplicitamente fornito per un singolo controllo locale."""

    governance_records: tuple[GovernanceRecord, ...]
    license_manifests: tuple[LicenseManifest, ...] = ()
    redaction_manifests: tuple[RedactionManifest, ...] = ()
    redacted_derivatives: tuple[RedactedDerivativeMaterial, ...] = ()

    @model_validator(mode="after")
    def _unique_records(self) -> DistributionGovernanceBundle:
        record_assets = [record.asset_id for record in self.governance_records]
        license_assets = [manifest.asset_id for manifest in self.license_manifests]
        redactions = [
            (manifest.artifact_id, manifest.field_path, manifest.original_checksum)
            for manifest in self.redaction_manifests
        ]
        derivatives = [
            (material.artifact_id, material.field_path, material.original_checksum)
            for material in self.redacted_derivatives
        ]
        if len(record_assets) != len(set(record_assets)):
            raise ValueError("governance record duplicati per asset")
        if len(license_assets) != len(set(license_assets)):
            raise ValueError("license manifest duplicati per asset")
        if len(redactions) != len(set(redactions)):
            raise ValueError("redaction manifest duplicati per artifact/campo/checksum")
        if len(derivatives) != len(set(derivatives)):
            raise ValueError("derivate redatte duplicate per artifact/campo/checksum")
        return self


class VerifiedRedactedDerivative(NTruthModel):
    artifact_id: str
    field_path: str
    original_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    derivative_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")


class DistributionReadiness(NTruthModel):
    """Esito del gate; non copia file e non effettua trasferimenti."""

    action: GovernanceAction
    authorized: Literal[True] = True
    current_artifacts_authorized: bool
    artifact_scope: Literal["current_local_artifacts", "redacted_derivatives_only"]
    authorization_grants: tuple[AuthorizationGrant, ...]
    privacy_decisions: tuple[PrivacyDecision, ...]
    verified_redacted_derivatives: tuple[VerifiedRedactedDerivative, ...] = ()
    privacy_audit_checksum: str
    transfer_performed: Literal[False] = False


def evaluate_distribution_readiness(
    readiness: ShareReadiness,
    audit: PrivacyAudit,
    governance: DistributionGovernanceBundle,
    *,
    action: GovernanceAction | str,
    privacy_policy: PrivacyPolicy | str = PrivacyPolicy.BLOCKED,
    acknowledgement_reference: str | None = None,
) -> DistributionReadiness:
    """Applica governance e privacy a share/redistribute, sempre fail-closed."""

    requested = GovernanceAction(action)
    if requested not in {GovernanceAction.SHARE, GovernanceAction.REDISTRIBUTE}:
        raise GovernanceDenied(
            "invalid_distribution_action",
            "sono ammesse soltanto share o redistribute",
        )
    if readiness.privacy_audit_checksum != audit.audit_checksum():
        raise GovernanceDenied("privacy_audit_changed", "privacy audit non coerente")
    if not readiness.assets:
        raise GovernanceDenied("empty_distribution_scope", "nessun asset da autorizzare")
    readiness_asset_ids = {asset.asset_id for asset in readiness.assets}
    scanned_asset_ids = set(audit.scanned_asset_ids)
    if readiness_asset_ids != scanned_asset_ids:
        raise GovernanceDenied(
            "privacy_scope_mismatch",
            "gli asset richiesti non coincidono con lo scope scansionato",
        )
    records = {record.asset_id: record for record in governance.governance_records}
    licenses = {manifest.asset_id: manifest for manifest in governance.license_manifests}
    grants: list[AuthorizationGrant] = []
    for asset in readiness.assets:
        record = records.get(asset.asset_id)
        if record is None:
            raise GovernanceDenied(
                "missing_record",
                f"governance record assente per asset {asset.asset_id}",
            )
        if (
            asset.governance_record_id is not None
            and record.record_id != asset.governance_record_id
        ):
            raise GovernanceDenied(
                "record_id_mismatch",
                f"record_id non coerente per asset {asset.asset_id}",
            )
        grants.append(
            authorize(
                record,
                requested,
                expected_asset_id=asset.asset_id,
                expected_asset_sha256=asset.sha256,
                expected_governance_hash=asset.governance_record_hash,
                license_manifest=licenses.get(asset.asset_id),
            )
        )

    redactions = {
        (manifest.artifact_id, manifest.field_path, manifest.original_checksum): manifest
        for manifest in governance.redaction_manifests
    }
    derivatives = {
        (material.artifact_id, material.field_path, material.original_checksum): material
        for material in governance.redacted_derivatives
    }
    selected_policy = PrivacyPolicy(privacy_policy)
    scan_keys = {
        (scan.artifact_id, scan.field_path, scan.original_checksum)
        for scan in audit.scans_with_findings
    }
    if selected_policy is PrivacyPolicy.REDACTED_COPY and (
        set(redactions) != scan_keys or set(derivatives) != scan_keys
    ):
        raise PrivacyBlocked(
            "manifest e contenuti delle derivate devono coincidere con l'intero scope privacy"
        )

    decisions: list[PrivacyDecision] = []
    verified_derivatives: list[VerifiedRedactedDerivative] = []
    for scan in audit.scans_with_findings:
        key = (scan.artifact_id, scan.field_path, scan.original_checksum)
        manifest = redactions.get(key)
        decisions.append(
            enforce_privacy(
                scan,
                selected_policy,
                acknowledgement_reference=acknowledgement_reference,
                redaction_manifest=manifest,
            )
        )
        if selected_policy is not PrivacyPolicy.REDACTED_COPY:
            continue
        assert manifest is not None
        material = derivatives[key]
        actual_checksum = hashlib.sha256(material.content.encode("utf-8")).hexdigest()
        if actual_checksum != manifest.derivative_checksum:
            raise PrivacyBlocked("checksum della derivata redatta non coerente col contenuto")
        residual = scan_text(
            material.content,
            artifact_id=material.artifact_id,
            field_path=material.field_path,
        )
        if residual.findings:
            raise PrivacyBlocked("la derivata contiene ancora identificatori rilevabili")
        verified_derivatives.append(
            VerifiedRedactedDerivative(
                artifact_id=material.artifact_id,
                field_path=material.field_path,
                original_checksum=material.original_checksum,
                derivative_checksum=actual_checksum,
            )
        )
    redacted_only = selected_policy is PrivacyPolicy.REDACTED_COPY and bool(
        audit.scans_with_findings
    )
    return DistributionReadiness(
        action=requested,
        current_artifacts_authorized=not redacted_only,
        artifact_scope=(
            "redacted_derivatives_only" if redacted_only else "current_local_artifacts"
        ),
        authorization_grants=tuple(grants),
        privacy_decisions=tuple(decisions),
        verified_redacted_derivatives=tuple(verified_derivatives),
        privacy_audit_checksum=audit.audit_checksum(),
    )


def execute_analysis(
    source: Path,
    *,
    out: Path,
    project_dir: Path | None = None,
    language: str = "it",
    domain: str = "quantitative_microscopy",
    ruleset_id: str = DEFAULT_RULESET_ID,
    ruleset_version: str = DEFAULT_RULESET_VERSION,
    on_preflight: Callable[[DomainTransparency], None] | None = None,
    require_domain_acknowledgement: bool = False,
    acknowledged_unvalidated_domain: bool = False,
) -> AnalysisExecution:
    """Esegue una singola analisi locale e tutti gli export previsti.

    Il callback viene invocato prima di ingestione/inferenza, cosi CLI e altri
    client possono rendere visibile lo stato non validato prima dell'uso.
    """

    source = source.expanduser()
    if not source.exists():
        raise FileNotFoundError(f"Percorso inesistente: {source}")

    output_root = out.expanduser().resolve()
    run_id, run_dir = unique_run_path(output_root)
    explicit_workspace = project_dir.expanduser().resolve() if project_dir is not None else None

    with staged_directory(run_dir) as staging:
        # Senza --project ogni run possiede manifest e fonti propri. Un workspace
        # preesistente viene riaperto soltanto quando il chiamante lo indica.
        workspace = explicit_workspace or staging / "project"
        project = Project.open_or_create(
            workspace,
            name=source.stem if source.is_file() else source.name,
            domain=domain,
            language="it" if language == "it" else "en",
            ruleset_id=ruleset_id,
            ruleset_version=ruleset_version,
        )
        transparency = assess_domain(project.manifest.domain)
        if on_preflight is not None:
            on_preflight(transparency)
        if (
            require_domain_acknowledgement
            and transparency.requires_acknowledgement
            and not acknowledged_unvalidated_domain
        ):
            raise DomainAcknowledgementRequired(transparency)

        ingest = project.add(source)
        if not project.manifest.files:
            raise NoUsableFilesError(ingest)

        ruleset = load_ruleset(ruleset_id, ruleset_version)
        result = analyze_project(project, ruleset=ruleset, lang=language)
        privacy_audit = build_privacy_audit(result.document, result.report)
        share_readiness = build_share_readiness(
            privacy_audit,
            project_manifest=project.manifest,
        )
        revision_dir = staging / "revisions" / "0000"
        staged_written = write_all(
            result.report,
            revision_dir,
            privacy_audit=privacy_audit,
            share_readiness=share_readiness,
        )

    written = remap_artifact_paths(
        staged_written,
        source_root=staging,
        destination_root=run_dir,
    )
    return AnalysisExecution(
        result=result,
        ingest=ingest,
        written=written,
        transparency=transparency,
        run_id=run_id,
        run_dir=run_dir,
        privacy_audit=privacy_audit,
        share_readiness=share_readiness,
    )
