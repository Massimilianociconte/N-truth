"""Clause-ID PRD v8 runtime gated by one complete conformance bundle."""

from __future__ import annotations

import dis
import hashlib
import inspect
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from types import CodeType, ModuleType
from typing import Any, cast

from pydantic import BaseModel, Field, JsonValue, field_validator, model_validator

from ntruth.conformance.harness import (
    ConformanceFailure,
    ConformanceFailureCode,
    ConformanceReport,
    evaluate_conformance,
)
from ntruth.derivation_theory.contracts import (
    ConformanceBundle,
    EvaluatorArtifactKind,
    ReviewedEvaluatorArtifactPin,
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
    InputRecordProofReference,
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
from ntruth.schemas.coverage import (
    PROFILE_COVERAGE_REVIEW_ISSUE_ID,
    ProfileCoverageStatement,
    ScenarioCoverage,
)
from ntruth.schemas.execution import (
    AdequacyEvaluatorPin,
    ImplementationRulePin,
    V8ExecutionManifest,
)
from ntruth.schemas.graph_v8 import V8ExperimentGraph, V8GraphNodeType
from ntruth.schemas.kernel import KernelModel, NonBlankStr
from ntruth.schemas.knowledge import KnowledgeState, KnowledgeValue
from ntruth.schemas.query import InferentialQuery
from ntruth.schemas.support import EvidenceBasis, ScientificReviewRequirement, SupportDescriptor

CLAIM_STATE_REVIEW_ISSUE_ID = "SRR-V8-023"

_PYDANTIC_CALLABLE_DECORATOR_GROUPS = (
    "validators",
    "field_validators",
    "root_validators",
    "field_serializers",
    "model_serializers",
    "model_validators",
    "computed_fields",
)
_MAX_REVIEWED_CALLABLES = 256
_MAX_REVIEWED_CALLABLE_BINDINGS = 1024

_REVIEWED_THEORY_ID = "ntruth-derivation-theory"
_REVIEWED_THEORY_VERSION = "0.1.0"
_REVIEWED_THEORY_CHECKSUM = "aa37639893e2ba7732496f2eb6a121291e0aad2d3bae51501c8f1ea9e9b6464f"
_REVIEWED_RULEBOOK_ID = "ntruth-v8-core"
_REVIEWED_RULEBOOK_VERSION = "0.1.0"
_REVIEWED_RULEBOOK_CHECKSUM = "dc10b6a53cc754b2be1263a83561dcb1c1faf555b80e61013a4dd45e28761c97"
_REVIEWED_EVALUATOR_REGISTRY_ID = "ntruth-reviewed-evaluator-registry"
_REVIEWED_EVALUATOR_REGISTRY_VERSION = "0.1.1"
_REVIEWED_EVALUATOR_REGISTRY_CHECKSUM = (
    "fb0be8b34e9f736d5fbe1a30f9c5151b701d3847880cb72bef3dd7f892f4b91f"
)
_REVIEWED_EVALUATOR_VERSION = "0.1.1"
_REVIEWED_RULE_ID_BY_CLAUSE = {
    "DT-A-ASSIGNMENT-UNIT": "V8-A-ASSIGNMENT-UNIT",
    "DT-B-EXPERIMENTAL-UNIT": "V8-B-EXPERIMENTAL-UNIT",
    "DT-C-EXPERIMENTAL-UNIT-COUNT": "V8-C-EXPERIMENTAL-UNIT-COUNT",
    "DT-D-BIOLOGICAL-SOURCE-COUNT": "V8-D-BIOLOGICAL-SOURCE-COUNT",
    "DT-E-INTERFERENCE-ESTIMAND": "V8-E-INTERFERENCE",
    "DT-F-ANALYTICAL-DEPENDENCE": "V8-F-ANALYTICAL-DEPENDENCE",
    "DT-G-INFERENCE-SCOPE": "V8-G-INFERENCE-SCOPE",
}
_REVIEWED_RULE_CHECKSUM_BY_ID = {
    "V8-A-ASSIGNMENT-UNIT": "552c9dc9b05dd3a31cbf2d747c45dbe3ef7ce15a14b18df072b4a6bfd2629908",
    "V8-B-EXPERIMENTAL-UNIT": "4530ea94565420a6c3cf6d648487de3ea2ea028cc3c55008374536970c854e58",
    "V8-C-EXPERIMENTAL-UNIT-COUNT": (
        "9adbeda8903c6cc01fab79aca8894392adec19d2c6ee6f326631b4467004bb2f"
    ),
    "V8-D-BIOLOGICAL-SOURCE-COUNT": (
        "afa97c4c6a971e871a0dcabd3c44cacecee18ae63a2874d1a6093a3369c6170f"
    ),
    "V8-E-INTERFERENCE": "3494b23193de54df74e4fb990e804727d0f89d4f25feeea34537e84b5638bb93",
    "V8-F-ANALYTICAL-DEPENDENCE": (
        "8b27aca224fe346a44da0f6ce348c651712e1ceb6afd7952feb721b3eef4f7c1"
    ),
    "V8-G-INFERENCE-SCOPE": "a5d89e9a8a950eb1b1adff970805a656e2e4e722b86ae132e2d80c01cd0d36b8",
}


class V8EvaluatorReviewRequired(ValueError):
    """No engineering-pinned executable identity matches the supplied contract."""

    def __init__(self, *, clause_id: str | None = None) -> None:
        self.review_requirement = ScientificReviewRequirement(
            issue_id="SRR-V8-024",
            rationale=(
                "The evaluator registry is an engineering identity gate only. A "
                "Theory/Rulebook successor requires an engineering-pinned evaluator "
                "artifact, including exact implementation bytes, plus separately "
                "authorized scientific review before deterministic re-derivation."
            ),
        )
        suffix = f" for {clause_id}" if clause_id is not None else ""
        super().__init__(
            f"SCIENTIFIC_REVIEW_REQUIRED: no engineering-pinned v8 evaluator identity{suffix}"
        )


@dataclass(frozen=True)
class _EvaluatorArtifact:
    artifact_id: str
    artifact_version: str
    artifact_checksum: str


def _reviewed_bundle_identity(bundle: ConformanceBundle) -> bool:
    return (
        bundle.theory.theory_id == _REVIEWED_THEORY_ID
        and bundle.theory.theory_version == _REVIEWED_THEORY_VERSION
        and bundle.theory.declared_checksum == _REVIEWED_THEORY_CHECKSUM
        and bundle.rulebook.rulebook_id == _REVIEWED_RULEBOOK_ID
        and bundle.rulebook.rulebook_version == _REVIEWED_RULEBOOK_VERSION
        and bundle.rulebook.declared_checksum == _REVIEWED_RULEBOOK_CHECKSUM
        and bundle.evaluator_registry.registry_id == _REVIEWED_EVALUATOR_REGISTRY_ID
        and bundle.evaluator_registry.registry_version == _REVIEWED_EVALUATOR_REGISTRY_VERSION
        and bundle.evaluator_registry.declared_checksum == _REVIEWED_EVALUATOR_REGISTRY_CHECKSUM
    )


def _derivation_dependencies() -> tuple[
    dict[str, Any],
    dict[str, type[BaseModel]],
]:
    executable_dependencies: dict[str, Any] = {
        "stable_id": stable_id,
        "selected_count_record": _selected_count_record,
        "required_values": _required_values,
        "state_for": _state_for,
        "count_payload": _count_payload,
        "resolved_payload": _resolved_payload,
        "derive_clause_claims": _derive_clause_claims,
        "derive_claim_set": derive_claim_set,
    }
    contract_dependencies: dict[str, type[BaseModel]] = {
        "kernel_model": KernelModel,
        "v8_derivation_input": V8DerivationInput,
        "query_causal_event_aggregate": QueryCausalEventAggregate,
        "canonical_count_record": CanonicalCountRecord,
        "canonical_count_registry": CanonicalCountRegistry,
        "profile_coverage_statement": ProfileCoverageStatement,
        "scenario_coverage": ScenarioCoverage,
        "support_descriptor": SupportDescriptor,
        "theory_clause": TheoryClause,
        "conformance_rule": V8ConformanceRule,
        "inferential_query": InferentialQuery,
        "experiment_graph": V8ExperimentGraph,
        "derived_claim": DerivedClaim,
        "derived_claim_set": DerivedClaimSet,
        "execution_manifest": V8ExecutionManifest,
    }
    return executable_dependencies, contract_dependencies


def _callable_runtime_identities(value: object) -> tuple[object, ...]:
    identities: list[object] = [
        value,
        getattr(value, "__code__", None),
        getattr(value, "__defaults__", None),
        getattr(value, "__kwdefaults__", None),
    ]
    keyword_defaults = getattr(value, "__kwdefaults__", None)
    if type(keyword_defaults) is dict:
        for name in sorted(keyword_defaults):
            identities.extend((name, keyword_defaults[name]))
    closure = getattr(value, "__closure__", None)
    identities.append(closure)
    if type(closure) is tuple:
        identities.extend(cell.cell_contents for cell in closure)
    return tuple(identities)


def _reviewed_constant_payload(value: object) -> object:
    value_type = type(value)
    if value is None or value is Ellipsis:
        return {"type": "none" if value is None else "ellipsis"}
    if value_type is bool:
        return {"type": "bool", "value": value}
    if value_type is int:
        return {"type": "int", "value": str(value)}
    if value_type is float:
        return {"type": "float", "value": cast(float, value).hex()}
    if value_type is complex:
        complex_value = cast(complex, value)
        return {
            "type": "complex",
            "real": complex_value.real.hex(),
            "imag": complex_value.imag.hex(),
        }
    if value_type is str:
        return {"type": "str", "value": value}
    if value_type is bytes:
        return {"type": "bytes", "value": cast(bytes, value).hex()}
    if value_type is tuple:
        tuple_value = cast(tuple[object, ...], value)
        return {
            "type": "tuple",
            "items": [_reviewed_constant_payload(item) for item in tuple_value],
        }
    if value_type is frozenset:
        frozenset_value = cast(frozenset[object], value)
        items = [_reviewed_constant_payload(item) for item in frozenset_value]
        return {
            "type": "frozenset",
            "items": sorted(items, key=canonical_checksum),
        }
    if value_type is slice:
        slice_value = cast(slice, value)
        return {
            "type": "slice",
            "start": _reviewed_constant_payload(slice_value.start),
            "stop": _reviewed_constant_payload(slice_value.stop),
            "step": _reviewed_constant_payload(slice_value.step),
        }
    if value_type is dict:
        dict_value = cast(dict[object, object], value)
        if any(type(key) is not str for key in dict_value):
            raise TypeError("pinned callable dictionaries require exact string keys")
        string_dict = cast(dict[str, object], dict_value)
        return {
            "type": "dict",
            "items": {
                key: _reviewed_constant_payload(string_dict[key]) for key in sorted(string_dict)
            },
        }
    if value_type is CodeType:
        return {"type": "code", "value": _reviewed_code_payload(cast(CodeType, value))}
    raise TypeError(f"unsupported pinned callable constant: {value_type.__name__}")


def _reviewed_code_payload(code: CodeType) -> dict[str, object]:
    return {
        "argcount": code.co_argcount,
        "posonlyargcount": code.co_posonlyargcount,
        "kwonlyargcount": code.co_kwonlyargcount,
        "nlocals": code.co_nlocals,
        "stacksize": code.co_stacksize,
        "flags": code.co_flags,
        "code": code.co_code.hex(),
        "constants": [_reviewed_constant_payload(item) for item in code.co_consts],
        "names": list(code.co_names),
        "varnames": list(code.co_varnames),
        "freevars": list(code.co_freevars),
        "cellvars": list(code.co_cellvars),
        "exception_table": code.co_exceptiontable.hex(),
    }


def _callable_semantic_checksum(function: Any) -> str:
    closure = function.__closure__
    return canonical_checksum(
        {
            "code": _reviewed_code_payload(function.__code__),
            "defaults": _reviewed_constant_payload(function.__defaults__),
            "kwdefaults": _reviewed_constant_payload(function.__kwdefaults__),
            "closure": _reviewed_constant_payload(
                tuple(cell.cell_contents for cell in closure) if closure is not None else None
            ),
        }
    )


def _unwrapped_function(value: object) -> object:
    return getattr(value, "__func__", value)


def _model_review_callables(
    model: type[BaseModel],
) -> tuple[tuple[str, object], ...]:
    decorators = model.__pydantic_decorators__
    dependencies: list[tuple[str, object]] = []
    for group_name in _PYDANTIC_CALLABLE_DECORATOR_GROUPS:
        group = getattr(decorators, group_name)
        if type(group) is not dict:
            raise TypeError("Pydantic decorator registry must remain an exact dict")
        for decorator_name in sorted(group):
            function = _unwrapped_function(group[decorator_name].func)
            if not inspect.isfunction(function):
                raise TypeError("pinned Pydantic callables must remain Python functions")
            dependencies.append(
                (
                    (
                        f"model:{model.__module__}.{model.__qualname__}:"
                        f"{group_name}:{decorator_name}"
                    ),
                    function,
                )
            )
    return tuple(dependencies)


def _module_attribute_callables(function: Any) -> tuple[tuple[str, Any], ...]:
    """Resolve Python functions reached through live module attribute loads."""

    global_values = function.__globals__
    if type(global_values) is not dict:
        raise TypeError("pinned callable globals must remain an exact dict")
    instructions = tuple(dis.get_instructions(function))
    dependencies: list[tuple[str, Any]] = []
    for index, instruction in enumerate(instructions):
        if instruction.opname != "LOAD_GLOBAL" or type(instruction.argval) is not str:
            continue
        value = global_values.get(instruction.argval)
        if not isinstance(value, ModuleType):
            continue
        attribute_path = instruction.argval
        for attribute_instruction in instructions[index + 1 :]:
            if attribute_instruction.opname not in {"LOAD_ATTR", "LOAD_METHOD"}:
                break
            if type(attribute_instruction.argval) is not str:
                raise TypeError("pinned module attribute names must remain exact strings")
            attribute_name = attribute_instruction.argval
            value = inspect.getattr_static(value, attribute_name)
            attribute_path = f"{attribute_path}.{attribute_name}"
            candidate = _unwrapped_function(value)
            if inspect.isfunction(candidate):
                dependencies.append((attribute_path, candidate))
    return tuple(dependencies)


def _reviewed_callable_closure(
    executable_dependencies: dict[str, Any],
    contract_dependencies: dict[str, type[BaseModel]],
) -> tuple[tuple[str, Any], ...]:
    """Resolve the bounded live callable-global graph used by engineering-pinned execution."""

    pending: list[tuple[str, object]] = [
        (f"executable:{name}", _unwrapped_function(dependency))
        for name, dependency in sorted(executable_dependencies.items())
    ]
    reviewed_models: dict[str, type[BaseModel]] = {
        **contract_dependencies,
        "knowledge_value": KnowledgeValue,
        "knowledge_value_json": KnowledgeValue[JsonValue],
    }
    for name, model in sorted(reviewed_models.items()):
        pending.extend(
            (f"{name}:{binding}", function) for binding, function in _model_review_callables(model)
        )

    dependencies: list[tuple[str, Any]] = []
    expanded: set[int] = set()
    while pending:
        binding, candidate = pending.pop(0)
        function = _unwrapped_function(candidate)
        if not inspect.isfunction(function):
            raise TypeError("pinned executable dependencies must remain Python functions")
        dependencies.append((binding, function))
        if len(dependencies) > _MAX_REVIEWED_CALLABLE_BINDINGS:
            raise ValueError("pinned callable binding closure exceeds its fixed bound")

        marker = id(function)
        if marker in expanded:
            continue
        expanded.add(marker)
        if len(expanded) > _MAX_REVIEWED_CALLABLES:
            raise ValueError("pinned callable closure exceeds its fixed bound")

        global_values = function.__globals__
        if type(global_values) is not dict:
            raise TypeError("pinned callable globals must remain an exact dict")
        for global_name in sorted(set(function.__code__.co_names)):
            referenced = _unwrapped_function(global_values.get(global_name))
            if inspect.isfunction(referenced):
                pending.append((f"{binding}->{global_name}", referenced))
        pending.extend(
            (f"{binding}->{attribute_path}", referenced)
            for attribute_path, referenced in _module_attribute_callables(function)
        )
    return tuple(sorted(dependencies, key=lambda item: item[0]))


def _schema_runtime_identities(model: type[BaseModel]) -> tuple[object, ...]:
    descriptor = inspect.getattr_static(model, "model_json_schema")
    function = getattr(descriptor, "__func__", descriptor)
    return (
        model,
        descriptor,
        *_callable_runtime_identities(function),
        getattr(model, "__pydantic_core_schema__", None),
        getattr(model, "__pydantic_validator__", None),
        getattr(model, "__pydantic_serializer__", None),
        getattr(model, "__pydantic_fields__", None),
    )


@dataclass(frozen=True)
class _RuntimeCacheToken:
    addresses: tuple[int, ...]
    semantic_fingerprints: tuple[str, ...]
    identities: tuple[object, ...] = field(compare=False, hash=False, repr=False)


def _derivation_dependency_checksum() -> str:
    """Hash the live closure with a cache key bound to executable/schema state."""

    executable_dependencies, contract_dependencies = _derivation_dependencies()
    try:
        callable_dependencies = _reviewed_callable_closure(
            executable_dependencies,
            contract_dependencies,
        )
        runtime_identities = (
            *_callable_runtime_identities(inspect.getsource),
            *(
                identity
                for _binding, dependency in callable_dependencies
                for identity in _callable_runtime_identities(dependency)
            ),
            *(
                identity
                for dependency in contract_dependencies.values()
                for identity in _schema_runtime_identities(dependency)
            ),
            *_schema_runtime_identities(KnowledgeValue),
            *_schema_runtime_identities(KnowledgeValue[JsonValue]),
        )
        cache_token = _RuntimeCacheToken(
            addresses=(
                len(callable_dependencies),
                *(id(identity) for identity in runtime_identities),
            ),
            semantic_fingerprints=tuple(
                _callable_semantic_checksum(dependency)
                for _binding, dependency in callable_dependencies
            ),
            identities=runtime_identities,
        )
    except Exception as exc:
        raise V8EvaluatorReviewRequired() from exc
    return _cached_derivation_dependency_checksum(cache_token)


@lru_cache(maxsize=16)
def _cached_derivation_dependency_checksum(cache_token: _RuntimeCacheToken) -> str:
    """Hash one dependency closure after its complete live identity was addressed."""

    del cache_token
    executable_dependencies, contract_dependencies = _derivation_dependencies()

    try:
        callable_dependencies = _reviewed_callable_closure(
            executable_dependencies,
            contract_dependencies,
        )
        callable_sources = tuple(
            {
                "binding": binding,
                "module": dependency.__module__,
                "qualname": dependency.__qualname__,
                "source": inspect.getsource(dependency),
                "semantic_code_checksum": _callable_semantic_checksum(dependency),
            }
            for binding, dependency in callable_dependencies
        )
        executable_sources = {
            name: inspect.getsource(dependency)
            for name, dependency in executable_dependencies.items()
        }
        contract_sources = {
            name: inspect.getsource(dependency)
            for name, dependency in contract_dependencies.items()
        }
        contract_schemas = {
            name: dependency.model_json_schema()
            for name, dependency in contract_dependencies.items()
        }
        contract_sources["knowledge_value"] = inspect.getsource(KnowledgeValue)
        contract_schemas["knowledge_value_json"] = KnowledgeValue[JsonValue].model_json_schema()

        dependency_modules: dict[str, str] = {}
        for dependency in (*executable_dependencies.values(), *contract_dependencies.values()):
            module = inspect.getmodule(dependency)
            if module is not None and module.__name__ != __name__:
                dependency_modules[module.__name__] = inspect.getsource(module)
        knowledge_module = inspect.getmodule(KnowledgeValue)
        if knowledge_module is not None:
            dependency_modules[knowledge_module.__name__] = inspect.getsource(knowledge_module)
    except Exception as exc:
        raise V8EvaluatorReviewRequired() from exc

    return canonical_checksum(
        {
            "manifest_version": "ntruth-v8-derivation-dependency-closure-3",
            "executables": executable_sources,
            "callable_global_closure": callable_sources,
            "contract_sources": contract_sources,
            "contract_schemas": contract_schemas,
            "dependency_modules": dependency_modules,
            "reviewed_rule_ids": _REVIEWED_RULE_ID_BY_CLAUSE,
            "reviewed_rule_checksums": _REVIEWED_RULE_CHECKSUM_BY_ID,
            "claim_state_review_issue_id": CLAIM_STATE_REVIEW_ISSUE_ID,
        }
    )


def _derivation_code_checksum(
    clause_id: str,
    *,
    dependency_checksum: str | None = None,
) -> str:
    """Hash the engineering-pinned evaluator and its scientific contract closure."""

    if dependency_checksum is None:
        dependency_checksum = _derivation_dependency_checksum()
    return canonical_checksum(
        {
            "clause_id": clause_id,
            "dependency_closure_checksum": dependency_checksum,
        }
    )


def _reviewed_derivation_artifact(
    bundle: ConformanceBundle,
    clause: TheoryClause,
    rule: V8ConformanceRule,
    *,
    dependency_checksum: str | None = None,
) -> _EvaluatorArtifact:
    expected_rule_id = _REVIEWED_RULE_ID_BY_CLAUSE.get(clause.clause_id)
    expected_artifact_id = f"ntruth-python-derivation-{clause.clause_id}"
    pin = _registered_evaluator_pin(
        bundle,
        EvaluatorArtifactKind.DERIVATION,
        clause,
        rule,
        expected_artifact_id,
    )
    if (
        not _reviewed_bundle_identity(bundle)
        or clause.clause_version != _REVIEWED_THEORY_VERSION
        or expected_rule_id != rule.rule_id
        or _REVIEWED_RULE_CHECKSUM_BY_ID.get(rule.rule_id) != rule_content_checksum(rule)
        or rule.rule_version != _REVIEWED_RULEBOOK_VERSION
        or rule.theory_clause_id != clause.clause_id
        or rule.theory_clause_version != clause.clause_version
        or pin.implementation_source_digest
        != _derivation_code_checksum(
            clause.clause_id,
            dependency_checksum=dependency_checksum,
        )
    ):
        raise V8EvaluatorReviewRequired(clause_id=clause.clause_id)
    return _EvaluatorArtifact(
        artifact_id=pin.artifact_id,
        artifact_version=pin.artifact_version,
        artifact_checksum=pin.implementation_source_digest,
    )


def _registered_evaluator_pin(
    bundle: ConformanceBundle,
    kind: EvaluatorArtifactKind,
    clause: TheoryClause,
    rule: V8ConformanceRule,
    expected_artifact_id: str,
) -> ReviewedEvaluatorArtifactPin:
    matches = tuple(
        pin
        for pin in bundle.evaluator_registry.artifact_pins
        if pin.evaluator_kind is kind
        and pin.theory_clause_id == clause.clause_id
        and pin.rule_id == rule.rule_id
    )
    if len(matches) != 1:
        raise V8EvaluatorReviewRequired(clause_id=clause.clause_id)
    pin = matches[0]
    if (
        pin.artifact_id != expected_artifact_id
        or pin.artifact_version != _REVIEWED_EVALUATOR_VERSION
        or pin.theory_id != bundle.theory.theory_id
        or pin.theory_version != bundle.theory.theory_version
        or pin.theory_checksum != bundle.theory.declared_checksum
        or pin.theory_clause_version != clause.clause_version
        or pin.rule_version != rule.rule_version
        or pin.rule_checksum != rule_content_checksum(rule)
    ):
        raise V8EvaluatorReviewRequired(clause_id=clause.clause_id)
    return pin


def _reviewed_adequacy_artifact(
    bundle: ConformanceBundle,
    clause: TheoryClause,
    rule: V8ConformanceRule,
) -> _EvaluatorArtifact:
    pin = _registered_evaluator_pin(
        bundle,
        EvaluatorArtifactKind.ADEQUACY,
        clause,
        rule,
        "ntruth-python-adequacy-interference-v8",
    )
    implementation_path = Path(__file__).resolve().parents[1] / "rules" / "v8_engine.py"
    current_digest = hashlib.sha256(implementation_path.read_bytes()).hexdigest()
    if (
        not _reviewed_bundle_identity(bundle)
        or clause.clause_id != "DT-E-INTERFERENCE-ESTIMAND"
        or clause.clause_version != _REVIEWED_THEORY_VERSION
        or rule.rule_id != "V8-E-INTERFERENCE"
        or _REVIEWED_RULE_CHECKSUM_BY_ID.get(rule.rule_id) != rule_content_checksum(rule)
        or rule.rule_version != _REVIEWED_RULEBOOK_VERSION
        or pin.implementation_source_digest != current_digest
    ):
        raise V8EvaluatorReviewRequired(clause_id=clause.clause_id)
    return _EvaluatorArtifact(
        artifact_id=pin.artifact_id,
        artifact_version=pin.artifact_version,
        artifact_checksum=pin.implementation_source_digest,
    )


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


@dataclass(frozen=True)
class _RuntimeFailureCheck:
    failures: tuple[ConformanceFailure, ...]
    error: Exception | None = None


@dataclass(frozen=True)
class _RuntimeBundlePreflight:
    report: ConformanceReport
    error: Exception | None = None


def _ordinary_review_cause(error: Exception) -> Exception | None:
    if isinstance(error, V8EvaluatorReviewRequired):
        cause = error.__cause__
        return cause if isinstance(cause, Exception) else None
    return error


def _checksum_check(bundle: ConformanceBundle) -> _RuntimeFailureCheck:
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
        (
            "evaluator registry",
            bundle.evaluator_registry,
            bundle.evaluator_registry.declared_checksum,
        ),
    )
    failures: list[ConformanceFailure] = []
    first_error: Exception | None = None
    for label, asset, declared in assets:
        try:
            actual = _asset_content_checksum(asset)
        except Exception as error:
            actual = None
            if first_error is None:
                first_error = error
        if actual != declared:
            failures.append(
                ConformanceFailure(
                    code=ConformanceFailureCode.CHECKSUM_MISMATCH,
                    message=f"{label} content checksum differs from its immutable declaration",
                )
            )
    return _RuntimeFailureCheck(tuple(failures), first_error)


