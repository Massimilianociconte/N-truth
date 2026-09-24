#!/usr/bin/env python3
"""Rigenera in locale i payload sintetici spostati fuori dal tracciamento Git.

Repository policy (scripts/check_repository_policy.py) impedisce di tracciare
payload con semantica corpus. I file restano quindi fuori dall'indice e questa
utilità li ricostruisce ai percorsi canonici usando le fabbriche deterministiche
esistenti:

- ``benchmarks/fewshot_p0/cases.jsonl`` — byte-stabile: la fabbrica
  ``ntruth.training.fewshot_p0_fixtures.write_fixture_suite`` riproduce
  esattamente i byte storicamente pubblicati (verificabile con --verify).
- ``data/training/p0-alpha`` snapshot sintetico — la fabbrica
  ``ntruth.training.p0_synthetic.write_snapshot`` è parametrica (seed fisso)
  ma l'ordine interno delle famiglie non è canonizzato: il risultato rispetta
  gli stessi contratti e gate anti-DEV, però NON riproduce necessariamente i
  byte dello snapshot congelato SYN_G1_UNANCHORED del 2026-08-02. Una
  rigenerazione produce un NUOVO snapshot locale; i checksum freschi vengono
  stampati e riscritti nel manifest dallo snapshot writer stesso.

I payload sintetici NON sono gold corpus e nessun artefatto prodotto qui è
validazione scientifica o autorizzazione di training.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# sha256 dei payload congelati del 2026-08-02 (SYN_G1_UNANCHORED): riferimenti
# di confronto, NON attestazioni di autenticità.
FROZEN_P0_ALPHA_SHA256 = {
    "train.jsonl": "80534c15f6b11a39e3c7f4d203d1375c3e7a62367526e20e35b9cc3517969679",
    "validation.jsonl": "0477a189bcd1e66a01a5e53299a1ffa84a3997efc50216bbfbb52e373c1ac624",
    "train.chat.jsonl": "423a56d2a38f27d5ef1b0b41383c58c0485f78a1c0d95de8ffb875e6ed0110fb",
    "validation.chat.jsonl": "f162c9b815773a5a9cc3728e25a343f4a4f2ecf575afa937ebfa6c87f0272cb9",
}
EXPECTED_FEWSHOT_CASES_SHA256 = "54e3f6b81d385b1b7a3058438cef79a7d18c068a5db419fbbb968ed4b742b64a"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def regenerate_fewshot(*, verify: bool) -> int:
    from ntruth.training.fewshot_p0_fixtures import write_fixture_suite

    out = REPO / "benchmarks" / "fewshot_p0"
    tracked_manifest = out / "manifest.json"
    # Il manifest tracciato porta chiavi di governance scritte a mano che la
    # fabbrica non genera: va preservato byte-per-byte durante la ricostruzione.
    preserved_manifest = tracked_manifest.read_bytes() if tracked_manifest.is_file() else None
    write_fixture_suite(out)
    if preserved_manifest is not None:
        tracked_manifest.write_bytes(preserved_manifest)
        print("preserved existing benchmarks/fewshot_p0/manifest.json byte-for-byte")
    observed = _sha256(out / "cases.jsonl")
    print(f"fewshot cases.jsonl sha256: {observed}")
    if verify and observed != EXPECTED_FEWSHOT_CASES_SHA256:
        print(
            "byte mismatch against published reference "
            f"{EXPECTED_FEWSHOT_CASES_SHA256}; suite was NOT regenerated identically",
            file=sys.stderr,
        )
        return 1
    print("fewshot suite rebuilt at canonical path")
    return 0


def regenerate_p0_alpha() -> int:
    from ntruth.training.p0_synthetic import write_snapshot

    out = REPO / "data" / "training" / "p0-alpha"
    dev_cases = REPO / "benchmarks" / "fewshot_p0" / "cases.jsonl"
    if not dev_cases.is_file():
        print(
            f"missing anti-leakage input {dev_cases}: run --suite fewshot first",
            file=sys.stderr,
        )
        return 1
    manifest = write_snapshot(out, n_train=2000, n_val=300, seed=13, dev_cases_path=dev_cases)
    if not manifest["quality_gate"]["passed"]:
        print("quality gate failed on regenerated snapshot", file=sys.stderr)
        return 1
    print(json.dumps({"renderer_version": manifest["renderer_version"], "seed": manifest["seed"]}))
    for name, frozen in FROZEN_P0_ALPHA_SHA256.items():
        path = out / name
        observed = _sha256(path)
        marker = "matches-frozen" if observed == frozen else "differs-from-frozen"
        print(f"{name} sha256: {observed} ({marker})")
    print("snapshot rebuilt at data/training/p0-alpha; manifest.json checksums refreshed by writer")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("fewshot", "p0-alpha", "all"), default="all")
    parser.add_argument("--verify", action="store_true", help="assert byte equality where proven")
    args = parser.parse_args()
    if args.suite in ("fewshot", "all"):
        rc = regenerate_fewshot(verify=args.verify)
        if rc != 0:
            return rc
    if args.suite in ("p0-alpha", "all"):
        return regenerate_p0_alpha()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
