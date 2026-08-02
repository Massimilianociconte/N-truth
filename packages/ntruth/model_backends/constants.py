"""Costanti tecniche del backend (nessuno stato di qualificazione).

La qualificazione operativa vive nel registry (cluster successivo), non qui.
"""

from __future__ import annotations

# Canonical Instruct checkpoint (Apache-2.0).
GRANITE_CANONICAL_MODEL_ID = "ibm-granite/granite-4.1-3b"
GRANITE_CANONICAL_REVISION = "c0650403e44e78ec0262dab1c90914c65b196c4e"

# MLX community conversion (bootstrap Apple Silicon; not official IBM).
GRANITE_MLX_REPO = "mlx-community/granite-4.1-3b-4bit"
GRANITE_MLX_REVISION = "b1b476b5a17c46b7d6cd663b4a8ed44b66720aef"
GRANITE_MLX_WEIGHT_FILE = "model.safetensors"
GRANITE_MLX_WEIGHT_BYTES = 2_127_162_429
GRANITE_MLX_WEIGHT_SHA256 = (
    "cff9d052cc3c68ea66b3d364788eb96fca2be82868d9ad92bd968e73b125194d"
)

# Relative path under repo (gitignored weights).
GRANITE_MLX_LOCAL_RELPATH = "models/local/granite-4.1-3b-4bit"

# Configured maximum context from model card / config.json — not host-validated.
GRANITE_CONFIGURED_MAX_CONTEXT_TOKENS = 131_072

# Profile filename for technical load config (no operational status fields).
GRANITE_MLX_PROFILE_FILENAME = "granite-4.1-3b-mlx.json"

__all__ = [
    "GRANITE_CANONICAL_MODEL_ID",
    "GRANITE_CANONICAL_REVISION",
    "GRANITE_CONFIGURED_MAX_CONTEXT_TOKENS",
    "GRANITE_MLX_LOCAL_RELPATH",
    "GRANITE_MLX_PROFILE_FILENAME",
    "GRANITE_MLX_REPO",
    "GRANITE_MLX_REVISION",
    "GRANITE_MLX_WEIGHT_BYTES",
    "GRANITE_MLX_WEIGHT_FILE",
    "GRANITE_MLX_WEIGHT_SHA256",
]
