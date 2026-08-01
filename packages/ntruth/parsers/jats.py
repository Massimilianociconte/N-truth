"""Parser JATS/XML preservando struttura, tabelle e legends (PRD FR-002).

Parsing difensivo: entita esterne e DTD non vengono risolte (PRD NFR-13).
"""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

from ntruth.parsers.base import ParseFailure, RawBlock, RawDocument, RawTable
from ntruth.schemas.document import ParserStatus

_MAX_DEPTH = 64


class JatsParser:
    name = "jats"

    def supports(self, path: Path, media_type: str) -> bool:
        return path.suffix.lower() in {".xml", ".nxml", ".jats"}

    def parse(self, path: Path) -> RawDocument:
        raw = path.read_bytes()
        # ElementTree non risolve entita esterne ne DTD remoti: il file viene letto
        # come dato inerte. Le dichiarazioni trovate vengono comunque segnalate.
        parser = ET.XMLParser()
        try:
            root = ET.fromstring(raw, parser=parser)
        except ET.ParseError as exc:
            raise ParseFailure(path, f"XML non valido (riga {exc.position[0]})") from exc

        doc = RawDocument(parser=self.name)
        if b"<!ENTITY" in raw:
            doc.warnings.append("dichiarazioni ENTITY ignorate per sicurezza")

        title = _text_of(root.find(".//article-title"))
        if title:
            doc.blocks.append(RawBlock(kind="heading", text=title, level=1))

        abstract = root.find(".//abstract")
        if abstract is not None:
            doc.blocks.append(RawBlock(kind="heading", text="Abstract", level=2))
            for paragraph in abstract.iter("p"):
                text = _text_of(paragraph)
                if text:
                    doc.blocks.append(RawBlock(kind="paragraph", text=text))

        body = root.find(".//body")
        if body is not None:
            _walk_sections(body, doc, depth=1)
        else:
            doc.warnings.append("elemento <body> assente")

        for back in root.iter("back"):
            _walk_sections(back, doc, depth=2)

        table_index = 0
        for wrap in root.iter("table-wrap"):
            caption = _text_of(wrap.find(".//caption")) or _text_of(wrap.find("label"))
            if caption:
                doc.blocks.append(RawBlock(kind="caption", text=caption))
            table_element = wrap.find(".//table")
            if table_element is not None:
                table_index += 1
                parsed = _convert_table(table_element, f"table-{table_index}", caption)
                if parsed is not None:
                    doc.tables.append(parsed)

        for fig in root.iter("fig"):
            label = _text_of(fig.find("label"))
            caption = _text_of(fig.find("caption"))
            legend = " ".join(x for x in (label, caption) if x)
            if legend:
                doc.blocks.append(RawBlock(kind="heading", text=label or "Figure", level=3))
                doc.blocks.append(RawBlock(kind="caption", text=legend))

        if doc.is_empty:
            doc.status = ParserStatus.FAILED
            doc.warnings.append("nessun contenuto estratto dal JATS")
        elif body is None:
            doc.status = ParserStatus.PARTIAL
        return doc


def _walk_sections(element: ET.Element, doc: RawDocument, depth: int, single: bool = False) -> None:
    """Visita in profondita preservando l'ordine e l'annidamento delle sezioni."""
    if depth > _MAX_DEPTH:
        doc.warnings.append("profondita XML oltre il limite: sottoalbero ignorato")
        return
    if single:
        _emit_section(element, doc, depth)
        return
    for child in element:
        if child.tag == "sec":
            _emit_section(child, doc, depth)
        elif child.tag == "p":
            text = _text_of(child)
            if text:
                doc.blocks.append(RawBlock(kind="paragraph", text=text))


def _emit_section(sec: ET.Element, doc: RawDocument, depth: int) -> None:
    title = _text_of(sec.find("title"))
    if title:
        doc.blocks.append(RawBlock(kind="heading", text=title, level=min(depth + 1, 6)))
    for child in sec:
        if child.tag == "p":
            text = _text_of(child)
            if text:
                doc.blocks.append(RawBlock(kind="paragraph", text=text))
        elif child.tag == "sec":
            _walk_sections(child, doc, depth + 1, single=True)
        elif child.tag == "list":
            for item in child.iter("list-item"):
                text = _text_of(item)
                if text:
                    doc.blocks.append(RawBlock(kind="list_item", text=text))


def _text_of(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return " ".join("".join(element.itertext()).split()).strip()


def _convert_table(element: ET.Element, name: str, caption: str | None) -> RawTable | None:
    rows: list[list[str]] = []
    for tr in element.iter("tr"):
        cells = [_text_of(td) for td in list(tr) if td.tag in {"td", "th"}]
        if cells:
            rows.append(cells)
    if len(rows) < 2:
        return None
    header = [h or f"col_{i + 1}" for i, h in enumerate(rows[0])]
    table = RawTable(name=name, columns=header, caption=caption)
    for values in rows[1:]:
        padded = values + [""] * (len(header) - len(values))
        table.rows.append(dict(zip(header, padded[: len(header)], strict=True)))
    return table
