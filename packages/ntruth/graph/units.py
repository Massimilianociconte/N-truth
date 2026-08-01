"""Risoluzione delle unita e dei tre n (PRD 7.1, 12.2).

Principio fondamentale: l'unita e relativa al fattore. Nello stesso studio il
genotipo puo essere definito a livello di animale, un farmaco applicato al
pozzetto e il tempo essere una misura ripetuta. Il resolver deriva l'unita
pertinente a ciascun contrasto ed endpoint e non riduce mai n a un campo globale.
"""

from __future__ import annotations

from ntruth.graph.builder import BuildResult
from ntruth.graph.index import GraphIndex
from ntruth.schemas.core import Confidence, Provenance, ProvenanceKind, stable_id
from ntruth.schemas.experiment import (
    ConditionalScenario,
    Contrast,
    DataSufficiency,
    Endpoint,
    Factor,
    Inferability,
    NKind,
    NScope,
    NStatement,
    ProcessFact,
    Question,
    RiskLabel,
    StatisticalModelFact,
    UnitAssessment,
)
from ntruth.schemas.graph import (
    BIOLOGICAL_SOURCE_TYPES,
    GraphNode,
    NodeType,
    RelationType,
)

_CONFIRMED_INDEPENDENCE_ORIGINS = frozenset(
    {ProvenanceKind.USER, ProvenanceKind.ADJUDICATION, ProvenanceKind.TABULAR}
)


def _confirmed_source_independence(node: GraphNode | None) -> bool:
    """True solo per una conferma o un campo strutturato, mai per autovalutazioni."""

    return bool(
        node is not None
        and node.attributes.get("declared_independent")
        and node.provenance.origin in _CONFIRMED_INDEPENDENCE_ORIGINS
    )


def resolve_units(
    block_id: str, build: BuildResult
) -> tuple[tuple[UnitAssessment, ...], tuple[Question, ...]]:
    """Un assessment per ogni combinazione fattore/contrasto/endpoint (GEN-006)."""
    index = GraphIndex(build.hierarchy)
    questions: list[Question] = []
    assessments: list[UnitAssessment] = []

    endpoints: tuple[Endpoint | None, ...] = build.endpoints or (None,)

    if not build.factors:
        assessments.append(_global_assessment(block_id, index, build, endpoints[0], questions))
        return tuple(assessments), tuple(questions)

    for factor in build.factors:
        factor_contrasts: tuple[Contrast | None, ...] = tuple(
            c for c in build.contrasts if factor.id in c.factor_ids
        ) or (None,)
        for contrast in factor_contrasts:
            scoped_endpoints = _endpoints_for_contrast(
                block_id, build, factor, contrast, endpoints, questions
            )
            for endpoint in scoped_endpoints:
                groups = _groups_for_scope(build, contrast, endpoint)
                for group in groups:
                    assessments.append(
                        _assess(
                            block_id,
                            index,
                            build,
                            factor,
                            contrast,
                            endpoint,
                            group,
                            questions,
                        )
                    )
    return tuple(assessments), _unique_questions(questions)


def _endpoints_for_contrast(
    block_id: str,
    build: BuildResult,
    factor: Factor,
    contrast: Contrast | None,
    fallback: tuple[Endpoint | None, ...],
    questions: list[Question],
) -> tuple[Endpoint | None, ...]:
    """Evita il prodotto cartesiano quando piu endpoint non sono legati."""

    if contrast is not None and contrast.endpoint_ids:
        return tuple(
            endpoint
            for endpoint_id in contrast.endpoint_ids
            if (endpoint := next((e for e in build.endpoints if e.id == endpoint_id), None))
            is not None
        )
    if len(fallback) <= 1:
        return fallback
    if contrast is None and len(build.factors) == 1:
        # Un solo fattore senza contrasto esplicito: gli endpoint appartengono
        # comunque allo stesso scope di fattore, senza incrocio tra confronti.
        return fallback

    scope = NScope(
        factor_id=factor.id,
        contrast_id=contrast.id if contrast else None,
    )
    questions.append(
        Question(
            id=stable_id("qst", block_id, "endpoint-binding", scope.key()),
            text=(
                f"Quali endpoint appartengono al confronto "
                f"'{contrast.label if contrast else factor.name}'?"
            ),
            reason="piu endpoint presenti senza legame univoco al contrasto",
            missing_field="contrast.endpoint_ids",
            scope=scope,
        )
    )
    return (None,)


