"""ModelQualificationRecord e ledger append-only (PRD v9 §12.6, §25.10, Appendice T).

Stati separati RUNTIME_QUALIFIED → STAGE_SEMANTIC_QUALIFIED → END_TO_END_QUALIFIED
→ TEAM_QUALIFIED → PROFILE_DEPLOYMENT_QUALIFIED. Nessuno stato implica
automaticamente il successivo: ogni avanzamento è una transizione esplicita,
registrata append-only con hash chaining e verifica dell'ordine valido.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, fields
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final

QUALIFICATION_SCHEMA_VERSION = "v9-25.10"
_SHA256_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")


class ModelQualificationError(RuntimeError):
    """Violazione fail-closed del contratto di qualificazione modello."""


class QualificationStage(StrEnum):
    RUNTIME_QUALIFIED = "RUNTIME_QUALIFIED"
    STAGE_SEMANTIC_QUALIFIED = "STAGE_SEMANTIC_QUALIFIED"
    END_TO_END_QUALIFIED = "END_TO_END_QUALIFIED"
    TEAM_QUALIFIED = "TEAM_QUALIFIED"
    PROFILE_DEPLOYMENT_QUALIFIED = "PROFILE_DEPLOYMENT_QUALIFIED"


class ContaminationRisk(StrEnum):
    NONE_KNOWN = "NONE_KNOWN"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


QUALIFICATION_STAGE_ORDER: Final[tuple[QualificationStage, ...]] = (
    QualificationStage.RUNTIME_QUALIFIED,
    QualificationStage.STAGE_SEMANTIC_QUALIFIED,
    QualificationStage.END_TO_END_QUALIFIED,
    QualificationStage.TEAM_QUALIFIED,
    QualificationStage.PROFILE_DEPLOYMENT_QUALIFIED,
)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def next_qualification_stage(stage: QualificationStage) -> QualificationStage | None:
    index = QUALIFICATION_STAGE_ORDER.index(stage)
    if index + 1 >= len(QUALIFICATION_STAGE_ORDER):
        return None
    return QUALIFICATION_STAGE_ORDER[index + 1]


def is_valid_transition(from_stage: QualificationStage, to_stage: QualificationStage) -> bool:
    """Solo l'avanzamento esatto al prossimo stato è valido: niente salti né regressioni."""
    return next_qualification_stage(from_stage) is to_stage


def _require_text(value: str, field_name: str) -> None:
    if not value.strip():
        raise ModelQualificationError(f"{field_name} obbligatorio e non vuoto")


def _require_sha256(value: str, field_name: str) -> None:
    _require_text(value, field_name)
    if not _SHA256_PATTERN.fullmatch(value.strip()):
        raise ModelQualificationError(
            f"{field_name} deve essere uno SHA-256 esadecimale minuscolo a 64 caratteri"
        )


@dataclass(frozen=True, slots=True)
class DecodingRuntimeProfile:
    context_window_tokens: int
    batch_size: int
    decoding_profile: str
    hardware_fingerprint: str

    def __post_init__(self) -> None:
        if self.context_window_tokens <= 0:
            raise ModelQualificationError("context_window_tokens deve essere > 0")
        if self.batch_size <= 0:
            raise ModelQualificationError("batch_size deve essere > 0")
        _require_text(self.decoding_profile, "decoding_profile")
        _require_text(self.hardware_fingerprint, "hardware_fingerprint")


@dataclass(frozen=True, slots=True)
class ModelQualificationRecord:
    """Record di qualificazione per una combinazione model/runtime (PRD §25.10)."""

    model_id: str
    artifact_sha256: str
    tokenizer_sha256: str
    chat_template_sha256: str
    quantization: str
    backend: str
    runtime_profile: DecodingRuntimeProfile
    task_profile: str
    calibration_id: str
    contamination_risk: ContaminationRisk
    model_revision: str = ""
    stage: QualificationStage = QualificationStage.RUNTIME_QUALIFIED

    def __post_init__(self) -> None:
        _require_text(self.model_id, "model_id")
        for field_name in ("artifact_sha256", "tokenizer_sha256", "chat_template_sha256"):
            _require_sha256(getattr(self, field_name), field_name)
        _require_text(self.quantization, "quantization")
        _require_text(self.backend, "backend")
        _require_text(self.task_profile, "task_profile")
        _require_text(self.calibration_id, "calibration_id")
        if self.stage is not QualificationStage.RUNTIME_QUALIFIED:
            raise ModelQualificationError(
                "un nuovo record parte da RUNTIME_QUALIFIED: l'avanzamento passa solo "
                "dal ledger (nessuno stato implica automaticamente il successivo)"
            )


@dataclass(frozen=True, slots=True)
class QualificationTransition:
    sequence: int
    timestamp: str
    from_stage: QualificationStage
    to_stage: QualificationStage
    actor: str
    rationale: str
    evidence_ref: str | None = None
    previous_transition_sha256: str | None = None
    transition_sha256: str = ""


