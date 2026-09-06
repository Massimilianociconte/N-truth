"""Parser CSV/TSV/XLSX per sample sheet (PRD FR-005).

Il sample sheet contiene la provenance essenziale del disegno: e per questo che
N-Truth legge tabelle e non solo testo (PRD 11.2). Le formule vengono disinnescate
prima di entrare nel Document IR (PRD NFR-13).
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from ntruth.ingest.safety import neutralize_formula
from ntruth.parsers.base import ParseFailure, RawDocument, RawTable
from ntruth.schemas.document import ParserStatus

if TYPE_CHECKING:
    from openpyxl.workbook.workbook import Workbook
    from openpyxl.worksheet.worksheet import Worksheet

MAX_ROWS = 200_000
MAX_COLUMNS = 512


class CsvParser:
    name = "csv"

    def supports(self, path: Path, media_type: str) -> bool:
        return path.suffix.lower() in {".csv", ".tsv"}

    def parse(self, path: Path) -> RawDocument:
        doc = RawDocument(parser=self.name)
        try:
            content = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            content = path.read_text(encoding="latin-1")
            doc.warnings.append("codifica non UTF-8: letto come latin-1")
        except OSError as exc:  # pragma: no cover
            raise ParseFailure(path, f"lettura fallita ({exc})") from exc

        # Il contratto D0/extended per .csv e il separatore virgola: lo sniffing
        # resta solo per estensioni non ambigue, perche la prosa puo flippare
        # il delimiter rilevato e spezzare le righe a meta pipeline.
        if path.suffix.lower() == ".tsv":
            delimiter = "\t"
        elif path.suffix.lower() == ".csv":
            delimiter = ","
        else:
            delimiter = _sniff_delimiter(content)
        reader = csv.reader(io.StringIO(content), delimiter=delimiter)
        table = _build_table(path.stem, reader, doc)
        if table is not None:
            doc.tables.append(table)
        else:
            doc.status = ParserStatus.FAILED
            doc.warnings.append("file tabellare vuoto")
        return doc


class XlsxParser:
    name = "xlsx"

    def supports(self, path: Path, media_type: str) -> bool:
        return path.suffix.lower() == ".xlsx"

    def parse(self, path: Path) -> RawDocument:
        try:
            from openpyxl import load_workbook
        except ImportError as exc:  # pragma: no cover - dipendenza dichiarata
            raise ParseFailure(path, "openpyxl non installato") from exc

        doc = RawDocument(parser=self.name)
        try:
            # data_only=False conserva la formula come testo inerte. openpyxl non
            # la esegue; _build_table la neutralizza prima del Document IR.
            # read_only limita la memoria (NFR-07/NFR-13).
            workbook = load_workbook(str(path), data_only=False, read_only=True)
        except Exception as exc:
            raise ParseFailure(path, f"XLSX illeggibile ({type(exc).__name__})") from exc

        # Seconda lettura con data_only=True: recupera i valori calcolati che
        # Excel ha messo in cache. Le celle formula senza cache restano testo
        # inerte con un avviso esplicito (audit 2026-09-05, F8).
        try:
            values_workbook = load_workbook(str(path), data_only=True, read_only=True)
        except Exception:
            values_workbook = None

        try:
            for sheet in workbook.worksheets:
                values_sheet = _values_sheet(values_workbook, sheet.title)
                rows = _iter_sheet_rows(sheet, values_sheet, doc)
                table = _build_table(sheet.title, rows, doc, sheet=sheet.title)
                if table is None:
                    doc.warnings.append(f"foglio '{sheet.title}' vuoto")
                    continue
                doc.tables.append(table)
        finally:
            workbook.close()
            if values_workbook is not None:
                values_workbook.close()

        if not doc.tables:
            doc.status = ParserStatus.FAILED
            doc.warnings.append("nessun foglio leggibile")
        return doc


def _values_sheet(values_workbook: Workbook | None, title: str) -> Worksheet | None:
    """Return the cached-value twin of a sheet, or None when unavailable."""

    if values_workbook is None:
        return None
    try:
        return values_workbook[title]
    except KeyError:
        return None


def _iter_sheet_rows(
    sheet: Worksheet, values_sheet: Worksheet | None, doc: RawDocument
) -> Iterable[list[str]]:
    """Yield text rows, substituting cached values for formula cells.

    La formula resta la fonte quando la cache manca: il valore calcolato non
    viene mai inventato. Le celle senza cache sono contate e segnalate a fine
    foglio.
    """

    value_rows = values_sheet.iter_rows(values_only=True) if values_sheet is not None else None
    uncached = 0
    for row in sheet.iter_rows(values_only=True):
        value_row: tuple[object, ...] | None = None
        if value_rows is not None:
            value_row = next(value_rows, None)
        cells: list[str] = []
        for index, cell in enumerate(row):
            text = "" if cell is None else str(cell)
            if text.startswith("=") and value_row is not None and index < len(value_row):
                cached = value_row[index]
                if cached is not None and str(cached).strip():
                    text = str(cached)
                else:
                    uncached += 1
            cells.append(text)
        if any(value.strip() for value in cells):
            yield cells
    if uncached:
        doc.warnings.append(
            f"foglio '{sheet.title}': {uncached} formule senza valore calcolato in cache "
            "(aprire e salvare il file da Excel per generarla)"
        )


def _sniff_delimiter(content: str) -> str:
    sample = content[:4096]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def _build_table(
    name: str, rows: Iterable[list[str]], doc: RawDocument, sheet: str | None = None
) -> RawTable | None:
    iterator = iter(rows)
    try:
        header_raw = next(iterator)
    except StopIteration:
        return None
    if len(header_raw) > MAX_COLUMNS:
        doc.warnings.append(f"{name}: {len(header_raw)} colonne oltre il limite, troncate")
        header_raw = header_raw[:MAX_COLUMNS]
    formula_cells = 0
    safe_header: list[str] = []
    for value in header_raw:
        safe, changed = neutralize_formula(str(value))
        formula_cells += int(changed)
        safe_header.append(safe.strip())
    header = _unique_headers(safe_header)
    if not header:
        return None

    table = RawTable(name=name, sheet=sheet, columns=header)
    for index, raw in enumerate(iterator):
        if index >= MAX_ROWS:
            table.warnings.append(f"righe oltre {MAX_ROWS} ignorate")
            doc.status = ParserStatus.PARTIAL
            break
        if len(raw) != len(header):
            message = (
                f"{name}: riga {index + 2} non rettangolare "
                f"({len(raw)} celle, attese {len(header)}); output parziale"
            )
            table.warnings.append(message)
            doc.warnings.append(message)
            doc.status = ParserStatus.PARTIAL
        values = list(raw[: len(header)])
        values.extend([""] * (len(header) - len(values)))
        record: dict[str, str] = {}
        for column, value in zip(header, values, strict=True):
            safe, changed = neutralize_formula(str(value))
            formula_cells += int(changed)
            record[column] = safe.strip()
        table.rows.append(record)

    if formula_cells:
        message = f"{name}: {formula_cells} celle con prefisso di formula disinnescate"
        table.warnings.append(message)
        doc.warnings.append(message)
    return table


def _unique_headers(raw: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out: list[str] = []
    for index, value in enumerate(raw):
        name = (value or "").strip() or f"col_{index + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0
        out.append(name)
    return out