def _groups_for_scope(
    build: BuildResult, contrast: Contrast | None, endpoint: Endpoint | None
) -> tuple[str | None, ...]:
    """Apre assessment per gruppo solo quando almeno un gruppo e nominato."""

    if contrast is None:
        return (None,)
    explicit = {
        statement.scope.group.casefold()
        for statement in build.n_statements
        if statement.scope.contrast_id == contrast.id
        and statement.scope.group not in (None, "per_group")
        and (endpoint is None or statement.scope.endpoint_id in (None, endpoint.id))
    }
    if not explicit:
        return (None,)
    groups = tuple(
        group
        for group in (contrast.group_a, contrast.group_b)
        if group is not None and group.casefold() in explicit
    )
    # Se una fonte specifica un solo gruppo, apriamo anche l'altro lato del
    # contrasto: il valore mancante deve produrre una domanda, non sparire.
    if groups and contrast.group_a and contrast.group_b:
        return (contrast.group_a, contrast.group_b)
    return groups or (None,)


def _unique_questions(questions: list[Question]) -> tuple[Question, ...]:
    """Le domande sono deduplicate per ID: la stessa lacuna si chiede una volta."""
    seen: dict[str, Question] = {}
    for question in questions:
        seen.setdefault(question.id, question)
    return tuple(seen.values())


# ------------------------------------------------------------------- assessment


