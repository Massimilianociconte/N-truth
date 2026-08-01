"""FR-028/029/034 e NFR-14: export, parity API e warning pre-use."""

from __future__ import annotations

import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from ntruth.api.sessions import AnalysisSession, SessionRegistry
from ntruth.application import DomainAcknowledgementRequired, execute_analysis
from ntruth.corrections import CorrectionLedger
from ntruth.ingest.project import Project
from ntruth.pipeline import analyze_project
from ntruth.reporting import read_json, report_to_dict, write_all
from ntruth.schemas.core import stable_id
from ntruth.schemas.experiment import Correction, CorrectionReason
from ntruth.transparency import assess_domain

METHODS = (
    "# Materials and Methods\n\n"
    "Primary neurons were prepared from three independent preparations. "
    "Each preparation was plated into four wells. Cells were treated with NGF or "
    "vehicle at the level of the culture. Intensity per cell was quantified; n = 120 cells."
)

MULTI_METHODS = """# Experiment 1
## Materials and Methods
Three independent cultures received drug or vehicle. Intensity was measured in 30 cells.

# Experiment 2
## Materials and Methods
Four independent cultures received drug or vehicle. Intensity was measured in 40 cells.
"""

ProjectFactory = Callable[..., Project]


def test_supported_domain_is_visibly_unvalidated_before_external_validation() -> None:
    notice = assess_domain("quantitative-microscopy")
    assert notice.validation_status.value == "unvalidated"
    assert notice.ood_assessment == "not_evaluated"
    assert notice.requires_acknowledgement is True
    assert "non e ancora validato" in notice.warning


def test_unknown_domain_is_marked_out_of_scope() -> None:
    notice = assess_domain("clinical_trial")
    assert notice.validation_status.value == "out_of_scope"
    assert "fuori dal perimetro" in notice.warning


def test_report_records_ontology_and_domain_transparency(
    make_project: ProjectFactory,
) -> None:
    result = analyze_project(make_project({"m.md": METHODS}))
    assert result.report.versions.ontology_version == "0.1.0"
    assert result.report.domain_transparency.declared_domain == "quantitative_microscopy"
    assert result.report.domain_transparency.warning in result.report.limits


def test_ro_crate_is_json_ld_and_references_every_export(
    make_project: ProjectFactory, tmp_path: Path
) -> None:
    result = analyze_project(make_project({"m.md": METHODS}))
    written = write_all(result.report, tmp_path / "out")
    crate = json.loads(written["ro_crate"].read_text(encoding="utf-8"))

    assert crate["@context"][0] == "https://w3id.org/ro/crate/1.3/context"
    entities = {entity["@id"]: entity for entity in crate["@graph"]}
    assert entities["ro-crate-metadata.json"]["about"] == {"@id": "./"}
    root = entities["./"]
    referenced = {item["@id"] for item in root["hasPart"]}
    expected = {path.name for name, path in written.items() if name != "ro_crate"}
    assert referenced == expected
    assert root["ntruth:rulesetVersion"] == result.report.versions.ruleset_version
    assert root["ntruth:ontologyVersion"] == "0.1.0"
    assert root["ntruth:domainValidationStatus"] == "unvalidated"
    for file_id in referenced:
        assert len(entities[file_id]["sha256"]) == 64


def test_exported_report_can_be_reopened_with_checksum_validation(
    make_project: ProjectFactory, tmp_path: Path
) -> None:
    result = analyze_project(make_project({"m.md": METHODS}))
    written = write_all(result.report, tmp_path / "out")
    reopened = read_json(written["json"])
    assert report_to_dict(reopened) == report_to_dict(result.report)


def test_shared_application_is_the_cli_contract(
    make_project: ProjectFactory, tmp_path: Path
) -> None:
    project = make_project({"m.md": METHODS}, name="shared", project_name="shared")
    source = project.path_of(project.manifest.files[0])
    execution = execute_analysis(
        source,
        out=tmp_path / "application-out",
        project_dir=tmp_path / "application-project",
        language="it",
        domain="quantitative_microscopy",
    )
    exported = read_json(execution.written["json"])
    assert report_to_dict(exported) == report_to_dict(execution.result.report)
    assert {"json", "html", "graph_0", "ro_crate"} <= execution.written.keys()


def test_application_can_require_domain_acknowledgement(tmp_path: Path) -> None:
    source = tmp_path / "m.md"
    source.write_text(METHODS, encoding="utf-8")
    with pytest.raises(DomainAcknowledgementRequired):
        execute_analysis(
            source,
            out=tmp_path / "blocked-out",
            project_dir=tmp_path / "blocked-project",
            require_domain_acknowledgement=True,
        )
    assert not (tmp_path / "blocked-project" / "sources" / "m.md").exists()


