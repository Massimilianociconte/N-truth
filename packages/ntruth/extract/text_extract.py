"""Estrazione baseline da testo (PRD 13.2: baseline obbligatoria e fallback).

Precisione prima del richiamo: un falso allarme costa piu di una domanda
(PRD 25, rischio R4). Cio che non viene riconosciuto diventa informazione
mancante e produce una domanda, non un'inferenza inventata.
"""

from __future__ import annotations

import re
from typing import Protocol

from ntruth.extract.facts import (
    EndpointFact,
    EntityFact,
    ExtractionResult,
    FactorFact,
    NFact,
    ProcessFact,
    RelationFact,
    StatisticalModelFact,
    make_evidence,
)
from ntruth.extract.lexicon import (
    ALLOCATION_VERBS,
    APPLICATION_VERBS,
    ASSIGNMENT_VERBS,
    BIOLOGICAL_REPLICATE_HINTS,
    BLINDING_HINTS,
    EXCLUSION_HINTS,
    MIXED_MODEL_HINTS,
    POOLING_HINTS,
    SIMPLE_TEST_HINTS,
    TECHNICAL_REPLICATE_HINTS,
    is_ambiguous,
    lookup_entity,
)
from ntruth.extract.numbers import find_count_phrases, find_n_mentions, parse_number
from ntruth.schemas.core import EvidenceSpan
from ntruth.schemas.document import DocumentIR, Section, SectionRole
from ntruth.schemas.experiment import NKind
from ntruth.schemas.graph import BIOLOGICAL_SOURCE_TYPES, NodeType, RelationType, rank_of


class EvidenceFactory(Protocol):
    """Callable che localizza una porzione del paragrafo corrente."""

    def __call__(self, start: int, end: int, snippet: str | None = None) -> EvidenceSpan | None: ...


_ENT = r"[a-zA-Z][a-zA-Z \-]{1,28}?"

#: Modificatori che possono precedere il sostantivo ("three independent cultures").
#: Vanno consumati fuori dalla cattura, altrimenti il gruppo si ferma sul
#: modificatore e il termine non viene risolto.
_MODS = (
    r"(?:(?:independent|separate|distinct|different|biological|technical|primary|"
    r"indipendenti|distinte|separate|diverse|biologiche|tecniche|primarie|primaria)\s+)*"
)
_NUM = (
    r"\d{1,7}(?:[.,]\d{3})*|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"uno|una|due|tre|quattro|cinque|sei|sette|otto|nove|dieci"
)

_MODIFIERS = {
    "independent",
    "separate",
    "distinct",
    "different",
    "biological",
    "technical",
    "primary",
    "the",
    "each",
    "all",
    "single",
    "individual",
    "same",
    "our",
    "these",
    "indipendenti",
    "indipendente",
    "distinte",
    "diverse",
    "biologiche",
    "tecniche",
    "primarie",
    "primaria",
    "stesso",
    "stessa",
    "ogni",
    "ciascun",
    "ciascuna",
    "tutte",
    "tutti",
    "le",
    "i",
    "gli",
    "la",
    "il",
}

SENTENCE_SPLIT = re.compile(r"[^.!?;]+[.!?;]?")

PER_RELATION = re.compile(
    rf"(?:(?P<num>{_NUM})\s+)?{_MODS}(?P<child>{_ENT})\s+"
    rf"(?:(?:were|was|are|is)\s+)?"
    rf"(?:acquired|imaged|analy[sz]ed|analysed|measured|counted|collected|taken|"
    rf"seeded|plated|sampled|acquisit\w+|analizzat\w+|misurat\w+|contat\w+)?\s*"
    rf"(?:per|for each|in each|from each|within each|da ciascun\w*|per ciascun\w*|per ogni)\s+"
    rf"{_MODS}(?P<parent>{_ENT})\b",
    re.IGNORECASE,
)

PLATED_RELATION = re.compile(
    rf"{_MODS}(?P<child>{_ENT})\s+(?:were|was|are|is)\s+"
    rf"(?:then\s+)?(?:plated|seeded|distributed|split|divided|aliquoted|transferred|"
    rf"piastrat\w+|seminate?|distribuit\w+|suddivis\w+)\s+"
    rf"(?:in|into|onto|across|over|among|in|su|tra)\s+"
    rf"(?:(?P<num>{_NUM})\s+)?{_MODS}(?P<parent>{_ENT})\b",
    re.IGNORECASE,
)

DERIVED_RELATION = re.compile(
    rf"(?:(?P<childnum>{_NUM})\s+)?{_MODS}(?P<child>{_ENT})\s+"
    rf"(?:were|was|are|is)?\s*"
    rf"(?:derived|obtained|isolated|prepared|generated|dissociated|harvested|"
    rf"ottenut\w+|isolat\w+|preparat\w+|derivat\w+)\s+from\s+"
    rf"(?:(?P<num>{_NUM})\s+)?{_MODS}(?P<parent>{_ENT})\b",
    re.IGNORECASE,
)

