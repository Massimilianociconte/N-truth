"""Backend modello Train A — cluster 1+2 (Granite experimental + runtime registry).

Factory default remains legacy_qwen. Registry publishes artifact-bound qualification.
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
from ntruth.model_backends.registry import (
    ARTIFACT_FINGERPRINT_KEYS,
    MigrationStatus,
    ModelRegistryError,
    RuntimeQualificationStatus,
    ScientificValidationStatus,
    artifact_fingerprint,
    canonical_fingerprint_hash,
    claim_gates,
    load_registry,
    qualification_status,
    verify_public_chain,
)

__all__ = [
    "ARTIFACT_FINGERPRINT_KEYS",
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
    "MigrationStatus",
    "ModelBackend",
    "ModelMetadata",
    "ModelProvider",
    "ModelRegistryError",
    "ModelRole",
    "RuntimeDevice",
    "RuntimeQualificationStatus",
    "SamplingConfig",
    "ScientificValidationStatus",
    "artifact_fingerprint",
    "canonical_fingerprint_hash",
    "chat_template_fingerprint",
    "claim_gates",
    "create_model_backend",
    "load_registry",
    "qualification_status",
    "resolve_provider",
    "verify_public_chain",
]
