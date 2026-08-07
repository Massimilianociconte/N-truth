"""Resource manager sequenziale, cache-bounded e backend-agnostic."""

from __future__ import annotations

import os
import platform
import re
import resource
import subprocess
import time
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock
from typing import Protocol

from ntruth.runtime_resources.schema import (
    BundleRuntimeMetrics,
    ResourceSnapshot,
    RuntimeDevice,
    RuntimeEnvironment,
    RuntimeProfile,
    RuntimeResourceBudget,
    StageRuntimeMetrics,
)


class RuntimeResourceError(RuntimeError):
    """Base degli errori operativi fail-closed del resource manager."""


class ContextWindowExceeded(RuntimeResourceError):
    pass


class ResourceBudgetExceeded(RuntimeResourceError):
    pass


class ResourceMeasurementUnavailable(RuntimeResourceError):
    pass


class ComponentLoadError(RuntimeResourceError):
    pass


class BenchmarkEnvironmentMismatch(RuntimeResourceError):
    pass


class RuntimeComponent(Protocol):
    """Adapter minimo implementabile da encoder, LLM o verifier."""

    def run(self, payload: object, *, context_window_tokens: int) -> ComponentResult: ...

    def close(self) -> None: ...


class ResourceProbe(Protocol):
    def snapshot(self) -> ResourceSnapshot: ...


@dataclass(frozen=True, slots=True)
class ComponentResult:
    value: object
    output_tokens: int = 0

    def __post_init__(self) -> None:
        if self.output_tokens < 0:
            raise ValueError("output_tokens non puo essere negativo")


@dataclass(frozen=True, slots=True)
class RuntimeInput:
    payload: object
    input_tokens: int

    def __post_init__(self) -> None:
        if self.input_tokens < 0:
            raise ValueError("input_tokens non puo essere negativo")


ComponentFactory = Callable[[RuntimeDevice], RuntimeComponent]


@dataclass(frozen=True, slots=True)
class StageInvocation:
    stage_id: str
    component_id: str
    component_fingerprint: str
    factory: ComponentFactory
    inputs: tuple[RuntimeInput, ...]
    keep_warm: bool = True

    def __post_init__(self) -> None:
        if not self.stage_id.strip() or not self.component_id.strip():
            raise ValueError("stage_id e component_id sono obbligatori")
        if len(self.component_fingerprint) != 64 or any(
            character not in "0123456789abcdef" for character in self.component_fingerprint
        ):
            raise ValueError("component_fingerprint deve essere uno SHA-256 lowercase")
        if not self.inputs:
            raise ValueError("uno stage richiede almeno un input")


@dataclass(frozen=True, slots=True)
class BundleExecution:
    outputs: dict[str, tuple[object, ...]]
    metrics: BundleRuntimeMetrics


@dataclass(slots=True)
class _CachedComponent:
    component_id: str
    component: RuntimeComponent
    device: RuntimeDevice


