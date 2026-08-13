"""Pre-training go/no-go packet. The user decides when training happens."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from ntruth.data.eligibility_join import summarize_root_identity
from ntruth.schemas.core import FrozenModel, content_checksum
from ntruth.training.readiness import OverallReadiness, SmallModelTrainingReadiness
from ntruth.training.signoff import SignOffLedger, load_signoff_ledger

HOLD_SCHEMA_VERSION = "1.0.0"


class PretrainingHoldPacket(FrozenModel):
    schema_version: Literal["1.0.0"] = HOLD_SCHEMA_VERSION
    artifact_type: Literal["ntruth-pretraining-hold-packet"] = (
        "ntruth-pretraining-hold-packet"
    )
    status: Literal["HOLD_USER_DECIDES_TRAINING"] = "HOLD_USER_DECIDES_TRAINING"
    user_decides_when_training_happens: Literal[True] = True
    download_candidates_executed: Literal[False] = False
    baseline_ladder_executed: Literal[False] = False
    fine_tuning_executed: Literal[False] = False
    substantive_training_allowed: Literal[False] = False
    overall_readiness: OverallReadiness
    unsigned_human_slots: tuple[str, ...]
    remaining_blockers: tuple[str, ...]
    identity_observation: dict[str, Any] | None = None
    next_automatable_step: Literal[None] = None
    note: str = (
        "All automatable pre-training contracts are in force. Remaining gates "
        "are human. Do not download models or run baselines until the user "
        "decides to train."
    )


def build_pretraining_hold_packet(
    projection: SmallModelTrainingReadiness,
    *,
    signoff: SignOffLedger | None = None,
    identity_observation: Mapping[str, Any] | None = None,
) -> PretrainingHoldPacket:
    ledger = signoff if signoff is not None else load_signoff_ledger()
    blockers = tuple(item.code for item in projection.overall_blockers)
    unsigned = ledger.unsigned_slots()
    remaining = tuple(dict.fromkeys((*unsigned, *blockers)))
    return PretrainingHoldPacket(
        overall_readiness=projection.overall,
        unsigned_human_slots=unsigned,
        remaining_blockers=remaining,
        identity_observation=dict(identity_observation) if identity_observation else None,
    )


def hold_packet_as_machine_readable(packet: PretrainingHoldPacket) -> dict[str, Any]:
    payload = packet.model_dump(mode="json")
    payload["checksum"] = content_checksum(payload)
    if payload.get("substantive_training_allowed") is True:
        raise ValueError("hold packet cannot allow substantive training")
    if payload.get("download_candidates_executed") is True:
        raise ValueError("hold packet cannot claim download executed")
    if payload.get("baseline_ladder_executed") is True:
        raise ValueError("hold packet cannot claim baselines executed")
    return payload


def observe_identity_if_root(dataset_root: Any) -> dict[str, Any] | None:
    if dataset_root is None:
        return None
    from pathlib import Path

    root = Path(dataset_root)
    if not root.is_dir():
        return None
    return summarize_root_identity(root)
