# Verifiable governance and distribution workflow

`distribution-check` evaluates whether the exact artifacts of one revision may be
shared or redistributed. It is deliberately fail-closed and never performs a transfer.
The procedure below avoids fabricated IDs and placeholder checksums.

## 1. Generate a scope-bound pending template

After an analysis, generate a new file outside the repository:

```bash
uv run python scripts/create_governance_template.py \
  ./ntruth-out/runs/<run-id>/revisions/<revision> \
  --out /absolute/private/path/governance.pending.json
```

The script reads `share-readiness.json`, copies its actual asset IDs and SHA-256 values,
and writes `GovernanceRecord` objects with `status=pending` and no allowed uses. It
refuses to overwrite an existing file.

Confirm that it is structurally valid:

```bash
uv run python -c 'from pathlib import Path; from ntruth.application import DistributionGovernanceBundle; p=Path("/absolute/private/path/governance.pending.json"); b=DistributionGovernanceBundle.model_validate_json(p.read_text()); print(len(b.governance_records), "pending records valid")'
```

Running the gate with this file MUST fail with `record_not_approved`; that is the
expected regression check:

```bash
uv run ntruth distribution-check \
  ./ntruth-out/runs/<run-id>/revisions/<revision> \
  --governance /absolute/private/path/governance.pending.json \
  --action share
```

## 2. Review each asset

Do not change `asset_id` or `asset_sha256`. For every asset, a responsible reviewer must
record:

- ownership/data-controller role;
- the exact requested uses (`share` and `redistribute` are separate);
- an immutable authorization document/reference and its SHA-256;
- consent status and privacy/anonymization decision;
- grant time, expiry and revocation when applicable;
- whether it is a public third-party asset;
- restrictions and required attribution.

Compute evidence hashes from the actual local record, not from a copied example:

```bash
shasum -a 256 /absolute/private/path/authorization-record.pdf
```

An approved private asset requires at least:

```json
{
  "status": "approved",
  "allowed_uses": ["share"],
  "owner_role": "data_owner",
  "authorization_reference": "local://authorization/<immutable-id>",
  "authorization_sha256": "<sha256-of-the-actual-authorization-record>",
  "consent_status": "granted",
  "anonymization_status": "verified",
  "public_asset": false,
  "granted_at": "<timezone-aware-ISO-8601-timestamp>"
}
```

This fragment is not a complete bundle and its angle-bracket values are intentionally
invalid until replaced with evidence from the real review.

For a public third-party asset set `public_asset=true`. The bundle must then contain a
matching `LicenseManifest` with:

- the same `asset_id` and SHA-256;
- source and license-evidence URLs;
- exact SPDX identifier or canonical license URI;
- retrieval time and attribution;
- explicit requested use;
- reviewer and commercial-compatibility decision;
- `tier=tier_a` and `status=approved_tier_a` only after review.

Set the record's `license_manifest_id` to that asset ID and
`license_manifest_hash` to `LicenseManifest.manifest_hash()`. A missing or changed
manifest will be rejected.

## 3. Choose a privacy policy

### `blocked`

This is the default. Any finding blocks the operation. Use it when no documented
privacy decision exists.

### `acknowledged`

Use only after a named reviewer has examined the stand-off findings. The command
requires a non-empty, immutable local reference:

```bash
uv run ntruth distribution-check REVISION \
  --governance GOVERNANCE.json \
  --action share \
  --privacy-policy acknowledged \
  --acknowledgement-reference local://privacy-review/<immutable-id>
```

Privacy acknowledgement does not override missing governance, consent or license
permission.

### `redacted_copy`

For every scan with findings, the bundle must include exactly one `RedactionManifest`
and one `RedactedDerivativeMaterial` with the same artifact ID, field path and original
checksum. The gate recomputes the derivative checksum and scans the derivative again.
If one finding scope is missing, the checksum differs or an identifier remains, the
operation fails. When successful, authorization applies only to
`redacted_derivatives_only`, never to the originals.

The executable reference for this contract is
`tests/integration/test_prd_v3_governance_exports.py::test_redacted_copy_checksum_is_recomputed_from_exact_scanned_scope`.

## 4. Interpret the result

A successful result states the action and artifact scope and always ends with
`Nessun trasferimento eseguito`. It is evidence that the local records matched at that
moment; it is not a legal opinion and does not remain valid after a file, license,
authorization or revocation changes.

Keep governance files and authorization evidence outside Git. Re-run the gate
immediately before any separately authorized transfer.
