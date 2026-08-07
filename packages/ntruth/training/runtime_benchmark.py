"""Benchmark runtime misurato su hardware reale (ADR-0003, PRD Appendice T).

Protocollo di alta qualita:
1. fingerprint ambiente (machine_model, unified memory, OS, runtime);
2. stabilizzazione baseline e campionamento multiplo;
3. cold load / warmup / generate per profilo e dimensione context;
4. stage leggeri rules/hard_verifier per envelope non-ML;
5. replicate indipendenti; envelope = max osservato (derive_stage_budget);
6. artifact JSON budget + protocol report con metadata e raw observations.

Nessun peak teorico e inventato. I valori esistono solo se misurati.
"""

from __future__ import annotations

import gc
import hashlib
import json
import platform
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ntruth.runtime_resources.budget_io import save_runtime_resource_budget
from ntruth.runtime_resources.manager import HostResourceProbe
from ntruth.runtime_resources.profiles import runtime_profile
from ntruth.runtime_resources.schema import (
    BenchmarkIdentity,
    RuntimeProfileName,
    RuntimeResourceBudget,
    StageBenchmarkObservation,
    derive_stage_budget,
)
from ntruth.training.mlx_resource_bridge import (
    DEFAULT_STAGE_ID,
    installed_mlx_lm_version,
)
from ntruth.training.mlx_runtime import MLXPipelineError
from ntruth.training.runtime_env import (
    RuntimeEnvironmentProbeError,
    probe_runtime_environment,
)

PROTOCOL_VERSION = "1.0.0"
DEFAULT_BENCHMARK_PREFIX = "m5-pro-24g"
STAGE_MLX_GENERATE = DEFAULT_STAGE_ID
STAGE_RULES = "rules_engine"
STAGE_HARD = "hard_verifier"
STAGE_SEMANTIC = "semantic_verifier"


@dataclass(frozen=True, slots=True)
class ProfileWorkload:
    """Carico sintetico per un profilo: token target e lunghezze prompt."""

    profile: RuntimeProfileName
    prompt_chars: int
    max_new_tokens: int
    replicates: int = 3


# Workload conservativi ma distinti per profilo. Non sono claim di qualita:
# servono a stressare context/generate entro i limiti del profilo.
DEFAULT_WORKLOADS: tuple[ProfileWorkload, ...] = (
    ProfileWorkload(RuntimeProfileName.LOW_MEMORY, prompt_chars=2_500, max_new_tokens=64, replicates=3),
    ProfileWorkload(RuntimeProfileName.BALANCED, prompt_chars=6_000, max_new_tokens=128, replicates=3),
    ProfileWorkload(RuntimeProfileName.QUALITY, prompt_chars=12_000, max_new_tokens=192, replicates=3),
)


def _stable_benchmark_id(*, machine_model: str, memory_bytes: int, measured_at: datetime) -> str:
    stamp = measured_at.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    digest = hashlib.sha256(
        f"{machine_model}\0{memory_bytes}\0{stamp}".encode()
    ).hexdigest()[:10]
    return f"{DEFAULT_BENCHMARK_PREFIX}-{stamp}-{digest}"


def _stabilize(seconds: float = 1.0) -> None:
    gc.collect()
    time.sleep(max(0.0, seconds))


def _resource_deltas(
    probe: HostResourceProbe,
    *,
    samples: int = 5,
    interval_s: float = 0.05,
) -> tuple[int, int, int, int]:
    """Ritorna (baseline_rss, peak_rss, peak_ru, swap_after) su una finestra breve."""

    snaps = []
    for index in range(max(1, samples)):
        snaps.append(probe.snapshot())
        if index + 1 < samples:
            time.sleep(interval_s)
    rss_values = [s.resident_ram_bytes for s in snaps if s.resident_ram_bytes is not None]
    peak_values = [
        s.peak_resident_ram_bytes for s in snaps if s.peak_resident_ram_bytes is not None
    ]
    swap_values = [
        s.system_swap_used_bytes for s in snaps if s.system_swap_used_bytes is not None
    ]
    if not rss_values or not peak_values or not swap_values:
        raise MLXPipelineError(
            "misure RAM/swap incomplete: impossibile produrre un budget reale fail-closed"
        )
    return min(rss_values), max(rss_values), max(peak_values), max(swap_values)


