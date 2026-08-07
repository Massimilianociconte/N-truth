"""Adattamento del dataset governato al formato chat JSONL di MLX-LM."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ntruth.governance.lineage import CorpusSplit
from ntruth.parser_ai.contract import ParserAIInput
from ntruth.parser_ai.stages import (
    CandidateGraphSet,
    StageAuthority,
    StageName,
    StageProvenance,
    StageStatus,
    validate_candidate_graph_pair,
)
from ntruth.training.gold import GoldParserTarget
from ntruth.training.manifest import dumps_dataset_manifest, dumps_preparation_report
from ntruth.training.mlx_runtime import (
    SNAPSHOT_SCHEMA_VERSION,
    MLXPipelineError,
    _snapshot_identity,
    _write_json,
    sha256_file,
    utc_now,
)
from ntruth.training.records import (
    AnnotationStatus,
    PreparedDataset,
    PreparedRecord,
    dumps_prepared_jsonl,
)

PARSER_CANDIDATE_GRAPH_TASK = "parser_candidate_graph_v6"
PROMPT_TEMPLATE_VERSION = "ntruth-candidate-graph-v6-mlx-1.0.0"
SYSTEM_PROMPT = """You are the local N-Truth candidate-fact parser.
Read exactly one ParserAIInput v2.0.0 JSON object supplied by the user.
Return exactly one JSON object matching CandidateGraphSet v1.0.0 with authority=model.
Return candidate facts with evidence only: never emit a verdict, statistical test,
power analysis, alert, accusation, Markdown, commentary, or facts not supported by
the supplied source coordinates. Keep allocation and application levels distinct.
If evidence is absent, represent alternatives and missing facts; do not guess.
Provenance, input checksums, parent results, actor roles and timestamps are host-owned:
their generated values are ignored and deterministically replaced before validation.
Never emit determinability or a verdict. The deterministic N-Truth compiler, not
this model, derives determinability and applies scientific rules."""


def _chat_record(prepared: PreparedRecord) -> dict[str, Any]:
    record = prepared.record
    if record.task != PARSER_CANDIDATE_GRAPH_TASK:
        raise MLXPipelineError(
            f"record {record.record_id}: task atteso {PARSER_CANDIDATE_GRAPH_TASK}, "
            f"ricevuto {record.task}"
        )
    try:
        parser_input = ParserAIInput.model_validate_json(record.input_text)
        gold_target = GoldParserTarget.model_validate(record.target)
        if gold_target.source_record_id != record.record_id:
            raise ValueError("GoldParserTarget riferito a un record sorgente diverso")
        if gold_target.guideline_version != record.provenance.guideline_version:
            raise ValueError("versione guideline non coerente tra record e Parser Gold")
        if record.annotation_status is not AnnotationStatus.ADJUDICATED:
            raise ValueError("il Parser Gold per MLX richiede annotation_status=adjudicated")
        if record.provenance.adjudication_id != gold_target.adjudication_id:
            raise ValueError("adjudication_id non coerente tra record e Parser Gold")
        candidate_graph = validate_candidate_graph_pair(
            parser_input,
            gold_target.model_candidate_graph(),
        )
    except (ValueError, TypeError) as exc:
        raise MLXPipelineError(
            f"record {record.record_id}: contratto candidate/gold v6 non valido: {exc}"
        ) from exc
    user_content = json.dumps(
        parser_input.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    assistant_content = json.dumps(
        candidate_graph.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "record_id": record.record_id,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": assistant_content},
        ],
    }


def _write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for value in values:
            handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
    temporary.replace(path)


def _runtime_smoke_chat_record(index: int) -> dict[str, Any]:
    """Costruisce una riga smoke canonica, ricostruibile dal gate di integrità."""

    parser_input = ParserAIInput(
        metadata={"runtime_smoke_index": index},
        domain_hint="runtime_smoke_only",
        language="en",
    )
    target = CandidateGraphSet(
        result_id=f"runtime-smoke-result-{index:02d}",
        stage=StageName.CANDIDATE_GRAPH_SET,
        status=StageStatus.COMPLETE,
        provenance=StageProvenance(
            stage_run_id=f"runtime-smoke-stage-{index:02d}",
            stage=StageName.CANDIDATE_GRAPH_SET,
            authority=StageAuthority.MODEL,
            producer="ntruth-runtime-smoke",
            producer_version="1.0.0",
        ),
        graph_set_id=f"runtime-smoke-graph-{index:02d}",
    )
    target = validate_candidate_graph_pair(parser_input, target)
    return {
        "record_id": f"runtime-smoke-{index:02d}",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    parser_input.model_dump(mode="json"),
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            },
            {
                "role": "assistant",
                "content": json.dumps(
                    target.model_dump(mode="json"),
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            },
        ],
    }


def export_mlx_dataset(dataset: PreparedDataset, output_dir: Path) -> dict[str, Any]:
    """Scrive viste MLX autorizzate e conserva tutti i record nel manifest."""

    if output_dir.exists() and any(output_dir.iterdir()):
        raise MLXPipelineError(f"directory output non vuota: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    by_split: dict[CorpusSplit, list[dict[str, Any]]] = {split: [] for split in CorpusSplit}
    for prepared in dataset.records:
        if prepared.split is CorpusSplit.TRAIN and prepared.record.training_eligible:
            by_split[CorpusSplit.TRAIN].append(_chat_record(prepared))
        elif (
            prepared.split
            in {
                CorpusSplit.VALIDATION,
                CorpusSplit.TEST,
                CorpusSplit.EXTERNAL_CHALLENGE,
            }
            and prepared.record.evaluation_eligible
        ):
            by_split[prepared.split].append(_chat_record(prepared))
    for values in by_split.values():
        values.sort(key=lambda value: str(value["record_id"]))

    names = {
        CorpusSplit.TRAIN: "train.jsonl",
        CorpusSplit.VALIDATION: "valid.jsonl",
        CorpusSplit.TEST: "test.jsonl",
        CorpusSplit.EXTERNAL_CHALLENGE: "external.jsonl",
    }
    for split, filename in names.items():
        _write_jsonl(output_dir / filename, by_split[split])
    (output_dir / "dataset-manifest.source.json").write_text(
        dumps_dataset_manifest(dataset.manifest), encoding="utf-8"
    )
    (output_dir / "prepared-records.jsonl").write_text(
        dumps_prepared_jsonl(dataset.records), encoding="utf-8"
    )
    (output_dir / "preparation-report.json").write_text(
        dumps_preparation_report(dataset.report), encoding="utf-8"
    )

    leakage_groups: dict[str, str] = {}
    leakage_free = True
    for record in dataset.records:
        previous = leakage_groups.setdefault(record.leakage_group_id, record.split.value)
        leakage_free = leakage_free and previous == record.split.value
    synthetic = [record.record.provenance.synthetic for record in dataset.records]
    files = {}
    for filename in (
        *names.values(),
        "dataset-manifest.source.json",
        "prepared-records.jsonl",
        "preparation-report.json",
    ):
        path = output_dir / filename
        files[filename] = {"sha256": sha256_file(path), "size_bytes": path.stat().st_size}
    snapshot = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "created_at": utc_now(),
        "dataset_id": dataset.manifest.dataset_id,
        "parser_input_contract_version": "2.0.0",
        "candidate_graph_contract_version": "1.0.0",
        "gold_target_contract_version": "1.0.0",
        "prompt_template_version": PROMPT_TEMPLATE_VERSION,
        "training_approved": bool(by_split[CorpusSplit.TRAIN]),
        "leakage_check_passed": bool(dataset.records) and leakage_free,
        "synthetic_only": bool(synthetic) and all(synthetic),
        "counts": {
            "train": len(by_split[CorpusSplit.TRAIN]),
            "valid": len(by_split[CorpusSplit.VALIDATION]),
            "test": len(by_split[CorpusSplit.TEST]),
            "external": len(by_split[CorpusSplit.EXTERNAL_CHALLENGE]),
        },
        "source_records_checksum": dataset.manifest.records_checksum,
        "source_manifest": {
            "path": "dataset-manifest.source.json",
            "sha256": files["dataset-manifest.source.json"]["sha256"],
            "dataset_id": dataset.manifest.dataset_id,
            "manifest_checksum": dataset.manifest.manifest_checksum(),
            "records_checksum": dataset.manifest.records_checksum,
            "prepared_records_sha256": files["prepared-records.jsonl"]["sha256"],
            "preparation_report_sha256": files["preparation-report.json"]["sha256"],
        },
        "files": files,
    }
    snapshot["snapshot_sha256"], snapshot["snapshot_id"] = _snapshot_identity(snapshot)
    _write_json(output_dir / "snapshot-manifest.json", snapshot)
    return snapshot


def create_runtime_smoke_dataset(output_dir: Path) -> dict[str, Any]:
    """Crea fixture tecniche isolate; non e un corpus e non produce metriche."""

    if output_dir.exists() and any(output_dir.iterdir()):
        raise MLXPipelineError(f"directory smoke non vuota: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [_runtime_smoke_chat_record(index) for index in range(8)]
    split_rows = {"train": rows[:4], "valid": rows[4:6], "test": rows[6:]}
    files = {}
    for split, values in split_rows.items():
        path = output_dir / f"{split}.jsonl"
        _write_jsonl(path, values)
        files[path.name] = {"sha256": sha256_file(path), "size_bytes": path.stat().st_size}
    manifest = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "created_at": utc_now(),
        "dataset_id": "runtime-smoke-only",
        "training_approved": False,
        "leakage_check_passed": False,
        "synthetic_only": True,
        "runtime_smoke_only": True,
        "scientific_metrics_allowed": False,
        "parser_input_contract_version": "2.0.0",
        "candidate_graph_contract_version": "1.0.0",
        "prompt_template_version": PROMPT_TEMPLATE_VERSION,
        "counts": {name: len(values) for name, values in split_rows.items()},
        "files": files,
    }
    manifest["snapshot_sha256"], manifest["snapshot_id"] = _snapshot_identity(manifest)
    _write_json(output_dir / "snapshot-manifest.json", manifest)
    return manifest
