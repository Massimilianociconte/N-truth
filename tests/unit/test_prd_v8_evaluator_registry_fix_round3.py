"""RED regressions for immutable, pre-reviewed evaluator implementation pins."""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path

import pytest
import test_prd_v8_derivation_runtime as base

from ntruth.derivation_theory.loader import canonical_checksum

REGISTRY_FILENAME = "reviewed-evaluator-registry-0.1.1.json"


def _assert_review_required(error: Exception) -> None:
    assert error.__class__.__name__ == "V8EvaluatorReviewRequired"
    assert error.review_requirement.issue_id == "SRR-V8-024"  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "drifted_function_name",
    ("_state_for", "_required_values", "derive_claim_set"),
)
def test_same_contract_derivation_source_drift_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    drifted_function_name: str,
) -> None:
    """Catches treating changed derivation bytes as reviewed under artifact v0.1.0."""

    pipeline = import_module("ntruth.pipeline_v8")
    runtime = import_module("ntruth.derivation_theory.runtime")
    _, request = base._request()
    original_getsource = runtime.inspect.getsource

    def drifted_source(function: object) -> str:
        source = original_getsource(function)
        if getattr(function, "__name__", None) == drifted_function_name:
            return source + "\n# unreviewed same-version semantic implementation drift\n"
        return source

    monkeypatch.setattr(runtime.inspect, "getsource", drifted_source)

    with pytest.raises(Exception) as error:
        pipeline.run_v8_pipeline(request, conformance_bundle=base.CANONICAL_BUNDLE)

    _assert_review_required(error.value)


def test_same_contract_adequacy_source_drift_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catches treating changed adequacy bytes as reviewed under artifact v0.1.0."""

    pipeline = import_module("ntruth.pipeline_v8")
    _, request = base._request()
    engine_path = (
        base.REPOSITORY_ROOT / "packages" / "ntruth" / "rules" / "v8_engine.py"
    ).resolve()
    original_read_bytes = Path.read_bytes

    def drifted_read_bytes(path: Path) -> bytes:
        payload = original_read_bytes(path)
        if path.resolve() == engine_path:
            return payload + b"\n# unreviewed same-version adequacy implementation drift\n"
        return payload

    monkeypatch.setattr(Path, "read_bytes", drifted_read_bytes)

    with pytest.raises(Exception) as error:
        pipeline.run_v8_pipeline(request, conformance_bundle=base.CANONICAL_BUNDLE)

    _assert_review_required(error.value)


def test_evaluator_registry_asset_tamper_fails_checksum_gate(tmp_path: Path) -> None:
    """Catches accepting edited reviewed digests behind a stale declared checksum."""

    source = base.REPOSITORY_ROOT / "theories" / REGISTRY_FILENAME
    assert source.is_file(), "the reviewed evaluator registry asset is required"
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["artifact_pins"][0]["implementation_source_digest"] = "0" * 64
    tampered = tmp_path / REGISTRY_FILENAME
    tampered.write_text(json.dumps(payload), encoding="utf-8")
    loader = import_module("ntruth.derivation_theory.loader")
    load_registry = getattr(loader, "load_evaluator_registry_file", None)
    assert callable(load_registry), "the evaluator registry requires a checksum-verifying loader"

    with pytest.raises(loader.AssetChecksumError):
        load_registry(tampered)


def test_registry_is_complete_and_pinned_into_execution_manifest() -> None:
    """Catches omitting a reviewed evaluator or dropping its immutable manifest join."""

    pipeline = import_module("ntruth.pipeline_v8")
    _, request = base._request()

    result = pipeline.run_v8_pipeline(request, conformance_bundle=base.CANONICAL_BUNDLE)
    registry = base.CANONICAL_BUNDLE.evaluator_registry

    assert len(registry.artifact_pins) == 8
    assert result.execution_manifest.evaluator_registry_id == registry.registry_id
    assert result.execution_manifest.evaluator_registry_version == registry.registry_version
    assert result.execution_manifest.evaluator_registry_checksum == registry.declared_checksum
    expected_digests = {
        pin.artifact_id: pin.implementation_source_digest for pin in registry.artifact_pins
    }
    for pin in result.execution_manifest.implementation_rules:
        assert expected_digests[pin.implementation_artifact_id] == (
            pin.implementation_artifact_checksum
        )
    adequacy = result.execution_manifest.adequacy_evaluator
    assert expected_digests[adequacy.implementation_artifact_id] == (
        adequacy.implementation_artifact_checksum
    )


def test_rechecksummed_registry_contract_drift_fails_rulebook_anchor() -> None:
    """Catches replacing reviewed registry bytes while retaining its version."""

    runtime = import_module("ntruth.derivation_theory.runtime")
    registry = base.CANONICAL_BUNDLE.evaluator_registry
    first = registry.artifact_pins[0]
    changed = registry.model_copy(
        update={
            "artifact_pins": (
                first.model_copy(update={"implementation_source_digest": "0" * 64}),
                *registry.artifact_pins[1:],
            )
        }
    )
    changed = changed.model_copy(
        update={
            "declared_checksum": canonical_checksum(
                changed.model_dump(mode="json", exclude_unset=True),
                exclude_declared_checksum=True,
            )
        }
    )
    bundle = base.CANONICAL_BUNDLE.model_copy(update={"evaluator_registry": changed})

    report = runtime.verify_runtime_bundle(bundle)

    assert report.passed is False
    assert any(failure.code.value == "CHECKSUM_MISMATCH" for failure in report.failures)
