"""Factory backend — default MiniCPM (ADR-0019), legacy con opt-in.

Il percorso Granite (ADR-0010) resta disponibile come confronto esplicito:
richiede ``allow_legacy=True`` oppure ``NTRUTH_ALLOW_LEGACY_GRANITE=1|true|yes``.
Il percorso pre-migrazione Qwen resta disponibile come bootstrap esplicito:
richiede ``allow_legacy=True`` oppure ``NTRUTH_ALLOW_LEGACY_QWEN=1|true|yes``.
La policy di promozione e qualificazione vive in ``ntruth.model_backends.registry``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ntruth.model_backends.base import ModelBackend, ModelProvider
from ntruth.model_backends.constants import (
    MINICPM_CANONICAL_MODEL_ID,
    MINICPM_CONFIGURED_MAX_CONTEXT_TOKENS,
    MINICPM_MLX_REPO,
)
from ntruth.model_backends.errors import RuntimeDevice
from ntruth.model_backends.minicpm import MiniCPMBackend


def resolve_provider(*, provider: str | None = None) -> ModelProvider:
    """Risolve il provider senza registry.

    Precedenza: argomento ``provider`` → env ``NTRUTH_MODEL_PROVIDER`` →
    default ``minicpm`` (modello Train A provisionale registrato, ADR-0019).
    """

    raw = (provider or os.environ.get("NTRUTH_MODEL_PROVIDER") or "minicpm").strip().lower()
    if raw in {"minicpm", "minicpm5", "openbmb", "minicpm5-2b"}:
        return ModelProvider.MINICPM
    if raw in {"granite", "ibm-granite", "granite_4.1"}:
        return ModelProvider.GRANITE
    if raw in {"legacy_qwen", "qwen", "qwen3", "legacy"}:
        return ModelProvider.LEGACY_QWEN
    if raw in {"generic"}:
        return ModelProvider.GENERIC
    raise ValueError(f"provider sconosciuto: {raw!r}; usare minicpm | granite | legacy_qwen")


def create_model_backend(
    *,
    model_path: Path,
    adapter_path: Path | None = None,
    device: RuntimeDevice = RuntimeDevice.METAL,
    max_tokens: int = 1024,
    profile: dict[str, Any] | None = None,
    provider: str | None = None,
    allow_legacy: bool = False,
) -> ModelBackend:
    """Crea un backend fail-closed rispetto alla policy legacy.

    - **Default:** MiniCPM (provisional primary Train A; mai scientificamente selezionato).
    - **Legacy Granite/Qwen:** mai senza opt-in esplicito — ``allow_legacy=True``
      oppure env ``NTRUTH_ALLOW_LEGACY_GRANITE`` / ``NTRUTH_ALLOW_LEGACY_QWEN``
      (``1|true|yes``). Nessun fallback silenzioso.
    """

    from ntruth.model_backends.granite import GraniteBackend
    from ntruth.model_backends.registry import (
        ModelRegistryError,
        legacy_granite_opt_in_enabled,
        legacy_opt_in_enabled,
    )

    chosen = resolve_provider(provider=provider)
    model = (profile or {}).get("model", {}) if profile else {}

    if chosen is ModelProvider.MINICPM:
        return MiniCPMBackend(
            model_path=model_path,
            adapter_path=adapter_path,
            device=device,
            max_tokens=max_tokens,
            canonical_model_id=str(
                model.get("canonical_repository")
                or model.get("canonical_model_id")
                or MINICPM_CANONICAL_MODEL_ID
            ),
            mlx_repo=str(
                model.get("repository") or model.get("mlx_repository") or MINICPM_MLX_REPO
            ),
            revision=str(model.get("revision") or ""),
            weight_sha256=str(model.get("expected_weight_sha256") or "") or None,
            context_window_tokens=int(
                model.get("context_window_tokens")
                or model.get("configured_maximum_context_tokens")
                or MINICPM_CONFIGURED_MAX_CONTEXT_TOKENS
            ),
        )

    if chosen is ModelProvider.GRANITE:
        opt_in = legacy_granite_opt_in_enabled(allow_legacy=allow_legacy)
        if not opt_in:
            raise ModelRegistryError(
                "legacy Granite disabilitato di default (ADR-0019): serve opt-in esplicito "
                "(allow_legacy=True oppure NTRUTH_ALLOW_LEGACY_GRANITE=1); "
                "il default supportato e NTRUTH_MODEL_PROVIDER=minicpm"
            )
        return GraniteBackend(
            model_path=model_path,
            adapter_path=adapter_path,
            device=device,
            max_tokens=max_tokens,
            canonical_model_id=str(
                model.get("canonical_repository") or model.get("canonical_model_id") or ""
            ),
            mlx_repo=str(model.get("repository") or model.get("mlx_repository") or ""),
            revision=str(model.get("revision") or ""),
            weight_sha256=str(model.get("expected_weight_sha256") or "") or None,
            context_window_tokens=int(
                model.get("context_window_tokens")
                or model.get("configured_maximum_context_tokens")
                or 131_072
            ),
        )

    if chosen is ModelProvider.LEGACY_QWEN:
        from ntruth.model_backends.legacy.qwen_backend import LegacyQwenBackend

        opt_in = legacy_opt_in_enabled(allow_legacy=allow_legacy)
        if not opt_in:
            raise ModelRegistryError(
                "legacy Qwen disabilitato di default: serve opt-in esplicito "
                "(allow_legacy=True oppure NTRUTH_ALLOW_LEGACY_QWEN=1); "
                "il default supportato e NTRUTH_MODEL_PROVIDER=minicpm"
            )
        return LegacyQwenBackend(
            model_path=model_path,
            adapter_path=adapter_path,
            device=device,
            max_tokens=max_tokens,
            enabled=True,
        )

    raise ValueError(f"provider non istanziabile: {chosen}")


__all__ = ["create_model_backend", "resolve_provider"]