def _assess(
    block_id: str,
    index: GraphIndex,
    build: BuildResult,
    factor: Factor,
    contrast: Contrast | None,
    endpoint: Endpoint | None,
    group: str | None,
    questions: list[Question],
) -> UnitAssessment:
    scope = NScope(
        factor_id=factor.id,
        contrast_id=contrast.id if contrast else None,
        endpoint_id=endpoint.id if endpoint else None,
        group=group,
    )

    biological_unit = _biological_unit(index)
    observational_unit = _observational_unit(index, endpoint)
    analytical_unit, analytical_note = _analytical_unit(index, build, observational_unit)
    experimental_unit, exp_note = _experimental_unit(index, build, factor)

    n_observational = (
        index.derived_count_for_scope(
            observational_unit,
            factor_name=factor.name,
            group=group,
        )
        if observational_unit
        else None
    )
    n_declared, declared_statement = _declared_n(
        build.n_statements,
        scope,
        analytical_unit,
        allow_scope_fallback=(
            contrast is not None
            and len(build.contrasts) <= 1
            and len(build.endpoints) <= 1
            and group is None
        ),
    )
    if (
        declared_statement is not None
        and declared_statement.node_type is observational_unit
        and declared_statement.kind
        in {NKind.ANALYZED, NKind.OBSERVATIONAL, NKind.INDEPENDENT, NKind.DECLARED}
    ):
        n_observational = declared_statement.value

    n_allocated: int | None = None
    n_independent: int | None = None
    independent_entity: str | None = None
    if experimental_unit is not None:
        n_allocated = index.derived_count_for_scope(
            experimental_unit,
            factor_name=factor.name,
            group=group,
        )
        n_independent = n_allocated
        if (
            declared_statement is not None
            and declared_statement.node_type is experimental_unit
            and declared_statement.kind is NKind.ALLOCATED
        ):
            n_allocated = declared_statement.value
            n_independent = declared_statement.value
        elif (
            declared_statement is not None
            and declared_statement.node_type is experimental_unit
            and declared_statement.kind in {NKind.INDEPENDENT, NKind.DECLARED}
        ):
            n_independent = declared_statement.value
        elif (
            declared_statement is not None
            and declared_statement.node_type is experimental_unit
            and analytical_unit is experimental_unit
            and declared_statement.kind is NKind.ANALYZED
        ):
            # Un'esclusione della stessa unita allocata riduce anche il numero
            # di unita indipendenti analizzate; non vale invece per aggregati
            # analitici distinti (per esempio pool di animali).
            n_independent = declared_statement.value
        independent_entity = str(experimental_unit)

    n_analyzed = (
        index.derived_count_for_scope(
            analytical_unit,
            factor_name=factor.name,
            group=group,
        )
        if analytical_unit is not None
        else None
    )
    if (
        declared_statement is not None
        and declared_statement.node_type is analytical_unit
        and declared_statement.kind in {NKind.ANALYZED, NKind.DECLARED}
    ):
        n_analyzed = declared_statement.value

    clusters = _clusters(index, build, experimental_unit)
    sufficiency = _sufficiency(index, build, factor, experimental_unit)
    conditional_scenarios, independence_question = _conditional_independence_scenarios(
        block_id=block_id,
        index=index,
        factor=factor,
        scope=scope,
        experimental_unit=experimental_unit,
        n_candidate=n_independent,
        group=group,
        clusters=clusters,
        source_independence=sufficiency.source_independence,
    )
    if independence_question is not None:
        questions.append(independence_question)
    inferability = _inferability(
        factor,
        experimental_unit,
        n_independent,
        sufficiency,
        conditional_scenarios,
    )

    # Nei casi con due rami numerici entrambi derivati dal grafo, il valore
    # scalare sarebbe una falsa scelta implicita del ramo ``if_confirmed``.
    # Il conteggio candidato resta disponibile come ``n_allocated`` e i valori
    # di n indipendente vivono esclusivamente nello scenario condizionale.
    if (
        conditional_scenarios
        or sufficiency.source_independence is not Confidence.HIGH
        or inferability is Inferability.NOT_INFERABLE
    ):
        n_independent = None

    rationale = _rationale(
        factor=factor,
        experimental_unit=experimental_unit,
        observational_unit=observational_unit,
        analytical_unit=analytical_unit,
        n_independent=n_independent,
        n_observational=n_observational,
        clusters=clusters,
        extra_notes=[note for note in (exp_note, analytical_note) if note],
    )

    if (
        experimental_unit is not None
        and n_independent is None
        and n_allocated is None
        and not conditional_scenarios
    ):
        questions.append(
            Question(
                id=stable_id("qst", block_id, "count", str(experimental_unit), scope.describe()),
                text=(
                    f"Quante unita indipendenti di tipo {experimental_unit} sono state usate "
                    f"per il confronto {contrast.label if contrast else factor.name}?"
                ),
                reason="livello di intervento identificato ma conteggio assente",
                missing_field=f"count[{experimental_unit}]",
                scope=scope,
                priority=95,
                decisive=True,
                impact="Senza un conteggio scoped non e determinabile n indipendente.",
            )
        )

    experimental_node = index.node(experimental_unit) if experimental_unit else None
    observational_node = index.node(observational_unit) if observational_unit else None
    evidence_ids = tuple(
        dict.fromkeys(
            [
                *factor.evidence_ids,
                *(endpoint.evidence_ids if endpoint else ()),
                *(experimental_node.evidence_ids if experimental_node else ()),
                *(observational_node.evidence_ids if observational_node else ()),
                *(declared_statement.evidence_ids if declared_statement else ()),
            ]
        )
    )

    return UnitAssessment(
        id=stable_id("uas", block_id, scope.key()),
        scope=scope,
        biological_unit=biological_unit,
        experimental_unit=experimental_unit,
        observational_unit=observational_unit,
        analytical_unit=analytical_unit,
        n_declared=n_declared,
        n_allocated=n_allocated,
        n_analyzed=n_analyzed,
        n_observational=n_observational,
        n_independent=n_independent,
        independent_entity_type=independent_entity if n_independent is not None else None,
        cluster_types=clusters,
        inferability=inferability,
        conditional_scenarios=conditional_scenarios,
        risk=RiskLabel.INSUFFICIENT
        if inferability is Inferability.NOT_INFERABLE
        else RiskLabel.NO_ISSUE,
        data_sufficiency=sufficiency,
        rationale=rationale,
        evidence_ids=evidence_ids,
        provenance=Provenance(
            origin=ProvenanceKind.DERIVED,
            evidence_ids=evidence_ids,
            derivation="risoluzione deterministica delle unita dal grafo",
        ),
    )


