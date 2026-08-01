"""Contratti deterministici per preparare dataset supervisionati N-Truth.

Il modulo descrive artefatti di preparazione, non un runtime di training. I
record candidati restano esplicitamente non eleggibili finche la governance e
la revisione umana non li rendono utilizzabili.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from math import isclose
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, JsonValue, ValidationError, field_validator, model_validator

from ntruth.governance.lineage import CorpusSplit
from ntruth.schemas.core import FrozenModel, content_checksum

TRAINING_RECORD_SCHEMA_VERSION = "1.0.0"
NORMALIZATION_VERSION = "1.0.0"
MANIFEST_VERSION = "2.0.0"


class AnnotationStatus(StrEnum):
    """Maturita della supervisione umana associata a un record."""

    CANDIDATE = "candidate"
    SINGLE_REVIEWED = "single_reviewed"
    DOUBLE_REVIEWED = "double_reviewed"
    ADJUDICATED = "adjudicated"


class IssueSeverity(StrEnum):
    WARNING = "warning"
    ERROR = "error"


class DuplicateKind(StrEnum):
    EXACT = "exact"
    NEAR = "near"


class SupervisionProvenance(FrozenModel):
    """Provenienza minima necessaria per autorizzare e ricostruire un record."""

    source_id: str
    source_asset_id: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    governance_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    publication_id: str | None = None
    project_id: str | None = None
    bundle_id: str | None = None
    laboratory_id: str | None = None
    corresponding_author_id: str | None = None
    license_or_authorization_id: str | None = None
    guideline_version: str
    reviewer_count: int = Field(default=0, ge=0)
    reviewer_roles: tuple[str, ...] = ()
    adjudication_id: str | None = None
    synthetic: bool = False

    @field_validator(
        "source_id",
        "source_asset_id",
        "publication_id",
        "project_id",
        "bundle_id",
        "laboratory_id",
        "corresponding_author_id",
        "license_or_authorization_id",
        "guideline_version",
        "adjudication_id",
    )
    @classmethod
    def _non_blank_identifiers(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("gli identificatori di provenance non possono essere vuoti")
        return value.strip() if value is not None else None

    @field_validator("reviewer_roles")
    @classmethod
    def _non_blank_roles(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(role.strip() for role in value)
        if any(not role for role in normalized):
            raise ValueError("reviewer_roles non puo contenere ruoli vuoti")
        return normalized


class SupervisedRecord(FrozenModel):
    """Una riga JSONL supervisionata, ancora indipendente da qualsiasi split."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    record_id: str
    task: str
    language: str
    domain: str | None = None
    input_text: str
    target: dict[str, JsonValue] = Field(min_length=1)
    provenance: SupervisionProvenance
    annotation_status: AnnotationStatus = AnnotationStatus.CANDIDATE
    training_eligible: bool = False
    requested_split: CorpusSplit | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("record_id", "task", "language", "input_text")
    @classmethod
    def _required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("i campi testuali obbligatori non possono essere vuoti")
        return value

    @field_validator("domain")
    @classmethod
    def _optional_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("domain non puo essere una stringa vuota")
        return value

    @model_validator(mode="after")
    def _validate_curation_and_use(self) -> SupervisedRecord:
        if (
            self.annotation_status is AnnotationStatus.DOUBLE_REVIEWED
            and self.provenance.reviewer_count < 2
        ):
            raise ValueError("double_reviewed richiede almeno due revisioni")
        if self.annotation_status is AnnotationStatus.ADJUDICATED:
            if self.provenance.reviewer_count < 2:
                raise ValueError("adjudicated richiede almeno due revisioni")
            if self.provenance.adjudication_id is None:
                raise ValueError("adjudicated richiede adjudication_id")
        eligible_statuses = {
            AnnotationStatus.DOUBLE_REVIEWED,
            AnnotationStatus.ADJUDICATED,
        }
        if self.training_eligible and self.annotation_status not in eligible_statuses:
            raise ValueError("un record candidate/single_reviewed non e training-eligible")
        if self.training_eligible and self.provenance.license_or_authorization_id is None:
            raise ValueError("training_eligible richiede licenza o autorizzazione esplicita")
        if self.provenance.synthetic and self.requested_split not in {None, CorpusSplit.TRAIN}:
            raise ValueError("i record sintetici possono essere assegnati soltanto a train")
        return self


