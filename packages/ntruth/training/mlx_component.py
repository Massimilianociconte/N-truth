"""Adapter MLX che implementa ``RuntimeComponent`` (ADR-0003: in training/, non nel core).

Le importazioni MLX restano lazy nel costruttore/metodi cosi la definizione del
modulo resta importabile su Linux CI senza ``mlx``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ntruth.runtime_resources.manager import ComponentLoadError, ComponentResult
from ntruth.runtime_resources.schema import RuntimeDevice


def _apply_device_preference(device: RuntimeDevice) -> None:
    """Imposta un hint di device MLX se disponibile, senza interrompere il load."""

    try:
        import mlx.core as mx
    except ImportError:
        return
    try:
        if device is RuntimeDevice.CPU and hasattr(mx, "cpu"):
            mx.set_default_device(mx.cpu)
        elif device is RuntimeDevice.METAL and hasattr(mx, "gpu"):
            mx.set_default_device(mx.gpu)
    except Exception:
        # Preferenza non vincolante: MLX sceglie il default della piattaforma.
        return


def _render_chat_prompt(tokenizer: Any, messages: list[dict[str, Any]]) -> str:
    """Chat template provider-agnostic (Granite role tags; no Qwen thinking flags)."""

    return str(
        tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
    )


def _estimate_output_tokens(tokenizer: Any, text: str) -> int:
    if tokenizer is not None:
        encode = getattr(tokenizer, "encode", None)
        if callable(encode):
            try:
                tokens = encode(text, add_special_tokens=False)
                return max(0, len(tokens))
            except Exception:
                pass
    return max(0, len(text) // 4)


class MLXGenerateComponent:
    """Componente di generazione MLX-LM (default Granite) con load lazy e release.

    Preferisce ``GraniteBackend`` quando il path/modello e compatibile; resta un
    adapter RuntimeComponent generico senza importare token Qwen.
    """

    def __init__(
        self,
        *,
        model_path: Path,
        adapter_path: Path | None,
        device: RuntimeDevice,
        max_tokens: int = 1024,
        profile: dict[str, Any] | None = None,
    ) -> None:
        if max_tokens < 1:
            raise ValueError("max_tokens deve essere positivo")
        self.model_path = Path(model_path)
        self.adapter_path = Path(adapter_path) if adapter_path is not None else None
        self.device = device
        self.max_tokens = max_tokens
        self._closed = False
        self._model: Any = None
        self._tokenizer: Any = None
        self._generate: Any = None
        self._sampler: Any = None
        self._backend: Any = None

        # Percorso preferito: backend Granite astratto.
        try:
            from ntruth.model_backends.factory import create_model_backend

            self._backend = create_model_backend(
                model_path=self.model_path,
                adapter_path=self.adapter_path,
                device=device,
                max_tokens=max_tokens,
                profile=profile,
                allow_legacy=False,
            )
            self._backend.load()
            return
        except Exception:
            self._backend = None

        try:
            from mlx_lm import generate, load
            from mlx_lm.sample_utils import make_sampler
        except ImportError as exc:
            raise ComponentLoadError(
                "mlx-lm non installato; usare uv sync --extra ml"
            ) from exc

        _apply_device_preference(device)
        try:
            loaded = load(
                str(self.model_path),
                adapter_path=str(self.adapter_path) if self.adapter_path else None,
            )
        except Exception as exc:
            raise ComponentLoadError(f"caricamento MLX fallito: {exc}") from exc
        self._model = loaded[0]
        self._tokenizer = loaded[1]
        self._generate = generate
        self._sampler = make_sampler(temp=0.0)

    def run(self, payload: object, *, context_window_tokens: int) -> ComponentResult:
        if self._closed:
            raise RuntimeError("MLXGenerateComponent gia chiuso")
        if context_window_tokens < 1:
            raise ValueError("context_window_tokens deve essere positivo")

        if self._backend is not None:
            return self._backend.run(payload, context_window_tokens=context_window_tokens)

        if self._model is None or self._tokenizer is None or self._generate is None:
            raise RuntimeError("MLXGenerateComponent non caricato")
        prompt = self._payload_to_prompt(payload)
        max_tokens = min(self.max_tokens, max(1, context_window_tokens))
        raw = self._generate(
            self._model,
            self._tokenizer,
            prompt=prompt,
            max_tokens=max_tokens,
            sampler=self._sampler,
            verbose=False,
        )
        text = str(raw)
        return ComponentResult(
            value=text,
            output_tokens=_estimate_output_tokens(self._tokenizer, text),
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._backend is not None:
            self._backend.close()
            self._backend = None
        self._model = None
        self._tokenizer = None
        self._generate = None
        self._sampler = None
        try:
            import mlx.core as mx

            clear = getattr(mx, "clear_cache", None)
            if callable(clear):
                clear()
        except Exception:
            return

    def _payload_to_prompt(self, payload: object) -> str:
        if isinstance(payload, str):
            return payload
        if not isinstance(payload, dict):
            raise TypeError(
                "payload MLX deve essere str o dict con prompt/messages, "
                f"ricevuto {type(payload).__name__}"
            )
        prompt = payload.get("prompt")
        if isinstance(prompt, str) and prompt:
            return prompt
        messages = payload.get("messages")
        if isinstance(messages, list) and messages:
            normalized: list[dict[str, Any]] = []
            for item in messages:
                if not isinstance(item, dict):
                    raise TypeError("messages deve contenere oggetti dict")
                normalized.append(dict(item))
            return _render_chat_prompt(self._tokenizer, normalized)
        raise ValueError("payload MLX privo di prompt o messages utilizzabili")
