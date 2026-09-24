"""Backend modello Train A — cluster 1 (MiniCPM primario provvisorio, ADR-0019).

Esporta solo l'interfaccia astratta, MiniCPMBackend, il backend legacy Granite,
factory e legacy Qwen. Registry, ledger e constrained decoding **non** fanno
parte di questo cluster.
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
    MINICPM_CANONICAL_MODEL_ID,
    MINICPM_MLX_REPO,
    MINICPM_MLX_REVISION,
)
from ntruth.model_backends.errors import (
    ComponentLoadError,
    ConstrainedDecodingUnavailable,
    GraniteBackendError,
    MiniCPMBackendError,
    RuntimeDevice,
)
from ntruth.model_backends.factory import create_model_backend, resolve_provider
from ntruth.model_backends.granite import GraniteBackend
from ntruth.model_backends.minicpm import MiniCPMBackend, chat_template_fingerprint

__all__ = [
    "GRANITE_CANONICAL_MODEL_ID",
    "GRANITE_MLX_REPO",
    "GRANITE_MLX_REVISION",
    "MINICPM_CANONICAL_MODEL_ID",
    "MINICPM_MLX_REPO",
    "MINICPM_MLX_REVISION",
    "MODEL_MUST_NOT_EMIT",
    "BackendResourceMetrics",
    "ComponentLoadError",
    "ConstrainedDecodingUnavailable",
    "GenerationRequest",
    "GenerationResult",
    "GraniteBackend",
    "GraniteBackendError",
    "MiniCPMBackend",
    "MiniCPMBackendError",
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
