"""Regressions for fresh runtime preflight and transitive callable pin closure."""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import FunctionType
from typing import Any

import pytest
import test_prd_v8_derivation_runtime as base
from pydantic import BaseModel

import ntruth.derivation_theory.runtime as runtime
import ntruth.pipeline_v8 as pipeline
import ntruth.schemas.knowledge as knowledge
from ntruth.conformance.harness import (
    ConformanceFailureCode,
    evaluate_conformance,
)
from ntruth.derivation_theory.contracts import EvaluatorArtifactKind
from ntruth.derivation_theory.loader import canonical_checksum, load_canonical_bundle
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue

REPOSITORY_ROOT = Path(__file__).parents[2]


class _AbortPreflight(BaseException):
    pass


def _drifted_stable_id(prefix: str, *parts: object) -> str:
    return f"{prefix}-self-issued-live-pin-{len(parts)}"


def _allow_ambiguous_payload(_value: object) -> None:
    return None


def _live_reviewed_bundle(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Build a checksum-valid reviewed baseline without writing shared pin assets."""

    bundle = load_canonical_bundle(REPOSITORY_ROOT)
    rule_checksums = {
        rule.rule_id: runtime.rule_content_checksum(rule) for rule in bundle.rulebook.rules
    }
    monkeypatch.setattr(runtime, "_REVIEWED_RULE_CHECKSUM_BY_ID", rule_checksums)
    runtime._cached_derivation_dependency_checksum.cache_clear()
    dependency_checksum = runtime._derivation_dependency_checksum()
    adequacy_path = Path(runtime.__file__).resolve().parents[1] / "rules" / "v8_engine.py"
    adequacy_checksum = hashlib.sha256(adequacy_path.read_bytes()).hexdigest()

    pins = tuple(
        pin.model_copy(
            update={
                "theory_checksum": bundle.theory.declared_checksum,
                "rule_checksum": rule_checksums[pin.rule_id],
                "implementation_source_digest": (
                    runtime._derivation_code_checksum(
                        pin.theory_clause_id,
                        dependency_checksum=dependency_checksum,
                    )
                    if pin.evaluator_kind is EvaluatorArtifactKind.DERIVATION
                    else adequacy_checksum
                ),
            }
        )
        for pin in bundle.evaluator_registry.artifact_pins
    )
    registry = bundle.evaluator_registry.model_copy(update={"artifact_pins": pins})
    registry = registry.model_copy(
        update={
            "declared_checksum": canonical_checksum(
                registry.model_dump(mode="json", exclude_unset=True),
                exclude_declared_checksum=True,
            )
        }
    )
    rulebook = bundle.rulebook.model_copy(
        update={"evaluator_registry_checksum": registry.declared_checksum}
    )
    rulebook = rulebook.model_copy(
        update={
            "declared_checksum": canonical_checksum(
                rulebook.model_dump(mode="json", exclude_unset=True),
                exclude_declared_checksum=True,
            )
        }
    )
    bundle = bundle.model_copy(
        update={"rulebook": rulebook, "evaluator_registry": registry}
    )
    monkeypatch.setattr(runtime, "_REVIEWED_RULEBOOK_CHECKSUM", rulebook.declared_checksum)
    monkeypatch.setattr(
        runtime,
        "_REVIEWED_EVALUATOR_REGISTRY_CHECKSUM",
        registry.declared_checksum,
    )
    assert runtime.verify_runtime_bundle(bundle).passed is True
    return bundle


def _self_issued_bundle(bundle: Any) -> Any:
    dependency_checksum = runtime._derivation_dependency_checksum()
    pins = tuple(
        pin.model_copy(
            update={
                "implementation_source_digest": runtime._derivation_code_checksum(
                    pin.theory_clause_id,
                    dependency_checksum=dependency_checksum,
                )
            }
        )
        if pin.evaluator_kind is EvaluatorArtifactKind.DERIVATION
        else pin
        for pin in bundle.evaluator_registry.artifact_pins
    )
    registry = bundle.evaluator_registry.model_copy(update={"artifact_pins": pins})
    return bundle.model_copy(update={"evaluator_registry": registry})


def _pin_failures(report: Any) -> tuple[Any, ...]:
    return tuple(
        failure
        for failure in report.failures
        if failure.code is ConformanceFailureCode.PIN_MISMATCH
    )


def _canonical_request() -> Any:
    _, request = base._request()
    payload = BaseModel.model_dump(
        request,
        mode="python",
        exclude_unset=True,
        round_trip=True,
    )
    return runtime.V8DerivationInput.model_validate(payload)


def test_require_rejects_self_issued_live_pins_behind_stale_registry_checksum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _live_reviewed_bundle(monkeypatch)
    monkeypatch.setattr(runtime, "stable_id", _drifted_stable_id)
    forged = _self_issued_bundle(bundle)

    assert evaluate_conformance(forged).passed is True
    assert runtime.verify_runtime_bundle(forged).passed is False
    with pytest.raises(runtime.V8EvaluatorReviewRequired):
        runtime.require_reviewed_evaluator_bundle(forged)


def test_manifest_rejects_self_issued_live_pins_despite_caller_conformance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _live_reviewed_bundle(monkeypatch)
    monkeypatch.setattr(runtime, "stable_id", _drifted_stable_id)
    forged = _self_issued_bundle(bundle)
    caller_report = evaluate_conformance(forged)

    assert caller_report.passed is True
    with pytest.raises(runtime.V8EvaluatorReviewRequired):
        runtime.build_execution_manifest(forged, caller_report)


def test_manifest_uses_fresh_release_blockers_not_caller_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _live_reviewed_bundle(monkeypatch)
    fresh = runtime.verify_runtime_bundle(bundle)
    forged = fresh.model_copy(update={"release_blocker_issue_ids": ("SRR-FORGED",)})

    manifest = runtime.build_execution_manifest(bundle, forged)

    assert manifest.release_blocker_issue_ids == fresh.release_blocker_issue_ids
    assert manifest.release_blocker_issue_ids != forged.release_blocker_issue_ids


def test_transitive_validator_helper_drift_invalidates_warm_and_cold_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime._cached_derivation_dependency_checksum.cache_clear()
    reviewed = runtime._derivation_dependency_checksum()
    assert runtime._derivation_dependency_checksum() == reviewed
    warm_info = runtime._cached_derivation_dependency_checksum.cache_info()

    monkeypatch.setattr(
        knowledge,
        "ensure_unambiguous_scientific_payload",
        _allow_ambiguous_payload,
    )

    warm_drifted = runtime._derivation_dependency_checksum()
    runtime._cached_derivation_dependency_checksum.cache_clear()
    cold_drifted = runtime._derivation_dependency_checksum()
    assert warm_info.hits >= 1
    assert warm_drifted != reviewed
    assert cold_drifted == warm_drifted
    assert runtime._cached_derivation_dependency_checksum.cache_info().maxsize == 16


def test_equivalent_callable_replacements_are_digest_stable_and_cache_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = knowledge.ensure_unambiguous_scientific_payload
    runtime._cached_derivation_dependency_checksum.cache_clear()
    reviewed = runtime._derivation_dependency_checksum()
    replacements = [
        FunctionType(
            original.__code__,
            original.__globals__,
            original.__name__,
            original.__defaults__,
            original.__closure__,
        )
        for _ in range(24)
    ]
    for replacement in replacements:
        replacement.__kwdefaults__ = original.__kwdefaults__
        replacement.__qualname__ = original.__qualname__
        replacement.__module__ = original.__module__
        monkeypatch.setattr(
            knowledge,
            "ensure_unambiguous_scientific_payload",
            replacement,
        )
        assert runtime._derivation_dependency_checksum() == reviewed

    cache_info = runtime._cached_derivation_dependency_checksum.cache_info()
    assert cache_info.misses >= len(replacements)
    assert cache_info.maxsize == 16
    assert cache_info.currsize == 16


def test_code_constant_only_drift_changes_reviewed_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime._cached_derivation_dependency_checksum.cache_clear()
    reviewed = runtime._derivation_dependency_checksum()
    original_code = runtime.stable_id.__code__
    drifted_constants = tuple(
        ":" if value == "-" else value for value in original_code.co_consts
    )
    drifted_code = original_code.replace(co_consts=drifted_constants)
    assert drifted_code.co_code == original_code.co_code

    monkeypatch.setattr(runtime.stable_id, "__code__", drifted_code)

    assert runtime._derivation_dependency_checksum() != reviewed


def test_transitive_validator_helper_drift_rejects_reviewed_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _live_reviewed_bundle(monkeypatch)
    monkeypatch.setattr(
        knowledge,
        "ensure_unambiguous_scientific_payload",
        _allow_ambiguous_payload,
    )

    accepted = KnowledgeValue[object](
        knowledge_state=KnowledgeState.PRESENT,
        value=None,
        evidence_ids=("E-DRIFT",),
    )
    report = runtime.verify_runtime_bundle(bundle)

    assert accepted.value is None
    assert report.passed is False
    assert _pin_failures(report)


def test_ordinary_transitive_inspection_error_is_typed_at_every_public_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _live_reviewed_bundle(monkeypatch)
    caller_report = evaluate_conformance(bundle)
    original_getsource = runtime.inspect.getsource
    error = RuntimeError("transitive helper inspection failed")

    def broken_getsource(value: object) -> str:
        if value is knowledge.ensure_unambiguous_scientific_payload:
            raise error
        return original_getsource(value)

    monkeypatch.setattr(runtime.inspect, "getsource", broken_getsource)

    report = runtime.verify_runtime_bundle(bundle)
    assert report.passed is False
    assert _pin_failures(report)
    with pytest.raises(runtime.V8EvaluatorReviewRequired) as require_error:
        runtime.require_reviewed_evaluator_bundle(bundle)
    assert require_error.value.__cause__ is error
    with pytest.raises(runtime.V8EvaluatorReviewRequired) as manifest_error:
        runtime.build_execution_manifest(bundle, caller_report)
    assert manifest_error.value.__cause__ is error


def test_transitive_inspection_base_exception_propagates_from_every_public_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _live_reviewed_bundle(monkeypatch)
    caller_report = evaluate_conformance(bundle)
    original_getsource = runtime.inspect.getsource
    interrupted = _AbortPreflight("transitive helper inspection interrupted")

    def interrupted_getsource(value: object) -> str:
        if value is knowledge.ensure_unambiguous_scientific_payload:
            raise interrupted
        return original_getsource(value)

    monkeypatch.setattr(runtime.inspect, "getsource", interrupted_getsource)

    for call in (
        lambda: runtime.verify_runtime_bundle(bundle),
        lambda: runtime.require_reviewed_evaluator_bundle(bundle),
        lambda: runtime.build_execution_manifest(bundle, caller_report),
    ):
        with pytest.raises(_AbortPreflight) as captured:
            call()
        assert captured.value is interrupted


def test_pipeline_reports_structural_conformance_before_review_defense(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _live_reviewed_bundle(monkeypatch)
    request = _canonical_request()
    first_rule = bundle.rulebook.rules[0]
    malformed_rule = first_rule.model_copy(update={"theory_clause_id": "DT-Z-MISSING"})
    malformed = bundle.model_copy(
        update={
            "rulebook": bundle.rulebook.model_copy(
                update={"rules": (malformed_rule, *bundle.rulebook.rules[1:])}
            )
        }
    )

    with pytest.raises(pipeline.V8PipelineConformanceError) as captured:
        pipeline.run_v8_pipeline(request, conformance_bundle=malformed)

    assert captured.value.report.passed is False
    assert any(
        failure.code is ConformanceFailureCode.RULE_WITHOUT_THEORY_CLAUSE
        for failure in captured.value.report.failures
    )


def test_pipeline_preserves_review_required_for_live_implementation_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _live_reviewed_bundle(monkeypatch)
    request = _canonical_request()
    monkeypatch.setattr(runtime, "stable_id", _drifted_stable_id)

    with pytest.raises(runtime.V8EvaluatorReviewRequired):
        pipeline.run_v8_pipeline(request, conformance_bundle=bundle)
