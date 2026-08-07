"""Semantic verifier runtime indipendente dagli invarianti hard (ADR-0005/0006).

Che cos'e
---------
L'hard verifier controlla **invarianti strutturali e di policy** (grafo illegale,
count lifecycle, matrice di output, indipendenza mal formata). Non giudica se un
claim e **supportato dalle evidenze** o se due fatti scientificamente coesistenti
nel grafo si contraddicono a livello di contenuto.

Il semantic verifier copre quel secondo strato: supportabilita, contraddizioni,
coerenza numerica/temporale e limite di AUTHOR_ASSERTION. Non e un secondo
"truth engine" e **non puo**:

- rendere valido un blocco hard-invalid;
- chiudere un missing fact assente;
- sostituire la conferma umana sui campi decisivi;
- certificare un paper.

Backend
-------
- ``algorithmic_v1`` (default, shippato): regole deterministiche auditabili,
  indipendenti dal modello generatore per costruzione (nessun peso ML).
- ``model_provisional`` (opzionale): pass di un LLM con prompt VERIFY-only.
  Stesso backbone del parser **non** costituisce lineage indipendente
  scientificamente validato (ADR-0006): resta PROVISIONAL e non abilita release.

Attivazione
-----------
Chiamare ``verify_semantic(block)``. Integrare il risultato in
``build_validation_stack_report(..., semantic_invoked=True, ...)`` e, se
desiderato, in ``VerifierResult`` del parser stage.
"""

from __future__ import annotations

import itertools
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, model_validator

from ntruth.schemas.core import (
    Determinability,
    EvidenceSpan,
    EvidenceType,
    FrozenModel,
    ProvenanceKind,
)
from ntruth.schemas.experiment import (
    CountKind,
    CountQuantifier,
    ExperimentBlock,
    Factor,
    TriState,
)
from ntruth.schemas.graph import RelationType


class SemanticBackend(StrEnum):
    ALGORITHMIC_V1 = "algorithmic_v1"
    MODEL_PROVISIONAL = "model_provisional"


class SemanticStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"


class SemanticCheckSeverity(StrEnum):
    BLOCKING = "blocking"
    ADVISORY = "advisory"


class SemanticCheck(FrozenModel):
    check_id: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=1, max_length=120)
    severity: SemanticCheckSeverity
    message: str = Field(min_length=1, max_length=4000)
    related_ids: tuple[str, ...] = ()
    passed: bool

    @model_validator(mode="after")
    def _unique_related(self) -> Self:
        if len(self.related_ids) != len(set(self.related_ids)):
            raise ValueError("related_ids duplicati nel check semantico")
        return self


