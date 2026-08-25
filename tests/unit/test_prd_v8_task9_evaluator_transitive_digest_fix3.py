"""Regressions for attribute callables and mutable callable cache tokens."""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType
from typing import Any

import pytest
import test_prd_v8_task9_evaluator_transitive_digest_fix2 as fix2

import ntruth.derivation_theory.runtime as runtime
import ntruth.schemas.knowledge as knowledge
from ntruth.conformance.harness import ConformanceFailureCode, evaluate_conformance

_ORIGINAL_JSON_DUMPS = knowledge.json.dumps


class _AbortAttributeResolution(BaseException):
    pass


class _CallableJsonDumps:
    def __call__(self, *args: Any, **kwargs: Any) -> str:
        return _ORIGINAL_JSON_DUMPS(*args, **kwargs)


def _drifted_json_dumps(*args: Any, **kwargs: Any) -> str:
    return _ORIGINAL_JSON_DUMPS(*args, **kwargs)


def _pin_failures(report: Any) -> tuple[Any, ...]:
    return tuple(
        failure
        for failure in report.failures
        if failure.code is ConformanceFailureCode.PIN_MISMATCH
    )


def _mutable_helper() -> tuple[Callable[[object], None], dict[str, dict[str, str]]]:
    default_payload = {"mode": "reviewed-default"}
    keyword_payload = {"mode": "reviewed-keyword"}
    closure_payload = {"mode": "reviewed-closure"}

    def helper(
        value: object,
        payload: dict[str, str] = default_payload,
        *,
        keyword: dict[str, str] = keyword_payload,
    ) -> None:
        del value
        if not payload or not keyword or not closure_payload:
            raise ValueError("mutable helper payload must remain addressable")

    return helper, {
        "defaults": default_payload,
        "kwdefaults": keyword_payload,
        "closure": closure_payload,
    }


def test_module_qualified_validator_callable_drift_changes_warm_and_cold_digest_and_pins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = fix2._live_reviewed_bundle(monkeypatch)
    runtime._cached_derivation_dependency_checksum.cache_clear()
    reviewed = runtime._derivation_dependency_checksum()
    assert runtime._derivation_dependency_checksum() == reviewed

    monkeypatch.setattr(knowledge.json, "dumps", _drifted_json_dumps)

    warm_drifted = runtime._derivation_dependency_checksum()
    runtime._cached_derivation_dependency_checksum.cache_clear()
    cold_drifted = runtime._derivation_dependency_checksum()
    report = runtime.verify_runtime_bundle(bundle)

    assert warm_drifted != reviewed
    assert cold_drifted == warm_drifted
    assert report.passed is False
    assert len(_pin_failures(report)) == 7
    assert {failure.clause_id for failure in _pin_failures(report)} == {
        clause.clause_id for clause in bundle.theory.clauses
    }


def test_non_python_module_qualified_callable_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = fix2._live_reviewed_bundle(monkeypatch)
    monkeypatch.setattr(knowledge.json, "dumps", _CallableJsonDumps())

    report = runtime.verify_runtime_bundle(bundle)

    assert report.passed is False
    assert len(_pin_failures(report)) == 7


@pytest.mark.parametrize("payload_name", ("defaults", "kwdefaults", "closure"))
def test_in_place_mutable_callable_payload_changes_warm_and_cold_digest(
    monkeypatch: pytest.MonkeyPatch,
    payload_name: str,
) -> None:
    helper, payloads = _mutable_helper()
    monkeypatch.setattr(knowledge, "ensure_unambiguous_scientific_payload", helper)
    runtime._cached_derivation_dependency_checksum.cache_clear()
    reviewed = runtime._derivation_dependency_checksum()
    assert runtime._derivation_dependency_checksum() == reviewed

    payloads[payload_name]["mode"] = f"drifted-{payload_name}"

    warm_drifted = runtime._derivation_dependency_checksum()
    runtime._cached_derivation_dependency_checksum.cache_clear()
    cold_drifted = runtime._derivation_dependency_checksum()

    assert warm_drifted != reviewed
    assert cold_drifted == warm_drifted
    assert runtime._cached_derivation_dependency_checksum.cache_info().maxsize == 16


def test_attribute_resolution_exception_is_typed_at_every_public_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = fix2._live_reviewed_bundle(monkeypatch)
    caller_report = evaluate_conformance(bundle)
    original_getattr_static = runtime.inspect.getattr_static
    error = RuntimeError("module-qualified callable resolution failed")

    def broken_getattr_static(value: object, name: str, *default: object) -> object:
        if isinstance(value, ModuleType) and value is knowledge.json and name == "dumps":
            raise error
        return original_getattr_static(value, name, *default)

    monkeypatch.setattr(runtime.inspect, "getattr_static", broken_getattr_static)

    report = runtime.verify_runtime_bundle(bundle)
    assert report.passed is False
    assert len(_pin_failures(report)) == 7
    with pytest.raises(runtime.V8EvaluatorReviewRequired) as require_error:
        runtime.require_reviewed_evaluator_bundle(bundle)
    assert require_error.value.__cause__ is error
    with pytest.raises(runtime.V8EvaluatorReviewRequired) as manifest_error:
        runtime.build_execution_manifest(bundle, caller_report)
    assert manifest_error.value.__cause__ is error


def test_attribute_resolution_base_exception_propagates_from_every_public_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = fix2._live_reviewed_bundle(monkeypatch)
    caller_report = evaluate_conformance(bundle)
    original_getattr_static = runtime.inspect.getattr_static
    interrupted = _AbortAttributeResolution("module-qualified resolution interrupted")

    def interrupted_getattr_static(value: object, name: str, *default: object) -> object:
        if isinstance(value, ModuleType) and value is knowledge.json and name == "dumps":
            raise interrupted
        return original_getattr_static(value, name, *default)

    monkeypatch.setattr(runtime.inspect, "getattr_static", interrupted_getattr_static)

    for call in (
        lambda: runtime.verify_runtime_bundle(bundle),
        lambda: runtime.require_reviewed_evaluator_bundle(bundle),
        lambda: runtime.build_execution_manifest(bundle, caller_report),
    ):
        with pytest.raises(_AbortAttributeResolution) as captured:
            call()
        assert captured.value is interrupted
