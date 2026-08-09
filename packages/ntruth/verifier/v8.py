"""Fail-closed progressive verifier for PRD v8 inputs, pins and claims."""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Any

from ntruth.derivation_theory.contracts import ConformanceBundle
from ntruth.derivation_theory.loader import canonical_checksum
from ntruth.derivation_theory.runtime import (
    V8DerivationInput,
    build_execution_manifest,
    derive_claim_set,
    verify_runtime_bundle,
)
from ntruth.runtime_tree import ExactRuntimeTreeError, canonicalize_exact_model
from ntruth.schemas.claims import DerivedClaimSet
from ntruth.schemas.count_registry import (
    CanonicalCountKind,
    CanonicalCountRecord,
    CountQuantifier,
)
from ntruth.schemas.execution import V8ExecutionManifest
from ntruth.schemas.graph_v8 import V8GraphNodeType, V8GraphRelation, V8GraphRelationType
from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue


class V8VerificationCode(StrEnum):
    RUNTIME_TREE_MISMATCH = "RUNTIME_TREE_MISMATCH"
    MISSING_EXPLICIT_PREDICATE = "MISSING_EXPLICIT_PREDICATE"
    MISSING_SUPPORT_DESCRIPTOR = "MISSING_SUPPORT_DESCRIPTOR"
    CROSS_QUERY_SCOPE = "CROSS_QUERY_SCOPE"
    GRAPH_SCOPE_MISMATCH = "GRAPH_SCOPE_MISMATCH"
    GRAPH_TOPOLOGY_MISMATCH = "GRAPH_TOPOLOGY_MISMATCH"
    CAUSAL_SCOPE_MISMATCH = "CAUSAL_SCOPE_MISMATCH"
    PROFILE_SCOPE_MISMATCH = "PROFILE_SCOPE_MISMATCH"
    PROFILE_COVERAGE_INCOMPLETE = "PROFILE_COVERAGE_INCOMPLETE"
    SCENARIO_COVERAGE_MISMATCH = "SCENARIO_COVERAGE_MISMATCH"
    COUNT_SCOPE_MISMATCH = "COUNT_SCOPE_MISMATCH"
    VERSION_PIN_MISMATCH = "VERSION_PIN_MISMATCH"
    EXECUTION_MANIFEST_MISMATCH = "EXECUTION_MANIFEST_MISMATCH"
    CLAIM_SCOPE_MISMATCH = "CLAIM_SCOPE_MISMATCH"
    CLAIM_CLAUSE_MISMATCH = "CLAIM_CLAUSE_MISMATCH"
    CLAIM_PROOF_MISMATCH = "CLAIM_PROOF_MISMATCH"
    CLAIM_SUPPORT_MISMATCH = "CLAIM_SUPPORT_MISMATCH"
    CLAIM_COVERAGE_MISMATCH = "CLAIM_COVERAGE_MISMATCH"
    CLAIM_OUTPUT_MISMATCH = "CLAIM_OUTPUT_MISMATCH"
    BUNDLE_CONFORMANCE_FAILED = "BUNDLE_CONFORMANCE_FAILED"


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
    failed_stage: NonBlankStr | None = None
    issues: tuple[V8VerificationIssue, ...]


def _fact_issue(
    code: V8VerificationCode,
    message: str,
    *,
    clause_id: str | None = None,
    predicate_id: str | None = None,
) -> V8VerificationIssue:
    return V8VerificationIssue(
        code=code,
        stage="FACT_VERIFICATION",
        message=message,
        theory_clause_id=clause_id,
        predicate_id=predicate_id,
    )


def _runtime_tree_failure() -> V8VerificationReport:
    return V8VerificationReport(
        passed=False,
        highest_completed_stage="NONE",
        failed_stage="FACT_VERIFICATION",
        issues=(
            _fact_issue(
                V8VerificationCode.RUNTIME_TREE_MISMATCH,
                "Request or conformance bundle is not an exact canonical runtime tree.",
            ),
        ),
    )


def _canonical_runtime_inputs(
    request: object,
    conformance_bundle: object,
) -> tuple[V8DerivationInput, ConformanceBundle] | None:
    try:
        canonical_request = canonicalize_exact_model(
            request,
            V8DerivationInput,
            path="$.request",
        )
        canonical_bundle = canonicalize_exact_model(
            conformance_bundle,
            ConformanceBundle,
            path="$.conformance_bundle",
        )
    except ExactRuntimeTreeError:
        return None
    return canonical_request, canonical_bundle


