"""Fail-closed human sign-off slots for the pre-training hold.

Unsigned or absent slots cannot freeze registry v9, cannot write GOLD, and
cannot allow substantive training.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from ntruth.schemas.core import FrozenModel, content_checksum
from ntruth.schemas.registry_v9 import NORMATIVE_REGISTRY_V9_FROZEN

SIGNOFF_SCHEMA_VERSION = "1.0.0"
REQUIRED_SLOTS: tuple[str, ...] = (
    "scientific_registry_v9",
    "data_steward_legal_dua",
    "gold_dual_annotation_iaa",
    "independent_test_external_custodian",
    "fd_security_review",
)


class SignOffStatus(StrEnum):
    UNSIGNED = "UNSIGNED"
    REJECTED = "REJECTED"
    SIGNED = "SIGNED"


class SignOffSlot(FrozenModel):
    slot_id: str
    status: SignOffStatus = SignOffStatus.UNSIGNED
    signer_role: str | None = None
    artifact_sha256: str | None = None
    signed_at: str | None = None
    note: str = ""


class SignOffLedger(FrozenModel):
    schema_version: Literal["1.0.0"] = SIGNOFF_SCHEMA_VERSION
    artifact_type: Literal["ntruth-pretraining-signoff-ledger"] = (
        "ntruth-pretraining-signoff-ledger"
    )
    slots: tuple[SignOffSlot, ...]
    normative_registry_v9_frozen: Literal[False] = False
    substantive_training_allowed: Literal[False] = False
    gold_declared: Literal[False] = False

    def slot(self, slot_id: str) -> SignOffSlot:
        for item in self.slots:
            if item.slot_id == slot_id:
                return item
        raise KeyError(slot_id)

    def unsigned_slots(self) -> tuple[str, ...]:
        return tuple(
            item.slot_id for item in self.slots if item.status is not SignOffStatus.SIGNED
        )


def default_signoff_path() -> Path:
    return Path(__file__).resolve().parent / "signoff_unsigned.v1.json"


def empty_signoff_ledger() -> SignOffLedger:
    notes = {
        "scientific_registry_v9": "Human scientific owner must approve the PRD v9 registry",
        "data_steward_legal_dua": "Data steward must close license/DUA/redistribution/use",
        "gold_dual_annotation_iaa": "Independent dual annotation, agreement, adjudication",
        "independent_test_external_custodian": "Appoint a custodian for test/external",
        "fd_security_review": "Human security review of the O_RDONLY FD runner",
    }
    return SignOffLedger(
        slots=tuple(
            SignOffSlot(slot_id=slot_id, note=notes[slot_id]) for slot_id in REQUIRED_SLOTS
        )
    )


def load_signoff_ledger(path: Path | None = None) -> SignOffLedger:
    target = path or default_signoff_path()
    if not target.is_file():
        return empty_signoff_ledger()
    payload = json.loads(target.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = {key: value for key, value in payload.items() if key != "checksum"}
    ledger = SignOffLedger.model_validate(payload)
    assert_signoff_fail_closed(ledger)
    return ledger


def write_unsigned_template(path: Path | None = None) -> dict[str, Any]:
    ledger = empty_signoff_ledger()
    payload = ledger.model_dump(mode="json")
    payload["checksum"] = content_checksum(payload)
    target = path or default_signoff_path()
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def assert_signoff_fail_closed(ledger: SignOffLedger) -> None:
    present = {item.slot_id for item in ledger.slots}
    missing = [slot for slot in REQUIRED_SLOTS if slot not in present]
    if missing:
        raise ValueError(f"sign-off ledger missing required slots: {missing}")
    if ledger.normative_registry_v9_frozen is True:
        raise ValueError("unsigned sign-off ledger cannot freeze registry v9")
    if ledger.substantive_training_allowed is True:
        raise ValueError("unsigned sign-off ledger cannot allow substantive training")
    if ledger.gold_declared is True:
        raise ValueError("unsigned sign-off ledger cannot declare GOLD")
    if NORMATIVE_REGISTRY_V9_FROZEN is True:
        raise ValueError("registry draft cannot be frozen by sign-off machinery")


def apply_human_signoff(
    ledger: SignOffLedger,
    *,
    slot_id: str,
    closure: Mapping[str, Any] | None,
) -> SignOffLedger:
    """Refuse to sign, freeze, or promote GOLD without a human closure artifact."""

    if closure is None:
        raise ValueError("human sign-off requires a closure artifact")
    digest = closure.get("artifact_sha256")
    role = closure.get("signer_role")
    signed_at = closure.get("signed_at")
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError("human sign-off closure artifact_sha256 missing")
    if not isinstance(role, str) or not role.strip():
        raise ValueError("human sign-off signer_role missing")
    if not isinstance(signed_at, str) or not signed_at.strip():
        raise ValueError("human sign-off signed_at missing")
    # Even a well-formed closure is not auto-applied: a human must write the
    # signed ledger outside this automatic path.
    raise ValueError(
        "human steward must write signed slots outside the automatic path; "
        f"{slot_id} remains UNSIGNED"
    )


def signoff_cannot_write_gold(ledger: SignOffLedger) -> None:
    if ledger.gold_declared:
        raise ValueError("sign-off cannot write AuthorityLevel.NTRUTH_GOLD")
    if ledger.normative_registry_v9_frozen:
        raise ValueError("sign-off cannot freeze registry v9")