class HostResourceProbe:
    """Probe locale senza dipendenze; swap e sistema-wide e quindi dichiarato tale."""

    # macOS con locale IT usa virgola decimale (es. used = 413,69M).
    _SWAP_USED_RE = re.compile(
        r"used\s*=\s*([0-9]+(?:[.,][0-9]+)?)([KMGTP])",
        re.IGNORECASE,
    )

    def snapshot(self) -> ResourceSnapshot:
        return ResourceSnapshot(
            captured_at=datetime.now(UTC),
            resident_ram_bytes=self._resident_ram_bytes(),
            peak_resident_ram_bytes=self._peak_resident_ram_bytes(),
            system_swap_used_bytes=self._system_swap_used_bytes(),
        )

    @staticmethod
    def _resident_ram_bytes() -> int | None:
        try:
            completed = subprocess.run(
                ["ps", "-o", "rss=", "-p", str(os.getpid())],
                check=True,
                capture_output=True,
                text=True,
                timeout=2,
            )
            return int(completed.stdout.strip()) * 1024
        except (OSError, ValueError, subprocess.SubprocessError):
            return None

    @staticmethod
    def _peak_resident_ram_bytes() -> int | None:
        try:
            value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        except (OSError, ValueError):
            return None
        # macOS riporta byte; Linux e gli altri Unix comunemente KiB.
        return value if platform.system() == "Darwin" else value * 1024

    @classmethod
    def _system_swap_used_bytes(cls) -> int | None:
        if platform.system() == "Darwin":
            try:
                completed = subprocess.run(
                    ["sysctl", "-n", "vm.swapusage"],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
            except (OSError, subprocess.SubprocessError):
                return None
            match = cls._SWAP_USED_RE.search(completed.stdout)
            if match is None:
                return None
            units = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4, "P": 1024**5}
            amount = match.group(1).replace(",", ".")
            return int(float(amount) * units[match.group(2).upper()])
        try:
            values: dict[str, int] = {}
            with open("/proc/meminfo", encoding="utf-8") as handle:
                for line in handle:
                    key, _, raw = line.partition(":")
                    if key in {"SwapTotal", "SwapFree"}:
                        values[key] = int(raw.strip().split()[0]) * 1024
            if {"SwapTotal", "SwapFree"} <= values.keys():
                return max(0, values["SwapTotal"] - values["SwapFree"])
        except (OSError, ValueError, IndexError):
            return None
        return None