FROM_RELATION = re.compile(
    rf"(?P<childnum>{_NUM})\s+{_MODS}(?P<child>{_ENT})\s+from\s+"
    rf"(?P<num>{_NUM})\s+{_MODS}(?P<parent>{_ENT})\b",
    re.IGNORECASE,
)

SAME_SOURCE_RELATION = re.compile(
    rf"{_MODS}(?P<child>{_ENT})\s+(?:from|in|within|of)\s+the\s+same\s+{_MODS}(?P<parent>{_ENT})\b",
    re.IGNORECASE,
)

POOL_RELATION = re.compile(
    rf"(?:(?P<childnum>{_NUM})\s+)?{_MODS}(?P<child>{_ENT})\s+(?:were|was)?\s*"
    rf"(?:pooled|combined|merged|riunit\w+|combinat\w+)\s+"
    rf"(?:in|into|to form|to generate|per formare)\s+"
    rf"(?:(?P<num>{_NUM})\s+)?{_MODS}(?P<parent>{_ENT})\b",
    re.IGNORECASE,
)

REPEATED_MEASURE = re.compile(
    rf"(?:the\s+same\s+(?P<entity>{_ENT})\s+(?:was|were)\s+"
    rf"(?:measured|imaged|assessed|recorded|sampled|followed)\s+"
    rf"(?:at|over|across)\s+(?:(?P<num>{_NUM})\s+)?(?:time ?points?|times|days|weeks|tempi))"
    rf"|(?:(?P<num2>{_NUM})\s+(?:time ?points?|tempi)\s+(?:per|for each)\s+(?P<entity2>{_ENT}))",
    re.IGNORECASE,
)

ASSIGNMENT_EXPLICIT = re.compile(
    rf"(?:at the level of|applied at the|a livello di|al livello di)\s+(?:the\s+)?(?P<level>{_ENT})\b",
    re.IGNORECASE,
)

ASSIGNMENT_PER = re.compile(
    rf"(?:per|to each|for each|on each|su ciascun\w*|per ciascun\w*|per ogni)\s+(?P<level>{_ENT})\b",
    re.IGNORECASE,
)

ALLOCATION_SUBJECT = re.compile(
    rf"\b(?P<level>{_ENT})\s+(?:were|was|are|is)\s+(?:then\s+)?(?:randomly\s+)?"
    rf"(?:assigned|allocated|randomi[sz]ed|assegnat\w+|allocat\w+|randomizzat\w+)\b",
    re.IGNORECASE,
)

APPLICATION_SUBJECT = re.compile(
    rf"\b(?P<level>{_ENT})\s+(?:were|was|are|is)\s+(?:then\s+)?(?:randomly\s+)?"
    rf"(?:treated|exposed|infected|transfected|transduced|stimulated|injected|"
    rf"trattat\w+|espost\w+|infettat\w+|trasfettat\w+|stimolat\w+|iniettat\w+)\b",
    re.IGNORECASE,
)

TREATMENT_LEVELS = re.compile(
    r"\b(?:treated|stimulated|exposed|incubated|trattat\w+|stimolat\w+|espost\w+)\s+"
    r"(?:with|to|con|a)\s+(?P<a>[A-Za-z0-9][\wÀ-ſ\-/\.]{0,24})"
    r"(?:\s*(?:\(|,)?\s*(?:or|vs\.?|versus|o|oppure|and|e)\s+(?P<b>[A-Za-z0-9][\wÀ-ſ\-/\.]{0,24}))?",
    re.IGNORECASE,
)

CONTROL_TERMS = re.compile(
    r"\b(vehicle|control|untreated|sham|mock|dmso|saline|veicolo|controllo|non trattat\w+)\b",
    re.IGNORECASE,
)

GENOTYPE_TERMS = re.compile(
    r"\b(knock[- ]?out|knockout|ko|wild[- ]?type|wt|transgenic|tg|null|"
    r"heterozygous|homozygous|het|genotype|genotipo|mutant|mutante)\b",
    re.IGNORECASE,
)

DIET_TERMS = re.compile(r"\b(diet|dieta|chow|feeding|alimentazione)\b", re.IGNORECASE)

#: Nome di endpoint: da una a tre parole, senza verbi o congiunzioni.
_ENDPOINT_NAME = r"[A-Za-zÀ-ſ][\wÀ-ſ+/\-]{0,20}(?:\s+[A-Za-zÀ-ſ][\wÀ-ſ+/\-]{0,20}){0,2}"

