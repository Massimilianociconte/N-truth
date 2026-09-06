"""Estrazione tabelle PDF da coordinate (audit 2026-09-05, F1/F2).

I PDF di prova sono generati con sintassi PDF minima scritta a mano: il test
resta deterministico e non aggiunge dipendenze di generazione.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ntruth.parsers.pdf import PdfParser, _load_pdfplumber


def _minimal_pdf(content_stream: str) -> bytes:
    """Costruisce un PDF 1.4 a una pagina con un content stream arbitrario."""

    encoded = content_stream.encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(encoded)).encode() + b" >>\nstream\n" + encoded + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += str(number).encode() + b" 0 obj\n" + body + b"\nendobj\n"
    xref_pos = len(out)
    out += b"xref\n0 " + str(len(objects) + 1).encode() + b"\n"
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        b"trailer\n<< /Size " + str(len(objects) + 1).encode() + b" /Root 1 0 R >>\n"
        b"startxref\n" + str(xref_pos).encode() + b"\n%%EOF\n"
    )
    return bytes(out)


def _text(x: float, y: float, value: str) -> str:
    return f"BT /F1 10 Tf {x} {y} Td ({value}) Tj ET\n"


def _cell(x: float, y: float, width: float, height: float) -> str:
    return f"0.5 w {x} {y} {width} {height} re S\n"


def test_pdf_table_is_extracted_from_grid(tmp_path: Path) -> None:
    if _load_pdfplumber() is None:  # pragma: no cover - dipendenza ora nel core
        pytest.skip("pdfplumber non installato")
    stream = (
        _cell(100, 700, 150, 40)
        + _cell(250, 700, 150, 40)
        + _cell(100, 660, 150, 40)
        + _cell(250, 660, 150, 40)
        + _text(110, 712, "group")
        + _text(260, 712, "n")
        + _text(110, 672, "control")
        + _text(260, 672, "6")
    )
    path = tmp_path / "methods.pdf"
    path.write_bytes(_minimal_pdf(stream))
    doc = PdfParser().parse(path)
    assert doc.tables, doc.warnings
    table = doc.tables[0]
    assert table.columns[0].startswith(("group", "colonna"))
    assert table.rows
    assert any("6" in value for row in table.rows for value in row.values())
    assert any("control" in value for row in table.rows for value in row.values())


def test_pdf_two_column_layout_warns_on_reading_order(tmp_path: Path) -> None:
    if _load_pdfplumber() is None:  # pragma: no cover - dipendenza ora nel core
        pytest.skip("pdfplumber non installato")
    left_words = [_text(60, 700 - 14 * i, f"lorem{i}") for i in range(14)]
    right_words = [_text(400, 700 - 14 * i, f"ipsum{i}") for i in range(14)]
    path = tmp_path / "twocol.pdf"
    path.write_bytes(_minimal_pdf("".join(left_words + right_words)))
    doc = PdfParser().parse(path)
    assert any("due colonne" in warning for warning in doc.warnings)


def test_pdf_without_pdfplumber_keeps_text_and_warns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("ntruth.parsers.pdf._load_pdfplumber", lambda: None)
    stream = _text(72, 720, "Cells were assigned to control or treatment.")
    path = tmp_path / "plain.pdf"
    path.write_bytes(_minimal_pdf(stream))
    doc = PdfParser().parse(path)
    assert doc.blocks, "il testo deve restare disponibile senza pdfplumber"
    assert any("pdfplumber non installato" in warning for warning in doc.warnings)
    assert doc.tables == []


def test_scanned_pdf_fails_closed_with_ocr_hint(tmp_path: Path) -> None:
    # Una pagina senza operatori di testo: nessun carattere estraibile.
    path = tmp_path / "scanned.pdf"
    path.write_bytes(_minimal_pdf("0.5 w 72 720 468 20 re S\n"))
    doc = PdfParser().parse(path)
    assert doc.status.value == "failed"
    assert any("OCR" in warning for warning in doc.warnings)
