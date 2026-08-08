"""Fail-closed progressive verifier for the PRD v8 deterministic lane."""

from __future__ import annotations

from enum import StrEnum

from ntruth.derivation_theory.contracts import DerivationTheory
from ntruth.derivation_theory.runtime import V8DerivationInput, load_runtime_theory
from ntruth.schemas.claims import DerivedClaimSet
from ntruth.schemas.graph_v8 import V8GraphNodeType
from ntruth.schemas.kernel import KernelModel, NonBlankStr


class V8VerificationCode(StrEnum):
    MISSING_EXPLICIT_PREDICATE = "MISSING_EXPLICIT_PREDICATE"
    MISSING_SUPPORT_DESCRIPTOR = "MISSING_SUPPORT_DESCRIPTOR"
    CROSS_QUERY_SCOPE = "CROSS_QUERY_SCOPE"
    GRAPH_SCOPE_MISMATCH = "GRAPH_SCOPE_MISMATCH"
    CAUSAL_SCOPE_MISMATCH = "CAUSAL_SCOPE_MISMATCH"
    PROFILE_SCOPE_MISMATCH = "PROFILE_SCOPE_MISMATCH"
    CLAIM_SCOPE_MISMATCH = "CLAIM_SCOPE_MISMATCH"
    CLAIM_CLAUSE_MISMATCH = "CLAIM_CLAUSE_MISMATCH"
    CLAIM_PROOF_MISMATCH = "CLAIM_PROOF_MISMATCH"


class V8VerificationIssue(KernelModel):
    code: V8VerificationCode
    stage: NonBlankStr
    message: NonBlankStr
    theory_clause_id: NonBlankStr | None = None
    predicate_id: NonBlankStr | None = None
    claim_id: NonBlankStr | None = None


class V8VerificationReport(KernelModel):
    passed: bool
    highest_completed_stage: NonBlankStr
    issues: tuple[V8VerificationIssue, ...]


def verify_v8_pipeline_request(
    request: V8DerivationInput,
    *,
    theory: DerivationTheory | None = None,
) -> V8VerificationReport:
    """Validate graph/query/fact closure before any scientific derivation runs."""

    issues: list[V8VerificationIssue] = []
    theory = theory or load_runtime_theory()
    block_nodes = {
        node.node_id
        for node in request.graph.nodes
        if node.node_type is V8GraphNodeType.EXPERIMENT_BLOCK
    }
    query_nodes = {
        node.node_id
        for node in request.graph.nodes
        if node.node_type is V8GraphNodeType.INFERENTIAL_QUERY
    }
    if request.experiment_block_id not in block_nodes or request.query.id not in query_nodes:
        issues.append(
            V8VerificationIssue(
                code=V8VerificationCode.GRAPH_SCOPE_MISMATCH,
                stage="FACT_VERIFICATION",
                message="Graph must contain the requested block and InferentialQuery.",
            )
        )
    if (
        request.causal_aggregate.experiment_block_id != request.experiment_block_id
        or request.causal_aggregate.causal_context.inferential_query_id != request.query.id
    ):
        issues.append(
            V8VerificationIssue(
                code=V8VerificationCode.CAUSAL_SCOPE_MISMATCH,
                stage="FACT_VERIFICATION",
                message="Causal aggregate must share block and query scope.",
            )
        )
    if (
        request.profile_coverage.profile_id != request.query.profile_id
        or request.profile_coverage.theory_version != theory.theory_version
    ):
        issues.append(
            V8VerificationIssue(
                code=V8VerificationCode.PROFILE_SCOPE_MISMATCH,
                stage="FACT_VERIFICATION",
                message="Profile coverage must match query profile and runtime theory.",
            )
        )

    for predicate_id, value in request.predicate_values.items():
        if value.query_scope_id is not None and value.query_scope_id != request.query.id:
            issues.append(
                V8VerificationIssue(
                    code=V8VerificationCode.CROSS_QUERY_SCOPE,
                    stage="FACT_VERIFICATION",
                    message=f"Predicate {predicate_id} has a cross-query scope.",
                    predicate_id=predicate_id,
                )
            )

    for clause in theory.clauses:
        if clause.clause_id not in request.support_by_clause:
            issues.append(
                V8VerificationIssue(
                    code=V8VerificationCode.MISSING_SUPPORT_DESCRIPTOR,
                    stage="FACT_VERIFICATION",
                    message=f"Clause {clause.clause_id} lacks an explicit support descriptor.",
                    theory_clause_id=clause.clause_id,
                )
            )
        for requirement in clause.required_predicates:
            if requirement.predicate_id not in request.predicate_values:
                issues.append(
                    V8VerificationIssue(
                        code=V8VerificationCode.MISSING_EXPLICIT_PREDICATE,
                        stage="FACT_VERIFICATION",
                        message=(
                            "Missing facts must be represented by an explicit KnowledgeState: "
                            f"{requirement.predicate_id}."
                        ),
                        theory_clause_id=clause.clause_id,
                        predicate_id=requirement.predicate_id,
                    )
                )

    return V8VerificationReport(
        passed=not issues,
        highest_completed_stage="FACT_VERIFICATION",
        issues=tuple(issues),
    )


