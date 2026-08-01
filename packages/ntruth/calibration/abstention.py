"""Astensione e completezza informativa (PRD 8.7, NFR-05, FR-022).

"Non determinabile" e un output di prima classe. In questa versione la decisione
e deterministica e basata sulla completezza del materiale; la calibrazione
appresa (temperature scaling, conformal prediction, OOD) arrivera con il layer
ML e potra solo aggiungere astensioni, non rimuoverle (PRD 13.5).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ntruth.graph.builder import BuildResult
from ntruth.schemas.core import Confidence, Severity
from ntruth.schemas.document import DocumentIR, ParserStatus
from ntruth.schemas.experiment import DataSufficiency, Inferability, UnitAssessment

#: Condizioni obbligatorie di astensione (PRD 8.7).
ABSTENTION_CODES: dict[str, str] = {
    "intervention_level_unknown": "livello dell'intervento non identificabile",
    "source_independence_unknown": "indipendenza di colture o preparazioni non stabilibile",
    "replicate_unlinked": "termine di replica non collegato a un nodo del grafo",
    "unresolved_contradiction": "contraddizione non risolta tra fonti",
    "model_without_cluster": "modello statistico che non specifica cluster o effetti casuali",
    "endpoint_unlinked": "endpoint non collegabile a unita definite",
    "document_incomplete": "documento incompleto o testo estratto insufficiente",
}


@dataclass
class AbstentionDecision:
    """Esito della valutazione di completezza per un blocco."""

    abstained: bool = False
    reasons: list[str] = field(default_factory=list)
    codes: list[str] = field(default_factory=list)
    sufficiency: DataSufficiency = field(default_factory=DataSufficiency)

    def describe(self) -> str:
        if not self.abstained:
            return "Materiale sufficiente per formulare inferenze sull'unita sperimentale."
        return "Astensione: " + "; ".join(self.reasons) + "."


def evaluate_abstention(
    ir: DocumentIR, build: BuildResult, assessments: tuple[UnitAssessment, ...]
) -> AbstentionDecision:
    """Decide se il blocco puo sostenere una conclusione sull'unita."""
    codes: list[str] = []

    if any(a.experimental_unit is None for a in assessments) or not assessments:
        codes.append("intervention_level_unknown")

    if any(a.data_sufficiency.source_independence is not Confidence.HIGH for a in assessments):
        codes.append("source_independence_unknown")

    if any(s.node_type is None and s.value is not None for s in build.n_statements):
        codes.append("replicate_unlinked")

    if any(c.status == "unresolved" for c in build.contradictions):
        codes.append("unresolved_contradiction")

    mixed = [m for m in build.models if m.kind == "mixed"]
    if mixed and not any(m.accounts_for for m in mixed):
        codes.append("model_without_cluster")

    if build.endpoints and all(e.measured_on is None for e in build.endpoints):
        codes.append("endpoint_unlinked")

    if _document_incomplete(ir):
        codes.append("document_incomplete")

    codes = list(dict.fromkeys(codes))
    return AbstentionDecision(
        abstained=bool(codes),
        reasons=[ABSTENTION_CODES[c] for c in codes],
        codes=codes,
        sufficiency=aggregate_sufficiency(assessments),
    )


def _document_incomplete(ir: DocumentIR) -> bool:
    if not ir.files:
        return True
    if any(f.status in (ParserStatus.FAILED, ParserStatus.DEGRADED) for f in ir.files):
        return True
    return not ir.design_text() and not ir.tables


def aggregate_sufficiency(assessments: tuple[UnitAssessment, ...]) -> DataSufficiency:
    """Completezza del blocco = la piu bassa tra quelle dei suoi scope.

    Nessuna media: un aggregato non deve nascondere una lacuna (PRD FR-014).
    """
    if not assessments:
        return DataSufficiency()
    order = [Confidence.UNKNOWN, Confidence.LOW, Confidence.MEDIUM, Confidence.HIGH]

    def lowest(field_name: str) -> Confidence:
        values = [getattr(a.data_sufficiency, field_name) for a in assessments]
        return min(values, key=order.index)

    return DataSufficiency(
        intervention_level=lowest("intervention_level"),
        source_independence=lowest("source_independence"),
        exclusions=lowest("exclusions"),
        aggregation=lowest("aggregation"),
        statistical_model=lowest("statistical_model"),
    )


def enforce_evidence_floor(
    assessments: tuple[UnitAssessment, ...], ir: DocumentIR, alerts_severity: Severity | None = None
) -> tuple[UnitAssessment, ...]:
    """Su fonti degradate nessun alert critical puo poggiare su span incerti.

    Se tutti i file sono in stato degraded l'inferenza sull'unita viene
    declassata a `requires_confirmation` (PRD 11.4).
    """
    if not ir.files or not all(f.status is ParserStatus.DEGRADED for f in ir.files):
        return assessments
    downgraded: list[UnitAssessment] = []
    for assessment in assessments:
        if assessment.inferability is Inferability.INFERABLE:
            downgraded.append(
                assessment.model_copy(
                    update={
                        "inferability": Inferability.REQUIRES_CONFIRMATION,
                        "rationale": (
                            assessment.rationale
                            + " Estrazione testuale degradata: l'inferenza richiede conferma."
                        ),
                    }
                )
            )
        else:
            downgraded.append(assessment)
    return tuple(downgraded)
