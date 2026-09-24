"""Ponte MLX ↔ resource manager con componenti mock (nessun MLX reale)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ntruth.runtime_resources import (
    BenchmarkIdentity,
    ComponentResult,
    ResourceSnapshot,
    RuntimeDevice,
    RuntimeProfileName,
    RuntimeResourceBudget,
    StageBenchmarkObservation,
    derive_stage_budget,
    load_runtime_resource_budget,
    save_runtime_resource_budget,
)
from ntruth.runtime_resources.budget_io import RuntimeBudgetIOError
from ntruth.training.mlx_resource_bridge import (
    DEFAULT_STAGE_ID,
    dump_bundle_runtime_metrics,
    estimate_input_tokens,
    run_predict_bundle,
)
from ntruth.training.mlx_runtime import MLXPipelineError
from ntruth.training.runtime_env import (
    detect_machine_model,
    detect_operating_system,
    detect_unified_memory_bytes,
    probe_runtime_environment,
)


def _identity(
    *,
    machine_model: str | None = None,
    unified_memory_bytes: int | None = None,
    operating_system: str | None = None,
    runtime_name: str = "test-runtime",
    runtime_version: str = "fixture-1",
) -> BenchmarkIdentity:
    return BenchmarkIdentity(
        benchmark_id="bridge-fixture-001",
        machine_model=machine_model or detect_machine_model(),
        unified_memory_bytes=unified_memory_bytes or detect_unified_memory_bytes(),
        operating_system=operating_system or detect_operating_system(),
        runtime_name=runtime_name,
        runtime_version=runtime_version,
        measured_at=datetime(2026, 8, 1, tzinfo=UTC),
    )


def _budget(
    *,
    stage_id: str = DEFAULT_STAGE_ID,
    profile: RuntimeProfileName = RuntimeProfileName.BALANCED,
    max_input_tokens: int = 10_000,
    max_latency_ms: float = 60_000.0,
    max_additional_peak_ram_bytes: int = 10_000_000,
    max_swap_delta_bytes: int = 10_000_000,
    identity: BenchmarkIdentity | None = None,
) -> RuntimeResourceBudget:
    identity = identity or _identity()
    observation = StageBenchmarkObservation(
        observation_id=f"obs-{stage_id}-1",
        benchmark_id=identity.benchmark_id,
        profile=profile,
        stage_id=stage_id,
        input_tokens=max_input_tokens,
        output_tokens=16,
        latency_ms=max_latency_ms,
        additional_peak_ram_bytes=max_additional_peak_ram_bytes,
        swap_delta_bytes=max_swap_delta_bytes,
    )
    return RuntimeResourceBudget(
        identity=identity,
        stages=(derive_stage_budget(identity, (observation,)),),
    )


class _Probe:
    def __init__(self) -> None:
        self._index = 0

    def snapshot(self) -> ResourceSnapshot:
        self._index += 1
        base = 1_000 + self._index
        return ResourceSnapshot(
            captured_at=datetime(2026, 8, 1, tzinfo=UTC) + timedelta(milliseconds=self._index),
            resident_ram_bytes=base,
            peak_resident_ram_bytes=base + 10,
            system_swap_used_bytes=0,
        )


class _FakeComponent:
    def __init__(self, device: RuntimeDevice, events: list[str]) -> None:
        self.device = device
        self.events = events
        self.closed = False
        events.append(f"load:{device.value}")

    def run(self, payload: object, *, context_window_tokens: int) -> ComponentResult:
        assert not self.closed
        assert context_window_tokens > 0
        if isinstance(payload, dict) and "prompt" in payload:
            text = f"echo:{payload['prompt']}"
        else:
            text = f"echo:{payload}"
        self.events.append(f"run:{text}")
        return ComponentResult(value=text, output_tokens=3)

    def close(self) -> None:
        if not self.closed:
            self.events.append(f"close:{self.device.value}")
            self.closed = True


def _factory(events: list[str]) -> Callable[[RuntimeDevice], _FakeComponent]:
    return lambda device: _FakeComponent(device, events)


def test_load_and_save_runtime_resource_budget_roundtrip(tmp_path: Path) -> None:
    budget = _budget()
    path = tmp_path / "budget.json"
    save_runtime_resource_budget(budget, path)
    loaded = load_runtime_resource_budget(path)
    assert loaded == budget
    # Nessun default inventato: i byte sono quelli salvati.
    assert loaded.identity.unified_memory_bytes == budget.identity.unified_memory_bytes


def test_load_runtime_resource_budget_fail_closed_on_invalid_schema(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text('{"identity": {"benchmark_id": "x"}, "stages": []}\n', encoding="utf-8")
    with pytest.raises(RuntimeBudgetIOError, match="schema budget non valido"):
        load_runtime_resource_budget(path)


def test_load_runtime_resource_budget_fail_closed_on_non_object(tmp_path: Path) -> None:
    path = tmp_path / "list.json"
    path.write_text("[1, 2]\n", encoding="utf-8")
    with pytest.raises(RuntimeBudgetIOError, match="oggetto JSON"):
        load_runtime_resource_budget(path)


def test_estimate_input_tokens_uses_len_over_four_without_tokenizer() -> None:
    assert estimate_input_tokens("abcd") == 1
    assert estimate_input_tokens("abcdefgh") == 2
    assert estimate_input_tokens({"prompt": "x" * 40}) == 10


def test_estimate_input_tokens_prefers_tokenizer() -> None:
    class _Tok:
        def encode(self, text: str, add_special_tokens: bool = False) -> list[int]:
            del add_special_tokens
            return [1, 2, 3, 4, 5]

    assert estimate_input_tokens("ignored-length", tokenizer=_Tok()) == 5


def test_probe_runtime_environment_has_positive_memory() -> None:
    env = probe_runtime_environment("unit-test-runtime", "0.0.0")
    assert env.unified_memory_bytes > 0
    assert env.machine_model
    assert "M5" not in env.machine_model or env.machine_model.startswith("Mac")
    # Non inventiamo etichette marketing: hw.model tipicamente e MacN,M.
    assert env.runtime_name == "unit-test-runtime"
    assert env.runtime_version == "0.0.0"


def test_run_predict_bundle_returns_none_without_budget() -> None:
    result = run_predict_bundle(
        requests=[{"prompt": "hi"}],
        resource_budget_path=None,
        component_fingerprint="a" * 64,
    )
    assert result is None


def test_env_mismatch_fails_with_mlx_pipeline_error(tmp_path: Path) -> None:
    budget = _budget(
        identity=_identity(
            machine_model="TEMPLATE-NOT-MEASURED-OTHER-HOST",
            unified_memory_bytes=123456789,
        )
    )
    path = tmp_path / "budget.json"
    save_runtime_resource_budget(budget, path)
    events: list[str] = []
    with pytest.raises(MLXPipelineError, match="ripetere il benchmark"):
        run_predict_bundle(
            requests=[{"prompt": "hi"}],
            resource_budget_path=path,
            resource_profile="BALANCED",
            component_fingerprint="b" * 64,
            runtime_name=budget.identity.runtime_name,
            runtime_version=budget.identity.runtime_version,
            component_factory=_factory(events),
            probe=_Probe(),
            require_complete_measurements=True,
        )
    assert events == []


def test_bridge_orchestration_with_fake_component(tmp_path: Path) -> None:
    budget = _budget()
    path = tmp_path / "budget.json"
    save_runtime_resource_budget(budget, path)
    events: list[str] = []
    execution = run_predict_bundle(
        requests=[
            {"prompt": "alpha"},
            {"prompt": "beta"},
        ],
        resource_budget_path=path,
        resource_profile="BALANCED",
        component_fingerprint="c" * 64,
        runtime_name=budget.identity.runtime_name,
        runtime_version=budget.identity.runtime_version,
        component_factory=_factory(events),
        probe=_Probe(),
        require_complete_measurements=True,
        bundle_id="unit-bridge",
        keep_warm=False,
    )
    assert execution is not None
    assert execution.outputs[DEFAULT_STAGE_ID] == ("echo:alpha", "echo:beta")
    metrics = dump_bundle_runtime_metrics(execution.metrics)
    assert metrics["bundle_id"] == "unit-bridge"
    assert metrics["profile"] == "BALANCED"
    assert metrics["total_output_tokens"] == 6
    assert events[0].startswith("load:")
    assert "run:echo:alpha" in events
    assert "run:echo:beta" in events
    assert any(item.startswith("close:") for item in events)


def test_missing_stage_in_budget_fails(tmp_path: Path) -> None:
    budget = _budget(stage_id="other_stage")
    path = tmp_path / "budget.json"
    save_runtime_resource_budget(budget, path)
    with pytest.raises(MLXPipelineError, match="assente dal budget"):
        run_predict_bundle(
            requests=[{"prompt": "x"}],
            resource_budget_path=path,
            resource_profile="BALANCED",
            component_fingerprint="d" * 64,
            runtime_name=budget.identity.runtime_name,
            runtime_version=budget.identity.runtime_version,
            component_factory=_factory([]),
            probe=_Probe(),
        )
