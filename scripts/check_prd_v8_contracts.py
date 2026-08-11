#!/usr/bin/env python3
"""Fail-closed clean-checkout truth gate for PRD v8 contracts and docs."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from ntruth.conformance.examples import (
    evaluate_prd_v8_examples,
    load_prd_v8_example_registry_file,
)
from ntruth.conformance.harness import evaluate_conformance
from ntruth.derivation_theory.loader import load_canonical_bundle
from ntruth.derivation_theory.runtime import verify_runtime_bundle
from ntruth.governance.repository_truth import validate_current_target_map
from ntruth.schemas.kernel import kernel_json_schemas
from ntruth.schemas.schema_snapshot import load_kernel_schema_snapshot_file

CURRENT_DOCUMENTS = (
    "README.md",
    "CONTRIBUTING.md",
    "GOVERNANCE.md",
    "CHANGELOG.md",
    "docs/README.md",
    "docs/status-snapshot.md",
    "docs/prd-v8-data-training-evaluation-boundary.md",
    "docs/public-specification-v0.1.md",
    "docs/architettura.md",
    "docs/releasing.md",
    "docs/parser-ai-contract.md",
    "docs/mlx-training-pipeline.md",
    "docs/data-and-model-development.md",
    "docs/validation-protocol-draft.md",
    "docs/system-card-v0.1.md",
    "docs/governance-workflow.md",
    "docs/governance/external-engagement-policy.md",
    "docs/data-management-plan-draft.md",
    "docs/training/DECISION-hold-pending-real-anchor.md",
    "docs/architecture/prd-v8-current-to-target.yaml",
    "docs/audits/prd-v8-full-migration/IMPLEMENTATION_GAP_REPORT.md",
    "docs/audits/prd-v8-full-migration/FINAL_IMPLEMENTATION_MATRIX.md",
    "docs/audits/prd-v8-full-migration/REQUIREMENT_TRACEABILITY_MATRIX.md",
    "docs/audits/prd-v8-full-migration/SCIENTIFIC_REVIEW_REGISTER.md",
    "docs/audits/prd-v8-full-migration/SOURCE_RECONCILIATION.md",
)
LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
BASELINE_REQUIREMENT_RE = re.compile(r"^\| (V8-[^:|]+):", re.MULTILINE)
FINAL_REQUIREMENT_RE = re.compile(r"^\| (V8-[^| ]+) \|", re.MULTILINE)
REGISTER_ROW_RE = re.compile(r"^\| (SRR-V8-[0-9]{3}) \|", re.MULTILINE)
BLOCKER_ID_RE = re.compile(r"SRR-V8-[0-9]{3}")
BLOCKER_SHORTHAND_RE = re.compile(r"`[0-9]{3}`")
FINAL_STATUS_VALUES = frozenset({"IMPLEMENTED", "PARTIAL", "MISSING"})
HISTORICAL_NON_NORMATIVE_DOCUMENTS = (
    "docs/parser-ai-contract.md",
    "docs/mlx-training-pipeline.md",
    "docs/data-and-model-development.md",
    "docs/validation-protocol-draft.md",
    "docs/system-card-v0.1.md",
    "docs/governance-workflow.md",
    "docs/governance/external-engagement-policy.md",
    "docs/data-management-plan-draft.md",
    "docs/training/DECISION-hold-pending-real-anchor.md",
)


def _local_link_diagnostics(root: Path) -> tuple[str, ...]:
    diagnostics: list[str] = []
    for relative in CURRENT_DOCUMENTS:
        document = root / relative
        if not document.is_file():
            diagnostics.append(f"current document missing: {relative}")
            continue
        if document.suffix not in {".md", ".markdown"}:
            continue
        text = document.read_text(encoding="utf-8")
        for raw_target in LINK_RE.findall(text):
            target = raw_target.strip().strip("<>")
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            path_part = target.split("#", maxsplit=1)[0]
            if not path_part:
                continue
            candidate = (document.parent / path_part).resolve()
            try:
                candidate.relative_to(root.resolve())
            except ValueError:
                diagnostics.append(f"{relative}: local link escapes repository: {target}")
                continue
            if not candidate.exists():
                diagnostics.append(f"{relative}: broken local link: {target}")
    docs_index_path = root / "docs/README.md"
    try:
        docs_index = docs_index_path.read_text(encoding="utf-8")
        historical_offset = docs_index.index("## Historical records")
    except (OSError, ValueError) as exc:
        diagnostics.append(f"docs/README.md lacks a historical records boundary: {exc}")
        historical_offset = -1
        docs_index = ""
    for relative in HISTORICAL_NON_NORMATIVE_DOCUMENTS:
        try:
            text = (root / relative).read_text(encoding="utf-8")
        except OSError:
            continue
        if "HISTORICAL_NON_NORMATIVE" not in text:
            diagnostics.append(f"{relative}: historical contract lacks non-normative marker")
        index_target = relative.removeprefix("docs/")
        occurrence = docs_index.find(index_target)
        if historical_offset < 0 or occurrence < historical_offset:
            diagnostics.append(f"{relative}: historical contract is presented as current")
    current_boundary = root / "docs/prd-v8-data-training-evaluation-boundary.md"
    try:
        current_text = current_boundary.read_text(encoding="utf-8")
    except OSError as exc:
        diagnostics.append(f"current v8 data/training/evaluation boundary missing: {exc}")
    else:
        for required in (
            "ParserCandidateOutput",
            "GoldParserTarget",
            "EXTERNAL_CHALLENGE",
            "HOLD",
        ):
            if required not in current_text:
                diagnostics.append("current v8 data/training/evaluation boundary lacks " + required)
    return tuple(diagnostics)


def _requirements_matrix_diagnostics(root: Path) -> tuple[str, ...]:
    diagnostics: list[str] = []
    audit_root = root / "docs/audits/prd-v8-full-migration"
    baseline_path = audit_root / "REQUIREMENT_TRACEABILITY_MATRIX.md"
    final_path = audit_root / "FINAL_IMPLEMENTATION_MATRIX.md"
    register_path = audit_root / "SCIENTIFIC_REVIEW_REGISTER.md"
    try:
        baseline = baseline_path.read_text(encoding="utf-8")
        final = final_path.read_text(encoding="utf-8")
        register = register_path.read_text(encoding="utf-8")
    except OSError as exc:
        return (f"requirements matrix: {exc}",)

    registered_blockers = set(REGISTER_ROW_RE.findall(register))

    baseline_ids = BASELINE_REQUIREMENT_RE.findall(baseline)
    final_ids = FINAL_REQUIREMENT_RE.findall(final)
    if len(baseline_ids) != 88 or len(set(baseline_ids)) != 88:
        diagnostics.append("Phase 1 matrix must contain exactly 88 unique requirement IDs")
    if len(final_ids) != 88 or len(set(final_ids)) != 88:
        diagnostics.append("final matrix must contain exactly 88 unique requirement IDs")
    missing = sorted(set(baseline_ids) - set(final_ids))
    unexpected = sorted(set(final_ids) - set(baseline_ids))
    if missing:
        diagnostics.append(f"final matrix missing requirement IDs: {', '.join(missing)}")
    if unexpected:
        diagnostics.append(f"final matrix has unexpected requirement IDs: {', '.join(unexpected)}")

    statuses: list[str] = []
    for line in final.splitlines():
        if not line.startswith("| V8-"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 8:
            diagnostics.append(f"malformed final matrix row: {line[:80]}")
            continue
        requirement_id = cells[0]
        status = cells[3]
        statuses.append(status)
        if BLOCKER_SHORTHAND_RE.search(cells[6]):
            diagnostics.append(
                f"{requirement_id}: non-canonical blocker shorthand; use complete SRR-V8-NNN IDs"
            )
        blockers = set(BLOCKER_ID_RE.findall(cells[6]))
        if status in {"PARTIAL", "MISSING"} and not blockers:
            diagnostics.append(f"{requirement_id}: partial/missing row lacks a blocker ID")
        unknown_blockers = sorted(blockers - registered_blockers)
        if unknown_blockers:
            diagnostics.append(
                f"{requirement_id}: unregistered blocker IDs: {', '.join(unknown_blockers)}"
            )
    invalid_statuses = sorted(set(statuses) - FINAL_STATUS_VALUES)
    if invalid_statuses:
        diagnostics.append(
            "final matrix contains non-final statuses: " + ", ".join(invalid_statuses)
        )
    if "IMPLEMENTED_WITH_EXPLICIT_BLOCKERS" not in final:
        diagnostics.append("final matrix lacks repository-level conformance conclusion")
    return tuple(diagnostics)


def run_checks(root: Path) -> tuple[dict[str, str], tuple[str, ...]]:
    checks: dict[str, str] = {}
    diagnostics: list[str] = []

    architecture = validate_current_target_map(
        root / "docs/architecture/prd-v8-current-to-target.yaml",
        repository_root=root,
    )
    checks["architecture_map"] = "PASS" if architecture.valid else "FAIL"
    diagnostics.extend(architecture.diagnostics)

    link_diagnostics = _local_link_diagnostics(root)
    checks["current_document_links"] = "PASS" if not link_diagnostics else "FAIL"
    diagnostics.extend(link_diagnostics)

    matrix_diagnostics = _requirements_matrix_diagnostics(root)
    checks["requirements_matrix"] = "PASS" if not matrix_diagnostics else "FAIL"
    diagnostics.extend(matrix_diagnostics)

    try:
        snapshot = load_kernel_schema_snapshot_file(
            root / "packages/ntruth/schemas/assets/prd-v8-kernel-schemas-8.0.0.json"
        )
        if snapshot.schemas != kernel_json_schemas():
            raise ValueError("packaged kernel schema snapshot differs from runtime schemas")
    except (OSError, ValueError) as exc:
        checks["kernel_schema_snapshot"] = "FAIL"
        diagnostics.append(f"kernel schema snapshot: {exc}")
    else:
        checks["kernel_schema_snapshot"] = "PASS"

    try:
        registry = load_prd_v8_example_registry_file(
            root / "packages/ntruth/conformance/assets/"
            "prd-v8-example-conformance-registry-8.0.0.json"
        )
        report = evaluate_prd_v8_examples(registry)
        if not report.passed:
            raise ValueError("; ".join(report.failures))
    except (OSError, ValueError) as exc:
        checks["prd_examples"] = "FAIL"
        diagnostics.append(f"PRD examples: {exc}")
    else:
        checks["prd_examples"] = "PASS"

    try:
        bundle = load_canonical_bundle(root)
        conformance = evaluate_conformance(bundle)
        runtime_conformance = verify_runtime_bundle(bundle)
        failures = (*conformance.failures, *runtime_conformance.failures)
        if failures:
            raise ValueError("; ".join(str(failure) for failure in failures))
    except (OSError, ValueError) as exc:
        checks["theory_rulebook_conformance"] = "FAIL"
        diagnostics.append(f"Theory/Rulebook conformance: {exc}")
    else:
        checks["theory_rulebook_conformance"] = "PASS"

    return checks, tuple(diagnostics)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    checks, diagnostics = run_checks(root)
    payload: dict[str, Any] = {
        "schema_version": "8.0.0",
        "status": "PASS" if not diagnostics else "FAIL",
        "checks": checks,
        "diagnostics": diagnostics,
        "scientific_readiness": "HOLD",
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if not diagnostics else 1


if __name__ == "__main__":
    raise SystemExit(main())