def _evaluator_pin_check(bundle: ConformanceBundle) -> _RuntimeFailureCheck:
    """Resolve every live evaluator against the engineering-pinned registry identity gate."""

    first_error: Exception | None = None
    try:
        dependency_checksum = _derivation_dependency_checksum()
    except Exception as error:
        dependency_checksum = None
        first_error = _ordinary_review_cause(error)

    clauses = {clause.clause_id: clause for clause in bundle.theory.clauses}
    failures: list[ConformanceFailure] = []
    for rule in bundle.rulebook.rules:
        clause = clauses.get(rule.theory_clause_id)
        if clause is None:
            failures.append(
                ConformanceFailure(
                    code=ConformanceFailureCode.PIN_MISMATCH,
                    clause_id=rule.theory_clause_id,
                    rule_id=rule.rule_id,
                    message="derivation evaluator cannot resolve its Theory clause",
                )
            )
            continue
        try:
            if dependency_checksum is None:
                raise V8EvaluatorReviewRequired(clause_id=clause.clause_id)
            _reviewed_derivation_artifact(
                bundle,
                clause,
                rule,
                dependency_checksum=dependency_checksum,
            )
        except Exception as error:
            if first_error is None:
                first_error = _ordinary_review_cause(error)
            failures.append(
                ConformanceFailure(
                    code=ConformanceFailureCode.PIN_MISMATCH,
                    clause_id=clause.clause_id,
                    rule_id=rule.rule_id,
                    message=(
                        "live derivation evaluator differs from its engineering-pinned "
                        "registry identity"
                    ),
                )
            )

    try:
        _adequacy_pin(bundle)
    except Exception as error:
        if first_error is None:
            first_error = _ordinary_review_cause(error)
        failures.append(
            ConformanceFailure(
                code=ConformanceFailureCode.PIN_MISMATCH,
                clause_id="DT-E-INTERFERENCE-ESTIMAND",
                rule_id="V8-E-INTERFERENCE",
                message=(
                    "live adequacy evaluator differs from its engineering-pinned registry identity"
                ),
            )
        )
    return _RuntimeFailureCheck(tuple(failures), first_error)


