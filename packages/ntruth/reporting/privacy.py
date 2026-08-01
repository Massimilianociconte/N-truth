"""Audit privacy locale e readiness di distribuzione, senza mutare le fonti."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from ntruth.governance.privacy import PrivacyFinding, PrivacyScanResult, scan_text
from ntruth.schemas.core import NTruthModel, content_checksum, stable_id
from ntruth.schemas.document import DocumentIR
from ntruth.schemas.manifest import ProjectManifest
from ntruth.schemas.report import Report


class PrivacyAuditStatus(StrEnum):
    CLEAN = "clean"
    REVIEW_REQUIRED = "review_required"


class DistributionAsset(NTruthModel):
    """Riferimento non identificante necessario al gate di distribuzione."""

    asset_id: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    governance_record_id: str | None = None
    governance_record_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    license_manifest_id: str | None = None

    @model_validator(mode="after")
    def _versioned_governance_reference(self) -> DistributionAsset:
        if (self.governance_record_id is None) != (self.governance_record_hash is None):
            raise ValueError("riferimento governance incompleto")
        return self


class PrivacyAudit(NTruthModel):
    """Finding stand-off: nessun valore originale viene duplicato nell'artefatto."""

    document_id: str
    status: PrivacyAuditStatus
    scanned_fields: int = Field(ge=0)
    scanned_asset_ids: tuple[str, ...] = ()
    scans_with_findings: tuple[PrivacyScanResult, ...] = ()
    finding_count: int = Field(ge=0)
    original_sources_mutated: Literal[False] = False
    detector_version: str = "1.0.0"

    @model_validator(mode="after")
    def _summary_is_coherent(self) -> PrivacyAudit:
        actual = sum(len(scan.findings) for scan in self.scans_with_findings)
        if actual != self.finding_count:
            raise ValueError("finding_count privacy non coerente")
        expected = PrivacyAuditStatus.REVIEW_REQUIRED if actual else PrivacyAuditStatus.CLEAN
        if self.status is not expected:
            raise ValueError("status privacy non coerente con i finding")
        return self

    def audit_checksum(self) -> str:
        return content_checksum(self.model_dump(mode="json"))


class ShareReadiness(NTruthModel):
    """Stato informativo dopo analisi; non equivale a un'autorizzazione."""

    analysis_allowed: Literal[True] = True
    share_ready: Literal[False] = False
    redistribute_ready: Literal[False] = False
    privacy_status: PrivacyAuditStatus
    governance_status: Literal["not_evaluated"] = "not_evaluated"
    privacy_audit_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    assets: tuple[DistributionAsset, ...] = Field(min_length=1)
    reasons: tuple[str, ...]
    requires_explicit_distribution_check: Literal[True] = True

    @model_validator(mode="after")
    def _asset_scope_is_explicit(self) -> ShareReadiness:
        asset_ids = [asset.asset_id for asset in self.assets]
        if len(asset_ids) != len(set(asset_ids)):
            raise ValueError("assets di distribuzione duplicati")
        return self


def build_privacy_audit(document: DocumentIR, report: Report) -> PrivacyAudit:
    """Scansiona fonti e report corrente; conserva solo scan con finding."""

    scans: list[PrivacyScanResult] = []
    scanned_fields = 0

    def inspect(value: str, *, asset_id: str, field_path: str, label: str) -> None:
        nonlocal scanned_fields
        scanned_fields += 1
        scan = _scan_labeled_value(
            value,
            label=label,
            artifact_id=asset_id,
            field_path=field_path,
        )
        if scan.findings:
            scans.append(scan)

    for source in document.files:
        inspect(
            source.filename,
            asset_id=source.id,
            field_path=f"files[{source.id}].filename",
            label="filename",
        )
        inspect(
            source.relative_path,
            asset_id=source.id,
            field_path=f"files[{source.id}].relative_path",
            label="relative_path",
        )
        text = document.texts.get(source.id, "")
        if text:
            inspect(text, asset_id=source.id, field_path=f"files[{source.id}].text", label="text")
    for table in document.tables:
        for row_index, row in enumerate(table.rows):
            for column, value in row.items():
                inspect(
                    value,
                    asset_id=table.file_id,
                    field_path=f"tables[{table.id}].rows[{row_index}].{column}",
                    label=column,
                )
    report_payload = report.model_dump(mode="json")
    for field_path, label, value in _string_values(report_payload, "report"):
        inspect(value, asset_id=report.report_id, field_path=field_path, label=label)

    finding_count = sum(len(scan.findings) for scan in scans)
    return PrivacyAudit(
        document_id=document.id,
        status=(PrivacyAuditStatus.REVIEW_REQUIRED if finding_count else PrivacyAuditStatus.CLEAN),
        scanned_fields=scanned_fields,
        scanned_asset_ids=tuple(sorted({source.id for source in document.files})),
        scans_with_findings=tuple(scans),
        finding_count=finding_count,
    )


