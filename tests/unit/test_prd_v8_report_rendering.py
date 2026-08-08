"""Neutral JSON/YAML/HTML rendering regressions for PRD v8 ReportBundle."""

from __future__ import annotations

import json
from html import unescape
from pathlib import Path

import pytest
import test_prd_v8_quick_design as quick_design_fixture
import test_prd_v8_task6_contracts as contract_fixture

from ntruth.derivation_theory.loader import load_canonical_bundle
from ntruth.schemas.report_bundle import build_report_bundle
from ntruth.schemas.report_resolution import TrivialExplicitReportResolutionPolicy


def _bundle() -> object:
    _, submission = quick_design_fixture._submission()
    quick_design = __import__("ntruth.quick_design.v8", fromlist=["run_quick_design_v8"])
    result = quick_design.run_quick_design_v8(
        submission,
        conformance_bundle=load_canonical_bundle(
            quick_design_fixture.runtime_fixture.REPOSITORY_ROOT
        ),
    )
    current = result.report_bundle
    claims = contract_fixture._determinate_claim_set(current.claim_sets[0])
    return build_report_bundle(
        design_record_context=current.design_record_context,
        source_records=current.source_records,
        ai_candidates=current.ai_candidates,
        human_confirmations=current.human_confirmations,
        conflicts=current.conflicts,
        confirmed_graph=current.confirmed_graph,
        claim_sets=(claims,),
        report_resolution=TrivialExplicitReportResolutionPolicy().resolve(claims),
        design_adequacy_evaluations=current.design_adequacy_evaluations,
        count_records=current.count_records,
        scenario_coverages=current.scenario_coverages,
        sensitivities=current.sensitivities,
        questions=current.questions,
        statistical_handoff=current.statistical_handoff,
        profile_coverage=current.profile_coverage,
        inference_limits=current.inference_limits,
        execution_manifest=current.execution_manifest,
    )


def _with_inference_limits(bundle: object, limits: tuple[str, ...]) -> object:
    return build_report_bundle(
        design_record_context=bundle.design_record_context,
        source_records=bundle.source_records,
        ai_candidates=bundle.ai_candidates,
        human_confirmations=bundle.human_confirmations,
        conflicts=bundle.conflicts,
        confirmed_graph=bundle.confirmed_graph,
        claim_sets=bundle.claim_sets,
        report_resolution=bundle.report_resolution,
        design_adequacy_evaluations=bundle.design_adequacy_evaluations,
        count_records=bundle.count_records,
        scenario_coverages=bundle.scenario_coverages,
        sensitivities=bundle.sensitivities,
        questions=bundle.questions,
        statistical_handoff=bundle.statistical_handoff,
        profile_coverage=bundle.profile_coverage,
        inference_limits=limits,
        execution_manifest=bundle.execution_manifest,
    )


def test_report_bundle_json_yaml_are_deterministic_and_round_trip(tmp_path: Path) -> None:
    rendering = __import__("ntruth.reporting.v8", fromlist=["report_bundle_to_dict"])
    bundle = _bundle()
    json_path = tmp_path / "report-v8.json"
    yaml_path = tmp_path / "report-v8.yaml"

    rendering.write_report_bundle_json(bundle, json_path)
    rendering.write_report_bundle_yaml(bundle, yaml_path)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    yaml_payload = json.loads(yaml_path.read_text(encoding="utf-8"))

    assert payload == yaml_payload == rendering.report_bundle_to_dict(bundle)
    assert payload["report_id"] == bundle.report_id
    assert payload["content_checksum"] == bundle.content_checksum
    assert rendering.read_report_bundle_json(json_path) == bundle


def test_report_bundle_html_has_all_neutral_axes_without_approval_language() -> None:
    rendering = __import__("ntruth.reporting.v8", fromlist=["render_report_bundle_html"])
    bundle = _bundle()
    html = rendering.render_report_bundle_html(bundle)
    lower = html.lower()

    for label in (
        "Sources and design context",
        "AI candidates",
        "Human confirmations and conflicts",
        "Query-scoped derived claims",
        "Proof and support",
        "Design adequacy findings",
        "Scenario and profile coverage",
        "Counts",
        "Sensitivity and questions",
        "Statistical handoff",
        "Inference limits",
    ):
        assert label in html
    assert "DETERMINATE" in html
    assert "INTERFERENCE_POSSIBLE" in html
    assert "NON_EXHAUSTIVE" in html
    assert "HANDOFF_ONLY" in html
    assert bundle.epistemic_boundary in unescape(html)
    assert "determinability is not design approval" in lower

    for forbidden in (
        "green",
        "ready_for_review",
        "candidate_analysis_strategies",
        "good design",
        "approved",
        "mixed model",
        " gee ",
    ):
        assert forbidden not in lower


def test_report_bundle_html_escapes_source_controlled_text() -> None:
    rendering = __import__("ntruth.reporting.v8", fromlist=["render_report_bundle_html"])
    bundle = _bundle()
    malicious = _with_inference_limits(bundle, ('<script>alert("x")</script>',))

    html = rendering.render_report_bundle_html(malicious)

    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_every_report_renderer_rejects_checksum_tampering(tmp_path: Path) -> None:
    rendering = __import__("ntruth.reporting.v8", fromlist=["render_report_bundle_html"])
    tampered = _bundle().model_copy(update={"content_checksum": "0" * 64})

    with pytest.raises(ValueError, match="checksum"):
        rendering.report_bundle_to_dict(tampered)
    with pytest.raises(ValueError, match="checksum"):
        rendering.render_report_bundle_html(tampered)
    with pytest.raises(ValueError, match="checksum"):
        rendering.write_report_bundle_json(tampered, tmp_path / "tampered.json")
