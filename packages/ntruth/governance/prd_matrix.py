"""Parse the final PRD implementation matrix and pin v9 disposition.

The live tree is an engineering implementation of PRD v8.0. PRD v9.0 is the
official requirement source for *new* scientific-contract work. This module
does not promote v9-only tokens to IMPLEMENTED and does not close scientific
HOLD.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final

BLOCKER_ID_RE = re.compile(r"SRR-V8-[0-9]{3}")
FINAL_STATUS_VALUES = frozenset({"IMPLEMENTED", "PARTIAL", "MISSING"})

EXPECTED_REQUIREMENT_COUNT: Final = 88
EXPECTED_IMPLEMENTED_COUNT: Final = 36
EXPECTED_PARTIAL_COUNT: Final = 48
EXPECTED_MISSING_COUNT: Final = 4

MISSING_REQUIREMENT_IDS: Final[frozenset[str]] = frozenset(
    {
        "V8-CROSSWALK",
        "V8-CORPUS",
        "V8-SYNTH-ABLATION",
        "V8-STRATEGY-VALIDATION",
    }
)

MISSING_DISPOSITIONS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "V8-CROSSWALK": "EXTERNAL_EVIDENCE_ONLY",
        "V8-CORPUS": "EXTERNAL_EVIDENCE_ONLY",
        "V8-SYNTH-ABLATION": "EXTERNAL_EVIDENCE_ONLY",
        "V8-STRATEGY-VALIDATION": "KEEP_FAIL_CLOSED",
    }
)

V9_ONLY_UNSHIPPED_TOKENS: Final[tuple[str, ...]] = (
    "FactorRole",
    "ContrastType",
    "SupportProfile",
    "ContrastSupportClaim",
    "MaterialLineage",
    "TeamEvaluationProtocol",
)

SCIENTIFIC_STATUS_PIN: Final[Mapping[str, str]] = MappingProxyType(
    {
        "repository_implementation_status": "IMPLEMENTED_WITH_EXPLICIT_BLOCKERS",
        "scientific_validation": "NOT_STARTED",
        "training_and_external_challenge": "HOLD",
    }
)


@dataclass(frozen=True, slots=True)
class MatrixRow:
    """One final-matrix requirement row."""

    requirement_id: str
    status: str
    blocker_ids: tuple[str, ...]


def parse_final_matrix(text: str) -> tuple[MatrixRow, ...]:
    """Parse requirement rows from the final implementation matrix markdown."""

    rows: list[MatrixRow] = []
    for line in text.splitlines():
        if not line.startswith("| V8-"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 8:
            raise ValueError(f"malformed final matrix row: {line[:80]}")
        status = cells[3]
        if status not in FINAL_STATUS_VALUES:
            raise ValueError(f"{cells[0]}: invalid status {status!r}")
        rows.append(
            MatrixRow(
                requirement_id=cells[0],
                status=status,
                blocker_ids=tuple(sorted(set(BLOCKER_ID_RE.findall(cells[6])))),
            )
        )
    return tuple(rows)


def load_final_implementation_matrix(path: Path) -> tuple[MatrixRow, ...]:
    """Load the committed final matrix from disk."""

    return parse_final_matrix(path.read_text(encoding="utf-8"))


def matrix_status_counts(rows: tuple[MatrixRow, ...]) -> dict[str, int]:
    """Count IMPLEMENTED / PARTIAL / MISSING rows."""

    counts = {status: 0 for status in FINAL_STATUS_VALUES}
    for row in rows:
        counts[row.status] += 1
    return counts


def missing_requirement_ids(rows: tuple[MatrixRow, ...]) -> frozenset[str]:
    """Return the MISSING requirement identifiers."""

    return frozenset(row.requirement_id for row in rows if row.status == "MISSING")


def incomplete_rows_without_blockers(rows: tuple[MatrixRow, ...]) -> tuple[str, ...]:
    """Return PARTIAL/MISSING rows that forgot a registered-style blocker ID."""

    return tuple(
        row.requirement_id
        for row in rows
        if row.status in {"PARTIAL", "MISSING"} and not row.blocker_ids
    )


def disposition_for(requirement_id: str) -> str:
    """Return the operational class for a MISSING row, or raise if unknown."""

    try:
        return MISSING_DISPOSITIONS[requirement_id]
    except KeyError as exc:
        raise KeyError(f"no v9 disposition pin for {requirement_id}") from exc


def v9_only_tokens_claimed_implemented(text: str) -> tuple[str, ...]:
    """Detect false claims that a v9-only token is already the shipped kernel."""

    claimed: list[str] = []
    for token in V9_ONLY_UNSHIPPED_TOKENS:
        pattern = re.compile(
            rf"{re.escape(token)}\s+is\s+(?:now\s+)?(?:IMPLEMENTED|the shipped binding kernel)",
            re.IGNORECASE,
        )
        if pattern.search(text):
            claimed.append(token)
    return tuple(claimed)
