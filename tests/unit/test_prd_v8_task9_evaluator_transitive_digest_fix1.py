"""Fail-closed runtime verification for reviewed evaluator implementation pins."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import ntruth.derivation_theory.runtime as runtime
from ntruth.conformance.harness import ConformanceFailureCode, evaluate_conformance
from ntruth.derivation_theory.loader import load_canonical_bundle

REPOSITORY_ROOT = Path(__file__).parents[2]


class _AbortVerification(BaseException):
    pass


def _bundle() -> Any:
    return load_canonical_bundle(REPOSITORY_ROOT)


def _drifted_stable_id(prefix: str, *parts: object) -> str:
    return f"{prefix}-unreviewed-live-drift-{len(parts)}"


def _pin_failures(report: Any) -> tuple[Any, ...]:
    return tuple(
        failure
        for failure in report.failures
        if failure.code is ConformanceFailureCode.PIN_MISMATCH
    )


def test_runtime_bundle_verifier_resolves_every_live_derivation_pin_after_warmup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _bundle()
    assert runtime.verify_runtime_bundle(bundle).passed is True
    runtime._derivation_code_checksum("DT-A-ASSIGNMENT-UNIT")

    monkeypatch.setattr(runtime, "stable_id", _drifted_stable_id)

    report = runtime.verify_runtime_bundle(bundle)

    assert report.passed is False
    assert {failure.clause_id for failure in _pin_failures(report)} == {
        clause.clause_id for clause in bundle.theory.clauses
    }


def test_runtime_bundle_verifier_detects_schema_method_drift_after_warmup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _bundle()
    reviewed = runtime._derivation_code_checksum("DT-A-ASSIGNMENT-UNIT")
    original_schema = runtime.DerivedClaim.model_json_schema

    def drifted_schema(cls: type[object], *args: Any, **kwargs: Any) -> dict[str, Any]:
        del cls
        schema = original_schema(*args, **kwargs)
        return {**schema, "x-unreviewed-live-schema-drift": True}

    monkeypatch.setattr(runtime.DerivedClaim, "model_json_schema", classmethod(drifted_schema))

    assert runtime._derivation_code_checksum("DT-A-ASSIGNMENT-UNIT") != reviewed
    report = runtime.verify_runtime_bundle(bundle)
    assert report.passed is False
    assert _pin_failures(report)


def test_ordinary_dependency_error_is_typed_by_verify_and_manifest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _bundle()
    conformance = evaluate_conformance(bundle)

    def broken_schema(cls: type[object], *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        del cls
        raise RuntimeError("schema inspection failed")

    monkeypatch.setattr(runtime.DerivedClaim, "model_json_schema", classmethod(broken_schema))

    report = runtime.verify_runtime_bundle(bundle)
    assert report.passed is False
    assert _pin_failures(report)
    with pytest.raises(runtime.V8EvaluatorReviewRequired) as captured:
        runtime.build_execution_manifest(bundle, conformance)
    assert isinstance(captured.value.__cause__, RuntimeError)


def test_runtime_bundle_verifier_resolves_live_adequacy_pin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _bundle()
    original_read_bytes = Path.read_bytes

    def drifted_engine_bytes(path: Path) -> bytes:
        payload = original_read_bytes(path)
        return payload + b"\n# unreviewed drift\n" if path.name == "v8_engine.py" else payload

    monkeypatch.setattr(Path, "read_bytes", drifted_engine_bytes)

    report = runtime.verify_runtime_bundle(bundle)

    assert report.passed is False
    assert any(
        failure.code is ConformanceFailureCode.PIN_MISMATCH
        and failure.clause_id == "DT-E-INTERFERENCE-ESTIMAND"
        and "adequacy" in failure.message.casefold()
        for failure in report.failures
    )


def test_dependency_base_exception_propagates_from_verify_and_manifest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _bundle()
    conformance = evaluate_conformance(bundle)
    interrupted = _AbortVerification("schema inspection interrupted")

    def interrupted_schema(cls: type[object], *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        del cls
        raise interrupted

    monkeypatch.setattr(
        runtime.DerivedClaim,
        "model_json_schema",
        classmethod(interrupted_schema),
    )

    with pytest.raises(_AbortVerification) as verify_error:
        runtime.verify_runtime_bundle(bundle)
    assert verify_error.value is interrupted
    with pytest.raises(_AbortVerification) as manifest_error:
        runtime.build_execution_manifest(bundle, conformance)
    assert manifest_error.value is interrupted
