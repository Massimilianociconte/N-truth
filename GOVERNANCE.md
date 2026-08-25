# N-Truth governance — PRD v8.0

N-Truth is governed as research software with separate engineering, data and
scientific authorities. Repository maintainers may merge software only after the
engineering gates pass; they cannot convert that merge into scientific validation,
training authorization or External Challenge permission.

Current status: `IMPLEMENTED_WITH_EXPLICIT_BLOCKERS`. Scientific/data readiness and
training remain HOLD.

## Decision classes

| Decision | Required authority | Repository representation |
|---|---|---|
| Software implementation | Maintainer plus code review | Commit, tests, ADR when architectural |
| Theory/rule semantic change | Theory owner plus independent scientific reviewers | New theory/rule version, clause IDs, fixtures, proof traces |
| Schema ambiguity closure | Schema owner plus affected scientific governance | Append-only decision in the Scientific Review Register |
| Data eligibility | Data/license/privacy reviewers and custodian | Content-addressed records/manifests; never inferred from location |
| Training authorization | Canonical Reality Gate v8 decision | Complete immutable pin tuple; current state HOLD |
| External Challenge use | Independent custodian/attester/scorer with separation of duties | Contamination, access and authority records; current state HOLD |
| Scientific release claim | Independent reference/evaluation evidence | Reference stability, E2E, residual and cluster-aware evidence |

## Scientific Review Register

Unresolved scientific choices are recorded in
[docs/audits/prd-v8-full-migration/SCIENTIFIC_REVIEW_REGISTER.md](docs/audits/prd-v8-full-migration/SCIENTIFIC_REVIEW_REGISTER.md).
A blocker is not closed by changing prose or making a test pass. Closure requires a
dated append-only decision, reviewer roles, rationale, affected versions and
re-derivation scope. Historical rows are not deleted.

## Change rules

- Derivation Theory, Rulebook and implementation fixtures are distinct versioned
  artifacts. A rule must name its theory clause, required/irrelevant predicates,
  positive/negative/counterfactual fixtures, proof trace and known-gap policy.
- Derived claims are never patched directly. Correct facts/evidence or register a
  `RuleChallenge`, then re-derive under explicit pins.
- PRD examples that conflict with normative text are preserved verbatim as
  expected-negative fixtures; no silent repair or implicit alias is allowed.
- PRD v7 compatibility is available only through visibly deprecated, explicitly named
  interfaces emitting `DEPRECATED_V7_ADAPTER`.
- Historical audited artifacts are immutable. Current documents may link to them but
  must label their role accurately.

## Review separation

At minimum, changes with scientific impact require software review and the relevant
domain/theory/statistical/governance review. External Challenge custodian, attester,
independent scorer, trainer, generator, model selector and release owner are distinct
roles. No self-issued JSON object or checksum constitutes authority.

## Repository and data safety

- Never commit corpus bytes, private annotations, model weights, credentials, keys or
  external challenge payloads.
- `TEST` and `EXTERNAL_CHALLENGE` are never training- or model-selection-eligible.
- Do not modify external dataset volumes as part of repository maintenance.
- Repository scanning is a detection gate, not a privacy/license/contamination
  attestation.
- No force-push to protected branches; no merge without review and green required CI.

## Release posture

A software artifact may be released as alpha when engineering gates pass. Labels such
as “scientifically validated”, “gold”, “authorized training”, “DRIVER-compliant” or
“production-ready” remain forbidden until the corresponding independent evidence
exists and Reality Gate v8 records a reviewed decision.
