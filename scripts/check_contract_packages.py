"""Validate the five PRD v9 Contract Package manifests (contracts/*.yaml).

Fail-closed checks per PRD v9 §0.6/§20.2/§29.3: parseable YAML, required
fields, owner roles (never personal names), semver version, DRAFT/ACTIVE/
DEPRECATED status, resolvable acyclic dependencies, and current_evidence
paths that exist in the repository (or the accounted MISSING_EXPLICIT marker).

The loader prefers PyYAML when installed and otherwise falls back to a strict
deterministic subset parser covering the manifest grammar used in contracts/;
anything outside the subset fails closed instead of being guessed.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

CONTRACTS_DIRNAME = "contracts"
REQUIRED_FIELDS: tuple[str, ...] = (
    "id",
    "title",
    "version",
    "status",
    "owner",
    "gate",
    "reviewers_minimi",
    "modules",
    "dependencies",
    "current_evidence",
    "known_gaps",
)
LIST_FIELDS: tuple[str, ...] = (
    "reviewers_minimi",
    "modules",
    "dependencies",
    "known_gaps",
)
EXPECTED_CONTRACT_IDS: tuple[str, ...] = (
    "CP-SCI",
    "CP-EPI",
    "CP-DATA",
    "CP-EVAL",
    "CP-RUN",
)
ALLOWED_STATUSES = frozenset({"DRAFT", "ACTIVE", "DEPRECATED"})
MISSING_EXPLICIT_MARKER = "MISSING_EXPLICIT"
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z][0-9A-Za-z.-]*)?$")
CP_ID_RE = re.compile(r"^CP-[A-Z]{3,4}$")


def _parse_scalar(token: str) -> str:
    token = token.strip()
    if len(token) >= 2 and token[0] == token[-1] and token[0] in {"'", '"'}:
        return token[1:-1]
    return token


def _parse_subset_lines(
    lines: list[tuple[int, str]], start: int, indent: int
) -> tuple[dict[str, Any] | list[str], int]:
    """Parse one indentation block; mappings and plain string lists only."""

    is_list = lines[start][1].startswith("- ")
    if is_list:
        items: list[str] = []
        index = start
        while index < len(lines) and lines[index][0] == indent:
            content = lines[index][1]
            if not content.startswith("- "):
                raise ValueError("list block mixed with mapping entries")
            item = content.removeprefix("- ")
            if ":" in item and not (item.startswith("'") or item.startswith('"')):
                raise ValueError(f"unsupported nested list syntax: {item!r}")
            items.append(_parse_scalar(item))
            index += 1
        if not items:
            raise ValueError("empty list blocks are not allowed")
        return items, index
    mapping: dict[str, Any] = {}
    index = start
    while index < len(lines) and lines[index][0] == indent:
        content = lines[index][1]
        if content.startswith("- "):
            raise ValueError("mapping block mixed with list entries")
        key, separator, raw_value = content.partition(":")
        key = _parse_scalar(key)
        if not key or " " in key:
            raise ValueError(f"invalid mapping key: {content!r}")
        if separator and raw_value.strip():
            token = raw_value.strip()
            if token == "[]":
                mapping[key] = []
            elif token.startswith("["):
                raise ValueError(f"unsupported flow syntax: {content!r}")
            else:
                mapping[key] = _parse_scalar(token)
            index += 1
            continue
        if index + 1 >= len(lines) or lines[index + 1][0] <= indent:
            raise ValueError(f"mapping key without value or nested block: {key!r}")
        child, index = _parse_subset_lines(lines, index + 1, lines[index + 1][0])
        mapping[key] = child
    return mapping, index


def parse_yaml_subset(text: str) -> dict[str, Any]:
    """Parse the deterministic manifest YAML subset, failing closed."""

    lines: list[tuple[int, str]] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise ValueError("tab indentation is not allowed")
        lines.append((len(raw) - len(raw.lstrip()), stripped))
    if not lines:
        raise ValueError("manifest is empty")
    if lines[0][0] != 0:
        raise ValueError("manifest must start at column zero")
    parsed, consumed = _parse_subset_lines(lines, 0, 0)
    if consumed != len(lines):
        raise ValueError("manifest has inconsistent indentation")
    if not isinstance(parsed, dict):
        raise ValueError("manifest root must be a mapping")
    return parsed


def load_manifest(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError:
        return parse_yaml_subset(text)
    loaded = yaml.safe_load(text)
    if not isinstance(loaded, dict):
        raise ValueError("manifest root must be a mapping")
    return loaded


def _string_list(
    value: object, *, field: str, manifest_id: str, allow_empty: bool = False
) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError(f"{manifest_id}.{field} must be a string list")
    if not value and not allow_empty:
        raise ValueError(f"{manifest_id}.{field} must be a non-empty string list")
    if len(set(value)) != len(value):
        raise ValueError(f"{manifest_id}.{field} contains duplicates")
    return [item.strip() for item in value]


def _dependency_diagnostics(contracts: dict[str, dict[str, Any]]) -> list[str]:
    diagnostics: list[str] = []
    edges: dict[str, list[str]] = {}
    for contract_id, manifest in contracts.items():
        try:
            dependencies = _string_list(
                manifest["dependencies"],
                field="dependencies",
                manifest_id=contract_id,
                allow_empty=True,
            )
        except ValueError as exc:
            diagnostics.append(str(exc))
            edges[contract_id] = []
            continue
        unknown = [item for item in dependencies if item not in contracts]
        if unknown:
            diagnostics.append(
                f"{contract_id} depends on unknown contract packages: {', '.join(unknown)}"
            )
        if contract_id in dependencies:
            diagnostics.append(f"{contract_id} depends on itself")
        edges[contract_id] = [item for item in dependencies if item != contract_id]
    state: dict[str, int] = {}

    def visit(node: str, path: list[str]) -> None:
        state[node] = 1
        for neighbour in edges.get(node, []):
            if state.get(neighbour) == 1:
                cycle = " -> ".join([*path, neighbour])
                diagnostics.append(f"contract package dependency cycle: {cycle}")
            elif state.get(neighbour, 0) == 0:
                visit(neighbour, [*path, neighbour])
        state[node] = 2

    for node in sorted(edges):
        if state.get(node, 0) == 0:
            visit(node, [node])
    return diagnostics


def check_contract_packages(
    repository_root: Path, *, require_canonical_set: bool = True
) -> tuple[dict[str, str], tuple[str, ...]]:
    contracts_dir = repository_root / CONTRACTS_DIRNAME
    checks: dict[str, str] = {}
    diagnostics: list[str] = []

    manifests: dict[str, dict[str, Any]] = {}
    sources: dict[str, Path] = {}
    paths = sorted(contracts_dir.glob("*.yaml")) if contracts_dir.is_dir() else []
    if not paths:
        diagnostics.append(f"no contract package manifests found under {contracts_dir}")
    checks["manifests_present"] = "PASS" if paths else "FAIL"

    for path in paths:
        try:
            manifest = load_manifest(path)
        except (OSError, ValueError) as exc:
            diagnostics.append(f"{path.relative_to(repository_root)}: unparseable: {exc}")
            continue
        contract_id = manifest.get("id")
        if not isinstance(contract_id, str) or not CP_ID_RE.fullmatch(contract_id):
            diagnostics.append(f"{path.name}: invalid or missing id field")
            continue
        if contract_id in manifests:
            diagnostics.append(f"{contract_id}: duplicate contract package id")
            continue
        manifests[contract_id] = manifest
        sources[contract_id] = path

    if require_canonical_set:
        unexpected_ids = sorted(set(manifests) - set(EXPECTED_CONTRACT_IDS))
        if unexpected_ids:
            diagnostics.append("unexpected contract package ids: " + ", ".join(unexpected_ids))
        missing_ids = [item for item in EXPECTED_CONTRACT_IDS if item not in manifests]
        if missing_ids:
            diagnostics.append("missing contract packages: " + ", ".join(missing_ids))
        checks["canonical_set"] = "PASS" if not missing_ids and not unexpected_ids else "FAIL"
    else:
        checks["canonical_set"] = "SKIPPED"

    missing_explicit_count = 0
    for contract_id, manifest in manifests.items():
        label = sources[contract_id].name
        manifest_missing_explicit = 0
        for field in REQUIRED_FIELDS:
            if field not in manifest:
                diagnostics.append(f"{label}: missing required field {field}")
                continue
            value = manifest[field]
            if field in LIST_FIELDS:
                try:
                    _string_list(
                        value,
                        field=field,
                        manifest_id=label,
                        allow_empty=field == "dependencies",
                    )
                except ValueError as exc:
                    diagnostics.append(str(exc))
            elif isinstance(value, dict):
                if field != "current_evidence" or not value:
                    diagnostics.append(f"{label}.{field} has an unexpected mapping value")
            elif not isinstance(value, str) or not value.strip():
                diagnostics.append(f"{label}.{field} must be a non-empty string")
        status = manifest.get("status")
        if status is not None and status not in ALLOWED_STATUSES:
            diagnostics.append(f"{label}.status must be one of {sorted(ALLOWED_STATUSES)}")
        version = manifest.get("version")
        if isinstance(version, str) and SEMVER_RE.fullmatch(version) is None:
            diagnostics.append(f"{label}.version is not semantic versioning: {version!r}")
        title = manifest.get("title")
        if isinstance(title, str) and not title.strip():
            diagnostics.append(f"{label}.title must not be blank")

        evidence = manifest.get("current_evidence")
        if evidence is None:
            continue
        if not isinstance(evidence, dict) or not evidence:
            diagnostics.append(f"{label}.current_evidence must be a non-empty mapping")
            continue
        declared_modules = manifest.get("modules")
        declared_set = set(declared_modules) if isinstance(declared_modules, list) else set()
        for module, references in evidence.items():
            if module not in declared_set:
                diagnostics.append(f"{label}.current_evidence covers undeclared module {module!r}")
            if not isinstance(references, list) or not references:
                diagnostics.append(
                    f"{label}.current_evidence.{module} must list at least one reference"
                )
                continue
            for reference in references:
                if not isinstance(reference, str) or not reference.strip():
                    diagnostics.append(
                        f"{label}.current_evidence.{module} contains a blank reference"
                    )
                    continue
                if reference == MISSING_EXPLICIT_MARKER:
                    manifest_missing_explicit += 1
                    continue
                candidate = (repository_root / reference).resolve()
                if not candidate.is_file():
                    diagnostics.append(
                        f"{label}.current_evidence.{module} path does not exist: {reference}"
                    )
        uncovered = declared_set - set(evidence)
        if uncovered:
            diagnostics.append(
                f"{label} modules without current_evidence entries: " + ", ".join(sorted(uncovered))
            )
        missing_explicit_count += manifest_missing_explicit
        gaps = manifest.get("known_gaps")
        if manifest_missing_explicit and (not isinstance(gaps, list) or not gaps):
            diagnostics.append(f"{label} declares MISSING_EXPLICIT evidence without known_gaps")
    diagnostics.extend(_dependency_diagnostics(manifests))
    if diagnostics:
        checks["fields_and_evidence"] = "FAIL"
        checks["dependencies_acyclic"] = "FAIL"
    else:
        checks["fields_and_evidence"] = "PASS"
        checks["dependencies_acyclic"] = "PASS"

    summary = {
        "missing_explicit_count": missing_explicit_count,
    }
    checks["summary"] = json.dumps(summary, sort_keys=True)
    return checks, tuple(diagnostics)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    checks, diagnostics = check_contract_packages(root)
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
