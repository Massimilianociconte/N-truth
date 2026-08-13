"""Unsigned sign-off slots and the pre-training go/no-go packet."""

from __future__ import annotations

import pytest

from ntruth.reality_gate import GatePurpose, evaluate_reality_gate
from ntruth.schemas.registry_v9 import NORMATIVE_REGISTRY_V9_FROZEN
from ntruth.training.pretraining_hold import (
    build_pretraining_hold_packet,
    hold_packet_as_machine_readable,
)
from ntruth.training.readiness import OverallReadiness, project_small_model_training_readiness
from ntruth.training.signoff import (
    REQUIRED_SLOTS,
    SignOffLedger,
    SignOffStatus,
    apply_human_signoff,
    assert_signoff_fail_closed,
    empty_signoff_ledger,
    load_signoff_ledger,
    write_unsigned_template,
)


def test_unsigned_ledger_names_required_slots_and_cannot_freeze() -> None:
    ledger = load_signoff_ledger()
    assert_signoff_fail_closed(ledger)
    assert tuple(item.slot_id for item in ledger.slots) == REQUIRED_SLOTS
    assert all(item.status is SignOffStatus.UNSIGNED for item in ledger.slots)
    assert ledger.normative_registry_v9_frozen is False
    assert ledger.substantive_training_allowed is False
    assert ledger.gold_declared is False
    assert NORMATIVE_REGISTRY_V9_FROZEN is False
    assert set(ledger.unsigned_slots()) == set(REQUIRED_SLOTS)


def test_empty_closure_and_well_formed_closure_cannot_auto_sign() -> None:
    ledger = empty_signoff_ledger()
    with pytest.raises(ValueError, match="closure artifact"):
        apply_human_signoff(
            ledger, slot_id="scientific_registry_v9", closure=None
        )
    with pytest.raises(ValueError, match="outside the automatic path"):
        apply_human_signoff(
            ledger,
            slot_id="scientific_registry_v9",
            closure={
                "artifact_sha256": "ab" * 32,
                "signer_role": "scientific-owner",
                "signed_at": "2026-08-14T00:00:00Z",
            },
        )
    assert ledger.slot("scientific_registry_v9").status is SignOffStatus.UNSIGNED


def test_self_frozen_ledger_is_rejected() -> None:
    payload = empty_signoff_ledger().model_dump(mode="json")
    payload["normative_registry_v9_frozen"] = True
    with pytest.raises(ValueError):
        SignOffLedger.model_validate(payload)
    payload = empty_signoff_ledger().model_dump(mode="json")
    payload["gold_declared"] = True
    with pytest.raises(ValueError):
        SignOffLedger.model_validate(payload)
    payload = empty_signoff_ledger().model_dump(mode="json")
    payload["substantive_training_allowed"] = True
    with pytest.raises(ValueError):
        SignOffLedger.model_validate(payload)


def test_hold_packet_says_user_decides_and_baselines_unexecuted() -> None:
    projection = project_small_model_training_readiness(
        evaluate_reality_gate((), purpose=GatePurpose.SUBSTANTIVE_TRAINING)
    )
    packet = build_pretraining_hold_packet(projection)
    payload = hold_packet_as_machine_readable(packet)

    assert payload["status"] == "HOLD_USER_DECIDES_TRAINING"
    assert payload["user_decides_when_training_happens"] is True
    assert payload["download_candidates_executed"] is False
    assert payload["baseline_ladder_executed"] is False
    assert payload["fine_tuning_executed"] is False
    assert payload["substantive_training_allowed"] is False
    assert payload["overall_readiness"] == OverallReadiness.NOT_READY.value
    assert payload["next_automatable_step"] is None
    for slot in REQUIRED_SLOTS:
        assert slot in payload["unsigned_human_slots"]
        assert slot in payload["remaining_blockers"]
    assert "ROOT_SUBSTANTIVE_TRAINING_BLOCKED" in payload["remaining_blockers"]


def test_unsigned_template_round_trip(tmp_path) -> None:
    path = tmp_path / "slots.json"
    write_unsigned_template(path)
    loaded = load_signoff_ledger(path)
    assert_signoff_fail_closed(loaded)
    assert loaded.unsigned_slots() == REQUIRED_SLOTS
