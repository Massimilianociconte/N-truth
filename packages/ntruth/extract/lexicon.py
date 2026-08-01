"""Lessico delle entita sperimentali (baseline rules/regex, PRD 13.2).

Il lessico e volutamente esplicito e revisionabile: e la baseline obbligatoria
e il fallback quando i modelli non sono disponibili (PRD 11.4). Termini
intrinsecamente ambigui non vengono risolti qui: producono una domanda.
"""

from __future__ import annotations

import re

from ntruth.schemas.graph import NodeType

#: Termine normalizzato (singolare, minuscolo) -> tipo di nodo.
ENTITY_TERMS: dict[str, NodeType] = {
    # sorgenti biologiche
    "donor": NodeType.HUMAN_DONOR,
    "donatore": NodeType.HUMAN_DONOR,
    "subject": NodeType.HUMAN_DONOR,
    "soggetto": NodeType.HUMAN_DONOR,
    "patient": NodeType.HUMAN_DONOR,
    "paziente": NodeType.HUMAN_DONOR,
    "individual": NodeType.HUMAN_DONOR,
    "individuo": NodeType.HUMAN_DONOR,
    "animal": NodeType.ANIMAL,
    "animale": NodeType.ANIMAL,
    "mouse": NodeType.ANIMAL,
    "mice": NodeType.ANIMAL,
    "topo": NodeType.ANIMAL,
    "rat": NodeType.ANIMAL,
    "ratto": NodeType.ANIMAL,
    "pup": NodeType.ANIMAL,
    "cucciolo": NodeType.ANIMAL,
    "dam": NodeType.DAM,
    "mother": NodeType.DAM,
    "madre": NodeType.DAM,
    "litter": NodeType.LITTER,
    "cucciolata": NodeType.LITTER,
    "cage": NodeType.CAGE,
    "gabbia": NodeType.CAGE,
    "cohort": NodeType.COHORT,
    "coorte": NodeType.COHORT,
    # tessuti e materiali
    "tissue": NodeType.TISSUE,
    "tessuto": NodeType.TISSUE,
    "biopsy": NodeType.PRIMARY_SAMPLE,
    "biopsia": NodeType.PRIMARY_SAMPLE,
    "specimen": NodeType.PRIMARY_SAMPLE,
    "campione": NodeType.PRIMARY_SAMPLE,
    "cell line": NodeType.CELL_LINE,
    "linea cellulare": NodeType.CELL_LINE,
    "culture": NodeType.CELL_CULTURE,
    "coltura": NodeType.CELL_CULTURE,
    "preparation": NodeType.CELL_CULTURE,
    "preparazione": NodeType.CELL_CULTURE,
    "dissection": NodeType.CELL_CULTURE,
    "isolation": NodeType.CELL_CULTURE,
    "isolamento": NodeType.CELL_CULTURE,
    "thaw": NodeType.CELL_CULTURE,
    "passage": NodeType.CELL_CULTURE,
    "passaggio": NodeType.CELL_CULTURE,
    "organoid": NodeType.ORGANOID,
    "organoide": NodeType.ORGANOID,
    "explant": NodeType.EXPLANT,
    "espianto": NodeType.EXPLANT,
    # livelli tecnici
    "aliquot": NodeType.ALIQUOT,
    "aliquota": NodeType.ALIQUOT,
    "pool": NodeType.POOL,
    "plate": NodeType.PLATE,
    "piastra": NodeType.PLATE,
    "dish": NodeType.PLATE,
    "coverslip": NodeType.PLATE,
    "vetrino": NodeType.SECTION_SLICE,
    "well": NodeType.WELL,
    "pozzetto": NodeType.WELL,
    "section": NodeType.SECTION_SLICE,
    "sezione": NodeType.SECTION_SLICE,
    "slice": NodeType.SECTION_SLICE,
    "slide": NodeType.SECTION_SLICE,
    "field": NodeType.FIELD,
    "campo": NodeType.FIELD,
    "field of view": NodeType.FIELD,
    "image": NodeType.FIELD,
    "immagine": NodeType.FIELD,
    "frame": NodeType.FIELD,
    "roi": NodeType.ROI,
    "region of interest": NodeType.ROI,
    "regione": NodeType.ROI,
    "cell": NodeType.CELL,
    "cellula": NodeType.CELL,
    "nucleus": NodeType.CELL,
    "nucleo": NodeType.CELL,
    "neuron": NodeType.CELL,
    "neurone": NodeType.CELL,
    "soma": NodeType.CELL,
    "library": NodeType.LIBRARY,
    "libreria": NodeType.LIBRARY,
    "run": NodeType.RUN,
    "lane": NodeType.RUN,
    "batch": NodeType.BATCH,
    "lotto": NodeType.BATCH,
    "session": NodeType.RUN,
    "sessione": NodeType.RUN,
}

