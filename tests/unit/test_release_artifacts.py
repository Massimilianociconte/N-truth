"""Contratti degli artefatti riproducibili di release."""

import importlib.util
import io
import tarfile
from pathlib import Path
from types import ModuleType

import pytest

from ntruth.release.sbom import build_sbom, render


def _load_distribution_script() -> ModuleType:
    script = Path(__file__).resolve().parents[2] / "scripts" / "check_distribution.py"
    spec = importlib.util.spec_from_file_location("ntruth_check_distribution", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_sdist = _load_distribution_script().check_sdist


def test_sbom_combines_python_and_frontend_lockfiles(tmp_path: Path) -> None:
    uv_lock = tmp_path / "uv.lock"
    uv_lock.write_text(
        """version = 1
revision = 3
requires-python = \">=3.12\"

[[package]]
name = \"ntruth\"
version = \"0.1.0\"
source = { editable = \".\" }
""",
        encoding="utf-8",
    )
    pnpm_lock = tmp_path / "pnpm-lock.yaml"
    pnpm_lock.write_text(
        """lockfileVersion: '9.0'

packages:

  '@scope/example@2.1.0':
    resolution: {integrity: sha512-YWJj}

  react@19.2.8:
    resolution: {integrity: sha512-ZGVm}

snapshots:
""",
        encoding="utf-8",
    )

    payload = build_sbom(uv_lock, pnpm_lock)
    by_ref = {item["bom-ref"]: item for item in payload["components"]}

    assert "pkg:pypi/ntruth@0.1.0" in by_ref
    assert "pkg:npm/%40scope/example@2.1.0" in by_ref
    assert by_ref["pkg:npm/react@19.2.8"]["hashes"] == [{"alg": "SHA-512", "content": "646566"}]
    properties = {item["name"]: item["value"] for item in payload["metadata"]["properties"]}
    assert properties["ntruth:pnpm-lock-sha256"] != "not-included"
    assert properties["ntruth:scope"] == "complete-development-lockfiles-not-runtime-only"
    assert render(payload).endswith("\n")


def _write_sdist(path: Path, extra_name: str | None = None) -> None:
    required = [
        "ntruth-0.1.0/pyproject.toml",
        "ntruth-0.1.0/apps/desktop/dist/index.html",
        "ntruth-0.1.0/apps/desktop/dist/assets/app.js",
    ]
    if extra_name:
        required.append(f"ntruth-0.1.0/{extra_name}")
    with tarfile.open(path, "w:gz") as archive:
        for name in required:
            payload = b"fixture"
            info = tarfile.TarInfo(name=name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))


@pytest.mark.parametrize(
    "forbidden",
    [
        ".hypothesis/examples/cache",
        "packages/ntruth/__pycache__/core.cpython-312.pyc",
        "local-data/raw/private.xml",
        "data/raw/corpus.jsonl",
        "models/checkpoints/model.safetensors",
        ".env.local",
        "certificate.pem",
    ],
)
def test_sdist_rejects_local_or_sensitive_assets(tmp_path: Path, forbidden: str) -> None:
    sdist = tmp_path / "ntruth.tar.gz"
    _write_sdist(sdist, forbidden)

    with pytest.raises(ValueError, match="locali o sensibili"):
        check_sdist(sdist)


def test_sdist_accepts_public_reproducible_assets(tmp_path: Path) -> None:
    sdist = tmp_path / "ntruth.tar.gz"
    _write_sdist(sdist)

    check_sdist(sdist)
