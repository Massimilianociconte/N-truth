"""Contratti degli artefatti riproducibili di release."""

import importlib.util
import io
import tarfile
import zipfile
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


_distribution_script = _load_distribution_script()
check_sdist = _distribution_script.check_sdist
check_wheel = _distribution_script.check_wheel


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


def _write_sdist(
    path: Path,
    extra_name: str | None = None,
    *,
    include_evaluator_registry: bool = True,
) -> None:
    required = [
        "ntruth-0.1.0/pyproject.toml",
        "ntruth-0.1.0/apps/desktop/dist/index.html",
        "ntruth-0.1.0/apps/desktop/dist/assets/app.js",
        "ntruth-0.1.0/theories/ntruth-derivation-theory-0.1.0.json",
        "ntruth-0.1.0/theories/simple-cell-culture-profile-closure-0.1.0.json",
        "ntruth-0.1.0/rulesets/ntruth-v8-core-0.1.0.json",
        ("ntruth-0.1.0/packages/ntruth/conformance/assets/reference-role-registry-0.1.0.json"),
        (
            "ntruth-0.1.0/packages/ntruth/conformance/assets/"
            "implementation-conformance-fixtures-simple-cell-culture-0.1.0.json"
        ),
        (
            "ntruth-0.1.0/packages/ntruth/conformance/assets/"
            "prd-v8-example-conformance-registry-8.0.0.json"
        ),
        "ntruth-0.1.0/packages/ntruth/schemas/assets/prd-v8-kernel-schemas-8.0.0.json",
    ]
    if include_evaluator_registry:
        required.append("ntruth-0.1.0/theories/reviewed-evaluator-registry-0.1.1.json")
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
        "models/local/model.gguf",
        "other/adapter.safetensors",
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


def test_sdist_rejects_missing_reviewed_evaluator_registry(tmp_path: Path) -> None:
    sdist = tmp_path / "ntruth.tar.gz"
    _write_sdist(sdist, include_evaluator_registry=False)

    with pytest.raises(ValueError, match="reviewed-evaluator-registry"):
        check_sdist(sdist)


def test_wheel_rejects_missing_prd_v8_conformance_bundle(tmp_path: Path) -> None:
    """Catches a release wheel that cannot reproduce checkout conformance."""

    wheel = tmp_path / "ntruth-0.1.0-py3-none-any.whl"
    baseline_names = (
        "ntruth/_ui/index.html",
        "ntruth/_ui/assets/app.js",
        "ntruth/_ui/assets/app.css",
        "ntruth/_bundled/models/qwen3-4b-instruct-2507-mlx-qlora.json",
        "ntruth/_bundled/rulesets/ntruth-core-0.1.0.json",
        "ntruth/_bundled/ontology/ntruth-core-0.1.0.json",
    )
    with zipfile.ZipFile(wheel, "w") as archive:
        for name in baseline_names:
            archive.writestr(name, "fixture")

    with pytest.raises(ValueError, match=r"ntruth-derivation-theory-0\.1\.0\.json"):
        check_wheel(wheel)


def test_wheel_rejects_missing_reviewed_evaluator_registry(tmp_path: Path) -> None:
    wheel = tmp_path / "ntruth-0.1.0-py3-none-any.whl"
    required_except_registry = (
        "ntruth/_ui/index.html",
        "ntruth/_ui/assets/app.js",
        "ntruth/_ui/assets/app.css",
        "ntruth/_bundled/models/qwen3-4b-instruct-2507-mlx-qlora.json",
        "ntruth/_bundled/theories/ntruth-derivation-theory-0.1.0.json",
        "ntruth/_bundled/theories/simple-cell-culture-profile-closure-0.1.0.json",
        "ntruth/_bundled/rulesets/ntruth-v8-core-0.1.0.json",
        "ntruth/_bundled/ontology/ntruth-core-0.1.0.json",
        "ntruth/conformance/assets/reference-role-registry-0.1.0.json",
        (
            "ntruth/conformance/assets/"
            "implementation-conformance-fixtures-simple-cell-culture-0.1.0.json"
        ),
    )
    with zipfile.ZipFile(wheel, "w") as archive:
        for name in required_except_registry:
            archive.writestr(name, "fixture")

    with pytest.raises(ValueError, match="reviewed-evaluator-registry"):
        check_wheel(wheel)
