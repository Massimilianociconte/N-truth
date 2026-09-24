"""Per-operation verification memo: faster, never weaker.

The scope may skip a deterministic re-verification only for byte-identical
content already verified in the same operation. Tampered content (even with a
recomputed checksum), failures and calls outside a scope are always re-verified.
"""

from __future__ import annotations

from typing import Any

import pytest
import test_prd_v8_derivation_runtime as runtime_fixture

import ntruth.pipeline_v8 as pipeline
from ntruth.schemas.core import content_checksum
from ntruth.schemas.report_bundle import VerifiedPipelineContext, build_verified_pipeline_context
from ntruth.verification_scope import (
    already_verified,
    record_verified,
    verification_scope,
    within_verification_scope,
)


def _counting_executions(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    calls: list[int] = []
    original = pipeline._execute_v8_pipeline

    def counted(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(pipeline, "_execute_v8_pipeline", counted)
    return calls


def _context() -> VerifiedPipelineContext:
    _, request = runtime_fixture._request()
    result = pipeline.run_v8_pipeline(request, conformance_bundle=runtime_fixture.CANONICAL_BUNDLE)
    return build_verified_pipeline_context(
        request=request,
        result=result,
        conformance_bundle=runtime_fixture.CANONICAL_BUNDLE,
    )


def _readdressed(payload: dict[str, Any]) -> dict[str, Any]:
    fields = {key: value for key, value in payload.items() if key not in {"context_id"}}
    fields.pop("content_checksum")
    checksum = content_checksum(fields)
    return {
        **fields,
        "context_id": f"PIPELINE-CONTEXT-{checksum[:20]}",
        "content_checksum": checksum,
    }


def test_helpers_are_inert_outside_a_scope() -> None:
    record_verified("namespace", "a" * 64)
    assert already_verified("namespace", "a" * 64) is False
    assert pipeline.memoized_results() is None


def test_outside_a_scope_every_validation_re_executes(monkeypatch: pytest.MonkeyPatch) -> None:
    context = _context()
    calls = _counting_executions(monkeypatch)
    payload = context.model_dump(mode="python")

    VerifiedPipelineContext.model_validate(payload)
    VerifiedPipelineContext.model_validate(payload)

    assert len(calls) == 2


def test_inside_a_scope_identical_content_is_re_executed_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context()
    calls = _counting_executions(monkeypatch)
    payload = context.model_dump(mode="python")

    with verification_scope():
        first = VerifiedPipelineContext.model_validate(payload)
        second = VerifiedPipelineContext.model_validate(payload)

    assert first == second == context
    assert len(calls) == 1


def test_tampered_result_with_recomputed_checksum_is_rejected_inside_scope() -> None:
    context = _context()
    payload = context.model_dump(mode="json")
    forged = dict(payload)
    forged_result = dict(forged["result_payload"])
    forged_result["stage_order"] = list(reversed(forged_result["stage_order"]))
    forged["result_payload"] = forged_result

    with verification_scope():
        VerifiedPipelineContext.model_validate(payload)
        with pytest.raises(ValueError, match="differs from Task4 re-execution"):
            VerifiedPipelineContext.model_validate(_readdressed(forged))


def test_failures_are_never_memoized() -> None:
    context = _context()
    payload = context.model_dump(mode="json")
    forged = dict(payload)
    forged_result = dict(forged["result_payload"])
    forged_result["stage_order"] = list(reversed(forged_result["stage_order"]))
    forged["result_payload"] = forged_result
    readdressed = _readdressed(forged)

    with verification_scope():
        for _ in range(2):
            with pytest.raises(ValueError, match="differs from Task4 re-execution"):
                VerifiedPipelineContext.model_validate(readdressed)


def test_scope_does_not_outlive_the_operation(monkeypatch: pytest.MonkeyPatch) -> None:
    context = _context()
    payload = context.model_dump(mode="python")

    @within_verification_scope
    def validate_twice() -> None:
        VerifiedPipelineContext.model_validate(payload)
        VerifiedPipelineContext.model_validate(payload)

    calls = _counting_executions(monkeypatch)
    validate_twice()
    validate_twice()

    assert len(calls) == 2
    assert pipeline.memoized_results() is None
