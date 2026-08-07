"""Backend modello Train A — cluster 1 (Granite sperimentale, non default).

Esporta solo l'interfaccia astratta, GraniteBackend, factory e legacy Qwen.
Registry, ledger e constrained decoding **non** fanno parte di questo cluster.
"""

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
    GRANITE_MLX_REPO,
    GRANITE_MLX_REVISION,
)
from ntruth.model_backends.errors import (
    ComponentLoadError,
    ConstrainedDecodingUnavailable,
    GraniteBackendError,
    RuntimeDevice,
)
from ntruth.model_backends.factory import create_model_backend, resolve_provider
from ntruth.model_backends.granite import GraniteBackend, chat_template_fingerprint

__all__ = [
    "GRANITE_CANONICAL_MODEL_ID",
    "GRANITE_MLX_REPO",
    "GRANITE_MLX_REVISION",
    "MODEL_MUST_NOT_EMIT",
    "BackendResourceMetrics",
    "ComponentLoadError",
    "ConstrainedDecodingUnavailable",
    "GenerationRequest",
    "GenerationResult",
    "GraniteBackend",
    "GraniteBackendError",
    "ModelBackend",
    "ModelMetadata",
    "ModelProvider",
    "ModelRole",
    "RuntimeDevice",
    "SamplingConfig",
    "chat_template_fingerprint",
    "create_model_backend",
    "resolve_provider",
]
