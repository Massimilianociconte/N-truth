"""Contratti misurabili per il runtime sequenziale dei componenti Train A.

I profili descrivono una politica operativa, non una stima di memoria. I limiti
di RAM, swap e latenza possono nascere soltanto da osservazioni di benchmark
associate a macchina, runtime e profilo espliciti.
"""

from __future__ import annotations

import math
from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import Field, field_validator, model_validator

from ntruth.schemas.core import FrozenModel


class RuntimeProfileName(StrEnum):
    LOW_MEMORY = "LOW_MEMORY"
    BALANCED = "BALANCED"
    QUALITY = "QUALITY"


class RuntimeDevice(StrEnum):
    METAL = "metal"
    CPU = "cpu"


class RuntimeProfile(FrozenModel):
    """Politica configurabile, deliberatamente priva di stime RAM teoriche."""

    name: RuntimeProfileName
    context_window_tokens: int = Field(gt=0)
    reserved_output_tokens: int = Field(ge=0)
    chunk_tokens: int = Field(gt=0)
    chunk_overlap_tokens: int = Field(ge=0)
    max_cached_components: int = Field(ge=0)
    preferred_device: RuntimeDevice = RuntimeDevice.METAL
    allow_cpu_fallback: bool = True

    @model_validator(mode="after")
    def _coherent_window(self) -> Self:
        input_window = self.context_window_tokens - self.reserved_output_tokens
        if input_window < 1:
            raise ValueError("reserved_output_tokens esaurisce la context window")
        if self.chunk_tokens > input_window:
            raise ValueError("chunk_tokens supera la context window disponibile")
        if self.chunk_overlap_tokens >= self.chunk_tokens:
            raise ValueError("chunk_overlap_tokens deve essere minore di chunk_tokens")
        return self

    @property
    def max_input_tokens(self) -> int:
        return self.context_window_tokens - self.reserved_output_tokens


class RuntimeEnvironment(FrozenModel):
    """Fingerprint esatto del runtime corrente fornito dall'adapter backend."""

    machine_model: str = Field(min_length=1, max_length=300)
    unified_memory_bytes: int = Field(gt=0)
    operating_system: str = Field(min_length=1, max_length=300)
    runtime_name: str = Field(min_length=1, max_length=200)
    runtime_version: str = Field(min_length=1, max_length=200)


class BenchmarkIdentity(FrozenModel):
    """Identita dell'ambiente sul quale sono state raccolte le misure."""

    benchmark_id: str = Field(min_length=1, max_length=200)
    machine_model: str = Field(min_length=1, max_length=300)
    unified_memory_bytes: int = Field(gt=0)
    operating_system: str = Field(min_length=1, max_length=300)
    runtime_name: str = Field(min_length=1, max_length=200)
    runtime_version: str = Field(min_length=1, max_length=200)
    measured_at: datetime

    @field_validator("measured_at")
    @classmethod
    def _timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("measured_at deve includere il fuso orario")
        return value

    def matches(self, environment: RuntimeEnvironment) -> bool:
        return all(
            (
                self.machine_model == environment.machine_model,
                self.unified_memory_bytes == environment.unified_memory_bytes,
                self.operating_system == environment.operating_system,
                self.runtime_name == environment.runtime_name,
                self.runtime_version == environment.runtime_version,
            )
        )


class StageBenchmarkObservation(FrozenModel):
    """Una misura reale; nessun campo e derivato dal numero di parametri."""

    observation_id: str = Field(min_length=1, max_length=200)
    benchmark_id: str = Field(min_length=1, max_length=200)
    profile: RuntimeProfileName
    stage_id: str = Field(min_length=1, max_length=200)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    latency_ms: float = Field(ge=0, allow_inf_nan=False)
    additional_peak_ram_bytes: int = Field(ge=0)
    swap_delta_bytes: int = Field(ge=0)