#: Parole che non possono comparire in un nome di endpoint.
_ENDPOINT_STOPWORDS = {
    "were",
    "was",
    "are",
    "is",
    "and",
    "or",
    "in",
    "from",
    "with",
    "of",
    "the",
    "each",
    "per",
    "all",
    "as",
    "than",
    "that",
    "using",
    "acquired",
    "measured",
    "counted",
    "quantified",
    "assessed",
    "calculated",
    "computed",
    "scored",
    "shown",
    "expressed",
    "normalized",
    "plated",
    "seeded",
    "treated",
    "e",
    "di",
    "con",
    "da",
    "sono",
    "erano",
    "ogni",
    "tutte",
    "tutti",
    "come",
    "quantificata",
    "quantificate",
    "misurata",
    "misurate",
    "valutata",
}

ENDPOINT_PER_UNIT = re.compile(
    rf"(?P<name>{_ENDPOINT_NAME})\s+per\s+(?P<unit>{_ENT})\b",
    re.IGNORECASE,
)

ENDPOINT_QUANTIFIED = re.compile(
    rf"(?P<name>{_ENDPOINT_NAME})\s+(?:was|were)\s+"
    r"(?:quantified|measured|assessed|computed|calculated|scored|"
    r"quantificat\w+|misurat\w+|valutat\w+)"
    r"(?:\s+as\s+(?P<alias>[^.,;]{1,50}))?",
    re.IGNORECASE,
)


def _valid_endpoint_name(name: str) -> bool:
    tokens = [t for t in re.split(r"\s+", name.strip().lower()) if t]
    if not tokens or len(tokens) > 3:
        return False
    if any(t in _ENDPOINT_STOPWORDS for t in tokens):
        return False
    return not re.fullmatch(r"[\d.,]+", name.strip())


AGGREGATION_HINT = re.compile(
    r"\b(averaged|mean(?:ed)? (?:per|across|over)|median (?:per|across)|"
    r"summari[sz]ed (?:per|by)|collapsed (?:to|per)|aggregated (?:per|by|across)|"
    rf"mediat\w+ (?:per|su)|aggregat\w+ (?:per|su))\s+(?:each\s+)?(?P<unit>{_ENT})?",
    re.IGNORECASE,
)

N_GROUP_SCOPE = re.compile(
    r"\b(?:in|for|within|nel|nella|per)\s+(?:the\s+|il\s+|la\s+)?"
    r"(?P<group>[A-Za-zÀ-ſ0-9][\wÀ-ſ+./-]{0,31})\s+"
    r"(?:group|condition|arm|gruppo|condizione|braccio)\b",
    re.IGNORECASE,
)

N_ENDPOINT_SCOPE = re.compile(
    r"\b(?:for|at|on|per)\s+(?:the\s+|l['’])?"
    r"(?P<endpoint>[A-Za-zÀ-ſ][\wÀ-ſ+./-]*(?:\s+[A-Za-zÀ-ſ][\wÀ-ſ+./-]*){0,3})\s+"
    r"(?:endpoint|outcome|readout|esito)\b",
    re.IGNORECASE,
)

N_TIMEPOINT_SCOPE = re.compile(
    r"\b(?:at|after|a|dopo)\s+(?P<timepoint>\d+(?:[.,]\d+)?\s*"
    r"(?:h|hr|hrs|hours?|d|days?|weeks?|ore?|giorni?|settimane?))\b",
    re.IGNORECASE,
)


def _clean_phrase(phrase: str) -> str:
    tokens = [t for t in re.split(r"[\s\-]+", phrase.strip().lower()) if t]
    while tokens and tokens[0] in _MODIFIERS:
        tokens.pop(0)
    return " ".join(tokens).strip(" .,:;")


def resolve_phrase(phrase: str) -> NodeType | None:
    """Risolve una frase nominale al tipo di nodo, ignorando i modificatori."""
    cleaned = _clean_phrase(phrase)
    if not cleaned:
        return None
    node_type = lookup_entity(cleaned)
    if node_type is not None:
        return node_type
    tokens = cleaned.split()
    for size in (2, 1):
        if len(tokens) >= size:
            node_type = lookup_entity(" ".join(tokens[-size:]))
            if node_type is not None:
                return node_type
    return None


def resolve_head_noun(phrase: str) -> tuple[NodeType | None, str]:
    """Risolve il primo sostantivo utile della frase: 'cells per group' -> Cell.

    Restituisce anche il termine effettivamente riconosciuto, cosi che
    l'evidenza citi cio che e stato letto e non l'intera coda della frase.
    """
    cleaned = _clean_phrase(phrase)
    if not cleaned:
        return None, ""
    tokens = cleaned.split()
    for size in (3, 2, 1):
        if len(tokens) < size:
            continue
        candidate = " ".join(tokens[:size])
        node_type = lookup_entity(candidate)
        if node_type is not None:
            return node_type, candidate
    return resolve_phrase(phrase), cleaned


