# Manifests for Granite artifacts (no weights in Git)

> **LEGACY (ADR-0019).** Granite è il braccio di confronto storico, non il
> default. Nuove evidenze MiniCPM vanno in `models/ntruth-minicpm-2b/manifests/`
> via `scripts/models/qualify_minicpm_runtime.py`. I manifest qui restano
> evidenza artifact-bound valida solo per i pesi Granite storici.

After acquisition, write JSON manifests here with:

- repository, revision
- local relative path
- weight_bytes, weight_sha256
- acquired_at
- integrity_ok

Example producer: `scripts/models/acquire_granite.py`