class MeasuredStageBudget(FrozenModel):
    """Envelope operativo derivato da osservazioni dello stesso benchmark."""

    benchmark_id: str
    profile: RuntimeProfileName
    stage_id: str
    observation_ids: tuple[str, ...] = Field(min_length=1)
    sample_count: int = Field(gt=0)
    max_input_tokens: int = Field(ge=0)
    max_additional_peak_ram_bytes: int = Field(ge=0)
    max_swap_delta_bytes: int = Field(ge=0)
    max_latency_ms: float = Field(ge=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def _observation_count_matches(self) -> Self:
        if len(self.observation_ids) != len(set(self.observation_ids)):
            raise ValueError("observation_ids contiene duplicati")
        if self.sample_count != len(self.observation_ids):
            raise ValueError("sample_count non coincide con observation_ids")
        return self


class RuntimeResourceBudget(FrozenModel):
    """Budget benchmark-bound per un solo ambiente e insieme di profili."""

    identity: BenchmarkIdentity
    stages: tuple[MeasuredStageBudget, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _same_benchmark_and_unique_keys(self) -> Self:
        keys: list[tuple[RuntimeProfileName, str]] = []
        for stage in self.stages:
            if stage.benchmark_id != self.identity.benchmark_id:
                raise ValueError("stage budget riferito a un benchmark differente")
            keys.append((stage.profile, stage.stage_id))
        if len(keys) != len(set(keys)):
            raise ValueError("stage budget duplicato per profilo e stage")
        return self

    def for_stage(self, profile: RuntimeProfileName, stage_id: str) -> MeasuredStageBudget:
        for stage in self.stages:
            if stage.profile is profile and stage.stage_id == stage_id:
                return stage
        raise KeyError(f"budget misurato assente per {profile.value}/{stage_id}")


class ResourceSnapshot(FrozenModel):
    captured_at: datetime
    resident_ram_bytes: int | None = Field(default=None, ge=0)
    peak_resident_ram_bytes: int | None = Field(default=None, ge=0)
    system_swap_used_bytes: int | None = Field(default=None, ge=0)

    @field_validator("captured_at")
    @classmethod
    def _captured_at_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("captured_at deve includere il fuso orario")
        return value


class StageRuntimeMetrics(FrozenModel):
    stage_id: str
    component_id: str
    component_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    device: RuntimeDevice
    chunk_count: int = Field(gt=0)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    latency_ms: float = Field(ge=0, allow_inf_nan=False)
    baseline_resident_ram_bytes: int | None = Field(default=None, ge=0)
    observed_peak_resident_ram_bytes: int | None = Field(default=None, ge=0)
    additional_peak_ram_bytes: int | None = Field(default=None, ge=0)
    swap_delta_bytes: int | None = Field(default=None, ge=0)
    cache_hit: bool
    cache_evictions: int = Field(ge=0)
    cpu_fallback_used: bool
    budget_compliant: bool | None


class BundleRuntimeMetrics(FrozenModel):
    bundle_id: str
    profile: RuntimeProfileName
    benchmark_id: str
    started_at: datetime
    completed_at: datetime
    stages: tuple[StageRuntimeMetrics, ...] = Field(min_length=1)
    total_input_tokens: int = Field(ge=0)
    total_output_tokens: int = Field(ge=0)
    total_latency_ms: float = Field(ge=0, allow_inf_nan=False)
    peak_resident_ram_bytes: int | None = Field(default=None, ge=0)
    peak_swap_delta_bytes: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _aggregates_match_stages(self) -> Self:
        if self.completed_at < self.started_at:
            raise ValueError("completed_at precede started_at")
        if self.total_input_tokens != sum(item.input_tokens for item in self.stages):
            raise ValueError("total_input_tokens non coincide con le metriche di stage")
        if self.total_output_tokens != sum(item.output_tokens for item in self.stages):
            raise ValueError("total_output_tokens non coincide con le metriche di stage")
        expected_latency = sum(item.latency_ms for item in self.stages)
        if not math.isclose(self.total_latency_ms, expected_latency, rel_tol=1e-9, abs_tol=1e-6):
            raise ValueError("total_latency_ms non coincide con le metriche di stage")
        return self


def derive_stage_budget(
    identity: BenchmarkIdentity,
    observations: tuple[StageBenchmarkObservation, ...],
) -> MeasuredStageBudget:
    """Deriva l'envelope osservato, senza applicare margini teorici universali.

    Carico concorrente, warmup e condizioni di sicurezza devono quindi essere
    inclusi nel protocollo di misura e nelle osservazioni, non aggiunti qui come
    percentuale presunta.
    """

    if not observations:
        raise ValueError("servono osservazioni reali per derivare un budget")
    benchmark_ids = {item.benchmark_id for item in observations}
    profiles = {item.profile for item in observations}
    stage_ids = {item.stage_id for item in observations}
    observation_ids = tuple(item.observation_id for item in observations)
    if benchmark_ids != {identity.benchmark_id}:
        raise ValueError("le osservazioni non appartengono al benchmark dichiarato")
    if len(profiles) != 1 or len(stage_ids) != 1:
        raise ValueError("le osservazioni devono descrivere un solo profilo e stage")
    if len(observation_ids) != len(set(observation_ids)):
        raise ValueError("observation_id duplicati")

    return MeasuredStageBudget(
        benchmark_id=identity.benchmark_id,
        profile=next(iter(profiles)),
        stage_id=next(iter(stage_ids)),
        observation_ids=observation_ids,
        sample_count=len(observations),
        max_input_tokens=max(item.input_tokens for item in observations),
        max_additional_peak_ram_bytes=max(item.additional_peak_ram_bytes for item in observations),
        max_swap_delta_bytes=max(item.swap_delta_bytes for item in observations),
        max_latency_ms=max(item.latency_ms for item in observations),
    )