def extract_from_document(ir: DocumentIR) -> ExtractionResult:
    """Estrae candidate facts dalle sole sezioni rilevanti per il disegno."""
    result = ExtractionResult()
    for section, body in ir.design_text():
        _extract_section(ir, section, body, result)
    result.dedupe_evidence()
    return result


def _extract_section(ir: DocumentIR, section: Section, body: str, result: ExtractionResult) -> None:
    paragraphs = ir.paragraphs_of(section.id)
    for paragraph in paragraphs:
        text = paragraph.text
        base = paragraph.start

        # I riferimenti al paragrafo corrente sono legati come default: la closure
        # deve citare il paragrafo dell'iterazione in cui e stata creata.
        def evidence_for(
            start: int,
            end: int,
            snippet: str | None = None,
            *,
            _file_id: str = paragraph.file_id,
            _base: int = base,
            _text: str = text,
        ) -> EvidenceSpan | None:
            return result.register(
                make_evidence(
                    file_id=_file_id,
                    section_id=section.id,
                    section_title=section.title,
                    start=_base + start,
                    end=_base + end,
                    text=snippet if snippet is not None else _text[start:end],
                    parser_version=ir.parser_version,
                )
            )

        _extract_n(text, section, evidence_for, result)
        _extract_relations(text, evidence_for, result)
        _extract_factors(text, evidence_for, result)
        _extract_endpoints(text, section, evidence_for, result)
        _extract_process(text, evidence_for, result)


# ------------------------------------------------------------------ n statements


def _extract_n(
    text: str,
    section: Section,
    evidence_for: EvidenceFactory,
    result: ExtractionResult,
) -> None:
    for mention in find_n_mentions(text):
        local_start = mention.start
        local_end = mention.end
        raw_entity = mention.entity_text or _entity_after(text, local_end)
        node_type, entity_text = resolve_head_noun(raw_entity) if raw_entity else (None, "")
        entity_text = entity_text or raw_entity.strip()
        ambiguous = bool(entity_text) and node_type is None
        sentence = _sentence_around(text, mention.start)
        group_hint, endpoint_hint, timepoint_hint = _scope_hints(sentence)
        kind = _classify_kind(sentence, mention.qualifiers, entity_text)
        evidence = evidence_for(local_start, min(len(text), local_end + 30))
        result.n_facts.append(
            NFact(
                value=mention.value,
                entity_text=entity_text or "",
                node_type=node_type,
                kind=kind,
                raw_text=mention.raw_text,
                qualifiers=mention.qualifiers,
                evidence=evidence,
                confidence=0.95 if node_type else 0.6,
                ambiguous_entity=ambiguous or not entity_text,
                endpoint_hint=endpoint_hint
                or (section.title if section.role is SectionRole.FIGURE_LEGEND else None),
                group_hint=group_hint,
                timepoint_hint=timepoint_hint,
            )
        )

    for mention in find_count_phrases(text):
        node_type = resolve_phrase(mention.entity_text)
        if node_type is None:
            if is_ambiguous(mention.entity_text):
                evidence = evidence_for(mention.start, mention.end)
                result.n_facts.append(
                    NFact(
                        value=mention.value,
                        entity_text=mention.entity_text,
                        node_type=None,
                        kind=NKind.DECLARED,
                        raw_text=mention.raw_text,
                        qualifiers=mention.qualifiers,
                        evidence=evidence,
                        confidence=0.5,
                        ambiguous_entity=True,
                    )
                )
            continue
        evidence = evidence_for(mention.start, mention.end)

        # "Due animali sono stati esclusi" e un conteggio di esclusioni, non il
        # numero di animali dello studio (PRD ANI-005, ARRIVE 2.0).
        exclusion_sentence = _sentence_around(text, mention.start)
        exclusion_tail = text[mention.end : min(len(text), mention.end + 32)]
        if EXCLUSION_HINTS.search(exclusion_tail):
            group_hint, endpoint_hint, _ = _scope_hints(exclusion_sentence)
            result.processes.append(
                ProcessFact(
                    kind="exclusion",
                    detail=mention.raw_text,
                    node_type=node_type,
                    value=mention.value,
                    evidence=evidence,
                    endpoint_hint=endpoint_hint,
                    group_hint=group_hint,
                )
            )
            continue

        # "cinque campi per pozzetto" e una cardinalita gerarchica; "120 cellule per
        # gruppo" e un totale riferito a un gruppo sperimentale, non a un contenitore.
        per_parent = any(
            q.startswith("per_") and resolve_phrase(q.removeprefix("per_")) is not None
            for q in mention.qualifiers
        )
        sentence = _sentence_around(text, mention.start)
        group_hint, endpoint_hint, timepoint_hint = _scope_hints(sentence)
        attributes: dict[str, str | int | float | bool | None] = {"raw": mention.raw_text}
        if any(
            q in {"per_group", "per_condition", "per_treatment", "per_arm"}
            for q in mention.qualifiers
        ):
            attributes["scope_qualifier"] = "per_group"
        if group_hint:
            attributes["scope_group"] = group_hint
        if endpoint_hint:
            attributes["scope_endpoint"] = endpoint_hint
        if timepoint_hint:
            attributes["scope_timepoint"] = timepoint_hint
        result.entities.append(
            EntityFact(
                node_type=node_type,
                label=str(node_type),
                count=mention.value,
                per_parent=per_parent,
                evidence=evidence,
                confidence=0.9,
                attributes=attributes,
            )
        )


