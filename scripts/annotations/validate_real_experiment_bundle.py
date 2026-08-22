#!/usr/bin/env python3
"""Valida un Real Experiment Bundle (reality check P0) contro lo schema JSON.

Non promuove gold. Fallisce se training_eligible o gold sono true.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA = (
    REPO
    / "data"
    / "annotations"
    / "reality-check"
    / "schemas"
    / "real_experiment_bundle.schema.json"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="Path to bundle.json")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    args = parser.parse_args()

    try:
        import jsonschema
    except ImportError:
        # fallback: structural checks without jsonschema package
        return _fallback_validate(args.bundle)

    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    instance = json.loads(args.bundle.read_text(encoding="utf-8"))
    try:
        jsonschema.validate(instance=instance, schema=schema)
    except jsonschema.ValidationError as exc:
        print(f"INVALID: {exc.message}", file=sys.stderr)
        print(f"path: {list(exc.absolute_path)}", file=sys.stderr)
        return 1

    # Extra policy gates
    if instance.get("gold") is not False:
        print("INVALID: gold must be false in reality-check phase", file=sys.stderr)
        return 1
    if instance.get("training_eligible") is not False:
        print(
            "INVALID: training_eligible must be false until separate promotion",
            file=sys.stderr,
        )
        return 1
    if (
        instance.get("evaluation_eligible") is True
        and instance.get("annotation_phase") == "internal_trial_3_5"
    ):
        print(
            "INVALID: internal trial bundles must keep evaluation_eligible=false",
            file=sys.stderr,
        )
        return 1
    if not instance.get("guideline_version") or not instance.get("schema_version"):
        print("INVALID: guideline_version and schema_version required", file=sys.stderr)
        return 1
    if (
        instance.get("bundle_role") == "INTERNAL_REALITY_CHECK"
        and instance.get("review_status") is None
    ):
        print("INVALID: review_status required for INTERNAL_REALITY_CHECK", file=sys.stderr)
        return 1
    bad_hash = "0" * 64
    for src in instance.get("sources") or []:
        if src.get("sha256") == bad_hash:
            print(
                f"WARN: source {src.get('source_id')} still has placeholder sha256",
                file=sys.stderr,
            )
        if src.get("immutable") is False:
            print(
                f"WARN: source {src.get('source_id')} immutable=false "
                "(prefer new file+hash instead of rewrite)",
                file=sys.stderr,
            )

    out = {
        "valid": True,
        "bundle_id": instance.get("bundle_id"),
        "bundle_role": instance.get("bundle_role"),
        "annotation_phase": instance.get("annotation_phase"),
        "annotation_status": instance.get("annotation_status"),
        "review_status": instance.get("review_status"),
        "guideline_version": instance.get("guideline_version"),
        "schema_version": instance.get("schema_version"),
        "blocks": len(instance.get("experiment_blocks") or []),
        "gold": instance.get("gold"),
        "training_eligible": instance.get("training_eligible"),
        "evaluation_eligible": instance.get("evaluation_eligible"),
        "source_origin": instance.get("source_origin"),
        "reality_check_class": instance.get("reality_check_class"),
        "real_anchor_eligible": instance.get("real_anchor_eligible"),
    }
    if instance.get("reality_check_class") == "PROTOCOL_DRY_RUN":
        out["note"] = "PROTOCOL_DRY_RUN: protocol stress-test only; not real anchor"
    if instance.get("real_anchor_eligible") is False:
        out["real_anchor_eligible"] = False
    print(json.dumps(out, indent=2))
    return 0


def _fallback_validate(bundle_path: Path) -> int:
    data = json.loads(bundle_path.read_text(encoding="utf-8"))
    required = [
        "schema_version",
        "bundle_id",
        "annotation_phase",
        "annotation_status",
        "gold",
        "training_eligible",
        "provenance",
        "sources",
        "experiment_blocks",
        "primary_annotator",
        "guideline_version",
    ]
    missing = [k for k in required if k not in data]
    if missing:
        print(f"INVALID missing keys: {missing}", file=sys.stderr)
        return 1
    if data.get("gold") is not False or data.get("training_eligible") is not False:
        print("INVALID: gold and training_eligible must be false", file=sys.stderr)
        return 1
    if data.get("schema_version") != "0.1.0":
        print("INVALID: schema_version must be 0.1.0", file=sys.stderr)
        return 1
    if not data.get("sources") or not data.get("experiment_blocks"):
        print("INVALID: sources and experiment_blocks required", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "valid": True,
                "mode": "fallback_no_jsonschema",
                "bundle_id": data.get("bundle_id"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
