#!/usr/bin/env python3
"""Genera un bundle pending dallo share-readiness di una revisione locale."""

from __future__ import annotations

import argparse
from pathlib import Path

from pydantic import ValidationError

from ntruth.governance.templates import pending_distribution_bundle
from ntruth.reporting import ShareReadiness


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Crea un template fail-closed; non autorizza ne trasferisce alcun asset."
    )
    parser.add_argument("revision_dir", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    source = args.revision_dir.expanduser() / "share-readiness.json"
    destination = args.out.expanduser()
    if destination.exists():
        parser.error(f"output gia esistente, non sovrascritto: {destination}")
    try:
        readiness = ShareReadiness.model_validate_json(source.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        parser.error(f"share-readiness non valido: {exc}")
    if not readiness.assets:
        parser.error("share-readiness senza asset: nessun template generato")

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        pending_distribution_bundle(readiness).model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Template pending scritto in {destination}; nessun uso e autorizzato.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
