"""Handler for CRAFT v5.0.2 with pinned 67/30 Shared Task partition."""

from __future__ import annotations

import re
import shutil
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ntruth.data.config import (
    CRAFT_VERSION,
    DATASET_TASK_POLICIES,
    FORBIDDEN_NTRUTH_TARGETS,
    get_manifests_dir,
)
from ntruth.data.fs import (
    atomic_extract_archive,
    atomic_write_text,
    is_ignorable_metadata,
)
from ntruth.data.schemas import (
    CommonEnvelope,
    CoreferenceChain,
    CoreferencePayload,
    Eligibility,
    MentionRecord,
    NativeAnnotationTier,
    NTruthUsageTier,
    Provenance,
    SourceReference,
    SplitAssignment,
)
from ntruth.data.source_locks import (
    ensure_pinned_archive,
    ensure_pinned_archive_verified_copy,
    load_archive_lock,
    resume_marker_matches,
    write_authenticated_resume_marker,
)
from ntruth.data.splits import (
    load_craft_2019_shared_task_split,
    stable_split,
    validate_anti_leakage,
)


class CRAFTError(RuntimeError):
    """CRAFT dataset processing error."""


def parse_craft_coreference(
    annotation_path: Path, text: str
) -> tuple[CoreferencePayload, dict[str, Any]]:
    """Parse losslessly representable CRAFT Knowtator-2 identity chains.

    The canonical payload cannot represent discontinuous mentions or APPOS
    relations. Any chain containing one of those constructs is excluded in
    full and reported, rather than silently flattening or inventing spans.
    """
    try:
        root = ET.parse(annotation_path).getroot()
    except (ET.ParseError, OSError) as exc:
        raise CRAFTError(f"Invalid CRAFT coreference XML {annotation_path}: {exc}") from exc

    annotations: dict[str, ET.Element] = {}
    for annotation in root.findall(".//annotation"):
        annotation_id = annotation.get("id")
        if not annotation_id or annotation_id in annotations:
            raise CRAFTError(f"Missing or duplicate annotation id in {annotation_path}")
        annotations[annotation_id] = annotation

    vertices: dict[str, str] = {}
    for vertex in root.findall(".//vertex"):
        vertex_id = vertex.get("id")
        annotation_id = vertex.get("annotation")
        if not vertex_id or not annotation_id or vertex_id in vertices:
            raise CRAFTError(f"Invalid or duplicate vertex in {annotation_path}")
        if annotation_id not in annotations:
            raise CRAFTError(f"Vertex {vertex_id} references missing annotation {annotation_id}")
        vertices[vertex_id] = annotation_id

    chain_members: dict[str, list[str]] = defaultdict(list)
    upstream_members = 0
    for triple in root.findall(".//triple"):
        if triple.get("property") != "Coreferring strings":
            continue
        subject = triple.get("subject")
        object_ = triple.get("object")
        if subject not in vertices or object_ not in vertices:
            raise CRAFTError(f"Coreference triple references missing vertex in {annotation_path}")
        chain_id = vertices[subject]
        mention_id = vertices[object_]
        chain_class = annotations[chain_id].find("class")
        if chain_class is None or chain_class.get("label") != "IDENTITY chain":
            raise CRAFTError(f"Coreference subject {chain_id} is not an IDENTITY chain")
        if mention_id in chain_members[chain_id]:
            raise CRAFTError(f"Duplicate member {mention_id} in chain {chain_id}")
        chain_members[chain_id].append(mention_id)
        upstream_members += 1

    mentions: list[MentionRecord] = []
    chains: list[CoreferenceChain] = []
    emitted_mention_ids: set[str] = set()
    exclusion_reasons: Counter[str] = Counter()

    for chain_id, member_ids in chain_members.items():
        parsed_mentions: list[MentionRecord] = []
        exclusion_reason: str | None = None
        for mention_id in member_ids:
            annotation = annotations[mention_id]
            mention_class = annotation.find("class")
            if mention_class is None or mention_class.get("label") != "Noun Phrase":
                exclusion_reason = "unsupported_member_class"
                break

            spans = annotation.findall("span")
            if len(spans) != 1:
                exclusion_reason = "discontinuous_mention"
                break

            span = spans[0]
            try:
                start = int(span.get("start", ""))
                end = int(span.get("end", ""))
            except ValueError as exc:
                raise CRAFTError(f"Invalid offsets for mention {mention_id}") from exc
            if start < 0 or end <= start or end > len(text):
                raise CRAFTError(f"Out-of-bounds offsets for mention {mention_id}")

            annotated_text = span.text or ""
            source_text = text[start:end]
            if source_text != annotated_text:
                raise CRAFTError(f"Mention {mention_id} span text does not match source text")
            parsed_mentions.append(
                MentionRecord(
                    mention_id=mention_id,
                    start=start,
                    end=end,
                    text=source_text,
                )
            )

        if exclusion_reason is not None:
            exclusion_reasons[exclusion_reason] += 1
            continue
        if len(parsed_mentions) < 2:
            exclusion_reasons["singleton_chain"] += 1
            continue
        duplicate_ids = emitted_mention_ids.intersection(member_ids)
        if duplicate_ids:
            duplicates = ", ".join(sorted(duplicate_ids))
            raise CRAFTError(f"Mentions belong to multiple identity chains: {duplicates}")
        emitted_mention_ids.update(member_ids)
        mentions.extend(parsed_mentions)
        chains.append(CoreferenceChain(chain_id=chain_id, mention_ids=member_ids))

    payload = CoreferencePayload(text=text, mentions=mentions, chains=chains)
    report = {
        "upstream_chains": len(chain_members),
        "upstream_members": upstream_members,
        "emitted_chains": len(chains),
        "emitted_mentions": len(mentions),
        "excluded_chains": sum(exclusion_reasons.values()),
        "exclusion_reasons": dict(sorted(exclusion_reasons.items())),
    }
    return payload, report


