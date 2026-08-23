"""Contratto opzionale per adattatori OCR con provenance (PRD v9 roadmap).

N-Truth non esegue OCR e non include alcun motore: questo modulo definisce
SOLO il contratto tipato che un plugin esterno deve rispettare e il registro
explicitamente vuoto di default. Qualsiasi percorso di analisi che trovi un
documento senza testo estraiibile fallisce chiaramente citando l'assenza di
OCR (comportamento documentato), finché un operatore non registra
esplicitamente un adattatore in un ambiente controllato.

Fail-closed per costruzione:
- nessun motore bundled, nessun download implicito;
- ``register_adapter`` è l'unico punto di ingresso, esplicito e verificabile;
- ogni prodotto OCR porta ``OcrProvenance`` (motore, versione, pagina,
  confidenza dichiarata) e non è mai trattato come testo nativo del documento.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pydantic import Field

from ntruth.schemas.kernel import KernelModel, NonBlankStr


class OcrProvenance(KernelModel):
    """Provenance obbligatoria di ogni pagina prodotta da un adattatore OCR."""

    engine_id: NonBlankStr
    engine_version: NonBlankStr
    page: int = Field(ge=1)
    declared_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    language_hint: NonBlankStr | None = None


@dataclass(frozen=True, slots=True)
class OcrPageResult:
    """Testo di una pagina con la sua provenance immutabile."""

    page: int
    text: str
    provenance: OcrProvenance


class OcrAdapter(Protocol):
    """Protocollo minimo per un plugin OCR esterno."""

    engine_id: str
    engine_version: str

    def supports(self, path: str) -> bool:
        """True se l'adattatore sa gestire il file."""
        ...

    def run(self, path: str) -> list[OcrPageResult]:
        """Estrae il testo pagina per pagina con provenance completa."""
        ...


_REGISTRY: dict[str, OcrAdapter] = {}


class OcrUnavailable(RuntimeError):
    """Nessun adattatore OCR registrato: il percorso resta non supportato."""


def register_adapter(adapter: OcrAdapter) -> None:
    """Registra esplicitamente un adattatore (solo ambienti controllati)."""
    _REGISTRY[adapter.engine_id] = adapter


def unregister_all() -> None:
    """Svuota il registro (usato dai test e dal reset operativo)."""
    _REGISTRY.clear()


def get_adapter(engine_id: str) -> OcrAdapter:
    try:
        return _REGISTRY[engine_id]
    except KeyError as exc:  # pragma: no cover - messaggio stabile per i parser
        raise OcrUnavailable(
            f"OCR non disponibile: nessun adattatore registrato con id {engine_id!r}; "
            "N-Truth non esegue OCR e non scarica motori"
        ) from exc


def registered_engines() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


__all__ = [
    "OcrAdapter",
    "OcrPageResult",
    "OcrProvenance",
    "OcrUnavailable",
    "get_adapter",
    "register_adapter",
    "registered_engines",
    "unregister_all",
]
