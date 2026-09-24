#!/usr/bin/env python3
"""Fail-closed mechanical freeze-kit for TEAM-EVAL-V0.1 (CP-EVAL mechanical readiness).

Mechanizes the sign-off workflow declared by the header of
docs/team-evaluation-protocol-v0.1.md: the freeze can flip only from
PREREGISTRATION_DRAFT to FROZEN_PREREGISTRATION, and only when all FOUR human
role attestations exist (biostatistician-methodologist, wet-lab-lead,
annotation-lead, evaluation-custodian). The kit fabricates nothing: every
missing human blocks the freeze with a message naming WHO is missing. It never
rewrites the protocol markdown; the status transition lives in the emitted
versioned record, and adopting it upstream is a human governance step.

Subcommands:
  prepare-record  Emit a ready-to-fill attestation bundle scaffold (stdout),
                  pinning the SHA-256 of the current protocol markdown.
  verify          Validate an attestation bundle (exactly-once coverage of the
                  four roles, initials-only identities, dates >= draft date,
                  protocol hash pinning). Absent/partial bundles fail closed
                  naming the missing signers.
  emit-frozen     Verify, then emit the frozen versioned record: the original
                  record fields are preserved, ``status`` flips to
                  FROZEN_PREREGISTRATION, and the envelope carries frozen_at,
                  the attestations digest and source_protocol_sha256. Refuses
                  overwrite without --force and refuses whenever the
                  working-tree protocol bytes deviate from the attested hash.

Structured JSON findings/exit-code style mirrors the sibling scripts under
scripts/. Exit codes: 0 pass, 1 gate refusal, 2 CLI misuse.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

PROTOCOL_PATH = Path("docs/team-evaluation-protocol-v0.1.md")
DEFAULT_BUNDLE_PATH = Path("data_manifests/team-eval-freeze-attestations.json")
DRAFT_RECORD_HELP = (
    "path to the filled TeamEvaluationProtocolRecord draft JSON "
    "(schema_version 9.0.0, produced per packages/ntruth/team_evaluation/models.py)"
)

SCHEMA_VERSION = "9.0.0"
PROTOCOL_ID = "TEAM-EVAL-V0.1"
DRAFT_STATUS = "PREREGISTRATION_DRAFT"
FROZEN_STATUS = "FROZEN_PREREGISTRATION"
BUNDLE_KIND = "team-eval-freeze-attestations"
FREEZE_RECORD_KIND = "team-eval-freeze-record"

# Draft v0.1 was committed on 2026-08-25 (commit cb270e3). The date is pinned
# so the gate stays deterministic offline; signatures predating the protocol
# draft are structurally impossible and fail closed.
PROTOCOL_DRAFT_DATE = "2026-08-25"

ROLE_TOKENS: tuple[str, ...] = (
    "biostatistician-methodologist",
    "wet-lab-lead",
    "annotation-lead",
    "evaluation-custodian",
)

INITIALS_RE = re.compile(r"^[A-Z]{2,4}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ATTESTATION_ROLE_LABELS = "one of " + ", ".join(ROLE_TOKENS)

INSTRUCTIONS: tuple[str, ...] = (
    "Fill one attestation entry per required role token; every entry is a HUMAN "
    f"sign-off ({', '.join(ROLE_TOKENS)}). The kit fabricates no signature and the "
    "freeze stays blocked until all four humans attest.",
    "signed_name_initials must match ^[A-Z]{2,4}$: initials only. Personal names and "
    "email addresses must never enter the repository (same owner-role discipline as "
    "the contract packages).",
    "attested_at is the human signing date (YYYY-MM-DD) and cannot predate the "
    f"protocol draft date {PROTOCOL_DRAFT_DATE}.",
    "statement_ref quotes the frozen-commitment sentence identifiers from the header "
    "of docs/team-evaluation-protocol-v0.1.md that the signer attests.",
    "Save the completed bundle where maintainers choose custody (default "
    f"{DEFAULT_BUNDLE_PATH}). The kit never commits, stages or pushes anything.",
    "If docs/team-evaluation-protocol-v0.1.md changes by even one byte, the pinned "
    "protocol_sha256 stops matching and the gate fails closed; regenerate the "
    "bundle via prepare-record.",
    "After verify passes, emit-frozen records the FROZEN_PREREGISTRATION transition "
    "in a NEW versioned record file. It never edits the protocol markdown: adopting "
    "the flipped status upstream (new minor-version file or appendix) is a dated, "
    "human-owned governance decision per the conventions maintainers choose.",
    "Nothing here authorizes any claim: data_collection_started stays false and "
    "scientific validation remains NOT_STARTED (anti-overclaim, protocol section 9).",
)


class FreezeGateError(ValueError):
    """A freeze-gate precondition failed; the freeze stays blocked."""


@dataclass(frozen=True)
class VerifiedBundle:
    """Output of a passing verify: the trusted attestation state."""

    payload: dict[str, Any]
    attestations: tuple[dict[str, Any], ...]
    protocol_sha256: str
    attestations_digest: str


def sha256_of_bytes(data: bytes) -> str:
    """Plain sha256 hexdigest over raw file bytes."""
    return hashlib.sha256(data).hexdigest()


def canonical_json_blob(payload: Any) -> str:
    """Recipe identical to ntruth.derivation_theory.loader.canonical_checksum."""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def attestations_digest(
    attestations: Sequence[Mapping[str, Any]],
) -> str:
    """sha256 over the attestations array canonically sorted by role_token."""
    ordered = sorted((dict(item) for item in attestations), key=lambda item: item["role_token"])
    return sha256_of_bytes(canonical_json_blob(ordered).encode("utf-8"))


def read_protocol_bytes(protocol_path: Path) -> bytes:
    try:
        return protocol_path.read_bytes()
    except OSError as exc:
        msg = f"cannot read protocol file {protocol_path}: {exc}"
        raise FreezeGateError(msg) from exc


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        msg = f"cannot read {path}: {exc}"
        raise FreezeGateError(msg) from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        msg = f"{path} is not valid JSON: {exc}"
        raise FreezeGateError(msg) from exc
    if not isinstance(payload, dict):
        msg = f"{path} must contain a JSON object at the top level"
        raise FreezeGateError(msg)
    return payload


def _reject_unknown_keys(container: Mapping[str, Any], allowed: frozenset[str], label: str) -> None:
    unknown = sorted(set(container) - allowed)
    if unknown:
        msg = f"{label} contains unsupported fields: {', '.join(unknown)}"
        raise FreezeGateError(msg)


def _require_str(container: Mapping[str, Any], key: str, label: str) -> str:
    value = container.get(key)
    if not isinstance(value, str) or not value.strip():
        msg = f"{label}.{key} must be a non-empty string"
        raise FreezeGateError(msg)
    return value


def build_scaffold(protocol_sha256: str) -> dict[str, Any]:
    """Ready-to-fill attestation bundle scaffold (deterministic, sorted keys)."""
    return {
        "_instructions": list(INSTRUCTIONS),
        "attestations": [
            {
                "attested_at": "",
                "role_token": role_token,
                "signed_name_initials": "",
                "statement_ref": "",
            }
            for role_token in ROLE_TOKENS
        ],
        "bundle": BUNDLE_KIND,
        "protocol_id": PROTOCOL_ID,
        "protocol_sha256": protocol_sha256,
        "schema_version": SCHEMA_VERSION,
        "status": DRAFT_STATUS,
    }


def prepare_scaffold(protocol_path: Path) -> dict[str, Any]:
    return build_scaffold(sha256_of_bytes(read_protocol_bytes(protocol_path)))


def verify_attestation_payload(
    payload: Any,
    *,
    expected_protocol_sha256: str,
    origin: str,
) -> VerifiedBundle:
    """Strictly validate a parsed attestation bundle (fail-closed)."""
    if not isinstance(payload, dict):
        msg = f"{origin}: attestation bundle must be a JSON object"
        raise FreezeGateError(msg)
    allowed_keys = frozenset({"_instructions"}) | {
        "attestations",
        "bundle",
        "protocol_id",
        "protocol_sha256",
        "schema_version",
        "status",
    }
    _reject_unknown_keys(payload, allowed_keys, origin)
    if payload.get("bundle") != BUNDLE_KIND:
        msg = f"{origin}: field bundle must be {BUNDLE_KIND!r}"
        raise FreezeGateError(msg)
    if payload.get("schema_version") != SCHEMA_VERSION:
        msg = f"{origin}: field schema_version must be {SCHEMA_VERSION!r}"
        raise FreezeGateError(msg)
    if payload.get("protocol_id") != PROTOCOL_ID:
        msg = f"{origin}: field protocol_id must be {PROTOCOL_ID!r}"
        raise FreezeGateError(msg)
    status = payload.get("status")
    if status is not None and status != DRAFT_STATUS:
        msg = (
            f"{origin}: field status must be {DRAFT_STATUS!r} or absent; got {status!r}. "
            "The FROZEN_PREREGISTRATION transition belongs to emitted records only."
        )
        raise FreezeGateError(msg)
    instructions = payload.get("_instructions")
    if instructions is not None and (
        not isinstance(instructions, list)
        or any(not isinstance(item, str) or not item.strip() for item in instructions)
    ):
        msg = f"{origin}._instructions must be a list of non-empty strings"
        raise FreezeGateError(msg)

    pinned = _require_str(payload, "protocol_sha256", origin)
    if SHA256_RE.fullmatch(pinned) is None:
        msg = (
            f"{origin}.protocol_sha256 must be a lowercase 64-hex sha256 "
            f"(got {pinned!r}); re-run prepare-record"
        )
        raise FreezeGateError(msg)
    if pinned != expected_protocol_sha256:
        msg = (
            f"{origin}: stale or deviated bundle. It pins {pinned}, but the "
            f"current {PROTOCOL_PATH.as_posix()} bytes hash to "
            f"{expected_protocol_sha256}. Re-run prepare-record and re-sign."
        )
        raise FreezeGateError(msg)

    raw_attestations = payload.get("attestations")
    if not isinstance(raw_attestations, list):
        msg = f"{origin}.attestations must be a list of attestation objects"
        raise FreezeGateError(msg)
    diagnostics: list[str] = []
    seen_roles: dict[str, int] = {}
    seen_signers: dict[str, str] = {}
    cleaned: list[dict[str, Any]] = []
    for index, entry in enumerate(raw_attestations):
        label = f"{origin}.attestations[{index}]"
        if not isinstance(entry, dict):
            diagnostics.append(f"{label} must be a JSON object")
            continue
        _entry_diagnostics(entry, index, label, diagnostics, seen_roles, seen_signers)
        cleaned.append(
            {
                "attested_at": entry.get("attested_at"),
                "role_token": entry.get("role_token"),
                "signed_name_initials": entry.get("signed_name_initials"),
                "statement_ref": entry.get("statement_ref"),
            }
        )
    if diagnostics:
        raise FreezeGateError("freeze blocked:\n" + "\n".join(f"- {line}" for line in diagnostics))

    missing_roles = sorted(set(ROLE_TOKENS) - seen_roles.keys())
    if missing_roles:
        who = ", ".join(missing_roles)
        total_missing = len(missing_roles)
        plural = "role attestations" if total_missing > 1 else "role attestation"
        msg = (
            f"freeze blocked: no valid attestation coverage for {total_missing} human "
            f"{plural}: {who}. All four role tokens are required exactly once "
            f"({', '.join(ROLE_TOKENS)})."
        )
        raise FreezeGateError(msg)

    return VerifiedBundle(
        payload=payload,
        attestations=tuple(cleaned),
        protocol_sha256=pinned,
        attestations_digest=attestations_digest(cleaned),
    )


def _entry_diagnostics(
    entry: Mapping[str, Any],
    index: int,
    label: str,
    diagnostics: list[str],
    seen_roles: dict[str, int],
    seen_signers: dict[str, str],
) -> None:
    # Every finding names the offending role token too, so the failure output
    # always says WHO the gate is waiting for.
    role_context = f"{label} (role {entry.get('role_token')!r})"
    allowed = frozenset({"attested_at", "role_token", "signed_name_initials", "statement_ref"})
    unknown = sorted(set(entry) - allowed)
    if unknown:
        diagnostics.append(f"{role_context} contains unsupported fields: {', '.join(unknown)}")
        return
    role_token = entry.get("role_token")
    if role_token not in ROLE_TOKENS:
        diagnostics.append(
            f"{role_context}: field role_token must be {ATTESTATION_ROLE_LABELS}; "
            f"got {role_token!r}"
        )
    elif role_token in seen_roles:
        diagnostics.append(
            f"{role_context} attests twice "
            f"(first seen in attestations[{seen_roles[role_token]}]); "
            "each role token must appear exactly once"
        )
    else:
        seen_roles[str(role_token)] = index

    initials = entry.get("signed_name_initials")
    if isinstance(initials, str) and INITIALS_RE.fullmatch(initials):
        previous_owner = seen_signers.get(initials)
        if previous_owner is not None:
            diagnostics.append(
                f"{role_context}: signed_name_initials {initials!r} signs two roles "
                f"({previous_owner} and {role_token!r}); "
                "the four signers must be distinct"
            )
        elif isinstance(role_token, str):
            seen_signers[initials] = role_token
    else:
        shown = "" if not isinstance(initials, str) else initials
        diagnostics.append(
            f"{role_context}: field signed_name_initials must match ^[A-Z]{{2,4}}$ "
            "(initials token only; personal names and emails stay OFF-repo forever); "
            f"got {shown!r}"
        )

    attested_at = entry.get("attested_at")
    if not isinstance(attested_at, str) or DATE_RE.fullmatch(attested_at) is None:
        diagnostics.append(
            f"{role_context}: field attested_at must be a calendar date formatted "
            f"YYYY-MM-DD; got {attested_at!r}"
        )
    elif attested_at < PROTOCOL_DRAFT_DATE:
        diagnostics.append(
            f"{role_context}: field attested_at {attested_at} predates the protocol "
            f"draft date {PROTOCOL_DRAFT_DATE}; a signature cannot precede the "
            "protocol it freezes"
        )

    statement_ref = entry.get("statement_ref")
    if not isinstance(statement_ref, str) or not statement_ref.strip():
        diagnostics.append(
            f"{role_context}: field statement_ref must quote the frozen-commitment "
            "sentence ids (non-empty string)"
        )


def verify_attestation_file(
    record_path: Path,
    *,
    protocol_path: Path,
) -> VerifiedBundle:
    """Verify command core; a missing bundle is a blocked freeze, not an error to guess."""
    if not record_path.is_file():
        who = ", ".join(ROLE_TOKENS)
        msg = (
            f"freeze blocked: no attestations provided (expected bundle file not found: "
            f"{record_path}). Signatures from four humans are still missing: {who}. "
            "Run prepare-record to obtain a scaffold."
        )
        raise FreezeGateError(msg)
    return verify_attestation_payload(
        load_json_object(record_path),
        expected_protocol_sha256=sha256_of_bytes(read_protocol_bytes(protocol_path)),
        origin=str(record_path),
    )


def emit_frozen_record(
    *,
    draft_record_path: Path,
    protocol_path: Path,
    out_path: Path | None,
    force: bool,
    bundle_path: Path | None = None,
    verified: VerifiedBundle | None = None,
) -> dict[str, Any]:
    """Verify, then emit the frozen versioned record; never mutates the markdown.

    Exactly one of ``bundle_path`` or ``verified`` must be given. The
    ``verified`` seam exists so callers (and the deviation regressions) can
    inject a bundle whose verify step passed against DIFFERENT protocol bytes:
    the working-tree binding below still refuses, proving the guard holds after
    a successful verify.
    """
    if (bundle_path is None) == (verified is None):
        msg = "emit_frozen_record requires exactly one of bundle_path or verified"
        raise FreezeGateError(msg)
    if verified is not None and bundle_path is not None:
        msg = "emit_frozen_record accepts only one of bundle_path or verified"
        raise FreezeGateError(msg)
    bundle = (
        verified
        if verified is not None
        else verify_attestation_file(bundle_path, protocol_path=protocol_path)
    )

    draft_payload = load_json_object(draft_record_path)
    draft_status = draft_payload.get("status")
    if draft_status != DRAFT_STATUS:
        msg = (
            f"{draft_record_path}: refusing to freeze a record whose status is "
            f"{draft_status!r}; freezing transitions records only from "
            f"{DRAFT_STATUS}. Adoption of an already-emitted frozen record upstream "
            "is a human governance step."
        )
        raise FreezeGateError(msg)
    if draft_payload.get("data_collection_started") is not False:
        msg = (
            f"{draft_record_path}: refusing to freeze a record claiming "
            "data_collection_started != false (anti-overclaim; no data may exist "
            "before the protocol is adopted)."
        )
        raise FreezeGateError(msg)

    live_protocol_sha256 = sha256_of_bytes(read_protocol_bytes(protocol_path))
    if live_protocol_sha256 != bundle.protocol_sha256:
        msg = (
            "refusing to emit: the working-tree protocol bytes deviate from the "
            f"attested bundle. Working tree {PROTOCOL_PATH.as_posix()} hashes to "
            f"{live_protocol_sha256}, bundle pins {bundle.protocol_sha256}. "
            "Any change is a preregistered deviation needing separate documentation."
        )
        raise FreezeGateError(msg)

    frozen_payload: dict[str, Any] = {
        **draft_payload,
        "status": FROZEN_STATUS,
    }
    try:
        from ntruth.team_evaluation import TeamEvaluationProtocolRecord

        validated = TeamEvaluationProtocolRecord.model_validate(frozen_payload)
    except Exception as exc:  # surface any package-model rejection verbatim
        msg = (
            f"{draft_record_path}: the package contract "
            "packages/ntruth/team_evaluation/models.py rejected the frozen record; "
            f"nothing was written. Reason: {exc}"
        )
        raise FreezeGateError(msg) from exc

    exists = bool(out_path and out_path.exists())
    warning: str | None = None
    if exists and not force:
        msg = (
            f"refusing to overwrite existing {out_path}: pass --force deliberately "
            "to replace an already emitted frozen record."
        )
        raise FreezeGateError(msg)
    if exists and force:
        warning = f"[WARN] overwriting existing frozen record file per explicit --force: {out_path}"

    frozen_record_json = validated.model_dump(mode="json")
    envelope: dict[str, Any] = {
        "attestations": sorted(bundle.attestations, key=lambda item: item["role_token"]),
        "attestations_digest": bundle.attestations_digest,
        "bundle_kind": FREEZE_RECORD_KIND,
        "frozen_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "note": (
            "Status transition recorded here; the protocol markdown is untouched. "
            "Adopting FROZEN_PREREGISTRATION upstream requires a dated deviation "
            "block per maintainer-chosen conventions."
        ),
        "protocol_id": PROTOCOL_ID,
        "record": frozen_record_json,
        "schema_version": SCHEMA_VERSION,
        "source_protocol_sha256": live_protocol_sha256,
    }
    written = False
    if out_path is not None:
        text = json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        out_path.write_text(text, encoding="utf-8")
        written = True
    return {
        "attestations_digest": bundle.attestations_digest,
        "outcome": ("wrote file" if written else "printed to stdout (no --out given)"),
        "record_status": FROZEN_STATUS,
        "source_protocol_sha256": live_protocol_sha256,
        "target": str(out_path) if out_path is not None else "<stdout>",
        "warning": warning,
    }


def _resolve(path_value: str) -> Path:
    candidate = Path(path_value)
    return candidate if candidate.is_absolute() else REPOSITORY_ROOT / candidate


def _print_failure(exc: FreezeGateError) -> None:
    print(
        json.dumps(
            {"diagnostics": [str(exc)], "status": "FAIL"},
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def _cmd_verify(args: argparse.Namespace) -> int:
    bundle = verify_attestation_file(_resolve(args.record), protocol_path=_resolve(args.protocol))
    result = {
        "attestations_digest": bundle.attestations_digest,
        "covered_roles": [item["role_token"] for item in bundle.attestations],
        "protocol_sha256": bundle.protocol_sha256,
        "status": "PASS",
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


def _cmd_prepare(args: argparse.Namespace) -> int:
    scaffold = prepare_scaffold(_resolve(args.protocol))
    print(json.dumps(scaffold, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _cmd_emit(args: argparse.Namespace) -> int:
    result = emit_frozen_record(
        bundle_path=_resolve(args.bundle),
        draft_record_path=_resolve(args.draft_record),
        protocol_path=_resolve(args.protocol),
        out_path=_resolve(args.out) if args.out else None,
        force=args.force,
    )
    if result["warning"]:
        print(result["warning"], file=sys.stderr)
    print(json.dumps({**result, "status": "PASS"}, ensure_ascii=False, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    verify_parser = subparsers.add_parser(
        "verify", help="validate an attestation bundle against the current protocol bytes"
    )
    verify_parser.add_argument(
        "--record",
        type=str,
        default=str(DEFAULT_BUNDLE_PATH),
        help=f"attestation bundle path (default: {DEFAULT_BUNDLE_PATH})",
    )
    verify_parser.add_argument("--protocol", type=str, default=str(PROTOCOL_PATH))
    verify_parser.set_defaults(handler=_cmd_verify)

    prepare_parser = subparsers.add_parser(
        "prepare-record", help="emit a ready-to-fill attestation bundle scaffold"
    )
    prepare_parser.add_argument("--protocol", type=str, default=str(PROTOCOL_PATH))
    prepare_parser.set_defaults(handler=_cmd_prepare)

    emit_parser = subparsers.add_parser(
        "emit-frozen", help="after verify passes, emit the frozen versioned record"
    )
    emit_parser.add_argument(
        "--bundle",
        type=str,
        default=str(DEFAULT_BUNDLE_PATH),
        help=f"verified attestation bundle path (default: {DEFAULT_BUNDLE_PATH})",
    )
    emit_parser.add_argument("--draft-record", type=str, required=True, help=DRAFT_RECORD_HELP)
    emit_parser.add_argument("--protocol", type=str, default=str(PROTOCOL_PATH))
    emit_parser.add_argument(
        "--out", type=str, default=None, help="output path; prints to stdout when omitted"
    )
    emit_parser.add_argument(
        "--force",
        action="store_true",
        help="explicitly allow overwriting an existing output file (warned)",
    )
    emit_parser.set_defaults(handler=_cmd_emit)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handler = args.handler
    try:
        return int(handler(args))
    except FreezeGateError as exc:
        _print_failure(exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
