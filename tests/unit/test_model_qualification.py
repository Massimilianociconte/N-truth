"""Test P5: ModelQualificationRecord, transizioni e registry integration (PRD v9 §25.10)."""

from __future__ import annotations

import dataclasses

import pytest

from ntruth.model_backends.qualification import (
    ContaminationRisk,
    DecodingRuntimeProfile,
    ModelQualificationError,
    ModelQualificationLedger,
    ModelQualificationRecord,
    QualificationStage,
    QualificationTransition,
    compute_transition_sha256,
    is_valid_transition,
    sha256_text,
    verify_transition_sequence,
)
from ntruth.model_backends.registry import (
    ARTIFACT_FINGERPRINT_KEYS,
    evaluate_model_qualification_record,
)


def make_profile() -> DecodingRuntimeProfile:
    return DecodingRuntimeProfile(
        context_window_tokens=32768,
        batch_size=1,
        decoding_profile="greedy;temperature=0.0;seed=0",
        hardware_fingerprint="apple-m5-pro-24gb",
    )


def make_record() -> ModelQualificationRecord:
    return ModelQualificationRecord(
        model_id="ibm-granite/granite-4.1-3b",
        model_revision="main",
        artifact_sha256=sha256_text("weights"),
        tokenizer_sha256=sha256_text("tokenizer"),
        chat_template_sha256=sha256_text("chat-template"),
        quantization="q4_k_m",
        backend="mlx-lm",
        runtime_profile=make_profile(),
        task_profile="P0_assignment_explicit",
        calibration_id="CAL-P0-2026-01",
        contamination_risk=ContaminationRisk.LOW,
    )


FULL_CHAIN = (
    QualificationStage.STAGE_SEMANTIC_QUALIFIED,
    QualificationStage.END_TO_END_QUALIFIED,
    QualificationStage.TEAM_QUALIFIED,
    QualificationStage.PROFILE_DEPLOYMENT_QUALIFIED,
)


def advance_full(ledger: ModelQualificationLedger) -> None:
    for stage in FULL_CHAIN:
        ledger.append(to_stage=stage, actor="ml-lead", rationale=f"evidence for {stage.value}")


class TestModelQualificationRecord:
    def test_new_record_starts_runtime_qualified(self) -> None:
        record = make_record()
        assert record.stage is QualificationStage.RUNTIME_QUALIFIED

    def test_record_cannot_be_constructed_at_advanced_state(self) -> None:
        with pytest.raises(ModelQualificationError, match="RUNTIME_QUALIFIED"):
            dataclasses.replace(make_record(), stage=QualificationStage.TEAM_QUALIFIED)

    def test_record_is_immutable(self) -> None:
        record = make_record()
        with pytest.raises(dataclasses.FrozenInstanceError):
            record.artifact_sha256 = sha256_text("other")
        assert record.artifact_sha256 == sha256_text("weights")

    def test_blank_and_malformed_fields_rejected(self) -> None:
        base = {
            "model_id": "",
            "artifact_sha256": "not-a-hash",
        }
        with pytest.raises(ModelQualificationError):
            ModelQualificationRecord(
                model_id="m",
                artifact_sha256=base["artifact_sha256"],
                tokenizer_sha256=sha256_text("t"),
                chat_template_sha256=sha256_text("c"),
                quantization="q4",
                backend="mlx-lm",
                runtime_profile=make_profile(),
                task_profile="P0",
                calibration_id="CAL-1",
                contamination_risk=ContaminationRisk.UNKNOWN,
            )
        with pytest.raises(ModelQualificationError, match="model_id"):
            ModelQualificationRecord(
                model_id=base["model_id"],
                artifact_sha256=sha256_text("w"),
                tokenizer_sha256=sha256_text("t"),
                chat_template_sha256=sha256_text("c"),
                quantization="q4",
                backend="mlx-lm",
                runtime_profile=make_profile(),
                task_profile="P0",
                calibration_id="CAL-1",
                contamination_risk=ContaminationRisk.LOW,
            )
        with pytest.raises(ModelQualificationError, match="context_window_tokens"):
            DecodingRuntimeProfile(
                context_window_tokens=0,
                batch_size=1,
                decoding_profile="greedy",
                hardware_fingerprint="hw",
            )


