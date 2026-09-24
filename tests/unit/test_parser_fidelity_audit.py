"""Fedelta dei parser: nessuna cella o pagina persa in silenzio.

Controesempi dell'audit scientifico 2026-09-12 (A04, A09, A10) e degli export
CSV reali con righe vuote, preservati come regressioni.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from conftest import ProjectFactory

from ntruth.parsers.base import RawDocument
from ntruth.parsers.pdf import (
    MAX_PDF_TABLE_COLUMNS,
    MAX_PDF_TABLE_ROWS,
    PdfParser,
    _extract_page_tables,
    _grid_to_table,
)
from ntruth.parsers.tabular import MAX_COLUMNS, CsvParser, _build_table
from ntruth.schemas.document import ParserStatus
from ntruth.schemas.manifest import ReleaseProfile


def _cells(table: Any) -> list[str]:
    return [value for row in table.rows for value in row.values()]


@pytest.mark.parametrize(
    "header",
    [
        ["animal", "animal", "animal_1"],
        ["animal_1", "animal", "animal"],
        ["", "col_1", ""],
        ["x", "x", "x", "x_1", "x_2"],
    ],
)
def test_tabular_header_collisions_never_drop_cells(header: list[str]) -> None:
    doc = RawDocument(parser="csv")
    values = [f"v{index}" for index in range(len(header))]
    table = _build_table("sheet", iter([header, values]), doc)
    assert table is not None
    assert len(set(table.columns)) == len(header)
    assert sorted(_cells(table)) == sorted(values)
    assert doc.status is ParserStatus.OK


def test_tabular_duplicate_header_is_reported() -> None:
    doc = RawDocument(parser="csv")
    table = _build_table("sheet", iter([["animal", "animal"], ["A", "B"]]), doc)
    assert table is not None
    assert table.rows == [{"animal": "A", "animal_1": "B"}]
    assert any("animal->animal_1" in warning for warning in doc.warnings)


def test_csv_blank_lines_are_not_records(tmp_path: Path) -> None:
    path = tmp_path / "export.csv"
    path.write_text("\n\nanimal,group\r\nA,control\r\n\r\nB,drug\r\n\r\n", encoding="utf-8")
    doc = CsvParser().parse(path)
    assert doc.status is ParserStatus.OK, doc.warnings
    assert doc.tables[0].rows == [
        {"animal": "A", "group": "control"},
        {"animal": "B", "group": "drug"},
    ]


def test_csv_warning_keeps_source_row_number_after_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "late.csv"
    path.write_text("sample,value\nS1,1\n\nS2,2,extra\n", encoding="utf-8")
    doc = CsvParser().parse(path)
    assert doc.status is ParserStatus.PARTIAL
    assert any("riga 4 non rettangolare" in warning for warning in doc.warnings)


def test_csv_column_truncation_marks_partial() -> None:
    doc = RawDocument(parser="csv")
    header = [f"c{index}" for index in range(MAX_COLUMNS + 1)]
    table = _build_table("wide", iter([header, ["1"] * len(header)]), doc)
    assert table is not None
    assert len(table.columns) == MAX_COLUMNS
    assert doc.status is ParserStatus.PARTIAL


def test_pdf_table_row_truncation_is_declared() -> None:
    grid: list[list[str | None]] = [["id", "n"]] + [
        [str(index), "1"] for index in range(MAX_PDF_TABLE_ROWS + 2)
    ]
    table = _grid_to_table(grid, "t")
    assert table is not None
    assert len(table.rows) == MAX_PDF_TABLE_ROWS
    assert any(f"{MAX_PDF_TABLE_ROWS + 2} righe" in warning for warning in table.warnings)


def test_pdf_table_column_truncation_is_declared() -> None:
    width = MAX_PDF_TABLE_COLUMNS + 3
    grid: list[list[str | None]] = [[f"h{i}" for i in range(width)], ["1"] * width]
    table = _grid_to_table(grid, "t")
    assert table is not None
    assert len(table.columns) == MAX_PDF_TABLE_COLUMNS
    assert any(f"{width} colonne" in warning for warning in table.warnings)


def test_pdf_header_collision_keeps_every_cell() -> None:
    table = _grid_to_table([["x", "x", "x (2)"], ["1", "2", "3"]], "t")
    assert table is not None
    assert sorted(_cells(table)) == ["1", "2", "3"]


def test_pdf_truncated_table_marks_document_partial() -> None:
    grid = [["id", "n"]] + [[str(index), "1"] for index in range(MAX_PDF_TABLE_ROWS + 1)]
    page = SimpleNamespace(extract_tables=lambda: [grid])
    doc = RawDocument(parser="pdf")
    _extract_page_tables(page, 3, doc)
    assert doc.status is ParserStatus.PARTIAL
    assert any("pdf-page-3-table-1" in warning for warning in doc.warnings)


class _FakePage:
    def __init__(self, text: str) -> None:
        self._text = text

    def extract_text(self) -> str:
        return self._text


def test_pdf_page_without_text_is_declared_even_when_average_is_high(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pypdf

    class _FakeReader:
        is_encrypted = False

        def __init__(self, _path: str) -> None:
            self.pages = [_FakePage("Methods data " * 100), _FakePage("")]

    monkeypatch.setattr(pypdf, "PdfReader", _FakeReader)
    monkeypatch.setattr("ntruth.parsers.pdf._load_pdfplumber", lambda: None)
    path = tmp_path / "mixed.pdf"
    path.write_bytes(b"%PDF-1.4\n")
    doc = PdfParser().parse(path)
    assert doc.status is ParserStatus.PARTIAL
    assert any("pagine senza testo estraibile: 2 " in warning for warning in doc.warnings)


def test_partial_source_is_usable_but_marks_the_legacy_report_partial(
    make_project: ProjectFactory,
) -> None:
    # Un file PARTIAL entra comunque nel Document IR: il gate di abort deve
    # considerarlo utilizzabile e il report non puo dichiararsi "complete".
    from ntruth.parsers.registry import build_document_ir
    from ntruth.pipeline import _has_usable_parser_output, _report_status

    # La riga anomala e oltre il campione di sniff (64 righe) del media type.
    rows = ["sample,group", *(f"S{index},control" for index in range(1, 70)), "S70,drug,extra"]
    project = make_project(
        {"sheet.csv": "\n".join(rows) + "\n"},
        release_profile=ReleaseProfile.EXTENDED_EXPERIMENTAL,
    )
    document = build_document_ir(project)
    assert [source.status for source in document.files] == [ParserStatus.PARTIAL]
    assert _has_usable_parser_output(document) is True
    assert _report_status(document, ()) == "partial"
