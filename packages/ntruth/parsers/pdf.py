"""Parser PDF testuale (PRD FR-004).

L'OCR e solo un fallback esplicito e non e incluso nel core: un PDF senza testo
estraibile viene dichiarato `degraded` e le sue evidenze restano a bassa
confidenza. Le regole non possono generare alert critical basati solo su span
low-confidence (PRD 11.4).
"""

from __future__ import annotations

import re
from pathlib import Path

from ntruth.parsers.base import ParseFailure, RawBlock, RawDocument
from ntruth.parsers.sections import looks_like_heading
from ntruth.schemas.document import ParserStatus

#: Sotto questa densita di caratteri per pagina il PDF e verosimilmente scansionato.
MIN_CHARS_PER_PAGE = 200

_HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")
_MULTI_WS = re.compile(r"[ \t]+")


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

        cleaned = _HYPHEN_BREAK.sub(r"\1\2", joined)
        for chunk in re.split(r"\n\s*\n", cleaned):
            block_text = _MULTI_WS.sub(" ", chunk.replace("\n", " ")).strip()
            if not block_text:
                continue
            if looks_like_heading(block_text) and len(block_text.split()) <= 12:
                doc.blocks.append(RawBlock(kind="heading", text=block_text, level=2))
            else:
                doc.blocks.append(RawBlock(kind="paragraph", text=block_text))

        if doc.is_empty:
            doc.status = ParserStatus.FAILED
            doc.warnings.append("nessun blocco testuale ricostruito")
        return doc
