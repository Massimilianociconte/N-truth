"""Backend Qwen — percorso default esistente fino alla promozione Granite (cluster 2+).

In cluster 1 la factory lo istanzia come default. Non è scientificamente selezionato.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ntruth.model_backends.base import (
    BackendResourceMetrics,
    GenerationRequest,
    GenerationResult,
    ModelBackend,
    ModelMetadata,
    ModelProvider,
    ModelRole,
)
from ntruth.model_backends.errors import ComponentLoadError, RuntimeDevice


class LegacyQwenBackend(ModelBackend):
    """Backend MLX per snapshot Qwen (percorso esistente)."""

    def __init__(
        self,
        *,
        model_path: Path,
        adapter_path: Path | None = None,
        device: RuntimeDevice = RuntimeDevice.METAL,
        max_tokens: int = 1024,
        enabled: bool = True,
    ) -> None:
        if not enabled:
            raise RuntimeError(
                "LegacyQwenBackend rifiutato: enabled=False "
                "(in cluster 1 il default Qwen usa enabled=True)."
            )
        self.model_path = Path(model_path)
        self.adapter_path = Path(adapter_path) if adapter_path is not None else None
        self.device = device
        self.max_tokens = max_tokens
        self._closed = False
        self._model: Any = None
        self._tokenizer: Any = None
        self._generate: Any = None
        self._metrics = BackendResourceMetrics(unloaded=True)

    def model_metadata(self) -> ModelMetadata:
        return ModelMetadata(
            provider=ModelProvider.LEGACY_QWEN,
            model_id="Qwen/Qwen3-4B-Instruct-2507",
            revision="unknown",
            license="see upstream model card",
            tokenizer_id="Qwen/Qwen3-4B-Instruct-2507",
            chat_template_hash=None,
            context_window_tokens=32_768,
            dtype="4bit_mlx",
            quantization="4bit",
            backend_name="mlx-lm",
            weight_checksum_sha256=None,
            acquired_at=None,
            model_card_url="https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507",
            scientifically_selected=False,
            role=ModelRole.BOOTSTRAP_CANDIDATE,
            local_path=str(self.model_path),
            notes=(
                "Existing MLX bootstrap path; not scientifically selected.",
                "Candidate facts only.",
            ),
        )

    def supports_constrained_decoding(self) -> bool:
        return False

    def load(self) -> None:
        if self._model is not None:
            return
        if self._closed:
            self._closed = False
        if not self.model_path.exists():
            raise ComponentLoadError(f"pesi Qwen assenti: {self.model_path}")
        try:
            from mlx_lm import generate, load
        except ImportError as exc:
            raise ComponentLoadError("mlx-lm non installato") from exc
        try:
            loaded = load(
                str(self.model_path),
                adapter_path=str(self.adapter_path) if self.adapter_path else None,
            )
        except Exception as exc:
            raise ComponentLoadError(f"caricamento legacy Qwen fallito: {exc}") from exc
        self._model = loaded[0]
        self._tokenizer = loaded[1]
        self._generate = generate
        self._metrics = BackendResourceMetrics(unloaded=False)

    def unload(self) -> None:
        self._model = None
        self._tokenizer = None
        self._generate = None
        self._closed = True
        self._metrics = BackendResourceMetrics(unloaded=True)

    def reload(self) -> None:
        self.unload()
        self._closed = False
        self.load()

    def tokenize(self, text: str) -> list[int]:
        self.load()
        assert self._tokenizer is not None
        encode = getattr(self._tokenizer, "encode", None)
        if not callable(encode):
            raise RuntimeError("tokenizer senza encode")
        return list(encode(text, add_special_tokens=False))

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

    def generate_structured(self, request: GenerationRequest) -> GenerationResult:
        if request.constrained or request.output_schema is not None:
            raise RuntimeError(
                "LegacyQwenBackend cluster 1: constrained decoding non supportato "
                "(fail-closed, nessun fallback silenzioso)"
            )
        self.load()
        assert self._model is not None and self._tokenizer is not None
        assert self._generate is not None
        from mlx_lm.sample_utils import make_sampler

        prompt = self.apply_chat_template(request.messages, add_generation_prompt=True)
        input_tokens = len(self.tokenize(prompt))
        max_tokens = int(request.max_tokens)
        sampler = make_sampler(temp=float(request.temperature))
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
        output_tokens = len(self.tokenize(text)) if text else 0
        return GenerationResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            finish_reason="stop",
            max_tokens=max_tokens,
            constrained_status="FREE_DECODE",
            raw={"backend": "legacy-qwen-mlx", "mode": "free"},
        )

    def get_resource_metrics(self) -> BackendResourceMetrics:
        return self._metrics


__all__ = ["LegacyQwenBackend"]
