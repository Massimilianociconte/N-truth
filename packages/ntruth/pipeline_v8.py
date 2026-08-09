"""Thin bundle-gated orchestration for the deterministic PRD v8 lane."""

from __future__ import annotations

from ntruth.derivation_theory.contracts import ConformanceBundle
from ntruth.derivation_theory.runtime import (
    V8DerivationInput,
    build_execution_manifest,
    derive_claim_set,
    require_reviewed_evaluator_bundle,
    verify_runtime_bundle,
)
from ntruth.rules.v8_engine import evaluate_design_adequacy
from ntruth.runtime_tree import ExactRuntimeTreeError, canonicalize_exact_model
from ntruth.schemas.adequacy import DesignAdequacyEvaluation, DesignAdequacyFinding
from ntruth.schemas.claims import DerivedClaimSet
from ntruth.schemas.coverage import (
    PROFILE_COVERAGE_REVIEW_ISSUE_ID,
    ProfileCoverageStatement,
    ScenarioCoverage,
    ScenarioCoverageStatus,
)
from ntruth.schemas.execution import V8ExecutionManifest
from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.report_resolution import (
    ReportResolutionOutcome,
    ReportResolutionPolicy,
    ReportResolutionState,
    TrivialExplicitReportResolutionPolicy,
)

V8PipelineRequest = V8DerivationInput


class V8PipelineResult(KernelModel):
    execution_manifest: V8ExecutionManifest
    claim_set: DerivedClaimSet
    design_adequacy_evaluations: tuple[DesignAdequacyEvaluation, ...]
    report_resolution: ReportResolutionOutcome
    profile_coverage: ProfileCoverageStatement
    scenario_coverages: tuple[ScenarioCoverage, ...]
    stage_order: tuple[NonBlankStr, ...] = (
        "FACT_VERIFICATION",
        "THEORY_DERIVATION",
        "CLAIM_VERIFICATION",
        "RULE_ADEQUACY",
        "REPORT_RESOLUTION",
    )

    @property
    def design_adequacy_findings(self) -> tuple[DesignAdequacyEvaluation, ...]:
        """Deprecated name; evaluations are always non-empty and epistemic."""

        return self.design_adequacy_evaluations

    @property
    def scenario_space_complete(self) -> bool:
        if self.profile_coverage.contract_review.issue_id == PROFILE_COVERAGE_REVIEW_ISSUE_ID:
            return False
        return bool(self.scenario_coverages) and all(
            item.status is ScenarioCoverageStatus.EXHAUSTIVE_WITHIN_PROFILE
            for item in self.scenario_coverages
        )


class V8PipelineVerificationError(ValueError):
    def __init__(self, report: object) -> None:
        self.report = report
        super().__init__("PRD v8 pipeline failed progressive deterministic verification")


class V8PipelineConformanceError(ValueError):
    def __init__(self, report: object) -> None:
        self.report = report
        super().__init__("PRD v8 runtime bundle failed Theory/Rulebook conformance")


def run_v8_pipeline(
    request: V8PipelineRequest,
    *,
    conformance_bundle: ConformanceBundle,
    resolution_policy: ReportResolutionPolicy | None = None,
) -> V8PipelineResult:
    """Run only with one complete, content-addressed, conformant bundle."""

    from ntruth.verifier.v8 import (
        _runtime_tree_failure,
        verify_v8_derived_claim_set,
        verify_v8_pipeline_request,
    )

    try:
        request = canonicalize_exact_model(
            request,
            V8DerivationInput,
            path="$.request",
        )
        conformance_bundle = canonicalize_exact_model(
            conformance_bundle,
            ConformanceBundle,
            path="$.conformance_bundle",
        )
    except ExactRuntimeTreeError as error:
        raise V8PipelineVerificationError(_runtime_tree_failure()) from error
    require_reviewed_evaluator_bundle(conformance_bundle)
    conformance = verify_runtime_bundle(conformance_bundle)
    if not conformance.passed:
        raise V8PipelineConformanceError(conformance)
    manifest = build_execution_manifest(conformance_bundle, conformance)
    fact_verification = verify_v8_pipeline_request(
        request,
        conformance_bundle=conformance_bundle,
    )
    if not fact_verification.passed:
        raise V8PipelineVerificationError(fact_verification)
    claim_set = derive_claim_set(
        request,
        conformance_bundle=conformance_bundle,
        execution_manifest=manifest,
    )
    claim_verification = verify_v8_derived_claim_set(
        request,
        claim_set,
        conformance_bundle=conformance_bundle,
        execution_manifest=manifest,
    )
    if not claim_verification.passed:
        raise V8PipelineVerificationError(claim_verification)
    evaluations = evaluate_design_adequacy(
        request,
        claim_set,
        conformance_bundle=conformance_bundle,
        execution_manifest=manifest,
    )
    policy = resolution_policy or TrivialExplicitReportResolutionPolicy()
    return V8PipelineResult(
        execution_manifest=manifest,
        claim_set=claim_set,
        design_adequacy_evaluations=evaluations,
        report_resolution=policy.resolve(claim_set),
        profile_coverage=request.profile_coverage,
        scenario_coverages=request.scenario_coverages,
    )


__all__ = [
    "DesignAdequacyEvaluation",
    "DesignAdequacyFinding",
    "ProfileCoverageStatement",
    "ReportResolutionOutcome",
    "ReportResolutionPolicy",
    "ReportResolutionState",
    "ScenarioCoverage",
    "ScenarioCoverageStatus",
    "V8PipelineConformanceError",
    "V8PipelineRequest",
    "V8PipelineResult",
    "V8PipelineVerificationError",
    "run_v8_pipeline",
]
