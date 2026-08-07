"""Factory backend — cluster 1: Qwen resta il percorso default esistente.

Granite è disponibile esplicitamente, non promosso a default operativo.
Nessuna lettura di models/registry/.
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
    default ``legacy_qwen`` (comportamento pre-migrazione versionato).
    """

    raw = (provider or os.environ.get("NTRUTH_MODEL_PROVIDER") or "legacy_qwen").strip().lower()
    if raw in {"granite", "ibm-granite", "granite_4.1"}:
        return ModelProvider.GRANITE
    if raw in {"legacy_qwen", "qwen", "qwen3", "legacy"}:
        return ModelProvider.LEGACY_QWEN
    if raw in {"generic"}:
        return ModelProvider.GENERIC
    raise ValueError(
        f"provider sconosciuto: {raw!r}; usare granite | legacy_qwen"
    )


def create_model_backend(
    *,
    model_path: Path,
    adapter_path: Path | None = None,
    device: RuntimeDevice = RuntimeDevice.METAL,
    max_tokens: int = 1024,
    profile: dict[str, Any] | None = None,
    provider: str | None = None,
    allow_legacy: bool = True,
) -> ModelBackend:
    """Crea un backend.

    - **Default (cluster 1):** ``legacy_qwen`` se non specificato diversamente.
    - **Granite:** solo con ``provider="granite"`` o ``NTRUTH_MODEL_PROVIDER=granite``.

    ``allow_legacy`` è accettato per compatibilità; il default non richiede opt-in
    per Qwen in questo cluster (Qwen è ancora il percorso esistente).
    """

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
            mlx_repo=str(model.get("repository") or model.get("mlx_repository") or GRANITE_MLX_REPO),
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

        # Cluster 1: Qwen remains the existing default path.
        _ = allow_legacy  # reserved for cluster 2 promotion policy
        return LegacyQwenBackend(
            model_path=model_path,
            adapter_path=adapter_path,
            device=device,
            max_tokens=max_tokens,
            enabled=True,
        )

    raise ValueError(f"provider non istanziabile: {chosen}")


__all__ = ["create_model_backend", "resolve_provider"]