#: Plurali irregolari e forme che la normalizzazione non riduce da sola.
IRREGULAR_PLURALS: dict[str, str] = {
    "mice": "mouse",
    "nuclei": "nucleus",
    "analyses": "analysis",
    "colture": "coltura",
    "cellule": "cellula",
    "sezioni": "sezione",
    "regioni": "regione",
    "immagini": "immagine",
    "preparazioni": "preparazione",
    "animali": "animale",
    "individui": "individuo",
    "topi": "topo",
    "ratti": "ratto",
    "cuccioli": "cucciolo",
    "madri": "madre",
    "gabbie": "gabbia",
    "cucciolate": "cucciolata",
    "pozzetti": "pozzetto",
    "piastre": "piastra",
    "campi": "campo",
    "campioni": "campione",
    "tessuti": "tessuto",
    "donatori": "donatore",
    "soggetti": "soggetto",
    "pazienti": "paziente",
    "aliquote": "aliquota",
    "passaggi": "passaggio",
    "vetrini": "vetrino",
    "neuroni": "neurone",
    "organoidi": "organoide",
    "espianti": "espianto",
    "sessioni": "sessione",
    "lotti": "lotto",
}

#: Termini multi-parola riconosciuti prima della singolarizzazione.
MULTIWORD_TERMS: dict[str, NodeType] = {
    "cell line": NodeType.CELL_LINE,
    "cell lines": NodeType.CELL_LINE,
    "linea cellulare": NodeType.CELL_LINE,
    "linee cellulari": NodeType.CELL_LINE,
    "field of view": NodeType.FIELD,
    "fields of view": NodeType.FIELD,
    "campo visivo": NodeType.FIELD,
    "region of interest": NodeType.ROI,
    "regions of interest": NodeType.ROI,
    "primary culture": NodeType.CELL_CULTURE,
    "primary cultures": NodeType.CELL_CULTURE,
    "colture primarie": NodeType.CELL_CULTURE,
    "coltura primaria": NodeType.CELL_CULTURE,
    "independent culture": NodeType.CELL_CULTURE,
    "independent cultures": NodeType.CELL_CULTURE,
    "colture indipendenti": NodeType.CELL_CULTURE,
}

#: Termini che non identificano un livello: richiedono definizione operativa
#: (PRD GEN-003, 2.3 "replica e usato in modo incoerente").
AMBIGUOUS_TERMS: frozenset[str] = frozenset(
    {
        "replicate",
        "replicates",
        "replica",
        "repliche",
        "experiment",
        "experiments",
        "esperimento",
        "esperimenti",
        "independent experiment",
        "independent experiments",
        "esperimenti indipendenti",
        "sample",
        "samples",
        "campioni",
        "observation",
        "observations",
        "osservazioni",
        "measurement",
        "measurements",
        "misure",
        "datapoint",
        "data point",
        "data points",
    }
)

#: Qualificatori che marcano una replica dichiarata come biologica o tecnica.
BIOLOGICAL_REPLICATE_HINTS = re.compile(
    r"\b(biological (replicate|repeat)s?|independent (experiment|culture|preparation|"
    r"biological replicate)s?|repliche biologiche|colture indipendenti|"
    r"esperimenti indipendenti)\b",
    re.IGNORECASE,
)
TECHNICAL_REPLICATE_HINTS = re.compile(
    r"\b(technical (replicate|repeat)s?|repliche tecniche|duplicate|triplicate|"
    r"in duplicato|in triplicato)\b",
    re.IGNORECASE,
)

#: Verbi di assegnazione dell'intervento (PRD GEN-001).
ASSIGNMENT_VERBS = re.compile(
    r"\b(treated|treatment was applied|administered|exposed|randomi[sz]ed|assigned|"
    r"allocated|infected|transfected|transduced|stimulated|injected|received|"
    r"trattat\w+|somministrat\w+|espost\w+|randomizzat\w+|assegnat\w+|"
    r"infettat\w+|trasfettat\w+|stimolat\w+|iniettat\w+)\b",
    re.IGNORECASE,
)

# L'allocazione indipendente e l'applicazione materiale sono segnali diversi
# nel PRD v3. Il pattern storico sopra resta il rilevatore ampio di una frase
# che descrive un fattore; questi due pattern decidono invece quale campo
# candidato puo essere compilato.
ALLOCATION_VERBS = re.compile(
    r"\b(randomi[sz]ed|assigned|allocated|randomizzat\w+|assegnat\w+|allocat\w+)\b",
    re.IGNORECASE,
)
APPLICATION_VERBS = re.compile(
    r"\b(treated|treatment was applied|applied|administered|exposed|infected|"
    r"transfected|transduced|stimulated|injected|received|trattat\w+|"
    r"somministrat\w+|applicat\w+|espost\w+|infettat\w+|trasfettat\w+|"
    r"stimolat\w+|iniettat\w+|ricevut\w+)\b",
    re.IGNORECASE,
)