def _graph_topology_issues(request: V8DerivationInput) -> tuple[str, ...]:
    graph = request.graph
    nodes_by_id = {node.node_id: node for node in graph.nodes}
    errors: list[str] = []
    if any(relation.source_node_id == relation.target_node_id for relation in graph.relations):
        errors.append("Graph relations cannot be self-referential")

    structural_types = {
        V8GraphRelationType.NESTED_IN,
        V8GraphRelationType.CONTAINED_IN,
        V8GraphRelationType.DERIVED_FROM,
    }
    adjacency: dict[str, set[str]] = {node_id: set() for node_id in nodes_by_id}
    incoming: dict[str, int] = {node_id: 0 for node_id in nodes_by_id}
    for relation in graph.relations:
        if relation.relation_type not in structural_types:
            continue
        if relation.target_node_id not in adjacency[relation.source_node_id]:
            adjacency[relation.source_node_id].add(relation.target_node_id)
            incoming[relation.target_node_id] += 1
    ready = [node_id for node_id, degree in incoming.items() if degree == 0]
    visited = 0
    while ready:
        node_id = ready.pop()
        visited += 1
        for target_id in adjacency[node_id]:
            incoming[target_id] -= 1
            if incoming[target_id] == 0:
                ready.append(target_id)
    if visited != len(nodes_by_id):
        errors.append("NESTED_IN/CONTAINED_IN/DERIVED_FROM relations must be acyclic")

    query_ids = {
        node.node_id for node in graph.nodes if node.node_type is V8GraphNodeType.INFERENTIAL_QUERY
    }
    block_ids = {
        node.node_id for node in graph.nodes if node.node_type is V8GraphNodeType.EXPERIMENT_BLOCK
    }
    links_by_query: dict[str, list[V8GraphRelation]] = {query_id: [] for query_id in query_ids}
    for relation in graph.relations:
        if (
            relation.relation_type is V8GraphRelationType.NESTED_IN
            and relation.source_node_id in query_ids
            and relation.target_node_id in block_ids
        ):
            links_by_query[relation.source_node_id].append(relation)
    if any(len(relations) != 1 for relations in links_by_query.values()):
        errors.append("Each InferentialQuery requires exactly one NESTED_IN block binding")
    current_links = links_by_query.get(request.query.id, [])
    if len(current_links) == 1:
        link = current_links[0]
        if (
            link.target_node_id != request.experiment_block_id
            or link.query_scope.knowledge_state is not KnowledgeState.PRESENT
            or link.query_scope.value != request.query.id
            or link.factor_scope.knowledge_state is not KnowledgeState.NOT_APPLICABLE
            or link.decisive_attributes.knowledge_state is not KnowledgeState.NOT_APPLICABLE
        ):
            errors.append("InferentialQuery NESTED_IN binding has incompatible block or scope")
    return tuple(errors)


def _scientific_value_signature(value: KnowledgeValue[Any]) -> tuple[str, str]:
    """Compare epistemic state and value while excluding provenance metadata."""

    payload = value.model_dump(mode="json", include={"value", "conflicting_values"})
    return value.knowledge_state.value, canonical_checksum(payload)


def _present_signature(value: object) -> tuple[str, str]:
    return KnowledgeState.PRESENT.value, canonical_checksum(
        {"value": value, "conflicting_values": []}
    )


def _count_scope_issues(
    request: V8DerivationInput,
    record: CanonicalCountRecord,
    kind: CanonicalCountKind,
) -> tuple[str, ...]:
    """Join all ten count-scope dimensions to independent request facts."""

    unit_predicate = {
        CanonicalCountKind.EXPERIMENTAL_UNIT_COUNT: "candidate_unit",
        CanonicalCountKind.BIOLOGICAL_SOURCE_COUNT: "biological_source_unit_type",
    }[kind]
    predicate_scope = {
        "unit_type": unit_predicate,
        "group_id": "group_or_paired_set",
        "cohort_id": "count_cohort_id",
        "lifecycle_phase": "lifecycle_phase",
        "condition": "count_condition",
    }
    expected: dict[str, tuple[str, str] | None] = {
        field_name: (
            _scientific_value_signature(request.predicate_values[predicate_id])
            if predicate_id in request.predicate_values
            else None
        )
        for field_name, predicate_id in predicate_scope.items()
    }
    expected.update(
        {
            "factor_id": _present_signature(request.query.factor_id),
            "contrast_id": _present_signature(request.query.contrast_id),
            "endpoint_id": _present_signature(request.query.endpoint_id),
            "timepoint_id": _scientific_value_signature(request.query.timepoint_id),
            "population_scope": _scientific_value_signature(request.query.inference_population),
        }
    )
    errors: list[str] = []
    for field_name, expected_signature in expected.items():
        if expected_signature is None:
            errors.append(f"{field_name} lacks an independent request predicate")
            continue
        actual_signature = _scientific_value_signature(getattr(record.scope, field_name))
        if actual_signature != expected_signature:
            errors.append(f"{field_name} differs from the request scientific scope")

    instances_predicate = {
        CanonicalCountKind.EXPERIMENTAL_UNIT_COUNT: "experimental_unit_instances",
        CanonicalCountKind.BIOLOGICAL_SOURCE_COUNT: "biological_source_instances",
    }[kind]
    instances = request.predicate_values.get(instances_predicate)
    if (
        record.quantifier is CountQuantifier.EXACT
        and record.value.knowledge_state is KnowledgeState.PRESENT
        and isinstance(record.value.value, int)
    ):
        if (
            instances is None
            or instances.knowledge_state is not KnowledgeState.PRESENT
            or not isinstance(instances.value, Sequence)
            or isinstance(instances.value, (str, bytes, bytearray))
        ):
            errors.append(f"{instances_predicate} lacks explicit instance identities")
        else:
            distinct_instances = {
                canonical_checksum({"typed_instance_id": item}) for item in instances.value
            }
            if len(distinct_instances) != record.value.value:
                errors.append(
                    f"{instances_predicate} cardinality differs from the exact count value"
                )
    return tuple(errors)


