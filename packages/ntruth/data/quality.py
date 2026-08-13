"""Deterministic, streaming quality audit for canonical data envelopes."""

from __future__ import annotations

import hashlib
import json
import math
import re
import tempfile
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from ntruth.data.schemas import CommonEnvelope


class QualityStatus(StrEnum):
    PASS = "PASS"
    PARTIAL = "PARTIAL"
    FAIL = "FAIL"


class RecordCounts(BaseModel):
    physical_records: int = 0
    valid_records: int = 0
    invalid_records: int = 0
    blank_records: int = 0


class LengthSummary(BaseModel):
    count: int
    minimum: int
    maximum: int
    p50: int
    p90: int
    p95: int
    p99: int


class InputFileSummary(BaseModel):
    path: str
    sha256: str
    size_bytes: int
    physical_records: int


class QualityBlocker(BaseModel):
    code: str
    count: int
    message: str


class QualityReport(BaseModel):
    report_schema: str = "ntruth.data.quality.v1"
    status: QualityStatus
    heuristic_policy: str = "Conservative lexical and formatting candidates only; no semantic duplicate truth is inferred."
    inputs: list[InputFileSummary]
    records: RecordCounts
    split_counts: dict[str, int]
    issue_counts: dict[str, int]
    label_histograms: dict[str, dict[str, int]]
    annotation_tier_counts: dict[str, int]
    eligibility_counts: dict[str, dict[str, int]]
    lengths: dict[str, LengthSummary]
    blockers: list[QualityBlocker] = Field(default_factory=list)


_ISSUE_NAMES = (
    "no_valid_records",
    "blank_records",
    "invalid_utf8_records",
    "invalid_json_records",
    "schema_validation_errors",
    "missing_required_field_records",
    "missing_required_value_records",
    "invalid_provenance_sha256_records",
    "task_payload_mismatch_records",
    "missing_annotation_eligible_records",
    "duplicate_record_id",
    "exact_payload_duplicates",
    "normalized_text_duplicates",
    "normalized_token_duplicates",
    "heuristic_near_duplicate_candidates",
    "cross_split_group_leakage",
    "cross_split_normalized_content_leakage",
    "empty_content_records",
    "html_artifact_candidates",
    "citation_artifact_candidates",
    "ocr_noise_candidates",
    "encoding_problem_candidates",
    "language_contamination_candidates",
)

_HTML_RE = re.compile(r"</?[a-z][^>]{0,500}>", re.IGNORECASE)
_CITATION_RES = (
    re.compile(r"\{\{\s*cit(?:e|ation)\b", re.IGNORECASE),
    re.compile(r"\[(?:\d{1,4}[,;\-\s]*)+\]"),
    re.compile(r"\([A-Z][A-Za-z'\-]+(?:\s+et\s+al\.)?,?\s+(?:19|20)\d{2}[a-z]?\)"),
)
_OCR_RES = (
    re.compile(r"\b[A-Za-z]{2,}\|[A-Za-z]{2,}\b"),
    re.compile(r"(?:\b[A-Za-z]\s+){5,}[A-Za-z]\b"),
)
_MOJIBAKE_MARKERS = ("\ufffd", "Ã", "Â", "â€", "ðŸ")
_LEXICAL_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_payload(payload: Any) -> str:
    return json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _normalized_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(normalized.split())


def _lexical_fingerprint(normalized: str) -> str | None:
    tokens = _LEXICAL_TOKEN_RE.findall(normalized)
    if len(tokens) < 8:
        return None
    generalized = ["<number>" if token.isdecimal() else token for token in tokens]
    return _sha256_text(" ".join(generalized))


def _has_language_contamination_candidate(text: str) -> bool:
    letters = 0
    monitored_script_letters = 0
    for character in text:
        if not character.isalpha():
            continue
        letters += 1
        name = unicodedata.name(character, "")
        if any(
            script in name
            for script in (
                "ARABIC",
                "ARMENIAN",
                "BENGALI",
                "CJK",
                "CYRILLIC",
                "DEVANAGARI",
                "GEORGIAN",
                "HANGUL",
                "HEBREW",
                "HIRAGANA",
                "KATAKANA",
                "THAI",
            )
        ):
            monitored_script_letters += 1
    return monitored_script_letters >= 8 and monitored_script_letters / max(letters, 1) >= 0.2