class SemanticVerificationResult(FrozenModel):
    """Esito auditabile del semantic verifier; non e un verdict scientifico finale."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    status: SemanticStatus
    block_id: str
    backend: SemanticBackend
    checks: tuple[SemanticCheck, ...] = ()
    blocking_failure_codes: tuple[str, ...] = ()
    scientifically_validated_backend: bool = False
    can_override_hard_invalid: Literal[False] = False

    @property
    def invoked(self) -> bool:
        return True

    @property
    def passed(self) -> bool:
        return self.status is SemanticStatus.PASS

    @model_validator(mode="after")
    def _status_matches_checks(self) -> Self:
        blocking_failed = [
            item.code
            for item in self.checks
            if item.severity is SemanticCheckSeverity.BLOCKING and not item.passed
        ]
        if tuple(blocking_failed) != self.blocking_failure_codes:
            raise ValueError("blocking_failure_codes incoerente con i check")
        if blocking_failed and self.status is SemanticStatus.PASS:
            raise ValueError("status=pass con failure blocking")
        if self.can_override_hard_invalid:
            raise ValueError("il semantic verifier non puo override hard-invalid")
        if (
            self.backend is SemanticBackend.MODEL_PROVISIONAL
            and self.scientifically_validated_backend
        ):
            raise ValueError(
                "model_provisional non puo dichiararsi scientifically_validated_backend"
            )
        return self


_STRUCTURAL_OR_BETTER = frozenset(
    {
        EvidenceType.STRUCTURAL_FACT,
        EvidenceType.PROCEDURAL_EVENT,
        EvidenceType.SAMPLE_METADATA,
        EvidenceType.STATISTICAL_CODE,
        EvidenceType.IMAGE_METADATA,
        EvidenceType.USER_CONFIRMATION,
        EvidenceType.DERIVED_FACT,
    }
)


def _evidence_by_id(block: ExperimentBlock) -> dict[str, EvidenceSpan]:
    return {item.id: item for item in block.evidence}


def _check(
    *,
    check_id: str,
    code: str,
    message: str,
    passed: bool,
    severity: SemanticCheckSeverity = SemanticCheckSeverity.BLOCKING,
    related_ids: Sequence[str] = (),
) -> SemanticCheck:
    return SemanticCheck(
        check_id=check_id,
        code=code,
        severity=severity,
        message=message,
        related_ids=tuple(related_ids),
        passed=passed,
    )


def _decisive_factor_support(
    factor: Factor,
    evidence: Mapping[str, EvidenceSpan],
) -> SemanticCheck:
    """Allocation/indipendenza decisive non possono reggersi su sola AUTHOR_ASSERTION."""

    if factor.independently_assigned is not TriState.TRUE:
        return _check(
            check_id=f"factor-support-{factor.id}",
            code="decisive_support_not_applicable",
            message=f"factor {factor.id}: independently_assigned non TRUE",
            passed=True,
            severity=SemanticCheckSeverity.ADVISORY,
            related_ids=(factor.id,),
        )

    if factor.provenance.origin in {ProvenanceKind.USER, ProvenanceKind.ADJUDICATION}:
        return _check(
            check_id=f"factor-support-{factor.id}",
            code="decisive_support_human_confirmed",
            message=f"factor {factor.id}: conferma umana/adjudication registrata",
            passed=True,
            related_ids=(factor.id,),
        )

    ids = tuple(factor.independence_evidence_ids or ())
    if not ids:
        return _check(
            check_id=f"factor-support-{factor.id}",
            code="decisive_independence_without_evidence",
            message=(
                f"factor {factor.id}: independently_assigned=TRUE senza independence_evidence_ids"
            ),
            passed=False,
            related_ids=(factor.id,),
        )

    missing = [eid for eid in ids if eid not in evidence]
    if missing:
        return _check(
            check_id=f"factor-support-{factor.id}",
            code="decisive_evidence_id_missing",
            message=f"factor {factor.id}: evidence assenti dal blocco: {missing}",
            passed=False,
            related_ids=(factor.id, *missing),
        )

    types = {evidence[eid].evidence_type for eid in ids if evidence[eid].evidence_type is not None}
    if types and types <= {EvidenceType.AUTHOR_ASSERTION, EvidenceType.MODEL_INFERENCE}:
        return _check(
            check_id=f"factor-support-{factor.id}",
            code="author_assertion_alone_insufficient",
            message=(
                f"factor {factor.id}: le sole AUTHOR_ASSERTION/MODEL_INFERENCE non supportano "
                "l'indipendenza decisiva"
            ),
            passed=False,
            related_ids=(factor.id, *ids),
        )
    if types & _STRUCTURAL_OR_BETTER or EvidenceType.USER_CONFIRMATION in types:
        return _check(
            check_id=f"factor-support-{factor.id}",
            code="decisive_support_ok",
            message=f"factor {factor.id}: supporto non-assertivo presente",
            passed=True,
            related_ids=(factor.id, *ids),
        )
    return _check(
        check_id=f"factor-support-{factor.id}",
        code="decisive_support_unknown_evidence_types",
        message=f"factor {factor.id}: tipi di evidenza insufficienti o non classificati",
        passed=False,
        related_ids=(factor.id, *ids),
    )


def _numeric_lifecycle_consistency(block: ExperimentBlock) -> list[SemanticCheck]:
    """Confronta count EXACT con ordine lifecycle quando presenti e same-scope."""

    exact: dict[CountKind, list[int]] = {}
    for count in block.count_records:
        if count.quantifier is not CountQuantifier.EXACT:
            continue
        if count.value is None:
            continue
        exact.setdefault(count.kind, []).append(int(count.value))

    order = (
        CountKind.PLANNED_N,
        CountKind.ALLOCATED_N,
        CountKind.TREATED_N,
        CountKind.OBSERVED_N,
        CountKind.ANALYSED_N,
    )
    checks: list[SemanticCheck] = []
    present = [
        (kind, values[0]) for kind, values in exact.items() if len(values) == 1 and kind in order
    ]
    present_map = dict(present)
    for left, right in itertools.pairwise(order):
        if left in present_map and right in present_map:
            ok = present_map[left] >= present_map[right]
            checks.append(
                _check(
                    check_id=f"numeric-{left.value}-{right.value}",
                    code="numeric_lifecycle_order",
                    message=(
                        f"{left.value}={present_map[left]} vs {right.value}={present_map[right]}: "
                        + ("ordine rispettato" if ok else "ordine violato")
                    ),
                    passed=ok,
                )
            )
    if not checks:
        checks.append(
            _check(
                check_id="numeric-lifecycle-absent",
                code="numeric_lifecycle_not_applicable",
                message="coppie EXACT lifecycle insufficienti per il confronto",
                passed=True,
                severity=SemanticCheckSeverity.ADVISORY,
            )
        )
    return checks


def _contradiction_records(block: ExperimentBlock) -> SemanticCheck:
    if block.contradictions:
        return _check(
            check_id="contradictions-present",
            code="contradictions_require_review",
            message=(
                f"{len(block.contradictions)} contraddizioni esplicite: revisione umana richiesta"
            ),
            passed=False,
            related_ids=tuple(item.id for item in block.contradictions[:32]),
        )
    return _check(
        check_id="contradictions-none",
        code="no_explicit_contradictions",
        message="nessun contradiction record nel blocco",
        passed=True,
        severity=SemanticCheckSeverity.ADVISORY,
    )


def _allocation_application_coherence(block: ExperimentBlock) -> list[SemanticCheck]:
    checks: list[SemanticCheck] = []
    for factor in block.factors:
        if factor.allocation_level is None or factor.application_level is None:
            checks.append(
                _check(
                    check_id=f"alloc-app-{factor.id}",
                    code="allocation_application_partial",
                    message=f"factor {factor.id}: allocation/application incompleti",
                    passed=True,
                    severity=SemanticCheckSeverity.ADVISORY,
                    related_ids=(factor.id,),
                )
            )
            continue
        # rank_of not needed: if application is coarser than allocation without mechanism, advisory
        if (
            factor.allocation_level != factor.application_level
            and factor.independently_assigned is TriState.TRUE
            and not factor.independence_mechanism
        ):
            checks.append(
                _check(
                    check_id=f"alloc-app-{factor.id}",
                    code="allocation_application_mechanism_gap",
                    message=(
                        f"factor {factor.id}: allocation≠application con indipendenza TRUE "
                        "senza mechanism testuale"
                    ),
                    passed=False,
                    related_ids=(factor.id,),
                )
            )
        else:
            checks.append(
                _check(
                    check_id=f"alloc-app-{factor.id}",
                    code="allocation_application_ok",
                    message=f"factor {factor.id}: coerenza allocation/application accettabile",
                    passed=True,
                    related_ids=(factor.id,),
                )
            )
    if not checks:
        checks.append(
            _check(
                check_id="alloc-app-none",
                code="allocation_application_not_applicable",
                message="nessun factor da valutare",
                passed=True,
                severity=SemanticCheckSeverity.ADVISORY,
            )
        )
    return checks


def _evidence_grounding(
    block: ExperimentBlock,
    source_texts: Mapping[str, str] | None,
) -> list[SemanticCheck]:
    """Se sono forniti testi sorgente, verifica che gli span citati esistano come substring."""

    if not source_texts:
        return [
            _check(
                check_id="grounding-skipped",
                code="source_grounding_not_run",
                message="nessun source_texts fornito: grounding testuale non eseguito",
                passed=True,
                severity=SemanticCheckSeverity.ADVISORY,
            )
        ]
    checks: list[SemanticCheck] = []
    for span in block.evidence:
        blob = source_texts.get(span.file_id)
        if blob is None:
            checks.append(
                _check(
                    check_id=f"grounding-missing-doc-{span.id}",
                    code="source_text_missing_for_span",
                    message=f"evidence {span.id}: testo sorgente non fornito per file/document",
                    passed=False,
                    severity=SemanticCheckSeverity.ADVISORY,
                    related_ids=(span.id,),
                )
            )
            continue
        excerpt = (span.text or "").strip()
        if not excerpt:
            checks.append(
                _check(
                    check_id=f"grounding-empty-{span.id}",
                    code="empty_evidence_text",
                    message=f"evidence {span.id}: testo vuoto",
                    passed=False,
                    related_ids=(span.id,),
                )
            )
            continue
        ok = excerpt in blob
        checks.append(
            _check(
                check_id=f"grounding-{span.id}",
                code="evidence_span_grounded" if ok else "evidence_span_not_in_source",
                message=(
                    f"evidence {span.id}: "
                    + ("trovata nel testo sorgente" if ok else "non trovata nel testo sorgente")
                ),
                passed=ok,
                related_ids=(span.id,),
            )
        )
    return checks


def _determinability_author_assertion_gate(block: ExperimentBlock) -> SemanticCheck:
    if block.determinability is not Determinability.DETERMINATE:
        return _check(
            check_id="det-author-gate",
            code="determinability_not_determinate",
            message=f"determinability={block.determinability.value}: gate AUTHOR non applicabile",
            passed=True,
            severity=SemanticCheckSeverity.ADVISORY,
        )
    types = {span.evidence_type for span in block.evidence if span.evidence_type is not None}
    if types and types <= {EvidenceType.AUTHOR_ASSERTION}:
        return _check(
            check_id="det-author-gate",
            code="author_assertion_alone_cannot_close_determinability",
            message="DETERMINATE con sole AUTHOR_ASSERTION: semantic fail",
            passed=False,
        )
    return _check(
        check_id="det-author-gate",
        code="determinability_support_ok",
        message="DETERMINATE non regge su sole AUTHOR_ASSERTION",
        passed=True,
    )


def _relation_referential_hints(block: ExperimentBlock) -> list[SemanticCheck]:
    """Controlli semantici leggeri su relazioni ALLOCATE/MEASURE senza ridondare hard."""

    node_ids = {node.id for node in block.hierarchy.nodes} if block.hierarchy else set()
    checks: list[SemanticCheck] = []
    for relation in block.hierarchy.relations if block.hierarchy else ():
        if relation.type not in {
            RelationType.ALLOCATED_TO,
            RelationType.APPLIED_TO,
            RelationType.MEASURED_ON,
            RelationType.DERIVED_FROM,
        }:
            continue
        ok = relation.source in node_ids and relation.target in node_ids
        checks.append(
            _check(
                check_id=f"rel-{relation.id}",
                code="relation_endpoints_present" if ok else "relation_endpoints_missing",
                message=(
                    f"relation {relation.id} ({relation.type.value}): "
                    + ("endpoint presenti" if ok else "endpoint assenti dal hierarchy")
                ),
                passed=ok,
                related_ids=(relation.id, relation.source, relation.target),
            )
        )
    if not checks:
        checks.append(
            _check(
                check_id="rel-none",
                code="relations_not_applicable",
                message="nessuna relazione core da valutare semanticamente",
                passed=True,
                severity=SemanticCheckSeverity.ADVISORY,
            )
        )
    return checks


def verify_semantic(
    block: ExperimentBlock,
    *,
    source_texts: Mapping[str, str] | None = None,
    backend: SemanticBackend = SemanticBackend.ALGORITHMIC_V1,
) -> SemanticVerificationResult:
    """Esegue il semantic verifier sul blocco.

    ``backend=model_provisional`` richiede un adapter registrato e resta non validato
    scientificamente; se assente, fallisce fail-closed.
    """

    if backend is SemanticBackend.MODEL_PROVISIONAL:
        return _verify_semantic_model_provisional(block, source_texts=source_texts)

    evidence = _evidence_by_id(block)
    checks: list[SemanticCheck] = []
    for factor in block.factors:
        checks.append(_decisive_factor_support(factor, evidence))
    checks.extend(_allocation_application_coherence(block))
    checks.extend(_numeric_lifecycle_consistency(block))
    checks.append(_contradiction_records(block))
    checks.append(_determinability_author_assertion_gate(block))
    checks.extend(_relation_referential_hints(block))
    checks.extend(_evidence_grounding(block, source_texts))

    blocking_failures = tuple(
        item.code
        for item in checks
        if item.severity is SemanticCheckSeverity.BLOCKING and not item.passed
    )
    if blocking_failures:
        status = SemanticStatus.FAIL
    elif any(not item.passed for item in checks):
        status = SemanticStatus.PARTIAL
    else:
        status = SemanticStatus.PASS

    return SemanticVerificationResult(
        status=status,
        block_id=block.id,
        backend=SemanticBackend.ALGORITHMIC_V1,
        checks=tuple(checks),
        blocking_failure_codes=blocking_failures,
        scientifically_validated_backend=True,  # algorithmic rules are specified & testable
        can_override_hard_invalid=False,
    )


def _verify_semantic_model_provisional(
    block: ExperimentBlock,
    *,
    source_texts: Mapping[str, str] | None,
) -> SemanticVerificationResult:
    """Placeholder esplicito: nessun secondo modello validato e shippato.

    Ritorna FAIL fail-closed con codice che spiega i prerequisiti, cosi il runtime
    non finge un pass semantico basato su un backend assente.
    """

    del source_texts  # reserved for future model path
    check = _check(
        check_id="model-backend-absent",
        code="model_semantic_backend_not_configured",
        message=(
            "Backend model_provisional non configurato. Per un secondo modello serve: "
            "(1) lineage indipendente dal generator (pesi/prompt/training diversi), "
            "(2) schema VERIFY-only senza generazione di fatti, "
            "(3) benchmark su decisive fields e contradiction challenge, "
            "(4) budget runtime dedicato. Fino ad allora usare algorithmic_v1."
        ),
        passed=False,
    )
    return SemanticVerificationResult(
        status=SemanticStatus.FAIL,
        block_id=block.id,
        backend=SemanticBackend.MODEL_PROVISIONAL,
        checks=(check,),
        blocking_failure_codes=(check.code,),
        scientifically_validated_backend=False,
        can_override_hard_invalid=False,
    )


def semantic_to_stage_checks(
    result: SemanticVerificationResult,
) -> tuple[dict[str, object], ...]:
    """Proiezione leggera verso i check del parser stage (dict serializzabile)."""

    return tuple(
        {
            "check_id": item.check_id,
            "kind": "semantic",
            "status": "pass" if item.passed else "fail",
            "code": item.code,
            "message": item.message,
            "related_ids": list(item.related_ids),
        }
        for item in result.checks
    )


__all__ = [
    "SemanticBackend",
    "SemanticCheck",
    "SemanticCheckSeverity",
    "SemanticStatus",
    "SemanticVerificationResult",
    "semantic_to_stage_checks",
    "verify_semantic",
]