def _global_assessment(
    block_id: str,
    index: GraphIndex,
    build: BuildResult,
    endpoint: Endpoint | None,
    questions: list[Question],
) -> UnitAssessment:
    """Nessun fattore identificato: si dichiara l'astensione, non un n globale."""
    scope = NScope(endpoint_id=endpoint.id if endpoint else None, is_global=endpoint is None)
    observational_unit = _observational_unit(index, endpoint)
    questions.append(
        Question(
            id=stable_id("qst", block_id, "no_factor"),
            text=(
                "Quale fattore sperimentale viene confrontato e a quale livello e stato allocato?"
            ),
            reason="nessun fattore o intervento identificato nel materiale",
            missing_field="factors",
            priority=100,
            decisive=True,
            impact="Senza fattore e allocation non sono definibili unita sperimentale e n.",
        )
    )
    return UnitAssessment(
        id=stable_id("uas", block_id, "global"),
        scope=scope,
        biological_unit=_biological_unit(index),
        experimental_unit=None,
        observational_unit=observational_unit,
        analytical_unit=observational_unit,
        n_declared=None,
        n_observational=index.derived_count(observational_unit) if observational_unit else None,
        n_independent=None,
        inferability=Inferability.NOT_INFERABLE,
        risk=RiskLabel.INSUFFICIENT,
        data_sufficiency=DataSufficiency(),
        rationale=(
            "Nessun fattore sperimentale identificato: l'unita sperimentale non e definibile "
            "e n indipendente resta indeterminato."
        ),
        evidence_ids=(),
        provenance=Provenance(
            origin=ProvenanceKind.DERIVED,
            derivation="nessun fattore estratto dal materiale",
        ),
    )


# ----------------------------------------------------------------------- unita


def _biological_unit(index: GraphIndex) -> NodeType | None:
    sources = [t for t in index.levels if t in BIOLOGICAL_SOURCE_TYPES]
    return sources[0] if sources else None


def _observational_unit(index: GraphIndex, endpoint: Endpoint | None) -> NodeType | None:
    if endpoint is not None and endpoint.measured_on is not None:
        return endpoint.measured_on
    for relation in index.relations_of_type(RelationType.MEASURED_ON):
        target = index.node_type_of(relation.target)
        if target is not None:
            return target
    return index.finest_level()


def _analytical_unit(
    index: GraphIndex, build: BuildResult, observational_unit: NodeType | None
) -> tuple[NodeType | None, str | None]:
    """Record che entra nel modello statistico (PRD 7: unita analitica)."""
    pooling = _process(build.processes, "pooling")
    if pooling is not None and index.has(NodeType.POOL):
        return NodeType.POOL, (
            "l'analisi usa pool: i membri del pool non restano osservabili individualmente"
        )
    aggregation = _process(build.processes, "aggregation")
    if aggregation is not None and aggregation.node_type is not None:
        return aggregation.node_type, (
            f"i dati sono aggregati per {aggregation.node_type} prima dell'analisi"
        )
    declared = next(
        (s.node_type for s in build.n_statements if s.node_type is not None),
        None,
    )
    if declared is not None:
        return declared, None
    return observational_unit, None


