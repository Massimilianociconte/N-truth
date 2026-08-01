"""Motore di correzioni deterministico, append-only e senza dipendenze ML.

Il ledger conserva il blocco originale come snapshot JSON immutabile. Ogni
``apply``, ``undo`` e ``redo`` restituisce un nuovo ledger: nessuna operazione
cancella record o eventi precedenti. Il valore corrente e sempre ricostruito
replayando le patch attive sullo snapshot di base.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import ValidationError

from ntruth.corrections.json_patch import (
    JsonPatchError,
    JsonPatchOperation,
    apply_json_patch,
    parse_json_patch,
    parse_pointer,
)
from ntruth.graph.validation import (
    GraphValidationError,
    assert_valid_experiment_block,
)
from ntruth.schemas.core import content_checksum, stable_id
from ntruth.schemas.experiment import Correction, ExperimentBlock

_PROTECTED_ROOTS: frozenset[str] = frozenset(
    {
        "id",
        "document_id",
        "source_file_ids",
        "evidence",
        "versions",
        "corrections",
        "unit_assessments",
        "alerts",
        "questions",
        "data_sufficiency",
    }
)
_RULE_INPUT_ROOTS: frozenset[str] = frozenset(
    {
        "inference_targets",
        "hierarchy",
        "factors",
        "contrasts",
        "endpoints",
        "models",
        "n_statements",
        "processes",
        "contradictions",
    }
)


class CorrectionAction(StrEnum):
    APPLY = "apply"
    UNDO = "undo"
    REDO = "redo"


class CorrectionEngineError(ValueError):
    """Errore base del correction engine."""


class CorrectionValidationError(CorrectionEngineError):
    """La patch produrrebbe un ``ExperimentBlock`` strutturalmente non valido."""


class ProtectedCorrectionPath(CorrectionEngineError):
    """La patch tenta di modificare input, versioni, evidenze o audit trail."""


class DuplicateCorrection(CorrectionEngineError):
    """Un ID di correzione e gia presente nel ledger."""


class CorrectionSequenceError(CorrectionEngineError):
    """La sequenza della correzione non e monotona."""


class NothingToUndo(CorrectionEngineError):
    """Non esiste una correzione attiva da annullare."""


class NothingToRedo(CorrectionEngineError):
    """Non esiste una correzione annullata da riapplicare."""


class LedgerIntegrityError(CorrectionEngineError):
    """Snapshot, record o audit trail non sono piu coerenti fra loro."""


@dataclass(frozen=True, slots=True)
class CorrectionRecord:
    """Snapshot immutabile di una correzione applicata almeno una volta."""

    id: str
    correction_json: str
    operations: tuple[JsonPatchOperation, ...]
    before_checksum: str
    after_checksum: str

    @property
    def correction(self) -> Correction:
        return Correction.model_validate_json(self.correction_json)

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.id,
            "correction": self.correction.model_dump(mode="json"),
            "before_checksum": self.before_checksum,
            "after_checksum": self.after_checksum,
        }


@dataclass(frozen=True, slots=True)
class CorrectionAuditEvent:
    """Evento append-only di navigazione della storia."""

    id: str
    sequence: int
    action: CorrectionAction
    correction_id: str
    before_checksum: str
    after_checksum: str
    active_correction_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "sequence": self.sequence,
            "action": self.action.value,
            "correction_id": self.correction_id,
            "before_checksum": self.before_checksum,
            "after_checksum": self.after_checksum,
            "active_correction_ids": list(self.active_correction_ids),
        }


@dataclass(frozen=True, slots=True)
class CorrectionLedger:
    """Storia immutabile di correzioni e undo/redo per un blocco."""

    _base_json: str
    records: tuple[CorrectionRecord, ...] = ()
    audit_trail: tuple[CorrectionAuditEvent, ...] = ()

    @classmethod
    def start(cls, block: ExperimentBlock) -> CorrectionLedger:
        """Crea un ledger senza mutare il blocco ricevuto."""

        try:
            assert_valid_experiment_block(block)
        except GraphValidationError as exc:
            raise CorrectionValidationError(str(exc)) from exc
        return cls(_base_json=_canonical_json(block.model_dump(mode="json")))

    @property
    def base_block(self) -> ExperimentBlock:
        return ExperimentBlock.model_validate_json(self._base_json)

    @property
    def base_checksum(self) -> str:
        return _scientific_checksum(self.base_block)

    @property
    def active_correction_ids(self) -> tuple[str, ...]:
        active, _ = self._replay_controls()
        return tuple(active)

    @property
    def redo_correction_ids(self) -> tuple[str, ...]:
        _, redo = self._replay_controls()
        return tuple(reversed(redo))

    @property
    def active_changed_roots(self) -> tuple[str, ...]:
        """Campi top-level interessati dalle patch attive, in ordine stabile."""

        records = {item.correction.id: item for item in self.records}
        roots: set[str] = set()
        for correction_id in self.active_correction_ids:
            for operation in records[correction_id].operations:
                for pointer in (operation.path, operation.from_path):
                    if pointer is None:
                        continue
                    tokens = parse_pointer(pointer)
                    if tokens:
                        roots.add(tokens[0])
        return tuple(sorted(roots))

    @property
    def requires_rule_rerun(self) -> bool:
        """Indica che gli output derivati non vanno riusati senza ricalcolo."""

        return bool(set(self.active_changed_roots) & _RULE_INPUT_ROOTS)

    @property
    def next_sequence(self) -> int:
        """Sequenza valida per la prossima correzione append-only."""

        return self._next_correction_sequence()

    @property
    def current_block(self) -> ExperimentBlock:
        self.assert_integrity()
        return self._materialize(self.active_correction_ids)

    @property
    def current_checksum(self) -> str:
        return _scientific_checksum(self.current_block)

    def apply(self, correction: Correction) -> CorrectionLedger:
        """Applica una patch e accoda record + audit event in una nuova istanza."""

        self.assert_integrity()
        existing = {item.id for item in self.base_block.corrections}
        existing.update(item.correction.id for item in self.records)
        if correction.id in existing:
            raise DuplicateCorrection(f"correction id gia presente: {correction.id}")

        expected_sequence = self._next_correction_sequence()
        if correction.sequence != expected_sequence:
            raise CorrectionSequenceError(
                f"sequence attesa {expected_sequence}, ricevuta {correction.sequence}"
            )

        try:
            operations = parse_json_patch(correction.patch)
        except JsonPatchError as exc:
            raise CorrectionValidationError(str(exc)) from exc
        _validate_correction_paths(operations)

        before = self._materialize(self.active_correction_ids)
        before_checksum = _scientific_checksum(before)
        before_payload = before.model_dump(mode="json")

        try:
            patched = apply_json_patch(before_payload, operations)
        except JsonPatchError as exc:
            raise CorrectionValidationError(str(exc)) from exc
        if not isinstance(patched, dict):
            raise CorrectionValidationError("la patch deve produrre un ExperimentBlock JSON")

        patched["corrections"] = [
            *(item.model_dump(mode="json") for item in before.corrections),
            correction.model_dump(mode="json"),
        ]
        candidate = _validate_candidate(patched)
        after_checksum = _scientific_checksum(candidate)

        correction_json = _canonical_json(correction.model_dump(mode="json"))
        record = CorrectionRecord(
            id=stable_id("crr", correction.id, before_checksum, after_checksum, correction_json),
            correction_json=correction_json,
            operations=operations,
            before_checksum=before_checksum,
            after_checksum=after_checksum,
        )
        active_after = (*self.active_correction_ids, correction.id)
        event = _make_audit_event(
            sequence=len(self.audit_trail),
            action=CorrectionAction.APPLY,
            correction_id=correction.id,
            before_checksum=before_checksum,
            after_checksum=after_checksum,
            active_correction_ids=active_after,
        )
        return CorrectionLedger(
            _base_json=self._base_json,
            records=(*self.records, record),
            audit_trail=(*self.audit_trail, event),
        )

    def undo(self) -> CorrectionLedger:
        """Annulla l'ultima patch attiva conservando integralmente la storia."""

        self.assert_integrity()
        active = self.active_correction_ids
        if not active:
            raise NothingToUndo("nessuna correzione attiva")
        target = active[-1]
        before_checksum = _scientific_checksum(self._materialize(active))
        active_after = active[:-1]
        after_checksum = _scientific_checksum(self._materialize(active_after))
        event = _make_audit_event(
            sequence=len(self.audit_trail),
            action=CorrectionAction.UNDO,
            correction_id=target,
            before_checksum=before_checksum,
            after_checksum=after_checksum,
            active_correction_ids=active_after,
        )
        return CorrectionLedger(
            _base_json=self._base_json,
            records=self.records,
            audit_trail=(*self.audit_trail, event),
        )

    def redo(self) -> CorrectionLedger:
        """Riapplica l'ultima patch annullata e accoda un evento di audit."""

        self.assert_integrity()
        active, redo = self._replay_controls()
        if not redo:
            raise NothingToRedo("nessuna correzione da riapplicare")
        target = redo[-1]
        before_checksum = _scientific_checksum(self._materialize(tuple(active)))
        active_after = (*active, target)
        after_checksum = _scientific_checksum(self._materialize(active_after))
        event = _make_audit_event(
            sequence=len(self.audit_trail),
            action=CorrectionAction.REDO,
            correction_id=target,
            before_checksum=before_checksum,
            after_checksum=after_checksum,
            active_correction_ids=active_after,
        )
        return CorrectionLedger(
            _base_json=self._base_json,
            records=self.records,
            audit_trail=(*self.audit_trail, event),
        )

    def integrity_errors(self) -> tuple[str, ...]:
        """Verifica checksum, sequenze e replay senza modificare il ledger."""

        errors: list[str] = []
        try:
            base = self.base_block
            assert_valid_experiment_block(base)
        except (ValidationError, GraphValidationError, ValueError) as exc:
            return (f"base snapshot non valido: {exc}",)

        record_ids = [item.id for item in self.records]
        if len(record_ids) != len(set(record_ids)):
            errors.append("record id duplicato")
        correction_ids = [item.correction.id for item in self.records]
        base_correction_ids = [item.id for item in base.corrections]
        all_correction_ids = [*base_correction_ids, *correction_ids]
        if len(all_correction_ids) != len(set(all_correction_ids)):
            errors.append("correction id duplicato")

        record_by_correction = {item.correction.id: item for item in self.records}
        try:
            self._materialize(())
        except (CorrectionEngineError, ValidationError, JsonPatchError) as exc:
            errors.append(f"registro correzioni non valido: {exc}")

        for record in self.records:
            expected_record_id = stable_id(
                "crr",
                record.correction.id,
                record.before_checksum,
                record.after_checksum,
                record.correction_json,
            )
            if record.id != expected_record_id:
                errors.append(f"record id incoerente: {record.id}")
            try:
                parsed = parse_json_patch(record.correction.patch)
            except JsonPatchError as exc:
                errors.append(f"patch record non valida {record.id}: {exc}")
            else:
                if tuple(item.to_dict() for item in parsed) != tuple(
                    item.to_dict() for item in record.operations
                ):
                    errors.append(f"operazioni record incoerenti: {record.id}")

        active: list[str] = []
        redo: list[str] = []
        applied_counts = {correction_id: 0 for correction_id in record_by_correction}
        for index, event in enumerate(self.audit_trail):
            before_active = tuple(active)
            if event.sequence != index:
                errors.append(
                    f"audit sequence non contigua: attesa {index}, trovata {event.sequence}"
                )
            if event.correction_id not in record_by_correction:
                errors.append(f"audit riferisce correction inesistente: {event.correction_id}")
                continue
            if event.action is CorrectionAction.APPLY:
                applied_counts[event.correction_id] += 1
                if event.correction_id in active:
                    errors.append(f"apply duplicato sulla correction attiva {event.correction_id}")
                active.append(event.correction_id)
                redo.clear()
            elif event.action is CorrectionAction.UNDO:
                if not active or active[-1] != event.correction_id:
                    errors.append(f"undo fuori ordine per {event.correction_id}")
                    continue
                redo.append(active.pop())
            elif event.action is CorrectionAction.REDO:
                if not redo or redo[-1] != event.correction_id:
                    errors.append(f"redo fuori ordine per {event.correction_id}")
                    continue
                active.append(redo.pop())

            if event.active_correction_ids != tuple(active):
                errors.append(f"snapshot active incoerente nell'evento {event.id}")

            expected_event = _make_audit_event(
                sequence=event.sequence,
                action=event.action,
                correction_id=event.correction_id,
                before_checksum=event.before_checksum,
                after_checksum=event.after_checksum,
                active_correction_ids=event.active_correction_ids,
            )
            if event.id != expected_event.id:
                errors.append(f"audit event id incoerente: {event.id}")

            try:
                before_checksum = _scientific_checksum(self._materialize(before_active))
                after_checksum = _scientific_checksum(self._materialize(tuple(active)))
            except (CorrectionEngineError, ValidationError, JsonPatchError) as exc:
                errors.append(f"replay fallito nell'evento {event.id}: {exc}")
                continue
            if event.before_checksum != before_checksum:
                errors.append(f"before checksum incoerente nell'evento {event.id}")
            if event.after_checksum != after_checksum:
                errors.append(f"after checksum incoerente nell'evento {event.id}")
            if event.action is CorrectionAction.APPLY:
                record = record_by_correction[event.correction_id]
                if record.before_checksum != before_checksum:
                    errors.append(f"record before checksum incoerente: {record.id}")
                if record.after_checksum != after_checksum:
                    errors.append(f"record after checksum incoerente: {record.id}")

        for correction_id, count in applied_counts.items():
            if count != 1:
                errors.append(
                    f"correction {correction_id} deve avere un solo evento apply, trovati {count}"
                )

        return tuple(dict.fromkeys(errors))

    def assert_integrity(self) -> None:
        errors = self.integrity_errors()
        if errors:
            raise LedgerIntegrityError("; ".join(errors))

    def _materialize(self, active_ids: tuple[str, ...]) -> ExperimentBlock:
        payload = json.loads(self._base_json)
        records = {item.correction.id: item for item in self.records}
        for correction_id in active_ids:
            record = records.get(correction_id)
            if record is None:
                raise LedgerIntegrityError(f"correction record inesistente: {correction_id}")
            try:
                payload = apply_json_patch(payload, record.operations)
            except JsonPatchError as exc:
                raise LedgerIntegrityError(
                    f"replay fallito per correction {correction_id}: {exc}"
                ) from exc
            if not isinstance(payload, dict):
                raise LedgerIntegrityError("il replay non produce un ExperimentBlock JSON")

        base_corrections = json.loads(self._base_json).get("corrections", [])
        payload["corrections"] = [
            *base_corrections,
            *(item.correction.model_dump(mode="json") for item in self.records),
        ]
        return _validate_candidate(payload)

    def _replay_controls(self) -> tuple[list[str], list[str]]:
        records = {item.correction.id for item in self.records}
        active: list[str] = []
        redo: list[str] = []
        for event in self.audit_trail:
            if event.correction_id not in records:
                raise LedgerIntegrityError(
                    f"audit riferisce correction inesistente: {event.correction_id}"
                )
            if event.action is CorrectionAction.APPLY:
                active.append(event.correction_id)
                redo.clear()
            elif event.action is CorrectionAction.UNDO:
                if not active or active[-1] != event.correction_id:
                    raise LedgerIntegrityError(f"undo fuori ordine: {event.correction_id}")
                redo.append(active.pop())
            elif event.action is CorrectionAction.REDO:
                if not redo or redo[-1] != event.correction_id:
                    raise LedgerIntegrityError(f"redo fuori ordine: {event.correction_id}")
                active.append(redo.pop())
        return active, redo

    def _next_correction_sequence(self) -> int:
        sequences = [item.sequence for item in self.base_block.corrections]
        sequences.extend(item.correction.sequence for item in self.records)
        return max(sequences, default=-1) + 1


