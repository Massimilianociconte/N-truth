"""Parser PDF testuale con estrazione tabelle (PRD FR-004, audit 2026-09-05).

L'OCR e solo un fallback esplicito e non e incluso nel core: un PDF senza testo
estraibile viene dichiarato `degraded` e le sue evidenze restano a bassa
confidenza. Le regole non possono generare alert critical basati solo su span
low-confidence (PRD 11.4).

Le tabelle vengono estratte da pdfplumber (deterministico, nessuna rete) quando
la dipendenza e installata; in sua assenza il testo resta disponibile con un
avviso esplicito, mai un fallimento silenzioso del dato tabellare.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ntruth.parsers.base import ParseFailure, RawBlock, RawDocument, RawTable
from ntruth.parsers.sections import looks_like_heading
from ntruth.schemas.document import ParserStatus

#: Sotto questa densita di caratteri per pagina il PDF e verosimilmente scansionato.
MIN_CHARS_PER_PAGE = 200

MAX_PDF_TABLES_PER_PAGE = 10
MAX_PDF_TABLE_ROWS = 2000
MAX_PDF_TABLE_COLUMNS = 128

#: Sotto questa parola per meta-pagina un gutter verticale non e significativo.
_MULTI_COLUMN_MIN_WORDS_PER_SIDE = 12
#: Numero minimo di rettangoli/linee per sospettare una griglia non estratta.
_MIN_GRID_EDGES = 8

_HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")
_MULTI_WS = re.compile(r"[ \t]+")


def _load_pdfplumber() -> Any:
    """Import differito di pdfplumber; None quando la dipendenza non c'e."""

    try:
        import pdfplumber
    except ImportError:
        return None
    return pdfplumber


class PdfParser:
    name = "pdf"

    def supports(self, path: Path, media_type: str) -> bool:
        return path.suffix.lower() == ".pdf"

    def parse(self, path: Path) -> RawDocument:
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover - dipendenza dichiarata
            raise ParseFailure(path, "pypdf non installato") from exc

        try:
            reader = PdfReader(str(path))
        except Exception as exc:
            raise ParseFailure(path, f"PDF illeggibile ({type(exc).__name__})") from exc

        doc = RawDocument(parser=self.name)
        if getattr(reader, "is_encrypted", False):
            doc.status = ParserStatus.FAILED
            doc.warnings.append("PDF cifrato: nessuna estrazione")
            return doc

        pages_text: list[str] = []
        for index, page in enumerate(reader.pages):
            try:
                text = page.extract_text() or ""
            except Exception as exc:
                doc.warnings.append(f"pagina {index + 1} non estratta ({type(exc).__name__})")
                text = ""
            pages_text.append(text)

        joined = "\n".join(pages_text)
        total_chars = len(joined.strip())
        page_count = max(len(pages_text), 1)
        density = total_chars / page_count

        if total_chars == 0:
            doc.status = ParserStatus.FAILED
            doc.warnings.append(
                "nessun testo estraibile: PDF probabilmente scansionato, serve OCR esplicito"
            )
            return doc
        if density < MIN_CHARS_PER_PAGE:
            doc.status = ParserStatus.DEGRADED
            doc.warnings.append(
                f"densita testuale bassa ({density:.0f} caratteri/pagina): "
                "estrazione incerta, evidenze a bassa confidenza"
            )

        plumber = _load_pdfplumber()
        if plumber is None:
            doc.warnings.append("estrazione tabelle PDF non disponibile: pdfplumber non installato")
        else:
            _extract_layout(plumber, path, doc)

        cleaned = _HYPHEN_BREAK.sub(r"\1\2", joined)
        for chunk in re.split(r"\n\s*\n", cleaned):
            block_text = _MULTI_WS.sub(" ", chunk.replace("\n", " ")).strip()
            if not block_text:
                continue
            if looks_like_heading(block_text) and len(block_text.split()) <= 12:
                doc.blocks.append(RawBlock(kind="heading", text=block_text, level=2))
            else:
                doc.blocks.append(RawBlock(kind="paragraph", text=block_text))

        if doc.is_empty and not doc.tables:
            doc.status = ParserStatus.FAILED
            doc.warnings.append("nessun blocco testuale ricostruito")
        return doc