def craft_annotation_policy(
    split: str, parse_report: dict[str, Any]
) -> tuple[Eligibility, NativeAnnotationTier, str]:
    """Derive record eligibility without overstating a lossy conversion."""
    if split not in {"train", "validation", "test"}:
        raise CRAFTError(f"Unsupported CRAFT split: {split}")

    if not parse_report.get("upstream_chains") or not parse_report.get("emitted_chains"):
        return (
            Eligibility(
                training_eligible=False,
                evaluation_eligible=False,
                requires_review=True,
            ),
            NativeAnnotationTier.MISSING_ANNOTATION,
            "empty_annotation",
        )

    if parse_report.get("excluded_chains", 0):
        return (
            Eligibility(
                training_eligible=False,
                evaluation_eligible=False,
                requires_review=True,
            ),
            NativeAnnotationTier.HUMAN_CURATED_PARTIAL,
            "partial_annotation_conversion",
        )

    return (
        Eligibility(
            training_eligible=False,
            evaluation_eligible=False,
            requires_review=False,
        ),
        NativeAnnotationTier.HUMAN_CURATED_GOLD,
        "annotated",
    )


def extract_craft_article_id(path: Path) -> str | None:
    """Extract a PMCID embedded in a path component (rare in v5.0.2 layout)."""
    match = re.search(r"(?i)(PMC\d+)", str(path))
    return match.group(1).upper() if match else None


def _normalize_pmcid(value: str) -> str:
    value = value.strip().upper()
    if not value:
        raise CRAFTError("Empty PMCID")
    if value.startswith("PMC"):
        return value
    if value.isdigit():
        return f"PMC{value}"
    raise CRAFTError(f"Unrecognized PMCID token: {value}")