def _experimental_unit(
    index: GraphIndex, build: BuildResult, factor: Factor
) -> tuple[NodeType | None, str | None]:
    """Unita di allocation del fattore; nessun altro segnale la sovrascrive."""
    if factor.allocation_level is None:
        return None, None

    level = factor.allocation_level
    notes: list[str] = []

    if factor.application_level is not None:
        if factor.application_level is level:
            notes.append("allocation e applicazione fisica sono dichiarate allo stesso livello")
        else:
            notes.append(
                f"l'applicazione fisica avviene a {factor.application_level}, distinta "
                f"dall'allocation a {level}"
            )

    if factor.kind == "time":
        repeated = _process(build.processes, "repeated_measure")
        if repeated is not None and repeated.node_type is not None:
            notes.append(
                "il tempo e una misura ripetuta sulla stessa unita e non cambia l'allocation"
            )

    pooling = _process(build.processes, "pooling")
    if pooling is not None and index.has(NodeType.POOL):
        notes.append("il pooling puo cambiare l'unita analitica ma non l'unita di allocation")
    return level, "; ".join(notes) or None


def _clusters(
    index: GraphIndex,
    build: BuildResult,
    experimental_unit: NodeType | None,
) -> tuple[NodeType, ...]:
    """Livelli superiori che restano fonte di correlazione (blocchi o cluster)."""
    if experimental_unit is None:
        return ()
    return tuple(
        dict.fromkeys(
            [
                *index.ancestors(experimental_unit),
                *(
                    level
                    for model in build.models
                    for level in model.declared_clustering
                    if level is not experimental_unit
                ),
            ]
        )
    )


def _conditional_independence_scenarios(
    *,
    block_id: str,
    index: GraphIndex,
    factor: Factor,
    scope: NScope,
    experimental_unit: NodeType | None,
    n_candidate: int | None,
    group: str | None,
    clusters: tuple[NodeType, ...],
    source_independence: Confidence,
) -> tuple[tuple[ConditionalScenario, ...], Question | None]:
    """Espone alternative numeriche solo quando entrambe derivano dal grafo."""

    if experimental_unit is None or n_candidate is None:
        return (), None
    # Solo una conferma forte dell'indipendenza chiude il bivio. ``MEDIUM``
    # significa che il grafo contiene struttura utile ma non sufficiente e deve
    # quindi produrre uno scenario, quando entrambi i conteggi sono disponibili.
    if source_independence is Confidence.HIGH:
        return (), None
    node = index.node(experimental_unit)
    if _confirmed_source_independence(node):
        return (), None
    question_text = (
        f"Le unita di tipo {experimental_unit} allocate al fattore '{factor.name}' provengono "
        "da sorgenti biologiche indipendenti, oppure condividono la stessa sorgente?"
    )
    question = Question(
        id=stable_id("qst", block_id, "source-independence", scope.key()),
        text=question_text,
        reason="la relazione di indipendenza tra le sorgenti non e determinabile dal grafo",
        missing_field="source_independence",
        scope=scope,
        priority=100,
        decisive=True,
        impact="La risposta cambia n indipendente per questo gruppo e contrasto.",
    )

    alternative: tuple[NodeType, int] | None = None
    for cluster_type in clusters:
        cluster_count = index.derived_count_for_scope(
            cluster_type,
            factor_name=factor.name,
            group=group,
        )
        if cluster_count is not None and cluster_count != n_candidate:
            alternative = (cluster_type, cluster_count)
            break
    if alternative is None:
        # La domanda resta decisiva, ma non costruiamo un ramo numerico privo
        # di un valore osservato o derivabile.
        return (), question

    cluster_type, cluster_count = alternative
    key = group or "per_group"
    cluster_node = index.node(cluster_type)
    evidence_ids = tuple(
        dict.fromkeys(
            [
                *(node.evidence_ids if node is not None else ()),
                *(cluster_node.evidence_ids if cluster_node is not None else ()),
            ]
        )
    )
    return (
        ConditionalScenario(
            conditional_on=f"source_independence:{experimental_unit}",
            if_confirmed={key: n_candidate},
            if_rejected={key: cluster_count},
            question=question_text,
            rule_id="GEN-010",
            evidence_ids=evidence_ids,
        ),
    ), question


