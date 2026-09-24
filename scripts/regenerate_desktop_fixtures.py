"""Regenerate the desktop canonical Quick Design fixture from the Python lane.

The desktop client validates canonical responses against pinned conformance
checksums. Its test fixture must therefore come from the current backend, not
from a snapshot taken before an evaluator pin transition (the stale 0.1.0
fixture kept desktop tests green while the real guided preview failed).

Usage (repository root)::

    uv run python scripts/regenerate_desktop_fixtures.py          # rewrite
    uv run python scripts/regenerate_desktop_fixtures.py --check  # exit 1 on drift
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = (
    REPOSITORY_ROOT
    / "apps"
    / "desktop"
    / "src"
    / "test-fixtures"
    / "quick-design-v8-canonical.json"
)


def build_canonical_fixture() -> dict[str, Any]:
    """Run the canonical Python fixture through the current v8 lane."""

    for path in (REPOSITORY_ROOT / "packages", REPOSITORY_ROOT / "tests" / "unit"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    import test_prd_v8_quick_design as quick_design_fixture

    from ntruth.derivation_theory.runtime import load_runtime_bundle
    from ntruth.quick_design.v8 import run_quick_design_v8

    _, submission = quick_design_fixture._submission()
    result = run_quick_design_v8(submission, conformance_bundle=load_runtime_bundle())
    return {
        "response": result.model_dump(mode="json"),
        "submission": submission.model_dump(mode="json"),
    }


def render_fixture(fixture: dict[str, Any]) -> str:
    return json.dumps(fixture, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail instead of rewriting")
    args = parser.parse_args()
    rendered = render_fixture(build_canonical_fixture())
    current = FIXTURE_PATH.read_text(encoding="utf-8") if FIXTURE_PATH.exists() else ""
    if args.check:
        if current != rendered:
            print(f"DRIFT: {FIXTURE_PATH.relative_to(REPOSITORY_ROOT)} differs from the backend")
            return 1
        print("OK: desktop canonical fixture matches the backend")
        return 0
    FIXTURE_PATH.write_text(rendered, encoding="utf-8")
    print(f"rewrote {FIXTURE_PATH.relative_to(REPOSITORY_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