class TestQualificationTransitions:
    def test_only_next_stage_transition_is_valid(self) -> None:
        assert is_valid_transition(
            QualificationStage.RUNTIME_QUALIFIED,
            QualificationStage.STAGE_SEMANTIC_QUALIFIED,
        )
        assert not is_valid_transition(
            QualificationStage.RUNTIME_QUALIFIED, QualificationStage.TEAM_QUALIFIED
        )
        assert not is_valid_transition(
            QualificationStage.END_TO_END_QUALIFIED,
            QualificationStage.STAGE_SEMANTIC_QUALIFIED,
        )
        assert not is_valid_transition(
            QualificationStage.PROFILE_DEPLOYMENT_QUALIFIED,
            QualificationStage.PROFILE_DEPLOYMENT_QUALIFIED,
        )

    def test_full_chain_appends_transitions_in_order(self) -> None:
        ledger = ModelQualificationLedger(make_record())
        advance_full(ledger)
        transitions = ledger.transitions()
        assert [item.to_stage for item in transitions] == list(FULL_CHAIN)
        assert [item.sequence for item in transitions] == [1, 2, 3, 4]
        assert ledger.current_stage() is QualificationStage.PROFILE_DEPLOYMENT_QUALIFIED
        assert ledger.is_deployment_qualified()
        ledger.verify_chain()

    def test_hash_chain_links_each_transition(self) -> None:
        ledger = ModelQualificationLedger(make_record())
        first = ledger.append(
            to_stage=QualificationStage.STAGE_SEMANTIC_QUALIFIED,
            actor="ml-lead",
            rationale="stage semantic suite green",
        )
        second = ledger.append(
            to_stage=QualificationStage.END_TO_END_QUALIFIED,
            actor="ml-lead",
            rationale="end-to-end suite green",
        )
        assert second.previous_transition_sha256 == first.transition_sha256
        assert second.transition_sha256 == compute_transition_sha256(second)

    def test_out_of_order_transitions_rejected(self) -> None:
        ledger = ModelQualificationLedger(make_record())
        with pytest.raises(ModelQualificationError, match="fuori ordine"):
            ledger.append(
                to_stage=QualificationStage.TEAM_QUALIFIED,
                actor="ml-lead",
                rationale="skip attempt",
            )
        ledger.append(
            to_stage=QualificationStage.STAGE_SEMANTIC_QUALIFIED,
            actor="ml-lead",
            rationale="ok step",
        )
        with pytest.raises(ModelQualificationError, match="fuori ordine"):
            ledger.append(
                to_stage=QualificationStage.RUNTIME_QUALIFIED,
                actor="ml-lead",
                rationale="backward attempt",
            )
        with pytest.raises(ModelQualificationError, match="fuori ordine"):
            ledger.append(
                to_stage=QualificationStage.PROFILE_DEPLOYMENT_QUALIFIED,
                actor="ml-lead",
                rationale="skip to terminal",
            )
        assert ledger.current_stage() is QualificationStage.STAGE_SEMANTIC_QUALIFIED

    def test_terminal_state_rejects_further_advance(self) -> None:
        ledger = ModelQualificationLedger(make_record())
        advance_full(ledger)
        with pytest.raises(ModelQualificationError, match="terminale"):
            ledger.append(
                to_stage=QualificationStage.PROFILE_DEPLOYMENT_QUALIFIED,
                actor="ml-lead",
                rationale="already terminal",
            )

    def test_nobody_implies_the_next_state(self) -> None:
        ledger = ModelQualificationLedger(make_record())
        assert ledger.current_stage() is QualificationStage.RUNTIME_QUALIFIED
        assert ledger.transitions() == ()
        assert not ledger.is_deployment_qualified()

    def test_verify_transition_sequence_detects_tampering(self) -> None:
        ledger = ModelQualificationLedger(make_record())
        transition = ledger.append(
            to_stage=QualificationStage.STAGE_SEMANTIC_QUALIFIED,
            actor="ml-lead",
            rationale="ok",
        )
        verify_transition_sequence(QualificationStage.RUNTIME_QUALIFIED, [transition])
        tampered = dataclasses.replace(transition, rationale="rewritten history")
        with pytest.raises(ModelQualificationError, match="transition_sha256"):
            verify_transition_sequence(QualificationStage.RUNTIME_QUALIFIED, [tampered])
        broken_chain = QualificationTransition(
            sequence=1,
            timestamp=transition.timestamp,
            from_stage=QualificationStage.RUNTIME_QUALIFIED,
            to_stage=QualificationStage.STAGE_SEMANTIC_QUALIFIED,
            actor=transition.actor,
            rationale=transition.rationale,
            previous_transition_sha256=sha256_text("foreign"),
        )
        object.__setattr__(
            broken_chain, "transition_sha256", compute_transition_sha256(broken_chain)
        )
        with pytest.raises(ModelQualificationError, match="hash chain"):
            verify_transition_sequence(QualificationStage.RUNTIME_QUALIFIED, [broken_chain])
        bad_order = QualificationTransition(
            sequence=2,
            timestamp="2026-01-01T00:00:00Z",
            from_stage=QualificationStage.STAGE_SEMANTIC_QUALIFIED,
            to_stage=QualificationStage.TEAM_QUALIFIED,
            actor="ml-lead",
            rationale="out of order",
            previous_transition_sha256=transition.transition_sha256,
        )
        object.__setattr__(bad_order, "transition_sha256", compute_transition_sha256(bad_order))
        with pytest.raises(ModelQualificationError, match="fuori ordine"):
            verify_transition_sequence(
                QualificationStage.RUNTIME_QUALIFIED, [transition, bad_order]
            )

    def test_transitions_snapshot_is_tuple_and_isolated(self) -> None:
        ledger = ModelQualificationLedger(make_record())
        ledger.append(
            to_stage=QualificationStage.STAGE_SEMANTIC_QUALIFIED,
            actor="ml-lead",
            rationale="ok",
        )
        snapshot = ledger.transitions()
        assert isinstance(snapshot, tuple)
        assert all(isinstance(item, QualificationTransition) for item in snapshot)
        ledger.append(
            to_stage=QualificationStage.END_TO_END_QUALIFIED,
            actor="ml-lead",
            rationale="ok",
        )
        assert len(snapshot) == 1
        assert len(ledger.transitions()) == 2


