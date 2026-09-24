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
    """Errore operativo del backend Granite (legacy da ADR-0019)."""


class MiniCPMBackendError(RuntimeError):
    """Errore operativo del backend MiniCPM (primario provvisorio, ADR-0019)."""


class ConstrainedDecodingUnavailable(RuntimeError):
    """Constrained decoding richiesto ma non incluso nel cluster-1 del backend.

    Base RuntimeError (non provider-specifica) cosi sia il backend legacy
    Granite sia il backend MiniCPM possono sollevarla senza fallback silenziosi.
    """


__all__ = [
    "ComponentLoadError",
    "ConstrainedDecodingUnavailable",
    "GraniteBackendError",
    "MiniCPMBackendError",
    "RuntimeDevice",
]
