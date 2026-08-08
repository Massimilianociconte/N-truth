"""Thin orchestration for the deterministic PRD v8 scientific lane.

The dependency order is fixed: verified facts -> theory clauses -> verified claims ->
separate adequacy findings -> versioned report resolution.  Parser candidates and v7
Rulebook metadata are not scientific inputs to this lane.
"""

from __future__ import annotations

from ntruth.derivation_theory.contracts import ConformanceBundle, DerivationTheory
from ntruth.derivation_theory.runtime import (
    V8DerivationInput,
    derive_claim_set,
    implementation_rule_ids,
    load_runtime_bundle,
    verify_runtime_bundle,
)
from ntruth.rules.v8_engine import evaluate_design_adequacy
from ntruth.schemas.adequacy import DesignAdequacyFinding
from ntruth.schemas.claims import DerivedClaimSet
from ntruth.schemas.coverage import (
    ProfileCoverageStatement,
    ScenarioCoverage,
    ScenarioCoverageStatus,
)
from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.report_resolution import (
    ReportResolutionOutcome,
    ReportResolutionPolicy,
    ReportResolutionState,
    TrivialExplicitReportResolutionPolicy,
)

V8PipelineRequest = V8DerivationInput


class V8PipelineResult(KernelModel):
    claim_set: DerivedClaimSet
    design_adequacy_findings: tuple[DesignAdequacyFinding, ...]
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
    def scenario_space_complete(self) -> bool:
        return bool(self.scenario_coverages) and all(
            item.status is ScenarioCoverageStatus.EXHAUSTIVE_WITHIN_PROFILE
            for item in self.scenario_coverages
        )


class V8PipelineVerificationError(ValueError):
    """Progressive verification stopped the lane before a downstream stage."""

    def __init__(self, report: object) -> None:
        self.report = report
        super().__init__("PRD v8 pipeline failed progressive deterministic verification")


class V8PipelineConformanceError(ValueError):
    """The pinned Theory/Rulebook/fixture bundle failed its implementation gate."""

    def __init__(self, report: object) -> None:
        self.report = report
        super().__init__("PRD v8 runtime bundle failed Theory/Rulebook conformance")


def run_v8_pipeline(
    request: V8PipelineRequest,
    *,
    theory: DerivationTheory | None = None,
    conformance_bundle: ConformanceBundle | None = None,
    resolution_policy: ReportResolutionPolicy | None = None,
) -> V8PipelineResult:
    """Run the main v8 lane without parser verdicts or Rulebook-derived theory."""

    from ntruth.verifier.v8 import (
        verify_v8_derived_claim_set,
        verify_v8_pipeline_request,
    )

    if theory is not None and conformance_bundle is not None:
        raise ValueError("provide either reviewed theory or a conformance bundle, not both")
    rule_ids = None
    if theory is None:
        bundle = conformance_bundle or load_runtime_bundle()
        conformance = verify_runtime_bundle(bundle)
        if not conformance.passed:
            raise V8PipelineConformanceError(conformance)
        runtime_theory = bundle.theory
        expected_ruleset_version = (
            f"{bundle.rulebook.rulebook_id}-{bundle.rulebook.rulebook_version}"
        )
        if request.runtime_ruleset_version != expected_ruleset_version:
            raise ValueError("request runtime ruleset version does not match the pinned Rulebook")
        rule_ids = implementation_rule_ids(bundle)
    else:
        runtime_theory = theory
    fact_verification = verify_v8_pipeline_request(request, theory=runtime_theory)
    if not fact_verification.passed:
        raise V8PipelineVerificationError(fact_verification)
    if runtime_theory.profile_id != request.query.profile_id:
        raise ValueError("runtime theory and InferentialQuery profile do not match")
    if runtime_theory.theory_version != request.profile_coverage.theory_version:
        raise ValueError("runtime theory and ProfileCoverageStatement version do not match")

    claim_set = derive_claim_set(request, theory=runtime_theory, rule_ids=rule_ids)
    claim_verification = verify_v8_derived_claim_set(
        request,
        claim_set,
        theory=runtime_theory,
    )
    if not claim_verification.passed:
        raise V8PipelineVerificationError(claim_verification)

    findings = evaluate_design_adequacy(request, claim_set)
    policy = resolution_policy or TrivialExplicitReportResolutionPolicy()
    return V8PipelineResult(
        claim_set=claim_set,
        design_adequacy_findings=findings,
        report_resolution=policy.resolve(claim_set),
        profile_coverage=request.profile_coverage,
        scenario_coverages=request.scenario_coverages,
    )


__all__ = [
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
