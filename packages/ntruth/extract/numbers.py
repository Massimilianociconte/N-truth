"""Riconoscimento di numeri e menzioni di n (PRD FR-010, FR-013).

Ogni menzione conserva testo, posizione e qualificatori. Numeri espliciti,
dedotti e tabulari restano distinti: il tipo di provenance e sempre presente
(PRD FR-013).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

NUMBER_WORDS: dict[str, int] = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "uno": 1,
    "una": 1,
    "due": 2,
    "tre": 3,
    "quattro": 4,
    "cinque": 5,
    "sei": 6,
    "sette": 7,
    "otto": 8,
    "nove": 9,
    "dieci": 10,
    "undici": 11,
    "dodici": 12,
}

_NUMBER_WORD_ALT = "|".join(sorted(NUMBER_WORDS, key=len, reverse=True))

#: "n = 120", "N=3", "n = 5 mice", "at least n = 3"
N_EQUALS = re.compile(
    r"(?P<qualifier>\b(?:at least|almeno|minimo|up to|fino a)\s+)?"
    r"\bn\s*(?:=|:|\sof\s|\spari a\s)\s*"
    r"(?P<value>\d{1,7}(?:[.,]\d{3})*|" + _NUMBER_WORD_ALT + r")"
    r"(?P<tail>\s*(?:-|–)\s*\d{1,7})?"
    r"(?P<entity>\s+[a-z][a-z\s\-]{0,30})?",
    re.IGNORECASE,
)

#: "three independent donors", "1,200 cells", "4 wells"
COUNT_PHRASE = re.compile(
    r"\b(?P<value>\d{1,7}(?:[.,]\d{3})*|" + _NUMBER_WORD_ALT + r")\s+"
    r"(?P<modifiers>(?:(?:independent|separate|distinct|different|biological|technical|"
    r"indipendenti|separate|distinte|diverse|biologiche|tecniche)\s+){0,3})"
    r"(?P<entity>[a-z][a-z\s\-]{1,28}?)\b",
    re.IGNORECASE,
)

#: Qualificatori di scope: "per group", "per well", "in each condition"
SCOPE_QUALIFIER = re.compile(
    r"\b(?:per|for each|in each|for every|by|nel|per ciascun\w*|per ogni)\s+"
    r"(?P<scope>group|condition|treatment|genotype|arm|timepoint|time point|endpoint|"
    r"well|plate|field|image|section|slice|roi|cell|nucleus|animal|mouse|rat|pup|donor|"
    r"subject|patient|dam|litter|cage|culture|preparation|tissue|pool|aliquot|library|"
    r"run|batch|organoid|explant|"
    r"gruppo|condizione|trattamento|genotipo|pozzetto|animale|topo|donatore|soggetto|"
    r"madre|cucciolata|gabbia|coltura|preparazione|campo|sezione|cellula|tessuto|lotto)\b",
    re.IGNORECASE,
)

TOTAL_QUALIFIER = re.compile(r"\b(in total|total|overall|complessivi|in totale)\b", re.IGNORECASE)


@dataclass(slots=True)
class NumberMention:
    """Un numero trovato nel testo, con contesto e posizione assoluta."""

    value: int | None
    raw_text: str
    entity_text: str
    start: int
    end: int
    qualifiers: tuple[str, ...] = ()
    style: str = "count_phrase"  # n_equals | count_phrase
    is_range: bool = False


def parse_number(token: str) -> int | None:
    """Converte cifre con separatori o numeri scritti a parole."""
    text = token.strip().lower()
    if not text:
        return None
    if text in NUMBER_WORDS:
        return NUMBER_WORDS[text]
    cleaned = text.replace(",", "").replace(".", "").replace(" ", "")
    if cleaned.isdigit():
        try:
            return int(cleaned)
        except ValueError:  # pragma: no cover - difensivo
            return None
    return None


def find_n_mentions(text: str, offset: int = 0) -> list[NumberMention]:
    """Trova le menzioni esplicite di n (`n = ...`)."""
    mentions: list[NumberMention] = []
    for match in N_EQUALS.finditer(text):
        value = parse_number(match.group("value"))
        qualifiers: list[str] = []
        if match.group("qualifier"):
            qualifiers.append(match.group("qualifier").strip().lower())
        window = text[match.start() : min(len(text), match.end() + 60)]
        qualifiers.extend(_context_qualifiers(window))
        entity = (match.group("entity") or "").strip()
        mentions.append(
            NumberMention(
                value=value,
                raw_text=match.group(0).strip(),
                entity_text=entity,
                start=offset + match.start(),
                end=offset + match.end(),
                qualifiers=tuple(dict.fromkeys(qualifiers)),
                style="n_equals",
                is_range=bool(match.group("tail")),
            )
        )
    return mentions


def find_count_phrases(text: str, offset: int = 0) -> list[NumberMention]:
    """Trova conteggi in forma `<numero> <entita>`."""
    mentions: list[NumberMention] = []
    for match in COUNT_PHRASE.finditer(text):
        value = parse_number(match.group("value"))
        if value is None:
            continue
        modifiers = (match.group("modifiers") or "").strip().lower()
        entity = match.group("entity").strip()
        # Il qualificatore vale solo dentro la stessa frase: "quattro animali per
        # gabbia" e una cardinalita, "n = 8 animali. Cinque campi per pozzetto"
        # sono due affermazioni diverse.
        window = _sentence_window(text, match.start(), match.end())
        qualifiers = list(_context_qualifiers(window))
        if modifiers:
            qualifiers.extend(modifiers.split())
        mentions.append(
            NumberMention(
                value=value,
                raw_text=match.group(0).strip(),
                entity_text=entity,
                start=offset + match.start(),
                end=offset + match.end(),
                qualifiers=tuple(dict.fromkeys(qualifiers)),
                style="count_phrase",
            )
        )
    return mentions


def _sentence_window(text: str, start: int, end: int, max_chars: int = 48) -> str:
    """Finestra dopo il numero, troncata alla fine della frase."""
    tail = text[end : min(len(text), end + max_chars)]
    for terminator in (". ", "; ", ".\n", ";\n"):
        position = tail.find(terminator)
        if position != -1:
            tail = tail[:position]
    if tail.endswith("."):
        tail = tail[:-1]
    return text[start:end] + tail


def _context_qualifiers(window: str) -> list[str]:
    found: list[str] = []
    scope = SCOPE_QUALIFIER.search(window)
    if scope:
        found.append(f"per_{scope.group('scope').lower().replace(' ', '_')}")
    if TOTAL_QUALIFIER.search(window):
        found.append("total")
    return found