class RuntimeResourceManager:
    """Esegue stage in serie, misura risorse e gestisce una cache LRU esplicita."""

    def __init__(
        self,
        *,
        profile: RuntimeProfile,
        budget: RuntimeResourceBudget,
        environment: RuntimeEnvironment,
        probe: ResourceProbe | None = None,
        metrics_sink: Callable[[BundleRuntimeMetrics], None] | None = None,
        require_complete_measurements: bool = True,
    ) -> None:
        self.profile = profile
        self.budget = budget
        self.environment = environment
        self.probe = probe or HostResourceProbe()
        self.metrics_sink = metrics_sink
        self.require_complete_measurements = require_complete_measurements
        self._cache: OrderedDict[tuple[str, str, RuntimeDevice], _CachedComponent] = OrderedDict()
        self._lock = RLock()
        if not budget.identity.matches(environment):
            raise BenchmarkEnvironmentMismatch(
                "il budget non appartiene alla macchina/runtime correnti; ripetere il benchmark"
            )

    @property
    def cached_component_keys(self) -> tuple[tuple[str, str, RuntimeDevice], ...]:
        with self._lock:
            return tuple(self._cache)

    def execute_bundle(self, bundle_id: str, stages: Sequence[StageInvocation]) -> BundleExecution:
        if not bundle_id.strip():
            raise ValueError("bundle_id e obbligatorio")
        if not stages:
            raise ValueError("il bundle richiede almeno uno stage")
        stage_ids = [item.stage_id for item in stages]
        if len(stage_ids) != len(set(stage_ids)):
            raise ValueError("stage_id duplicati nel bundle")

        with self._lock:
            started_at = datetime.now(UTC)
            outputs: dict[str, tuple[object, ...]] = {}
            stage_metrics: list[StageRuntimeMetrics] = []
            try:
                for stage in stages:
                    stage_outputs, stage_metric = self._execute_stage(stage)
                    outputs[stage.stage_id] = stage_outputs
                    stage_metrics.append(stage_metric)
            except Exception:
                self.clear_cache()
                raise
            completed_at = datetime.now(UTC)
            peak_ram_values = [
                item.observed_peak_resident_ram_bytes
                for item in stage_metrics
                if item.observed_peak_resident_ram_bytes is not None
            ]
            swap_values = [
                item.swap_delta_bytes for item in stage_metrics if item.swap_delta_bytes is not None
            ]
            bundle_metrics = BundleRuntimeMetrics(
                bundle_id=bundle_id,
                profile=self.profile.name,
                benchmark_id=self.budget.identity.benchmark_id,
                started_at=started_at,
                completed_at=completed_at,
                stages=tuple(stage_metrics),
                total_input_tokens=sum(item.input_tokens for item in stage_metrics),
                total_output_tokens=sum(item.output_tokens for item in stage_metrics),
                total_latency_ms=sum(item.latency_ms for item in stage_metrics),
                peak_resident_ram_bytes=max(peak_ram_values) if peak_ram_values else None,
                peak_swap_delta_bytes=max(swap_values) if swap_values else None,
            )
            if self.metrics_sink is not None:
                try:
                    self.metrics_sink(bundle_metrics)
                except Exception:
                    self.clear_cache()
                    raise
            return BundleExecution(outputs=outputs, metrics=bundle_metrics)

    def unload_component(self, component_id: str, *, device: RuntimeDevice | None = None) -> int:
        """Scarica esplicitamente tutte le istanze corrispondenti e ritorna il numero."""

        with self._lock:
            keys = [
                key
                for key in self._cache
                if key[0] == component_id and (device is None or key[2] is device)
            ]
            for key in keys:
                cached = self._cache.pop(key)
                cached.component.close()
            return len(keys)

    def clear_cache(self) -> int:
        with self._lock:
            count = len(self._cache)
            while self._cache:
                _, cached = self._cache.popitem(last=False)
                cached.component.close()
            return count

    def close(self) -> None:
        self.clear_cache()

    def __enter__(self) -> RuntimeResourceManager:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _execute_stage(
        self, stage: StageInvocation
    ) -> tuple[tuple[object, ...], StageRuntimeMetrics]:
        measured_budget = self.budget.for_stage(self.profile.name, stage.stage_id)
        effective_context = min(self.profile.max_input_tokens, measured_budget.max_input_tokens)
        for item in stage.inputs:
            if item.input_tokens > effective_context:
                raise ContextWindowExceeded(
                    f"{stage.stage_id}: {item.input_tokens} token superano il limite "
                    f"misurato/configurato di {effective_context}"
                )

        before = self.probe.snapshot()
        started = time.perf_counter()
        component: RuntimeComponent | None = None
        cached = False
        cache_evictions = 0
        fallback = False
        device = self.profile.preferred_device
        samples = [before]
        try:
            try:
                component, cached, cache_evictions = self._acquire(
                    stage.component_id,
                    stage.component_fingerprint,
                    stage.factory,
                    device,
                )
            except (ComponentLoadError, MemoryError):
                if not self.profile.allow_cpu_fallback or device is RuntimeDevice.CPU:
                    raise
                self.unload_component(stage.component_id, device=device)
                device = RuntimeDevice.CPU
                component, cached, cache_evictions = self._acquire(
                    stage.component_id,
                    stage.component_fingerprint,
                    stage.factory,
                    device,
                )
                fallback = True

            results: list[object] = []
            output_tokens = 0
            for item in stage.inputs:
                result = component.run(item.payload, context_window_tokens=effective_context)
                results.append(result.value)
                output_tokens += result.output_tokens
                samples.append(self.probe.snapshot())
        except Exception:
            unloaded = self._unload_cached_instance(
                stage.component_id,
                stage.component_fingerprint,
                device,
            )
            if component is not None and not cached and not unloaded:
                component.close()
            raise
        finally:
            latency_ms = (time.perf_counter() - started) * 1000.0

        assert component is not None
        if not stage.keep_warm or self.profile.max_cached_components == 0:
            key = (stage.component_id, stage.component_fingerprint, device)
            resident = self._cache.pop(key, None)
            if resident is not None:
                resident.component.close()
            elif not cached:
                component.close()

        additional_peak, observed_peak, swap_delta = self._resource_deltas(samples)
        measurements_complete = additional_peak is not None and swap_delta is not None
        if self.require_complete_measurements and not measurements_complete:
            self.unload_component(stage.component_id, device=device)
            raise ResourceMeasurementUnavailable(
                f"{stage.stage_id}: RAM picco o swap non misurabili su questo host"
            )
        budget_compliant: bool | None = None
        if measurements_complete:
            assert additional_peak is not None and swap_delta is not None
            budget_compliant = (
                additional_peak <= measured_budget.max_additional_peak_ram_bytes
                and swap_delta <= measured_budget.max_swap_delta_bytes
                and latency_ms <= measured_budget.max_latency_ms
            )
            if not budget_compliant:
                self.unload_component(stage.component_id, device=device)
                raise ResourceBudgetExceeded(
                    f"{stage.stage_id}: budget misurato superato "
                    f"(RAM +{additional_peak} byte, swap +{swap_delta} byte, "
                    f"latenza {latency_ms:.3f} ms)"
                )

        metrics = StageRuntimeMetrics(
            stage_id=stage.stage_id,
            component_id=stage.component_id,
            component_fingerprint=stage.component_fingerprint,
            device=device,
            chunk_count=len(stage.inputs),
            input_tokens=sum(item.input_tokens for item in stage.inputs),
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            baseline_resident_ram_bytes=before.resident_ram_bytes,
            observed_peak_resident_ram_bytes=observed_peak,
            additional_peak_ram_bytes=additional_peak,
            swap_delta_bytes=swap_delta,
            cache_hit=cached,
            cache_evictions=cache_evictions,
            cpu_fallback_used=fallback,
            budget_compliant=budget_compliant,
        )
        return tuple(results), metrics

    def _acquire(
        self,
        component_id: str,
        component_fingerprint: str,
        factory: ComponentFactory,
        device: RuntimeDevice,
    ) -> tuple[RuntimeComponent, bool, int]:
        key = (component_id, component_fingerprint, device)
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached.component, True, 0

        component = factory(device)
        evictions = 0
        if self.profile.max_cached_components > 0:
            self._cache[key] = _CachedComponent(
                component_id=component_id,
                component=component,
                device=device,
            )
            while len(self._cache) > self.profile.max_cached_components:
                _, evicted = self._cache.popitem(last=False)
                evicted.component.close()
                evictions += 1
        return component, False, evictions

    def _unload_cached_instance(
        self,
        component_id: str,
        component_fingerprint: str,
        device: RuntimeDevice,
    ) -> bool:
        cached = self._cache.pop((component_id, component_fingerprint, device), None)
        if cached is None:
            return False
        cached.component.close()
        return True

    @staticmethod
    def _resource_deltas(
        snapshots: Sequence[ResourceSnapshot],
    ) -> tuple[int | None, int | None, int | None]:
        first = snapshots[0]
        residents = [
            item.resident_ram_bytes for item in snapshots if item.resident_ram_bytes is not None
        ]
        peaks = [
            item.peak_resident_ram_bytes
            for item in snapshots
            if item.peak_resident_ram_bytes is not None
        ]
        observed_peak = max((*residents, *peaks)) if residents or peaks else None
        incremental_candidates: list[int] = []
        if residents and first.resident_ram_bytes is not None:
            incremental_candidates.append(max(0, max(residents) - first.resident_ram_bytes))
        if peaks and first.peak_resident_ram_bytes is not None:
            incremental_candidates.append(max(0, max(peaks) - first.peak_resident_ram_bytes))
        additional_peak = max(incremental_candidates) if incremental_candidates else None

        swap_values = [
            item.system_swap_used_bytes
            for item in snapshots
            if item.system_swap_used_bytes is not None
        ]
        swap_delta = None
        if swap_values and first.system_swap_used_bytes is not None:
            swap_delta = max(0, max(swap_values) - first.system_swap_used_bytes)
        return additional_peak, observed_peak, swap_delta
