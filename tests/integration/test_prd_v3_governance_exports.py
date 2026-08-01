"""Integrazione PRD v3: schemi, privacy, licenze e gate distribuzione."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from conftest import ProjectFactory
from typer.testing import CliRunner

from ntruth.application import (
    DistributionGovernanceBundle,
    RedactedDerivativeMaterial,
    evaluate_distribution_readiness,
    execute_analysis,
)
from ntruth.cli.main import app
from ntruth.governance import (
    AnonymizationStatus,
    ConsentStatus,
    GovernanceAction,
    GovernanceDenied,
    GovernanceRecord,
    GovernanceStatus,
    PrivacyBlocked,
    RedactionManifest,
)
from ntruth.pipeline import analyze_project
from ntruth.reporting import write_all

METHODS = """# Methods

Three independent cell cultures received drug or vehicle. Signal was measured per culture.
"""


def _governance_records(assets: list[dict[str, object]]) -> tuple[GovernanceRecord, ...]:
    return tuple(
        GovernanceRecord(
            record_id=f"gov-{asset['asset_id']}",
            asset_id=str(asset["asset_id"]),
            asset_sha256=str(asset["sha256"]),
            status=GovernanceStatus.APPROVED,
            allowed_uses=frozenset({GovernanceAction.SHARE, GovernanceAction.REDISTRIBUTE}),
            owner_role="data_owner",
            authorization_reference=f"local://authorization/{asset['asset_id']}",
            authorization_sha256="b" * 64,
            consent_status=ConsentStatus.GRANTED,
            anonymization_status=AnonymizationStatus.VERIFIED,
            granted_at=datetime.now(UTC),
        )
        for asset in assets
    )


def test_write_all_exports_parser_ai_schemas_and_ro_crate_does_not_relicense_dataset(
    make_project: ProjectFactory,
    tmp_path: Path,
) -> None:
    result = analyze_project(make_project({"methods.md": METHODS}))

    written = write_all(result.report, tmp_path / "out")

    assert {
        "parser_ai_input_schema",
        "parser_ai_output_schema",
        "ro_crate",
    } <= written.keys()
    input_schema = json.loads(written["parser_ai_input_schema"].read_text(encoding="utf-8"))
    output_schema = json.loads(written["parser_ai_output_schema"].read_text(encoding="utf-8"))
    assert {"documents", "tables", "metadata", "statistical_code"} <= set(
        input_schema["properties"]
    )
    assert {"candidate_nodes", "candidate_edges", "determinability"} <= set(
        output_schema["properties"]
    )

    crate = json.loads(written["ro_crate"].read_text(encoding="utf-8"))
    entities = {entity["@id"]: entity for entity in crate["@graph"]}
    root = entities["./"]
    software = entities["#ntruth"]
    assert "license" not in root
    assert root["ntruth:datasetLicenseStatus"] == "not_asserted"
    assert root["ntruth:inputRightsStatus"] == "not_inferred"
    assert software["license"] == {"@id": "https://spdx.org/licenses/Apache-2.0"}
    assert entities["parser-ai-input.schema.json"]["conformsTo"] == {
        "@id": "https://json-schema.org/draft/2020-12/schema"
    }


def test_analysis_exposes_privacy_findings_without_mutating_or_blocking_source(
    tmp_path: Path,
) -> None:
    source = tmp_path / "methods.md"
    original = (
        "# Methods\n\nContact: alice@example.org. sample_id=SUBJ-009 received drug or vehicle.\n"
    )
    source.write_text(original, encoding="utf-8")

    execution = execute_analysis(source, out=tmp_path / "out")

    assert execution.privacy_audit.finding_count >= 2
    assert execution.share_readiness.analysis_allowed is True
    assert execution.share_readiness.share_ready is False
    assert source.read_text(encoding="utf-8") == original
    privacy_payload = execution.written["privacy_scan"].read_text(encoding="utf-8")
    assert "alice@example.org" not in privacy_payload
    assert "SUBJ-009" not in privacy_payload
    assert execution.written["share_readiness"].is_file()


def test_api_distribution_readiness_is_explicit_and_fail_closed(tmp_path: Path) -> None:
    pytest.importorskip("fastapi", reason="installare l'extra api")
    pytest.importorskip("httpx2", reason="installare l'extra api")
    from fastapi.testclient import TestClient

    from ntruth.api.app import create_app

    source = tmp_path / "methods.md"
    source.write_text(METHODS, encoding="utf-8")
    client = TestClient(create_app())
    analyzed = client.post(
        "/v1/analyze",
        json={
            "source": str(source),
            "out": str(tmp_path / "api-out"),
            "acknowledge_unvalidated_domain": True,
        },
    )
    assert analyzed.status_code == 200, analyzed.text
    body = analyzed.json()
    assert body["share_readiness"]["share_ready"] is False
    assert body["privacy_audit"]["original_sources_mutated"] is False

    missing = client.post(
        "/v1/distribution/readiness",
        json={"session_id": body["session_id"], "action": "share"},
    )
    assert missing.status_code == 409
    assert missing.json()["detail"]["code"] == "missing_record"

    records = _governance_records(body["share_readiness"]["assets"])
    ready = client.post(
        "/v1/distribution/readiness",
        json={
            "session_id": body["session_id"],
            "action": "share",
            "governance_records": [record.model_dump(mode="json") for record in records],
            "privacy_policy": "acknowledged",
            "acknowledgement_reference": "local://privacy-review/review-1",
        },
    )
    assert ready.status_code == 200, ready.text
    assert ready.json()["authorized"] is True
    assert ready.json()["current_artifacts_authorized"] is True
    assert ready.json()["transfer_performed"] is False


def test_cli_distribution_check_never_performs_a_transfer(tmp_path: Path) -> None:
    source = tmp_path / "methods.md"
    source.write_text(METHODS, encoding="utf-8")
    execution = execute_analysis(source, out=tmp_path / "out")
    records = _governance_records(
        [asset.model_dump(mode="json") for asset in execution.share_readiness.assets]
    )
    governance_path = tmp_path / "governance.json"
    governance_path.write_text(
        DistributionGovernanceBundle(governance_records=records).model_dump_json(indent=2),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "distribution-check",
            str(execution.written["json"].parent),
            "--governance",
            str(governance_path),
            "--action",
            "share",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "autorizzato" in result.output
    assert "Nessun trasferimento eseguito" in result.output


def test_distribution_gate_rejects_an_empty_asset_scope(tmp_path: Path) -> None:
    source = tmp_path / "methods.md"
    source.write_text(METHODS, encoding="utf-8")
    execution = execute_analysis(source, out=tmp_path / "out")
    empty_scope = execution.share_readiness.model_copy(update={"assets": ()})

    with pytest.raises(GovernanceDenied) as exc_info:
        evaluate_distribution_readiness(
            empty_scope,
            execution.privacy_audit,
            DistributionGovernanceBundle(governance_records=()),
            action="share",
        )

    assert exc_info.value.code == "empty_distribution_scope"


def test_redacted_copy_checksum_is_recomputed_from_exact_scanned_scope(tmp_path: Path) -> None:
    source = tmp_path / "methods.md"
    source.write_text(
        "# Methods\n\nContact alice@example.org; sample_id=SUBJ-009.",
        encoding="utf-8",
    )
    execution = execute_analysis(source, out=tmp_path / "out")
    records = _governance_records(
        [asset.model_dump(mode="json") for asset in execution.share_readiness.assets]
    )
    derivative_content = "[REDACTED]"
    actual_checksum = hashlib.sha256(derivative_content.encode("utf-8")).hexdigest()

    def bundle(checksum: str) -> DistributionGovernanceBundle:
        return DistributionGovernanceBundle(
            governance_records=records,
            redaction_manifests=tuple(
                RedactionManifest(
                    artifact_id=scan.artifact_id,
                    field_path=scan.field_path,
                    original_checksum=scan.original_checksum,
                    derivative_checksum=checksum,
                    redacted_finding_ids=tuple(finding.finding_id for finding in scan.findings),
                    replacement="[REDACTED]",
                )
                for scan in execution.privacy_audit.scans_with_findings
            ),
            redacted_derivatives=tuple(
                RedactedDerivativeMaterial(
                    artifact_id=scan.artifact_id,
                    field_path=scan.field_path,
                    original_checksum=scan.original_checksum,
                    content=derivative_content,
                )
                for scan in execution.privacy_audit.scans_with_findings
            ),
        )

    with pytest.raises(PrivacyBlocked, match="checksum della derivata"):
        evaluate_distribution_readiness(
            execution.share_readiness,
            execution.privacy_audit,
            bundle("0" * 64),
            action="share",
            privacy_policy="redacted_copy",
        )

    verified = evaluate_distribution_readiness(
        execution.share_readiness,
        execution.privacy_audit,
        bundle(actual_checksum),
        action="share",
        privacy_policy="redacted_copy",
    )
    assert verified.artifact_scope == "redacted_derivatives_only"
    assert verified.current_artifacts_authorized is False
    assert len(verified.verified_redacted_derivatives) == len(
        execution.privacy_audit.scans_with_findings
    )
    assert verified.transfer_performed is False
