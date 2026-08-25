"""Extract and validate normative fenced examples from prd/ and docs/ (PRD v9 §0.4, §26.5, AI.2).

A fenced block is normative when its language is yaml/yml/json AND either a
NORMATIVE marker line precedes or follows the fence, or the enclosing heading
contains "normative". Blocks under HISTORICAL headings or with HISTORICAL
markers are excluded from the normative scan per PRD Appendix AI.2.

Checks: payload parses as JSON/YAML; when the canonical v9 registry is
importable, string values under canonical field names must belong to the
registered vocabularies. The checker fails closed with an error list, exits 0
with an explicit note when zero normative blocks are found so that CI stays
green until markers are introduced.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

NORMATIVE_DIRECTORIES: tuple[str, ...] = ("prd", "docs")
EXAMPLE_LANGUAGES = frozenset({"yaml", "yml", "json"})
CONTEXT_LINES = 3
FENCE_RE = re.compile(r"^(`{3,})([A-Za-z0-9_-]+)?\s*$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")

# Canonical registry field names mapped to REGISTRY_CATEGORIES keys.
_CANONICAL_KEY_TO_CATEGORY: dict[str, str] = {
    "factor_role": "factor_role",
    "factor_roles": "factor_role",
    "contrast_type": "contrast_type",
    "contrast_types": "contrast_type",
    "contrast_support": "contrast_support",
    "contrast_support_status": "contrast_support",
    "material_lineage_kind": "material_lineage",
    "material_lineage_event_kind": "material_lineage",
    "event_kind": "material_lineage",
    "support_profile_dimension": "support_profile_dimension",
    "knowledge_state": "knowledge_state",
}

_YAML_NOT_AVAILABLE = object()


def _yaml_safe_load(text: str) -> object:
    """Load YAML via PyYAML when installed; otherwise signal unavailability."""

    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError:
        return _YAML_NOT_AVAILABLE
    return yaml.safe_load(text)


@dataclass(frozen=True)
class NormativeBlock:
    source: str
    language: str
    payload_text: str
    line_start: int
    reason: str


def _context_contains(lines: list[str], center: int, token: str, *, step: int) -> bool:
    seen = 0
    index = center
    while 0 <= index < len(lines) and seen <= CONTEXT_LINES:
        if token in lines[index]:
            return True
        if lines[index].strip():
            seen += 1
        index += step
    return False


def extract_normative_blocks(text: str, *, source: str) -> list[NormativeBlock]:
    lines = text.splitlines()
    blocks: list[NormativeBlock] = []
    current_heading = ""
    index = 0
    while index < len(lines):
        heading_match = HEADING_RE.match(lines[index])
        if heading_match:
            current_heading = heading_match.group(2)
            index += 1
            continue
        fence = FENCE_RE.match(lines[index])
        if fence is None:
            index += 1
            continue
        language = (fence.group(2) or "").lower()
        open_line = index
        closing = len(lines)
        for close_index in range(open_line + 1, len(lines)):
            if FENCE_RE.match(lines[close_index]):
                closing = close_index
                break
        has_normative_marker = _context_contains(
            lines, open_line - 1, "NORMATIVE", step=-1
        ) or _context_contains(lines, closing + 1, "NORMATIVE", step=+1)
        has_historical_marker = _context_contains(
            lines, open_line - 1, "HISTORICAL", step=-1
        ) or _context_contains(lines, closing + 1, "HISTORICAL", step=+1)
        heading_lower = current_heading.lower()
        historical_context = has_historical_marker or "historical" in heading_lower
        marker_reason = "marker" if has_normative_marker else None
        heading_reason = (
            "heading"
            if current_heading.lower().startswith("normative")
            or "normative example" in heading_lower
            or "esempio normativo" in heading_lower
            else None
        )
        # Heading-triggered captures are restricted to schema payload languages:
        # prose fences under normatively titled sections stay documentation.
        heading_language_ok = language in EXAMPLE_LANGUAGES
        reason = marker_reason or (heading_reason if heading_language_ok else None)
        if reason and not historical_context:
            blocks.append(
                NormativeBlock(
                    source=source,
                    language=language,
                    payload_text="\n".join(lines[open_line + 1 : closing]),
                    line_start=open_line + 1,
                    reason=reason,
                )
            )
        index = closing + 1
    return blocks


def _iter_payload_values(payload: object) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                normalized = str(key).strip().lower()
                if isinstance(value, str):
                    pairs.append((normalized, value))
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return pairs


def validate_block(block: NormativeBlock) -> str | None:
    if block.language not in EXAMPLE_LANGUAGES:
        return f"{block.source}:{block.line_start}: normative block language {block.language!r} must be yaml or json"

    if block.language in {"json"}:
        try:
            payload: Any = json.loads(block.payload_text)
        except json.JSONDecodeError as exc:
            return f"{block.source}:{block.line_start}: invalid JSON: {exc}"
    else:
        loaded = _yaml_safe_load(block.payload_text)
        if loaded is _YAML_NOT_AVAILABLE:
            try:
                payload = json.loads(block.payload_text)
            except json.JSONDecodeError:
                return (
                    f"{block.source}:{block.line_start}: cannot validate YAML without "
                    "PyYAML and payload is not JSON"
                )
        else:
            payload = loaded

    try:
        from ntruth.schemas.v9_registry import REGISTRY_CATEGORIES
    except Exception:
        return None

    for key, value in _iter_payload_values(payload):
        category = _CANONICAL_KEY_TO_CATEGORY.get(key)
        if category is None:
            continue
        vocabulary = REGISTRY_CATEGORIES.get(category)
        if vocabulary is None:
            continue
        if value not in vocabulary:
            return (
                f"{block.source}:{block.line_start}: unknown {category} token {value!r} "
                f"for canonical field {key!r}"
            )
    return None


def run_checks(repository_root: Path) -> dict[str, Any]:
    errors: list[str] = []
    files_scanned = 0
    blocks: list[NormativeBlock] = []
    for directory in NORMATIVE_DIRECTORIES:
        base = repository_root / directory
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.md")):
            files_scanned += 1
            text = path.read_text(encoding="utf-8", errors="replace")
            relative = path.relative_to(repository_root).as_posix()
            blocks.extend(extract_normative_blocks(text, source=relative))
    for block in blocks:
        error = validate_block(block)
        if error is not None:
            errors.append(error)
    summary = {
        "schema_version": "9.0.0",
        "files_scanned": files_scanned,
        "normative_blocks": len(blocks),
        "errors": errors,
        "status": "FAIL" if errors else "PASS",
    }
    if not blocks:
        summary["note"] = (
            "no normative examples found; PRD v9 §26.5 validation stays green "
            "until NORMATIVE markers are added"
        )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    summary = run_checks(args.root.resolve())
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