def _sentence_around(text: str, position: int) -> str:
    """Frase che contiene la posizione data, per valutare il contesto locale."""
    for match in SENTENCE_SPLIT.finditer(text):
        if match.start() <= position < match.end():
            return match.group(0)
    return text


def _entity_after(text: str, position: int) -> str:
    tail = text[position : position + 40]
    match = re.match(r"[\s,]*([a-zA-Z][a-zA-Z \-]{2,28})", tail)
    return match.group(1).strip() if match else ""


def _classify_kind(text: str, qualifiers: tuple[str, ...], entity_text: str) -> NKind:
    window = f"{entity_text} {' '.join(qualifiers)} {text}".lower()
    if re.search(r"\b(allocat(?:ed|i|o|e)|randomi[sz]ed|assegnat\w+)\b", window):
        return NKind.ALLOCATED
    if re.search(r"\b(analy[sz]ed|included|after exclusions?|analizzat\w+|inclus\w+)\b", window):
        return NKind.ANALYZED
    if re.search(r"\b(observations?|measurements?|records?|osservazioni|misure)\b", window):
        return NKind.OBSERVATIONAL
    if TECHNICAL_REPLICATE_HINTS.search(window):
        return NKind.DECLARED
    if BIOLOGICAL_REPLICATE_HINTS.search(entity_text or ""):
        return NKind.DECLARED
    return NKind.DECLARED


def _scope_hints(text: str) -> tuple[str | None, str | None, str | None]:
    """Estrae solo scope lessicalmente espliciti dalla frase della menzione."""

    group_match = N_GROUP_SCOPE.search(text)
    endpoint_match = N_ENDPOINT_SCOPE.search(text)
    timepoint_match = N_TIMEPOINT_SCOPE.search(text)
    group = group_match.group("group").strip(" .,;:") if group_match else None
    endpoint = endpoint_match.group("endpoint").strip(" .,;:") if endpoint_match else None
    timepoint = timepoint_match.group("timepoint").strip() if timepoint_match else None
    return group, endpoint, timepoint


# -------------------------------------------------------------------- relazioni


def _add_relation(
    result: ExtractionResult,
    *,
    rel_type: RelationType,
    child: NodeType,
    parent: NodeType,
    per_parent: int | None,
    evidence: EvidenceSpan | None,
    confidence: float,
    derivation: str,
) -> None:
    if child is parent:
        return
    child_rank, parent_rank = rank_of(child), rank_of(parent)
    if child_rank is not None and parent_rank is not None and child_rank <= parent_rank:
        # Il figlio deve stare sotto il genitore: relazioni invertite sono
        # segnalate come conflitto invece di essere corrette in silenzio.
        result.warnings.append(
            f"relazione ignorata perche invertita rispetto alla gerarchia: {child} -> {parent}"
        )
        return
    result.relations.append(
        RelationFact(
            type=rel_type,
            source_type=child,
            target_type=parent,
            per_parent_count=per_parent,
            evidence=evidence,
            confidence=confidence,
            derivation=derivation,
        )
    )


