"""Estrazione: NER baseline, n statements, coreference e relazioni (PRD 11.1).

In questa versione l'estrattore e interamente deterministico (regole e regex).
Quando il layer ML verra aggiunto produrra candidate facts nello stesso formato,
senza poter sovrascrivere ne le regole ne il grafo confermato (PRD 0.3).
"""

from ntruth.extract.coreference import resolve_coreferences
from ntruth.extract.facts import (
    EndpointFact,
    EntityFact,
    EntityInstanceFact,
    ExtractionResult,
    FactorFact,
    InstanceAssignmentFact,
    InstanceRelationFact,
    NFact,
    ProcessFact,
    RelationFact,
    StatisticalModelFact,
    make_evidence,
)
from ntruth.extract.lexicon import ENTITY_TERMS, is_ambiguous, lookup_entity, normalize_term
from ntruth.extract.numbers import NumberMention, find_count_phrases, find_n_mentions, parse_number
from ntruth.extract.table_extract import extract_from_tables
from ntruth.extract.text_extract import extract_from_document, resolve_phrase
from ntruth.schemas.document import DocumentIR


def extract(ir: DocumentIR) -> ExtractionResult:
    """Estrazione completa: testo e tabelle, unite in un unico insieme di fatti.

    Le due fonti restano distinguibili tramite la provenance di ogni fatto
    (`explicit` per il testo, `tabular` per il sample sheet).
    """
    result = extract_from_document(ir)
    result.merge(extract_from_tables(ir))
    coreference = resolve_coreferences(ir)
    result.mentions.extend(coreference.mentions)
    result.coreference_links.extend(coreference.links)
    result.evidence.extend(coreference.evidence)
    result.dedupe_evidence()
    result.endpoints = _dedupe_endpoints(result.endpoints)
    return result


def _dedupe_endpoints(endpoints: list[EndpointFact]) -> list[EndpointFact]:
    """Un endpoint citato piu volte resta un endpoint solo.

    Oltre ai duplicati esatti vengono uniti i nomi in cui uno e la coda
    dell'altro ("CTCF per cell" dentro "TH CTCF per cell"): la coreference
    completa e un compito del layer ML, qui si evita solo di moltiplicare
    lo stesso endpoint (PRD 13.1).
    """
    seen: dict[tuple[str, object], EndpointFact] = {}
    for endpoint in endpoints:
        key = (endpoint.name.strip().lower(), endpoint.measured_on)
        seen.setdefault(key, endpoint)

    kept: list[EndpointFact] = []
    ordered = sorted(seen.values(), key=lambda e: -len(e.name))
    for endpoint in ordered:
        name = endpoint.name.strip().lower()
        if any(
            other.measured_on == endpoint.measured_on
            and name != other.name.strip().lower()
            and other.name.strip().lower().endswith(name)
            for other in kept
        ):
            continue
        kept.append(endpoint)
    return kept


__all__ = [
    "ENTITY_TERMS",
    "EndpointFact",
    "EntityFact",
    "EntityInstanceFact",
    "ExtractionResult",
    "FactorFact",
    "InstanceAssignmentFact",
    "InstanceRelationFact",
    "NFact",
    "NumberMention",
    "ProcessFact",
    "RelationFact",
    "StatisticalModelFact",
    "extract",
    "extract_from_document",
    "extract_from_tables",
    "find_count_phrases",
    "find_n_mentions",
    "is_ambiguous",
    "lookup_entity",
    "make_evidence",
    "normalize_term",
    "parse_number",
    "resolve_phrase",
]
