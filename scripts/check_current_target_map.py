"""Validate the PRD v9 current-to-target map (docs/architecture/prd-current-to-target.yaml).

Minimal fail-closed checks per PRD §20.3: parseable YAML, required root and
component fields, allowed states, owner roles, and current/ADR paths that
exist in the repository unless the component is explicitly MISSING.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

MAP_PATH = Path("docs/architecture") / "prd-current-to-target.yaml"
HISTORICAL_NOTE_PATH = Path("docs/architecture") / "prd-v8-current-to-target.HISTORICAL.md"
ALLOWED_STATES = frozenset({"IMPLEMENTED", "PARTIAL", "MISSING"})
MISSING_PLACEHOLDER = "MISSING_EXPLICIT"
OWNER_ROLE_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
REQUIRED_ROOT_FIELDS: tuple[str, ...] = (
    "schema_version",
    "map_id",
    "map_version",
    "target_contract",
    "status_semantics",
    "historical_predecessor",
    "components",
)
REQUIRED_COMPONENT_FIELDS: tuple[str, ...] = (
    "current_paths",
    "state",
    "owner_role",
    "migration_issue",
    "clean_checkout_evidence",
)


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
            else:
                mapping[key] = _parse_scalar(token)
            index += 1
            continue
        if index + 1 >= len(lines) or lines[index + 1][0] <= indent:
            raise ValueError(f"mapping key without value or nested block: {key!r}")
        child, index = _parse_subset_lines(lines, index + 1, lines[index + 1][0])
        mapping[key] = child
    return mapping, index


def parse_map_text(text: str) -> dict[str, Any]:
    """Parse the map preferring PyYAML and falling back to a strict subset parser."""

    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError:
        lines: list[tuple[int, str]] = []
        for raw in text.splitlines():
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "\t" in raw[: len(raw) - len(raw.lstrip())]:
                raise ValueError("tab indentation is not allowed") from None
            lines.append((len(raw) - len(raw.lstrip()), stripped))
        if not lines:
            raise ValueError("map is empty") from None
        parsed, consumed = _parse_subset_lines(lines, 0, 0)
        if consumed != len(lines):
            raise ValueError("map has inconsistent indentation") from None
        if not isinstance(parsed, dict):
            raise ValueError("map root must be a mapping") from None
        return parsed
    loaded = yaml.safe_load(text)
    if not isinstance(loaded, dict):
        raise ValueError("map root must be a mapping") from None
    return loaded


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("expected a string list")
    return [item.strip() for item in value]


def check_current_target_map(
    repository_root: Path, *, map_relative_path: Path | None = None
) -> tuple[dict[str, str], tuple[str, ...]]:
    map_path = (
        repository_root / map_relative_path if map_relative_path else repository_root / MAP_PATH
    )
    checks: dict[str, str] = {}
    diagnostics: list[str] = []

    try:
        payload = parse_map_text(map_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"map_parseable": "FAIL"}, (f"cannot parse {map_path.name}: {exc}",)

    checks["map_parseable"] = "PASS"
    missing_root = [field for field in REQUIRED_ROOT_FIELDS if field not in payload]
    if missing_root:
        diagnostics.append("missing root fields: " + ", ".join(missing_root))
    checks["root_fields"] = "PASS" if not missing_root else "FAIL"

    predecessor = payload.get("historical_predecessor")
    note_file = payload.get("historical_note_file")
    if (
        isinstance(predecessor, str)
        and predecessor
        and not (repository_root / predecessor).is_file()
    ):
        diagnostics.append(f"historical_predecessor does not exist: {predecessor}")
    if isinstance(note_file, str) and note_file and not (repository_root / note_file).is_file():
        diagnostics.append(f"historical_note_file does not exist: {note_file}")

    components = payload.get("components")
    if not isinstance(components, dict) or not components:
        diagnostics.append("components must be a non-empty mapping")
        components = {}

    paths_resolve = True
    states_valid = True
    fields_valid = True
    state_counts: dict[str, int] = {state: 0 for state in sorted(ALLOWED_STATES)}
    for component_id, spec in components.items():
        label = f"component {component_id}"
        if not isinstance(spec, dict):
            diagnostics.append(f"{label}: entry must be a mapping")
            fields_valid = False
            continue
        for field in REQUIRED_COMPONENT_FIELDS:
            if field not in spec:
                diagnostics.append(f"{label}: missing required field {field}")
                fields_valid = False
        state = spec.get("state")
        if state not in ALLOWED_STATES:
            diagnostics.append(f"{label}: invalid state {state!r}")
            states_valid = False
        else:
            state_counts[state] += 1

        owner_role = spec.get("owner_role")
        if not isinstance(owner_role, str) or OWNER_ROLE_RE.fullmatch(owner_role) is None:
            diagnostics.append(
                f"{label}: owner_role must be a role id like 'semantic-lead': {owner_role!r}"
            )
            fields_valid = False

        migration_issue = spec.get("migration_issue")
        clean_checkout_evidence = spec.get("clean_checkout_evidence")
        if not isinstance(migration_issue, str) or not migration_issue.strip():
            diagnostics.append(f"{label}: migration_issue must be a non-empty string")
            fields_valid = False
        if not isinstance(clean_checkout_evidence, str) or not clean_checkout_evidence.strip():
            diagnostics.append(f"{label}: clean_checkout_evidence must be a non-empty command")
            fields_valid = False

        try:
            current_paths = _string_list(spec.get("current_paths"))
        except ValueError as exc:
            diagnostics.append(f"{label}: current_paths must be a string list ({exc})")
            fields_valid = False
            continue
        if state == "MISSING":
            unexpected = [item for item in current_paths if item != MISSING_PLACEHOLDER]
            if not current_paths or unexpected:
                diagnostics.append(
                    f"{label}: MISSING state requires only the {MISSING_PLACEHOLDER} placeholder"
                )
                paths_resolve = False
            continue
        if not current_paths:
            diagnostics.append(f"{label}: non-MISSING components need at least one current path")
            paths_resolve = False
        for relative in current_paths:
            candidate = repository_root / relative
            if relative == MISSING_PLACEHOLDER or not (candidate.exists()):
                diagnostics.append(f"{label}: current path does not exist: {relative}")
                paths_resolve = False
        try:
            adr_paths = _string_list(spec.get("adr_paths", []))
        except ValueError as exc:
            diagnostics.append(f"{label}: adr_paths must be a string list ({exc})")
            fields_valid = False
            continue
        for relative in adr_paths:
            if not (repository_root / relative).exists():
                diagnostics.append(f"{label}: ADR path does not exist: {relative}")
                paths_resolve = False

    checks["component_fields"] = "PASS" if fields_valid else "FAIL"
    checks["states_valid"] = "PASS" if states_valid else "FAIL"
    checks["paths_resolve"] = "PASS" if paths_resolve else "FAIL"
    checks["summary"] = json.dumps(
        {"component_count": len(components), "state_counts": state_counts},
        sort_keys=True,
    )
    return checks, tuple(diagnostics)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    checks, diagnostics = check_current_target_map(root)
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
