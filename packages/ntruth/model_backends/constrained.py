"""Structured decoding provider-agnostic (Outlines / MLX-LM) — Cluster 3A.

Fail-closed: se Outlines manca o lo schema non è valido, errore esplicito.
Nessun fallback silenzioso a free-decode. Sintassi only, non verità scientifica.

Gli errori pubblici vivono in ``errors.py``; questo modulo li importa.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, TypeVar

from pydantic import BaseModel, ValidationError

from ntruth.model_backends.errors import (
    ConstrainedDecodingError,
    ConstrainedDecodingUnavailable,
    ConstrainedStatus,
)
from ntruth.model_backends.stage_schemas import (
    FORBIDDEN_STAGE_FIELDS,
    NULL_TO_EMPTY_ARRAY_ALLOWLIST,
    resolve_stage_schema,
    schema_identity,
)

T = TypeVar("T", bound=BaseModel)

_ENUM_CASE_MAP: dict[str, dict[str, str]] = {
    # quantifier literals → forma canonica solo via mapping esatto case-insensitive
    "quantifier": {
        "exact": "EXACT",
        "approximate": "APPROXIMATE",
        "range": "RANGE",
        "lower_bound": "LOWER_BOUND",
        "upper_bound": "UPPER_BOUND",
        "unknown": "UNKNOWN",
        "not_reported": "NOT_REPORTED",
    },
    "relation_type": {
        "nested_in": "nested_in",
        "derived_from": "derived_from",
        "other": "other",
    },
    "status": {
        "complete": "complete",
        "partial": "partial",
        "failed": "failed",
    },
    "authority": {
        "model": "model",
    },
}


@dataclass(frozen=True, slots=True)
class ConstrainedCapability:
    status: ConstrainedStatus
    backend: str
    detail: str = ""
    outlines_version: str | None = None
    mlx_lm_version: str | None = None


@dataclass(frozen=True, slots=True)
class StructuredDecodeResult:
    """Contratto risultato structured decoding (sintassi, non scienza)."""

    status: ConstrainedStatus
    parsed: dict[str, Any] | None
    raw_output: str | None
    schema_valid: bool
    truncated: bool
    fallback_used: bool
    diagnostics: Mapping[str, Any]
    schema_name: str
    schema_version: str
    backend: str
    backend_version: str | None
    max_tokens: int
    terminated_by_eos: bool | None = None
    terminated_by_stop: bool | None = None
    schema_status: str = "EXPERIMENTAL"
    extra: Mapping[str, Any] = field(default_factory=dict)

    def as_diagnostics_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "schema_valid": self.schema_valid,
            "truncated": self.truncated,
            "fallback_used": self.fallback_used,
            "schema_name": self.schema_name,
            "schema_version": self.schema_version,
            "schema_status": self.schema_status,
            "backend": self.backend,
            "backend_version": self.backend_version,
            "max_tokens": self.max_tokens,
            "terminated_by_eos": self.terminated_by_eos,
            "terminated_by_stop": self.terminated_by_stop,
            "diagnostics": dict(self.diagnostics),
            **dict(self.extra),
        }


def probe_outlines_mlx() -> ConstrainedCapability:
    """Probe lazy: non importa Outlines a livello di package core se non chiamato."""

    outlines_version: str | None = None
    mlx_lm_version: str | None = None
    try:
        import outlines  # noqa: PLC0415
        from outlines import from_mlxlm  # noqa: F401, PLC0415
        from outlines import Generator  # noqa: F401, PLC0415

        outlines_version = getattr(outlines, "__version__", None)
        if outlines_version is None:
            try:
                from importlib.metadata import version as _pkg_version  # noqa: PLC0415

                outlines_version = _pkg_version("outlines")
            except Exception:  # noqa: BLE001
                outlines_version = None
    except ImportError as exc:
        return ConstrainedCapability(
            status=ConstrainedStatus.CONSTRAINED_UNAVAILABLE,
            backend="outlines+mlx-lm",
            detail=f"outlines non installato o API assente: {exc}",
        )
    try:
        import mlx_lm  # noqa: PLC0415

        mlx_lm_version = getattr(mlx_lm, "__version__", None)
        if mlx_lm_version is None:
            try:
                from importlib.metadata import version as _pkg_version  # noqa: PLC0415

                mlx_lm_version = _pkg_version("mlx-lm")
            except Exception:  # noqa: BLE001
                mlx_lm_version = None
    except ImportError as exc:
        return ConstrainedCapability(
            status=ConstrainedStatus.CONSTRAINED_UNAVAILABLE,
            backend="outlines+mlx-lm",
            detail=f"mlx-lm non installato: {exc}",
            outlines_version=outlines_version,
        )
    return ConstrainedCapability(
        status=ConstrainedStatus.CONSTRAINED_SUPPORTED,
        backend="outlines+mlx-lm",
        detail="outlines.from_mlxlm + Generator disponibili",
        outlines_version=outlines_version,
        mlx_lm_version=mlx_lm_version,
    )


def safe_structural_normalize(payload: Any) -> Any:
    """Normalizzazione strutturale sicura (allowlist).

    Consentito: null→[] su chiavi allowlist; ordinamento chiavi; whitespace
    non semantico; case enum solo via mapping esatto.
    Vietato: stringa→fatto/evidence/relazione; invenzione entità; missing facts;
    allocation/independence; rules engine.
    """

    if isinstance(payload, dict):
        out: dict[str, Any] = {}
        for key in sorted(payload.keys(), key=lambda k: str(k)):
            value = payload[key]
            if value is None and str(key) in NULL_TO_EMPTY_ARRAY_ALLOWLIST:
                out[str(key)] = []
                continue
            if isinstance(value, str) and str(key) in _ENUM_CASE_MAP:
                mapped = _ENUM_CASE_MAP[str(key)].get(value.strip().lower())
                out[str(key)] = mapped if mapped is not None else value.strip()
                continue
            if isinstance(value, str):
                # whitespace non semantico ai bordi; non inventare tipi
                out[str(key)] = value.strip() if value.strip() != value else value
                continue
            out[str(key)] = safe_structural_normalize(value)
        return out
    if isinstance(payload, list):
        return [safe_structural_normalize(item) for item in payload]
    return payload


def _reject_forbidden_fields(payload: Any, *, path: str = "") -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_s = str(key)
            if key_s in FORBIDDEN_STAGE_FIELDS:
                raise ConstrainedDecodingError(
                    ConstrainedStatus.SCHEMA_VALIDATION_FAILED,
                    f"campo vietato (candidate-only): {path + key_s}",
                )
            _reject_forbidden_fields(value, path=f"{path}{key_s}.")
    elif isinstance(payload, list):
        for idx, item in enumerate(payload):
            _reject_forbidden_fields(item, path=f"{path}[{idx}].")


def validate_against_schema(
    raw: str | Mapping[str, Any],
    output_type: type[BaseModel],
    *,
    apply_safe_normalize: bool = True,
) -> tuple[dict[str, Any], BaseModel]:
    """Parse + safe normalize + pydantic validate. Fail-closed su errori."""

    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            raise ConstrainedDecodingError(
                ConstrainedStatus.GENERATION_INCOMPLETE,
                "output structured vuoto",
            )
        try:
            loaded: Any = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ConstrainedDecodingError(
                ConstrainedStatus.GENERATION_INCOMPLETE,
                f"JSON non parsabile: {exc}",
            ) from exc
    else:
        loaded = dict(raw)

    if not isinstance(loaded, dict):
        raise ConstrainedDecodingError(
            ConstrainedStatus.SCHEMA_VALIDATION_FAILED,
            f"root JSON deve essere object, ottenuto {type(loaded).__name__}",
        )

    _reject_forbidden_fields(loaded)
    normalized = safe_structural_normalize(loaded) if apply_safe_normalize else loaded
    if not isinstance(normalized, dict):
        raise ConstrainedDecodingError(
            ConstrainedStatus.SCHEMA_VALIDATION_FAILED,
            "normalizzazione ha prodotto un non-object",
        )
    _reject_forbidden_fields(normalized)

    try:
        model = output_type.model_validate(normalized)
    except ValidationError as exc:
        raise ConstrainedDecodingError(
            ConstrainedStatus.SCHEMA_VALIDATION_FAILED,
            f"validazione schema fallita: {exc}",
        ) from exc

    parsed = model.model_dump(mode="json")
    return parsed, model


def compile_schema_probe(output_type: type[BaseModel]) -> dict[str, Any]:
    """Verifica che lo schema Pydantic sia serializzabile (pre-flight)."""

    try:
        schema = output_type.model_json_schema()
    except Exception as exc:  # noqa: BLE001
        raise ConstrainedDecodingError(
            ConstrainedStatus.CONSTRAINT_COMPILATION_FAILED,
            f"model_json_schema fallito: {exc}",
        ) from exc
    payload = json.dumps(schema, sort_keys=True)
    identity = schema_identity(output_type)
    return {
        "schema_title": schema.get("title") or output_type.__name__,
        "schema_bytes": len(payload.encode("utf-8")),
        "schema_keys": sorted(schema.keys()),
        "status": ConstrainedStatus.CONSTRAINED_SUPPORTED.value,
        **identity,
    }


def resolve_output_type(
    output_schema: type[BaseModel] | str | None,
    *,
    schema_name: str | None = None,
) -> type[BaseModel]:
    """Risolve il tipo di output; INVALID_OUTPUT_SCHEMA se assente/sconosciuto."""

    target = output_schema if output_schema is not None else schema_name
    if target is None:
        raise ConstrainedDecodingError(
            ConstrainedStatus.INVALID_OUTPUT_SCHEMA,
            "output_schema/schema_name obbligatorio per generate_structured constrained",
        )
    try:
        return resolve_stage_schema(target)
    except KeyError as exc:
        raise ConstrainedDecodingError(
            ConstrainedStatus.INVALID_OUTPUT_SCHEMA,
            str(exc),
        ) from exc
    except TypeError as exc:
        raise ConstrainedDecodingError(
            ConstrainedStatus.INVALID_OUTPUT_SCHEMA,
            str(exc),
        ) from exc


class OutlinesMlxAdapter:
    """Wrapper Outlines sopra un modello MLX già caricato."""

    def __init__(self, model: Any, tokenizer: Any) -> None:
        cap = probe_outlines_mlx()
        if cap.status is not ConstrainedStatus.CONSTRAINED_SUPPORTED:
            raise ConstrainedDecodingUnavailable(
                cap.detail or "outlines/mlx-lm non disponibili",
                status=cap.status,
            )
        try:
            import outlines  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover
            raise ConstrainedDecodingUnavailable(str(exc)) from exc
        try:
            self._mlx_model = outlines.from_mlxlm(model, tokenizer)
        except Exception as exc:  # noqa: BLE001
            raise ConstrainedDecodingError(
                ConstrainedStatus.CONSTRAINT_INITIALIZATION_FAILED,
                f"from_mlxlm fallito: {exc}",
            ) from exc
        self._tokenizer = tokenizer
        self._outlines = outlines
        self._cap = cap
        self._backend_version = cap.outlines_version

    def _build_generator(self, output_type: type[BaseModel]) -> Any:
        try:
            # Pre-flight JSON schema
            compile_schema_probe(output_type)
            return self._outlines.Generator(self._mlx_model, output_type)
        except ConstrainedDecodingError:
            raise
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).lower()
            if any(k in msg for k in ("schema", "compile", "json", "type", "regex")):
                status = ConstrainedStatus.CONSTRAINT_COMPILATION_FAILED
            else:
                status = ConstrainedStatus.CONSTRAINT_INITIALIZATION_FAILED
            raise ConstrainedDecodingError(
                status,
                f"inizializzazione/compilazione Generator fallita: {exc}",
            ) from exc

    def generate(
        self,
        prompt: str,
        output_type: type[BaseModel],
        *,
        max_tokens: int,
    ) -> StructuredDecodeResult:
        """Genera JSON vincolato e valida contro lo schema. Fail-closed."""

        if max_tokens <= 0:
            raise ConstrainedDecodingError(
                ConstrainedStatus.CONSTRAINT_INITIALIZATION_FAILED,
                "max_tokens deve essere > 0",
            )

        identity = schema_identity(output_type)
        generator = self._build_generator(output_type)

        try:
            raw_obj = generator(prompt, max_tokens=max_tokens)
        except ConstrainedDecodingError:
            raise
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).lower()
            if any(k in msg for k in ("schema", "compile", "jsonschema", "grammar")):
                raise ConstrainedDecodingError(
                    ConstrainedStatus.CONSTRAINT_COMPILATION_FAILED,
                    str(exc),
                ) from exc
            if any(k in msg for k in ("load", "weight", "metal", "mlx")):
                raise ConstrainedDecodingError(
                    ConstrainedStatus.BACKEND_LOAD_FAILED,
                    str(exc),
                ) from exc
            raise ConstrainedDecodingError(
                ConstrainedStatus.GENERATION_INCOMPLETE,
                str(exc),
            ) from exc

        if isinstance(raw_obj, BaseModel):
            raw_text = raw_obj.model_dump_json()
        elif isinstance(raw_obj, Mapping):
            raw_text = json.dumps(raw_obj, ensure_ascii=False, sort_keys=True)
        else:
            raw_text = str(raw_obj)

        if not raw_text.strip():
            return StructuredDecodeResult(
                status=ConstrainedStatus.GENERATION_INCOMPLETE,
                parsed=None,
                raw_output=raw_text,
                schema_valid=False,
                truncated=False,
                fallback_used=False,
                diagnostics={"reason": "empty_output"},
                schema_name=identity["schema_name"],
                schema_version=identity["schema_version"],
                schema_status=identity["schema_status"],
                backend="outlines+mlx-lm",
                backend_version=self._backend_version,
                max_tokens=max_tokens,
            )

        try:
            parsed, _model = validate_against_schema(raw_text, output_type)
        except ConstrainedDecodingError as exc:
            truncated = _looks_truncated(raw_text, max_tokens=max_tokens)
            if exc.status is ConstrainedStatus.GENERATION_INCOMPLETE and truncated:
                status = ConstrainedStatus.GENERATION_INCOMPLETE
            else:
                status = exc.status
            return StructuredDecodeResult(
                status=status,
                parsed=None,
                raw_output=raw_text,
                schema_valid=False,
                truncated=truncated,
                fallback_used=False,
                diagnostics={"error": exc.message, "status": exc.status.value},
                schema_name=identity["schema_name"],
                schema_version=identity["schema_version"],
                schema_status=identity["schema_status"],
                backend="outlines+mlx-lm",
                backend_version=self._backend_version,
                max_tokens=max_tokens,
            )

        truncated = _looks_truncated(raw_text, max_tokens=max_tokens)
        return StructuredDecodeResult(
            status=ConstrainedStatus.GENERATION_OK,
            parsed=parsed,
            raw_output=raw_text,
            schema_valid=True,
            truncated=truncated,
            fallback_used=False,
            diagnostics={
                "mode": "outlines_generator",
                "outlines_version": self._backend_version,
                "mlx_lm_version": self._cap.mlx_lm_version,
            },
            schema_name=identity["schema_name"],
            schema_version=identity["schema_version"],
            schema_status=identity["schema_status"],
            backend="outlines+mlx-lm",
            backend_version=self._backend_version,
            max_tokens=max_tokens,
            # EOS/stop non esposti in modo affidabile da Outlines/MLX qui.
            terminated_by_eos=None,
            terminated_by_stop=None,
        )


def _looks_truncated(raw: str, *, max_tokens: int) -> bool:
    """Euristica conservativa: sbilanciamento braces o testo molto lungo vs budget."""

    if raw.count("{") > raw.count("}"):
        return True
    if raw.count("[") > raw.count("]"):
        return True
    # Non inventiamo token count se il tokenizer non è disponibile qui.
    # Solo segnale grezzo su lunghezza caratteri rispetto a un budget grezzo.
    if max_tokens > 0 and len(raw) > max_tokens * 16:
        return True
    # JSON apparentemente tagliato a metà stringa
    if re.search(r'[^\\]"\s*$', raw) is None and raw.rstrip().endswith('"'):
        return False
    return False


def require_constrained_capability() -> ConstrainedCapability:
    """Fail-closed helper: solleva se Outlines/MLX non supportano constrained."""

    cap = probe_outlines_mlx()
    if cap.status is not ConstrainedStatus.CONSTRAINED_SUPPORTED:
        raise ConstrainedDecodingUnavailable(
            cap.detail or "constrained decoding non disponibile",
            status=cap.status,
        )
    return cap


__all__ = [
    "ConstrainedCapability",
    "ConstrainedDecodingError",
    "ConstrainedDecodingUnavailable",
    "ConstrainedStatus",
    "OutlinesMlxAdapter",
    "StructuredDecodeResult",
    "compile_schema_probe",
    "probe_outlines_mlx",
    "require_constrained_capability",
    "resolve_output_type",
    "safe_structural_normalize",
    "validate_against_schema",
]