def _extract_relations(text: str, evidence_for: EvidenceFactory, result: ExtractionResult) -> None:
    for match in PER_RELATION.finditer(text):
        child = resolve_phrase(match.group("child"))
        parent = resolve_phrase(match.group("parent"))
        if child is None or parent is None:
            continue
        count = parse_number(match.group("num") or "")
        evidence = evidence_for(match.start(), match.end())
        _add_relation(
            result,
            rel_type=RelationType.NESTED_IN,
            child=child,
            parent=parent,
            per_parent=count,
            evidence=evidence,
            confidence=0.9,
            derivation="pattern 'X per Y'",
        )
        if count is not None:
            result.entities.append(
                EntityFact(
                    node_type=child,
                    label=str(child),
                    count=count,
                    per_parent=True,
                    evidence=evidence,
                    confidence=0.9,
                )
            )

    for match in PLATED_RELATION.finditer(text):
        source = resolve_phrase(match.group("child"))
        destination = resolve_phrase(match.group("parent"))
        if source is None or destination is None:
            continue
        count = parse_number(match.group("num") or "")
        evidence = evidence_for(match.start(), match.end())

        # "X e stato seminato in Y": se X e piu grossolano di Y (una preparazione
        # distribuita in pozzetti), il contenitore Y e cio che deriva da X.
        source_rank, destination_rank = rank_of(source), rank_of(destination)
        inverted = (
            source_rank is not None
            and destination_rank is not None
            and source_rank < destination_rank
        )
        child, parent = (destination, source) if inverted else (source, destination)
        _add_relation(
            result,
            rel_type=RelationType.NESTED_IN,
            child=child,
            parent=parent,
            per_parent=count if inverted else None,
            evidence=evidence,
            confidence=0.85,
            derivation="pattern 'X seminate in Y'",
        )
        if count is not None:
            result.entities.append(
                EntityFact(
                    node_type=destination,
                    label=str(destination),
                    count=count,
                    per_parent=inverted,
                    evidence=evidence,
                    confidence=0.85,
                )
            )

    for pattern, derivation, rel in (
        (DERIVED_RELATION, "pattern 'X derivate da Y'", RelationType.DERIVED_FROM),
        (FROM_RELATION, "pattern 'N X da M Y'", RelationType.DERIVED_FROM),
    ):
        for match in pattern.finditer(text):
            child = resolve_phrase(match.group("child"))
            parent = resolve_phrase(match.group("parent"))
            if child is None or parent is None:
                continue
            evidence = evidence_for(match.start(), match.end())
            _add_relation(
                result,
                rel_type=rel,
                child=child,
                parent=parent,
                per_parent=None,
                evidence=evidence,
                confidence=0.85,
                derivation=derivation,
            )
            parent_count = parse_number(match.group("num") or "")
            if parent_count is not None:
                independent = bool(
                    BIOLOGICAL_REPLICATE_HINTS.search(match.group(0))
                    or re.search(
                        r"\b(independent|separate|distinct|indipendenti)\b",
                        match.group(0),
                        re.IGNORECASE,
                    )
                )
                result.entities.append(
                    EntityFact(
                        node_type=parent,
                        label=str(parent),
                        count=parent_count,
                        evidence=evidence,
                        confidence=0.9,
                        attributes={"declared_independent": independent},
                    )
                )
            child_count = parse_number(match.groupdict().get("childnum") or "")
            if child_count is not None:
                result.entities.append(
                    EntityFact(
                        node_type=child,
                        label=str(child),
                        count=child_count,
                        evidence=evidence,
                        confidence=0.9,
                    )
                )

    for match in SAME_SOURCE_RELATION.finditer(text):
        child = resolve_phrase(match.group("child"))
        parent = resolve_phrase(match.group("parent"))
        if child is None or parent is None:
            continue
        evidence = evidence_for(match.start(), match.end())
        _add_relation(
            result,
            rel_type=RelationType.NESTED_IN,
            child=child,
            parent=parent,
            per_parent=None,
            evidence=evidence,
            confidence=0.9,
            derivation="pattern 'stessa sorgente'",
        )

    for match in POOL_RELATION.finditer(text):
        child = resolve_phrase(match.group("child"))
        parent_phrase = match.group("parent")
        parent = resolve_phrase(parent_phrase) or NodeType.POOL
        if child is None:
            continue
        evidence = evidence_for(match.start(), match.end())
        result.relations.append(
            RelationFact(
                type=RelationType.POOLED_INTO,
                source_type=child,
                target_type=parent,
                per_parent_count=parse_number(match.group("num") or ""),
                evidence=evidence,
                confidence=0.9,
                derivation="pattern 'pooled into'",
            )
        )
        pool_count = parse_number(match.group("num") or "")
        result.entities.append(
            EntityFact(
                node_type=parent,
                label=str(parent),
                count=pool_count,
                evidence=evidence,
                confidence=0.9,
            )
        )
        member_count = parse_number(match.group("childnum") or "")
        if member_count is not None:
            result.entities.append(
                EntityFact(
                    node_type=child,
                    label=str(child),
                    count=member_count,
                    evidence=evidence,
                    confidence=0.9,
                )
            )
        result.processes.append(
            ProcessFact(
                kind="pooling",
                detail=match.group(0).strip(),
                node_type=child,
                value=pool_count,
                evidence=evidence,
            )
        )

    for match in REPEATED_MEASURE.finditer(text):
        entity_phrase = match.group("entity") or match.group("entity2") or ""
        entity = resolve_phrase(entity_phrase)
        evidence = evidence_for(match.start(), match.end())
        count = parse_number(match.group("num") or match.group("num2") or "")
        result.processes.append(
            ProcessFact(
                kind="repeated_measure",
                detail=match.group(0).strip(),
                node_type=entity,
                value=count,
                evidence=evidence,
            )
        )
        if entity is not None:
            result.relations.append(
                RelationFact(
                    type=RelationType.REPEATED_MEASURE_OF,
                    source_type=entity,
                    target_type=entity,
                    per_parent_count=count,
                    evidence=evidence,
                    confidence=0.8,
                    derivation="pattern 'misure ripetute'",
                )
            )


