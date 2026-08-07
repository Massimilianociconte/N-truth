# Conversione e distribuzione Granite 4.1 3B

## Canonical (Safetensors)

```text
ibm-granite/granite-4.1-3b   # Instruct (default)
ibm-granite/granite-4.1-3b-base  # ablation only
```

Acquisizione Instruct (Transformers / training server):

```bash
huggingface-cli download ibm-granite/granite-4.1-3b \
  --local-dir models/ntruth-granite-3b/canonical/instruct
```

## MLX (macOS Apple Silicon)

> **Conversione community, non artefatto ufficiale IBM.**  
> Repository: `mlx-community/granite-4.1-3b-4bit` (convertito con MLX-LM).

Bootstrap 4-bit community (checksum nel profilo e report di migrazione):

| Campo | Valore |
|---|---|
| file | `model.safetensors` |
| bytes | 2127162429 |
| SHA-256 | `cff9d052cc3c68ea66b3d364788eb96fca2be82868d9ad92bd968e73b125194d` |
| revision | `b1b476b5a17c46b7d6cd663b4a8ed44b66720aef` |

```bash
uv run python scripts/models/acquire_granite.py --confirm-license-and-download
```

Converte da canonical con mlx-lm (se si vuole riprodurre la quantizzazione):

```bash
python -m mlx_lm convert \
  --hf-path ibm-granite/granite-4.1-3b \
  --mlx-path models/ntruth-granite-3b/mlx/4bit \
  -q
```

## GGUF (Windows / Linux / Metal llama.cpp)

Ufficiale IBM:

```bash
huggingface-cli download ibm-granite/granite-4.1-3b-GGUF \
  --include '*Q4_K_M*' \
  --local-dir models/ntruth-granite-3b/gguf/Q4_K_M
```

Analogamente `Q5_K_M`. Non committare i binari: solo manifest/checksum.

## Layout atteso (git-ignored weights)

```text
models/ntruth-granite-3b/
├── canonical/
├── adapters/
├── gguf/Q4_K_M/  Q5_K_M/
├── mlx/4bit/
└── manifests/
models/local/granite-4.1-3b-4bit/   # path usato dal profilo MLX
```
