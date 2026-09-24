"""Truthful wording for the evaluator registry engineering identity gate."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

import ntruth.derivation_theory.runtime as runtime
from ntruth.conformance.harness import ConformanceFailureCode, evaluate_conformance
from ntruth.derivation_theory.contracts import (
    ReviewedEvaluatorArtifactPin,
    ReviewedEvaluatorRegistry,
)
from ntruth.derivation_theory.loader import load_canonical_bundle

REPOSITORY_ROOT = Path(__file__).parents[2]


def test_registry_gate_and_pin_diagnostics_do_not_claim_external_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches promoting an engineering identity pin to scientific review evidence."""

    gate_description = runtime._evaluator_pin_check.__doc__ or ""
    blocker = runtime.V8EvaluatorReviewRequired(clause_id="DT-A-ASSIGNMENT-UNIT")
    wording = " ".join(
        (
            gate_description,
            str(blocker),
            blocker.review_requirement.rationale,
        )
    ).casefold()

    assert "engineering-pinned" in wording
    assert "engineering identity" in wording
    assert "external reviewed" not in wording
    assert "explicitly reviewed evaluator" not in wording
    assert "no reviewed v8 evaluator" not in wording

    monkeypatch.setattr(runtime, "_derivation_dependency_checksum", lambda: "0" * 64)
    pin_failures = tuple(
        failure
        for failure in runtime._evaluator_pin_check(load_canonical_bundle(REPOSITORY_ROOT)).failures
        if failure.code is ConformanceFailureCode.PIN_MISMATCH and failure.rule_id is not None
    )

    assert len(pin_failures) == 7
    assert all("engineering-pinned" in failure.message for failure in pin_failures)
    assert all("reviewed registry" not in failure.message for failure in pin_failures)


def test_contract_and_repository_descriptions_identify_engineering_pins() -> None:
    """Catches presenting code-identity records as scientific review artifacts."""

    contract_wording = " ".join(
        (
            ReviewedEvaluatorArtifactPin.__doc__ or "",
            ReviewedEvaluatorRegistry.__doc__ or "",
        )
    ).casefold()
    readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8").casefold()

    assert "engineering identity" in contract_wording
    assert "scientific executable reviewed" not in contract_wording
    assert "pre-reviewed" not in contract_wording
    assert "engineering identity pins" in readme
    assert "reviewed code pins" not in readme


def test_cross_asset_diagnostics_describe_engineering_identity_pins() -> None:
    """Catches conformance failures implying that code-identity pins are reviewed."""

    bundle = load_canonical_bundle(REPOSITORY_ROOT)
    pins = list(bundle.evaluator_registry.artifact_pins)
    pins[0] = pins[0].model_copy(update={"theory_clause_id": pins[1].theory_clause_id})
    mutated = bundle.model_copy(
        update={
            "evaluator_registry": bundle.evaluator_registry.model_copy(
                update={"artifact_pins": tuple(pins)}
            )
        }
    )

    pin_messages = tuple(
        failure.message.casefold()
        for failure in evaluate_conformance(mutated).failures
        if failure.code is ConformanceFailureCode.PIN_MISMATCH
        and "evaluator" in failure.message.casefold()
    )

    assert len(pin_messages) == 2
    assert all("engineering" in message for message in pin_messages)
    assert all("reviewed evaluator" not in message for message in pin_messages)


def test_duplicate_pin_diagnostic_describes_engineering_identity_registry() -> None:
    """Catches a validation error presenting identity pins as review evidence."""

    registry_payload = load_canonical_bundle(REPOSITORY_ROOT).evaluator_registry.model_dump(
        mode="json"
    )
    registry_payload["artifact_pins"][1] = registry_payload["artifact_pins"][0]

    with pytest.raises(ValidationError) as captured:
        ReviewedEvaluatorRegistry.model_validate(registry_payload)

    message = str(captured.value).casefold()
    assert "engineering identity registry contains duplicate artifact pins" in message
    assert "reviewed evaluator registry" not in message