def verify_v8_derived_claim_set(
    request: V8DerivationInput,
    claim_set: DerivedClaimSet,
    *,
    theory: DerivationTheory,
) -> V8VerificationReport:
    """Verify the theory-clause and proof boundary before adequacy evaluation."""

    issues: list[V8VerificationIssue] = []
    clauses = {clause.clause_id: clause for clause in theory.clauses}
    if claim_set.inferential_query_id != request.query.id:
        issues.append(
            V8VerificationIssue(
                code=V8VerificationCode.CLAIM_SCOPE_MISMATCH,
                stage="CLAIM_VERIFICATION",
                message="DerivedClaimSet and request query scopes differ.",
            )
        )
    for claim in claim_set.claims:
        if claim.inferential_query_id != request.query.id:
            issues.append(
                V8VerificationIssue(
                    code=V8VerificationCode.CLAIM_SCOPE_MISMATCH,
                    stage="CLAIM_VERIFICATION",
                    message="DerivedClaim has a cross-query scope.",
                    claim_id=claim.claim_id,
                )
            )
        if len(claim.theory_clauses) != 1 or claim.theory_clauses[0] not in clauses:
            issues.append(
                V8VerificationIssue(
                    code=V8VerificationCode.CLAIM_CLAUSE_MISMATCH,
                    stage="CLAIM_VERIFICATION",
                    message="DerivedClaim does not reference exactly one runtime theory clause.",
                    claim_id=claim.claim_id,
                )
            )
            continue
        clause = clauses[claim.theory_clauses[0]]
        expected = tuple(item.predicate_id for item in clause.required_predicates)
        proof_predicates = tuple(
            reference.predicate_id
            for step in claim.proof_trace
            for reference in step.predicate_references
        )
        if (
            claim.claim_type not in clause.output_claim_types
            or claim.required_predicates != expected
        ):
            issues.append(
                V8VerificationIssue(
                    code=V8VerificationCode.CLAIM_CLAUSE_MISMATCH,
                    stage="CLAIM_VERIFICATION",
                    message="Claim output or required predicates diverge from its theory clause.",
                    theory_clause_id=clause.clause_id,
                    claim_id=claim.claim_id,
                )
            )
        if proof_predicates != expected:
            issues.append(
                V8VerificationIssue(
                    code=V8VerificationCode.CLAIM_PROOF_MISMATCH,
                    stage="CLAIM_VERIFICATION",
                    message="Proof trace does not exactly reproduce clause-required predicates.",
                    theory_clause_id=clause.clause_id,
                    claim_id=claim.claim_id,
                )
            )
    return V8VerificationReport(
        passed=not issues,
        highest_completed_stage=("CLAIM_VERIFICATION" if not issues else "THEORY_DERIVATION"),
        issues=tuple(issues),
    )


__all__ = [
    "V8VerificationCode",
    "V8VerificationIssue",
    "V8VerificationReport",
    "verify_v8_derived_claim_set",
    "verify_v8_pipeline_request",
]