#: Marcatori espliciti del livello di assegnazione.
ASSIGNMENT_LEVEL_MARKERS = re.compile(
    r"\b(?:at the level of|at the|per|for each|each|by|a livello di|per ciascun\w*|"
    r"per ogni|su ciascun\w*)\s+(?P<term>[a-z][a-z\s]{2,24}?)\b",
    re.IGNORECASE,
)

#: Modelli statistici e termini di clustering (PRD GEN-009, GEN-002).
MIXED_MODEL_HINTS = re.compile(
    r"\b(mixed[- ]effects? model|linear mixed model|lmm|glmm|hierarchical model|"
    r"multilevel model|random (effect|intercept|slope)s?|nested anova|"
    r"modello (misto|gerarchico)|effetti casuali)\b",
    re.IGNORECASE,
)
SIMPLE_TEST_HINTS = re.compile(
    r"\b(unpaired|paired|two[- ]tailed|student'?s)?\s*t[- ]test\b|"
    r"\b(one|two)[- ]way anova\b|\bmann[- ]whitney\b|\bwilcoxon\b|\bkruskal[- ]wallis\b|"
    r"\bchi[- ]square[d]?\b|\bfisher'?s exact\b|\btest t\b|\banalisi della varianza\b",
    re.IGNORECASE,
)
POOLING_HINTS = re.compile(
    r"\b(pooled|pooling|combined into|merged into|aggregated (across|by|per)|"
    r"pseudobulk|riuniti|aggregat\w+ (per|su))\b",
    re.IGNORECASE,
)
EXCLUSION_HINTS = re.compile(
    r"\b(excluded|exclusion|removed from analysis|discarded|dropped out|attrition|"
    r"esclus\w+|rimoss\w+ dall'analisi|scartat\w+)\b",
    re.IGNORECASE,
)
BLINDING_HINTS = re.compile(r"\b(blinded|blinding|masked|in cieco|alla cieca)\b", re.IGNORECASE)

_WS = re.compile(r"\s+")


def normalize_term(term: str) -> str:
    """Minuscolo, spazi normalizzati e singolare approssimato."""
    text = _WS.sub(" ", term.strip().lower()).strip(" .,:;()[]")
    if not text:
        return ""
    if text in MULTIWORD_TERMS or text in ENTITY_TERMS:
        return text
    if text in IRREGULAR_PLURALS:
        return IRREGULAR_PLURALS[text]
    if text.endswith("ies") and len(text) > 4:
        candidate = text[:-3] + "y"
        if candidate in ENTITY_TERMS:
            return candidate
    for suffix in ("es", "s", "i", "e"):
        if text.endswith(suffix) and len(text) > len(suffix) + 2:
            candidate = text[: -len(suffix)]
            if candidate in ENTITY_TERMS:
                return candidate
    return text


def lookup_entity(term: str) -> NodeType | None:
    """Tipo di nodo per un termine, None se sconosciuto o ambiguo."""
    raw = _WS.sub(" ", term.strip().lower()).strip(" .,:;()[]")
    if raw in MULTIWORD_TERMS:
        return MULTIWORD_TERMS[raw]
    if raw in AMBIGUOUS_TERMS:
        return None
    normalized = normalize_term(raw)
    if normalized in AMBIGUOUS_TERMS:
        return None
    return ENTITY_TERMS.get(normalized)


def is_ambiguous(term: str) -> bool:
    raw = _WS.sub(" ", term.strip().lower()).strip(" .,:;()[]")
    return raw in AMBIGUOUS_TERMS or normalize_term(raw) in AMBIGUOUS_TERMS


#: Regex alternativa con tutti i termini noti, per la ricerca nel testo.
def entity_pattern() -> re.Pattern[str]:
    terms = sorted(
        {*ENTITY_TERMS, *MULTIWORD_TERMS, *IRREGULAR_PLURALS, *AMBIGUOUS_TERMS},
        key=len,
        reverse=True,
    )
    # Le forme plurali regolari vengono coperte da un suffisso opzionale.
    alternatives = "|".join(re.escape(t) for t in terms if t)
    return re.compile(rf"\b(?P<term>{alternatives})(?P<plural>s|es|i|e)?\b", re.IGNORECASE)


ENTITY_PATTERN = entity_pattern()