def compute_transition_sha256(transition: QualificationTransition) -> str:
    payload = {
        "schema_version": QUALIFICATION_SCHEMA_VERSION,
        "sequence": transition.sequence,
        "timestamp": transition.timestamp,
        "from_stage": transition.from_stage.value,
        "to_stage": transition.to_stage.value,
        "actor": transition.actor,
        "rationale": transition.rationale,
        "evidence_ref": transition.evidence_ref,
        "previous_transition_sha256": transition.previous_transition_sha256,
    }
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_transition_sequence(
    initial_stage: QualificationStage,
    transitions: Sequence[QualificationTransition],
) -> None:
    """Verifica sequence 1..N senza buchi, ordine valido e catena di hash."""
    expected_sequence = 1
    previous_hash: str | None = None
    current_stage = initial_stage
    for transition in transitions:
        if transition.sequence != expected_sequence:
            raise ModelQualificationError(
                f"sequence non monotona: attesa {expected_sequence}, trovata {transition.sequence}"
            )
        if transition.from_stage is not current_stage:
            raise ModelQualificationError(
                f"transizione sequence={transition.sequence} parte da "
                f"{transition.from_stage.value} ma lo stato corrente è {current_stage.value}"
            )
        if not is_valid_transition(transition.from_stage, transition.to_stage):
            raise ModelQualificationError(
                f"transizione fuori ordine rifiutata: "
                f"{transition.from_stage.value} → {transition.to_stage.value}; "
                "nessuno stato implica automaticamente il successivo"
            )
        recomputed = compute_transition_sha256(transition)
        if recomputed != transition.transition_sha256:
            raise ModelQualificationError(
                f"transition_sha256 non valida a sequence={transition.sequence}"
            )
        if transition.previous_transition_sha256 != previous_hash:
            raise ModelQualificationError(f"hash chain rotta a sequence={transition.sequence}")
        previous_hash = transition.transition_sha256
        current_stage = transition.to_stage
        expected_sequence += 1


def _advance_record(
    record: ModelQualificationRecord, to_stage: QualificationStage
) -> ModelQualificationRecord:
    advanced = object.__new__(ModelQualificationRecord)
    for field_info in fields(record):
        object.__setattr__(advanced, field_info.name, getattr(record, field_info.name))
    object.__setattr__(advanced, "stage", to_stage)
    return advanced


class ModelQualificationLedger:
    """Ledger in memoria append-only: unica via di avanzamento tra stati."""

    def __init__(self, record: ModelQualificationRecord) -> None:
        validated = ModelQualificationRecord(
            model_id=record.model_id,
            artifact_sha256=record.artifact_sha256,
            tokenizer_sha256=record.tokenizer_sha256,
            chat_template_sha256=record.chat_template_sha256,
            quantization=record.quantization,
            backend=record.backend,
            runtime_profile=record.runtime_profile,
            task_profile=record.task_profile,
            calibration_id=record.calibration_id,
            contamination_risk=record.contamination_risk,
            model_revision=record.model_revision,
        )
        self._initial_stage = validated.stage
        self._record = validated
        self._transitions: list[QualificationTransition] = []

    @property
    def record(self) -> ModelQualificationRecord:
        return self._record

    def current_record(self) -> ModelQualificationRecord:
        return self._record

    def current_stage(self) -> QualificationStage:
        return self._record.stage

    def transitions(self) -> tuple[QualificationTransition, ...]:
        return tuple(self._transitions)

    def append(
        self,
        *,
        to_stage: QualificationStage,
        actor: str,
        rationale: str,
        evidence_ref: str | None = None,
    ) -> QualificationTransition:
        _require_text(actor, "actor")
        _require_text(rationale, "rationale")
        from_stage = self.current_stage()
        if not is_valid_transition(from_stage, to_stage):
            raise ModelQualificationError(
                f"transizione fuori ordine rifiutata: {from_stage.value} → "
                f"{to_stage.value}; nessuno stato implica automaticamente il successivo"
                + (
                    f" ({from_stage.value} è lo stato terminale)"
                    if next_qualification_stage(from_stage) is None
                    else ""
                )
            )
        latest = self._transitions[-1] if self._transitions else None
        transition = QualificationTransition(
            sequence=len(self._transitions) + 1,
            timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            from_stage=from_stage,
            to_stage=to_stage,
            actor=actor.strip(),
            rationale=rationale.strip(),
            evidence_ref=evidence_ref,
            previous_transition_sha256=(latest.transition_sha256 if latest is not None else None),
        )
        object.__setattr__(transition, "transition_sha256", compute_transition_sha256(transition))
        verify_transition_sequence(self._initial_stage, [*self._transitions, transition])
        self._record = _advance_record(self._record, to_stage)
        self._transitions.append(transition)
        return transition

    def verify_chain(self) -> None:
        verify_transition_sequence(self._initial_stage, self._transitions)

    def is_deployment_qualified(self) -> bool:
        return self.current_stage() is QualificationStage.PROFILE_DEPLOYMENT_QUALIFIED