def _process(processes: tuple[ProcessFact, ...], kind: str) -> ProcessFact | None:
    return next((p for p in processes if p.kind == kind), None)


def _declared_n(
    statements: tuple[NStatement, ...],
    scope: NScope,
    analytical_unit: NodeType | None,
    *,
    allow_scope_fallback: bool,
) -> tuple[int | None, NStatement | None]:
    """n dichiarato pertinente allo scope, senza forzare corrispondenze."""
    candidates = [s for s in statements if s.value is not None]
    if not candidates:
        return None, None

    def compatible(statement: NStatement) -> bool:
        for field in ("factor_id", "contrast_id", "endpoint_id", "timepoint"):
            stated = getattr(statement.scope, field)
            requested = getattr(scope, field)
            if stated is not None and requested is not None and stated != requested:
                return False
        stated_group = statement.scope.group
        return not (
            stated_group not in (None, "per_group")
            and scope.group is not None
            and stated_group.casefold() != scope.group.casefold()
        )

    pool = [statement for statement in candidates if compatible(statement)]
    if not pool:
        return None, None

    if not allow_scope_fallback:
        strictly_scoped: list[NStatement] = []
        for statement in pool:
            exact_ids = all(
                requested is None or stated == requested
                for stated, requested in (
                    (statement.scope.factor_id, scope.factor_id),
                    (statement.scope.contrast_id, scope.contrast_id),
                    (statement.scope.endpoint_id, scope.endpoint_id),
                    (statement.scope.timepoint, scope.timepoint),
                )
            )
            group_is_exact = scope.group is None or statement.scope.group in {
                scope.group,
                "per_group",
            }
            if exact_ids and group_is_exact:
                strictly_scoped.append(statement)
        pool = strictly_scoped
        if not pool:
            return None, None

    # Se esistono valori esplicitamente legati alla dimensione richiesta, i
    # valori globali non competono con essi.
    for field in ("endpoint_id", "contrast_id", "factor_id", "timepoint"):
        requested = getattr(scope, field)
        exact = [statement for statement in pool if getattr(statement.scope, field) == requested]
        if requested is not None and exact:
            pool = exact
    if scope.group is not None:
        exact_group_statements = [
            statement
            for statement in pool
            if statement.scope.group is not None
            and (
                statement.scope.group == "per_group"
                or statement.scope.group.casefold() == scope.group.casefold()
            )
        ]
        if exact_group_statements:
            pool = exact_group_statements

    kind_priority = {
        NKind.ANALYZED: 0,
        NKind.INDEPENDENT: 1,
        NKind.DECLARED: 2,
        NKind.OBSERVATIONAL: 3,
        NKind.ALLOCATED: 4,
    }

    def score(statement: NStatement) -> tuple[int, int, int]:
        unit_penalty = 0 if statement.node_type is analytical_unit else 1
        specificity_penalty = -sum(value is not None for value in statement.scope.key())
        return (
            unit_penalty,
            kind_priority[statement.kind],
            specificity_penalty,
        )

    pool.sort(key=score)
    best_score = score(pool[0])
    best = [statement for statement in pool if score(statement) == best_score]
    if len({statement.value for statement in best}) > 1:
        return None, None
    chosen = best[0]
    return chosen.value, chosen


# ----------------------------------------------------------------- completezza