def _extract_layout(plumber: Any, path: Path, doc: RawDocument) -> None:
    """Estrae tabelle e note di layout; fallisce come avviso, mai come crash."""

    try:
        with plumber.open(str(path)) as pdf:
            for page_index, page in enumerate(pdf.pages, start=1):
                _extract_page_tables(page, page_index, doc)
                note = _multi_column_note(page, page_index)
                if note:
                    doc.warnings.append(note)
                grid_note = _unextracted_grid_note(page, page_index)
                if grid_note:
                    doc.warnings.append(grid_note)
    except Exception as exc:
        doc.warnings.append(f"estrazione tabelle non riuscita ({type(exc).__name__})")


def _extract_page_tables(page: Any, page_number: int, doc: RawDocument) -> None:
    try:
        grids = page.extract_tables() or []
    except Exception as exc:
        doc.warnings.append(
            f"pagina {page_number}: estrazione tabelle fallita ({type(exc).__name__})"
        )
        return
    if len(grids) > MAX_PDF_TABLES_PER_PAGE:
        doc.warnings.append(
            f"pagina {page_number}: oltre {MAX_PDF_TABLES_PER_PAGE} tabelle, "
            "le restanti sono ignorate"
        )
    for table_index, grid in enumerate(grids[:MAX_PDF_TABLES_PER_PAGE], start=1):
        table = _grid_to_table(grid, f"pdf-page-{page_number}-table-{table_index}")
        if table is None:
            continue
        doc.tables.append(table)


def _grid_to_table(grid: list[list[str | None]], name: str) -> RawTable | None:
    """Normalizza la griglia pdfplumber in RawTable; scarta i falsi positivi."""

    rows = [[("" if cell is None else str(cell)).strip() for cell in row] for row in grid if row]
    rows = [row for row in rows if any(row)]
    if len(rows) < 2 or max(len(row) for row in rows) < 2:
        return None
    width = min(max(len(row) for row in rows), MAX_PDF_TABLE_COLUMNS)
    rows = [row[:width] + [""] * (width - len(row[:width])) for row in rows]
    if len(rows) > MAX_PDF_TABLE_ROWS:
        rows = rows[: MAX_PDF_TABLE_ROWS + 1]
    header = _unique_headers(rows[0])
    if not header:
        return None
    table = RawTable(name=name, columns=header)
    for row in rows[1 : MAX_PDF_TABLE_ROWS + 1]:
        table.rows.append(dict(zip(header, row, strict=False)))
    if len(rows) - 1 > MAX_PDF_TABLE_ROWS:
        table.warnings.append(f"righe oltre {MAX_PDF_TABLE_ROWS} ignorate")
    return table


def _unique_headers(header: list[str]) -> list[str]:
    """Rende le colonne univoche mantenendo l'etichetta originale quando c'e."""

    seen: dict[str, int] = {}
    out: list[str] = []
    for index, value in enumerate(header):
        label = value or f"colonna {index + 1}"
        count = seen.get(label, 0)
        seen[label] = count + 1
        out.append(label if count == 0 else f"{label} ({count + 1})")
    return out


def _multi_column_note(page: Any, page_number: int) -> str | None:
    """Rileva un gutter verticale pieno: due colonne senza parola a cavallo."""

    try:
        words = page.extract_words() or []
    except Exception:
        return None
    if len(words) < 2 * _MULTI_COLUMN_MIN_WORDS_PER_SIDE:
        return None
    mid = page.width / 2
    left = [word for word in words if word["x1"] <= mid]
    right = [word for word in words if word["x0"] >= mid]
    if len(words) - len(left) - len(right) > 0:
        return None
    if len(left) < _MULTI_COLUMN_MIN_WORDS_PER_SIDE:
        return None
    if len(right) < _MULTI_COLUMN_MIN_WORDS_PER_SIDE:
        return None
    gutter = min(word["x0"] for word in right) - max(word["x1"] for word in left)
    if gutter <= 0:
        return None
    return (
        f"pagina {page_number}: layout probabilmente a due colonne "
        "(gutter verticale pieno); l'ordine di lettura non e garantito"
    )


def _unextracted_grid_note(page: Any, page_number: int) -> str | None:
    """Avvisa quando la pagina ha griglie di righe ma nessuna tabella estratta."""

    try:
        edges = len(page.rects) + len(page.lines)
        if edges < _MIN_GRID_EDGES:
            return None
        tables = page.extract_tables() or []
    except Exception:
        return None
    if tables:
        return None
    return (
        f"pagina {page_number}: rilevate {edges} linee/rettangoli di griglia ma "
        "nessuna tabella estratta; il dato tabellare potrebbe essere incompleto"
    )
