"""Profilo input D0 e opt-in dei parser sperimentali."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ntruth.api.app import AnalyzeRequest
from ntruth.ingest.project import Project
from ntruth.ingest.safety import SafetyError
from ntruth.parsers.registry import build_document_ir, parser_for
from ntruth.schemas.manifest import ProjectFile, ProjectManifest, ReleaseProfile


def test_legacy_manifest_without_profile_loads_as_conservative_d0() -> None:
    legacy = {
        "project_id": "legacy-project",
        "name": "Legacy",
        "schema_version": "0.1.0",
    }

    manifest = ProjectManifest.model_validate(legacy)

    assert manifest.release_profile is ReleaseProfile.D0_CORE


def test_legacy_manifest_with_complex_files_migrates_losslessly_to_extended(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "legacy-jats"
    source_dir = workspace / "sources"
    source_dir.mkdir(parents=True)
    source = source_dir / "article.nxml"
    source.write_text(
        "<article><body><sec><title>Methods</title><p>Three cultures.</p></sec></body></article>",
        encoding="utf-8",
    )
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    project_file = ProjectFile(
        file_id="legacy-jats-file",
        filename=source.name,
        relative_path="sources/article.nxml",
        media_type="application/xml",
        size_bytes=source.stat().st_size,
        sha256=digest,
    )
    legacy = ProjectManifest(
        project_id="legacy-jats-project",
        name="Legacy JATS",
        schema_version="0.2.0",
        release_profile=ReleaseProfile.EXTENDED_EXPERIMENTAL,
        files=(project_file,),
    ).model_dump(mode="json")
    legacy.pop("release_profile")
    manifest_path = workspace / "manifest.json"
    manifest_path.write_text(
        json.dumps(legacy, ensure_ascii=False),
        encoding="utf-8",
    )
    manifest_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    reopened = Project.open_or_create(
        workspace,
        release_profile=ReleaseProfile.EXTENDED_EXPERIMENTAL,
        migrate_legacy_manifest=True,
        legacy_manifest_sha256=manifest_digest,
    )

    assert reopened.manifest.release_profile is ReleaseProfile.EXTENDED_EXPERIMENTAL
    assert build_document_ir(reopened).files[0].parser == "jats"


def test_profile_is_persisted_and_mismatch_on_existing_workspace_is_rejected(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "project"
    project = Project.create(
        workspace,
        name="experimental",
        release_profile=ReleaseProfile.EXTENDED_EXPERIMENTAL,
    )

    saved = json.loads(project.save().read_text(encoding="utf-8"))
    reopened = Project.open(workspace)

    assert saved["release_profile"] == "extended_experimental"
    assert reopened.manifest.release_profile is ReleaseProfile.EXTENDED_EXPERIMENTAL
    with pytest.raises(SafetyError, match="non coincide"):
        Project.open_or_create(workspace, release_profile=ReleaseProfile.D0_CORE)


def test_d0_rejects_jats_while_explicit_profile_parses_it(tmp_path: Path) -> None:
    source = tmp_path / "article.nxml"
    source.write_text(
        "<article><body><sec><title>Methods</title><p>Three cultures.</p></sec></body></article>",
        encoding="utf-8",
    )
    core = Project.create(tmp_path / "core", name="core")
    experimental = Project.create(
        tmp_path / "experimental",
        name="experimental",
        release_profile=ReleaseProfile.EXTENDED_EXPERIMENTAL,
    )

    core_ingest = core.add(source)
    experimental_ingest = experimental.add(source)

    assert not core_ingest.accepted
    assert "extended_experimental" in (core_ingest.rejected[0].reason or "")
    assert experimental_ingest.accepted
    document = build_document_ir(experimental)
    assert document.files[0].parser == "jats"


def test_parser_registry_defaults_to_d0_and_requires_explicit_opt_in(tmp_path: Path) -> None:
    path = tmp_path / "article.xml"

    assert parser_for(path, "application/xml") is None
    assert parser_for(path, "application/xml", ReleaseProfile.EXTENDED_EXPERIMENTAL).name == "jats"


def test_api_contract_defaults_to_d0_and_accepts_explicit_profile() -> None:
    default = AnalyzeRequest(source="methods.md")
    experimental = AnalyzeRequest(
        source="methods.pdf",
        release_profile="extended_experimental",
    )

    assert default.release_profile is ReleaseProfile.D0_CORE
    assert experimental.release_profile is ReleaseProfile.EXTENDED_EXPERIMENTAL
