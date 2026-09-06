"""Mechanize requirement traceability checking for the PRD v8 migration audits.

Parses docs/audits/prd-v8-full-migration/REQUIREMENT_TRACEABILITY_MATRIX.md
(the pre-implementation clean-checkout baseline) and reconciles it with
FINAL_IMPLEMENTATION_MATRIX.md and SCIENTIFIC_REVIEW_REGISTER.md.

Fail-closed checks: dynamically detected table headers (English and Italian
variants), one row per requirement with a valid V8 identifier, exactly one
allowed disposition from the matrix-declared status vocabulary, scientific
risk vocabulary, evidence paths that resolve in the tracked repository tree
(MISSING_EXPLICIT accounted as an explicit sentinel), and SRR-V8-* blocker
references that exist in the register. Cross-file rules are conservative:
an RTM row claiming a stronger status than the final matrix supports is a
warning unless an explicit ``OVERRIDE:`` marker is present in the row, as is
an identifier missing from one of the two overlapping matrices.

Errors always fail; warnings fail only under --strict, mirroring the
structured JSON findings/exit-code style of the sibling scripts under
scripts/.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "9.0.0"

AUDITS_DIRNAME = "docs/audits/prd-v8-full-migration"
MATRIX_PATH = Path(AUDITS_DIRNAME) / "REQUIREMENT_TRACEABILITY_MATRIX.md"
FINAL_MATRIX_PATH = Path(AUDITS_DIRNAME) / "FINAL_IMPLEMENTATION_MATRIX.md"
REGISTER_PATH = Path(AUDITS_DIRNAME) / "SCIENTIFIC_REVIEW_REGISTER.md"

# Dispositions harvested from the status legend of the traceability matrix at
# HEAD cd17cb209eb80ed169df11b8d8f6a322663dc2b1 (base origin/main@fe089eff42c
# 16e3fa55606be340c85df57c5442b), line 7: IMPLEMENTED · PARTIAL · MISSING ·
# INCOMPATIBLE · LEGACY. Ranked weakest-to-strongest for cross-matrix claims.
ALLOWED_DISPOSITIONS: tuple[str, ...] = (
    "MISSING",
    "LEGACY",
    "INCOMPATIBLE",
    "PARTIAL",
    "IMPLEMENTED",
)
DISPOSITION_STRENGTH: dict[str, int] = {
    value: rank for rank, value in enumerate(ALLOWED_DISPOSITIONS)
}
# Scientific risk legend, same file, line 9: CRITICAL/HIGH/MEDIUM/LOW.
ALLOWED_RISKS: tuple[str, ...] = ("CRITICAL", "HIGH", "MEDIUM", "LOW")
# Evidence sentinel parity with scripts/check_contract_packages.py.
EVIDENCE_SENTINELS = frozenset({"MISSING_EXPLICIT"})

HEADER_ID_NAMES = frozenset({"requirement_v8", "requisito_v8"})
HEADER_STATUS_NAMES = frozenset({"status"})
HEADER_EVIDENCE_NAMES = frozenset({"files involved", "file coinvolti"})
HEADER_RISK_NAMES = frozenset({"scientific risk", "rischio scientifico"})

ID_BODY_RE = r"V8-[A-Z0-9]+(?:[/-][A-Z0-9]+)*"
REQUIREMENT_ID_RE = re.compile(rf"^{ID_BODY_RE}$")
CELL_ID_RE = re.compile(rf"^({ID_BODY_RE})(?:\s*:\s*(.*))?$", re.DOTALL)
SEPARATOR_CELL_RE = re.compile(r"^:?-{3,}:?$")
BACKTICK_RE = re.compile(r"`([^`]+)`")
SRR_REF_RE = re.compile(r"SRR-V8-(\d{3})")
SRR_RANGE_RE = re.compile(r"SRR-V8-(\d{3})(?:…|\.\.\.|-)(\d{3})")
UNKNOWN_SENTINEL_RE = re.compile(r"^[A-Z0-9]+(?:_[A-Z0-9]+)+$")
OVERRIDE_MARKER = "OVERRIDE:"

TRACKED_WALK_PRUNE = frozenset(
    {
        ".git",
        ".venv",
        "node_modules",
        "__pycache__",
        ".cache",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        ".hypothesis",
    }
)
DIRECT_PREFIXES: tuple[str, ...] = (
    "",
    "packages/ntruth/",
    "packages/",
    "docs/",
    "scripts/",
    "tests/",
    "data_manifests/",
)


@dataclass(frozen=True)
class RequirementRow:
    requirement_id: str
    line_number: int
    cells: tuple[str, ...]
    status: str
    risk: str
    evidence: tuple[tuple[str, bool], ...]


@dataclass(frozen=True)
class ParsedMatrix:
    relative: str
    rows: tuple[RequirementRow, ...]


def _logical_rows(text: str) -> list[tuple[int, str]]:
    """Fold consecutive pipe lines into logical rows, tolerating multi-line cells."""
    logical: list[tuple[int, str]] = []
    in_fence = False
    buffered: list[str] = []
    start = 0
    for line_number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not line.strip().startswith("|"):
            continue
        if not buffered:
            start = line_number
        buffered.append(line)
        if line.rstrip().endswith("|"):
            logical.append((start, "\n".join(buffered)))
            buffered = []
    return logical


def _split_cells(raw: str) -> tuple[str, ...] | None:
    content = raw.strip()
    if not (content.startswith("|") and content.endswith("|")):
        return None
    inner = content[1:-1]
    return tuple(cell.strip() for cell in inner.split("|"))


def _is_separator(cells: tuple[str, ...]) -> bool:
    return bool(cells) and all(SEPARATOR_CELL_RE.fullmatch(cell) for cell in cells)


def _column_index(cells: tuple[str, ...], names: frozenset[str]) -> int:
    lowered = [cell.lower().strip() for cell in cells]
    for name in names:
        if name in lowered:
            return lowered.index(name)
    return -1


def _evidence_tokens(evidence_cell: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for segment in evidence_cell.split(";"):
        backticked = BACKTICK_RE.findall(segment)
        if backticked:
            tokens.extend(token.strip() for token in backticked)
            continue
        stripped = segment.strip().strip("`").strip()
        if stripped:
            tokens.append(stripped)
    return tuple(tokens)


def parse_matrix(path: Path, relative: str) -> tuple[ParsedMatrix | None, list[str]]:
    """Parse one matrix file into rows, detecting the header row dynamically."""
    errors: list[str] = []
    if not path.is_file():
        return None, [f"{relative}: file not found"]
    logical = _logical_rows(path.read_text(encoding="utf-8"))
    if not logical:
        return None, [f"{relative}: no requirement tables found"]

    header_seen = False
    header_width = 0
    id_col = status_col = evidence_col = risk_col = -1
    rows: list[RequirementRow] = []
    for line_number, raw in logical:
        cells = _split_cells(raw)
        if cells is None:
            errors.append(f"{relative}:{line_number}: table row does not close with a pipe")
            continue
        if _is_separator(cells):
            continue
        if _column_index(cells, HEADER_ID_NAMES) >= 0:
            header_seen = True
            header_width = len(cells)
            id_col = _column_index(cells, HEADER_ID_NAMES)
            status_col = _column_index(cells, HEADER_STATUS_NAMES)
            evidence_col = _column_index(cells, HEADER_EVIDENCE_NAMES)
            risk_col = _column_index(cells, HEADER_RISK_NAMES)
            if status_col < 0:
                errors.append(f"{relative}:{line_number}: header lacks a status column")
            if evidence_col < 0:
                errors.append(f"{relative}:{line_number}: header lacks an evidence column")
            if risk_col < 0:
                errors.append(f"{relative}:{line_number}: header lacks a risk column")
            continue
        if not header_seen:
            continue
        id_cell = cells[id_col].strip() if 0 <= id_col < len(cells) else ""
        match = CELL_ID_RE.match(id_cell.replace("\n", " "))
        if match is None:
            if any(cell.strip() for cell in cells):
                errors.append(
                    f"{relative}:{line_number}: invalid requirement id {id_cell.strip()!r}"
                )
            continue
        requirement_id = match.group(1)
        if len(cells) != header_width:
            errors.append(
                f"{relative}:{line_number}: {requirement_id}: row has {len(cells)} cells, "
                f"header declares {header_width}"
            )
            continue
        rows.append(
            RequirementRow(
                requirement_id=requirement_id,
                line_number=line_number,
                cells=cells,
                status=cells[status_col] if 0 <= status_col < len(cells) else "",
                risk=cells[risk_col] if 0 <= risk_col < len(cells) else "",
                evidence=_evidence_tokens(
                    cells[evidence_col] if 0 <= evidence_col < len(cells) else ""
                ),
            )
        )
    if not header_seen:
        errors.append(f"{relative}: no requirement table header row detected")
        return None, errors
    if not rows:
        errors.append(f"{relative}: no requirement rows found")
    return ParsedMatrix(relative=relative, rows=tuple(rows)), errors


def _evidence_tokens(evidence_cell: str) -> tuple[tuple[str, bool], ...]:
    """Return ``(token, was_backticked)`` pairs from one evidence cell."""
    tokens: list[tuple[str, bool]] = []
    for segment in evidence_cell.split(";"):
        backticked = BACKTICK_RE.findall(segment)
        if backticked:
            tokens.extend((item.strip(), True) for item in backticked)
            continue
        stripped = segment.strip().strip("`").strip()
        if stripped:
            tokens.append((stripped, False))
    return tuple(tokens)


def _is_path_like(token: str, *, backticked: bool) -> bool:
    if not token or " " in token:
        return False
    if re.search(r"\.[A-Za-z][A-Za-z0-9]+$", token):
        return True
    if token.endswith("/"):
        return True
    return backticked and "/" in token


def _is_sentinel_like(token: str) -> bool:
    return UNKNOWN_SENTINEL_RE.fullmatch(token) is not None


def _tracked_index(repository_root: Path) -> frozenset[str] | None:
    try:
        completed = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=repository_root,
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return frozenset(
        entry.decode("utf-8", errors="replace") for entry in completed.stdout.split(b"\0") if entry
    )


def _pruned_walk_index(repository_root: Path) -> frozenset[str]:
    index: set[str] = set()
    for current, dirnames, filenames in os.walk(repository_root):
        dirnames[:] = [name for name in dirnames if name not in TRACKED_WALK_PRUNE]
        base = Path(current)
        for filename in filenames:
            index.add(base.joinpath(filename).relative_to(repository_root).as_posix())
    return frozenset(index)


def _resolve_evidence(
    token: str,
    index: frozenset[str],
    repository_root: Path,
    matrix_dir: Path,
) -> Path | None:
    for prefix in DIRECT_PREFIXES:
        candidate = repository_root / prefix / token
        if candidate.exists():
            return candidate
    sibling = matrix_dir / token
    if sibling.exists():
        return sibling
    for entry in index:
        if entry == token or entry.endswith("/" + token):
            return repository_root / entry
    return None


def _srr_universe(register_text: str) -> frozenset[str]:
    return frozenset(SRR_REF_RE.findall(register_text))


def _srr_references(text: str) -> set[str]:
    """Expand SRR-V8-NNN singles and ellipsis/hyphen ranges deterministically."""
    covered: set[str] = set()
    for start, end in SRR_RANGE_RE.findall(text):
        covered.update(f"{number:03d}" for number in range(int(start), int(end) + 1))
    references = set(covered)
    references.update(single for single in SRR_REF_RE.findall(text) if single not in covered)
    return references


def check_requirement_traceability(
    repository_root: Path,
    *,
    matrix_path: Path,
    final_matrix_path: Path,
    register_path: Path,
) -> tuple[dict[str, str], tuple[str, ...], tuple[str, ...], dict[str, Any]]:
    checks: dict[str, str] = {}
    errors: list[str] = []
    warnings: list[str] = []

    def display(target: Path) -> str:
        try:
            return target.resolve().relative_to(repository_root).as_posix()
        except ValueError:
            return target.resolve().as_posix()

    matrix_rel = display(matrix_path)
    final_rel = display(final_matrix_path)
    register_rel = display(register_path)

    matrix_text = ""
    if matrix_path.is_file():
        matrix_text = matrix_path.read_text(encoding="utf-8")
    final_text = ""
    if final_matrix_path.is_file():
        final_text = final_matrix_path.read_text(encoding="utf-8")
    register_text = ""
    if register_path.is_file():
        register_text = register_path.read_text(encoding="utf-8")
    else:
        errors.append(f"{register_rel}: file not found")

    parsed, parse_errors = parse_matrix(matrix_path, matrix_rel)
    final_parsed, final_parse_errors = parse_matrix(final_matrix_path, final_rel)
    errors.extend([*parse_errors, *final_parse_errors])
    checks["matrix_parse"] = "PASS" if not parse_errors else "FAIL"
    checks["final_matrix_parse"] = "PASS" if not final_parse_errors else "FAIL"
    checks["register_present"] = "PASS" if register_text else "FAIL"

    if parsed is None or final_parsed is None:
        checks["ids_unique"] = "FAIL"
        checks["dispositions_allowlist"] = "FAIL"
        checks["risk_vocabulary"] = "FAIL"
        checks["evidence_paths_resolve"] = "FAIL"
        checks["srr_references_resolve"] = "FAIL"
        checks["cross_matrix_consistency"] = "FAIL"
        summary = {"requirement_counts": {}, "status_tallies": {}, "strict": None}
        return checks, tuple(sorted(errors)), tuple(sorted(warnings)), summary

    index = _tracked_index(repository_root)
    if index is None:
        index = _pruned_walk_index(repository_root)
    srr_universe = _srr_universe(register_text) if register_text else frozenset()

    documents = (("RTM", parsed, matrix_text), ("FINAL", final_parsed, final_text))
    for label, document, text in documents:
        document_errors_before = len(errors)
        matrix_dir = (repository_root / document.relative).parent
        seen: set[str] = set()
        tallies: dict[str, int] = {value: 0 for value in ALLOWED_DISPOSITIONS}
        for row in document.rows:
            label_line = f"{document.relative}:{row.line_number}: {row.requirement_id}"
            if row.requirement_id in seen:
                errors.append(f"{label_line}: duplicate requirement id")
            seen.add(row.requirement_id)
            if row.status not in ALLOWED_DISPOSITIONS:
                errors.append(
                    f"{label_line}: disposition {row.status!r} must be one of "
                    f"{list(ALLOWED_DISPOSITIONS)}"
                )
            else:
                tallies[row.status] += 1
            if row.risk not in ALLOWED_RISKS:
                errors.append(
                    f"{label_line}: risk {row.risk!r} must be one of {list(ALLOWED_RISKS)}"
                )
            for token, backticked in row.evidence:
                if not _is_path_like(token, backticked=backticked):
                    if _is_sentinel_like(token) and token not in EVIDENCE_SENTINELS:
                        errors.append(f"{label_line}: unknown evidence sentinel {token!r}")
                    continue
                if _resolve_evidence(token, index, repository_root, matrix_dir) is None:
                    errors.append(
                        f"{label_line}: evidence path does not resolve in the tracked tree: {token}"
                    )
        unknown_srr = sorted(_srr_references(text) - srr_universe)
        if unknown_srr:
            errors.append(
                f"{document.relative}: SRR references absent from {register_rel}: "
                + ", ".join(unknown_srr)
            )
        duplicate_errors = sum(
            1 for error in errors[document_errors_before:] if "duplicate requirement id" in error
        )
        checks[f"{label}_rows_valid"] = "PASS" if len(errors) == document_errors_before else "FAIL"
        checks[f"{label}_ids_unique"] = "PASS" if not duplicate_errors else "FAIL"
        checks[f"{label}_dispositions"] = (
            "PASS" if document.rows and sum(tallies.values()) == len(document.rows) else "FAIL"
        )

    rtm_ids = {row.requirement_id for row in parsed.rows}
    final_ids = {row.requirement_id for row in final_parsed.rows}
    orphans_rtm = sorted(rtm_ids - final_ids)
    orphans_final = sorted(final_ids - rtm_ids)
    if orphans_rtm:
        warnings.append(f"{matrix_rel}: ids absent from final matrix: " + ", ".join(orphans_rtm))
    if orphans_final:
        warnings.append(
            f"{final_rel}: ids absent from traceability matrix: " + ", ".join(orphans_final)
        )

    final_status: dict[str, str] = {}
    for row in final_parsed.rows:
        final_status.setdefault(row.requirement_id, row.status)
    for row in parsed.rows:
        supported = final_status.get(row.requirement_id)
        if supported is None or row.status not in DISPOSITION_STRENGTH:
            continue
        if DISPOSITION_STRENGTH[row.status] > DISPOSITION_STRENGTH.get(supported, -1):
            if OVERRIDE_MARKER in " ".join(row.cells):
                continue
            warnings.append(
                f"{matrix_rel}:{row.line_number}: {row.requirement_id}: RTM claims "
                f"{row.status} but final matrix supports {supported} (add {OVERRIDE_MARKER} "
                "or fix the row)"
            )

    checks["cross_matrix_consistency"] = "FAIL" if errors else ("PASS" if not warnings else "WARN")
    summary = {
        "requirement_counts": {"RTM": len(parsed.rows), "FINAL": len(final_parsed.rows)},
        "status_tallies": {
            label: {
                value: sum(1 for row in document.rows if row.status == value)
                for value in ALLOWED_DISPOSITIONS
            }
            for label, document, _text in documents
        },
        "unresolved_evidence": sum(
            1 for error in errors if "evidence path does not resolve" in error
        ),
    }
    return checks, tuple(sorted(errors)), tuple(sorted(warnings)), summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--matrix", type=Path, default=None)
    parser.add_argument("--final-matrix", type=Path, default=None)
    parser.add_argument("--register", type=Path, default=None)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    matrix = args.matrix if args.matrix is not None else root / MATRIX_PATH
    final_matrix = args.final_matrix if args.final_matrix is not None else root / FINAL_MATRIX_PATH
    register = args.register if args.register is not None else root / REGISTER_PATH
    checks, errors, warnings, summary = check_requirement_traceability(
        root,
        matrix_path=matrix,
        final_matrix_path=final_matrix,
        register_path=register,
    )
    if args.strict:
        errors = tuple(sorted({*errors, *warnings}))
        warnings = ()
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "FAIL" if errors else "PASS",
        "checks": checks,
        "diagnostics": errors,
        "warnings": warnings,
        "summary": {**summary, "strict": args.strict},
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