def _fresh_runtime_preflight(bundle: ConformanceBundle) -> _RuntimeBundlePreflight:
    """Recompute cross-asset, checksum, and live evaluator closure in one pass."""

    try:
        report = evaluate_conformance(bundle)
    except Exception as error:
        raise V8EvaluatorReviewRequired() from error
    checksum_check = _checksum_check(bundle)
    evaluator_check = _evaluator_pin_check(bundle)
    failures = (
        *report.failures,
        *checksum_check.failures,
        *evaluator_check.failures,
    )
    return _RuntimeBundlePreflight(
        report=report.model_copy(update={"passed": not failures, "failures": failures}),
        error=checksum_check.error or evaluator_check.error,
    )


def verify_runtime_bundle(bundle: ConformanceBundle) -> ConformanceReport:
    """Verify both cross-asset conformance and the bytes represented by each pin."""

    return _fresh_runtime_preflight(bundle).report


def require_reviewed_evaluator_bundle(bundle: ConformanceBundle) -> None:
    """Reject unregistered contract/registry successors before any runtime manifest exists."""

    preflight = _fresh_runtime_preflight(bundle)
    if not _reviewed_bundle_identity(bundle) or not preflight.report.passed:
        raise V8EvaluatorReviewRequired() from preflight.error


def _rule_pins(bundle: ConformanceBundle) -> tuple[ImplementationRulePin, ...]:
    clauses = {clause.clause_id: clause for clause in bundle.theory.clauses}
    dependency_checksum = _derivation_dependency_checksum()
    pins: list[ImplementationRulePin] = []
    for rule in bundle.rulebook.rules:
        clause = clauses[rule.theory_clause_id]
        artifact = _reviewed_derivation_artifact(
            bundle,
            clause,
            rule,
            dependency_checksum=dependency_checksum,
        )
        pins.append(
            ImplementationRulePin(
                theory_id=bundle.theory.theory_id,
                theory_version=bundle.theory.theory_version,
                theory_checksum=bundle.theory.declared_checksum,
                rule_id=rule.rule_id,
                rule_version=rule.rule_version,
                rule_checksum=rule_content_checksum(rule),
                theory_clause_id=rule.theory_clause_id,
                theory_clause_version=rule.theory_clause_version,
                implementation_artifact_id=artifact.artifact_id,
                implementation_artifact_version=artifact.artifact_version,
                implementation_artifact_checksum=artifact.artifact_checksum,
                required_predicate_ids=tuple(
                    item.predicate_id for item in rule.required_predicates
                ),
                irrelevant_predicates=rule.irrelevant_predicates,
            )
        )
    return tuple(pins)


