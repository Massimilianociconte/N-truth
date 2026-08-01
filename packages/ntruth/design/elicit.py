"""Elicitazione deterministica delle informazioni mancanti nel design IR."""

from __future__ import annotations

from ntruth.design.schema import DesignSpecification, ElicitationResult
from ntruth.schemas.core import stable_id
from ntruth.schemas.experiment import InferenceTargetStatus, NScope, Question


def elicit_design(specification: DesignSpecification) -> ElicitationResult:
    """Genera domande riproducibili senza completare campi con supposizioni."""

    generated: list[Question] = []
    blocking_ids: list[str] = []

    def add(
        *,
        code: str,
        text: str,
        reason: str,
        missing_field: str,
        scope: NScope | None = None,
        priority: int = 100,
        decisive: bool = True,
        impact: str = "",
        blocking: bool = True,
    ) -> None:
        question_id = stable_id(
            "qst",
            specification.specification_id,
            code,
            scope.key() if scope is not None else (),
        )
        generated.append(
            Question(
                id=question_id,
                text=text,
                reason=reason,
                missing_field=missing_field,
                scope=scope,
                priority=priority,
                decisive=decisive,
                impact=impact,
            )
        )
        if blocking:
            blocking_ids.append(question_id)

    if not specification.inference_targets:
        add(
            code="missing-inference-target",
            text="Qual e la domanda scientifica e quale popolazione deve sostenere il claim?",
            reason="nessun target inferenziale e stato dichiarato",
            missing_field="inference_targets",
            impact="Senza target non e definibile lo scope dell'inferenza.",
        )

    if not specification.estimands:
        add(
            code="missing-estimand",
            text=(
                "Quali endpoint, misura di effetto, popolazione o unita target, livello di "
                "generalizzazione e fattori definiscono l'estimand?"
            ),
            reason="nessun estimand minimo e stato dichiarato",
            missing_field="estimands",
            impact="Il compiler non puo produrre un handoff inferenziale completo.",
        )

    factors_by_id = {factor.id: factor for factor in specification.factors}
    for target in specification.inference_targets:
        scope = NScope(inference_target_id=target.id)
        prefix = f"inference_targets[{target.id}]"

        if target.status is InferenceTargetStatus.MISSING:
            add(
                code=f"target-missing:{target.id}",
                text="Qual e la domanda scientifica a cui deve rispondere questo disegno?",
                reason="il target inferenziale e marcato missing",
                missing_field=prefix,
                scope=scope,
            )
        elif target.status is InferenceTargetStatus.EXTRACTED:
            add(
                code=f"target-confirmation:{target.id}",
                text="Confermi che domanda, claim e popolazione estratti descrivono l'inferenza?",
                reason="un target estratto resta un candidate fact finche non e confermato",
                missing_field=f"{prefix}.status",
                scope=scope,
                impact="Il target estratto deve essere confermato prima dell'handoff.",
            )
        elif target.status is InferenceTargetStatus.CONFLICTED:
            add(
                code=f"target-conflict:{target.id}",
                text="Quale delle formulazioni in conflitto descrive il target inferenziale?",
                reason="le fonti non identificano un target univoco",
                missing_field=f"{prefix}.status",
                scope=scope,
                impact="Le alternative in conflitto impediscono un unico scope inferenziale.",
            )

        if not (target.question_text.strip() or target.claim_text.strip()):
            add(
                code=f"target-question:{target.id}",
                text="Qual e la domanda scientifica o il claim specifico?",
                reason="domanda e claim non sono dichiarati",
                missing_field=f"{prefix}.question_text",
                scope=scope,
            )
        if not target.population_of_inference.strip():
            add(
                code=f"target-population:{target.id}",
                text="Qual e la popolazione di inferenza del claim?",
                reason="la popolazione di inferenza non e dichiarata",
                missing_field=f"{prefix}.population_of_inference",
                scope=scope,
                impact="La popolazione target determina i limiti di generalizzazione.",
            )
        if target.target_biological_unit is None:
            add(
                code=f"target-unit:{target.id}",
                text="Quale entita biologica deve sostenere la generalizzazione del claim?",
                reason="l'unita biologica target non e dichiarata",
                missing_field=f"{prefix}.target_biological_unit",
                scope=scope,
                impact="L'unita target e necessaria per distinguere stima e generalizzazione.",
            )
        if not target.factor_ids:
            add(
                code=f"target-factors:{target.id}",
                text="Quali fattori manipolati o osservati appartengono a questa domanda?",
                reason="il target non e collegato ad alcun fattore",
                missing_field=f"{prefix}.factor_ids",
                scope=scope,
            )
        if not target.contrast_ids:
            add(
                code=f"target-contrasts:{target.id}",
                text="Quale confronto specifico deve sostenere il claim?",
                reason="il target non e collegato ad alcun contrasto",
                missing_field=f"{prefix}.contrast_ids",
                scope=scope,
            )
        if not target.endpoint_ids:
            add(
                code=f"target-endpoints:{target.id}",
                text="Quale endpoint risponde alla domanda scientifica?",
                reason="il target non e collegato ad alcun endpoint",
                missing_field=f"{prefix}.endpoint_ids",
                scope=scope,
            )

        for factor_id in target.factor_ids:
            factor = factors_by_id[factor_id]
            if factor.allocation_level is None:
                add(
                    code=f"factor-allocation:{target.id}:{factor_id}",
                    text=(f"Quale unita ha ricevuto indipendentemente il fattore '{factor.name}'?"),
                    reason="livello di allocation del fattore non dichiarato",
                    missing_field=f"factors[{factor_id}].allocation_level",
                    scope=NScope(factor_id=factor_id, inference_target_id=target.id),
                    impact="L'allocation determina l'unita sperimentale per il fattore.",
                )
            if factor.application_level is None:
                add(
                    code=f"factor-application:{target.id}:{factor_id}",
                    text=(
                        f"A quale livello e stata applicata fisicamente la procedura del "
                        f"fattore '{factor.name}'?"
                    ),
                    reason="livello di applicazione fisica non dichiarato",
                    missing_field=f"factors[{factor_id}].application_level",
                    scope=NScope(factor_id=factor_id, inference_target_id=target.id),
                    priority=70,
                    decisive=False,
                    impact=(
                        "Serve a verificare coerenza e provenance, ma non sostituisce l'allocation."
                    ),
                    blocking=False,
                )

        for endpoint_id in target.endpoint_ids:
            covered = any(
                estimand.endpoint_id == endpoint_id
                and set(target.factor_ids).issubset(estimand.factor_ids)
                for estimand in specification.estimands
            )
            if covered:
                continue
            add(
                code=f"target-estimand:{target.id}:{endpoint_id}",
                text=(
                    "Quali misura di effetto, popolazione o unita target e livello di "
                    f"generalizzazione definiscono l'estimand per l'endpoint {endpoint_id}?"
                ),
                reason="nessun estimand minimo copre endpoint e fattori del target",
                missing_field="estimands",
                scope=NScope(
                    endpoint_id=endpoint_id,
                    inference_target_id=target.id,
                ),
                priority=100,
                impact="Un endpoint senza estimand rende incompleto l'handoff inferenziale.",
            )

    questions_by_id = {question.id: question for question in specification.questions}
    for question in generated:
        questions_by_id.setdefault(question.id, question)

    unique_blocking = tuple(dict.fromkeys(blocking_ids))
    return ElicitationResult(
        specification_id=specification.specification_id,
        questions=tuple(questions_by_id.values()),
        blocking_question_ids=unique_blocking,
        complete=not unique_blocking,
    )
