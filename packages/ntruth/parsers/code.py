"""Import non esecutivo di script statistici R/Python (PRD v3 FR-005).

Questo modulo non usa ``exec``, ``eval``, import dinamici o subprocess. Legge i
byte, accetta solo testo UTF-8 e conserva coordinate/checksum. Le dichiarazioni
di clustering sono candidate *silver* ``STATISTICAL_CODE`` e non allocazioni.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Literal

from ntruth.parsers.base import (
    ParseFailure,
    RawDocument,
    RawStatisticalCode,
    RawStatisticalCodeCandidate,
)

_LANGUAGE_BY_SUFFIX: dict[str, Literal["r", "python", "r_markdown"]] = {
    ".r": "r",
    ".py": "python",
    ".rmd": "r_markdown",
}

# Pattern volutamente stretti: descrivono sintassi di raggruppamento esplicita,
# non cercano di dedurre il disegno sperimentale o l'allocazione dei trattamenti.
_COMMON_CLUSTER_PATTERNS = (
    re.compile(
        r"\b(?:groups?|cluster|clusters)\s*=\s*(?P<cluster>"
        r"(?:[A-Za-z_]\w*\s*\[\s*['\"][^'\"]+['\"]\s*\]|"
        r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*))",
        re.IGNORECASE,
    ),
)

_R_CLUSTER_PATTERNS = (
    re.compile(r"\|\s*(?P<cluster>[A-Za-z_]\w*(?:\s*[/+:]\s*[A-Za-z_]\w*)*)\s*\)?"),
    re.compile(r"\bError\s*\(\s*(?P<cluster>[A-Za-z_]\w*(?:\s*/\s*[A-Za-z_]\w*)*)", re.I),
)


class CodeParser:
    """Parser testuale dedicato; non inoltra il codice ai normali estrattori."""

    name = "statistical-code-read-only"

    def supports(self, path: Path, media_type: str) -> bool:
        del media_type
        return path.suffix.lower() in _LANGUAGE_BY_SUFFIX

    def parse(self, path: Path) -> RawDocument:
        try:
            payload = path.read_bytes()
        except OSError as exc:  # pragma: no cover - errore di sistema
            raise ParseFailure(path, f"lettura fallita ({exc})") from exc
        if b"\x00" in payload:
            raise ParseFailure(path, "script non testuale: byte NUL rilevato")
        try:
            text = payload.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ParseFailure(path, "script non UTF-8; import testuale rifiutato") from exc
        if not text.strip():
            raise ParseFailure(path, "script privo di contenuto testuale")

        suffix = path.suffix.lower()
        language = _LANGUAGE_BY_SUFFIX[suffix]
        candidates = tuple(_clustering_candidates(text, language))
        artifact = RawStatisticalCode(
            language=language,
            text=text,
            sha256=hashlib.sha256(payload).hexdigest(),
            start=0,
            end=len(text),
            line_start=1,
            line_end=text.count("\n") + 1,
            candidates=candidates,
        )
        return RawDocument(
            parser=self.name,
            statistical_code=[artifact],
            warnings=[
                "codice statistico importato come testo read-only; "
                "candidate di clustering silver, mai evidenza di allocazione"
            ],
        )


def _clustering_candidates(
    text: str, language: Literal["r", "python", "r_markdown"]
) -> list[RawStatisticalCodeCandidate]:
    candidates: list[RawStatisticalCodeCandidate] = []
    patterns: tuple[re.Pattern[str], ...] = _COMMON_CLUSTER_PATTERNS
    if language in {"r", "r_markdown"}:
        patterns += _R_CLUSTER_PATTERNS
    line_start = 0
    for line_number, line in enumerate(text.splitlines(keepends=True), start=1):
        line_without_newline = line.rstrip("\r\n")
        for pattern in patterns:
            for match in pattern.finditer(line_without_newline):
                cluster = match.group("cluster").strip()
                start = line_start + match.start("cluster")
                end = line_start + match.end("cluster")
                candidate = RawStatisticalCodeCandidate(
                    cluster_expression=cluster,
                    declaration=line_without_newline.strip(),
                    start=start,
                    end=end,
                    line_start=line_number,
                    line_end=line_number,
                )
                if candidate not in candidates:
                    candidates.append(candidate)
        line_start += len(line)
    return candidates
