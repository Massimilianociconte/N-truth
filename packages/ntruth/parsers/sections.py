"""Classificazione deterministica delle sezioni (PRD FR-008).

Il ruolo della sezione decide che cosa viene estratto. La classificazione e
basata su pattern espliciti: quando nessun pattern corrisponde il ruolo resta
`other` con confidenza dichiarata, non viene indovinato.
"""

from __future__ import annotations

import re

from ntruth.schemas.document import SectionRole

#: Pattern ordinati: il primo che corrisponde vince. Italiano e inglese sono
#: entrambi supportati, ma il layer linguistico resta separato da quello
#: scientifico (PRD NFR-15).
_HEADING_PATTERNS: list[tuple[SectionRole, re.Pattern[str]]] = [
    (
        SectionRole.STATISTICS,
        re.compile(
            r"^(statistic(s|al)([\s\-]*(analysis|analyses|methods|procedures))?|"
            r"analisi\s+statistic\w+|metodi\s+statistici|quantification\s+and\s+statistical\s+analysis)\b",
            re.IGNORECASE,
        ),
    ),
    (
        SectionRole.FIGURE_LEGEND,
        re.compile(
            r"^(supplement(ary|al)\s+)?(fig(ure|\.)?)\s*\.?\s*[0-9ivxlc]+\b|"
            r"^(figure\s+legends?|legend[ae]?\s+(delle\s+)?figur\w+|didascali\w+)\b",
            re.IGNORECASE,
        ),
    ),
    (
        SectionRole.TABLE_CAPTION,
        re.compile(
            r"^(supplement(ary|al)\s+)?tab(le|ella)\s*\.?\s*[0-9ivxlc]+\b|^table\s+captions?\b",
            re.IGNORECASE,
        ),
    ),
    (
        SectionRole.EXCLUSION,
        re.compile(
            r"^(exclusion|inclusion\s+and\s+exclusion|excluded\s+\w+|"
            r"criteri\s+di\s+(esclusione|inclusione))\b",
            re.IGNORECASE,
        ),
    ),
    (
        SectionRole.SAMPLE_DESCRIPTION,
        re.compile(
            r"^(sample\s+(description|sheet|preparation|collection)|samples?|specimens?|"
            r"cell\s+(culture|lines?)|primary\s+(cultures?|cells?)|animals?(\s+and\s+housing)?|"
            r"subjects|participants|experimental\s+(design|model|animals)|"
            r"colture\s+cellulari|animali|campion\w+|disegno\s+sperimentale)\b",
            re.IGNORECASE,
        ),
    ),
    (
        SectionRole.METHODS,
        re.compile(
            r"^((materials?|material)\s+and\s+methods?|methods?|"
            r"experimental\s+(procedures?|section)|star\s*\*?\s*methods|protocol[so]?|"
            r"metodi|materiali\s+e\s+metodi|procedure\s+sperimentali)\b",
            re.IGNORECASE,
        ),
    ),
    (SectionRole.ABSTRACT, re.compile(r"^(abstract|summary|riassunto|sommario)\b", re.IGNORECASE)),
    (
        SectionRole.INTRODUCTION,
        re.compile(r"^(introduction|background|introduzione)\b", re.IGNORECASE),
    ),
    (SectionRole.RESULTS, re.compile(r"^(results?|risultati)\b", re.IGNORECASE)),
    (
        SectionRole.DISCUSSION,
        re.compile(r"^(discussion|conclusions?|discussione|conclusioni)\b", re.IGNORECASE),
    ),
    (
        SectionRole.REFERENCES,
        re.compile(r"^(references|bibliography|bibliografia|literature\s+cited)\b", re.IGNORECASE),
    ),
    (
        SectionRole.SUPPLEMENT,
        re.compile(
            r"^(supplement(ary|al)?(\s+(methods?|information|material))?|"
            r"materiale\s+supplementare|appendi(x|ce))\b",
            re.IGNORECASE,
        ),
    ),
]

#: Sottosezioni di Methods che restano Methods anche se il titolo e specifico.
_METHODS_HINTS = re.compile(
    r"(immunofluorescen|microscop|imaging|transfection|treatment|drug|western|"
    r"quantification|image\s+analysis|acquisition|staining|colorazione|trattament)",
    re.IGNORECASE,
)

_EXPERIMENT_HEADING = re.compile(
    r"^(?:experiment(?:\s+block)?|study|esperimento|studio)\s*"
    r"(?:#|n[.o°]*\s*)?(?:[a-z]|[ivxlcdm]+|[a-z0-9_.-]*\d[a-z0-9_.-]*)\s*$",
    re.IGNORECASE,
)

_MAX_HEADING_CHARS = 120


def classify_heading(title: str) -> tuple[SectionRole, float, str]:
    """Ruolo, confidenza e origine della decisione."""
    text = title.strip().strip("#").strip()
    if not text:
        return SectionRole.OTHER, 0.0, "empty_heading"
    for role, pattern in _HEADING_PATTERNS:
        if pattern.search(text):
            return role, 0.95, "heading_match"
    if _METHODS_HINTS.search(text):
        return SectionRole.METHODS, 0.6, "methods_hint"
    return SectionRole.OTHER, 0.3, "no_match"


def looks_like_heading(line: str) -> bool:
    """Euristica per testo piatto: riga corta, senza punto finale, che apre una sezione."""
    text = line.strip()
    if not text or len(text) > _MAX_HEADING_CHARS:
        return False
    if text.startswith("#"):
        return True
    if text.endswith((".", ";", ",")) and not re.match(r"^(fig|tab)", text, re.IGNORECASE):
        return False
    role, confidence, _ = classify_heading(text)
    if role is not SectionRole.OTHER and confidence >= 0.6:
        return True
    if _EXPERIMENT_HEADING.match(text):
        return True
    # Titoli numerati tipo "2.1 Cell culture"
    return bool(re.match(r"^\d+(\.\d+)*\s+\S", text)) and len(text.split()) <= 12


def heading_level(line: str) -> int:
    text = line.strip()
    if text.startswith("#"):
        return min(len(text) - len(text.lstrip("#")), 6)
    numbered = re.match(r"^(\d+(?:\.\d+)*)\s+", text)
    if numbered:
        return numbered.group(1).count(".") + 1
    return 1
