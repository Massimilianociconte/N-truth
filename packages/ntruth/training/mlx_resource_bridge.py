"""Ponte MLX ↔ RuntimeResourceManager (adapter in training/, ADR-0003).

Quando ``resource_budget_path`` e assente il chiamante usa il percorso legacy.
I budget devono provenire da misure reali: nessun peak M5 e hardcoded qui.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ntruth.runtime_resources.budget_io import (
    RuntimeBudgetIOError,
    load_runtime_resource_budget,
)
from ntruth.runtime_resources.manager import (
    BenchmarkEnvironmentMismatch,
    BundleExecution,
    BundleRuntimeMetrics,
    ComponentFactory,
    ComponentLoadError,
    ResourceProbe,
    RuntimeInput,
    RuntimeResourceManager,
    StageInvocation,
)
from ntruth.runtime_resources.profiles import runtime_profile
from ntruth.runtime_resources.schema import RuntimeDevice, RuntimeProfileName
from ntruth.training.mlx_runtime import MLXPipelineError
from ntruth.training.runtime_env import (
    RuntimeEnvironmentProbeError,
    probe_runtime_environment,
)

DEFAULT_STAGE_ID = "mlx_generate"
DEFAULT_COMPONENT_ID = "mlx_lm"
DEFAULT_RUNTIME_NAME = "mlx-lm"


def installed_mlx_lm_version() -> str:
    """Versione installata di mlx-lm, o marker esplicito se assente."""

    try:
        return importlib.metadata.version("mlx-lm")
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def estimate_input_tokens(
    payload: Mapping[str, Any] | str,
    *,
    tokenizer: Any | None = None,
) -> int:
    """Stima token di input: tokenizer se disponibile, altrimenti ``len//4``."""

    if isinstance(payload, str):
        text = payload
    else:
        prompt = payload.get("prompt")
        if isinstance(prompt, str) and prompt:
            text = prompt
        else:
            messages = payload.get("messages")
            if isinstance(messages, list):
                text = json.dumps(messages, ensure_ascii=False, sort_keys=True)
            else:
                text = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True)

    if tokenizer is not None:
        encode = getattr(tokenizer, "encode", None)
        if callable(encode):
            try:
                tokens = encode(text, add_special_tokens=False)
                count = len(tokens)
                if count >= 0:
                    return max(1, count) if text else 0
            except Exception:
                pass
    if not text:
        return 0
    return max(1, len(text) // 4)


def component_fingerprint_for(
    model_path: Path,
    adapter_path: Path | None,
    *,
    explicit: str | None = None,
) -> str:
    """SHA-256 lowercase per StageInvocation; preferisce un hash gia verificato."""

    if explicit is not None:
        value = explicit.strip().lower()
        if len(value) == 64 and all(character in "0123456789abcdef" for character in value):
            return value
        raise MLXPipelineError("component_fingerprint deve essere SHA-256 lowercase")
    digest = hashlib.sha256()
    digest.update(str(Path(model_path).resolve()).encode("utf-8"))
    if adapter_path is not None:
        digest.update(str(Path(adapter_path).resolve()).encode("utf-8"))
    return digest.hexdigest()


def dump_bundle_runtime_metrics(metrics: BundleRuntimeMetrics) -> dict[str, Any]:
    """Serializza le metriche di bundle per il report di evaluation."""

    return metrics.model_dump(mode="json")


def _default_mlx_factory(
    *,
    model_path: Path,
    adapter_path: Path | None,
    max_tokens: int,
) -> ComponentFactory:
    from ntruth.training.mlx_component import MLXGenerateComponent

    def factory(device: RuntimeDevice) -> MLXGenerateComponent:
        try:
            return MLXGenerateComponent(
                model_path=model_path,
                adapter_path=adapter_path,
                device=device,
                max_tokens=max_tokens,
            )
        except ComponentLoadError:
            raise
        except Exception as exc:
            raise ComponentLoadError(str(exc)) from exc

    return factory


def run_predict_bundle(
    *,
    requests: Sequence[Mapping[str, Any] | str],
    resource_budget_path: Path | None,
    resource_profile: str = "BALANCED",
    stage_id: str = DEFAULT_STAGE_ID,
    component_id: str = DEFAULT_COMPONENT_ID,
    component_fingerprint: str | None = None,
    model_path: Path | None = None,
    adapter_path: Path | None = None,
    max_tokens: int = 1024,
    runtime_name: str | None = None,
    runtime_version: str | None = None,
    require_complete_measurements: bool = True,
    probe: ResourceProbe | None = None,
    component_factory: ComponentFactory | None = None,
    tokenizer: Any | None = None,
    bundle_id: str = "mlx-predict",
    keep_warm: bool = False,
) -> BundleExecution | None:
    """Esegue una generazione batch sotto ``RuntimeResourceManager``.

    Se ``resource_budget_path`` e ``None`` restituisce ``None`` (percorso legacy).
    In caso di mismatch ambiente/budget solleva ``MLXPipelineError`` chiara.
    Il manager viene sempre chiuso (unload) all'uscita.
    """

    if resource_budget_path is None:
        return None
    if not requests:
        raise MLXPipelineError("run_predict_bundle richiede almeno una request")

    try:
        budget = load_runtime_resource_budget(Path(resource_budget_path))
    except RuntimeBudgetIOError as exc:
        raise MLXPipelineError(str(exc)) from exc

    try:
        profile_name = RuntimeProfileName(resource_profile)
    except ValueError as exc:
        raise MLXPipelineError(
            f"resource_profile non supportato: {resource_profile!r} "
            f"(attesi {[item.value for item in RuntimeProfileName]})"
        ) from exc

    try:
        budget.for_stage(profile_name, stage_id)
    except KeyError as exc:
        raise MLXPipelineError(
            f"stage {stage_id!r} assente dal budget per profilo {profile_name.value}"
        ) from exc

    # Runtime effettivo (non copiato dal budget) cosi un mismatch non viene mascherato.
    name = (runtime_name or DEFAULT_RUNTIME_NAME).strip()
    version = (
        runtime_version if runtime_version is not None else installed_mlx_lm_version()
    ).strip()
    try:
        environment = probe_runtime_environment(name, version)
    except RuntimeEnvironmentProbeError as exc:
        raise MLXPipelineError(f"ambiente runtime non misurabile: {exc}") from exc

    profile = runtime_profile(profile_name)
    fingerprint = component_fingerprint_for(
        model_path or Path("."),
        adapter_path,
        explicit=component_fingerprint,
    )

    factory = component_factory
    if factory is None:
        if model_path is None:
            raise MLXPipelineError(
                "model_path obbligatorio quando non si fornisce component_factory"
            )
        factory = _default_mlx_factory(
            model_path=Path(model_path),
            adapter_path=Path(adapter_path) if adapter_path is not None else None,
            max_tokens=max_tokens,
        )

    inputs: list[RuntimeInput] = []
    for index, request in enumerate(requests):
        if isinstance(request, str):
            payload: Mapping[str, Any] | str = request
        elif isinstance(request, Mapping):
            payload = dict(request)
        else:
            raise MLXPipelineError(
                f"request[{index}] deve essere str o mapping, ricevuto {type(request).__name__}"
            )
        inputs.append(
            RuntimeInput(
                payload=payload,
                input_tokens=estimate_input_tokens(payload, tokenizer=tokenizer),
            )
        )

    manager: RuntimeResourceManager | None = None
    try:
        try:
            manager = RuntimeResourceManager(
                profile=profile,
                budget=budget,
                environment=environment,
                probe=probe,
                require_complete_measurements=require_complete_measurements,
            )
        except BenchmarkEnvironmentMismatch as exc:
            raise MLXPipelineError(
                "budget di risorse non appartiene all'ambiente corrente; "
                "ripetere il benchmark sulla macchina/runtime attivi "
                f"(identity={budget.identity.benchmark_id!r}, "
                f"machine={environment.machine_model!r}, "
                f"runtime={environment.runtime_name!r} "
                f"{environment.runtime_version!r}): {exc}"
            ) from exc

        stage = StageInvocation(
            stage_id=stage_id,
            component_id=component_id,
            component_fingerprint=fingerprint,
            factory=factory,
            inputs=tuple(inputs),
            keep_warm=keep_warm,
        )
        return manager.execute_bundle(bundle_id, (stage,))
    except MLXPipelineError:
        raise
    except Exception as exc:
        raise MLXPipelineError(f"esecuzione resource-managed fallita: {exc}") from exc
    finally:
        if manager is not None:
            manager.close()
