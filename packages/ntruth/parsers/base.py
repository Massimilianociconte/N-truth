"""Contratto comune dei parser: da byte a blocchi con coordinate.

Ogni parser dichiara il proprio esito. Un file non leggibile viene riportato,
mai ignorato in silenzio (PRD FR-006).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from ntruth.schemas.document import ParserStatus

BlockKind = Literal["heading", "paragraph", "caption", "list_item"]


@dataclass(slots=True, frozen=True)
class RawStatisticalCodeCandidate:
    """Dichiarazione sintattica di clustering trovata nel codice.

    E una evidenza *silver* e non rappresenta mai una dichiarazione di
    allocazione/randomizzazione. Gli offset puntano al testo originale.
    """

    cluster_expression: str
    declaration: str
    start: int
    end: int
    line_start: int
    line_end: int


@dataclass(slots=True, frozen=True)
class RawStatisticalCode:
    """Artefatto di codice letto come byte/testo, mai importato o eseguito."""

    language: Literal["r", "python", "r_markdown"]
    text: str
    sha256: str
    start: int
    end: int
    line_start: int
    line_end: int
    candidates: tuple[RawStatisticalCodeCandidate, ...] = ()


@dataclass(slots=True)
class RawBlock:
    """Blocco testuale prima dell'assegnazione di sezione."""

    kind: BlockKind
    text: str
    level: int = 0


@dataclass(slots=True)
class RawTable:
    """Tabella o foglio, gia normalizzato a stringhe."""

    name: str
    columns: list[str] = field(default_factory=list)
    rows: list[dict[str, str]] = field(default_factory=list)
    sheet: str | None = None
    caption: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RawDocument:
    """Uscita di un parser per un singolo file."""

    parser: str
    status: ParserStatus = ParserStatus.OK
    blocks: list[RawBlock] = field(default_factory=list)
    tables: list[RawTable] = field(default_factory=list)
    statistical_code: list[RawStatisticalCode] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.blocks and not self.tables and not self.statistical_code


class Parser(Protocol):
    """Interfaccia minima. I parser sono isolati dal resto per contratto (NFR-11)."""

    name: str

    def supports(self, path: Path, media_type: str) -> bool: ...

    def parse(self, path: Path) -> RawDocument: ...


class ParseFailure(RuntimeError):
    """Errore di parsing con file e punto, come richiesto dall'error handling (PRD 11.4)."""

    def __init__(self, path: Path, detail: str) -> None:
        super().__init__(f"{path.name}: {detail}")
        self.path = path
        self.detail = detail