def _has_encoding_problem_candidate(text: str) -> bool:
    if any(marker in text for marker in _MOJIBAKE_MARKERS):
        return True
    return any(ord(character) < 32 and character not in "\n\r\t" for character in text)


def _record_text_and_tokens(envelope: CommonEnvelope) -> tuple[str, list[str] | None]:
    payload = envelope.payload
    if payload.kind == "token_classification":
        text = payload.normalized_text or " ".join(payload.tokens)
        return text, payload.tokens
    return payload.text, None


def _update_label_histograms(
    envelope: CommonEnvelope,
    histograms: defaultdict[str, Counter[str]],
) -> None:
    payload = envelope.payload
    if payload.kind == "token_classification":
        histograms["entity_tags"].update(payload.entity_tags or [])
        histograms["role_tags"].update(payload.role_tags or [])
    elif payload.kind == "span_relation":
        histograms["span_labels"].update(span.label for span in payload.spans)
        histograms["relation_types"].update(
            relation.relation_type for relation in payload.relations
        )
    elif payload.kind == "document_classification":
        histograms["document_labels"].update(payload.labels)


def _update_structural_lengths(
    envelope: CommonEnvelope,
    lengths: defaultdict[str, list[int]],
) -> None:
    payload = envelope.payload
    if payload.kind == "token_classification":
        lengths["tokens"].append(len(payload.tokens))
    elif payload.kind == "span_relation":
        lengths["spans"].append(len(payload.spans))
        lengths["relations"].append(len(payload.relations))
    elif payload.kind == "document_classification":
        lengths["labels"].append(len(payload.labels))
    elif payload.kind == "coreference":
        lengths["mentions"].append(len(payload.mentions))
        lengths["chains"].append(len(payload.chains))


def _percentile(sorted_values: list[int], probability: float) -> int:
    index = max(0, math.ceil(probability * len(sorted_values)) - 1)
    return sorted_values[index]


def _summarize_lengths(values: Iterable[int]) -> LengthSummary:
    ordered = sorted(values)
    return LengthSummary(
        count=len(ordered),
        minimum=ordered[0],
        maximum=ordered[-1],
        p50=_percentile(ordered, 0.50),
        p90=_percentile(ordered, 0.90),
        p95=_percentile(ordered, 0.95),
        p99=_percentile(ordered, 0.99),
    )


def _blockers(issue_counts: dict[str, int]) -> list[QualityBlocker]:
    specifications = (
        (
            "NO_VALID_RECORDS",
            "The audited snapshot contains no valid CommonEnvelope records.",
            issue_counts["no_valid_records"],
        ),
        (
            "INVALID_RECORDS",
            "One or more physical records cannot be validated as CommonEnvelope.",
            issue_counts["invalid_utf8_records"]
            + issue_counts["invalid_json_records"]
            + issue_counts["schema_validation_errors"],
        ),
        (
            "EMPTY_CONTENT",
            "One or more valid envelopes contain no auditable text or tokens.",
            issue_counts["empty_content_records"],
        ),
        (
            "MISSING_REQUIRED_VALUES",
            "One or more required identity, provenance, or task values are empty.",
            issue_counts["missing_required_value_records"],
        ),
        (
            "INVALID_PROVENANCE_SHA256",
            "One or more provenance sha256 values are not 64 hexadecimal characters.",
            issue_counts["invalid_provenance_sha256_records"],
        ),
        (
            "TASK_PAYLOAD_MISMATCH",
            "task_type does not agree with the discriminated payload kind.",
            issue_counts["task_payload_mismatch_records"],
        ),
        (
            "MISSING_ANNOTATION_ELIGIBLE",
            "A record without an annotation remains training or evaluation eligible.",
            issue_counts["missing_annotation_eligible_records"],
        ),
        (
            "DUPLICATE_RECORD_ID",
            "record_id is not unique across the audited snapshot.",
            issue_counts["duplicate_record_id"],
        ),
        (
            "CROSS_SPLIT_GROUP_LEAKAGE",
            "A group_id occurs in more than one split.",
            issue_counts["cross_split_group_leakage"],
        ),
        (
            "CROSS_SPLIT_CONTENT_LEAKAGE",
            "Normalized content occurs in more than one split.",
            issue_counts["cross_split_normalized_content_leakage"],
        ),
    )
    return [
        QualityBlocker(code=code, count=count, message=message)
        for code, message, count in specifications
        if count
    ]


