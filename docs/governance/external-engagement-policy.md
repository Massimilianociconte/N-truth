# External engagement policy (public)

**Version:** 0.1
**Updated:** 2026-08-03

## Purpose

Define how N-Truth records scientific contacts, potential data offers and
organisational discussions **without** overstating relationships or leaking
private correspondence.

## Relationship classes

| Class | Meaning |
|-------|---------|
| `CONTACT` | Person or organisation informed of the project; no agreed contribution |
| `POTENTIAL_CONTRIBUTOR` | Possible future data or advice; no formal commitment |
| `FORMAL_PARTNER` | Written agreement only |

Do **not** use the words partner, collaboration agreement, or endorsement in
public docs unless `commitment_status=FORMAL_PARTNER` and a written agreement
exists.

## What may appear in Git

- Names and organisations already public in scientific context
- High-level engagement and commitment status
- Candidate dataset roles and hard holds (`training_eligible=false`, etc.)
- Public notes without quoting private email text

## What must never appear in Git

- Email addresses, phone numbers, postal addresses
- Full correspondence or message excerpts
- Tokens, attachments, or access credentials
- Claims of formal partnership without written basis
- Unauthorised dataset details that a contact has not cleared for public note

## Private registry

Private contact details and correspondence metadata (if any) live only at:

```text
/Volumes/FLASH128/N-Truth-Private/collaboration-registry.private.yaml
```

That path is outside the repository and is Git-ignored. Agents and developers
must not copy private fields into commits, issues, or PR bodies.

## Data candidates

External datasets listed under `data_manifests/external-source-candidates.yaml`
default to:

- not received / not released until proven otherwise
- fail-closed licence and evaluation flags
- no training or development without a written partition and use decision

Lazic-related material remains `ROLE_DECISION_PENDING` / `OFFERED_IN_PRINCIPLE_DETAILS_PENDING`
under PRD v7 §14.4 until a written profile-relative role is agreed **before** full
label access. It is not default EXTERNAL_CHALLENGE and is not in vitro gold.

NC3Rs ARRIVE checker data remains `AUXILIARY_CANDIDATE` / `ANNOUNCED_NOT_RELEASED`
until released and reviewed; default use is reporting/evidence extraction only.
It must not be treated as experimental-unit or pseudoreplication gold.
No NC3Rs partnership, approval or endorsement is claimed.

Historical audit labels use `LEGACY_WS_B` / `LEGACY_WS_C` and must not be silently
reinterpreted as PRD v7 Workstreams A–D (`V7_WS_*`).
