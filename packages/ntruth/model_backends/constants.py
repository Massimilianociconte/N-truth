"""Costanti tecniche del backend (nessuno stato di qualificazione).

La qualificazione operativa vive nel registry (cluster successivo), non qui.
"""

from __future__ import annotations

# Provisional primary Train A (ADR-0019): MiniCPM5-2B, Apache-2.0.
MINICPM_CANONICAL_MODEL_ID = "openbmb/MiniCPM5-2B"
MINICPM_CANONICAL_REVISION = "12a3808a956f869c767195e9266b59c4d21d92e2"

# Official vendor MLX 4-bit (Apple Silicon bootstrap; not a community conversion).
MINICPM_MLX_REPO = "openbmb/MiniCPM5-2B-MLX"
MINICPM_MLX_REVISION = "8a9ad7539ac86281d0ac2b017ba04a5de53fe9a3"
MINICPM_MLX_WEIGHT_FILE = "model.safetensors"
MINICPM_MLX_WEIGHT_BYTES = 1_416_035_216
MINICPM_MLX_WEIGHT_SHA256 = "c207798696a4a454e7ac211b25227625466c693335941cee8904fb922f295cc1"

# Ablation arm: MiniCPM5-1B (official vendor MLX 4-bit).
MINICPM_1B_CANONICAL_MODEL_ID = "openbmb/MiniCPM5-1B"
MINICPM_1B_CANONICAL_REVISION = "87179e5c1f455ef22e6223592d2d61351b525bfc"
MINICPM_1B_MLX_REPO = "openbmb/MiniCPM5-1B-MLX"
MINICPM_1B_MLX_REVISION = "9879b18bf2928355fcdf4287635388a3665a40cb"
MINICPM_1B_MLX_WEIGHT_FILE = "model.safetensors"
MINICPM_1B_MLX_WEIGHT_BYTES = 608_026_621
MINICPM_1B_MLX_WEIGHT_SHA256 = "a23e0c5c79944a0b2cc92cb9ab79376b4dce41e2312383727e21ee43fe19cb4f"

# Relative path under repo (gitignored weights).
MINICPM_MLX_LOCAL_RELPATH = "models/local/minicpm5-2b-4bit"

# Configured maximum context from model card / config.json — not host-validated.
MINICPM_CONFIGURED_MAX_CONTEXT_TOKENS = 131_072

# Llama-standard architecture: no custom kernels; Outlines/MLX-LM load it directly.
MINICPM_ARCHITECTURE = "LlamaForCausalLM_standard_no_custom_kernels"
MINICPM_PARAMETER_COUNT = 2_516_756_480

# Profile filename for technical load config (no operational status fields).
MINICPM_MLX_PROFILE_FILENAME = "minicpm5-2b-mlx-qlora.json"

# Chat template: MiniCPM5 ChatML-style with enable_thinking flag. N-Truth renders
# with enable_thinking=false (empty think block, direct JSON); thinking stays off.
MINICPM_CHAT_TEMPLATE = "minicpm5_chatml_no_think"

# Legacy Granite 4.1 3B (ADR-0010; demoted to legacy opt-in by ADR-0019).
# Canonical Instruct checkpoint (Apache-2.0).
GRANITE_CANONICAL_MODEL_ID = "ibm-granite/granite-4.1-3b"
GRANITE_CANONICAL_REVISION = "c0650403e44e78ec0262dab1c90914c65b196c4e"

# MLX community conversion (bootstrap Apple Silicon; not official IBM).
GRANITE_MLX_REPO = "mlx-community/granite-4.1-3b-4bit"
GRANITE_MLX_REVISION = "b1b476b5a17c46b7d6cd663b4a8ed44b66720aef"
GRANITE_MLX_WEIGHT_FILE = "model.safetensors"
GRANITE_MLX_WEIGHT_BYTES = 2_127_162_429
GRANITE_MLX_WEIGHT_SHA256 = "cff9d052cc3c68ea66b3d364788eb96fca2be82868d9ad92bd968e73b125194d"

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
    "MINICPM_1B_CANONICAL_MODEL_ID",
    "MINICPM_1B_CANONICAL_REVISION",
    "MINICPM_1B_MLX_REPO",
    "MINICPM_1B_MLX_REVISION",
    "MINICPM_1B_MLX_WEIGHT_BYTES",
    "MINICPM_1B_MLX_WEIGHT_FILE",
    "MINICPM_1B_MLX_WEIGHT_SHA256",
    "MINICPM_ARCHITECTURE",
    "MINICPM_CANONICAL_MODEL_ID",
    "MINICPM_CANONICAL_REVISION",
    "MINICPM_CHAT_TEMPLATE",
    "MINICPM_CONFIGURED_MAX_CONTEXT_TOKENS",
    "MINICPM_MLX_LOCAL_RELPATH",
    "MINICPM_MLX_PROFILE_FILENAME",
    "MINICPM_MLX_REPO",
    "MINICPM_MLX_REVISION",
    "MINICPM_MLX_WEIGHT_BYTES",
    "MINICPM_MLX_WEIGHT_FILE",
    "MINICPM_MLX_WEIGHT_SHA256",
    "MINICPM_PARAMETER_COUNT",
]