class SplitRatios(FrozenModel):
    """Pesi per gli split interni; external e sempre assegnato esplicitamente."""

    train: float = Field(default=0.8, ge=0.0, le=1.0)
    validation: float = Field(default=0.1, ge=0.0, le=1.0)
    test: float = Field(default=0.1, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _sum_to_one(self) -> SplitRatios:
        if not isclose(self.train + self.validation + self.test, 1.0, abs_tol=1e-12):
            raise ValueError("le proporzioni train/validation/test devono sommare a 1")
        return self

    def as_dict(self) -> dict[CorpusSplit, float]:
        return {
            CorpusSplit.TRAIN: self.train,
            CorpusSplit.VALIDATION: self.validation,
            CorpusSplit.TEST: self.test,
        }


class PreparationConfig(FrozenModel):
    """Configurazione completa e serializzabile della preparazione."""

    record_schema_version: Literal["1.0.0"] = "1.0.0"
    normalization_version: Literal["1.0.0"] = "1.0.0"
    seed: str = "ntruth-dataset-v1"
    near_duplicate_threshold: float = Field(default=0.92, ge=0.8, le=1.0)
    shingle_size: int = Field(default=5, ge=1, le=20)
    split_ratios: SplitRatios = Field(default_factory=SplitRatios)
    require_training_eligible: bool = True
    fail_on_error: bool = True
    parent_dataset_ids: tuple[str, ...] = ()

    @field_validator("record_schema_version", "normalization_version", "seed")
    @classmethod
    def _non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("versioni e seed non possono essere vuoti")
        return value

    @field_validator("parent_dataset_ids")
    @classmethod
    def _unique_parents(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item.strip() for item in value):
            raise ValueError("parent_dataset_ids non puo contenere valori vuoti")
        if len(value) != len(set(value)):
            raise ValueError("parent_dataset_ids duplicati")
        return value

    def checksum(self) -> str:
        payload = self.model_dump(mode="json", exclude={"fail_on_error"})
        return content_checksum(payload)


class ValidationIssue(FrozenModel):
    code: str
    severity: IssueSeverity
    detail: str
    record_ids: tuple[str, ...] = ()


class DuplicateDecision(FrozenModel):
    kind: DuplicateKind
    duplicate_record_id: str
    canonical_record_id: str
    duplicate_source_asset_id: str
    canonical_source_asset_id: str
    duplicate_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    similarity: float = Field(ge=0.0, le=1.0)
    reason: str


class PreparedRecord(FrozenModel):
    """Record conservato con normalizzazione, fingerprint e split tracciati."""

    record: SupervisedRecord
    normalized_input: str
    canonical_target: str
    exact_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    near_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    leakage_group_id: str
    split: CorpusSplit

    @model_validator(mode="after")
    def _synthetic_only_train(self) -> PreparedRecord:
        if self.record.provenance.synthetic and self.split is not CorpusSplit.TRAIN:
            raise ValueError("i record sintetici possono apparire soltanto in train")
        return self


class ManifestRecord(FrozenModel):
    record_id: str
    record_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    exact_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    near_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    split: CorpusSplit
    leakage_group_id: str
    source_id: str
    source_asset_id: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    governance_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    annotation_status: AnnotationStatus
    training_eligible: bool
    license_or_authorization_id: str | None = None
    reviewer_count: int = Field(ge=0)
    adjudication_id: str | None = None
    synthetic: bool = False

    @model_validator(mode="after")
    def _validate_training_authorization(self) -> ManifestRecord:
        if not self.training_eligible:
            return self
        if self.annotation_status not in {
            AnnotationStatus.DOUBLE_REVIEWED,
            AnnotationStatus.ADJUDICATED,
        }:
            raise ValueError("training_eligible richiede revisione doppia o adjudication")
        if self.reviewer_count < 2:
            raise ValueError("training_eligible richiede almeno due reviewer")
        if self.license_or_authorization_id is None:
            raise ValueError("training_eligible richiede licenza o autorizzazione")
        if self.annotation_status is AnnotationStatus.ADJUDICATED and self.adjudication_id is None:
            raise ValueError("adjudicated richiede adjudication_id nel manifest")
        return self


class PreparationReport(FrozenModel):
    input_count: int = Field(ge=0)
    eligible_count: int = Field(ge=0)
    excluded_count: int = Field(ge=0)
    kept_count: int = Field(ge=0)
    exact_duplicate_count: int = Field(ge=0)
    near_duplicate_count: int = Field(ge=0)
    leakage_group_count: int = Field(ge=0)
    split_counts: dict[str, int]
    dataset_records_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    issues: tuple[ValidationIssue, ...] = ()
    duplicate_decisions: tuple[DuplicateDecision, ...] = ()

    @model_validator(mode="after")
    def _validate_counts(self) -> PreparationReport:
        if self.eligible_count + self.excluded_count != self.input_count:
            raise ValueError("eligible_count + excluded_count deve coincidere con input_count")
        if self.kept_count + self.exact_duplicate_count + self.near_duplicate_count != (
            self.eligible_count
        ):
            raise ValueError("i conteggi di deduplica non ricostruiscono gli eleggibili")
        if sum(self.split_counts.values()) != self.kept_count:
            raise ValueError("split_counts non coincide con kept_count")
        return self


class DatasetManifest(FrozenModel):
    """Manifest content-addressed dell'output pronto per un futuro trainer."""

    manifest_version: Literal["2.0.0"] = "2.0.0"
    dataset_id: str = ""
    parent_dataset_ids: tuple[str, ...] = ()
    record_schema_version: str
    normalization_version: str
    config_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    records_checksum: str = ""
    decisions_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    report_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    records: tuple[ManifestRecord, ...] = ()

    @model_validator(mode="after")
    def _validate_manifest(self) -> DatasetManifest:
        record_ids = [record.record_id for record in self.records]
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("record_id duplicati nel dataset manifest")
        group_splits: dict[str, set[CorpusSplit]] = {}
        for record in self.records:
            group_splits.setdefault(record.leakage_group_id, set()).add(record.split)
            if record.synthetic and record.split is not CorpusSplit.TRAIN:
                raise ValueError("record sintetici ammessi soltanto in train")
        if any(len(splits) > 1 for splits in group_splits.values()):
            raise ValueError("un leakage group attraversa split differenti")
        expected_records_checksum = self.computed_records_checksum()
        if self.records_checksum and self.records_checksum != expected_records_checksum:
            raise ValueError("records_checksum non coerente con il manifest")
        object.__setattr__(self, "records_checksum", expected_records_checksum)
        expected_id = self.computed_dataset_id()
        if self.dataset_id and self.dataset_id != expected_id:
            raise ValueError("dataset_id non coerente con il contenuto")
        object.__setattr__(self, "dataset_id", expected_id)
        if self.dataset_id in self.parent_dataset_ids:
            raise ValueError("un dataset non puo essere padre di se stesso")
        return self

    def _sorted_record_payloads(self) -> list[dict[str, object]]:
        return sorted(
            (record.model_dump(mode="json") for record in self.records),
            key=lambda item: str(item["record_id"]),
        )

    def computed_records_checksum(self) -> str:
        return content_checksum(self._sorted_record_payloads())

    def _identity_payload(self) -> dict[str, object]:
        return {
            "manifest_version": self.manifest_version,
            "parents": sorted(self.parent_dataset_ids),
            "record_schema_version": self.record_schema_version,
            "normalization_version": self.normalization_version,
            "config_checksum": self.config_checksum,
            "records_checksum": self.computed_records_checksum(),
            "decisions_checksum": self.decisions_checksum,
            "report_checksum": self.report_checksum,
            "records": self._sorted_record_payloads(),
        }

    def manifest_checksum(self) -> str:
        return content_checksum(self._identity_payload())

    def computed_dataset_id(self) -> str:
        return f"dataset-{self.manifest_checksum()[:20]}"


class PreparedDataset(FrozenModel):
    records: tuple[PreparedRecord, ...]
    manifest: DatasetManifest
    report: PreparationReport

    @model_validator(mode="after")
    def _cross_check(self) -> PreparedDataset:
        prepared_by_id = {record.record.record_id: record for record in self.records}
        if len(prepared_by_id) != len(self.records):
            raise ValueError("record_id duplicati nei record preparati")
        manifest_by_id = {record.record_id: record for record in self.manifest.records}
        if prepared_by_id.keys() != manifest_by_id.keys():
            raise ValueError("record preparati e manifest non coincidono")
        for record_id, prepared in prepared_by_id.items():
            entry = manifest_by_id[record_id]
            if (
                prepared.split is not entry.split
                or prepared.leakage_group_id != entry.leakage_group_id
                or prepared.exact_fingerprint != entry.exact_fingerprint
                or prepared.near_fingerprint != entry.near_fingerprint
                or prepared.record.annotation_status is not entry.annotation_status
                or prepared.record.training_eligible != entry.training_eligible
                or (
                    prepared.record.provenance.license_or_authorization_id
                    != entry.license_or_authorization_id
                )
                or prepared.record.provenance.reviewer_count != entry.reviewer_count
                or prepared.record.provenance.adjudication_id != entry.adjudication_id
            ):
                raise ValueError(f"manifest incoerente per record {record_id}")
        if self.report.kept_count != len(self.records):
            raise ValueError("report.kept_count non coincide con i record preparati")
        if self.report.dataset_records_checksum != self.manifest.records_checksum:
            raise ValueError("checksum record incoerente tra report e manifest")
        return self


_ZERO_WIDTH = str.maketrans("", "", "\u200b\u200c\u200d\ufeff")
_TOKEN_RE = re.compile(r"\w+", flags=re.UNICODE)


def _sha256(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_text(value: str) -> str:
    """Canonizza Unicode e whitespace per confronti, senza mutare il record fonte."""

    normalized = unicodedata.normalize("NFKC", value).translate(_ZERO_WIDTH)
    return " ".join(normalized.casefold().split())


def _normalize_json(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFKC", value)
    if isinstance(value, list):
        return [_normalize_json(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_json(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _normalize_json(item) for key, item in value.items()}
    return value


def canonical_json(value: Any) -> str:
    """JSON canonico: chiavi ordinate, niente NaN, nessuna dipendenza dalla locale."""

    return json.dumps(
        _normalize_json(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def token_shingles(normalized_text: str, size: int) -> frozenset[str]:
    """Shingle lessicali usati soltanto per near-duplicate conservative."""

    tokens = _TOKEN_RE.findall(normalized_text)
    if not tokens:
        return frozenset()
    if len(tokens) < size:
        return frozenset({" ".join(tokens)})
    return frozenset(
        " ".join(tokens[index : index + size]) for index in range(len(tokens) - size + 1)
    )


def jaccard_similarity(left: frozenset[str], right: frozenset[str]) -> float:
    if not left and not right:
        # Gli exact duplicate sono gia stati rimossi. Due input privi di token
        # lessicali non forniscono evidenza sufficiente per un near-match.
        return 0.0
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


@dataclass(frozen=True, slots=True)
class NormalizedRecord:
    record: SupervisedRecord
    normalized_input: str
    canonical_target: str
    exact_fingerprint: str
    near_fingerprint: str
    content_key: str
    shingles: frozenset[str]


def normalize_record(record: SupervisedRecord, *, shingle_size: int) -> NormalizedRecord:
    normalized_input = normalize_text(record.input_text)
    canonical_target = canonical_json(record.target)
    common = {
        "task": normalize_text(record.task),
        "language": normalize_text(record.language),
        "domain": normalize_text(record.domain) if record.domain is not None else None,
        "input": normalized_input,
    }
    content_key = _sha256(canonical_json(common))
    exact_fingerprint = _sha256(canonical_json({**common, "target": json.loads(canonical_target)}))
    shingles = token_shingles(normalized_input, shingle_size)
    near_fingerprint = _sha256(canonical_json(sorted(shingles)))
    return NormalizedRecord(
        record=record,
        normalized_input=normalized_input,
        canonical_target=canonical_target,
        exact_fingerprint=exact_fingerprint,
        near_fingerprint=near_fingerprint,
        content_key=content_key,
        shingles=shingles,
    )


class DatasetFormatError(ValueError):
    """Errore JSONL con la riga fisica utile per correggere l'asset sorgente."""

    def __init__(self, line_number: int, detail: str) -> None:
        self.line_number = line_number
        self.detail = detail
        super().__init__(f"riga JSONL {line_number}: {detail}")


def loads_supervised_jsonl(payload: str | bytes) -> tuple[SupervisedRecord, ...]:
    """Carica JSONL locale; le righe vuote sono ignorate ma mai emesse in output."""

    text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
    records: list[SupervisedRecord] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(SupervisedRecord.model_validate_json(line))
        except (ValidationError, ValueError) as error:
            raise DatasetFormatError(line_number, str(error)) from error
    return tuple(records)


def dumps_supervised_jsonl(records: tuple[SupervisedRecord, ...]) -> str:
    """Serializza record ordinati per ID con un'unica forma JSON canonica."""

    ordered = sorted(records, key=lambda record: record.record_id)
    identifiers = [record.record_id for record in ordered]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("record_id duplicati: impossibile produrre JSONL canonico")
    if not ordered:
        return ""
    return "\n".join(canonical_json(record.model_dump(mode="json")) for record in ordered) + "\n"


def dumps_prepared_jsonl(records: tuple[PreparedRecord, ...]) -> str:
    """Serializza l'output includendo fingerprint, gruppo e split assegnato."""

    ordered = sorted(records, key=lambda record: record.record.record_id)
    if not ordered:
        return ""
    return "\n".join(canonical_json(record.model_dump(mode="json")) for record in ordered) + "\n"


def load_supervised_jsonl(path: str | Path) -> tuple[SupervisedRecord, ...]:
    return loads_supervised_jsonl(Path(path).read_bytes())
