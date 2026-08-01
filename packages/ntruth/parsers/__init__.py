"""Parser: JATS/DOCX/PDF/CSV/XLSX/TXT -> Document IR con span e celle (PRD 11.1)."""

from ntruth.parsers.base import (
    ParseFailure,
    Parser,
    RawBlock,
    RawDocument,
    RawStatisticalCode,
    RawStatisticalCodeCandidate,
    RawTable,
)
from ntruth.parsers.code import CodeParser
from ntruth.parsers.registry import PARSERS, build_document_ir, parser_for
from ntruth.parsers.sections import classify_heading, looks_like_heading

__all__ = [
    "PARSERS",
    "CodeParser",
    "ParseFailure",
    "Parser",
    "RawBlock",
    "RawDocument",
    "RawStatisticalCode",
    "RawStatisticalCodeCandidate",
    "RawTable",
    "build_document_ir",
    "classify_heading",
    "looks_like_heading",
    "parser_for",
]