# ----------------------------------------------------------------------- fattori


def _extract_factors(text: str, evidence_for: EvidenceFactory, result: ExtractionResult) -> None:
    for sentence_match in SENTENCE_SPLIT.finditer(text):
        sentence = sentence_match.group(0)
        if not sentence.strip():
            continue
        offset = sentence_match.start()
        has_verb = bool(ASSIGNMENT_VERBS.search(sentence))

        levels_match = TREATMENT_LEVELS.search(sentence)
        genotype = GENOTYPE_TERMS.search(sentence)
        diet = DIET_TERMS.search(sentence)

        if not (levels_match or (genotype and has_verb) or (diet and has_verb)):
            continue

        evidence = evidence_for(offset, offset + len(sentence))
        allocation, allocation_conf, allocation_evidence = _allocation_level(
            sentence, offset, evidence_for
        )
        application, application_conf, application_evidence = _application_level(
            sentence, offset, evidence_for
        )

        if levels_match:
            levels = [levels_match.group("a")]
            if levels_match.group("b"):
                levels.append(levels_match.group("b"))
            control = CONTROL_TERMS.search(sentence)
            if control and control.group(0) not in levels:
                levels.append(control.group(0))
            result.factors.append(
                FactorFact(
                    name="treatment",
                    levels=tuple(dict.fromkeys(x.strip(" .,;") for x in levels if x)),
                    kind="treatment",
                    allocation_level=allocation,
                    application_level=application,
                    allocation_confidence=allocation_conf,
                    application_confidence=application_conf,
                    allocation_evidence=allocation_evidence,
                    application_evidence=application_evidence,
                    evidence=evidence,
                    randomized=bool(re.search(r"randomi[sz]ed|randomizzat", sentence, re.I)),
                )
            )
        if genotype:
            result.factors.append(
                FactorFact(
                    name="genotype",
                    levels=tuple(
                        dict.fromkeys(m.group(0).lower() for m in GENOTYPE_TERMS.finditer(sentence))
                    ),
                    kind="genotype",
                    allocation_level=allocation,
                    application_level=application,
                    allocation_confidence=allocation_conf if allocation else 0.0,
                    application_confidence=application_conf if application else 0.0,
                    allocation_evidence=allocation_evidence,
                    application_evidence=application_evidence,
                    evidence=evidence,
                )
            )
        if diet:
            result.factors.append(
                FactorFact(
                    name="diet",
                    levels=(),
                    kind="diet",
                    allocation_level=allocation,
                    application_level=application,
                    allocation_confidence=allocation_conf,
                    application_confidence=application_conf,
                    allocation_evidence=allocation_evidence,
                    application_evidence=application_evidence,
                    evidence=evidence,
                )
            )


def _allocation_level(
    sentence: str, offset: int, evidence_for: EvidenceFactory
) -> tuple[NodeType | None, float, EvidenceSpan | None]:
    """Propone il livello allocato senza confonderlo con l'applicazione."""
    explicit = ASSIGNMENT_EXPLICIT.search(sentence)
    if explicit and not explicit.group(0).casefold().startswith("applied"):
        node_type = resolve_phrase(explicit.group("level"))
        if node_type is not None:
            evidence = evidence_for(offset + explicit.start(), offset + explicit.end())
            return node_type, 0.92, evidence

    subject = ALLOCATION_SUBJECT.search(sentence)
    if subject:
        node_type = resolve_phrase(subject.group("level"))
        if node_type is not None:
            evidence = evidence_for(offset + subject.start(), offset + subject.end())
            return node_type, 0.8, evidence

    if ALLOCATION_VERBS.search(sentence):
        for match in ASSIGNMENT_PER.finditer(sentence):
            node_type = resolve_phrase(match.group("level"))
            if node_type is not None:
                evidence = evidence_for(offset + match.start(), offset + match.end())
                return node_type, 0.75, evidence

    return None, 0.0, None


def _application_level(
    sentence: str, offset: int, evidence_for: EvidenceFactory
) -> tuple[NodeType | None, float, EvidenceSpan | None]:
    """Propone l'unita che riceve materialmente l'intervento."""

    subject = APPLICATION_SUBJECT.search(sentence)
    if subject:
        node_type = resolve_phrase(subject.group("level"))
        if node_type is not None:
            evidence = evidence_for(offset + subject.start(), offset + subject.end())
            return node_type, 0.88, evidence

    explicit = ASSIGNMENT_EXPLICIT.search(sentence)
    if explicit and APPLICATION_VERBS.search(sentence):
        node_type = resolve_phrase(explicit.group("level"))
        if node_type is not None:
            evidence = evidence_for(offset + explicit.start(), offset + explicit.end())
            return node_type, 0.82, evidence

    if APPLICATION_VERBS.search(sentence):
        for match in ASSIGNMENT_PER.finditer(sentence):
            node_type = resolve_phrase(match.group("level"))
            if node_type is not None:
                evidence = evidence_for(offset + match.start(), offset + match.end())
                return node_type, 0.75, evidence

    return None, 0.0, None


