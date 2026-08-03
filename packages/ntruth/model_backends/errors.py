"""Errori e tipi minimi del backend (senza runtime_resources).

Gli stati constrained decoding vivono qui per evitare import circolari:
``constrained.py`` importa da questo modulo; questo modulo non importa
``constrained`` né ``stage_schemas``.
"""

from __future__ import annotations

from enum import StrEnum


class RuntimeDevice(StrEnum):
    """Device hint per il backend (MLX Metal su Apple Silicon)."""

    METAL = "metal"
    CPU = "cpu"
    AUTO = "auto"


class ConstrainedStatus(StrEnum):
    """Stati machine-readable del percorso structured decoding (fail-closed).

    Sintassi/schema only: non rappresentano verità scientifica né qualifica runtime.
    """

    CONSTRAINED_SUPPORTED = "CONSTRAINED_SUPPORTED"
    CONSTRAINED_UNAVAILABLE = "CONSTRAINED_UNAVAILABLE"
    CONSTRAINT_INITIALIZATION_FAILED = "CONSTRAINT_INITIALIZATION_FAILED"
    CONSTRAINT_COMPILATION_FAILED = "CONSTRAINT_COMPILATION_FAILED"
    GENERATION_OK = "GENERATION_OK"
    GENERATION_INCOMPLETE = "GENERATION_INCOMPLETE"
    SCHEMA_VALIDATION_FAILED = "SCHEMA_VALIDATION_FAILED"
    INVALID_OUTPUT_SCHEMA = "INVALID_OUTPUT_SCHEMA"
    BACKEND_LOAD_FAILED = "BACKEND_LOAD_FAILED"
    # Free-decode esplicito (non un successo constrained).
    FREE_DECODE = "FREE_DECODE"


class ComponentLoadError(RuntimeError):
    """Caricamento pesi/tokenizer fallito o dipendenza ML assente."""


class GraniteBackendError(RuntimeError):
    """Errore operativo del backend Granite."""


class ConstrainedDecodingError(GraniteBackendError):
    """Errore esplicito del percorso structured decoding (nessun fallback silenzioso)."""

    def __init__(self, status: ConstrainedStatus, message: str) -> None:
        super().__init__(f"{status.value}: {message}")
        self.status = status
        self.message = message


class ConstrainedDecodingUnavailable(ConstrainedDecodingError):
    """Structured decoding richiesto ma non disponibile (fail-closed)."""

    def __init__(
        self,
        message: str = "constrained decoding non disponibile; nessun fallback a free-decode",
        *,
        status: ConstrainedStatus = ConstrainedStatus.CONSTRAINED_UNAVAILABLE,
    ) -> None:
        super().__init__(status, message)


__all__ = [
    "ComponentLoadError",
    "ConstrainedDecodingError",
    "ConstrainedDecodingUnavailable",
    "ConstrainedStatus",
    "GraniteBackendError",
    "RuntimeDevice",
]
