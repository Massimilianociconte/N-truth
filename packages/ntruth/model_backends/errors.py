"""Errori e tipi minimi del backend (senza runtime_resources)."""

from __future__ import annotations

from enum import StrEnum


class RuntimeDevice(StrEnum):
    """Device hint per il backend (MLX Metal su Apple Silicon)."""

    METAL = "metal"
    CPU = "cpu"
    AUTO = "auto"


class ComponentLoadError(RuntimeError):
    """Caricamento pesi/tokenizer fallito o dipendenza ML assente."""


class GraniteBackendError(RuntimeError):
    """Errore operativo del backend Granite."""


class ConstrainedDecodingUnavailable(GraniteBackendError):
    """Constrained decoding richiesto ma non incluso in questo cluster."""


__all__ = [
    "ComponentLoadError",
    "ConstrainedDecodingUnavailable",
    "GraniteBackendError",
    "RuntimeDevice",
]