def build_share_readiness(
    audit: PrivacyAudit,
    *,
    project_manifest: ProjectManifest | None = None,
    assets: tuple[DistributionAsset, ...] | None = None,
) -> ShareReadiness:
    """Costruisce la readiness conservativa senza creare governance implicita."""

    if assets is None:
        if project_manifest is None:
            raise ValueError("project_manifest o assets richiesto")
        assets = tuple(
            DistributionAsset(
                asset_id=item.file_id,
                sha256=item.sha256,
                governance_record_id=item.governance_record_id,
                governance_record_hash=item.governance_record_hash,
                license_manifest_id=(
                    item.license_manifest.asset_id if item.license_manifest is not None else None
                ),
            )
            for item in project_manifest.files
        )
    reasons = ["distribution_authorization_not_evaluated"]
    if audit.finding_count:
        reasons.append("privacy_findings_require_policy")
    if any(asset.governance_record_id is None for asset in assets):
        reasons.append("governance_reference_missing_for_one_or_more_assets")
    return ShareReadiness(
        privacy_status=audit.status,
        privacy_audit_checksum=audit.audit_checksum(),
        assets=assets,
        reasons=tuple(reasons),
    )


def write_privacy_audit(audit: PrivacyAudit, path: Path) -> Path:
    return _write_model(audit.model_dump(mode="json"), path)


def write_share_readiness(readiness: ShareReadiness, path: Path) -> Path:
    return _write_model(readiness.model_dump(mode="json"), path)


def _write_model(payload: dict[str, object], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return path


def _scan_labeled_value(
    value: str,
    *,
    label: str,
    artifact_id: str,
    field_path: str,
) -> PrivacyScanResult:
    """Usa l'etichetta per sample/name-like e riporta gli offset al valore reale."""

    prefix = f"{label}="
    combined = prefix + value
    scan = scan_text(combined, artifact_id=artifact_id, field_path=field_path)
    translated: list[PrivacyFinding] = []
    for finding in scan.findings:
        if finding.end <= len(prefix):
            continue
        start = max(0, finding.start - len(prefix))
        end = finding.end - len(prefix)
        translated.append(
            finding.model_copy(
                update={
                    "finding_id": stable_id(
                        "privacy",
                        artifact_id,
                        field_path,
                        finding.kind,
                        start,
                        end,
                        finding.matched_sha256,
                    ),
                    "start": start,
                    "end": end,
                    "line": value.count("\n", 0, start) + 1,
                    "column": start - value.rfind("\n", 0, start),
                }
            )
        )
    return PrivacyScanResult(
        artifact_id=artifact_id,
        field_path=field_path,
        original_checksum=hashlib.sha256(value.encode("utf-8")).hexdigest(),
        findings=tuple(translated),
    )


def _string_values(value: object, path: str) -> Iterator[tuple[str, str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _string_values(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _string_values(child, f"{path}[{index}]")
    elif isinstance(value, str):
        label = path.rsplit(".", maxsplit=1)[-1].split("[", maxsplit=1)[0]
        yield path, label, value
