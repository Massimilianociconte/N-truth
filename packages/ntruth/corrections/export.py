"""Export separato delle correzioni come candidate annotations (FR-030)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ntruth.corrections.engine import CorrectionLedger
from ntruth.schemas.core import content_checksum

CANDIDATE_ARTIFACT_TYPE = "ntruth_candidate_annotations"
CANDIDATE_ARTIFACT_VERSION = "1.0.0"


def candidate_annotations_payload(ledger: CorrectionLedger) -> dict[str, Any]:
    """Crea un artefatto candidate-only; non esiste promozione implicita a gold."""

    ledger.assert_integrity()
    base = ledger.base_block
    active = set(ledger.active_correction_ids)
    candidates: list[dict[str, Any]] = []

    for correction in base.corrections:
        candidates.append(
            {
                "record_id": None,
                "correction": correction.model_dump(mode="json"),
                "active": True,
                "imported_without_ledger_event": True,
                "gold_status": "not_gold",
                "training_eligible": False,
                "requires_adjudication": True,
            }
        )

    for record in ledger.records:
        correction = record.correction
        candidates.append(
            {
                **record.to_dict(),
                "active": correction.id in active,
                "imported_without_ledger_event": False,
                "gold_status": "not_gold",
                "training_eligible": False,
                "requires_adjudication": True,
            }
        )

    audit_trail = [event.to_dict() for event in ledger.audit_trail]
    history_state = _history_state(ledger)
    payload: dict[str, Any] = {
        "artifact_type": CANDIDATE_ARTIFACT_TYPE,
        "artifact_version": CANDIDATE_ARTIFACT_VERSION,
        "gold_status": "not_gold",
        "training_eligible": False,
        "requires_separate_curation": True,
        "source": {
            "block_id": base.id,
            "document_id": base.document_id,
            "source_file_ids": list(base.source_file_ids),
            "base_checksum": ledger.base_checksum,
            "current_checksum": ledger.current_checksum,
            "versions": base.versions.model_dump(mode="json"),
        },
        "active_correction_ids": list(ledger.active_correction_ids),
        "redo_correction_ids": list(ledger.redo_correction_ids),
        "active_changed_roots": list(ledger.active_changed_roots),
        "requires_rule_rerun": ledger.requires_rule_rerun,
        "candidate_annotations": candidates,
        "candidate_annotations_checksum": content_checksum(candidates),
        "audit_trail": audit_trail,
        "audit_checksum": content_checksum(audit_trail),
        "history_state": history_state,
    }
    payload["content_checksum"] = content_checksum(payload)
    return payload


def _history_state(ledger: CorrectionLedger) -> dict[str, Any]:
    """Riassume navigabilita e branching senza scartare l'audit append-only."""

    redo_depth = 0
    branching_occurred = False
    for event in ledger.audit_trail:
        if event.action.value == "undo":
            redo_depth += 1
        elif event.action.value == "redo":
            redo_depth -= 1
        else:
            if redo_depth:
                branching_occurred = True
            redo_depth = 0

    return {
        "head_action": ledger.audit_trail[-1].action.value if ledger.audit_trail else None,
        "undo_available": bool(ledger.active_correction_ids),
        "redo_available": bool(ledger.redo_correction_ids),
        "branching_occurred": branching_occurred,
        "audit_event_count": len(ledger.audit_trail),
    }


def write_candidate_annotations(ledger: CorrectionLedger, path: Path) -> Path:
    """Scrive soltanto l'artefatto candidate, mai un manifest gold o training."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            candidate_annotations_payload(ledger),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path