def _synthetic_prompt(chars: int, *, label: str) -> str:
    """Prompt scientificamente neutro, ripetibile, senza dati personali."""

    seed = (
        "N-Truth runtime resource benchmark. "
        "Methods-like prose for token/context stress only. "
        "Wells received vehicle or compound after independent assignment. "
        "Do not invent experimental facts; reply with a short JSON object "
        '{"status":"ok","note":"benchmark"}. '
    )
    body = (seed * ((chars // len(seed)) + 2))[: max(64, chars)]
    return f"[benchmark:{label}]\n{body}"


def _estimate_tokens(text: str, tokenizer: Any | None) -> int:
    if tokenizer is not None:
        encode = getattr(tokenizer, "encode", None)
        if callable(encode):
            try:
                return max(1, len(encode(text, add_special_tokens=False)))
            except Exception:
                pass
    return max(1, len(text) // 4)


def measure_mlx_stage_observations(
    *,
    model_path: Path,
    workloads: Sequence[ProfileWorkload],
    benchmark_id: str,
    probe: HostResourceProbe | None = None,
    adapter_path: Path | None = None,
) -> tuple[list[StageBenchmarkObservation], dict[str, Any]]:
    """Carica il modello una volta e misura generate per profilo/replica."""

    probe = probe or HostResourceProbe()
    model_path = Path(model_path).resolve()
    if not model_path.exists():
        raise MLXPipelineError(f"modello assente: {model_path}")

    try:
        from mlx_lm import generate, load
        from mlx_lm.sample_utils import make_sampler
    except ImportError as exc:
        raise MLXPipelineError("mlx-lm non installato; usare uv sync --extra ml") from exc

    _stabilize(1.5)
    before_load_rss, _, before_load_peak, before_load_swap = _resource_deltas(probe, samples=3)
    load_started = time.perf_counter()
    loaded = load(
        str(model_path),
        adapter_path=str(adapter_path) if adapter_path is not None else None,
    )
    model, tokenizer = loaded[0], loaded[1]
    sampler = make_sampler(temp=0.0)
    # Warm Metal kernels without counting as profile generate.
    warm_prompt = _synthetic_prompt(512, label="warmup")
    _ = generate(model, tokenizer, prompt=warm_prompt, max_tokens=16, sampler=sampler, verbose=False)
    load_latency_ms = (time.perf_counter() - load_started) * 1000.0
    after_load_rss, after_load_peak_rss, after_load_ru, after_load_swap = _resource_deltas(
        probe, samples=5
    )
    load_meta = {
        "before_rss_bytes": before_load_rss,
        "after_rss_bytes": after_load_rss,
        "peak_rss_window_bytes": after_load_peak_rss,
        "peak_ru_maxrss_bytes": after_load_ru,
        "swap_before_bytes": before_load_swap,
        "swap_after_bytes": after_load_swap,
        "additional_peak_rss_bytes": max(0, after_load_peak_rss - before_load_rss),
        "swap_delta_bytes": max(0, after_load_swap - before_load_swap),
        "load_and_warmup_latency_ms": load_latency_ms,
        "model_path": str(model_path),
    }

    observations: list[StageBenchmarkObservation] = []
    raw_runs: list[dict[str, Any]] = []
    try:
        for workload in workloads:
            profile = runtime_profile(workload.profile)
            for replica in range(1, workload.replicates + 1):
                prompt = _synthetic_prompt(
                    workload.prompt_chars,
                    label=f"{workload.profile.value}-r{replica}",
                )
                input_tokens = _estimate_tokens(prompt, tokenizer)
                # Rispetta la context window del profilo (input + reserved output).
                if input_tokens > profile.max_input_tokens:
                    # Tronca il prompt in modo deterministico fino a rientrare.
                    ratio = profile.max_input_tokens / max(1, input_tokens)
                    keep = max(64, int(len(prompt) * ratio * 0.95))
                    prompt = prompt[:keep]
                    input_tokens = _estimate_tokens(prompt, tokenizer)
                max_tokens = min(workload.max_new_tokens, profile.reserved_output_tokens)

                _stabilize(0.4)
                base_rss, _, base_peak, base_swap = _resource_deltas(probe, samples=3)
                started = time.perf_counter()
                # Campiona RSS durante la generazione con un thread-free loop:
                # generate e sincrono; misuriamo prima/dopo e ru_maxrss.
                output = generate(
                    model,
                    tokenizer,
                    prompt=prompt,
                    max_tokens=max_tokens,
                    sampler=sampler,
                    verbose=False,
                )
                latency_ms = (time.perf_counter() - started) * 1000.0
                end_rss, end_peak_rss, end_ru, end_swap = _resource_deltas(probe, samples=4)
                output_tokens = _estimate_tokens(str(output), tokenizer)
                additional_peak = max(
                    0,
                    max(end_peak_rss, end_ru, end_rss) - base_rss,
                )
                # Include the model-resident footprint in the stage envelope so
                # sequential single-component runs remain fail-closed under budget.
                additional_with_model = max(
                    additional_peak,
                    max(0, end_rss - before_load_rss),
                    max(0, end_ru - before_load_peak),
                )
                swap_delta = max(0, end_swap - base_swap)
                observation_id = (
                    f"obs-{workload.profile.value.lower()}-{STAGE_MLX_GENERATE}-r{replica}"
                )
                observations.append(
                    StageBenchmarkObservation(
                        observation_id=observation_id,
                        benchmark_id=benchmark_id,
                        profile=workload.profile,
                        stage_id=STAGE_MLX_GENERATE,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        latency_ms=latency_ms,
                        additional_peak_ram_bytes=additional_with_model,
                        swap_delta_bytes=swap_delta,
                    )
                )
                raw_runs.append(
                    {
                        "observation_id": observation_id,
                        "profile": workload.profile.value,
                        "replica": replica,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "latency_ms": latency_ms,
                        "baseline_rss_bytes": base_rss,
                        "end_rss_bytes": end_rss,
                        "end_peak_rss_window_bytes": end_peak_rss,
                        "end_ru_maxrss_bytes": end_ru,
                        "additional_peak_ram_bytes": additional_with_model,
                        "swap_delta_bytes": swap_delta,
                        "prompt_chars": len(prompt),
                        "max_new_tokens": max_tokens,
                        "output_chars": len(str(output)),
                    }
                )
    finally:
        del model
        del tokenizer
        gc.collect()
        _stabilize(0.5)

    return observations, {"load": load_meta, "generate_runs": raw_runs}


def measure_cpu_stage_observations(
    *,
    benchmark_id: str,
    profiles: Sequence[RuntimeProfileName],
    replicates: int = 3,
    probe: HostResourceProbe | None = None,
    work_root: Path | None = None,
) -> tuple[list[StageBenchmarkObservation], dict[str, Any]]:
    """Misura stage deterministici rules + hard + semantic (senza ML)."""

    import tempfile

    from ntruth.application import execute_analysis
    from ntruth.schemas.manifest import ReleaseProfile
    from ntruth.verifier import verify_block
    from ntruth.verifier.semantic import verify_semantic

    probe = probe or HostResourceProbe()
    fixture_methods = (
        Path(__file__).resolve().parents[3]
        / "tests"
        / "scientific_fixtures"
        / "uc01_donor_cells"
        / "methods.md"
    )
    if not fixture_methods.is_file():
        raise MLXPipelineError(f"fixture assente per benchmark CPU: {fixture_methods}")

    observations: list[StageBenchmarkObservation] = []
    raw: list[dict[str, Any]] = []
    root = Path(work_root) if work_root is not None else Path(tempfile.mkdtemp(prefix="ntruth-bench-"))
    root.mkdir(parents=True, exist_ok=True)

    def _run_analysis() -> Any:
        return execute_analysis(
            fixture_methods,
            out=root / "out",
            project_dir=None,
            language="en",
            domain="quantitative_microscopy",
            release_profile=ReleaseProfile.D0_CORE,
            require_domain_acknowledgement=False,
            acknowledged_unvalidated_domain=True,
        )

    first = _run_analysis()
    blocks = first.result.report.blocks if first.result.report.blocks else ()
    if not blocks:
        # Report blocks can be empty on some paths; use block_analyses.
        analyses = first.result.block_analyses
        if not analyses:
            raise MLXPipelineError("benchmark CPU: nessun ExperimentBlock dalla fixture")
        block = analyses[0].block
    else:
        block = blocks[0]

    for profile in profiles:
        for stage_id, runner in (
            (STAGE_RULES, _run_analysis),
            (STAGE_HARD, lambda: verify_block(block)),
            (STAGE_SEMANTIC, lambda: verify_semantic(block)),
        ):
            for replica in range(1, replicates + 1):
                _stabilize(0.2)
                base_rss, _, _, base_swap = _resource_deltas(probe, samples=2)
                started = time.perf_counter()
                runner()
                latency_ms = (time.perf_counter() - started) * 1000.0
                end_rss, end_peak, end_ru, end_swap = _resource_deltas(probe, samples=3)
                additional = max(0, max(end_rss, end_peak, end_ru) - base_rss)
                swap_delta = max(0, end_swap - base_swap)
                observation_id = f"obs-{profile.value.lower()}-{stage_id}-r{replica}"
                observations.append(
                    StageBenchmarkObservation(
                        observation_id=observation_id,
                        benchmark_id=benchmark_id,
                        profile=profile,
                        stage_id=stage_id,
                        input_tokens=0,
                        output_tokens=0,
                        latency_ms=latency_ms,
                        additional_peak_ram_bytes=additional,
                        swap_delta_bytes=swap_delta,
                    )
                )
                raw.append(
                    {
                        "observation_id": observation_id,
                        "profile": profile.value,
                        "stage_id": stage_id,
                        "replica": replica,
                        "latency_ms": latency_ms,
                        "additional_peak_ram_bytes": additional,
                        "swap_delta_bytes": swap_delta,
                    }
                )
    return observations, {"cpu_runs": raw, "work_root": str(root)}


def build_budget_from_observations(
    *,
    identity: BenchmarkIdentity,
    observations: Sequence[StageBenchmarkObservation],
) -> RuntimeResourceBudget:
    if not observations:
        raise MLXPipelineError("nessuna osservazione: budget non costruibile")
    # Group by (profile, stage_id)
    groups: dict[tuple[RuntimeProfileName, str], list[StageBenchmarkObservation]] = {}
    for item in observations:
        if item.benchmark_id != identity.benchmark_id:
            raise MLXPipelineError("observation con benchmark_id diverso dall'identity")
        groups.setdefault((item.profile, item.stage_id), []).append(item)
    stages = tuple(
        derive_stage_budget(identity, tuple(items)) for items in groups.values()
    )
    return RuntimeResourceBudget(identity=identity, stages=stages)


def run_full_runtime_benchmark(
    *,
    model_path: Path,
    output_dir: Path,
    workloads: Sequence[ProfileWorkload] = DEFAULT_WORKLOADS,
    include_cpu_stages: bool = True,
    adapter_path: Path | None = None,
    runtime_name: str = "mlx-lm",
    runtime_version: str | None = None,
) -> dict[str, Any]:
    """Esegue il protocollo completo e scrive budget + report."""

    version = runtime_version or installed_mlx_lm_version()
    try:
        environment = probe_runtime_environment(runtime_name, version)
    except RuntimeEnvironmentProbeError as exc:
        raise MLXPipelineError(str(exc)) from exc

    measured_at = datetime.now(UTC)
    benchmark_id = _stable_benchmark_id(
        machine_model=environment.machine_model,
        memory_bytes=environment.unified_memory_bytes,
        measured_at=measured_at,
    )
    identity = BenchmarkIdentity(
        benchmark_id=benchmark_id,
        machine_model=environment.machine_model,
        unified_memory_bytes=environment.unified_memory_bytes,
        operating_system=environment.operating_system,
        runtime_name=environment.runtime_name,
        runtime_version=environment.runtime_version,
        measured_at=measured_at,
    )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    host_meta = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "protocol_version": PROTOCOL_VERSION,
    }

    mlx_obs, mlx_raw = measure_mlx_stage_observations(
        model_path=model_path,
        workloads=workloads,
        benchmark_id=benchmark_id,
        adapter_path=adapter_path,
    )
    all_obs = list(mlx_obs)
    cpu_raw: dict[str, Any] = {}
    if include_cpu_stages:
        cpu_obs, cpu_raw = measure_cpu_stage_observations(
            benchmark_id=benchmark_id,
            profiles=tuple(item.profile for item in workloads),
            replicates=2,
        )
        all_obs.extend(cpu_obs)

    budget = build_budget_from_observations(identity=identity, observations=all_obs)
    budget_path = output_dir / f"{benchmark_id}.budget.json"
    report_path = output_dir / f"{benchmark_id}.protocol.json"
    save_runtime_resource_budget(budget, budget_path)

    report = {
        "protocol_version": PROTOCOL_VERSION,
        "benchmark_id": benchmark_id,
        "measured_at": measured_at.isoformat().replace("+00:00", "Z"),
        "identity": identity.model_dump(mode="json"),
        "environment_probe": environment.model_dump(mode="json"),
        "host": host_meta,
        "model_path": str(Path(model_path).resolve()),
        "workloads": [
            {
                "profile": w.profile.value,
                "prompt_chars": w.prompt_chars,
                "max_new_tokens": w.max_new_tokens,
                "replicates": w.replicates,
            }
            for w in workloads
        ],
        "observation_count": len(all_obs),
        "observations": [item.model_dump(mode="json") for item in all_obs],
        "mlx_raw": mlx_raw,
        "cpu_raw": cpu_raw,
        "budget_path": str(budget_path),
        "budget_stage_keys": [
            f"{stage.profile.value}/{stage.stage_id}" for stage in budget.stages
        ],
        "quality_notes": [
            "Envelope per stage = massimi osservati (derive_stage_budget).",
            "additional_peak_ram_bytes include footprint modello per fail-closed sequenziale.",
            "Swap e system-wide (HostResourceProbe); non attribuito al solo processo.",
            "Questo artifact e misurato; non e validazione scientifica del modello.",
            "Ripetere il benchmark se cambiano modello, quantizzazione, runtime o OS major.",
        ],
        "release_claim": "measured_runtime_budget_only",
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "benchmark_id": benchmark_id,
        "budget_path": str(budget_path),
        "report_path": str(report_path),
        "identity": identity.model_dump(mode="json"),
        "stage_count": len(budget.stages),
        "observation_count": len(all_obs),
    }


__all__ = [
    "DEFAULT_WORKLOADS",
    "PROTOCOL_VERSION",
    "ProfileWorkload",
    "STAGE_HARD",
    "STAGE_MLX_GENERATE",
    "STAGE_RULES",
    "STAGE_SEMANTIC",
    "build_budget_from_observations",
    "measure_cpu_stage_observations",
    "measure_mlx_stage_observations",
    "run_full_runtime_benchmark",
]
