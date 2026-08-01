"""Correzioni human-in-the-loop, audit append-only ed export candidate."""

from ntruth.corrections.engine import (
    CorrectionAction,
    CorrectionAuditEvent,
    CorrectionEngineError,
    CorrectionLedger,
    CorrectionRecord,
    CorrectionSequenceError,
    CorrectionValidationError,
    DuplicateCorrection,
    LedgerIntegrityError,
    NothingToRedo,
    NothingToUndo,
    ProtectedCorrectionPath,
)
from ntruth.corrections.export import (
    CANDIDATE_ARTIFACT_TYPE,
    candidate_annotations_payload,
    write_candidate_annotations,
)
from ntruth.corrections.json_patch import (
    JsonPatchError,
    JsonPatchOperation,
    JsonPatchTestFailed,
    apply_json_patch,
    parse_json_patch,
)
from ntruth.corrections.recalculate import (
    CorrectionRecalculation,
    recalculate_corrected_block,
)

__all__ = [
    "CANDIDATE_ARTIFACT_TYPE",
    "CorrectionAction",
    "CorrectionAuditEvent",
    "CorrectionEngineError",
    "CorrectionLedger",
    "CorrectionRecalculation",
    "CorrectionRecord",
    "CorrectionSequenceError",
    "CorrectionValidationError",
    "DuplicateCorrection",
    "JsonPatchError",
    "JsonPatchOperation",
    "JsonPatchTestFailed",
    "LedgerIntegrityError",
    "NothingToRedo",
    "NothingToUndo",
    "ProtectedCorrectionPath",
    "apply_json_patch",
    "candidate_annotations_payload",
    "parse_json_patch",
    "recalculate_corrected_block",
    "write_candidate_annotations",
]
