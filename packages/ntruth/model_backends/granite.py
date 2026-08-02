"""Backend sperimentale IBM Granite 4.1 3B Instruct via MLX-LM.

Cluster 1: backend disponibile e testabile, **non** default operativo e **non**
qualificato. Stato di qualificazione: solo registry (commit successivo).

Checkpoint canonico: ``ibm-granite/granite-4.1-3b`` (Apache-2.0).
Bootstrap Apple Silicon: conversione community ``mlx-community/granite-4.1-3b-4bit``
(non artefatto ufficiale IBM).

Candidate facts only. Constrained decoding non incluso in questo cluster:
richieste ``constrained=True`` falliscono esplicitamente.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ntruth.model_backends.base import (
    MODEL_MUST_NOT_EMIT,
    BackendResourceMetrics,
    GenerationRequest,
    GenerationResult,
    ModelBackend,
    ModelMetadata,
    ModelProvider,
    ModelRole,
    SamplingConfig,
)
from ntruth.model_backends.constants import (
    GRANITE_CANONICAL_MODEL_ID,
    GRANITE_CONFIGURED_MAX_CONTEXT_TOKENS,
    GRANITE_MLX_REPO,
)
from ntruth.model_backends.errors import (
    ComponentLoadError,
    ConstrainedDecodingUnavailable,
    GraniteBackendError,
    RuntimeDevice,
)


class GraniteBackend(ModelBackend):
    """Implementazione Granite via MLX-LM (Metal) — free decode only (cluster 1)."""

    MLX_LIBRARY_DEFAULT_MAX_TOKENS = 256

    def __init__(
        self,
        *,
        model_path: Path,
        adapter_path: Path | None = None,
        device: RuntimeDevice = RuntimeDevice.METAL,
        max_tokens: int = 1024,
        canonical_model_id: str = GRANITE_CANONICAL_MODEL_ID,
        mlx_repo: str = GRANITE_MLX_REPO,
        revision: str = "",
        weight_sha256: str | None = None,
        context_window_tokens: int = GRANITE_CONFIGURED_MAX_CONTEXT_TOKENS,
    ) -> None:
        self.model_path = Path(model_path)
        self.adapter_path = Path(adapter_path) if adapter_path is not None else None
        self.device = device
        self.max_tokens = max_tokens
        self.canonical_model_id = canonical_model_id
        self.mlx_repo = mlx_repo
        self.revision = revision
        self.weight_sha256 = weight_sha256
        self.context_window_tokens = context_window_tokens
        self._model: Any = None
        self._tokenizer: Any = None
        self._generate: Any = None
        self._sampler: Any = None
        self._closed = False
        self._metrics = BackendResourceMetrics(unloaded=True)
        self._load_ms: float | None = None

    def model_metadata(self) -> ModelMetadata:
        return ModelMetadata(
            provider=ModelProvider.GRANITE,
            model_id=self.canonical_model_id,
            revision=self.revision or "unknown",
            license="Apache-2.0",
            tokenizer_id=self.canonical_model_id,
            chat_template_hash=None,
            context_window_tokens=self.context_window_tokens,
            dtype="bf16_canonical_or_4bit_mlx",
            quantization="4bit" if "4bit" in str(self.model_path) else "auto",
            backend_name="mlx-lm",
            weight_checksum_sha256=self.weight_sha256,
            acquired_at=None,
            model_card_url=f"https://huggingface.co/{self.canonical_model_id}",
            scientifically_selected=False,
            role=ModelRole.EXPERIMENTAL,
            parameter_count=3_402_836_480,
            local_path=str(self.model_path),
            notes=(
                "Experimental Granite backend (cluster 1); not operational default.",
                "Qualification status is not stored in this module.",
                "Candidate facts only; rules engine owns scientific consequences.",
                f"MLX path (community conversion, not official IBM): {self.mlx_repo}",
                f"Configured maximum context tokens: {self.context_window_tokens} "
                "(not host-validated).",
                f"Forbidden model outputs: {sorted(MODEL_MUST_NOT_EMIT)}",
            ),
        )

    def supports_constrained_decoding(self) -> bool:
        return False

    def load(self) -> None:
        if self._model is not None:
            return
        if self._closed:
            # Allow reload after unload.
            self._closed = False
        if not self.model_path.exists():
            raise ComponentLoadError(
                f"pesi Granite assenti: {self.model_path} "
                "(eseguire scripts/models/acquire_granite.py fuori da Git)"
            )
        started = time.perf_counter()
        try:
            from mlx_lm import generate, load
            from mlx_lm.sample_utils import make_sampler
        except ImportError as exc:
            raise ComponentLoadError(
                "mlx-lm non installato; usare uv sync --extra ml (Apple Silicon)"
            ) from exc
        try:
            loaded = load(
                str(self.model_path),
                adapter_path=str(self.adapter_path) if self.adapter_path else None,
            )
        except Exception as exc:
            raise ComponentLoadError(f"caricamento Granite/MLX fallito: {exc}") from exc
        self._model = loaded[0]
        self._tokenizer = loaded[1]
        self._generate = generate
        self._sampler = make_sampler(temp=0.0)
        self._load_ms = (time.perf_counter() - started) * 1000.0
        self._metrics = BackendResourceMetrics(
            load_ms=self._load_ms,
            unloaded=False,
        )

    def unload(self) -> None:
        self._model = None
        self._tokenizer = None
        self._generate = None
        self._sampler = None
        self._closed = True
        self._metrics = BackendResourceMetrics(
            load_ms=self._load_ms,
            unloaded=True,
        )

    def reload(self) -> None:
        self.unload()
        self._closed = False
        self.load()

    def tokenize(self, text: str) -> list[int]:
        self.load()
        assert self._tokenizer is not None
        encode = getattr(self._tokenizer, "encode", None)
        if not callable(encode):
            raise GraniteBackendError("tokenizer senza encode")
        tokens = encode(text, add_special_tokens=False)
        return list(tokens)

    def apply_chat_template(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        add_generation_prompt: bool = True,
    ) -> str:
        self.load()
        assert self._tokenizer is not None
        return str(
            self._tokenizer.apply_chat_template(
                list(messages),
                tokenize=False,
                add_generation_prompt=add_generation_prompt,
            )
        )

    def _prepare_messages(self, request: GenerationRequest) -> list[dict[str, str]]:
        messages = [dict(m) for m in request.messages]
        if request.task_tag:
            tag = (
                request.task_tag
                if request.task_tag.startswith("<")
                else f"<{request.task_tag}>"
            )
            messages = [
                {
                    "role": "system",
                    "content": (
                        f"N-Truth Train A. Task tag {tag}. "
                        "Emit only candidate experimental structure as JSON. "
                        "Never emit final independent n, statistical test choice, "
                        "experiment validity, paper score, or determinability verdict."
                    ),
                },
                *messages,
            ]
        return messages

    def generate_structured(self, request: GenerationRequest) -> GenerationResult:
        want_constrained = bool(request.constrained or request.output_schema is not None)
        if want_constrained:
            raise ConstrainedDecodingUnavailable(
                "constrained decoding non incluso nel cluster 1 del backend Granite; "
                "richiedere free-decode oppure attendere il cluster constrained decoding. "
                "Nessun fallback silenzioso."
            )

        self.load()
        assert self._model is not None and self._tokenizer is not None
        assert self._generate is not None

        messages = self._prepare_messages(request)
        prompt = self.apply_chat_template(messages, add_generation_prompt=True)
        input_tokens = len(self.tokenize(prompt))
        max_tokens = int(request.max_tokens)
        if max_tokens <= 0:
            raise GraniteBackendError("max_tokens deve essere > 0 (esplicito)")
        sampling = request.sampling or SamplingConfig(temperature=request.temperature)
        temp = float(sampling.temperature)

        return self._generate_free(
            prompt=prompt,
            input_tokens=input_tokens,
            max_tokens=max_tokens,
            temperature=temp,
            stop=request.stop,
        )

    def _generate_free(
        self,
        *,
        prompt: str,
        input_tokens: int,
        max_tokens: int,
        temperature: float,
        stop: tuple[str, ...],
    ) -> GenerationResult:
        from mlx_lm.sample_utils import make_sampler

        assert self._model is not None and self._tokenizer is not None
        assert self._generate is not None
        sampler = make_sampler(temp=temperature)
        text, finish_reason, raw_meta = self._generate_with_diagnostics(
            prompt=prompt,
            max_tokens=max_tokens,
            sampler=sampler,
            stop=stop,
        )
        output_tokens = len(self.tokenize(text)) if text else 0
        terminated_by_eos = finish_reason == "stop"
        truncated = finish_reason == "length" or output_tokens >= max_tokens
        if text.count("{") > text.count("}"):
            truncated = True
        latency_ms = raw_meta.get("latency_ms")
        self._metrics = BackendResourceMetrics(
            load_ms=self._load_ms,
            last_latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            unloaded=False,
        )
        return GenerationResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            finish_reason=finish_reason,
            max_tokens=max_tokens,
            terminated_by_eos=terminated_by_eos,
            terminated_by_stop=terminated_by_eos,
            truncated=truncated,
            constrained_status="FREE_DECODE",
            raw={
                "backend": "granite-mlx",
                "mode": "free",
                "latency_ms": latency_ms,
                "mlx_library_default_max_tokens": self.MLX_LIBRARY_DEFAULT_MAX_TOKENS,
                "eos_token": getattr(self._tokenizer, "eos_token", None),
                "stop": list(stop),
                **raw_meta,
            },
        )

    def _generate_with_diagnostics(
        self,
        *,
        prompt: str,
        max_tokens: int,
        sampler: Any,
        stop: tuple[str, ...],
    ) -> tuple[str, str, dict[str, Any]]:
        started = time.perf_counter()
        finish_reason = "stop"
        peak_memory = None
        try:
            from mlx_lm.generate import stream_generate

            chunks: list[str] = []
            last_fr: str | None = None
            for response in stream_generate(
                self._model,
                self._tokenizer,
                prompt=prompt,
                max_tokens=max_tokens,
                sampler=sampler,
            ):
                chunks.append(str(getattr(response, "text", "") or ""))
                fr = getattr(response, "finish_reason", None)
                if fr is not None:
                    last_fr = str(fr)
                peak_memory = getattr(response, "peak_memory", peak_memory)
            text = "".join(chunks)
            if last_fr in {"stop", "length"}:
                finish_reason = last_fr
        except Exception:
            text = str(
                self._generate(
                    self._model,
                    self._tokenizer,
                    prompt=prompt,
                    max_tokens=max_tokens,
                    sampler=sampler,
                    verbose=False,
                )
            )
        latency_ms = (time.perf_counter() - started) * 1000.0
        out_tok = len(self.tokenize(text)) if text else 0
        if finish_reason == "stop" and out_tok >= max_tokens:
            finish_reason = "length"
        return (
            text,
            finish_reason,
            {
                "latency_ms": latency_ms,
                "peak_memory_gb": peak_memory,
                "stop_requested": list(stop),
            },
        )

    def get_resource_metrics(self) -> BackendResourceMetrics:
        return self._metrics

    def close(self) -> None:
        self.unload()


def chat_template_fingerprint(template_text: str) -> str:
    return hashlib.sha256(template_text.encode("utf-8")).hexdigest()


__all__ = [
    "GraniteBackend",
    "GraniteBackendError",
    "chat_template_fingerprint",
]
