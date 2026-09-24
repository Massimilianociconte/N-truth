"""Neutral JSON/YAML/HTML rendering regressions for PRD v8 ReportBundle."""

from __future__ import annotations

import json
from html import unescape
from pathlib import Path

import pytest
import test_prd_v8_quick_design as quick_design_fixture

from ntruth.derivation_theory.loader import load_canonical_bundle
from ntruth.schemas.report_bundle import build_report_bundle


def _bundle() -> object:
    _, submission = quick_design_fixture._submission()
    quick_design = __import__("ntruth.quick_design.v8", fromlist=["run_quick_design_v8"])
    result = quick_design.run_quick_design_v8(
        submission,
        conformance_bundle=load_canonical_bundle(
            quick_design_fixture.runtime_fixture.REPOSITORY_ROOT
        ),
    )
    return result.report_bundle


def _with_inference_limits(bundle: object, limits: tuple[str, ...]) -> object:
    return build_report_bundle(
        verified_pipeline_contexts=bundle.verified_pipeline_contexts,
        design_record_context=bundle.design_record_context,
        prospective_input_ledgers=bundle.prospective_input_ledgers,
        source_records=bundle.source_records,
        evidence_records=bundle.evidence_records,
        ai_candidates=bundle.ai_candidates,
        human_confirmations=bundle.human_confirmations,
        conflicts=bundle.conflicts,
        sensitivities=bundle.sensitivities,
        questions=bundle.questions,
        statistical_handoff=bundle.statistical_handoff,
        inference_limits=limits,
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
    assert "INSUFFICIENT_INFORMATION" in html
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
