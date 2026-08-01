"""Generazione deterministica dell'SBOM CycloneDX dai lockfile uv e pnpm.

Il modulo non interroga la rete. Le licenze non presenti nei lockfile restano
intenzionalmente assenti: non vengono indovinate e richiedono una review di release.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import tomllib
from pathlib import Path
from typing import Any


def _component(package: dict[str, Any]) -> dict[str, Any]:
    name = str(package["name"])
    version = str(package["version"])
    component: dict[str, Any] = {
        "type": "library",
        "bom-ref": f"pkg:pypi/{name}@{version}",
        "name": name,
        "version": version,
        "purl": f"pkg:pypi/{name}@{version}",
    }
    source = package.get("source") or {}
    if "editable" in source:
        component["type"] = "application"
    hashes = sorted(
        {
            wheel.get("hash", "").removeprefix("sha256:")
            for wheel in package.get("wheels", [])
            if wheel.get("hash", "").startswith("sha256:")
        }
    )
    if hashes:
        component["hashes"] = [{"alg": "SHA-256", "content": value} for value in hashes]
    return component


def _pnpm_components(lock_path: Path) -> list[dict[str, Any]]:
    """Legge la sezione ``packages`` di pnpm senza dipendenze YAML runtime."""

    lines = lock_path.read_text(encoding="utf-8").splitlines()
    in_packages = False
    current_key: str | None = None
    integrity_by_key: dict[str, str] = {}
    for line in lines:
        if line == "packages:":
            in_packages = True
            continue
        if in_packages and line and not line.startswith(" "):
            break
        if not in_packages:
            continue
        if line.startswith("  ") and not line.startswith("    ") and line.endswith(":"):
            current_key = line.strip()[:-1].strip("'").strip('"')
            integrity_by_key.setdefault(current_key, "")
            continue
        marker = "integrity: sha512-"
        if current_key is not None and marker in line:
            integrity_by_key[current_key] = line.split(marker, 1)[1].rstrip("}").strip()

    components: list[dict[str, Any]] = []
    for key, encoded_hash in sorted(integrity_by_key.items()):
        separator = key.rfind("@")
        if separator <= 0 or separator == len(key) - 1:
            continue
        name = key[:separator]
        version = key[separator + 1 :]
        purl_name = name.replace("@", "%40", 1) if name.startswith("@") else name
        purl = f"pkg:npm/{purl_name}@{version}"
        component: dict[str, Any] = {
            "type": "library",
            "bom-ref": purl,
            "name": name,
            "version": version,
            "purl": purl,
        }
        if encoded_hash:
            try:
                digest = base64.b64decode(encoded_hash, validate=True).hex()
            except ValueError:
                digest = ""
            if digest:
                component["hashes"] = [{"alg": "SHA-512", "content": digest}]
        components.append(component)
    return components


def build_sbom(lock_path: Path, pnpm_lock_path: Path | None = None) -> dict[str, Any]:
    """Costruisce un documento CycloneDX stabile dai lockfile locali."""

    raw = lock_path.read_bytes()
    lock = tomllib.loads(raw.decode("utf-8"))
    packages = sorted(
        lock.get("package", []), key=lambda package: (package["name"], package["version"])
    )
    components = [_component(package) for package in packages]
    refs = {component["name"]: component["bom-ref"] for component in components}
    dependencies: list[dict[str, Any]] = []
    for package in packages:
        ref = refs.get(str(package["name"]))
        if ref is None:
            continue
        depends_on = sorted(
            {
                refs[name]
                for dependency in package.get("dependencies", [])
                if (name := str(dependency["name"])) in refs
            }
        )
        dependencies.append({"ref": ref, "dependsOn": depends_on})

    lock_hash = hashlib.sha256(raw).hexdigest()
    pnpm_raw = pnpm_lock_path.read_bytes() if pnpm_lock_path is not None else b""
    pnpm_hash = hashlib.sha256(pnpm_raw).hexdigest() if pnpm_raw else "not-included"
    if pnpm_lock_path is not None:
        npm_components = _pnpm_components(pnpm_lock_path)
        components.extend(npm_components)
        dependencies.extend(
            {"ref": component["bom-ref"], "dependsOn": []} for component in npm_components
        )
    serial_hash = hashlib.sha256(raw + b"\0" + pnpm_raw).hexdigest()
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": (
            f"urn:uuid:{serial_hash[:8]}-{serial_hash[8:12]}-5{serial_hash[13:16]}-"
            f"8{serial_hash[17:20]}-{serial_hash[20:32]}"
        ),
        "version": 1,
        "metadata": {
            "tools": {
                "components": [
                    {
                        "type": "application",
                        "name": "ntruth-lockfile-sbom",
                        "version": "1",
                    }
                ]
            },
            "properties": [
                {"name": "ntruth:uv-lock-sha256", "value": lock_hash},
                {"name": "ntruth:pnpm-lock-sha256", "value": pnpm_hash},
                {"name": "ntruth:network-used", "value": "false"},
                {
                    "name": "ntruth:scope",
                    "value": "complete-development-lockfiles-not-runtime-only",
                },
            ],
        },
        "components": components,
        "dependencies": dependencies,
    }


def render(payload: dict[str, Any]) -> str:
    """Serializza l'SBOM in forma deterministica con newline finale."""

    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    """Entry point condiviso dal wrapper ``scripts/generate_sbom.py``."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, default=Path("uv.lock"))
    parser.add_argument(
        "--pnpm-lock",
        type=Path,
        default=Path("apps/desktop/pnpm-lock.yaml"),
    )
    parser.add_argument("--check", type=Path)
    parser.add_argument("--out", type=Path, default=Path("sbom.cdx.json"))
    args = parser.parse_args()
    if not args.lock.is_file():
        parser.error(f"lockfile assente: {args.lock}")
    pnpm_lock = args.pnpm_lock if args.pnpm_lock.is_file() else None
    expected = render(build_sbom(args.lock, pnpm_lock))
    if args.check:
        actual = args.check.read_text(encoding="utf-8") if args.check.is_file() else ""
        if actual != expected:
            print(f"SBOM non aggiornato: rigenerare {args.check}", file=sys.stderr)
            return 1
        return 0
    args.out.write_text(expected, encoding="utf-8")
    return 0