def audit_common_envelope_jsonl(paths: Iterable[Path]) -> QualityReport:
    """Audit JSONL files without retaining complete record payloads in memory."""
    input_paths = sorted({Path(path).resolve() for path in paths}, key=lambda path: str(path))
    issue_counts: Counter[str] = Counter({name: 0 for name in _ISSUE_NAMES})
    split_counts: Counter[str] = Counter()
    annotation_tiers: Counter[str] = Counter()
    eligibility: dict[str, Counter[str]] = {
        field: Counter({"false": 0, "true": 0})
        for field in ("training_eligible", "evaluation_eligible", "requires_review")
    }
    label_histograms: defaultdict[str, Counter[str]] = defaultdict(Counter)
    lengths: defaultdict[str, list[int]] = defaultdict(list)
    records = RecordCounts()
    input_summaries: list[InputFileSummary] = []

    record_ids: set[str] = set()
    payload_hashes: set[str] = set()
    normalized_text_hashes: set[str] = set()
    normalized_token_hashes: set[str] = set()
    lexical_hashes: defaultdict[str, set[str]] = defaultdict(set)
    group_splits: defaultdict[str, set[str]] = defaultdict(set)
    content_splits: defaultdict[str, set[str]] = defaultdict(set)

    for path in input_paths:
        file_hash = hashlib.sha256()
        file_size_bytes = 0
        file_physical_records = 0
        with path.open("rb") as stream:
            for raw_line in stream:
                file_hash.update(raw_line)
                file_size_bytes += len(raw_line)
                file_physical_records += 1
                records.physical_records += 1
                if not raw_line.strip():
                    records.blank_records += 1
                    issue_counts["blank_records"] += 1
                    continue
                try:
                    record_text = raw_line.decode("utf-8")
                except UnicodeDecodeError:
                    records.invalid_records += 1
                    issue_counts["invalid_utf8_records"] += 1
                    continue
                try:
                    raw_record = json.loads(record_text)
                except json.JSONDecodeError:
                    records.invalid_records += 1
                    issue_counts["invalid_json_records"] += 1
                    continue
                try:
                    envelope = CommonEnvelope.model_validate(raw_record)
                except ValidationError as exc:
                    records.invalid_records += 1
                    issue_counts["schema_validation_errors"] += 1
                    if any(error["type"] == "missing" for error in exc.errors()):
                        issue_counts["missing_required_field_records"] += 1
                    continue

                records.valid_records += 1
                split_name = envelope.split.name
                split_counts[split_name] += 1
                group_splits[envelope.split.group_id].add(split_name)
                annotation_tiers[envelope.native_annotation_tier.value] += 1
                for field_name, counter in eligibility.items():
                    counter[str(getattr(envelope.eligibility, field_name)).lower()] += 1

                required_values = (
                    envelope.record_id,
                    envelope.source.dataset,
                    envelope.source.version,
                    envelope.source.commit,
                    envelope.source.document_id,
                    envelope.source.segment_id,
                    envelope.split.authority,
                    envelope.split.group_id,
                    envelope.provenance.source_url,
                    envelope.provenance.transform_version,
                )
                if (
                    any(not value.strip() for value in required_values)
                    or not envelope.allowed_tasks
                    or any(not task.strip() for task in envelope.allowed_tasks)
                ):
                    issue_counts["missing_required_value_records"] += 1
                if not re.fullmatch(r"[0-9a-fA-F]{64}", envelope.provenance.sha256):
                    issue_counts["invalid_provenance_sha256_records"] += 1
                if envelope.task_type != envelope.payload.kind:
                    issue_counts["task_payload_mismatch_records"] += 1
                if (
                    envelope.annotation_status == "missing_annotation_file"
                    or envelope.native_annotation_tier.value == "MISSING_ANNOTATION"
                ) and (
                    envelope.eligibility.training_eligible
                    or envelope.eligibility.evaluation_eligible
                ):
                    issue_counts["missing_annotation_eligible_records"] += 1

                if envelope.record_id in record_ids:
                    issue_counts["duplicate_record_id"] += 1
                else:
                    record_ids.add(envelope.record_id)

                payload_hash = _sha256_text(_canonical_payload(envelope.payload))
                if payload_hash in payload_hashes:
                    issue_counts["exact_payload_duplicates"] += 1
                else:
                    payload_hashes.add(payload_hash)

                text, tokens = _record_text_and_tokens(envelope)
                normalized = _normalized_text(text)
                lengths["text_characters"].append(len(text))
                _update_structural_lengths(envelope, lengths)
                _update_label_histograms(envelope, label_histograms)

                if not normalized:
                    issue_counts["empty_content_records"] += 1
                else:
                    normalized_hash = _sha256_text(normalized)
                    content_splits[normalized_hash].add(split_name)
                    if normalized_hash in normalized_text_hashes:
                        issue_counts["normalized_text_duplicates"] += 1
                    else:
                        normalized_text_hashes.add(normalized_hash)
                    lexical_hash = _lexical_fingerprint(normalized)
                    if lexical_hash is not None:
                        distinct_normalized = lexical_hashes[lexical_hash]
                        if distinct_normalized and normalized_hash not in distinct_normalized:
                            issue_counts["heuristic_near_duplicate_candidates"] += 1
                        distinct_normalized.add(normalized_hash)

                if tokens is not None:
                    normalized_tokens = _normalized_text(" ".join(tokens))
                    token_hash = _sha256_text(normalized_tokens)
                    if token_hash in normalized_token_hashes:
                        issue_counts["normalized_token_duplicates"] += 1
                    else:
                        normalized_token_hashes.add(token_hash)

                if _HTML_RE.search(text):
                    issue_counts["html_artifact_candidates"] += 1
                if any(pattern.search(text) for pattern in _CITATION_RES):
                    issue_counts["citation_artifact_candidates"] += 1
                if any(pattern.search(text) for pattern in _OCR_RES):
                    issue_counts["ocr_noise_candidates"] += 1
                if _has_encoding_problem_candidate(text):
                    issue_counts["encoding_problem_candidates"] += 1
                if _has_language_contamination_candidate(text):
                    issue_counts["language_contamination_candidates"] += 1

        input_summaries.append(
            InputFileSummary(
                path=str(path),
                sha256=file_hash.hexdigest(),
                size_bytes=file_size_bytes,
                physical_records=file_physical_records,
            )
        )

    if records.valid_records == 0:
        issue_counts["no_valid_records"] = 1
    issue_counts["cross_split_group_leakage"] = sum(
        1 for splits in group_splits.values() if len(splits) > 1
    )
    issue_counts["cross_split_normalized_content_leakage"] = sum(
        1 for splits in content_splits.values() if len(splits) > 1
    )
    blockers = _blockers(dict(issue_counts))
    if blockers:
        status = QualityStatus.FAIL
    elif any(issue_counts.values()):
        status = QualityStatus.PARTIAL
    else:
        status = QualityStatus.PASS

    return QualityReport(
        status=status,
        inputs=input_summaries,
        records=records,
        split_counts=dict(sorted(split_counts.items())),
        issue_counts={name: issue_counts[name] for name in _ISSUE_NAMES},
        label_histograms={
            name: dict(sorted(histogram.items()))
            for name, histogram in sorted(label_histograms.items())
            if histogram
        },
        annotation_tier_counts=dict(sorted(annotation_tiers.items())),
        eligibility_counts={
            name: {value: counter[value] for value in ("false", "true")}
            for name, counter in eligibility.items()
        },
        lengths={
            name: _summarize_lengths(values) for name, values in sorted(lengths.items()) if values
        },
        blockers=blockers,
    )


def write_quality_report(report: QualityReport, destination: Path) -> None:
    """Atomically write a stable, machine-readable quality report."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(
        report.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
        delete=False,
    ) as stream:
        temporary_path = Path(stream.name)
        stream.write(encoded)
        stream.write("\n")
    temporary_path.replace(destination)
