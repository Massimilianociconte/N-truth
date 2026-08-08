"""Canonical Reality Gate is v8; v7 survives only through explicit adapters."""

from __future__ import annotations

from typer.testing import CliRunner

import ntruth.reality_gate as canonical
from ntruth.cli.main import app


def test_root_namespace_is_v8_and_does_not_export_unqualified_v7_evaluator() -> None:
    assert canonical.RealityGatePredicateNameV8.BLOCKING_SCHEMA_GAPS.value == (
        "blocking_schema_gaps"
    )
    assert not hasattr(canonical, "evaluate_reality_gate")
    assert not hasattr(canonical, "GatePredicateName")


def test_v7_gate_is_available_only_from_explicit_v7_namespace() -> None:
    from ntruth.reality_gate.v7 import GatePurposeV7, evaluate_reality_gate_v7

    result = evaluate_reality_gate_v7((), purpose=GatePurposeV7.MVT_A_EXPLORATORY)
    assert result.gate_version == "7.0.0"
    assert result.substantive_training_allowed is False


def test_cli_canonical_gate_reports_v8_hold_and_v7_is_deprecated_explicitly() -> None:
    canonical_result = CliRunner().invoke(app, ["quick-design", "reality-gate"])
    assert canonical_result.exit_code == 0
    assert "8.0.0" in canonical_result.stdout
    assert "HOLD" in canonical_result.stdout
    assert "SCIENTIFIC_REVIEW_REQUIRED" in canonical_result.stdout

    legacy = CliRunner().invoke(app, ["quick-design", "reality-gate-v7"])
    assert legacy.exit_code == 0
    assert "DEPRECATED_V7_ADAPTER" in legacy.stdout