def load_craft_id_mappings(raw_root: Path) -> dict[str, Any]:
    """Parse articles/ids/craft-idmappings.txt → PMCID/PMID/filename indices."""
    mapping_path = raw_root / "articles" / "ids" / "craft-idmappings.txt"
    if not mapping_path.exists():
        # tolerate nested single-root remnants
        candidates = [
            p
            for p in raw_root.rglob("craft-idmappings.txt")
            if p.is_file() and not is_ignorable_metadata(p)
        ]
        if not candidates:
            raise CRAFTError("craft-idmappings.txt not found under CRAFT raw root")
        mapping_path = sorted(candidates)[0]

    pmcid_by_pmid: dict[str, str] = {}
    pmcid_by_filename: dict[str, str] = {}
    pmid_by_pmcid: dict[str, str] = {}

    for line in mapping_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split("\t")
        if len(parts) < 3:
            continue
        filename, pmcid_raw, pmid = parts[0].strip(), parts[1].strip(), parts[2].strip()
        pmcid = _normalize_pmcid(pmcid_raw)
        pmcid_by_pmid[pmid] = pmcid
        pmcid_by_filename[filename] = pmcid
        pmcid_by_filename[Path(filename).stem] = pmcid
        pmid_by_pmcid[pmcid] = pmid

    if not pmcid_by_pmid:
        raise CRAFTError("No PMCID mappings parsed from craft-idmappings.txt")

    return {
        "mapping_path": str(mapping_path),
        "pmcid_by_pmid": pmcid_by_pmid,
        "pmcid_by_filename": pmcid_by_filename,
        "pmid_by_pmcid": pmid_by_pmcid,
        "pmcids": sorted(pmid_by_pmcid.keys()),
    }


def load_craft_official_split(raw_root: Path) -> tuple[str, dict[str, str], dict[str, Any]]:
    """Load official train/dev/test PMID lists and map them to PMCIDs.

    Authority: CRAFT Shared Task 2019 identifier files shipped in the corpus
    (articles/ids/craft-ids-{train,dev,test}.txt). Dev maps to validation.
    """
    mappings = load_craft_id_mappings(raw_root)
    pmcid_by_pmid: dict[str, str] = mappings["pmcid_by_pmid"]
    ids_dir = Path(mappings["mapping_path"]).parent

    def _read_pmids(name: str) -> list[str]:
        path = ids_dir / f"craft-ids-{name}.txt"
        if not path.exists():
            raise CRAFTError(f"Official CRAFT id file missing: {path}")
        return [
            line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
        ]

    train_pmids = _read_pmids("train")
    dev_pmids = _read_pmids("dev")
    test_pmids = _read_pmids("test")

    def _map(pmids: list[str], label: str) -> list[str]:
        out: list[str] = []
        for pmid in pmids:
            pmcid = pmcid_by_pmid.get(pmid)
            if pmcid is None:
                raise CRAFTError(f"Official {label} PMID {pmid} missing from craft-idmappings.txt")
            out.append(pmcid)
        return out

    train_pmcids = _map(train_pmids, "train")
    dev_pmcids = _map(dev_pmids, "dev")
    test_pmcids = _map(test_pmids, "test")

    train_dev = set(train_pmcids) | set(dev_pmcids)
    test_set = set(test_pmcids)
    if not train_dev.isdisjoint(test_set):
        raise CRAFTError("Official CRAFT train/dev and test PMCID sets overlap")
    if set(train_pmcids) & set(dev_pmcids):
        raise CRAFTError("Official CRAFT train and dev PMCID sets overlap")

    split_map: dict[str, str] = {}
    for pmcid in train_pmcids:
        split_map[pmcid] = "train"
    for pmcid in dev_pmcids:
        split_map[pmcid] = "validation"
    for pmcid in test_pmcids:
        split_map[pmcid] = "test"

    evidence = {
        "source": "articles/ids/craft-ids-{train,dev,test}.txt + craft-idmappings.txt",
        "source_counts": {
            "train": len(train_pmcids),
            "validation": len(dev_pmcids),
            "test": len(test_pmcids),
        },
        "mapping_path": mappings["mapping_path"],
    }
    return "craft_shared_task_2019", split_map, evidence