def current_artifact_payload(record: ModelQualificationRecord) -> dict[str, object]:
    return {
        "model_id": record.model_id,
        "model_revision": record.model_revision,
        "weights_sha256": record.artifact_sha256,
        "tokenizer_revision": record.tokenizer_sha256,
        "chat_template_hash": record.chat_template_sha256,
        "quantization": record.quantization,
        "backend": record.backend,
        "task_profile": record.task_profile,
    }


class TestRegistryIntegration:
    def test_absent_record_is_fail_closed(self) -> None:
        outcome = evaluate_model_qualification_record(None)
        assert outcome["provided"] is False
        assert outcome["deployable"] is False
        assert outcome["stale_reasons"] == ["MODEL_QUALIFICATION_RECORD_ABSENT"]

    def test_qualified_record_on_matching_artifact_is_deployable(self) -> None:
        ledger = ModelQualificationLedger(make_record())
        advance_full(ledger)
        outcome = evaluate_model_qualification_record(
            ledger.current_record(),
            current_artifact=current_artifact_payload(make_record()),
        )
        assert outcome["provided"] is True
        assert outcome["stage"] == "PROFILE_DEPLOYMENT_QUALIFIED"
        assert outcome["matches_current_artifact"] is True
        assert outcome["stale"] is False
        assert outcome["deployable"] is True

    def test_partial_qualification_is_not_deployable(self) -> None:
        record = make_record()
        outcome = evaluate_model_qualification_record(
            record,
            current_artifact=current_artifact_payload(record),
        )
        assert outcome["stage"] == "RUNTIME_QUALIFIED"
        assert outcome["deployable"] is False

    def test_artifact_drift_marks_stale_and_blocks_deployment(self) -> None:
        ledger = ModelQualificationLedger(make_record())
        advance_full(ledger)
        drifted = current_artifact_payload(make_record())
        drifted["weights_sha256"] = sha256_text("requantized-weights")
        outcome = evaluate_model_qualification_record(
            ledger.current_record(), current_artifact=drifted
        )
        assert outcome["matches_current_artifact"] is False
        assert outcome["deployable"] is False
        assert any(reason.startswith("weights_sha256:") for reason in outcome["stale_reasons"])

    def test_missing_current_artifact_never_deployable(self) -> None:
        ledger = ModelQualificationLedger(make_record())
        advance_full(ledger)
        outcome = evaluate_model_qualification_record(ledger.current_record())
        assert outcome["deployable"] is False
        assert outcome["stale_reasons"] == ["CURRENT_ARTIFACT_UNAVAILABLE"]

    def test_binding_keys_are_registry_compatible(self) -> None:
        record = make_record()
        outcome = evaluate_model_qualification_record(
            record, current_artifact=current_artifact_payload(record)
        )
        binding = outcome["binding"]
        assert set(binding).issubset(set(ARTIFACT_FINGERPRINT_KEYS))
        assert binding["weights_sha256"] == record.artifact_sha256
