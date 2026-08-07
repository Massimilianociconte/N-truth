"""Verifica hard, semantic e policy degli output scientifici del PRD v6."""

from ntruth.verifier.hard import (
    HardVerificationResult,
    VerificationStatus,
    verify_block,
)
from ntruth.verifier.output_policy import (
    OutputPolicyViolation,
    apply_output_policy,
    apply_rule_evaluation_output_policy,
    output_policy_violations,
)
from ntruth.verifier.semantic import (
    SemanticBackend,
    SemanticCheck,
    SemanticCheckSeverity,
    SemanticStatus,
    SemanticVerificationResult,
    semantic_to_stage_checks,
    verify_semantic,
)
from ntruth.verifier.validation_stack import (
    AUTHOR_ASSERTION_ALONE_CODE,
    EVIDENCE_SUPPORT_EMPTY_CODE,
    EVIDENCE_SUPPORT_PASS_CODE,
    LayerOutcome,
    LayerResult,
    ValidationLayer,
    ValidationStackReport,
    build_validation_stack_report,
    evidence_support_from_types,
)

__all__ = [
    "AUTHOR_ASSERTION_ALONE_CODE",
    "EVIDENCE_SUPPORT_EMPTY_CODE",
    "EVIDENCE_SUPPORT_PASS_CODE",
    "HardVerificationResult",
    "LayerOutcome",
    "LayerResult",
    "OutputPolicyViolation",
    "SemanticBackend",
    "SemanticCheck",
    "SemanticCheckSeverity",
    "SemanticStatus",
    "SemanticVerificationResult",
    "ValidationLayer",
    "ValidationStackReport",
    "VerificationStatus",
    "apply_output_policy",
    "apply_rule_evaluation_output_policy",
    "build_validation_stack_report",
    "evidence_support_from_types",
    "output_policy_violations",
    "semantic_to_stage_checks",
    "verify_block",
    "verify_semantic",
]
