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
from ntruth.corrections.v8 import (
    DirectDerivedClaimPatchError,
    ReDerivationEvent,
    RuleChallengeOutcomeReviewRequired,
    V8ReDerivationResult,
    apply_v8_patch,
    rederive_after_rule_challenge,
    reject_direct_derived_claim_patch,
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
    "DirectDerivedClaimPatchError",
    "DuplicateCorrection",
    "JsonPatchError",
    "JsonPatchOperation",
    "JsonPatchTestFailed",
    "LedgerIntegrityError",
    "NothingToRedo",
    "NothingToUndo",
    "ProtectedCorrectionPath",
    "ReDerivationEvent",
    "RuleChallengeOutcomeReviewRequired",
    "V8ReDerivationResult",
    "apply_json_patch",
    "apply_v8_patch",
    "candidate_annotations_payload",
    "parse_json_patch",
    "recalculate_corrected_block",
    "rederive_after_rule_challenge",
    "reject_direct_derived_claim_patch",
    "write_candidate_annotations",
]
