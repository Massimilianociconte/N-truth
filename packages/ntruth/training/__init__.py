"""Preparazione deterministica di dataset; nessun training viene avviato qui."""

from ntruth.training.manifest import dumps_dataset_manifest, dumps_preparation_report
from ntruth.training.preparation import DatasetValidationError, prepare_dataset
from ntruth.training.records import (
    AnnotationStatus,
    DatasetFormatError,
    DatasetManifest,
    DuplicateDecision,
    DuplicateKind,
    PreparationConfig,
    PreparationReport,
    PreparedDataset,
    PreparedRecord,
    SplitRatios,
    SupervisedRecord,
    SupervisionProvenance,
    dumps_prepared_jsonl,
    dumps_supervised_jsonl,
    load_supervised_jsonl,
    loads_supervised_jsonl,
)

__all__ = [
    "AnnotationStatus",
    "DatasetFormatError",
    "DatasetManifest",
    "DatasetValidationError",
    "DuplicateDecision",
    "DuplicateKind",
    "PreparationConfig",
    "PreparationReport",
    "PreparedDataset",
    "PreparedRecord",
    "SplitRatios",
    "SupervisedRecord",
    "SupervisionProvenance",
    "dumps_dataset_manifest",
    "dumps_preparation_report",
    "dumps_prepared_jsonl",
    "dumps_supervised_jsonl",
    "load_supervised_jsonl",
    "loads_supervised_jsonl",
    "prepare_dataset",
]