def verify_v8_pipeline_request(
    request: V8DerivationInput,
    *,
    conformance_bundle: ConformanceBundle,
) -> V8VerificationReport:
    """Close graph/query/count/coverage/version facts before derivation."""

    canonical = _canonical_runtime_inputs(request, conformance_bundle)
    if canonical is None:
        return _runtime_tree_failure()
    request, conformance_bundle = canonical
    issues: list[V8VerificationIssue] = []
    theory = conformance_bundle.theory
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
            _fact_issue(
                V8VerificationCode.GRAPH_SCOPE_MISMATCH,
                "Graph must contain the requested block and InferentialQuery.",
            )
        )
    for mismatch in _graph_topology_issues(request):
        issues.append(
            _fact_issue(
                V8VerificationCode.GRAPH_TOPOLOGY_MISMATCH,
                mismatch,
            )
        )
    if (
        request.causal_aggregate.experiment_block_id != request.experiment_block_id
        or request.causal_aggregate.causal_context.inferential_query_id != request.query.id
    ):
        issues.append(
            _fact_issue(
                V8VerificationCode.CAUSAL_SCOPE_MISMATCH,
                "Causal aggregate must share block and query scope.",
            )
        )
    profile = request.profile_coverage
    closure = conformance_bundle.profile_closure
    if (
        profile.profile_id != theory.profile_id
        or profile.profile_id != request.query.profile_id
        or profile.profile_version != theory.profile_version
        or profile.profile_version != closure.profile_version
        or profile.theory_version != theory.theory_version
        or profile.predicate_closure_argument_id != closure.asset_id
    ):
        issues.append(
            _fact_issue(
                V8VerificationCode.PROFILE_SCOPE_MISMATCH,
                "Profile coverage must pin query, Theory and predicate-closure asset.",
            )
        )
    required_predicates = {
        item.predicate_id for clause in theory.clauses for item in clause.required_predicates
    }
    covered = set(profile.covered_predicate_ids)
    if not required_predicates.issubset(covered) or not covered.issubset(
        set(closure.candidate_predicate_ids)
    ):
        issues.append(
            _fact_issue(
                V8VerificationCode.PROFILE_COVERAGE_INCOMPLETE,
                "Profile coverage must contain every Theory predicate and remain within the "
                "pinned closure candidate set.",
            )
        )
    clause_ids = {clause.clause_id for clause in theory.clauses}
    for coverage in request.scenario_coverages:
        if (
            coverage.profile_id != theory.profile_id
            or coverage.theory_version != theory.theory_version
            or not set(coverage.emitting_clause_ids).issubset(clause_ids)
        ):
            issues.append(
                _fact_issue(
                    V8VerificationCode.SCENARIO_COVERAGE_MISMATCH,
                    "ScenarioCoverage must reference this profile, Theory and real clauses.",
                )
            )
    expected_ruleset = (
        f"{conformance_bundle.rulebook.rulebook_id}-{conformance_bundle.rulebook.rulebook_version}"
    )
    if request.runtime_ruleset_version != expected_ruleset:
        issues.append(
            _fact_issue(
                V8VerificationCode.VERSION_PIN_MISMATCH,
                "Request ruleset version must equal the verified Rulebook ID/version.",
            )
        )
    for predicate_id, value in request.predicate_values.items():
        if value.query_scope_id is not None and value.query_scope_id != request.query.id:
            issues.append(
                _fact_issue(
                    V8VerificationCode.CROSS_QUERY_SCOPE,
                    f"Predicate {predicate_id} has a cross-query scope.",
                    predicate_id=predicate_id,
                )
            )
    for clause in theory.clauses:
        if clause.clause_id not in request.support_by_clause:
            issues.append(
                _fact_issue(
                    V8VerificationCode.MISSING_SUPPORT_DESCRIPTOR,
                    f"Clause {clause.clause_id} lacks an explicit support descriptor.",
                    clause_id=clause.clause_id,
                )
            )
        for requirement in clause.required_predicates:
            if requirement.predicate_id not in request.predicate_values:
                issues.append(
                    _fact_issue(
                        V8VerificationCode.MISSING_EXPLICIT_PREDICATE,
                        "Missing facts require an explicit KnowledgeState: "
                        f"{requirement.predicate_id}.",
                        clause_id=clause.clause_id,
                        predicate_id=requirement.predicate_id,
                    )
                )
    count_records = {record.count_id: record for record in request.count_registry.records}
    for count_id, kind in (
        (
            request.experimental_unit_count_record_id,
            CanonicalCountKind.EXPERIMENTAL_UNIT_COUNT,
        ),
        (
            request.biological_source_count_record_id,
            CanonicalCountKind.BIOLOGICAL_SOURCE_COUNT,
        ),
    ):
        record = count_records.get(count_id)
        if record is None or record.kind is not kind or record.scope.query_id != request.query.id:
            issues.append(
                _fact_issue(
                    V8VerificationCode.COUNT_SCOPE_MISMATCH,
                    f"{count_id} must identify one {kind.value} record in this query scope.",
                )
            )
            continue
        for mismatch in _count_scope_issues(request, record, kind):
            issues.append(
                _fact_issue(
                    V8VerificationCode.COUNT_SCOPE_MISMATCH,
                    f"{count_id}: {mismatch}.",
                )
            )
    return V8VerificationReport(
        passed=not issues,
        highest_completed_stage="FACT_VERIFICATION" if not issues else "NONE",
        failed_stage=None if not issues else "FACT_VERIFICATION",
        issues=tuple(issues),
    )


