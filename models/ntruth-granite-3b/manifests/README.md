# Manifests for Granite artifacts (no weights in Git)

After acquisition, write JSON manifests here with:

- repository, revision
- local relative path
- weight_bytes, weight_sha256
- acquired_at
- integrity_ok

Example producer: `scripts/models/acquire_granite.py`