def _discover_files_by_pmcid(raw_root: Path, mappings: dict[str, Any]) -> dict[str, list[Path]]:
    """Index raw files under each PMCID using idmappings + path heuristics."""
    files_by_pmcid: dict[str, list[Path]] = {pmcid: [] for pmcid in mappings["pmcids"]}
    pmcid_by_pmid: dict[str, str] = mappings["pmcid_by_pmid"]
    pmcid_by_filename: dict[str, str] = mappings["pmcid_by_filename"]
    pmid_by_pmcid: dict[str, str] = mappings["pmid_by_pmcid"]

    for path in raw_root.rglob("*"):
        if not path.is_file() or is_ignorable_metadata(path):
            continue

        pmcid = extract_craft_article_id(path)
        if pmcid is None:
            name = path.name
            stem = path.stem
            pmcid = pmcid_by_filename.get(name) or pmcid_by_filename.get(stem)
        if pmcid is None and path.suffix == ".txt" and path.stem.isdigit():
            # articles/txt/{pmid}.txt layout
            pmcid = pmcid_by_pmid.get(path.stem)
        if pmcid is None:
            # nxml often ends with -{pmcid_numeric}.nxml without PMC prefix
            match = re.search(r"-(\d+)\.(?:nxml|txt|xml)$", path.name)
            if match:
                token = match.group(1)
                pmcid = pmcid_by_pmid.get(token) or (
                    f"PMC{token}" if f"PMC{token}" in files_by_pmcid else None
                )

        if pmcid and pmcid in files_by_pmcid:
            files_by_pmcid[pmcid].append(path)

    # Ensure primary text path is preferred when present
    for pmcid, pmid in pmid_by_pmcid.items():
        preferred = raw_root / "articles" / "txt" / f"{pmid}.txt"
        if preferred.exists() and preferred not in files_by_pmcid[pmcid]:
            files_by_pmcid[pmcid].append(preferred)

    return files_by_pmcid


