"""Predicati valutabili sul grafo (PRD 8.1).

Le precondizioni delle regole sono espresse in questo piccolo linguaggio, non
in codice Python: cosi un biostatistico puo revisionare e modificare una regola
senza toccare il software e senza retraining (PRD FR-018, 11.2).

Un predicato sconosciuto non e mai vero per default: la regola diventa
`unevaluable` e viene riportata.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from ntruth.graph.builder import BuildResult
from ntruth.graph.index import GraphIndex
from ntruth.schemas.core import Confidence
from ntruth.schemas.experiment import (
    Contrast,
    DataSufficiency,
    Endpoint,
    Factor,
    ProcessFact,
    StatisticalModelFact,
    UnitAssessment,
)
from ntruth.schemas.graph import TECHNICAL_TYPES, NodeType, rank_of

#: Alias usati nelle regole: nomi brevi e di dominio verso i tipi del grafo.
TYPE_ALIASES: dict[str, NodeType] = {
    "culture": NodeType.CELL_CULTURE,
    "cellculture": NodeType.CELL_CULTURE,
    "preparation": NodeType.CELL_CULTURE,
    "donor": NodeType.HUMAN_DONOR,
    "humandonor": NodeType.HUMAN_DONOR,
    "subject": NodeType.HUMAN_DONOR,
    "animal": NodeType.ANIMAL,
    "dam": NodeType.DAM,
    "litter": NodeType.LITTER,
    "cage": NodeType.CAGE,
    "cellline": NodeType.CELL_LINE,
    "cell_line": NodeType.CELL_LINE,
    "tissue": NodeType.TISSUE,
    "organoid": NodeType.ORGANOID,
    "explant": NodeType.EXPLANT,
    "pool": NodeType.POOL,
    "aliquot": NodeType.ALIQUOT,
    "plate": NodeType.PLATE,
    "well": NodeType.WELL,
    "section": NodeType.SECTION_SLICE,
    "slice": NodeType.SECTION_SLICE,
    "field": NodeType.FIELD,
    "image": NodeType.FIELD,
    "roi": NodeType.ROI,
    "cell": NodeType.CELL,
    "nucleus": NodeType.CELL,
    "library": NodeType.LIBRARY,
    "run": NodeType.RUN,
    "batch": NodeType.BATCH,
    "instrument": NodeType.INSTRUMENT,
    "cohort": NodeType.COHORT,
    "primarysample": NodeType.PRIMARY_SAMPLE,
}

_CALL = re.compile(r"^(?P<negated>not\s+)?(?P<name>[a-z_][a-z0-9_]*)\s*\((?P<args>.*)\)$", re.S)

_CONFIDENCE_ORDER = [Confidence.UNKNOWN, Confidence.LOW, Confidence.MEDIUM, Confidence.HIGH]


class UnknownPredicate(LookupError):
    """Predicato non riconosciuto: la regola non puo essere valutata."""


def resolve_type(token: str) -> NodeType | None:
    key = token.strip().strip("'\"").lower().replace(" ", "").replace("_", "")
    for name, node_type in TYPE_ALIASES.items():
        if name.replace("_", "") == key:
            return node_type
    for node_type in NodeType:
        if str(node_type).lower().replace("_", "") == key:
            return node_type
    return None


@dataclass
class RuleContext:
    """Tutto cio che una regola puo osservare. Nessun accesso al testo grezzo."""

    index: GraphIndex
    build: BuildResult
    assessment: UnitAssessment
    factor: Factor | None
    contrast: Contrast | None
    endpoint: Endpoint | None

    # ---------------------------------------------------------------- helpers

    @property
    def sufficiency(self) -> DataSufficiency:
        return self.assessment.data_sufficiency

    @property
    def models(self) -> tuple[StatisticalModelFact, ...]:
        return self.build.models

    @property
    def processes(self) -> tuple[ProcessFact, ...]:
        return self.build.processes

    def has_process(self, kind: str) -> bool:
        return any(p.kind == kind for p in self.processes)

    def model_levels(self) -> set[NodeType]:
        levels: set[NodeType] = set()
        for model in self.models:
            levels.update(model.accounts_for)
        return levels


PredicateFn = Callable[[RuleContext, list[str]], bool]
REGISTRY: dict[str, PredicateFn] = {}


def predicate(name: str) -> Callable[[PredicateFn], PredicateFn]:
    def decorator(fn: PredicateFn) -> PredicateFn:
        REGISTRY[name] = fn
        return fn

    return decorator


def evaluate(expression: str, context: RuleContext) -> bool:
    """Valuta un predicato normalizzato. Solleva UnknownPredicate se ignoto."""
    match = _CALL.match(expression.strip())
    if not match:
        raise UnknownPredicate(expression)
    name = match.group("name")
    fn = REGISTRY.get(name)
    if fn is None:
        raise UnknownPredicate(expression)
    args = [a.strip() for a in match.group("args").split(",") if a.strip()]
    value = fn(context, args)
    return not value if match.group("negated") else value


# ------------------------------------------------------------- struttura grafo


@predicate("level_present")
def _level_present(ctx: RuleContext, args: list[str]) -> bool:
    node_type = resolve_type(args[0])
    return node_type is not None and ctx.index.has(node_type)


@predicate("nested")
def _nested(ctx: RuleContext, args: list[str]) -> bool:
    child, parent = resolve_type(args[0]), resolve_type(args[1])
    return child is not None and parent is not None and ctx.index.is_nested_in(child, parent)


@predicate("derived")
def _derived(ctx: RuleContext, args: list[str]) -> bool:
    from ntruth.schemas.graph import RelationType

    child, parent = resolve_type(args[0]), resolve_type(args[1])
    if child is None or parent is None:
        return False
    return ctx.index.relation(RelationType.DERIVED_FROM, child, parent) is not None


@predicate("multiple_instances")
def _multiple_instances(ctx: RuleContext, args: list[str]) -> bool:
    node_type = resolve_type(args[0])
    if node_type is None:
        return False
    count = ctx.index.derived_count(node_type)
    return count is not None and count > 1


@predicate("single_instance")
def _single_instance(ctx: RuleContext, args: list[str]) -> bool:
    node_type = resolve_type(args[0])
    if node_type is None:
        return False
    return ctx.index.derived_count(node_type) == 1


@predicate("count_unknown")
def _count_unknown(ctx: RuleContext, args: list[str]) -> bool:
    node_type = resolve_type(args[0])
    return node_type is not None and ctx.index.derived_count(node_type) is None


@predicate("technical_level")
def _technical_level(ctx: RuleContext, args: list[str]) -> bool:
    node_type = resolve_type(args[0])
    return node_type is not None and node_type in TECHNICAL_TYPES


@predicate("independence_declared")
def _independence_declared(ctx: RuleContext, args: list[str]) -> bool:
    node_type = resolve_type(args[0])
    if node_type is None:
        return False
    return bool(ctx.index.attribute(node_type, "declared_independent"))


# --------------------------------------------------------------------- unita


@predicate("assigned_at")
def _assigned_at(ctx: RuleContext, args: list[str]) -> bool:
    node_type = resolve_type(args[0])
    return node_type is not None and ctx.assessment.experimental_unit is node_type


@predicate("assigned_at_or_above")
def _assigned_at_or_above(ctx: RuleContext, args: list[str]) -> bool:
    node_type = resolve_type(args[0])
    unit = ctx.assessment.experimental_unit
    if node_type is None or unit is None:
        return False
    unit_rank, target_rank = rank_of(unit), rank_of(node_type)
    if unit_rank is None or target_rank is None:
        return unit is node_type
    return unit_rank <= target_rank


@predicate("assigned_at_or_below")
def _assigned_at_or_below(ctx: RuleContext, args: list[str]) -> bool:
    node_type = resolve_type(args[0])
    unit = ctx.assessment.experimental_unit
    if node_type is None or unit is None:
        return False
    unit_rank, target_rank = rank_of(unit), rank_of(node_type)
    if unit_rank is None or target_rank is None:
        return unit is node_type
    return unit_rank >= target_rank


@predicate("assignment_unknown")
def _assignment_unknown(ctx: RuleContext, args: list[str]) -> bool:
    return ctx.assessment.experimental_unit is None


@predicate("analyzed_as")
def _analyzed_as(ctx: RuleContext, args: list[str]) -> bool:
    node_type = resolve_type(args[0])
    return node_type is not None and ctx.assessment.analytical_unit is node_type


@predicate("measured_on")
def _measured_on(ctx: RuleContext, args: list[str]) -> bool:
    node_type = resolve_type(args[0])
    return node_type is not None and ctx.assessment.observational_unit is node_type


@predicate("analysis_finer_than_assignment")
def _analysis_finer(ctx: RuleContext, args: list[str]) -> bool:
    if not _finer(ctx.assessment.analytical_unit, ctx.assessment.experimental_unit):
        return False

    # ``rank_of`` descrive una gerarchia operativa, non la direzione della
    # trasformazione dei campioni. Un pool compare piu in basso dell'animale
    # nella gerarchia, ma combina unita allocate e quindi non crea osservazioni
    # piu fini. Lo stesso vale per un'aggregazione esplicita quando il numero di
    # unita analizzate non supera quello delle unita allocate. Senza entrambi i
    # conteggi il motore non presume che l'aggregazione abbia ridotto la
    # granularita e conserva il segnale prudenziale.
    allocated = ctx.assessment.n_allocated
    analyzed = ctx.assessment.n_analyzed
    aggregation_declared = (
        ctx.assessment.analytical_unit is NodeType.POOL and ctx.has_process("pooling")
    ) or ctx.has_process("aggregation")
    return not (
        aggregation_declared
        and allocated is not None
        and analyzed is not None
        and analyzed <= allocated
    )


@predicate("observation_finer_than_assignment")
def _observation_finer(ctx: RuleContext, args: list[str]) -> bool:
    return _finer(ctx.assessment.observational_unit, ctx.assessment.experimental_unit)


def _finer(candidate: NodeType | None, reference: NodeType | None) -> bool:
    if candidate is None or reference is None:
        return False
    candidate_rank, reference_rank = rank_of(candidate), rank_of(reference)
    if candidate_rank is None or reference_rank is None:
        return False
    return candidate_rank > reference_rank


@predicate("n_independent_unknown")
def _n_independent_unknown(ctx: RuleContext, args: list[str]) -> bool:
    return ctx.assessment.n_independent is None


@predicate("declared_equals_observational")
def _declared_equals_observational(ctx: RuleContext, args: list[str]) -> bool:
    declared = ctx.assessment.n_declared
    observational = ctx.assessment.n_observational
    return declared is not None and observational is not None and declared == observational


@predicate("declared_exceeds_independent")
def _declared_exceeds_independent(ctx: RuleContext, args: list[str]) -> bool:
    declared = ctx.assessment.n_declared
    independent = ctx.assessment.n_independent
    return declared is not None and independent is not None and declared > independent


@predicate("declared_n_scope_global")
def _declared_n_scope_global(ctx: RuleContext, args: list[str]) -> bool:
    statements = [s for s in ctx.build.n_statements if s.value is not None]
    return bool(statements) and all(s.scope.is_global for s in statements)


@predicate("multiple_scopes")
def _multiple_scopes(ctx: RuleContext, args: list[str]) -> bool:
    return len(ctx.build.endpoints) > 1 or len(ctx.build.contrasts) > 1


@predicate("ambiguous_replicate_term")
def _ambiguous_replicate_term(ctx: RuleContext, args: list[str]) -> bool:
    return any(s.node_type is None and s.value is not None for s in ctx.build.n_statements)


# ------------------------------------------------------------------- modello


@predicate("model_declared")
def _model_declared(ctx: RuleContext, args: list[str]) -> bool:
    return bool(ctx.models)


@predicate("model_is_mixed")
def _model_is_mixed(ctx: RuleContext, args: list[str]) -> bool:
    return any(m.kind == "mixed" for m in ctx.models)


@predicate("model_is_simple")
def _model_is_simple(ctx: RuleContext, args: list[str]) -> bool:
    return any(m.kind == "simple" for m in ctx.models) and not any(
        m.kind == "mixed" for m in ctx.models
    )


@predicate("model_accounts_for")
def _model_accounts_for(ctx: RuleContext, args: list[str]) -> bool:
    node_type = resolve_type(args[0])
    return node_type is not None and node_type in ctx.model_levels()


@predicate("model_accounts_for_assignment")
def _model_accounts_for_assignment(ctx: RuleContext, args: list[str]) -> bool:
    """Il modello dichiara esplicitamente il livello di assegnazione o un suo antenato."""
    unit = ctx.assessment.experimental_unit
    if unit is None:
        return False
    levels = ctx.model_levels()
    if not levels:
        return False
    if unit in levels:
        return True
    return any(ancestor in levels for ancestor in ctx.index.ancestors(unit))


# ------------------------------------------------------------------ processo


@predicate("pooling_present")
def _pooling_present(ctx: RuleContext, args: list[str]) -> bool:
    return ctx.has_process("pooling")


@predicate("aggregation_present")
def _aggregation_present(ctx: RuleContext, args: list[str]) -> bool:
    """Anche il pooling e un'aggregazione: cambia il record, non l'unita biologica."""
    return ctx.has_process("aggregation") or ctx.has_process("pooling")


@predicate("repeated_measures_present")
def _repeated_measures_present(ctx: RuleContext, args: list[str]) -> bool:
    return ctx.has_process("repeated_measure")


@predicate("exclusions_reported")
def _exclusions_reported(ctx: RuleContext, args: list[str]) -> bool:
    return ctx.has_process("exclusion")


@predicate("blinding_reported")
def _blinding_reported(ctx: RuleContext, args: list[str]) -> bool:
    return ctx.has_process("blinding")


@predicate("perfect_confounding")
def _perfect_confounding(ctx: RuleContext, args: list[str]) -> bool:
    return ctx.has_process("confounding")


@predicate("contradiction_unresolved")
def _contradiction_unresolved(ctx: RuleContext, args: list[str]) -> bool:
    return any(c.status == "unresolved" for c in ctx.build.contradictions)


@predicate("factor_kind")
def _factor_kind(ctx: RuleContext, args: list[str]) -> bool:
    return ctx.factor is not None and ctx.factor.kind == args[0].strip().strip("'\"")


@predicate("endpoint_unlinked")
def _endpoint_unlinked(ctx: RuleContext, args: list[str]) -> bool:
    return ctx.endpoint is None or ctx.endpoint.measured_on is None


# -------------------------------------------------------------- completezza


@predicate("sufficiency_below")
def _sufficiency_below(ctx: RuleContext, args: list[str]) -> bool:
    """`sufficiency_below(source_independence, medium)`."""
    dimension = args[0].strip().strip("'\"")
    threshold = (
        Confidence(args[1].strip().strip("'\"").lower()) if len(args) > 1 else Confidence.MEDIUM
    )
    value = getattr(ctx.sufficiency, dimension, None)
    if value is None:
        raise UnknownPredicate(f"sufficiency_below: dimensione ignota '{dimension}'")
    return _CONFIDENCE_ORDER.index(value) < _CONFIDENCE_ORDER.index(threshold)


@predicate("sufficiency_at_least")
def _sufficiency_at_least(ctx: RuleContext, args: list[str]) -> bool:
    return not _sufficiency_below(ctx, args)
