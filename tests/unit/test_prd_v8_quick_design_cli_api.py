"""Explicit PRD v8 Quick Design CLI/API surfaces and qualified v7 adapters."""

from __future__ import annotations

import json
from pathlib import Path

import test_prd_v8_quick_design as quick_design_fixture
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from ntruth.api.app import create_app
from ntruth.cli.main import app
from ntruth.schemas.authority import AuthorityType
from ntruth.schemas.prospective import SupportBindingScope, build_prospective_input_ledger
from ntruth.schemas.support import EvidenceBasis, EvidenceTypeV8


def _submission_payload(*, raw_wizard: bool = False) -> dict[str, object]:
    _, submission = quick_design_fixture._submission()
    if raw_wizard:
        supports = {
            clause_id: descriptor.model_copy(
                update={
                    "authority_type": AuthorityType.USER_CONFIRMATION,
                    "evidence_basis": EvidenceBasis.AUTHOR_ASSERTED,
                    "support_grade": descriptor.support_grade.model_copy(
                        update={"token": "ASSERTION_ONLY"}
                    ),
                }
            )
            for clause_id, descriptor in submission.pipeline_request.support_by_clause.items()
        }
        request = submission.pipeline_request.model_copy(update={"support_by_clause": supports})
        default_support = next(iter(supports.values()))
        bindings = tuple(
            binding.model_copy(
                update={
                    "support": (
                        supports[binding.scope_id]
                        if binding.scope_kind is SupportBindingScope.THEORY_CLAUSE
                        else default_support
                    )
                }
            )
            for binding in submission.input_ledger.support_bindings
        )
        evidence_records = tuple(
            record.model_copy(update={"evidence_type": EvidenceTypeV8.AUTHOR_ASSERTION})
            for record in submission.input_ledger.evidence_records
        )
        ledger = build_prospective_input_ledger(
            request=request,
            sources=submission.input_ledger.sources,
            evidence_records=evidence_records,
            confirmation_events=(),
            artifacts=submission.input_ledger.artifacts,
            support_bindings=bindings,
        )
        handoff = submission.statistical_handoff.model_copy(
            update={
                "items": tuple(
                    item.model_copy(update={"authority": AuthorityType.USER_CONFIRMATION})
                    for item in submission.statistical_handoff.items
                )
            }
        )
        submission = submission.model_validate(
            submission.model_copy(
                update={
                    "pipeline_request": request,
                    "input_ledger": ledger,
                    "statistical_handoff": handoff,
                }
            ).model_dump(mode="python")
        )
    return submission.model_dump(mode="json")


def test_unqualified_quick_design_run_is_v8_and_writes_neutral_bundle(tmp_path: Path) -> None:
    submission_path = tmp_path / "quick-design-v8.json"
    submission_path.write_text(
        json.dumps(_submission_payload(raw_wizard=True), ensure_ascii=False),
        encoding="utf-8",
    )
    output = tmp_path / "out"

    result = CliRunner().invoke(
        app,
        ["quick-design", "run", str(submission_path), "--out", str(output)],
    )

    assert result.exit_code == 0, result.output
    assert "PRD_V8" in result.output
    assert "HANDOFF_ONLY" in result.output
    assert "DEPRECATED_V7_ADAPTER" not in result.output
    assert (output / "planned-design-v8.json").is_file()
    assert (output / "report-v8.json").is_file()
    assert (output / "report-v8.yaml").is_file()
    html = (output / "report-v8.html").read_text(encoding="utf-8").lower()
    assert "determinability is not design approval" in html
    assert "green" not in html


def test_unqualified_quick_design_run_no_longer_accepts_v7_flags(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        ["quick-design", "run", "--source", "cells", "--n-per-level", "2"],
    )

    assert result.exit_code == 2
    assert "DEPRECATED_V7_ADAPTER" not in result.output


def test_explicit_quick_design_v7_cli_is_visibly_deprecated() -> None:
    result = CliRunner().invoke(
        app,
        [
            "quick-design",
            "run-v7",
            "--source",
            "cells",
            "--n-per-level",
            "2",
            "--planned-unit-type",
            "well",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "DEPRECATED_V7_ADAPTER" in result.output


def test_v8_quick_design_api_returns_canonical_neutral_report() -> None:
    client = TestClient(create_app())

    response = client.post("/v8/quick-design", json=_submission_payload(raw_wizard=True))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["contract"] == {
        "code": "PRD_V8",
        "version": "8.0.0",
        "strategy_module_status": "HANDOFF_ONLY",
        "input_mode": "RAW_AUTHOR_ASSERTED",
        "guided_confirmation": False,
    }
    assert body["planned_design"]["plan_id"].startswith("PLAN-")
    assert body["report"]["report_id"].startswith("REPORT-")
    assert body["report"]["strategy_module_status"] == "HANDOFF_ONLY"


def test_v8_quick_design_api_rejects_direct_scientific_verdict_fields() -> None:
    client = TestClient(create_app())
    payload = _submission_payload()
    payload["determinability"] = "DETERMINATE"
    payload["design_adequate"] = True

    response = client.post("/v8/quick-design", json=payload)

    assert response.status_code == 422


def test_explicit_v7_quick_design_api_is_qualified_and_deprecated() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/v7/quick-design",
        json={"source_description": "cells", "planned_units_per_level": 2},
    )

    assert response.status_code == 200, response.text
    assert response.json()["contract"] == {
        "code": "DEPRECATED_V7_ADAPTER",
        "version": "v7",
    }