def install_craft(root: Path, refresh: bool = False) -> dict[str, Any]:
    source_ref = CRAFT_VERSION
    archive_lock = load_archive_lock("craft", source_ref=source_ref)
    archive_sha = archive_lock.sha256
    archive = root / "downloads" / f"craft-{source_ref}.zip"
    raw_root = root / "raw" / "craft" / source_ref
    processed_root = root / "processed" / "craft" / source_ref

    marker = raw_root / ".ntruth_complete.json"
    if refresh or not resume_marker_matches(marker, archive_lock):
        with ensure_pinned_archive_verified_copy(
            archive, archive_lock, refresh=refresh, timeout=120, root=root
        ) as verified_archive:
            atomic_extract_archive(
                verified_archive,
                raw_root,
                {
                    "dataset": archive_lock.marker_dataset,
                    "source_ref": archive_lock.source_ref,
                    "source_url": "https://github.com/lhunter-lab/CRAFT",
                    "archive_sha256": archive_sha,
                },
                trusted_root=root,
            )
        write_authenticated_resume_marker(
            raw_root,
            archive_lock,
            metadata={"source_url": "https://github.com/lhunter-lab/CRAFT"},
        )
    else:
        ensure_pinned_archive(archive, archive_lock, refresh=False, timeout=120, root=root)

    # License capture
    license_src = raw_root / "LICENSE.txt"
    if license_src.exists():
        licenses_dir = root / "manifests" / "licenses"
        licenses_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(license_src, licenses_dir / "craft_LICENSE.txt")
        readme_src = raw_root / "README.md"
        if readme_src.exists():
            shutil.copy2(readme_src, licenses_dir / "craft_README.md")

    mappings = load_craft_id_mappings(raw_root)
    found_pmcids = set(mappings["pmcids"])
    files_by_pmcid = _discover_files_by_pmcid(raw_root, mappings)

    if not found_pmcids:
        raise CRAFTError("No PMC identifiers discovered in CRAFT archive")

    split_evidence: dict[str, Any] = {}
    try:
        split_authority, split_map, split_evidence = load_craft_official_split(raw_root)
        counts = split_evidence.get("source_counts", {})
        if (
            counts.get("train", 0) + counts.get("validation", 0) != 67
            or counts.get("test", 0) != 30
        ):
            raise CRAFTError(
                "Official CRAFT split sizes invalid: "
                f"train_dev={counts.get('train', 0) + counts.get('validation', 0)} "
                f"test={counts.get('test', 0)}"
            )
    except Exception as official_exc:
        manifest_path = get_manifests_dir() / "craft_shared_task_2019_split.json"
        try:
            split_authority, split_map = load_craft_2019_shared_task_split(manifest_path)
            # Ensure manifest IDs actually belong to this corpus
            if not set(split_map).issubset(found_pmcids):
                raise CRAFTError(
                    "Package CRAFT split manifest does not match corpus PMCIDs "
                    f"(intersection={len(set(split_map) & found_pmcids)}/{len(found_pmcids)})"
                )
            split_evidence = {
                "source": str(manifest_path),
                "fallback_reason": str(official_exc),
            }
        except Exception as package_exc:
            split_authority = "custom_pmcid_level_fallback"
            split_map = stable_split(sorted(found_pmcids), seed="20260803", ratios=(80, 10, 10))
            split_evidence = {
                "source": "stable_split_fallback",
                "official_error": str(official_exc),
                "package_error": str(package_exc),
            }

    # Restrict to discovered corpus articles
    split_map = {pmcid: split for pmcid, split in split_map.items() if pmcid in found_pmcids}
    validate_anti_leakage(split_map)

    split_counts: dict[str, int] = {"train": 0, "validation": 0, "test": 0}
    parse_totals: Counter[str] = Counter()
    exclusion_reasons: Counter[str] = Counter()
    review_required_records = 0
    training_eligible_records = 0
    evaluation_eligible_records = 0
    for split in ("train", "validation", "test"):
        out_dir = processed_root / split
        out_dir.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []

        for pmcid in sorted(found_pmcids):
            if split_map.get(pmcid) != split:
                continue

            pmc_files = files_by_pmcid.get(pmcid, [])
            text_files = [
                p for p in pmc_files if p.suffix == ".txt" and not p.name.endswith(".copyright")
            ]
            # Prefer articles/txt/{pmid}.txt
            pmid = mappings["pmid_by_pmcid"].get(pmcid)
            preferred = None
            if pmid:
                candidate = raw_root / "articles" / "txt" / f"{pmid}.txt"
                if candidate.exists():
                    preferred = candidate
            text_path = preferred or (text_files[0] if text_files else None)
            if text_path is None:
                raise CRAFTError(f"Source article text missing for {pmcid}")
            text_content = text_path.read_text(encoding="utf-8")

            if pmid is None:
                raise CRAFTError(f"PMID mapping missing for {pmcid}")
            coreference_path = raw_root / "coreference-annotation" / "knowtator-2" / f"{pmid}.xml"
            if not coreference_path.exists():
                raise CRAFTError(f"Coreference annotation missing for {pmcid}: {coreference_path}")
            payload, parse_report = parse_craft_coreference(coreference_path, text_content)
            eligibility, native_tier, annotation_status = craft_annotation_policy(
                split, parse_report
            )
            for key in (
                "upstream_chains",
                "upstream_members",
                "emitted_chains",
                "emitted_mentions",
                "excluded_chains",
            ):
                parse_totals[key] += parse_report[key]
            exclusion_reasons.update(parse_report["exclusion_reasons"])
            review_required_records += int(eligibility.requires_review)
            training_eligible_records += int(eligibility.training_eligible)
            evaluation_eligible_records += int(eligibility.evaluation_eligible)

            envelope = CommonEnvelope(
                record_id=f"craft:{pmcid}",
                source=SourceReference(
                    dataset="CRAFT",
                    version=source_ref,
                    commit=source_ref,
                    document_id=pmcid,
                    segment_id=pmcid,
                ),
                split=SplitAssignment(name=split, authority=split_authority, group_id=pmcid),
                eligibility=eligibility,
                provenance=Provenance(
                    source_url="https://github.com/lhunter-lab/CRAFT",
                    sha256=archive_sha,
                    transform_version="1.1.0",
                ),
                native_annotation_tier=native_tier,
                ntruth_usage_tier=NTruthUsageTier.SILVER_AUXILIARY,
                allowed_tasks=DATASET_TASK_POLICIES["CRAFT"],
                forbidden_targets=FORBIDDEN_NTRUTH_TARGETS,
                annotation_status=annotation_status,
                task_type="coreference",
                payload=payload,
            )
            lines.append(envelope.model_dump_json() + "\n")

        atomic_write_text(out_dir / "records.jsonl", "".join(lines))
        split_counts[split] = len(lines)

    source_status = "VERIFIED" if split_authority == "craft_shared_task_2019" else "UNVERIFIED"
    if sum(split_counts.values()) != 97:
        source_status = "UNVERIFIED"

    upstream_dev = split_counts["train"] + split_counts["validation"]
    return {
        "dataset": "CRAFT",
        "version": source_ref,
        "source_ref": source_ref,
        "source_status": source_status,
        "raw_path": str(raw_root),
        "processed_path": str(processed_root),
        "split_authority": split_authority,
        "split_counts": split_counts,
        "split_evidence": split_evidence,
        "upstream_split": {
            "development_articles": 67 if upstream_dev == 67 else upstream_dev,
            "evaluation_articles": 30 if split_counts["test"] == 30 else split_counts["test"],
            "authority": "craft_shared_task_2019_identifier_files",
            "note": "Official CRAFT Shared Task partition is 67 development + 30 evaluation articles.",
        },
        "ntruth_split": {
            "train": split_counts["train"],
            "validation": split_counts["validation"],
            "test": split_counts["test"],
            "authority": "ntruth_derivation_from_official_development_partition",
            "note": (
                "60 train / 7 validation are an N-Truth derivation of the 67 official development "
                "articles (official train→train, official dev→validation). This is NOT an official "
                "three-way upstream split. Test remains the 30 official evaluation articles."
            ),
        },
        "license": "CC-BY-3.0",
        "status": "ACQUIRED_AND_PROCESSED_NOT_TRAINING_READY",
        "model_use_status": "BLOCKED",
        "training_ready_status": "NOT_MATERIALIZED",
        "model_use_blockers": [
            "canonical_task_corpus_adapter_not_validated",
            "license_use_decision_not_bound_to_records",
            "lossless_coreference_conversion_not_complete",
        ],
        "annotation_conversion": {
            **dict(parse_totals),
            "exclusion_reasons": dict(sorted(exclusion_reasons.items())),
            "review_required_records": review_required_records,
            "training_eligible_records": training_eligible_records,
            "evaluation_eligible_records": evaluation_eligible_records,
            "status": "PARTIAL_FAIL_CLOSED" if review_required_records else "LOSSLESS",
            "note": (
                "The canonical CoreferencePayload cannot represent discontinuous mentions or "
                "APPOS relation members. Affected chains are excluded in full; affected records "
                "require review and are ineligible for training or evaluation."
            ),
        },
        "native_annotation_tier": (
            NativeAnnotationTier.HUMAN_CURATED_PARTIAL
            if review_required_records
            else NativeAnnotationTier.HUMAN_CURATED_GOLD
        ),
        "ntruth_usage_tier": NTruthUsageTier.SILVER_AUXILIARY,
        "files": [{"path": str(archive.relative_to(root)), "sha256": archive_sha}],
    }
