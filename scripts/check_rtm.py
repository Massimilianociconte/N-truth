"""Validate the PRD v9 Requirements Traceability Matrix baseline (App. AP, FR-091).

Fail-closed checks on ``data/rtm-v0.1.csv``: exact header, non-empty fields,
unique requirement ids, PRD section format, role-style owners, allowed
statuses, and schema/test paths that exist in the repository unless they carry
the explicit MISSING_EXPLICIT / NONE_WITH_RATIONALE markers.  IMPLEMENTED rows
require at least one real, existing test path.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

RTM_PATH = Path("data") / "rtm-v0.1.csv"
REQUIRED_COLUMNS: tuple[str, ...] = (
    "requirement_id",
    "source_prd_section",
    "schema_or_api",
    "component",
    "test",
    "metric_gate",
    "owner_role",
    "status",
    "evidence_note",
)
ALLOWED_STATUSES = frozenset({"PLANNED", "PARTIAL", "IMPLEMENTED"})
SCHEMA_MARKER = "MISSING_EXPLICIT"
TEST_MARKER = "NONE_WITH_RATIONALE"
REQUIREMENT_ID_RE = re.compile(r"^(?:FR-\d{3}|NFR-\d{2})$")
SECTION_RE = re.compile(r"^\d+(?:\.\d+)?$")
OWNER_ROLE_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _split_paths(cell: str) -> list[str]:
    return [item.strip() for item in cell.split(";") if item.strip()]


def check_rtm(repository_root: Path) -> tuple[dict[str, str], tuple[str, ...]]:
    csv_path = repository_root / RTM_PATH
    checks: dict[str, str] = {}
    diagnostics: list[str] = []

    try:
        text = csv_path.read_text(encoding="utf-8")
    except OSError as exc:
        return {"rtm_present": "FAIL"}, (f"cannot read {RTM_PATH}: {exc}",)

    reader = csv.DictReader(text.splitlines())
    header = tuple(reader.fieldnames or ())
    checks["columns_exact"] = "PASS" if header == REQUIRED_COLUMNS else "FAIL"
    if header != REQUIRED_COLUMNS:
        diagnostics.append(f"header must be exactly {list(REQUIRED_COLUMNS)}")

    seen_ids: set[str] = set()
    status_counts: dict[str, int] = {status: 0 for status in sorted(ALLOWED_STATUSES)}
    rows_valid = True
    paths_resolve = True
    statuses_coherent = True

    for line_number, row in enumerate(reader, start=2):
        label = f"row {line_number}"
        requirement_id = (row.get("requirement_id") or "").strip()
        for column in REQUIRED_COLUMNS:
            value = (row.get(column) or "").strip()
            if not value:
                diagnostics.append(f"{label}: empty field {column}")
                rows_valid = False
        if not REQUIREMENT_ID_RE.fullmatch(requirement_id):
            diagnostics.append(f"{label}: invalid requirement id {requirement_id!r}")
            rows_valid = False
        elif requirement_id in seen_ids:
            diagnostics.append(f"{label}: duplicate requirement id {requirement_id}")
            rows_valid = False
        else:
            seen_ids.add(requirement_id)

        section = (row.get("source_prd_section") or "").strip()
        if section and SECTION_RE.fullmatch(section) is None:
            diagnostics.append(
                f"{label}: source_prd_section must be like '21.1' or '22': {section!r}"
            )
            rows_valid = False

        status = (row.get("status") or "").strip()
        if status and status not in ALLOWED_STATUSES:
            diagnostics.append(f"{label}: status must be one of {sorted(ALLOWED_STATUSES)}")
            rows_valid = False
        elif status:
            status_counts[status] += 1

        owner_role = (row.get("owner_role") or "").strip()
        if owner_role and OWNER_ROLE_RE.fullmatch(owner_role) is None:
            diagnostics.append(
                f"{label}: owner_role must be a role id like 'semantic-lead': {owner_role!r}"
            )
            rows_valid = False

        schema_or_api = (row.get("schema_or_api") or "").strip()
        if schema_or_api != SCHEMA_MARKER and schema_or_api:
            candidate = repository_root / schema_or_api
            if not candidate.exists():
                diagnostics.append(f"{label}: schema_or_api path does not exist: {schema_or_api}")
                paths_resolve = False

        test_cell = (row.get("test") or "").strip()
        test_paths = _split_paths(test_cell)
        has_marker = TEST_MARKER in test_paths
        real_test_paths = [item for item in test_paths if item != TEST_MARKER]
        if has_marker and len(test_paths) > 1:
            diagnostics.append(f"{label}: {TEST_MARKER} cannot be combined with real test paths")
            rows_valid = False
        for test_path in real_test_paths:
            if not (repository_root / test_path).exists():
                diagnostics.append(f"{label}: test path does not exist: {test_path}")
                paths_resolve = False
        if status == "IMPLEMENTED" and (has_marker or not real_test_paths):
            diagnostics.append(f"{label}: IMPLEMENTED requires at least one existing test path")
            statuses_coherent = False

    checks["rows_valid"] = "PASS" if rows_valid else "FAIL"
    checks["paths_resolve"] = "PASS" if paths_resolve else "FAIL"
    checks["statuses_coherent"] = "PASS" if statuses_coherent else "FAIL"
    checks["requirements_unique"] = "PASS" if rows_valid else "FAIL"
    checks["summary"] = json.dumps(
        {
            "requirement_count": len(seen_ids),
            "status_counts": status_counts,
        },
        sort_keys=True,
    )
    return checks, tuple(diagnostics)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    checks, diagnostics = check_rtm(root)
    payload = {
        "schema_version": "9.0.0",
        "status": "PASS" if not diagnostics else "FAIL",
        "checks": checks,
        "diagnostics": diagnostics,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if not diagnostics else 1


if __name__ == "__main__":
    raise SystemExit(main())
