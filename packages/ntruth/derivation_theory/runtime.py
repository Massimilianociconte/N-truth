"""Clause-ID PRD v8 runtime gated by one complete conformance bundle."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, JsonValue, field_validator, model_validator

from ntruth.conformance.harness import (
    ConformanceFailure,
    ConformanceFailureCode,
    ConformanceReport,
    evaluate_conformance,
)
from ntruth.derivation_theory.contracts import (
    ConformanceBundle,
    TheoryClause,
    V8ConformanceRule,
)
from ntruth.derivation_theory.loader import (
    canonical_checksum,
    load_canonical_bundle,
    load_installed_bundle,
)
from ntruth.schemas.causal_context import QueryCausalEventAggregate
from ntruth.schemas.claims import (
    DerivedClaim,
    DerivedClaimSet,
    DeterminabilityState,
    PredicateProofReference,
    ProofTraceStep,
)
from ntruth.schemas.core import stable_id
from ntruth.schemas.count_registry import (
    CanonicalCountKind,
    CanonicalCountRecord,
    CanonicalCountRegistry,
    CountQuantifier,
)
from ntruth.schemas.coverage import ProfileCoverageStatement, ScenarioCoverage
from ntruth.schemas.execution import ImplementationRulePin, V8ExecutionManifest
from ntruth.schemas.graph_v8 import V8ExperimentGraph, V8GraphNodeType
from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.query import InferentialQuery
from ntruth.schemas.support import EvidenceBasis, ScientificReviewRequirement, SupportDescriptor

CLAIM_STATE_REVIEW_ISSUE_ID = "SRR-V8-023"


class V8DerivationInput(KernelModel):
    experiment_block_id: NonBlankStr
    graph: V8ExperimentGraph
    query: InferentialQuery
    causal_aggregate: QueryCausalEventAggregate
    predicate_values: dict[NonBlankStr, KnowledgeValue[JsonValue]] = Field(min_length=1)
    support_by_clause: dict[NonBlankStr, SupportDescriptor] = Field(min_length=1)
    profile_coverage: ProfileCoverageStatement
    scenario_coverages: tuple[ScenarioCoverage, ...] = ()
    count_registry: CanonicalCountRegistry
    experimental_unit_count_record_id: NonBlankStr
    biological_source_count_record_id: NonBlankStr
    runtime_ruleset_version: NonBlankStr

    @field_validator("predicate_values", mode="before")
    @classmethod
    def _normalize_json_predicates(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        return {
            key: item.model_dump(mode="json") if isinstance(item, BaseModel) else item
            for key, item in value.items()
        }

    @model_validator(mode="after")
    def _scope_integrity(self) -> V8DerivationInput:
        if self.causal_aggregate.experiment_block_id != self.experiment_block_id:
            raise ValueError("causal aggregate must share the pipeline Experiment Block")
        if self.causal_aggregate.causal_context.inferential_query_id != self.query.id:
            raise ValueError("causal aggregate must share the pipeline InferentialQuery")
        block_nodes = {
            node.node_id
            for node in self.graph.nodes
            if node.node_type is V8GraphNodeType.EXPERIMENT_BLOCK
        }
        query_nodes = {
            node.node_id
            for node in self.graph.nodes
            if node.node_type is V8GraphNodeType.INFERENTIAL_QUERY
        }
        if self.experiment_block_id not in block_nodes:
            raise ValueError("v8 graph does not contain the requested Experiment Block")
        if self.query.id not in query_nodes:
            raise ValueError("v8 graph does not contain the requested InferentialQuery")
        for predicate_id, value in self.predicate_values.items():
            if value.query_scope_id is not None and value.query_scope_id != self.query.id:
                raise ValueError(f"predicate {predicate_id} has a cross-query scope")
        if self.profile_coverage.profile_id != self.query.profile_id:
            raise ValueError("profile coverage must share the InferentialQuery profile")
        for coverage in self.scenario_coverages:
            if coverage.profile_id != self.query.profile_id:
                raise ValueError("scenario coverage must share the InferentialQuery profile")
        _selected_count_record(
            self,
            self.experimental_unit_count_record_id,
            CanonicalCountKind.EXPERIMENTAL_UNIT_COUNT,
        )
        _selected_count_record(
            self,
            self.biological_source_count_record_id,
            CanonicalCountKind.BIOLOGICAL_SOURCE_COUNT,
        )
        return self


def load_runtime_bundle() -> ConformanceBundle:
    """Load the complete pinned bundle; public execution still requires it explicitly."""

    try:
        return load_installed_bundle()
    except FileNotFoundError:
        return load_canonical_bundle(Path(__file__).resolve().parents[3])


def _asset_content_checksum(asset: BaseModel) -> str:
    return canonical_checksum(
        asset.model_dump(mode="json", exclude_unset=True),
        exclude_declared_checksum=True,
    )


def rule_content_checksum(rule: V8ConformanceRule) -> str:
    return canonical_checksum(rule.model_dump(mode="json", exclude_unset=True))


def _checksum_failures(bundle: ConformanceBundle) -> tuple[ConformanceFailure, ...]:
    assets = (
        ("Theory", bundle.theory, bundle.theory.declared_checksum),
        ("Rulebook", bundle.rulebook, bundle.rulebook.declared_checksum),
        ("profile closure", bundle.profile_closure, bundle.profile_closure.declared_checksum),
        (
            "reference registry",
            bundle.reference_registry,
            bundle.reference_registry.declared_checksum,
        ),
        ("fixture set", bundle.fixture_set, bundle.fixture_set.declared_checksum),
    )
    failures: list[ConformanceFailure] = []
    for label, asset, declared in assets:
        actual = _asset_content_checksum(asset)
        if actual != declared:
            failures.append(
                ConformanceFailure(
                    code=ConformanceFailureCode.CHECKSUM_MISMATCH,
                    message=f"{label} content checksum differs from its immutable declaration",
                )
            )
    return tuple(failures)


def verify_runtime_bundle(bundle: ConformanceBundle) -> ConformanceReport:
    """Verify both cross-asset conformance and the bytes represented by each pin."""

    report = evaluate_conformance(bundle)
    failures = (*report.failures, *_checksum_failures(bundle))
    return report.model_copy(update={"passed": not failures, "failures": failures})


def _rule_pins(bundle: ConformanceBundle) -> tuple[ImplementationRulePin, ...]:
    return tuple(
        ImplementationRulePin(
            rule_id=rule.rule_id,
            rule_version=rule.rule_version,
            rule_checksum=rule_content_checksum(rule),
            theory_clause_id=rule.theory_clause_id,
            theory_clause_version=rule.theory_clause_version,
            required_predicate_ids=tuple(item.predicate_id for item in rule.required_predicates),
            irrelevant_predicates=rule.irrelevant_predicates,
        )
        for rule in bundle.rulebook.rules
    )


def build_execution_manifest(
    bundle: ConformanceBundle,
    conformance: ConformanceReport,
) -> V8ExecutionManifest:
    """Create the immutable join record for the exact verified execution bytes."""

    rule_pins = _rule_pins(bundle)
    manifest_id = stable_id(
        "v8-execution-manifest",
        bundle.theory.declared_checksum,
        bundle.rulebook.declared_checksum,
        bundle.profile_closure.declared_checksum,
        bundle.reference_registry.declared_checksum,
        bundle.fixture_set.declared_checksum,
        *(pin.rule_checksum for pin in rule_pins),
    )
    return V8ExecutionManifest(
        manifest_id=manifest_id,
        theory_id=bundle.theory.theory_id,
        theory_version=bundle.theory.theory_version,
        theory_checksum=bundle.theory.declared_checksum,
        rulebook_id=bundle.rulebook.rulebook_id,
        rulebook_version=bundle.rulebook.rulebook_version,
        rulebook_checksum=bundle.rulebook.declared_checksum,
        profile_closure_asset_id=bundle.profile_closure.asset_id,
        profile_closure_asset_version=bundle.profile_closure.asset_version,
        profile_closure_checksum=bundle.profile_closure.declared_checksum,
        reference_registry_id=bundle.reference_registry.registry_id,
        reference_registry_version=bundle.reference_registry.registry_version,
        reference_registry_checksum=bundle.reference_registry.declared_checksum,
        fixture_set_id=bundle.fixture_set.fixture_set_id,
        fixture_set_version=bundle.fixture_set.fixture_set_version,
        fixture_set_checksum=bundle.fixture_set.declared_checksum,
        implementation_rules=rule_pins,
        release_blocker_issue_ids=conformance.release_blocker_issue_ids,
    )


def _selected_count_record(
    request: V8DerivationInput,
    count_id: str,
    expected_kind: CanonicalCountKind,
) -> CanonicalCountRecord:
    matches = tuple(
        record for record in request.count_registry.records if record.count_id == count_id
    )
    if len(matches) != 1:
        raise ValueError(f"canonical count record {count_id!r} is missing or ambiguous")
    record = matches[0]
    if record.kind is not expected_kind:
        raise ValueError(f"{count_id} is not a canonical {expected_kind.value} record")
    if record.scope.query_id != request.query.id:
        raise ValueError(f"{count_id} has a cross-query count scope")
    expected_scope_values = {
        "factor_id": request.query.factor_id,
        "contrast_id": request.query.contrast_id,
        "endpoint_id": request.query.endpoint_id,
    }
    for field_name, expected in expected_scope_values.items():
        scoped = getattr(record.scope, field_name)
        if scoped.knowledge_state is not KnowledgeState.PRESENT or scoped.value != expected:
            raise ValueError(f"{count_id} {field_name} does not match the InferentialQuery")
    if record.scope.lifecycle_phase.knowledge_state is not KnowledgeState.PRESENT:
        raise ValueError(f"{count_id} lifecycle phase is not comparison-ready")
    return record


def _required_values(
    request: V8DerivationInput,
    clause: TheoryClause,
) -> tuple[tuple[str, KnowledgeValue[JsonValue]], ...]:
    values: list[tuple[str, KnowledgeValue[JsonValue]]] = []
    for requirement in clause.required_predicates:
        value = request.predicate_values.get(requirement.predicate_id)
        if value is None:
            raise ValueError(
                "missing predicate must be represented with an explicit KnowledgeState: "
                f"{requirement.predicate_id}"
            )
        values.append((requirement.predicate_id, value))
    return tuple(values)


def _state_for(
    required: tuple[tuple[str, KnowledgeValue[JsonValue]], ...],
    support: SupportDescriptor,
) -> DeterminabilityState:
    states = {value.knowledge_state for _, value in required}
    if KnowledgeState.CONFLICTING in states:
        return DeterminabilityState.CONFLICTING_INFORMATION
    if states & {KnowledgeState.UNKNOWN, KnowledgeState.NOT_REPORTED}:
        return DeterminabilityState.INSUFFICIENT_INFORMATION
    if support.evidence_basis in {EvidenceBasis.AUTHOR_ASSERTED, EvidenceBasis.INFERRED_CANDIDATE}:
        return DeterminabilityState.INSUFFICIENT_INFORMATION
    if support.evidence_basis is EvidenceBasis.SELF_REPORT:
        return DeterminabilityState.INSUFFICIENT_INFORMATION
    return DeterminabilityState.DETERMINATE


def _count_payload(
    request: V8DerivationInput,
    claim_type: str,
) -> tuple[JsonValue | None, tuple[str, ...]]:
    count_id, kind = {
        "EXPERIMENTAL_UNIT_COUNT": (
            request.experimental_unit_count_record_id,
            CanonicalCountKind.EXPERIMENTAL_UNIT_COUNT,
        ),
        "BIOLOGICAL_SOURCE_COUNT": (
            request.biological_source_count_record_id,
            CanonicalCountKind.BIOLOGICAL_SOURCE_COUNT,
        ),
    }[claim_type]
    record = _selected_count_record(request, count_id, kind)
    if (
        record.value.knowledge_state is not KnowledgeState.PRESENT
        or record.quantifier is not CountQuantifier.EXACT
        or not isinstance(record.value.value, int)
    ):
        return None, record.source_evidence
    payload = record.model_dump(
        mode="json",
        exclude_defaults=True,
        exclude_none=True,
    )
    # The registry version is a normative pin even when it equals the schema
    # default.  Empty/default scientific containers are deliberately omitted:
    # in the open-world kernel they would be ambiguous rather than evidence.
    payload["registry_version"] = record.registry_version
    return payload, tuple(dict.fromkeys((*record.source_evidence, *record.value.evidence_ids)))


def _resolved_payload(
    claim_type: str,
    request: V8DerivationInput,
) -> tuple[JsonValue | None, tuple[str, ...]]:
    values = request.predicate_values
    if claim_type in {"EXPERIMENTAL_UNIT_COUNT", "BIOLOGICAL_SOURCE_COUNT"}:
        return _count_payload(request, claim_type)
    if claim_type in {"ASSIGNMENT_UNIT", "EXPERIMENTAL_UNIT_CANDIDATE"}:
        payload = (
            values["candidate_unit"].value
            if values["assignment_separability_support"].value is True
            else None
        )
        return payload, ()
    if claim_type == "EXPERIMENTAL_UNIT":
        payload = (
            values["candidate_unit"].value
            if values["assignment_separability"].value is True
            and values["realized_exposure_separability"].value is True
            else None
        )
        return payload, ()
    if claim_type == "INTERFERENCE_ESTIMAND_SUPPORT":
        consequences = {
            "no_known_path": "NO_KNOWN_PATH_DOES_NOT_PROVE_ABSENCE",
            "possible": "CAVEAT_OR_SENSITIVITY_REQUIRED",
            "documented": "UNSUPPORTED_OR_UNSPECIFIED_WITHOUT_EXPOSURE_MAPPING",
            "unknown": "CAVEAT_QUESTION_OR_SENSITIVITY_REQUIRED",
        }
        return consequences.get(str(values["interference_status"].value)), ()
    if claim_type == "ANALYTICAL_UNIT":
        return values["analytical_grouping"].value, ()
    if claim_type == "STATISTICAL_HANDOFF_REQUIREMENTS":
        return "HANDOFF_ONLY", ()
    if claim_type == "INFERENCE_SCOPE":
        return "LIMITED_TO_DECLARED_QUERY_PROTOCOL_AND_SOURCE_SCOPE", ()
    raise ValueError(f"no clause evaluator for claim type {claim_type}")


def _derive_clause_claims(
    request: V8DerivationInput,
    bundle: ConformanceBundle,
    clause: TheoryClause,
    rule: V8ConformanceRule,
) -> tuple[DerivedClaim, ...]:
    required = _required_values(request, clause)
    support = request.support_by_clause[clause.clause_id]
    base_evidence = tuple(
        dict.fromkeys(evidence_id for _, value in required for evidence_id in value.evidence_ids)
    )
    claims: list[DerivedClaim] = []
    for claim_type in clause.output_claim_types:
        state = _state_for(required, support)
        payload: JsonValue | None = None
        count_evidence: tuple[str, ...] = ()
        if state is DeterminabilityState.DETERMINATE:
            payload, count_evidence = _resolved_payload(claim_type, request)
        evidence_ids = tuple(dict.fromkeys((*base_evidence, *count_evidence)))
        if payload is None:
            state = DeterminabilityState.INSUFFICIENT_INFORMATION
            value = KnowledgeValue[JsonValue](
                knowledge_state=KnowledgeState.UNKNOWN,
                rationale=(
                    f"Clause {clause.clause_id} cannot emit an unconditional {claim_type} "
                    "from the verified predicates and canonical count records."
                ),
                query_scope_id=request.query.id,
            )
            state_review = ScientificReviewRequirement(
                issue_id=CLAIM_STATE_REVIEW_ISSUE_ID,
                rationale="Positive non-determinate payloads remain blocked.",
            )
        else:
            if not evidence_ids:
                raise ValueError(f"DETERMINATE {claim_type} requires factual evidence")
            value = KnowledgeValue[JsonValue](
                knowledge_state=KnowledgeState.PRESENT,
                value=payload,
                evidence_ids=evidence_ids,
                query_scope_id=request.query.id,
            )
            state_review = None
        proof = ProofTraceStep(
            step_id=stable_id(
                "proof",
                request.experiment_block_id,
                request.query.id,
                clause.clause_id,
                claim_type,
            ),
            predicate_references=tuple(
                PredicateProofReference(predicate_id=predicate_id, predicate_value=value)
                for predicate_id, value in required
            ),
            theory_clause_id=clause.clause_id,
            rule_id=rule.rule_id,
        )
        claims.append(
            DerivedClaim(
                claim_id=stable_id(
                    "claim",
                    request.experiment_block_id,
                    request.query.id,
                    bundle.theory.theory_version,
                    claim_type,
                ),
                claim_type=claim_type,
                inferential_query_id=request.query.id,
                value=value,
                determinability_state=state,
                support_grade=support.support_grade,
                required_predicates=tuple(predicate_id for predicate_id, _ in required),
                irrelevant_predicates=rule.irrelevant_predicates,
                assumptions=("record_complete_for_claim",),
                sensitivity_records=(),
                theory_version=bundle.theory.theory_version,
                theory_clauses=(clause.clause_id,),
                ruleset_version=request.runtime_ruleset_version,
                rule_trace=(rule.rule_id,),
                proof_trace=(proof,),
                profile_coverage=request.profile_coverage.claim_reference(),
                state_contract_review=state_review,
            )
        )
    return tuple(claims)


def derive_claim_set(
    request: V8DerivationInput,
    *,
    conformance_bundle: ConformanceBundle,
    execution_manifest: V8ExecutionManifest,
) -> DerivedClaimSet:
    """Derive only from Theory clauses, using conformant rules solely for trace pins."""

    rules = {rule.theory_clause_id: rule for rule in conformance_bundle.rulebook.rules}
    if execution_manifest.theory_checksum != conformance_bundle.theory.declared_checksum:
        raise ValueError("execution manifest and Derivation Theory checksum differ")
    claims = tuple(
        claim
        for clause in conformance_bundle.theory.clauses
        for claim in _derive_clause_claims(
            request,
            conformance_bundle,
            clause,
            rules[clause.clause_id],
        )
    )
    return DerivedClaimSet(
        claim_set_id=stable_id(
            "claim-set",
            request.experiment_block_id,
            request.query.id,
            execution_manifest.manifest_id,
        ),
        inferential_query_id=request.query.id,
        claims=claims,
    )


__all__ = [
    "CLAIM_STATE_REVIEW_ISSUE_ID",
    "V8DerivationInput",
    "build_execution_manifest",
    "derive_claim_set",
    "load_runtime_bundle",
    "rule_content_checksum",
    "verify_runtime_bundle",
]