def _adequacy_pin(bundle: ConformanceBundle) -> AdequacyEvaluatorPin:
    clause = next(
        item for item in bundle.theory.clauses if item.clause_id == "DT-E-INTERFERENCE-ESTIMAND"
    )
    rule = next(
        item
        for item in bundle.rulebook.rules
        if item.theory_clause_id == "DT-E-INTERFERENCE-ESTIMAND"
    )
    artifact = _reviewed_adequacy_artifact(bundle, clause, rule)
    return AdequacyEvaluatorPin(
        theory_id=bundle.theory.theory_id,
        theory_version=bundle.theory.theory_version,
        theory_checksum=bundle.theory.declared_checksum,
        theory_clause_id=clause.clause_id,
        theory_clause_version=clause.clause_version,
        rule_id=rule.rule_id,
        rule_version=rule.rule_version,
        rule_checksum=rule_content_checksum(rule),
        implementation_artifact_id=artifact.artifact_id,
        implementation_artifact_version=artifact.artifact_version,
        implementation_artifact_checksum=artifact.artifact_checksum,
    )


def build_execution_manifest(
    bundle: ConformanceBundle,
    conformance: ConformanceReport,
) -> V8ExecutionManifest:
    """Create the immutable join record for the exact verified execution bytes."""

    del conformance
    preflight = _fresh_runtime_preflight(bundle)
    if not _reviewed_bundle_identity(bundle) or not preflight.report.passed:
        raise V8EvaluatorReviewRequired() from preflight.error
    try:
        rule_pins = _rule_pins(bundle)
        adequacy_pin = _adequacy_pin(bundle)
    except V8EvaluatorReviewRequired:
        raise
    except Exception as exc:
        raise V8EvaluatorReviewRequired() from exc
    manifest_id = stable_id(
        "v8-execution-manifest",
        bundle.theory.declared_checksum,
        bundle.rulebook.declared_checksum,
        bundle.profile_closure.declared_checksum,
        bundle.reference_registry.declared_checksum,
        bundle.fixture_set.declared_checksum,
        bundle.evaluator_registry.declared_checksum,
        *(pin.rule_checksum for pin in rule_pins),
        *(pin.implementation_artifact_checksum for pin in rule_pins),
        adequacy_pin.implementation_artifact_checksum,
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
        evaluator_registry_id=bundle.evaluator_registry.registry_id,
        evaluator_registry_version=bundle.evaluator_registry.registry_version,
        evaluator_registry_checksum=bundle.evaluator_registry.declared_checksum,
        implementation_rules=rule_pins,
        adequacy_evaluator=adequacy_pin,
        release_blocker_issue_ids=preflight.report.release_blocker_issue_ids,
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
        if (
            state is DeterminabilityState.DETERMINATE
            and request.profile_coverage.contract_review.issue_id
            == PROFILE_COVERAGE_REVIEW_ISSUE_ID
        ):
            state = DeterminabilityState.INSUFFICIENT_INFORMATION
        payload: JsonValue | None = None
        count_evidence: tuple[str, ...] = ()
        if state is DeterminabilityState.DETERMINATE:
            payload, count_evidence = _resolved_payload(claim_type, request)
        evidence_ids = tuple(dict.fromkeys((*base_evidence, *count_evidence)))
        if payload is None:
            if state is DeterminabilityState.DETERMINATE:
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
                PredicateProofReference(
                    predicate_id=predicate_id,
                    predicate_value=KnowledgeValue[JsonValue].model_validate(
                        value.model_dump(mode="json")
                    ),
                )
                for predicate_id, value in required
            ),
            input_record_references=(
                (
                    InputRecordProofReference(
                        record_id=record.count_id,
                        record_kind=record.kind,
                        record_value=record.value,
                        record_scope=record.scope,
                    ),
                )
                if claim_type in {"EXPERIMENTAL_UNIT_COUNT", "BIOLOGICAL_SOURCE_COUNT"}
                and (
                    record := _selected_count_record(
                        request,
                        (
                            request.experimental_unit_count_record_id
                            if claim_type == "EXPERIMENTAL_UNIT_COUNT"
                            else request.biological_source_count_record_id
                        ),
                        (
                            CanonicalCountKind.EXPERIMENTAL_UNIT_COUNT
                            if claim_type == "EXPERIMENTAL_UNIT_COUNT"
                            else CanonicalCountKind.BIOLOGICAL_SOURCE_COUNT
                        ),
                    )
                )
                else ()
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
    "V8EvaluatorReviewRequired",
    "build_execution_manifest",
    "derive_claim_set",
    "load_runtime_bundle",
    "require_reviewed_evaluator_bundle",
    "rule_content_checksum",
    "verify_runtime_bundle",
]
