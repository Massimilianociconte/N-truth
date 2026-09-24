"""API locale di persistenza piano/esecuzione prospettico su SQLite append-only."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from ntruth.prospective import (
    ProspectiveD0Draft,
    ProspectiveDeviation,
    ProspectiveDeviationCategory,
    ProspectiveExecutionExclusion,
    ProspectiveGoldRecord,
    ProspectiveLostSample,
    ProspectivePlanExecutionRecord,
    ProspectivePoolingEvent,
    ProspectiveSubstitution,
    ProspectiveTreatmentChange,
)
from ntruth.sample_sheet import SampleLifecycleStatus, SampleSheetRow, SampleSheetSpec
from ntruth.schemas.experiment import ExclusionPhase, TriState


def _client():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx2")
    from fastapi.testclient import TestClient

    from ntruth.api.app import create_app

    return TestClient(create_app(), base_url="http://127.0.0.1")


def _design() -> ProspectiveD0Draft:
    return ProspectiveD0Draft(
        experiment_block_id="EB-PROSPECTIVE-1",
        title="Planned design",
        question_text="Does treatment alter the endpoint?",
        population_of_inference="declared experimental units",
        factor_name="treatment",
        factor_kind="treatment",
        level_a="vehicle",
        level_b="drug",
        endpoint_name="viability",
        endpoint_id="endpoint-1",
        measured_on="Well",
        allocation_level="Well",
        application_level="Well",
        independently_assigned=TriState.TRUE,
        independence_mechanism=(
            "Each well is assigned independently from the recorded randomisation list."
        ),
        target_biological_unit="Well",
        reviewer_role="researcher",
    )


def _row(
    sample_id: str,
    level: str,
    *,
    lifecycle: SampleLifecycleStatus = SampleLifecycleStatus.PLANNED,
    exclusion_reason: str | None = None,
) -> SampleSheetRow:
    return SampleSheetRow(
        sample_id=sample_id,
        source_id="source-1",
        preparation_id="preparation-1",
        well_id=sample_id,
        factor_levels={"factor_level_treatment": level},
        lifecycle_status=lifecycle,
        exclusion_reason=exclusion_reason,
    )


def _sheet(*rows: SampleSheetRow) -> SampleSheetSpec:
    return SampleSheetSpec(
        headers=(
            "sample_id",
            "source_id",
            "preparation_id",
            "well_id",
            "factor_level_treatment",
            "lifecycle_status",
            "exclusion_reason",
        ),
        factor_columns=("factor_level_treatment",),
        rows=rows,
    )


def _record() -> ProspectivePlanExecutionRecord:
    planned = _sheet(
        _row("P1", "vehicle"),
        _row("P2", "vehicle"),
        _row("P3", "vehicle"),
        _row("P4", "drug"),
        _row("P5", "drug"),
        _row("P6", "drug"),
    )
    final = _sheet(
        _row("P1", "drug", lifecycle=SampleLifecycleStatus.TREATED),
        _row(
            "P2",
            "vehicle",
            lifecycle=SampleLifecycleStatus.EXCLUDED,
            exclusion_reason="prespecified contamination criterion",
        ),
        _row("S4", "drug", lifecycle=SampleLifecycleStatus.TREATED),
        _row("POOL1", "drug", lifecycle=SampleLifecycleStatus.OBSERVED),
    )
    return ProspectivePlanExecutionRecord(
        record_id="plan-execution-1",
        planned_design=_design(),
        planned_sample_sheet=planned,
        executed_design=_design(),
        deviations=(
            ProspectiveDeviation(
                deviation_id="dev-1",
                category=ProspectiveDeviationCategory.PROCEDURE_CHANGE,
                description="Documented execution events changed the planned inventory.",
                affected_sample_ids=("P1", "P2", "P3", "P4", "P5", "P6", "S4", "POOL1"),
            ),
        ),
        substitutions=(
            ProspectiveSubstitution(
                substitution_id="sub-1",
                planned_sample_id="P4",
                substitute_sample_id="S4",
                reason="P4 failed pre-treatment quality control.",
            ),
        ),
        exclusions=(
            ProspectiveExecutionExclusion(
                exclusion_id="exc-1",
                sample_id="P2",
                reason="prespecified contamination criterion",
                phase=ExclusionPhase.POST_TREATMENT,
                prespecified=TriState.TRUE,
                author_role="wet_lab_reviewer",
            ),
        ),
        pooling=(
            ProspectivePoolingEvent(
                pooling_id="pool-1",
                input_sample_ids=("P5", "P6"),
                output_sample_id="POOL1",
                reason="Protocol-required pooled assay.",
            ),
        ),
        lost_samples=(
            ProspectiveLostSample(
                lost_sample_id="lost-1",
                sample_id="P3",
                phase="before measurement",
                reason="Sample container was lost during transfer.",
            ),
        ),
        treatment_changes=(
            ProspectiveTreatmentChange(
                treatment_change_id="treatment-1",
                sample_id="P1",
                factor_column="factor_level_treatment",
                planned_level="vehicle",
                executed_level="drug",
                reason="Recorded dispensing correction before treatment application.",
            ),
        ),
        final_sample_sheet=final,
        recorded_by_role="prospective_researcher",
    )


def test_health_exposes_plan_execution_persistence() -> None:
    client = _client()
    response = client.get("/v1/health")
    assert response.status_code == 200
    assert response.json()["plan_execution_persistence"] == "sqlite_append_only"


def test_append_get_and_promote_plan_execution_are_local_and_append_only(
    tmp_path: Path,
) -> None:
    client = _client()
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    project_id = "prj-api-plan-exec"
    record = _record()
    record_payload = record.model_dump(mode="json")

    created = client.post(
        "/v1/prospective/plan-execution",
        json={
            "project_id": project_id,
            "project_dir": str(project_dir),
            "record": record_payload,
            "actor_role": "prospective_researcher",
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["status"] == "candidate"
    assert body["project_id"] == project_id
    assert body["parent_candidate_id"] is None
    assert len(body["content_checksum"]) == 64
    assert body["payload"]["record_id"] == record.record_id
    assert (project_dir / "ntruth.sqlite3").is_file()

    # Idempotenza: stesso payload produce lo stesso record di storage.
    again = client.post(
        "/v1/prospective/plan-execution",
        json={
            "project_id": project_id,
            "project_dir": str(project_dir),
            "record": record_payload,
            "actor_role": "other_role",
        },
    )
    assert again.status_code == 200, again.text
    assert again.json()["record_id"] == body["record_id"]
    assert again.json()["content_checksum"] == body["content_checksum"]

    loaded = client.get(
        f"/v1/prospective/plan-execution/{body['record_id']}",
        params={"project_dir": str(project_dir)},
    )
    assert loaded.status_code == 200, loaded.text
    assert loaded.json()["payload"]["record_id"] == record.record_id
    assert loaded.json()["status"] == "candidate"

    gold = ProspectiveGoldRecord(
        gold_id="prospective-gold-api-1",
        plan_execution=record,
        source_annotation_ids=("annotation-a", "annotation-b"),
        reviewer_roles=("wet_lab_reviewer", "biostatistician"),
        adjudicator_role="independent_adjudicator",
        adjudicated_at=datetime(2026, 8, 1, tzinfo=UTC),
    )

    promoted = client.post(
        f"/v1/prospective/plan-execution/{body['record_id']}/gold",
        json={
            "project_dir": str(project_dir),
            "gold": gold.model_dump(mode="json"),
            "actor_role": "independent_adjudicator",
        },
    )
    assert promoted.status_code == 200, promoted.text
    gold_body = promoted.json()
    assert gold_body["status"] == "adjudicated_gold"
    assert gold_body["parent_candidate_id"] == body["record_id"]
    assert gold_body["payload"]["gold_id"] == "prospective-gold-api-1"
    assert gold_body["record_id"] != body["record_id"]

    # Il candidato non e mutato.
    candidate_after = client.get(
        f"/v1/prospective/plan-execution/{body['record_id']}",
        params={"project_dir": str(project_dir)},
    )
    assert candidate_after.status_code == 200
    assert candidate_after.json()["status"] == "candidate"
    assert candidate_after.json()["content_checksum"] == body["content_checksum"]

    # Secondo promote fallisce (fail-closed, un solo gold per candidato).
    conflict = client.post(
        f"/v1/prospective/plan-execution/{body['record_id']}/gold",
        json={
            "project_dir": str(project_dir),
            "gold": gold.model_dump(mode="json"),
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "plan_execution_gold_conflict"


def test_invalid_plan_execution_payload_is_rejected_without_write(tmp_path: Path) -> None:
    client = _client()
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    response = client.post(
        "/v1/prospective/plan-execution",
        json={
            "project_id": "prj-invalid",
            "project_dir": str(project_dir),
            "record": {"record_id": "incomplete"},
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "plan_execution_invalid"


def test_missing_plan_execution_record_is_404(tmp_path: Path) -> None:
    client = _client()
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    response = client.get(
        "/v1/prospective/plan-execution/not-present",
        params={"project_dir": str(project_dir)},
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "plan_execution_not_found"


def test_gold_plan_execution_mismatch_is_rejected(tmp_path: Path) -> None:
    client = _client()
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    record = _record()

    created = client.post(
        "/v1/prospective/plan-execution",
        json={
            "project_id": "prj-mismatch",
            "project_dir": str(project_dir),
            "record": record.model_dump(mode="json"),
        },
    )
    assert created.status_code == 200, created.text
    candidate_id = created.json()["record_id"]

    mismatched = ProspectiveGoldRecord(
        gold_id="prospective-gold-mismatch",
        plan_execution=record.model_copy(update={"record_id": "other-record-id"}),
        source_annotation_ids=("annotation-a", "annotation-b"),
        reviewer_roles=("wet_lab_reviewer", "biostatistician"),
        adjudicator_role="independent_adjudicator",
        adjudicated_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    response = client.post(
        f"/v1/prospective/plan-execution/{candidate_id}/gold",
        json={
            "project_dir": str(project_dir),
            "gold": mismatched.model_dump(mode="json"),
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "plan_execution_gold_mismatch"
