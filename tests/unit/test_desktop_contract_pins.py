"""The desktop client and its fixtures must track the backend conformance pins.

Regression for the stale client pins found on 2026-09-23: the desktop parser
still accepted only the evaluator-registry 0.1.0 checksums, so every real guided
preview failed with "malformed PRD v8 build response" while desktop tests stayed
green on a 0.1.0 fixture.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

from ntruth.derivation_theory.runtime import load_runtime_bundle
from ntruth.schemas.core import content_checksum

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
API_TS = REPOSITORY_ROOT / "apps" / "desktop" / "src" / "api.ts"
SCRIPT = REPOSITORY_ROOT / "scripts" / "regenerate_desktop_fixtures.py"


def _client_asset_pins() -> dict[str, str]:
    text = API_TS.read_text(encoding="utf-8")
    block = re.search(r"REVIEWED_CONFORMANCE_ASSET_PINS = \{(?P<body>.*?)\} as const", text, re.S)
    assert block is not None, "REVIEWED_CONFORMANCE_ASSET_PINS not found in api.ts"
    return dict(re.findall(r'(\w+): "([0-9a-f]{64})"', block.group("body")))


def _client_bundle_checksum() -> str:
    text = API_TS.read_text(encoding="utf-8")
    match = re.search(r'REVIEWED_CONFORMANCE_BUNDLE_CHECKSUM =\s*"([0-9a-f]{64})"', text)
    assert match is not None, "REVIEWED_CONFORMANCE_BUNDLE_CHECKSUM not found in api.ts"
    return match.group(1)


def test_client_asset_pins_match_the_backend_bundle() -> None:
    bundle = load_runtime_bundle()
    backend = {
        "theory": bundle.theory.declared_checksum,
        "rulebook": bundle.rulebook.declared_checksum,
        "profile_closure": bundle.profile_closure.declared_checksum,
        "reference_registry": bundle.reference_registry.declared_checksum,
        "fixture_set": bundle.fixture_set.declared_checksum,
        "evaluator_registry": bundle.evaluator_registry.declared_checksum,
    }
    assert _client_asset_pins() == backend


def test_client_bundle_checksum_matches_the_backend_bundle() -> None:
    bundle = load_runtime_bundle()
    assert _client_bundle_checksum() == content_checksum(bundle.model_dump(mode="json"))


def test_desktop_canonical_fixture_is_regenerated_from_the_backend() -> None:
    spec = importlib.util.spec_from_file_location("regenerate_desktop_fixtures", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("regenerate_desktop_fixtures", module)
    spec.loader.exec_module(module)
    expected = module.render_fixture(module.build_canonical_fixture())
    current = module.FIXTURE_PATH.read_text(encoding="utf-8")
    assert current == expected, (
        "apps/desktop fixture drifted from the backend: run "
        "`uv run python scripts/regenerate_desktop_fixtures.py`"
    )