def _sufficiency(
    index: GraphIndex,
    build: BuildResult,
    factor: Factor,
    experimental_unit: NodeType | None,
) -> DataSufficiency:
    intervention = Confidence.UNKNOWN
    if factor.allocation_level is not None:
        if factor.allocation_confidence >= 0.9:
            intervention = Confidence.HIGH
        elif factor.allocation_confidence >= 0.7:
            intervention = Confidence.MEDIUM
        else:
            intervention = Confidence.LOW

    source_independence = Confidence.UNKNOWN
    if experimental_unit is not None:
        node = index.node(experimental_unit)
        pooling = _process(build.processes, "pooling")
        if experimental_unit is NodeType.POOL and pooling is not None:
            # I pool sono unita analitiche costruite: l'indipendenza dipende dai
            # membri, che restano non osservabili individualmente.
            source_independence = (
                Confidence.MEDIUM if index.count(NodeType.POOL) is not None else Confidence.LOW
            )
        elif _confirmed_source_independence(node):
            # La stringa dell'autore "independent experiments/replicates" e una
            # AUTHOR_ASSERTION, non una prova. Il flag diventa conclusivo solo
            # quando arriva da conferma umana/adjudication o da un campo
            # strutturato che codifica esplicitamente l'indipendenza (PRD 9.2).
            source_independence = Confidence.HIGH
        elif index.count(experimental_unit) is not None:
            parents = index.ancestors(experimental_unit)
            source_independence = Confidence.MEDIUM if parents else Confidence.LOW
        else:
            source_independence = Confidence.LOW

    exclusions = Confidence.UNKNOWN
    exclusion = _process(build.processes, "exclusion")
    if exclusion is not None:
        exclusions = Confidence.HIGH if exclusion.value is not None else Confidence.MEDIUM

    aggregation = Confidence.UNKNOWN
    if _process(build.processes, "aggregation") is not None:
        aggregation = Confidence.HIGH
    elif _process(build.processes, "pooling") is not None:
        aggregation = Confidence.MEDIUM

    statistical_model = Confidence.UNKNOWN
    model = _best_model(build.models)
    if model is not None:
        statistical_model = Confidence.HIGH if model.accounts_for else Confidence.MEDIUM

    return DataSufficiency(
        intervention_level=intervention,
        source_independence=source_independence,
        exclusions=exclusions,
        aggregation=aggregation,
        statistical_model=statistical_model,
    )


def _best_model(models: tuple[StatisticalModelFact, ...]) -> StatisticalModelFact | None:
    mixed = next((m for m in models if m.kind == "mixed"), None)
    return mixed or (models[0] if models else None)


def _inferability(
    factor: Factor,
    experimental_unit: NodeType | None,
    n_independent: int | None,
    sufficiency: DataSufficiency,
    conditional_scenarios: tuple[ConditionalScenario, ...],
) -> Inferability:
    if experimental_unit is None or n_independent is None:
        return Inferability.NOT_INFERABLE
    if conditional_scenarios:
        return Inferability.CONDITIONAL
    if sufficiency.source_independence is not Confidence.HIGH:
        return Inferability.REQUIRES_CONFIRMATION
    if factor.allocation_confidence < 0.8:
        return Inferability.REQUIRES_CONFIRMATION
    if sufficiency.intervention_level is Confidence.MEDIUM:
        return Inferability.CONDITIONAL
    return Inferability.INFERABLE


def _rationale(
    *,
    factor: Factor,
    experimental_unit: NodeType | None,
    observational_unit: NodeType | None,
    analytical_unit: NodeType | None,
    n_independent: int | None,
    n_observational: int | None,
    clusters: tuple[NodeType, ...],
    extra_notes: list[str],
) -> str:
    if experimental_unit is None:
        base = (
            f"Il livello di allocation del fattore '{factor.name}' non e identificabile "
            "dal materiale: l'unita sperimentale resta indeterminata."
        )
    else:
        base = (
            f"Il fattore '{factor.name}' risulta assegnato a livello di {experimental_unit}; "
            f"la misura e effettuata su {observational_unit or 'entita non identificata'}"
        )
        if analytical_unit is not None and analytical_unit is not observational_unit:
            base += f" e l'analisi usa {analytical_unit}"
        base += "."
        if n_independent is not None:
            base += f" Unita indipendenti per questo contrasto: {n_independent}."
        if n_observational is not None:
            base += f" Osservazioni: {n_observational}."
        if clusters:
            names = ", ".join(str(c) for c in clusters)
            base += f" Livelli superiori che restano fonte di correlazione: {names}."
    for note in extra_notes:
        base += f" {note[0].upper()}{note[1:]}."
    return base
