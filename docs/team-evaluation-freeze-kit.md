# TEAM-EVAL-V0.1 freeze kit (mechanical sign-off gate)

Date: 2026-08-27 · Scope: CP-EVAL mechanical readiness for the
`TEAM-EVAL-V0.1` preregistration freeze.

## Purpose

`scripts/team_evaluation_freeze_gate.py` mechanizes the human sign-off
workflow declared by the header of
[`docs/team-evaluation-protocol-v0.1.md`](team-evaluation-protocol-v0.1.md):
the protocol may flip from `PREREGISTRATION_DRAFT` to
`FROZEN_PREREGISTRATION` **only** when the four required human role
attestations exist — `biostatistician-methodologist`, `wet-lab-lead`,
`annotation-lead`, `evaluation-custodian`. The gate is fail-closed and every
failure names WHO is missing; it fabricates no signature, never rewrites the
protocol markdown, and never commits, stages or pushes anything.

## Non-goal (explicit)

This kit produces **no** science claims and no evidence. Signing humans remain
an external prerequisite per the protocol header: all four signatures exist
outside this repository and only their initials-token attestations (pattern
`^[A-Z]{2,4}$`) are ever stored in-repo — personal names and emails stay
OFF-repo forever. Until the four attestations exist, nothing is frozen and the
protocol stays `PREREGISTRATION_DRAFT`; that state is correct and must remain
visible in every artifact the kit touches.

## Record shape (schema mapping vs packages/ntruth/team_evaluation/models.py)

`TeamEvaluationProtocolRecord` is declared with `extra="forbid"`
(`packages/ntruth/team_evaluation/models.py:26`), so freeze metadata cannot be
flattened into the record body without breaking the package contract.
Therefore `emit-frozen` writes a versioned envelope:

```json
{
  "attestations": ["… verified entries, sorted by role_token …"],
  "attestations_digest": "<sha256 over the canonically sorted attestations array>",
  "bundle_kind": "team-eval-freeze-record",
  "frozen_at": "…",
  "note": "Status transition recorded here; the protocol markdown is untouched. …",
  "protocol_id": "TEAM-EVAL-V0.1",
  "record": { "…original record fields preserved verbatim…", "status": "FROZEN_PREREGISTRATION" },
  "schema_version": "9.0.0",
  "source_protocol_sha256": "<sha256 of docs/team-evaluation-protocol-v0.1.md bytes>"
}
```

Mapping decisions:

1. `envelope["record"]` validates directly via
   `TeamEvaluationProtocolRecord.model_validate` — it contains exactly the
   model's fields, with `status` flipped to the existing enum member
   `PreregistrationStatus.FROZEN_PREREGISTRATION`
   (`models.py:34-36`). All other original field values are preserved
   byte-for-byte from the draft, including `data_collection_started: false`.
2. `emit-frozen` refuses drafts claiming `data_collection_started != false`
   (anti-overclaim, protocol §9): freezing must not become a vehicle for
   pretending data exists.
3. Hash canon mirrors
   `ntruth.derivation_theory.loader.canonical_checksum`
   (`json.dumps(..., ensure_ascii=False, sort_keys=True,
   separators=(",", ":"))`, UTF-8) wherever JSON is hashed; raw file bytes use
   plain sha256 hexdigest.

## CLI usage

```console
# 1) Scaffold a ready-to-fill attestation bundle (deterministic output):
uv run python scripts/team_evaluation_freeze_gate.py prepare-record > \
    data_manifests/team-eval-freeze-attestations.json

# 2) Fill one entry per role; initials only; dates >= 2026-08-25 (draft date);
#    statement_ref quotes the frozen-commitment sentence ids from the header.

# 3) Verify (default --record data_manifests/team-eval-freeze-attestations.json):
uv run python scripts/team_evaluation_freeze_gate.py verify

# 4) Emit the frozen versioned record (never touches the markdown):
uv run python scripts/team_evaluation_freeze_gate.py emit-frozen \
    --draft-record path/to/draft-record.json --out path/to/frozen-record.json
```

Success prints one JSON object with `"status": "PASS"`; refusals print
`{"diagnostics": […], "status": "FAIL"}` on stdout and exit `1`.

### Failure demos (observed outputs)

Missing bundle file:

```json
{"diagnostics": ["freeze blocked: no attestations provided (expected bundle file not found: data_manifests/team-eval-freeze-attestations.json). Signatures from four humans are still missing: biostatistician-methodologist, wet-lab-lead, annotation-lead, evaluation-custodian. Run prepare-record to obtain a scaffold."], "status": "FAIL"}
```

Three-of-four roles signed (`evaluation-custodian` missing):

```json
{"diagnostics": ["freeze blocked: no valid attestation coverage for 1 human role attestation: evaluation-custodian. All four role tokens are required exactly once (biostatistician-methodologist, wet-lab-lead, annotation-lead, evaluation-custodian)."], "status": "FAIL"}
```

Other fail-closed refusals: duplicate role token ("attests twice"), duplicate
signer ("signs two roles … the four signers must be distinct"), non-conforming
or personal-looking initials fields, signing dates before `2026-08-25`,
stale bundles whose pinned `protocol_sha256` differs from the current
markdown bytes ("stale or deviated bundle … Re-run prepare-record and
re-sign."), post-verify drift ("refusing to emit: the working-tree protocol
bytes deviate from the attested bundle … Any change is a preregistered
deviation needing separate documentation."), overwrite refusal without
`--force`.

## CP-EVAL relationship

This kit satisfies the mechanical-readiness half of the CP-EVAL gap "frozen
versioned deliverable": the script, its tests and this document are listed as
evidence under `current_evidence.team_evaluation` in
[`contracts/cp-eval.yaml`](../contracts/cp-eval.yaml). The actual freeze
remains blocked pending four humans, and
`contracts/cp-eval.yaml:known_gaps` says so explicitly. SRR/report-policy
statements elsewhere in the repository are unchanged by this kit; no
scientific validation status moved (`NOT_STARTED` stands).

## Adoption of an emitted frozen record (human governance step)

The kit records the status transition inside the emitted record file and does
not modify `docs/team-evaluation-protocol-v0.1.md`. Adopting the flip upstream
means maintainers later append one dated deviation block noting the status
field change — in a new minor-version protocol file or an appendix, per repo
conventions they choose at that time. After adoption, any further change to
the frozen content is a preregistered deviation needing separate
documentation (protocol header).

## Anti-overclaim echo

No data has been collected; no results exist. This protocol produces no
evidence: while `status` remains `PREREGISTRATION_DRAFT` and
`data_collection_started = false`, no number, internal benchmark or synthetic
smoke test constitutes an H/A/H+A team result. The scientific validation of
the project formally remains `NOT_STARTED` (SCIENTIFIC_STATUS_PIN) with
training and external challenge in HOLD. The emitted frozen record keeps
`data_collection_started = false`; the gate refuses otherwise.
