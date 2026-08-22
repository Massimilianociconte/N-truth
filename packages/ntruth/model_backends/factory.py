"""Factory backend — default Granite (ADR-0010), legacy Qwen solo con opt-in.

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
    GRANITE_CANONICAL_MODEL_ID,
    GRANITE_CONFIGURED_MAX_CONTEXT_TOKENS,
    GRANITE_MLX_REPO,
)
from ntruth.model_backends.errors import RuntimeDevice
from ntruth.model_backends.granite import GraniteBackend


def resolve_provider(*, provider: str | None = None) -> ModelProvider:
    """Risolve il provider senza registry.

    Precedenza: argomento ``provider`` → env ``NTRUTH_MODEL_PROVIDER`` →
    default ``granite`` (modello Train A provisionale registrato, ADR-0010).
    """

    raw = (provider or os.environ.get("NTRUTH_MODEL_PROVIDER") or "granite").strip().lower()
    if raw in {"granite", "ibm-granite", "granite_4.1"}:
        return ModelProvider.GRANITE
    if raw in {"legacy_qwen", "qwen", "qwen3", "legacy"}:
        return ModelProvider.LEGACY_QWEN
    if raw in {"generic"}:
        return ModelProvider.GENERIC
    raise ValueError(f"provider sconosciuto: {raw!r}; usare granite | legacy_qwen")


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

    - **Default:** Granite (provisional primary Train A; mai scientificamente selezionato).
    - **Legacy Qwen:** mai senza opt-in esplicito — ``allow_legacy=True`` oppure
      env ``NTRUTH_ALLOW_LEGACY_QWEN=1|true|yes``. Nessun fallback silenzioso.
    """

    from ntruth.model_backends.registry import (
        ModelRegistryError,
        legacy_opt_in_enabled,
    )

    chosen = resolve_provider(provider=provider)
    model = (profile or {}).get("model", {}) if profile else {}

    if chosen is ModelProvider.GRANITE:
        return GraniteBackend(
            model_path=model_path,
            adapter_path=adapter_path,
            device=device,
            max_tokens=max_tokens,
            canonical_model_id=str(
                model.get("canonical_repository")
                or model.get("canonical_model_id")
                or GRANITE_CANONICAL_MODEL_ID
            ),
            mlx_repo=str(
                model.get("repository") or model.get("mlx_repository") or GRANITE_MLX_REPO
            ),
            revision=str(model.get("revision") or ""),
            weight_sha256=str(model.get("expected_weight_sha256") or "") or None,
            context_window_tokens=int(
                model.get("context_window_tokens")
                or model.get("configured_maximum_context_tokens")
                or GRANITE_CONFIGURED_MAX_CONTEXT_TOKENS
            ),
        )

    if chosen is ModelProvider.LEGACY_QWEN:
        from ntruth.model_backends.legacy.qwen_backend import LegacyQwenBackend

        opt_in = legacy_opt_in_enabled(allow_legacy=allow_legacy)
        if not opt_in:
            raise ModelRegistryError(
                "legacy Qwen disabilitato di default: serve opt-in esplicito "
                "(allow_legacy=True oppure NTRUTH_ALLOW_LEGACY_QWEN=1); "
                "il default supportato e NTRUTH_MODEL_PROVIDER=granite"
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
