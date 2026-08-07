"""Contratti del resource manager senza caricare MLX o pesi reali."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from ntruth.runtime_resources import (
    BenchmarkEnvironmentMismatch,
    BenchmarkIdentity,
    ComponentLoadError,
    ComponentResult,
    ContextWindowExceeded,
    HierarchicalChunker,
    ResourceBudgetExceeded,
    ResourceSnapshot,
    RuntimeDevice,
    RuntimeEnvironment,
    RuntimeInput,
    RuntimeProfileName,
    RuntimeResourceBudget,
    RuntimeResourceManager,
    RuntimeSection,
    StageBenchmarkObservation,
    StageInvocation,
    derive_stage_budget,
    runtime_profile,
)


def _identity() -> BenchmarkIdentity:
    return BenchmarkIdentity(
        benchmark_id="m5-pro-24g-run-001",
        machine_model="MacBook Pro M5 Pro",
        unified_memory_bytes=24 * 1024**3,
        operating_system="macOS benchmark fixture",
        runtime_name="backend-under-test",
        runtime_version="candidate-1",
        measured_at=datetime(2026, 8, 1, tzinfo=UTC),
    )


def _environment() -> RuntimeEnvironment:
    identity = _identity()
    return RuntimeEnvironment(
        machine_model=identity.machine_model,
        unified_memory_bytes=identity.unified_memory_bytes,
        operating_system=identity.operating_system,
        runtime_name=identity.runtime_name,
        runtime_version=identity.runtime_version,
    )


def _budget(*stage_ids: str, max_input_tokens: int = 100) -> RuntimeResourceBudget:
    identity = _identity()
    stages = []
    for stage_id in stage_ids:
        stages.append(
            derive_stage_budget(
                identity,
                (
                    StageBenchmarkObservation(
                        observation_id=f"obs-{stage_id}-1",
                        benchmark_id=identity.benchmark_id,
                        profile=RuntimeProfileName.BALANCED,
                        stage_id=stage_id,
                        input_tokens=max_input_tokens,
                        output_tokens=10,
                        latency_ms=100.0,
                        additional_peak_ram_bytes=1_000,
                        swap_delta_bytes=100,
                    ),
                ),
            )
        )
    return RuntimeResourceBudget(identity=identity, stages=tuple(stages))


class _Probe:
    def __init__(self, snapshots: list[tuple[int | None, int | None, int | None]]) -> None:
        self._snapshots = iter(snapshots)
        self._index = 0

    def snapshot(self) -> ResourceSnapshot:
        resident, peak, swap = next(self._snapshots)
        self._index += 1
        return ResourceSnapshot(
            captured_at=datetime(2026, 8, 1, tzinfo=UTC) + timedelta(milliseconds=self._index),
            resident_ram_bytes=resident,
            peak_resident_ram_bytes=peak,
            system_swap_used_bytes=swap,
        )


class _Component:
    def __init__(self, component_id: str, device: RuntimeDevice, events: list[str]) -> None:
        self.component_id = component_id
        self.device = device
        self.events = events
        self.closed = False
        events.append(f"load:{component_id}:{device.value}")

    def run(self, payload: object, *, context_window_tokens: int) -> ComponentResult:
        assert not self.closed
        self.events.append(f"run:{self.component_id}:{payload}:{context_window_tokens}")
        return ComponentResult(value=f"{self.component_id}:{payload}", output_tokens=2)

    def close(self) -> None:
        if not self.closed:
            self.events.append(f"close:{self.component_id}:{self.device.value}")
            self.closed = True


class _FailingComponent(_Component):
    def run(self, payload: object, *, context_window_tokens: int) -> ComponentResult:
        self.events.append(f"fail:{self.component_id}:{payload}:{context_window_tokens}")
        raise RuntimeError("simulated component failure")


def _factory(component_id: str, events: list[str]) -> Callable[[RuntimeDevice], _Component]:
    return lambda device: _Component(component_id, device, events)


def test_profiles_are_policy_only_and_context_window_is_configurable() -> None:
    low = runtime_profile(RuntimeProfileName.LOW_MEMORY)
    balanced = runtime_profile(
        RuntimeProfileName.BALANCED,
        context_window_tokens=6_000,
        reserved_output_tokens=1_000,
        chunk_tokens=4_000,
        chunk_overlap_tokens=400,
    )
    quality = runtime_profile(RuntimeProfileName.QUALITY)

    assert low.max_cached_components == 0
    assert balanced.max_input_tokens == 5_000
    assert quality.context_window_tokens > balanced.context_window_tokens
    assert "ram" not in " ".join(runtime_profile(RuntimeProfileName.BALANCED).model_dump())


def test_budget_can_only_be_derived_from_homogeneous_measured_observations() -> None:
    identity = _identity()
    observations = (
        StageBenchmarkObservation(
            observation_id="obs-1",
            benchmark_id=identity.benchmark_id,
            profile=RuntimeProfileName.BALANCED,
            stage_id="entity_count",
            input_tokens=2_000,
            output_tokens=100,
            latency_ms=250.0,
            additional_peak_ram_bytes=1_000,
            swap_delta_bytes=0,
        ),
        StageBenchmarkObservation(
            observation_id="obs-2",
            benchmark_id=identity.benchmark_id,
            profile=RuntimeProfileName.BALANCED,
            stage_id="entity_count",
            input_tokens=2_500,
            output_tokens=120,
            latency_ms=300.0,
            additional_peak_ram_bytes=2_000,
            swap_delta_bytes=10,
        ),
    )

    budget = derive_stage_budget(identity, observations)

    assert budget.observation_ids == ("obs-1", "obs-2")
    assert budget.max_input_tokens == 2_500
    assert budget.max_additional_peak_ram_bytes == 2_000
    assert budget.max_swap_delta_bytes == 10
    assert budget.max_latency_ms == pytest.approx(300.0)
    with pytest.raises(ValueError, match="osservazioni reali"):
        derive_stage_budget(identity, ())


def test_hierarchical_chunking_preserves_section_boundaries_and_overlap() -> None:
    chunks = HierarchicalChunker(chunk_tokens=4, overlap_tokens=1).chunk_sections(
        (
            RuntimeSection(
                document_id="doc-1",
                section_id="methods",
                text="one two three four five six seven",
                start_offset=100,
                parent_section_id="paper",
                level=2,
            ),
            RuntimeSection(
                document_id="doc-1",
                section_id="results",
                text="alpha beta",
                start_offset=200,
                parent_section_id="paper",
                level=2,
            ),
        )
    )

    assert [(item.section_id, item.text) for item in chunks] == [
        ("methods", "one two three four"),
        ("methods", "four five six seven"),
        ("results", "alpha beta"),
    ]
    assert chunks[0].start == 100
    assert chunks[1].start == 114
    assert chunks[0].parent_section_id == "paper"
    assert max(item.token_count for item in chunks) == 4


def test_stages_run_sequentially_and_lru_evicts_with_explicit_close() -> None:
    events: list[str] = []
    captured = []
    manager = RuntimeResourceManager(
        profile=runtime_profile(RuntimeProfileName.BALANCED),
        budget=_budget("route", "extract", "verify"),
        environment=_environment(),
        probe=_Probe(
            [
                (100, 100, 0),
                (120, 120, 0),
                (120, 120, 0),
                (135, 135, 0),
                (135, 135, 0),
                (145, 145, 0),
            ]
        ),
        metrics_sink=captured.append,
    )
    stages = (
        StageInvocation(
            stage_id="route",
            component_id="encoder",
            component_fingerprint="a" * 64,
            factory=_factory("encoder", events),
            inputs=(RuntimeInput("a", 4),),
        ),
        StageInvocation(
            stage_id="extract",
            component_id="small-llm",
            component_fingerprint="b" * 64,
            factory=_factory("small-llm", events),
            inputs=(RuntimeInput("b", 5),),
        ),
        StageInvocation(
            stage_id="verify",
            component_id="small-llm",
            component_fingerprint="b" * 64,
            factory=_factory("small-llm", events),
            inputs=(RuntimeInput("c", 6),),
        ),
    )

    execution = manager.execute_bundle("bundle-1", stages)

    assert execution.outputs == {
        "route": ("encoder:a",),
        "extract": ("small-llm:b",),
        "verify": ("small-llm:c",),
    }
    assert events == [
        "load:encoder:metal",
        "run:encoder:a:100",
        "load:small-llm:metal",
        "close:encoder:metal",
        "run:small-llm:b:100",
        "run:small-llm:c:100",
    ]
    assert [item.cache_hit for item in execution.metrics.stages] == [False, False, True]
    assert [item.cache_evictions for item in execution.metrics.stages] == [0, 1, 0]
    assert execution.metrics.total_input_tokens == 15
    assert execution.metrics.total_output_tokens == 6
    assert execution.metrics.peak_resident_ram_bytes == 145
    assert captured == [execution.metrics]
    assert execution.metrics.stages[0].component_fingerprint == "a" * 64
    assert manager.cached_component_keys == (("small-llm", "b" * 64, RuntimeDevice.METAL),)
    assert manager.clear_cache() == 1
    assert events[-1] == "close:small-llm:metal"


def test_low_memory_profile_unloads_each_stage() -> None:
    events: list[str] = []
    low = runtime_profile(RuntimeProfileName.LOW_MEMORY)
    identity = _identity()
    observation = StageBenchmarkObservation(
        observation_id="low-route-1",
        benchmark_id=identity.benchmark_id,
        profile=RuntimeProfileName.LOW_MEMORY,
        stage_id="route",
        input_tokens=10,
        output_tokens=1,
        latency_ms=1,
        additional_peak_ram_bytes=100,
        swap_delta_bytes=0,
    )
    manager = RuntimeResourceManager(
        profile=low,
        budget=RuntimeResourceBudget(
            identity=identity,
            stages=(derive_stage_budget(identity, (observation,)),),
        ),
        environment=_environment(),
        probe=_Probe([(100, 100, 0), (110, 110, 0)]),
    )

    manager.execute_bundle(
        "bundle-low",
        (
            StageInvocation(
                stage_id="route",
                component_id="encoder",
                component_fingerprint="a" * 64,
                factory=_factory("encoder", events),
                inputs=(RuntimeInput("payload", 10),),
            ),
        ),
    )

    assert events[-1] == "close:encoder:metal"
    assert manager.cached_component_keys == ()


def test_component_load_failure_uses_explicit_cpu_fallback() -> None:
    events: list[str] = []

    def factory(device: RuntimeDevice) -> _Component:
        events.append(f"attempt:{device.value}")
        if device is RuntimeDevice.METAL:
            raise ComponentLoadError("simulated Metal OOM before execution")
        return _Component("candidate", device, events)

    manager = RuntimeResourceManager(
        profile=runtime_profile(RuntimeProfileName.BALANCED),
        budget=_budget("candidate"),
        environment=_environment(),
        probe=_Probe([(100, 100, 0), (110, 110, 0)]),
    )
    execution = manager.execute_bundle(
        "bundle-fallback",
        (
            StageInvocation(
                stage_id="candidate",
                component_id="candidate",
                component_fingerprint="c" * 64,
                factory=factory,
                inputs=(RuntimeInput("payload", 10),),
                keep_warm=False,
            ),
        ),
    )

    metric = execution.metrics.stages[0]
    assert events[:3] == ["attempt:metal", "attempt:cpu", "load:candidate:cpu"]
    assert metric.device is RuntimeDevice.CPU
    assert metric.cpu_fallback_used is True
    assert events[-1] == "close:candidate:cpu"


def test_context_limit_is_checked_before_loading_a_component() -> None:
    events: list[str] = []
    manager = RuntimeResourceManager(
        profile=runtime_profile(RuntimeProfileName.BALANCED),
        budget=_budget("extract", max_input_tokens=10),
        environment=_environment(),
        probe=_Probe([]),
    )

    with pytest.raises(ContextWindowExceeded, match="superano il limite"):
        manager.execute_bundle(
            "too-long",
            (
                StageInvocation(
                    stage_id="extract",
                    component_id="llm",
                    component_fingerprint="d" * 64,
                    factory=_factory("llm", events),
                    inputs=(RuntimeInput("payload", 11),),
                ),
            ),
        )
    assert events == []


def test_measured_ram_or_swap_overrun_fails_closed_and_unloads() -> None:
    events: list[str] = []
    manager = RuntimeResourceManager(
        profile=runtime_profile(RuntimeProfileName.BALANCED),
        budget=_budget("extract"),
        environment=_environment(),
        probe=_Probe([(100, 100, 0), (1_500, 1_500, 0)]),
    )

    with pytest.raises(ResourceBudgetExceeded, match="budget misurato superato"):
        manager.execute_bundle(
            "over-budget",
            (
                StageInvocation(
                    stage_id="extract",
                    component_id="llm",
                    component_fingerprint="d" * 64,
                    factory=_factory("llm", events),
                    inputs=(RuntimeInput("payload", 10),),
                ),
            ),
        )
    assert manager.cached_component_keys == ()
    assert events[-1] == "close:llm:metal"


def test_same_component_label_with_new_fingerprint_cannot_reuse_stale_cache() -> None:
    events: list[str] = []
    manager = RuntimeResourceManager(
        profile=runtime_profile(RuntimeProfileName.BALANCED),
        budget=_budget("first", "second"),
        environment=_environment(),
        probe=_Probe([(100, 100, 0), (110, 110, 0), (110, 110, 0), (120, 120, 0)]),
    )

    execution = manager.execute_bundle(
        "fingerprint-change",
        (
            StageInvocation(
                stage_id="first",
                component_id="parser",
                component_fingerprint="a" * 64,
                factory=_factory("parser-v1", events),
                inputs=(RuntimeInput("one", 1),),
            ),
            StageInvocation(
                stage_id="second",
                component_id="parser",
                component_fingerprint="b" * 64,
                factory=_factory("parser-v2", events),
                inputs=(RuntimeInput("two", 1),),
            ),
        ),
    )

    assert execution.outputs["second"] == ("parser-v2:two",)
    assert "close:parser-v1:metal" in events
    assert execution.metrics.stages[1].cache_hit is False


def test_stage_failure_closes_newly_cached_component_exactly_once() -> None:
    events: list[str] = []
    manager = RuntimeResourceManager(
        profile=runtime_profile(RuntimeProfileName.BALANCED),
        budget=_budget("extract"),
        environment=_environment(),
        probe=_Probe([(100, 100, 0)]),
    )

    with pytest.raises(RuntimeError, match="simulated component failure"):
        manager.execute_bundle(
            "failed-run",
            (
                StageInvocation(
                    stage_id="extract",
                    component_id="parser",
                    component_fingerprint="a" * 64,
                    factory=lambda device: _FailingComponent("parser", device, events),
                    inputs=(RuntimeInput("payload", 1),),
                ),
            ),
        )

    assert events.count("close:parser:metal") == 1
    assert manager.cached_component_keys == ()


def test_later_preflight_failure_unloads_components_from_earlier_stages() -> None:
    events: list[str] = []
    manager = RuntimeResourceManager(
        profile=runtime_profile(RuntimeProfileName.BALANCED),
        budget=_budget("route", "extract", max_input_tokens=10),
        environment=_environment(),
        probe=_Probe([(100, 100, 0), (110, 110, 0)]),
    )

    with pytest.raises(ContextWindowExceeded):
        manager.execute_bundle(
            "late-preflight-failure",
            (
                StageInvocation(
                    stage_id="route",
                    component_id="encoder",
                    component_fingerprint="a" * 64,
                    factory=_factory("encoder", events),
                    inputs=(RuntimeInput("short", 1),),
                ),
                StageInvocation(
                    stage_id="extract",
                    component_id="llm",
                    component_fingerprint="b" * 64,
                    factory=_factory("llm", events),
                    inputs=(RuntimeInput("too long", 11),),
                ),
            ),
        )

    assert "load:llm:metal" not in events
    assert events[-1] == "close:encoder:metal"
    assert manager.cached_component_keys == ()


def test_budget_from_a_different_runtime_is_rejected_before_execution() -> None:
    environment = _environment().model_copy(update={"runtime_version": "candidate-2"})

    with pytest.raises(BenchmarkEnvironmentMismatch, match="ripetere il benchmark"):
        RuntimeResourceManager(
            profile=runtime_profile(RuntimeProfileName.BALANCED),
            budget=_budget("route"),
            environment=environment,
            probe=_Probe([]),
        )