def test_cli_requires_domain_acknowledgement_before_analysis(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from ntruth.cli.main import app

    source = tmp_path / "cli.md"
    source.write_text(METHODS, encoding="utf-8")
    result = CliRunner().invoke(app, ["analyze", str(source), "--out", str(tmp_path / "cli-out")])
    assert result.exit_code == 2, result.output
    assert "ATTENZIONE DOMINIO" in result.output
    assert "--acknowledge-unvalidated-domain" in result.output
    assert "Progetto:" not in result.output


def test_cli_continues_after_explicit_domain_acknowledgement(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from ntruth.cli.main import app

    source = tmp_path / "cli.md"
    source.write_text(METHODS, encoding="utf-8")
    result = CliRunner().invoke(
        app,
        [
            "analyze",
            str(source),
            "--out",
            str(tmp_path / "cli-out"),
            "--acknowledge-unvalidated-domain",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Progetto:" in result.output


def test_application_and_ro_crate_preserve_multiple_blocks(tmp_path: Path) -> None:
    source = tmp_path / "multi.md"
    source.write_text(MULTI_METHODS, encoding="utf-8")
    execution = execute_analysis(
        source,
        out=tmp_path / "multi-out",
        project_dir=tmp_path / "multi-project",
    )
    assert len(execution.result.report.blocks) == 2
    assert {"graph_0", "graph_1"} <= execution.written.keys()

    crate = json.loads(execution.written["ro_crate"].read_text(encoding="utf-8"))
    root = next(entity for entity in crate["@graph"] if entity["@id"] == "./")
    referenced = {item["@id"] for item in root["hasPart"]}
    assert {"graph.json", "graph-1.json"} <= referenced


def test_default_runs_are_isolated_and_previous_outputs_are_never_overwritten(
    tmp_path: Path,
) -> None:
    first_source = tmp_path / "first.md"
    second_source = tmp_path / "second.md"
    first_source.write_text(METHODS, encoding="utf-8")
    second_source.write_text(METHODS.replace("three", "four"), encoding="utf-8")
    output_root = tmp_path / "shared-output-root"

    first = execute_analysis(first_source, out=output_root)
    first_report = first.written["json"].read_bytes()
    first_manifest = (first.run_dir / "project" / "manifest.json").read_bytes()
    second = execute_analysis(second_source, out=output_root)

    assert first.run_id != second.run_id
    assert first.run_dir != second.run_dir
    assert first.written["json"].parent.name == "0000"
    assert second.written["json"].parent.name == "0000"
    assert first.written["json"].read_bytes() == first_report
    assert (first.run_dir / "project" / "manifest.json").read_bytes() == first_manifest
    assert sorted(path.name for path in (output_root / "runs").iterdir()) == sorted(
        [first.run_id, second.run_id]
    )
    assert not list((output_root / "runs").glob(".*.tmp"))


def test_concurrent_corrections_are_serialized_into_atomic_immutable_revisions(
    tmp_path: Path,
) -> None:
    source = tmp_path / "concurrent.md"
    source.write_text(METHODS, encoding="utf-8")
    execution = execute_analysis(source, out=tmp_path / "concurrent-out")
    session = SessionRegistry().create(execution)
    block = execution.result.report.blocks[0]
    original_value = block.n_statements[0].value
    assert original_value is not None

    barrier = Barrier(3)

    def mutate(label: str, path: str, value: object) -> int:
        barrier.wait()

        def build(ledger: CorrectionLedger) -> Correction:
            return Correction(
                id=stable_id(
                    "cor",
                    label,
                    ledger.current_checksum,
                    ledger.next_sequence,
                ),
                sequence=ledger.next_sequence,
                reason=CorrectionReason.TYPO,
                rationale=f"Correzione concorrente indipendente per {label}.",
                patch=({"op": "replace", "path": path, "value": value},),
                reviewer_role="concurrency_test",
            )

        return session.apply_generated(block.id, build).execution.revision

    with ThreadPoolExecutor(max_workers=2) as pool:
        title_future = pool.submit(mutate, "title", "/title", "Titolo concorrente")
        value_future = pool.submit(
            mutate,
            "n-value",
            "/n_statements/0/value",
            original_value + 1,
        )
        barrier.wait()
        revisions = sorted([title_future.result(), value_future.result()])

    assert revisions == [1, 2]
    assert session.execution.revision == 2
    final_ledger = session.ledger(block.id)
    assert len(final_ledger.records) == 2
    assert len(final_ledger.audit_trail) == 2
    assert final_ledger.current_block.title == "Titolo concorrente"
    assert final_ledger.current_block.n_statements[0].value == original_value + 1

    revisions_dir = execution.run_dir / "revisions"
    assert sorted(path.name for path in revisions_dir.iterdir()) == ["0000", "0001", "0002"]
    assert not list(revisions_dir.glob(".*.tmp"))
    revision_two_crate = (revisions_dir / "0002" / "ro-crate-metadata.json").read_bytes()

    undone = session.undo(block.id)
    undone_payload = undone.candidate_payload
    undone_history = undone_payload["history_state"]
    assert isinstance(undone_history, dict)
    assert undone.execution.revision == 3
    assert undone_history["undo_available"] is True
    assert undone_history["redo_available"] is True
    assert undone_history["branching_occurred"] is False

    def branch_factory(ledger: CorrectionLedger) -> Correction:
        return Correction(
            id=stable_id("cor", "branch", ledger.current_checksum, ledger.next_sequence),
            sequence=ledger.next_sequence,
            reason=CorrectionReason.TYPO,
            rationale="Nuovo ramo dopo undo, conservando integralmente l'audit.",
            patch=({"op": "replace", "path": "/title", "value": "Ramo alternativo"},),
            reviewer_role="concurrency_test",
        )

    branched = session.apply_generated(block.id, branch_factory)
    candidate_path = branched.execution.written[branched.candidate_artifact_name]
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    history = candidate["history_state"]
    assert history == {
        "audit_event_count": 4,
        "branching_occurred": True,
        "head_action": "apply",
        "redo_available": False,
        "undo_available": True,
    }

    crate_path = branched.execution.written["ro_crate"]
    crate = json.loads(crate_path.read_text(encoding="utf-8"))
    entities = {entity["@id"]: entity for entity in crate["@graph"]}
    candidate_entity = entities[candidate_path.name]
    assert candidate_entity["ntruth:contentChecksum"] == candidate["content_checksum"]
    assert (
        candidate_entity["ntruth:candidateAnnotationsChecksum"]
        == candidate["candidate_annotations_checksum"]
    )
    assert candidate_entity["ntruth:auditChecksum"] == candidate["audit_checksum"]
    assert candidate_entity["ntruth:auditEventCount"] == 4
    assert candidate_entity["ntruth:undoAvailable"] is True
    assert candidate_entity["ntruth:redoAvailable"] is False
    assert candidate_entity["ntruth:branchingOccurred"] is True
    root = entities["./"]
    assert {item["@id"] for item in root["ntruth:candidateAnnotationArtifacts"]} == {
        candidate_path.name
    }
    assert candidate_path.stat().st_mtime_ns <= crate_path.stat().st_mtime_ns
    assert (revisions_dir / "0002" / "ro-crate-metadata.json").read_bytes() == revision_two_crate


def test_failed_session_revision_is_not_published_or_made_current(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ntruth.api.sessions as sessions_module

    source = tmp_path / "atomic-failure.md"
    source.write_text(METHODS, encoding="utf-8")
    execution = execute_analysis(source, out=tmp_path / "atomic-failure-out")
    session = AnalysisSession(id="failure-test", execution=execution)
    block = execution.result.report.blocks[0]

    def fail_after_partial_write(
        report: object,
        out_dir: Path,
        **kwargs: object,
    ) -> dict[str, Path]:
        del report, kwargs
        (out_dir / "partial.tmp").write_text("partial", encoding="utf-8")
        raise OSError("simulated export failure")

    monkeypatch.setattr(sessions_module, "write_all", fail_after_partial_write)

    def build(ledger: CorrectionLedger) -> Correction:
        return Correction(
            id=stable_id("cor", "failure", ledger.current_checksum),
            sequence=ledger.next_sequence,
            reason=CorrectionReason.TYPO,
            rationale="La pubblicazione simulata deve fallire atomicamente.",
            patch=({"op": "replace", "path": "/title", "value": "Non pubblicato"},),
        )

    with pytest.raises(OSError, match="simulated export failure"):
        session.apply_generated(block.id, build)

    assert session.execution.revision == 0
    assert session.execution.result.report.blocks[0].title == block.title
    assert not (execution.run_dir / "revisions" / "0001").exists()
    assert not list((execution.run_dir / "revisions").glob(".*.tmp"))


def test_fastapi_health_acknowledgement_report_and_parity(tmp_path: Path) -> None:
    pytest.importorskip("fastapi", reason="installare l'extra api")
    pytest.importorskip("httpx2", reason="installare l'extra api")
    from fastapi.testclient import TestClient

    from ntruth.api.app import create_app

    source = tmp_path / "source"
    source.mkdir()
    (source / "m.md").write_text(METHODS, encoding="utf-8")

    direct = execute_analysis(
        source,
        out=tmp_path / "direct-out",
        project_dir=tmp_path / "direct-project",
        language="it",
        domain="quantitative_microscopy",
    )

    client = TestClient(create_app())
    health = client.get("/v1/health")
    assert health.status_code == 200
    assert health.json()["offline_core"] is True

    payload: dict[str, object] = {
        "source": str(source),
        "out": str(tmp_path / "api-out"),
        "project_dir": str(tmp_path / "api-project"),
        "language": "it",
        "domain": "quantitative_microscopy",
    }
    blocked = client.post("/v1/analyze", json=payload)
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "domain_acknowledgement_required"

    payload["acknowledge_unvalidated_domain"] = True
    response = client.post("/v1/analyze", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["report"] == report_to_dict(direct.result.report)
    assert "ro_crate" in body["artifacts"]
    assert body["revision"] == 0
    assert Path(body["output_dir"]).name == body["run_id"]
    session_id = body["session_id"]
    block = body["report"]["blocks"][0]
    block_id = block["id"]
    source_question_ids = {item["id"] for item in block["questions"]}
    factor = block["factors"][0]
    contrast = block["contrasts"][0]
    endpoint = block["endpoints"][0]
    statement = block["n_statements"][0]
    old_value = statement["value"]
    evidence_ids = statement["evidence_ids"]

    confirmed = client.post(
        "/v1/design/inference-targets/confirm",
        json={
            "session_id": session_id,
            "block_id": block_id,
            "target": {
                "question_text": "NGF modifica l'intensita per cellula?",
                "claim_text": "Effetto di NGF nelle preparazioni neuronali studiate.",
                "population_of_inference": "preparazioni neuronali nelle condizioni dichiarate",
                "factor_ids": [factor["id"]],
                "contrast_ids": [contrast["id"]],
                "endpoint_ids": [endpoint["id"]],
                "target_biological_unit": "CellCulture",
                "rationale": "Target dichiarato dal ricercatore prima della compilazione.",
                "reviewer_role": "researcher",
                "estimands": [
                    {
                        "endpoint_id": endpoint["id"],
                        "effect_measure": "mean difference",
                        "target_population_or_unit": "preparazioni neuronali studiate",
                        "generalization_level": "preparazioni nelle condizioni dichiarate",
                        "factor_ids": [factor["id"]],
                    }
                ],
            },
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    confirmed_body = confirmed.json()
    assert confirmed_body["revision"] == 1
    confirmed_block = confirmed_body["report"]["blocks"][0]
    assert confirmed_block["inference_targets"][0]["status"] == "user_confirmed"
    assert confirmed_block["estimands"][0]["effect_measure"] == "mean difference"
    assert source_question_ids <= {item["id"] for item in confirmed_block["questions"]}
    compilation = confirmed_body["report"]["design_compilations"][block_id]
    assert compilation["status"] == "ready"
    assert compilation["analysis_handoff"]["prohibited_outputs"] == [
        "statistical_test_selection",
        "model_formula",
        "power_analysis",
    ]

    corrected = client.post(
        "/v1/corrections/apply",
        json={
            "session_id": session_id,
            "block_id": block_id,
            "correction": {
                "reason": "typo",
                "rationale": "Il valore corretto e riportato nella fonte primaria.",
                "patch": [
                    {
                        "op": "replace",
                        "path": "/n_statements/0/value",
                        "value": old_value + 1,
                    }
                ],
                "evidence_ids": evidence_ids,
                "reviewer_role": "reviewer",
            },
        },
    )
    assert corrected.status_code == 200, corrected.text
    corrected_body = corrected.json()
    assert corrected_body["revision"] == 2
    corrected_block = corrected_body["report"]["blocks"][0]
    assert corrected_block["n_statements"][0]["value"] == old_value + 1
    assert corrected_body["recalculation_ms"] < 2_000
    assert corrected_body["candidate_annotations"]["gold_status"] == "not_gold"
    assert corrected_body["candidate_annotations"]["training_eligible"] is False
    assert block_id in corrected_body["report"]["rule_evaluations"]

    candidate_download = client.get(
        f"/v1/sessions/{session_id}/artifacts/{corrected_body['candidate_artifact_name']}"
    )
    assert candidate_download.status_code == 200
    assert candidate_download.json()["content_checksum"]

    undone = client.post(
        "/v1/corrections/undo",
        json={"session_id": session_id, "block_id": block_id},
    )
    assert undone.status_code == 200
    assert undone.json()["revision"] == 3
    assert undone.json()["report"]["blocks"][0]["n_statements"][0]["value"] == old_value
    assert len(undone.json()["audit_trail"]) == 3

    redone = client.post(
        "/v1/corrections/redo",
        json={"session_id": session_id, "block_id": block_id},
    )
    assert redone.status_code == 200
    assert redone.json()["revision"] == 4
    assert redone.json()["report"]["blocks"][0]["n_statements"][0]["value"] == old_value + 1

    loaded = client.get("/v1/reports", params={"path": body["artifacts"]["json"]})
    assert loaded.status_code == 200
    assert loaded.json()["report_id"] == body["report"]["report_id"]