def _claim_issue(
    code: V8VerificationCode,
    message: str,
    claim_id: str,
    clause_id: str | None = None,
) -> V8VerificationIssue:
    return V8VerificationIssue(
        code=code,
        stage="CLAIM_VERIFICATION",
        message=message,
        theory_clause_id=clause_id,
        claim_id=claim_id,
    )


def verify_v8_derived_claim_set(
    request: V8DerivationInput,
    claim_set: DerivedClaimSet,
    *,
    conformance_bundle: ConformanceBundle,
    execution_manifest: V8ExecutionManifest,
) -> V8VerificationReport:
    """Join every claim byte back to request, Theory, Rulebook and execution pins."""

    canonical = _canonical_runtime_inputs(request, conformance_bundle)
    if canonical is None:
        return _runtime_tree_failure()
    request, conformance_bundle = canonical
    conformance = verify_runtime_bundle(conformance_bundle)
    if not conformance.passed:
        return V8VerificationReport(
            passed=False,
            highest_completed_stage="NONE",
            failed_stage="BUNDLE_CONFORMANCE",
            issues=(
                V8VerificationIssue(
                    code=V8VerificationCode.BUNDLE_CONFORMANCE_FAILED,
                    stage="BUNDLE_CONFORMANCE",
                    message=(
                        "Standalone claim verification requires a fully conformant, "
                        "checksum-verified Theory bundle."
                    ),
                ),
            ),
        )

    issues: list[V8VerificationIssue] = []
    expected_manifest = build_execution_manifest(conformance_bundle, conformance)
    if execution_manifest != expected_manifest:
        issues.append(
            V8VerificationIssue(
                code=V8VerificationCode.EXECUTION_MANIFEST_MISMATCH,
                stage="CLAIM_VERIFICATION",
                message="Execution manifest does not identify the supplied bundle bytes.",
            )
        )
    clauses = {clause.clause_id: clause for clause in conformance_bundle.theory.clauses}
    rules = {rule.theory_clause_id: rule for rule in conformance_bundle.rulebook.rules}
    if claim_set.inferential_query_id != request.query.id:
        issues.append(
            V8VerificationIssue(
                code=V8VerificationCode.CLAIM_SCOPE_MISMATCH,
                stage="CLAIM_VERIFICATION",
                message="DerivedClaimSet and request query scopes differ.",
            )
        )
    expected_claim_set = derive_claim_set(
        request,
        conformance_bundle=conformance_bundle,
        execution_manifest=expected_manifest,
    )
    if claim_set != expected_claim_set:
        issues.append(
            V8VerificationIssue(
                code=V8VerificationCode.CLAIM_OUTPUT_MISMATCH,
                stage="CLAIM_VERIFICATION",
                message=(
                    "DerivedClaimSet differs from deterministic re-derivation of the full "
                    "expected claim contract."
                ),
            )
        )
    for claim in claim_set.claims:
        clause_id = claim.theory_clauses[0] if len(claim.theory_clauses) == 1 else None
        clause = clauses.get(clause_id or "")
        rule = rules.get(clause_id or "")
        if (
            claim.inferential_query_id != request.query.id
            or claim.value.query_scope_id != request.query.id
        ):
            issues.append(
                _claim_issue(
                    V8VerificationCode.CLAIM_SCOPE_MISMATCH,
                    "Claim and scientific value must share the request query scope.",
                    claim.claim_id,
                    clause_id,
                )
            )
        if clause is None or rule is None:
            issues.append(
                _claim_issue(
                    V8VerificationCode.CLAIM_CLAUSE_MISMATCH,
                    "Claim lacks one conformant Theory clause/rule mapping.",
                    claim.claim_id,
                    clause_id,
                )
            )
            continue
        expected_required = tuple(item.predicate_id for item in clause.required_predicates)
        expected_ruleset = (
            f"{conformance_bundle.rulebook.rulebook_id}-"
            f"{conformance_bundle.rulebook.rulebook_version}"
        )
        if (
            claim.claim_type not in clause.output_claim_types
            or claim.required_predicates != expected_required
            or claim.theory_version != conformance_bundle.theory.theory_version
            or claim.ruleset_version != expected_ruleset
        ):
            issues.append(
                _claim_issue(
                    V8VerificationCode.CLAIM_CLAUSE_MISMATCH,
                    "Claim output, predicates or Theory/Rulebook versions diverge.",
                    claim.claim_id,
                    clause_id,
                )
            )
        if claim.rule_trace != (rule.rule_id,) or len(claim.proof_trace) != 1:
            issues.append(
                _claim_issue(
                    V8VerificationCode.CLAIM_PROOF_MISMATCH,
                    "Claim must reference exactly its conformant implementation rule.",
                    claim.claim_id,
                    clause_id,
                )
            )
        else:
            proof = claim.proof_trace[0]
            expected_references = tuple(
                (
                    predicate_id,
                    canonical_checksum(request.predicate_values[predicate_id]),
                )
                for predicate_id in expected_required
            )
            actual_references = tuple(
                (
                    reference.predicate_id,
                    canonical_checksum(reference.predicate_value),
                )
                for reference in proof.predicate_references
            )
            if (
                proof.theory_clause_id != clause.clause_id
                or proof.rule_id != rule.rule_id
                or actual_references != expected_references
            ):
                issues.append(
                    _claim_issue(
                        V8VerificationCode.CLAIM_PROOF_MISMATCH,
                        "Proof IDs and predicate bytes must equal the verified request.",
                        claim.claim_id,
                        clause_id,
                    )
                )
        support = request.support_by_clause[clause.clause_id]
        if claim.support_grade != support.support_grade:
            issues.append(
                _claim_issue(
                    V8VerificationCode.CLAIM_SUPPORT_MISMATCH,
                    "Claim SupportGrade differs from the clause support descriptor.",
                    claim.claim_id,
                    clause_id,
                )
            )
        if claim.irrelevant_predicates != rule.irrelevant_predicates:
            issues.append(
                _claim_issue(
                    V8VerificationCode.CLAIM_PROOF_MISMATCH,
                    "Irrelevant predicate IDs/rationales differ from the conformant rule.",
                    claim.claim_id,
                    clause_id,
                )
            )
        if claim.profile_coverage != request.profile_coverage.claim_reference():
            issues.append(
                _claim_issue(
                    V8VerificationCode.CLAIM_COVERAGE_MISMATCH,
                    "Claim profile coverage differs from the verified request.",
                    claim.claim_id,
                    clause_id,
                )
            )
    return V8VerificationReport(
        passed=not issues,
        highest_completed_stage="CLAIM_VERIFICATION" if not issues else "THEORY_DERIVATION",
        failed_stage=None if not issues else "CLAIM_VERIFICATION",
        issues=tuple(issues),
    )


__all__ = [
    "V8VerificationCode",
    "V8VerificationIssue",
    "V8VerificationReport",
    "verify_v8_derived_claim_set",
    "verify_v8_pipeline_request",
]
