"""SourceData-NLP multitask → canonical entity_roles task corpus."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Literal, cast

from ntruth.data.fs import is_ignorable_metadata, sha256_file
from ntruth.task_corpora.authority import (
    AuthorityLevel,
    ExclusionReason,
    SupervisionSource,
)
from ntruth.task_corpora.config import (
    DEFAULT_ALLOWED_USES,
    DEFAULT_SEED,
    FORBIDDEN_GOLD_USES,
    RECORDS_SHA256_C1_INITIAL,
    RECORDS_SHA256_C1_USE_DECISION,
    ROOT_REALITY_GATE_REF,
    SCHEMA_VERSION,
    TASK_ENTITY_ROLES,
    TRANSFORM_VERSION,
    package_dir,
    task_output_dir,
)
from ntruth.task_corpora.io_util import (
    record_checksum,
    records_content_sha256,
    write_json,
    write_jsonl_records,
)
from ntruth.task_corpora.license_loader import (
    adapter_build_permitted,
    evaluation_permitted,
    load_license_decision,
    training_permitted,
)
from ntruth.task_corpora.readiness import project_sourcedata_c0_c1
from ntruth.task_corpora.schemas import (
    BuildManifest,
    EntityRolesPayload,
    ExclusionRecord,
    LicenseUseDecision,
    SourceIdentity,
    TaskRecord,
    TransformLineage,
)
from ntruth.task_corpora.validate import (
    assert_bio_tags_known,
    assert_token_label_lengths,
    count_groups_crossing_splits,
)

ADAPTER_NAME = "sourcedata_entity_roles"
MAPPING_VERSION = "0.1.0"
SplitName = Literal["train", "validation", "test", "trial"]


def load_label_map() -> dict[str, Any]:
    path = package_dir() / "label_maps" / "sourcedata_entity_roles.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _source_multitask_dir(root: Path) -> Path:
    return root / "training_ready" / "sourcedata_multitask"


def _map_tag(tag: str, allowed_types: set[str], mapping: dict[str, str]) -> str | None:
    if tag == "O":
        return "O"
    if tag not in mapping:
        return None
    if "-" in tag:
        typ = tag.split("-", 1)[1]
        if typ not in allowed_types:
            return None
    return mapping[tag]


def convert_source_record(
    rec: dict[str, Any],
    *,
    split: SplitName,
    source_path: str,
    parent_sha: str,
    license_decision: LicenseUseDecision,
    label_map: dict[str, Any],
    line_no: int,
) -> tuple[TaskRecord | None, ExclusionRecord | None]:
    payload = rec.get("payload") or {}
    tokens = list(payload.get("tokens") or [])
    entity_tags = list(payload.get("entity_tags") or [])
    role_tags = list(payload.get("role_tags") or [])

    try:
        assert_token_label_lengths(tokens, entity_tags, role_tags)
    except Exception as exc:
        return None, ExclusionRecord(
            source_path=source_path,
            source_record_id=rec.get("record_id"),
            reason=ExclusionReason.TOKEN_LABEL_LENGTH_MISMATCH.value,
            detail=str(exc),
            split=split,
        )

    entity_types = set(label_map["entity_types"])
    role_types = set(label_map["role_types"])
    mapping: dict[str, str] = label_map["source_to_canonical"]

    unknown_e = assert_bio_tags_known(entity_tags, entity_types)
    unknown_r = assert_bio_tags_known(role_tags, role_types)
    if unknown_e or unknown_r:
        return None, ExclusionRecord(
            source_path=source_path,
            source_record_id=rec.get("record_id"),
            reason=ExclusionReason.UNMAPPED_LABEL.value,
            detail=f"entity={unknown_e[:5]} role={unknown_r[:5]}",
            split=split,
        )

    entity_labels: list[str] = []
    for tag in entity_tags:
        mapped = _map_tag(tag, entity_types, mapping)
        if mapped is None:
            return None, ExclusionRecord(
                source_path=source_path,
                source_record_id=rec.get("record_id"),
                reason=ExclusionReason.UNMAPPED_LABEL.value,
                detail=f"entity tag {tag}",
                split=split,
            )
        entity_labels.append(mapped)

    role_labels: list[str] = []
    for tag in role_tags:
        mapped = _map_tag(tag, role_types, mapping)
        if mapped is None:
            return None, ExclusionRecord(
                source_path=source_path,
                source_record_id=rec.get("record_id"),
                reason=ExclusionReason.UNMAPPED_LABEL.value,
                detail=f"role tag {tag}",
                split=split,
            )
        role_labels.append(mapped)

    src = rec.get("source") or {}
    spl = rec.get("split") or {}
    document_id = str(src.get("document_id") or "")
    segment_id = str(src.get("segment_id") or rec.get("record_id") or f"line-{line_no}")
    leakage = document_id or segment_id or str(rec.get("record_id") or f"line-{line_no}")
    if not str(leakage).strip():
        return None, ExclusionRecord(
            source_path=source_path,
            source_record_id=rec.get("record_id"),
            reason=ExclusionReason.MISSING_LEAKAGE_GROUP.value,
            detail="empty leakage_group",
            split=split,
        )

    train_ok = training_permitted(license_decision) and split == "train"
    # evaluation_allowed=unknown fails closed — no evaluation_eligible until explicit grant.
    eval_ok = split in {"validation", "test"} and evaluation_permitted(license_decision)

    offsets_raw = payload.get("token_offsets")
    offsets: list[tuple[int, int]] | None = (
        None if offsets_raw is None else [tuple(x) for x in offsets_raw]
    )

    er_payload = EntityRolesPayload(
        tokens=tokens,
        entity_labels=entity_labels,
        role_labels=role_labels,
        token_offsets=offsets,
        normalized_text=payload.get("normalized_text"),
    )

    record = TaskRecord(
        record_id=f"entity_roles:sourcedata:{segment_id}:{line_no}",
        task_type=TASK_ENTITY_ROLES,
        source=SourceIdentity(
            dataset="SourceData",
            version=str(src.get("version") or "2.0.3"),
            commit=str(src.get("commit") or ""),
            document_id=document_id,
            segment_id=segment_id,
            source_record_id=rec.get("record_id"),
        ),
        split=split,
        split_authority=str(spl.get("authority") or "upstream_official"),
        leakage_group=str(leakage),
        supervision_source=SupervisionSource.HUMAN_PUBLIC,
        authority_level=AuthorityLevel.AUXILIARY,
        allowed_uses=list(DEFAULT_ALLOWED_USES),
        forbidden_uses=list(FORBIDDEN_GOLD_USES),
        licence=license_decision,
        training_eligible=train_ok,
        evaluation_eligible=eval_ok,
        requires_review=False,
        transform_lineage=TransformLineage(
            adapter=ADAPTER_NAME,
            transform_version=TRANSFORM_VERSION,
            parent_path=source_path,
            parent_checksum=parent_sha,
            mapping_version=MAPPING_VERSION,
        ),
        checksum="pending",
        payload=er_payload,
    )
    dump = record.model_dump(mode="json")
    dump["checksum"] = record_checksum(dump)
    return TaskRecord.model_validate(dump), None


def build_sourcedata_entity_roles(root: Path, *, resume: bool = True) -> BuildManifest:
    """Build entity_roles corpus from verified SourceData multitask snapshot."""
    del resume  # reserved; writers are always overwrite-atomic / idempotent
    license_decision = load_license_decision("sourcedata")
    if not adapter_build_permitted(license_decision):
        raise RuntimeError(
            "SourceData licence forbids adapter build "
            "(adapter_build_allowed/derived_labels_allowed fail closed)"
        )

    label_map = load_label_map()
    src_root = _source_multitask_dir(root)
    if not src_root.is_dir():
        raise FileNotFoundError(f"missing SourceData multitask processed path: {src_root}")

    out_dir = task_output_dir(root, TASK_ENTITY_ROLES) / "sourcedata" / "v2.0.3"
    out_dir.mkdir(parents=True, exist_ok=True)

    record_counts: dict[str, int] = {}
    exclusion_counter: Counter[str] = Counter()
    all_lines: list[str] = []
    exclusions: list[dict[str, Any]] = []
    entity_hist: Counter[str] = Counter()
    role_hist: Counter[str] = Counter()
    group_to_splits: dict[str, set[str]] = {}
    document_id_present = 0
    document_id_missing = 0

    for split in ("train", "validation", "test"):
        split_name = cast(SplitName, split)
        src_path = src_root / split / "records.jsonl"
        if not src_path.exists() or is_ignorable_metadata(src_path):
            raise FileNotFoundError(f"missing {src_path}")
        parent_sha = sha256_file(src_path)
        try:
            rel_source = str(src_path.relative_to(root))
        except ValueError:
            rel_source = str(src_path)

        split_records: list[str] = []
        with src_path.open(encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError as exc:
                    exclusion_counter[ExclusionReason.MALFORMED_SOURCE.value] += 1
                    exclusions.append(
                        ExclusionRecord(
                            source_path=rel_source,
                            reason=ExclusionReason.MALFORMED_SOURCE.value,
                            detail=str(exc),
                            split=split,
                        ).model_dump()
                    )
                    continue

                task_rec, excl = convert_source_record(
                    rec,
                    split=split_name,
                    source_path=rel_source,
                    parent_sha=parent_sha,
                    license_decision=license_decision,
                    label_map=label_map,
                    line_no=line_no,
                )
                if excl is not None:
                    exclusion_counter[excl.reason] += 1
                    exclusions.append(excl.model_dump())
                    continue
                assert task_rec is not None
                line_json = task_rec.model_dump_json()
                split_records.append(line_json)
                all_lines.append(line_json)
                group_to_splits.setdefault(task_rec.leakage_group, set()).add(task_rec.split)
                if task_rec.source.document_id.strip():
                    document_id_present += 1
                else:
                    document_id_missing += 1
                for lab in task_rec.payload.entity_labels:
                    if lab != "O":
                        entity_hist[lab] += 1
                for lab in task_rec.payload.role_labels:
                    if lab != "O":
                        role_hist[lab] += 1

        write_jsonl_records(out_dir / f"{split}.jsonl", split_records)
        record_counts[split] = len(split_records)

    records_sha = records_content_sha256(all_lines)
    groups_crossing = count_groups_crossing_splits(group_to_splits)

    write_jsonl_records(
        out_dir / "exclusions.jsonl",
        [json.dumps(e, sort_keys=True) for e in exclusions],
    )
    write_json(
        out_dir / "stats.json",
        {
            "task_type": TASK_ENTITY_ROLES,
            "source": "SourceData",
            "record_counts": record_counts,
            "exclusion_counts": dict(exclusion_counter),
            "entity_label_histogram": dict(sorted(entity_hist.items())),
            "role_label_histogram": dict(sorted(role_hist.items())),
            "synthetic_fraction": 0.0,
            "groups_crossing_splits": groups_crossing,
            "training_allowed_by_licence": license_decision.training_allowed,
            "development_allowed_by_licence": license_decision.development_allowed,
            "evaluation_allowed_by_licence": license_decision.evaluation_allowed,
            "authority_level": AuthorityLevel.AUXILIARY.value,
        },
    )

    try:
        out_rel = str(out_dir.relative_to(root))
    except ValueError:
        out_rel = str(out_dir)

    # Preserve prior content hashes in lineage (do not rewrite historical evidence).
    previous_sha = RECORDS_SHA256_C1_USE_DECISION
    prev_manifest_path = out_dir / "manifest.json"
    if prev_manifest_path.exists():
        try:
            old_man = json.loads(prev_manifest_path.read_text(encoding="utf-8"))
            old_hash = old_man.get("records_sha256")
            old_prev = old_man.get("previous_records_sha256")
            if old_hash == records_sha:
                # Idempotent rebuild: keep previous pointer from on-disk lineage.
                previous_sha = old_prev or RECORDS_SHA256_C1_USE_DECISION
            elif old_hash:
                previous_sha = str(old_hash)
        except (OSError, json.JSONDecodeError, TypeError):
            previous_sha = RECORDS_SHA256_C1_USE_DECISION

    change_reason = (
        "schema_v0.2_partition_metadata_transform_bump;lineage_preserves_prior_content_hashes"
    )
    content_lineage = [
        {
            "records_sha256": RECORDS_SHA256_C1_INITIAL,
            "transform_version": "0.1.0",
            "schema_version": "0.1.0",
            "change_reason": "initial_c1_entity_roles",
        },
        {
            "records_sha256": RECORDS_SHA256_C1_USE_DECISION,
            "transform_version": "0.1.0",
            "schema_version": "0.1.0",
            "change_reason": "granular_use_decision_and_evaluation_fail_closed",
        },
        {
            "records_sha256": records_sha,
            "transform_version": TRANSFORM_VERSION,
            "schema_version": SCHEMA_VERSION,
            "change_reason": change_reason,
        },
    ]

    total_emitted = sum(record_counts.values())
    # Multitask snapshot currently has empty document_id; fallback is record_id →
    # groups_crossing_splits is 0 by construction until document-level IDs land.
    granularity = (
        "DOCUMENT_ID"
        if document_id_present == total_emitted and total_emitted > 0
        else ("MIXED" if document_id_present > 0 else "RECORD_LEVEL_FALLBACK")
    )

    # Manifest-only readiness projection onto root Reality Gate contracts.
    # Does not rewrite TaskRecord JSONL lines or change records_sha256 inputs.
    readiness = project_sourcedata_c0_c1(
        licence_verified=False,
        paper_level_provenance=False,
        ntruth_partition_approved=False,
        leakage_group_granularity=granularity,
    )

    manifest = BuildManifest(
        task_type=TASK_ENTITY_ROLES,
        source_dataset="SourceData",
        source_version="2.0.3",
        adapter=ADAPTER_NAME,
        schema_version=SCHEMA_VERSION,
        transform_version=TRANSFORM_VERSION,
        mapping_version=MAPPING_VERSION,
        seed=DEFAULT_SEED,
        root=str(root),
        output_dir=out_rel,
        record_counts=record_counts,
        exclusion_counts=dict(exclusion_counter),
        records_sha256=records_sha,
        previous_records_sha256=previous_sha,
        change_reason=change_reason,
        content_lineage=content_lineage,
        groups_crossing_splits=groups_crossing,
        partition_origin="UPSTREAM_SOURCEDATA",
        partition_preserved=True,
        ntruth_partition_approved=False,
        model_use_status="BLOCKED",
        engineering_readiness=readiness.engineering_component_status,
        data_readiness=readiness.data_readiness.value,
        scientific_validation=readiness.scientific_validation.value,
        reality_gate_status=readiness.reality_gate_status,
        reality_gate_ref=ROOT_REALITY_GATE_REF,
        reality_gate_satisfied_by_public_corpora=False,
        reality_gate_satisfied_by_silver_adapter=False,
        dataset_readiness_projection=readiness.model_dump(mode="json"),
        leakage_group_granularity=granularity,
        paper_level_leakage_claim_allowed=False,
        synthetic_fraction=0.0,
    )
    write_json(out_dir / "manifest.json", manifest.model_dump(mode="json"))
    write_json(
        out_dir / "label_map_used.json",
        {
            "mapping_version": MAPPING_VERSION,
            "path": "packages/ntruth/task_corpora/label_maps/sourcedata_entity_roles.json",
        },
    )
    write_json(
        out_dir / "leakage_audit.json",
        {
            "groups_crossing_splits": groups_crossing,
            "unique_leakage_groups": len(group_to_splits),
            "document_id_present": document_id_present,
            "document_id_missing": document_id_missing,
            "leakage_group_granularity": granularity,
            "policy": (
                "leakage_group = document_id if present else segment_id/record_id; "
                "upstream_official splits preserved; "
                "RECORD_LEVEL_FALLBACK is not sufficient for paper-level leakage claims"
            ),
            "paper_level_leakage_claim_allowed": False,
        },
    )

    return manifest
