"""Parser TXT e Markdown (PRD FR-003)."""

from __future__ import annotations

import re
from pathlib import Path

from ntruth.parsers.base import ParseFailure, RawBlock, RawDocument, RawTable
from ntruth.parsers.sections import heading_level, looks_like_heading
from ntruth.schemas.document import ParserStatus

_MD_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_MD_TABLE_SEP = re.compile(r"^\s*\|[\s:\-|]+\|\s*$")


class TextParser:
    name = "text"

    def supports(self, path: Path, media_type: str) -> bool:
        return path.suffix.lower() in {".txt", ".md"}

    def parse(self, path: Path) -> RawDocument:
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = path.read_text(encoding="latin-1")
            except OSError as exc:  # pragma: no cover - errore di sistema
                raise ParseFailure(path, f"lettura fallita ({exc})") from exc
        except OSError as exc:  # pragma: no cover
            raise ParseFailure(path, f"lettura fallita ({exc})") from exc

        doc = RawDocument(parser=self.name)
        lines = content.splitlines()
        buffer: list[str] = []
        table_buffer: list[str] = []
        table_index = 0

        def flush_paragraph() -> None:
            text = " ".join(s.strip() for s in buffer).strip()
            buffer.clear()
            if text:
                doc.blocks.append(RawBlock(kind="paragraph", text=text))

        def flush_table() -> None:
            nonlocal table_index
            rows = list(table_buffer)
            table_buffer.clear()
            table = _parse_markdown_table(rows, f"table-{table_index + 1}")
            if table is not None:
                doc.tables.append(table)
                table_index += 1

        for line in lines:
            if _MD_TABLE_ROW.match(line):
                flush_paragraph()
                table_buffer.append(line)
                continue
            if table_buffer:
                flush_table()
            if not line.strip():
                flush_paragraph()
                continue
            if looks_like_heading(line):
                flush_paragraph()
                doc.blocks.append(
                    RawBlock(
                        kind="heading",
                        text=line.strip().lstrip("#").strip(),
                        level=heading_level(line),
                    )
                )
                continue
            buffer.append(line)

        flush_paragraph()
        if table_buffer:
            flush_table()

        if doc.is_empty:
            doc.status = ParserStatus.FAILED
            doc.warnings.append("nessun contenuto testuale estratto")
        return doc


def _parse_markdown_table(rows: list[str], name: str) -> RawTable | None:
    cleaned = [r.strip().strip("|") for r in rows if not _MD_TABLE_SEP.match(r)]
    if len(cleaned) < 2:
        return None
    header = [c.strip() for c in cleaned[0].split("|")]
    table = RawTable(name=name, columns=header)
    for raw in cleaned[1:]:
        cells = [c.strip() for c in raw.split("|")]
        if len(cells) < len(header):
            cells.extend([""] * (len(header) - len(cells)))
        table.rows.append(dict(zip(header, cells[: len(header)], strict=True)))
    return table
