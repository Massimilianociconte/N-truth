"""Interfaccia astratta provider-agnostic per i backend modello Train A.

Il parser, il verifier, il rules engine e la UI NON devono importare librerie
specifiche di Granite, Qwen o altri vendor. Comunicano solo tramite ModelBackend.

Il modello produce esclusivamente candidate facts tracciabili; non emette n finale,
pseudoreplicazione definitiva, validita dell'esperimento, test statistico o giudizio
sul paper (PRD Train A / ADR-0002).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ModelProvider(StrEnum):
    GRANITE = "granite"
    LEGACY_QWEN = "legacy_qwen"
    GENERIC = "generic"


class ModelRole(StrEnum):
    """Ruolo dichiarato: mai scientificamente selezionato senza gold+benchmark."""

    PROVISIONAL_PRIMARY = "provisional_primary_train_a"
    BOOTSTRAP_CANDIDATE = "reproducible_bootstrap_candidate"
    ABLATION_BASE = "ablation_base_only"
    LEGACY_UNSUPPORTED = "legacy_unsupported"
    EXPERIMENTAL = "experimental_backend"


@dataclass(frozen=True, slots=True)
class ModelMetadata:
    provider: ModelProvider
    model_id: str
    revision: str
    license: str
    tokenizer_id: str
    chat_template_hash: str | None
    context_window_tokens: int
    dtype: str
    quantization: str
    backend_name: str
    weight_checksum_sha256: str | None
    acquired_at: str | None
    model_card_url: str
    # Descriptive only — not a qualification ledger status.
    scientifically_selected: bool
    role: ModelRole
    parameter_count: int | None = None
    local_path: str | None = None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SamplingConfig:
    """Parametri di campionamento espliciti (mai ereditare default server silenti)."""

    temperature: float = 0.0
    top_p: float | None = None
    seed: int | None = 0


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    """Richiesta di generazione strutturata (candidate-only)."""

    messages: Sequence[Mapping[str, str]]
    max_tokens: int = 1024
    temperature: float = 0.0
    stop: tuple[str, ...] = ()
    task_tag: str | None = None
    schema_name: str | None = None
    # Reserved for a later constrained-decoding cluster; backends must fail closed.
    output_schema: type[Any] | str | None = None
    constrained: bool = False
    sampling: SamplingConfig | None = None


@dataclass(frozen=True, slots=True)
class GenerationResult:
    text: str
    input_tokens: int
    output_tokens: str | int
    finish_reason: str
    raw: Mapping[str, Any] = field(default_factory=dict)
    max_tokens: int | None = None
    terminated_by_eos: bool = False
    terminated_by_stop: bool = False
    truncated: bool = False
    constrained_status: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.output_tokens, str):
            object.__setattr__(self, "output_tokens", int(self.output_tokens))


@dataclass(frozen=True, slots=True)
class BackendResourceMetrics:
    load_ms: float | None = None
    warmup_ms: float | None = None
    last_latency_ms: float | None = None
    peak_resident_ram_bytes: int | None = None
    swap_delta_bytes: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_hits: int = 0
    cache_evictions: int = 0
    unloaded: bool = False


class ModelBackend(ABC):
    """Contratto runtime condiviso da tutti i provider modello."""

    @abstractmethod
    def load(self) -> None:
        """Carica pesi/tokenizer in memoria."""

    @abstractmethod
    def unload(self) -> None:
        """Rilascia riferimenti e invita il backend a liberare cache se possibile."""

    def reload(self) -> None:
        """Unload seguito da load (default; sottoclassi possono sovrascrivere)."""

        self.unload()
        self.load()

    @abstractmethod
    def tokenize(self, text: str) -> list[int]:
        """Tokenizza testo grezzo; non applica chat template."""

    @abstractmethod
    def generate_structured(self, request: GenerationRequest) -> GenerationResult:
        """Genera output testuale/JSON candidato; non emette verdetti scientifici.

        Se ``request.constrained`` o ``request.output_schema`` sono impostati, il
        backend deve usare decoding vincolato o sollevare errore esplicito
        (nessun fallback silenzioso a free-decode).
        """

    @abstractmethod
    def get_resource_metrics(self) -> BackendResourceMetrics:
        """Ultima telemetria osservata (load/warmup/generate)."""

    @abstractmethod
    def supports_constrained_decoding(self) -> bool:
        """True se il backend supporta grammar/schema-constrained decoding nativo."""

    @abstractmethod
    def model_metadata(self) -> ModelMetadata:
        """Metadati immutabili del checkpoint caricato o configurato."""

    def apply_chat_template(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        add_generation_prompt: bool = True,
    ) -> str:
        """Default: non implementato; i backend concreti lo sovrascrivono."""

        raise NotImplementedError(f"{type(self).__name__} non implementa apply_chat_template")


# Output policy reminder embedded for code search / audits.
MODEL_MUST_NOT_EMIT = frozenset(
    {
        "final_independent_n",
        "definitive_pseudoreplication_verdict",
        "experiment_validity_judgement",
        "statistical_test_choice",
        "paper_quality_score",
        "determinability_verdict",
    }
)

__all__ = [
    "MODEL_MUST_NOT_EMIT",
    "BackendResourceMetrics",
    "GenerationRequest",
    "GenerationResult",
    "ModelBackend",
    "ModelMetadata",
    "ModelProvider",
    "ModelRole",
    "SamplingConfig",
]
