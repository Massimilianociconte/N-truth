"""Adapter constrained decoding provider-agnostic (Outlines / MLX-LM).

Non collega ``parser_ai`` a Outlines: riceve tipi/schema e genera JSON vincolato.
Fallimenti espliciti via ``ConstrainedStatus`` — nessun fallback silenzioso.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class ConstrainedStatus(StrEnum):
    CONSTRAINED_SUPPORTED = "CONSTRAINED_SUPPORTED"
    CONSTRAINED_UNAVAILABLE = "CONSTRAINED_UNAVAILABLE"
    CONSTRAINT_COMPILATION_FAILED = "CONSTRAINT_COMPILATION_FAILED"
    GENERATION_INCOMPLETE = "GENERATION_INCOMPLETE"
    GENERATION_OK = "GENERATION_OK"
    FREE_DECODE = "FREE_DECODE"


class ConstrainedDecodingError(RuntimeError):
    def __init__(self, status: ConstrainedStatus, message: str) -> None:
        super().__init__(f"{status.value}: {message}")
        self.status = status


@dataclass(frozen=True, slots=True)
class ConstrainedCapability:
    status: ConstrainedStatus
    backend: str
    detail: str = ""


def probe_outlines_mlx() -> ConstrainedCapability:
    try:
        import outlines  # noqa: F401
        from outlines import from_mlxlm  # noqa: F401
    except ImportError as exc:
        return ConstrainedCapability(
            status=ConstrainedStatus.CONSTRAINED_UNAVAILABLE,
            backend="outlines+mlx-lm",
            detail=f"outlines non installato: {exc}",
        )
    try:
        import mlx_lm  # noqa: F401
    except ImportError as exc:
        return ConstrainedCapability(
            status=ConstrainedStatus.CONSTRAINED_UNAVAILABLE,
            backend="outlines+mlx-lm",
            detail=f"mlx-lm non installato: {exc}",
        )
    return ConstrainedCapability(
        status=ConstrainedStatus.CONSTRAINED_SUPPORTED,
        backend="outlines+mlx-lm",
        detail="outlines.from_mlxlm disponibile",
    )


class OutlinesMlxAdapter:
    """Wrapper Outlines sopra un modello MLX gia caricato."""

    def __init__(self, model: Any, tokenizer: Any) -> None:
        cap = probe_outlines_mlx()
        if cap.status is not ConstrainedStatus.CONSTRAINED_SUPPORTED:
            raise ConstrainedDecodingError(cap.status, cap.detail)
        try:
            import outlines
        except ImportError as exc:  # pragma: no cover
            raise ConstrainedDecodingError(
                ConstrainedStatus.CONSTRAINED_UNAVAILABLE, str(exc)
            ) from exc
        try:
            self._steerable = outlines.from_mlxlm(model, tokenizer)
        except Exception as exc:
            raise ConstrainedDecodingError(
                ConstrainedStatus.CONSTRAINT_COMPILATION_FAILED,
                f"from_mlxlm fallito: {exc}",
            ) from exc
        self._tokenizer = tokenizer

    def generate(
        self,
        prompt: str,
        output_type: type[BaseModel] | type,
        *,
        max_tokens: int,
    ) -> tuple[str, ConstrainedStatus]:
        try:
            text = self._steerable(prompt, output_type, max_tokens=max_tokens)
        except Exception as exc:
            raise ConstrainedDecodingError(
                ConstrainedStatus.CONSTRAINT_COMPILATION_FAILED
                if "schema" in str(exc).lower() or "compile" in str(exc).lower()
                else ConstrainedStatus.GENERATION_INCOMPLETE,
                str(exc),
            ) from exc
        raw = str(text)
        # Outlines restituisce tipicamente JSON completo; se vuoto → incomplete.
        if not raw.strip():
            return raw, ConstrainedStatus.GENERATION_INCOMPLETE
        return raw, ConstrainedStatus.GENERATION_OK


def compile_schema_probe(output_type: type[BaseModel]) -> dict[str, Any]:
    """Verifica che lo schema Pydantic sia serializzabile (pre-flight test)."""

    try:
        schema = output_type.model_json_schema()
    except Exception as exc:
        raise ConstrainedDecodingError(
            ConstrainedStatus.CONSTRAINT_COMPILATION_FAILED,
            f"model_json_schema fallito: {exc}",
        ) from exc
    # Dimensioni utili per report
    import json

    payload = json.dumps(schema, sort_keys=True)
    return {
        "schema_title": schema.get("title") or output_type.__name__,
        "schema_bytes": len(payload.encode("utf-8")),
        "schema_keys": sorted(schema.keys()),
        "status": ConstrainedStatus.CONSTRAINED_SUPPORTED.value,
    }


__all__ = [
    "ConstrainedCapability",
    "ConstrainedDecodingError",
    "ConstrainedStatus",
    "OutlinesMlxAdapter",
    "compile_schema_probe",
    "probe_outlines_mlx",
]
