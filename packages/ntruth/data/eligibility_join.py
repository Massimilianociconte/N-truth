"""Join per-source rights with corpus-native identity. Never writes GOLD."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Literal

from ntruth.data.identity import extract_stable_identity, identity_as_mapping
from ntruth.data.rights import (
    CANONICAL_SOURCES,
    evaluate_record_eligibility,
    rights_for_source,
)
from ntruth.data.schemas import CommonEnvelope
from ntruth.schemas.core import FrozenModel
from ntruth.task_corpora.authority import AuthorityLevel

SOURCE_PROCESSED_PATHS: dict[str, tuple[str, ...]] = {
    "SourceData": ("processed", "sourcedata", "v2.0.3", "multitask", "train", "records.jsonl"),
    "PreClinIE": (
        "processed",
        "preclinie",
        "f38df55a28505a77d30eefb5b867bbfdcc9baf25",
        "train",
        "records.jsonl",
    ),
    "MeasEval": (
        "processed",
        "measeval",
        "1fa738b6bc9b72c84c88a80344ca3ab39a310a44",
        "train",
        "records.jsonl",
    ),
    "CRAFT": ("processed", "craft", "v5.0.2", "train", "records.jsonl"),
}


class EligibilityJoinResult(FrozenModel):
    source: str
    record_id: str
    paper_id: str | None = None
    experiment_id: str | None = None
    family_id: str | None = None
    identity_complete: bool
    training_eligible: Literal[False] = False
    evaluation_eligible: Literal[False] = False
    authority_level: AuthorityLevel = AuthorityLevel.CANDIDATE
    gold_quantity: Literal[None] = None
    blockers: tuple[str, ...]


def join_envelope_eligibility(
    envelope: Mapping[str, Any] | CommonEnvelope,
) -> EligibilityJoinResult:
    if isinstance(envelope, CommonEnvelope):
        source = envelope.source.dataset
        record_id = envelope.record_id
        source_ref = envelope.source.commit or envelope.source.version
        asset = f"{source}@{envelope.source.version}"
        parsed = envelope
    else:
        source_obj = envelope.get("source")
        if not isinstance(source_obj, Mapping):
            raise ValueError("envelope source missing")
        source = str(source_obj.get("dataset") or "")
        record_id = str(envelope.get("record_id") or "")
        source_ref = str(source_obj.get("commit") or source_obj.get("version") or "")
        asset = f"{source}@{source_obj.get('version') or 'unknown'}"
        parsed = envelope
    if source not in CANONICAL_SOURCES:
        raise ValueError(f"unknown source for eligibility join: {source}")
    identity = extract_stable_identity(parsed, source_asset_id=asset, source_ref=source_ref)
    _eligible, blockers = evaluate_record_eligibility(
        source, identity=identity_as_mapping(identity)
    )
    del _eligible
    if AuthorityLevel.NTRUTH_GOLD in (identity.paper_id,):  # pragma: no cover - type guard
        raise ValueError("identity join cannot carry GOLD")
    return EligibilityJoinResult(
        source=source,
        record_id=record_id,
        paper_id=identity.paper_id,
        experiment_id=identity.experiment_id,
        family_id=identity.family_id,
        identity_complete=identity.complete(),
        blockers=blockers,
    )


def assert_join_not_gold(result: EligibilityJoinResult) -> None:
    if result.authority_level is AuthorityLevel.NTRUTH_GOLD:
        raise ValueError("eligibility join cannot write AuthorityLevel.NTRUTH_GOLD")
    if result.gold_quantity is not None:
        raise ValueError("eligibility join cannot invent GOLD quantity")
    if result.training_eligible or result.evaluation_eligible:
        raise ValueError("eligibility join cannot mark records eligible without human closure")


def iter_jsonl_envelopes(path: Path, *, limit: int | None = None) -> Iterable[dict[str, Any]]:
    count = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"non-object envelope in {path}")
            yield payload
            count += 1
            if limit is not None and count >= limit:
                return


def summarize_root_identity(
    dataset_root: Path,
    *,
    per_source_limit: int = 32,
) -> dict[str, Any]:
    """Observe FLASH128 identity recovery. Does not write training_ready or GOLD."""

    sources: dict[str, Any] = {}
    for source, parts in SOURCE_PROCESSED_PATHS.items():
        path = dataset_root.joinpath(*parts)
        rights = rights_for_source(source)
        recovered = {"paper": 0, "experiment": 0, "family": 0, "complete": 0, "scanned": 0}
        blockers: set[str] = set(rights.blockers)
        if path.is_file() and not path.is_symlink():
            for envelope in iter_jsonl_envelopes(path, limit=per_source_limit):
                result = join_envelope_eligibility(envelope)
                assert_join_not_gold(result)
                recovered["scanned"] += 1
                recovered["paper"] += int(result.paper_id is not None)
                recovered["experiment"] += int(result.experiment_id is not None)
                recovered["family"] += int(result.family_id is not None)
                recovered["complete"] += int(result.identity_complete)
                blockers.update(result.blockers)
        sources[source] = {
            "path_present": path.is_file(),
            "recovered": recovered,
            "eligible": 0,
            "blockers": sorted(blockers),
        }
    return {
        "dataset_root": str(dataset_root),
        "eligible_records": 0,
        "gold_records": 0,
        "writes_training_ready": False,
        "sources": sources,
    }