def _assignment_level(
    sentence: str, offset: int, evidence_for: EvidenceFactory
) -> tuple[NodeType | None, float, EvidenceSpan | None]:
    """Alias legacy del solo livello di allocazione."""

    return _allocation_level(sentence, offset, evidence_for)


# ---------------------------------------------------------------------- endpoint


def _extract_endpoints(
    text: str,
    section: Section,
    evidence_for: EvidenceFactory,
    result: ExtractionResult,
) -> None:
    for match in ENDPOINT_PER_UNIT.finditer(text):
        unit = resolve_phrase(match.group("unit"))
        name = match.group("name").strip(" .,;")
        if unit is None or len(name) < 2 or not _valid_endpoint_name(name):
            continue
        if resolve_phrase(name) is not None:
            # "cells per well" descrive la gerarchia, non un endpoint.
            continue
        evidence = evidence_for(match.start(), match.end())
        result.endpoints.append(
            EndpointFact(
                name=f"{name} per {_clean_phrase(match.group('unit'))}",
                measured_on=unit,
                evidence=evidence,
            )
        )

    for match in ENDPOINT_QUANTIFIED.finditer(text):
        name = match.group("name").strip(" .,;")
        if len(name) < 2 or not _valid_endpoint_name(name):
            continue
        alias = (match.group("alias") or "").strip()
        unit = resolve_phrase(alias.split(" per ")[-1]) if " per " in alias else None
        evidence = evidence_for(match.start(), match.end())
        result.endpoints.append(
            EndpointFact(name=alias or name, measured_on=unit, evidence=evidence)
        )

    for match in AGGREGATION_HINT.finditer(text):
        unit = resolve_phrase(match.group("unit") or "")
        evidence = evidence_for(match.start(), match.end())
        result.processes.append(
            ProcessFact(
                kind="aggregation",
                detail=match.group(0).strip(),
                node_type=unit,
                evidence=evidence,
            )
        )


# ----------------------------------------------------------------------- processo


def _extract_process(text: str, evidence_for: EvidenceFactory, result: ExtractionResult) -> None:
    mixed = MIXED_MODEL_HINTS.search(text)
    if mixed:
        evidence = evidence_for(mixed.start(), min(len(text), mixed.end() + 120))
        accounts = _model_accounts_for(text[mixed.start() : mixed.start() + 220])
        result.models.append(
            StatisticalModelFact(
                kind="mixed",
                accounts_for=accounts,
                raw_text=mixed.group(0),
                evidence=evidence,
            )
        )
    simple = SIMPLE_TEST_HINTS.search(text)
    if simple:
        evidence = evidence_for(simple.start(), simple.end())
        result.models.append(
            StatisticalModelFact(kind="simple", raw_text=simple.group(0), evidence=evidence)
        )

    for pattern, kind in (
        (POOLING_HINTS, "pooling"),
        (EXCLUSION_HINTS, "exclusion"),
        (BLINDING_HINTS, "blinding"),
    ):
        match = pattern.search(text)
        if match:
            evidence = evidence_for(match.start(), min(len(text), match.end() + 80))
            group_hint, endpoint_hint, _ = _scope_hints(text)
            result.processes.append(
                ProcessFact(
                    kind=kind,
                    detail=match.group(0),
                    evidence=evidence,
                    endpoint_hint=endpoint_hint,
                    group_hint=group_hint,
                )
            )


def _model_accounts_for(window: str) -> tuple[NodeType, ...]:
    """Livelli citati come random effect o cluster nel modello (GEN-009)."""
    found: list[NodeType] = []
    for match in re.finditer(
        r"\b(?:random (?:effects? |intercepts? )?(?:for|of|per|by)|"
        r"nested (?:within|in)|grouped by|clustered by|per|for)\s+([a-zA-Z][a-zA-Z \-]{2,24})",
        window,
        re.IGNORECASE,
    ):
        node_type = resolve_phrase(match.group(1))
        if node_type is not None and node_type not in found:
            found.append(node_type)
    for match in re.finditer(r"\(\s*1\s*\|\s*([A-Za-z_][\w\- ]{1,24})\s*\)", window):
        node_type = resolve_phrase(match.group(1).replace("_", " "))
        if node_type is not None and node_type not in found:
            found.append(node_type)
    return tuple(found)


def biological_sources(result: ExtractionResult) -> list[NodeType]:
    """Tipi di sorgente biologica osservati, dal piu alto al piu basso."""
    seen = {e.node_type for e in result.entities if e.node_type in BIOLOGICAL_SOURCE_TYPES}
    return sorted(seen, key=lambda t: rank_of(t) or 0)