def _validate_candidate(payload: dict[str, Any]) -> ExperimentBlock:
    try:
        block = ExperimentBlock.model_validate(payload)
        assert_valid_experiment_block(block)
    except (ValidationError, GraphValidationError) as exc:
        raise CorrectionValidationError(str(exc)) from exc
    return block


def _validate_correction_paths(operations: tuple[JsonPatchOperation, ...]) -> None:
    for operation in operations:
        if operation.op != "test" and _is_protected(operation.path):
            raise ProtectedCorrectionPath(f"path protetto: {operation.path!r}")
        if operation.op in {"move", "copy"}:
            if operation.from_path is None:  # pragma: no cover - parser
                raise JsonPatchError(f"{operation.op}: campo 'from' assente")
            if _is_protected(operation.from_path):
                raise ProtectedCorrectionPath(f"source path protetto: {operation.from_path!r}")


def _is_protected(pointer: str) -> bool:
    tokens = parse_pointer(pointer)
    return not tokens or tokens[0] in _PROTECTED_ROOTS


def _scientific_checksum(block: ExperimentBlock) -> str:
    return content_checksum(block.model_dump(mode="json", exclude={"corrections"}))


def _make_audit_event(
    *,
    sequence: int,
    action: CorrectionAction,
    correction_id: str,
    before_checksum: str,
    after_checksum: str,
    active_correction_ids: tuple[str, ...],
) -> CorrectionAuditEvent:
    event_id = stable_id(
        "cae",
        sequence,
        action.value,
        correction_id,
        before_checksum,
        after_checksum,
        active_correction_ids,
    )
    return CorrectionAuditEvent(
        id=event_id,
        sequence=sequence,
        action=action,
        correction_id=correction_id,
        before_checksum=before_checksum,
        after_checksum=after_checksum,
        active_correction_ids=active_correction_ids,
    )


def _canonical_json(payload: Any) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
