"""Contratti leggeri per il release smoke test isolato."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_smoke_script() -> ModuleType:
    script = Path(__file__).resolve().parents[2] / "scripts" / "smoke_release.py"
    spec = importlib.util.spec_from_file_location("ntruth_smoke_release", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


smoke_release = _load_smoke_script()


def test_discover_distributions_requires_one_wheel_and_one_sdist(tmp_path: Path) -> None:
    wheel = tmp_path / "ntruth-0.1.0-py3-none-any.whl"
    sdist = tmp_path / "ntruth-0.1.0.tar.gz"
    wheel.touch()
    sdist.touch()

    distributions = smoke_release.discover_distributions(tmp_path)

    assert [(item.kind, item.path) for item in distributions] == [
        ("wheel", wheel),
        ("sdist", sdist),
    ]


@pytest.mark.parametrize("missing", ["wheel", "sdist"])
def test_discover_distributions_rejects_missing_artifact(tmp_path: Path, missing: str) -> None:
    if missing != "wheel":
        (tmp_path / "ntruth-0.1.0-py3-none-any.whl").touch()
    if missing != "sdist":
        (tmp_path / "ntruth-0.1.0.tar.gz").touch()

    with pytest.raises(ValueError, match="Attes"):
        smoke_release.discover_distributions(tmp_path)


def test_cli_contract_rejects_incomplete_bundled_ruleset() -> None:
    version = "N-Truth 0.1.0 · schema 0.2.0"
    rules = "\n".join(
        [
            "ntruth-core@0.1.0 — 2 regole (checksum abcdef1234)",
            "  GEN-001   [info] general Prima regola",
        ]
    )

    with pytest.raises(RuntimeError, match="Ruleset installato incompleto"):
        smoke_release.assert_cli_contract(version, rules)


def test_clean_environment_makes_offline_mode_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UV_OFFLINE", "inherited")

    online = smoke_release.clean_environment(offline=False)
    offline = smoke_release.clean_environment(offline=True)

    assert "UV_OFFLINE" not in online
    assert offline["UV_OFFLINE"] == "1"
