"""Tokenizzazione, generazione, scoring ed export locale degli adapter MLX."""

from __future__ import annotations

import json
import math
import re
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ntruth.parser_ai.contract import ParserAIInput, ParserAIOutput, validate_contract_pair
from ntruth.training.calibration import ConfidenceObservation, calibration_report
from ntruth.training.metrics import (
    aggregate_scores,
    confidence_observations,
    parse_prediction_text,
    score_invalid_output,
    score_output,
)
from ntruth.training.mlx_runtime import (
    MLXPipelineError,
    _model_path,
    _write_json,
    iter_jsonl,
    load_profile,
    sha256_file,
    utc_now,
    validate_snapshot_integrity,
    verify_model,
)

EVALUATION_LINEAGE_SCHEMA_VERSION = "1.0.0"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_EVALUATION_SPLIT_FILES = {
    "validation": "valid.jsonl",
    "test": "test.jsonl",
    "external": "external.jsonl",
}
_SNAPSHOT_COUNT_NAMES = {
    "validation": "valid",
    "test": "test",
    "external": "external",
}
_EXPORTABLE_RUN_STATUSES = {"completed_maximum_phases", "early_stopped"}
_EVALUABLE_RUN_STATUSES = {*_EXPORTABLE_RUN_STATUSES, "stopped_memory_ceiling"}


def _read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MLXPipelineError(f"{label} non leggibile: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise MLXPipelineError(f"{label} deve essere un oggetto JSON: {path}")
    return value


def _require_sha256(value: object, *, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise MLXPipelineError(f"{label} assente o non valido")
    return value


def _require_equal(actual: object, expected: object, *, label: str) -> None:
    if actual != expected:
        raise MLXPipelineError(f"lineage non coerente: {label}")


def _verify_best_run(
    profile_path: Path,
    repo_root: Path,
    run_dir: Path,
    *,
    adapter_path: Path | None = None,
) -> dict[str, Any]:
    """Verifica profilo, modello, run-state e adapter ``best`` come un'unita."""

    profile_path = profile_path.resolve()
    repo_root = repo_root.resolve()
    run_dir = run_dir.resolve()
    expected_adapter_dir = run_dir / "best"
    supplied_adapter = (adapter_path or expected_adapter_dir).resolve()
    if supplied_adapter != expected_adapter_dir or supplied_adapter.name != "best":
        raise MLXPipelineError("inferenza consentita soltanto con l'adapter best del run")

    state_path = run_dir / "run-state.json"
    state = _read_json_object(state_path, label="run-state")
    if state.get("schema_version") != "2.0.0":
        raise MLXPipelineError("run-state v2 obbligatorio per inferenza ed export")
    status = state.get("status")
    if status not in _EVALUABLE_RUN_STATUSES:
        raise MLXPipelineError(f"run non valutabile nello stato {status!r}")

    profile_sha256 = sha256_file(profile_path)
    _require_equal(state.get("profile_sha256"), profile_sha256, label="profilo del run")
    model_check = verify_model(profile_path, repo_root)
    model_provenance_sha256 = _require_sha256(
        model_check.get("provenance_sha256"),
        label="provenance modello verificato",
    )
    _require_equal(
        state.get("model_provenance_sha256"),
        model_provenance_sha256,
        label="provenance modello del run",
    )

    best_phase = state.get("best_phase")
    last_completed_phase = state.get("last_completed_phase")
    if (
        isinstance(best_phase, bool)
        or not isinstance(best_phase, int)
        or best_phase < 1
        or isinstance(last_completed_phase, bool)
        or not isinstance(last_completed_phase, int)
        or last_completed_phase < best_phase
    ):
        raise MLXPipelineError("best_phase non valido nel run-state")

    adapter_file = expected_adapter_dir / "adapters.safetensors"
    if adapter_file.is_symlink() or not adapter_file.is_file():
        raise MLXPipelineError("adapter best assente o symlink non ammesso")
    adapter_sha256 = sha256_file(adapter_file)
    expected_adapter_sha256 = _require_sha256(
        state.get("best_adapter_sha256"),
        label="best_adapter_sha256 nel run-state",
    )
    _require_equal(adapter_sha256, expected_adapter_sha256, label="checksum adapter best")

    adapter_config = expected_adapter_dir / "adapter_config.json"
    adapter_config_sha256: str | None = None
    expected_config_sha256 = state.get("best_adapter_config_sha256")
    if adapter_config.exists():
        if adapter_config.is_symlink() or not adapter_config.is_file():
            raise MLXPipelineError("adapter_config best non regolare")
        adapter_config_sha256 = sha256_file(adapter_config)
        _require_equal(
            _require_sha256(
                expected_config_sha256,
                label="best_adapter_config_sha256 nel run-state",
            ),
            adapter_config_sha256,
            label="checksum adapter_config best",
        )
    elif expected_config_sha256 is not None:
        raise MLXPipelineError("adapter_config best mancante rispetto al run-state")

    dataset_snapshot_sha256 = _require_sha256(
        state.get("dataset_snapshot_sha256"),
        label="dataset_snapshot_sha256 nel run-state",
    )
    dataset_manifest_sha256 = _require_sha256(
        state.get("dataset_manifest_sha256"),
        label="dataset_manifest_sha256 nel run-state",
    )
    dataset_snapshot_id = state.get("dataset_snapshot_id")
    if not isinstance(dataset_snapshot_id, str) or not dataset_snapshot_id:
        raise MLXPipelineError("dataset_snapshot_id assente nel run-state")
    smoke_test = state.get("smoke_test")
    if not isinstance(smoke_test, bool):
        raise MLXPipelineError("smoke_test non booleano nel run-state")

    return {
        "schema_version": EVALUATION_LINEAGE_SCHEMA_VERSION,
        "repo_root": str(repo_root),
        "profile_path": str(profile_path),
        "profile_sha256": profile_sha256,
        "model_provenance_sha256": model_provenance_sha256,
        "run_dir": str(run_dir),
        "run_state_path": str(state_path),
        "run_state_sha256": sha256_file(state_path),
        "run_status": status,
        "run_dataset_snapshot_id": dataset_snapshot_id,
        "run_dataset_snapshot_sha256": dataset_snapshot_sha256,
        "run_dataset_manifest_sha256": dataset_manifest_sha256,
        "smoke_test": smoke_test,
        "best_phase": best_phase,
        "adapter_path": str(expected_adapter_dir),
        "adapter_sha256": adapter_sha256,
        "adapter_config_sha256": adapter_config_sha256,
    }


def _verify_evaluation_snapshot(
    evaluation_jsonl: Path,
    declared_split: str,
    run_lineage: Mapping[str, Any],
) -> tuple[Path, dict[str, Any]]:
    filename = _EVALUATION_SPLIT_FILES.get(declared_split)
    if filename is None:
        raise MLXPipelineError(f"split di evaluation non supportato: {declared_split}")
    evaluation_jsonl = evaluation_jsonl.absolute()
    if evaluation_jsonl.is_symlink() or evaluation_jsonl.name != filename:
        raise MLXPipelineError(
            f"mismatch split/file: {declared_split} richiede esattamente {filename}"
        )
    data_dir = evaluation_jsonl.parent.resolve()
    expected_path = data_dir / filename
    if evaluation_jsonl.resolve() != expected_path or not expected_path.is_file():
        raise MLXPipelineError(
            f"mismatch split/file: {declared_split} richiede il file manifestato {filename}"
        )

    smoke_test = run_lineage.get("smoke_test") is True
    snapshot = validate_snapshot_integrity(
        data_dir,
        smoke_test=smoke_test,
        require_nonempty_training_splits=declared_split != "external",
    )
    count_name = _SNAPSHOT_COUNT_NAMES[declared_split]
    if int(snapshot["counts"].get(count_name, 0)) < 1:
        raise MLXPipelineError(f"split di evaluation vuoto: {declared_split}")

    if declared_split in {"validation", "test"}:
        _require_equal(
            snapshot["snapshot_id"],
            run_lineage.get("run_dataset_snapshot_id"),
            label=f"snapshot {declared_split} rispetto al run",
        )
        _require_equal(
            snapshot["snapshot_sha256"],
            run_lineage.get("run_dataset_snapshot_sha256"),
            label=f"checksum snapshot {declared_split} rispetto al run",
        )
        _require_equal(
            snapshot["manifest_sha256"],
            run_lineage.get("run_dataset_manifest_sha256"),
            label=f"manifest snapshot {declared_split} rispetto al run",
        )
    return expected_path, snapshot


def _evaluation_lineage(
    run_lineage: Mapping[str, Any],
    evaluation_path: Path,
    snapshot: Mapping[str, Any],
    declared_split: str,
) -> dict[str, Any]:
    filename = _EVALUATION_SPLIT_FILES[declared_split]
    return {
        **dict(run_lineage),
        "declared_split": declared_split,
        "evaluation_dataset_path": str(evaluation_path.parent),
        "evaluation_file": filename,
        "evaluation_sha256": snapshot["file_hashes"][filename],
        "evaluation_snapshot_id": snapshot["snapshot_id"],
        "evaluation_snapshot_sha256": snapshot["snapshot_sha256"],
        "evaluation_manifest_sha256": snapshot["manifest_sha256"],
        "evaluation_runtime_smoke_only": snapshot["runtime_smoke_only"],
    }


def _percentile(values: list[int], fraction: float) -> float:
    if not values:
        raise ValueError("percentile su insieme vuoto")
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def tokenize_report(
    profile_path: Path,
    repo_root: Path,
    data_dir: Path,
    output_path: Path,
) -> dict[str, Any]:
    """Misura le lunghezze reali senza produrre copie tokenizzate permanenti."""

    profile = load_profile(profile_path)
    model_path = _model_path(repo_root, profile)
    if not (model_path / "model.safetensors").is_file():
        raise MLXPipelineError("modello locale assente; eseguire prima download-model")
    try:
        from transformers import AutoTokenizer
    except ImportError as exc:
        raise MLXPipelineError("transformers non installato; usare uv sync --extra ml") from exc
    tokenizer = AutoTokenizer.from_pretrained(
        model_path,
        local_files_only=True,
        trust_remote_code=False,
    )
    maximum = int(profile["data"]["max_sequence_length"])
    report: dict[str, Any] = {
        "schema_version": "1.0.0",
        "created_at": utc_now(),
        "model_path": str(model_path),
        "maximum_sequence_length": maximum,
        "splits": {},
    }
    all_lengths: list[int] = []
    for split in ("train", "valid", "test"):
        lengths: list[int] = []
        for record in iter_jsonl(data_dir / f"{split}.jsonl"):
            messages = record.get("messages")
            if not isinstance(messages, list):
                raise MLXPipelineError(f"record {split} senza messages")
            try:
                rendered = tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=False,
                    enable_thinking=False,
                )
            except TypeError:
                rendered = tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=False,
                )
            tokens = tokenizer.encode(str(rendered), add_special_tokens=False)
            lengths.append(len(tokens))
        if not lengths:
            raise MLXPipelineError(f"split vuoto durante tokenizzazione: {split}")
        all_lengths.extend(lengths)
        report["splits"][split] = {
            "records": len(lengths),
            "minimum": min(lengths),
            "median": _percentile(lengths, 0.50),
            "p95": _percentile(lengths, 0.95),
            "maximum": max(lengths),
            "over_limit": sum(length > maximum for length in lengths),
        }
    report["overall"] = {
        "records": len(all_lengths),
        "p95": _percentile(all_lengths, 0.95),
        "maximum": max(all_lengths),
        "over_limit": sum(length > maximum for length in all_lengths),
        "gate_passed": all(length <= maximum for length in all_lengths),
    }
    _write_json(output_path, report)
    return report


def _chat_prompt(tokenizer: Any, messages: list[dict[str, Any]]) -> str:
    try:
        return str(
            tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
        )
    except TypeError:
        return str(
            tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        )


def _gold_and_prompt(
    record: dict[str, Any],
) -> tuple[str, list[dict[str, Any]], ParserAIInput, ParserAIOutput]:
    record_id = str(record.get("record_id") or record.get("sample_id") or "")
    if not record_id:
        raise MLXPipelineError("record di evaluation senza record_id/sample_id")
    messages = record.get("messages")
    if not isinstance(messages, list) or len(messages) < 2:
        raise MLXPipelineError(f"record {record_id} senza conversazione completa")
    final = messages[-1]
    if not isinstance(final, dict) or final.get("role") != "assistant":
        raise MLXPipelineError(f"record {record_id}: l'ultimo messaggio deve essere assistant")
    content = final.get("content")
    if not isinstance(content, str):
        raise MLXPipelineError(f"record {record_id}: gold assistant non testuale")
    prompt_messages = [dict(item) for item in messages[:-1] if isinstance(item, dict)]
    user_messages = [item for item in prompt_messages if item.get("role") == "user"]
    if not user_messages or not isinstance(user_messages[-1].get("content"), str):
        raise MLXPipelineError(f"record {record_id}: ParserAIInput user assente")
    try:
        parser_input = ParserAIInput.model_validate_json(user_messages[-1]["content"])
        gold = validate_contract_pair(parser_input, parse_prediction_text(content))
    except (ValueError, TypeError) as exc:
        raise MLXPipelineError(f"record {record_id}: coppia input/gold non valida: {exc}") from exc
    return record_id, prompt_messages, parser_input, gold


def predict_and_score(
    profile_path: Path,
    repo_root: Path,
    evaluation_jsonl: Path,
    adapter_path: Path,
    output_dir: Path,
    *,
    declared_split: str,
    retry_invalid_once: bool = True,
) -> dict[str, Any]:
    """Genera JSON locale, valida lo schema e calcola metriche candidate-fact."""

    profile = load_profile(profile_path)
    model_path = _model_path(repo_root, profile)
    adapter_path = adapter_path.resolve()
    run_lineage = _verify_best_run(
        profile_path,
        repo_root,
        adapter_path.parent,
        adapter_path=adapter_path,
    )
    evaluation_path, snapshot = _verify_evaluation_snapshot(
        evaluation_jsonl,
        declared_split,
        run_lineage,
    )
    lineage = _evaluation_lineage(
        run_lineage,
        evaluation_path,
        snapshot,
        declared_split,
    )
    if output_dir.exists() and any(output_dir.iterdir()):
        raise MLXPipelineError("directory predictions non vuota")
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        from mlx_lm import generate, load
        from mlx_lm.sample_utils import make_sampler
    except ImportError as exc:
        raise MLXPipelineError("mlx-lm non installato; usare uv sync --extra ml") from exc

    loaded = load(str(model_path), adapter_path=str(adapter_path))
    model, tokenizer = loaded[0], loaded[1]
    sampler = make_sampler(temp=0.0)
    maximum_tokens = int(profile["data"].get("generation_max_tokens", 1024))
    prediction_path = output_dir / "predictions.jsonl"
    scores: list[dict[str, Any]] = []
    observations: list[ConfidenceObservation] = []
    rows = list(iter_jsonl(evaluation_path))
    with prediction_path.open("w", encoding="utf-8") as handle:
        for record in rows:
            record_id, prompt_messages, parser_input, gold = _gold_and_prompt(record)
            raw_outputs: list[str] = []
            validation_error: str | None = None
            predicted: ParserAIOutput | None = None
            attempts = 2 if retry_invalid_once else 1
            for attempt in range(attempts):
                messages = list(prompt_messages)
                if attempt:
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "The previous response failed JSON/schema validation. Return exactly "
                                "one JSON object matching ParserAIOutput v2.0.0; do not add facts, prose "
                                "or Markdown. Validation error: " + str(validation_error)[:500]
                            ),
                        }
                    )
                prompt = _chat_prompt(tokenizer, messages)
                raw = generate(
                    model,
                    tokenizer,
                    prompt=prompt,
                    max_tokens=maximum_tokens,
                    sampler=sampler,
                    verbose=False,
                )
                raw_outputs.append(raw)
                try:
                    predicted = validate_contract_pair(parser_input, parse_prediction_text(raw))
                    validation_error = None
                    break
                except (ValueError, TypeError) as exc:
                    validation_error = str(exc)
            if predicted is None:
                score = score_invalid_output(gold, validation_error or "output non valido")
                payload = {
                    "record_id": record_id,
                    "schema_valid": False,
                    "error": validation_error,
                    "attempts": len(raw_outputs),
                    "raw_outputs": raw_outputs,
                    "gold": gold.model_dump(mode="json"),
                    "prediction": None,
                    "score": score,
                }
            else:
                score = score_output(predicted, gold)
                observations.extend(confidence_observations(predicted, gold))
                payload = {
                    "record_id": record_id,
                    "schema_valid": True,
                    "error": None,
                    "attempts": len(raw_outputs),
                    "raw_outputs": raw_outputs,
                    "gold": gold.model_dump(mode="json"),
                    "prediction": predicted.model_dump(mode="json"),
                    "score": score,
                }
            scores.append(score)
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()

    report = aggregate_scores(scores)
    report.update(
        {
            "schema_version": "1.0.0",
            "created_at": utc_now(),
            "evaluation_file": str(evaluation_path),
            "evaluation_sha256": lineage["evaluation_sha256"],
            "adapter_path": str(adapter_path),
            "records": len(rows),
            "confidence_observations": len(observations),
            "retry_invalid_once": retry_invalid_once,
            "declared_split": declared_split,
            "lineage": lineage,
        }
    )
    observations_path = output_dir / "confidence-observations.jsonl"
    with observations_path.open("w", encoding="utf-8") as handle:
        for observation in observations:
            handle.write(
                json.dumps(
                    {"confidence": observation.confidence, "correct": observation.correct},
                    sort_keys=True,
                )
                + "\n"
            )
    report["predictions_sha256"] = sha256_file(prediction_path)
    report["confidence_observations_sha256"] = sha256_file(observations_path)
    _write_json(output_dir / "metrics.json", report)
    return report


def _lineage_path(lineage: Mapping[str, Any], key: str) -> Path:
    value = lineage.get(key)
    if not isinstance(value, str) or not value:
        raise MLXPipelineError(f"lineage priva del path obbligatorio {key}")
    return Path(value).resolve()


_PREDICTION_ROW_KEYS = frozenset(
    {
        "record_id",
        "schema_valid",
        "error",
        "attempts",
        "raw_outputs",
        "gold",
        "prediction",
        "score",
    }
)


def _parse_generated_output(parser_input: ParserAIInput, raw: str) -> ParserAIOutput:
    return validate_contract_pair(parser_input, parse_prediction_text(raw))


def _reconstruct_evaluation(
    evaluation_path: Path,
    predictions_path: Path,
    *,
    retry_invalid_once: bool,
) -> tuple[dict[str, Any], tuple[ConfidenceObservation, ...]]:
    gold_rows = list(iter_jsonl(evaluation_path))
    prediction_rows = list(iter_jsonl(predictions_path))
    if len(gold_rows) != len(prediction_rows):
        raise MLXPipelineError("predictions non allineate al numero di gold manifestati")

    scores: list[dict[str, Any]] = []
    observations: list[ConfidenceObservation] = []
    for gold_row, prediction_row in zip(gold_rows, prediction_rows, strict=True):
        record_id, _messages, parser_input, gold = _gold_and_prompt(gold_row)
        if set(prediction_row) != _PREDICTION_ROW_KEYS:
            raise MLXPipelineError(f"record prediction {record_id}: campi inattesi o mancanti")
        _require_equal(
            prediction_row.get("record_id"),
            record_id,
            label=f"record_id prediction {record_id}",
        )
        _require_equal(
            prediction_row.get("gold"),
            gold.model_dump(mode="json"),
            label=f"gold prediction {record_id} rispetto allo snapshot",
        )

        schema_valid = prediction_row.get("schema_valid")
        if not isinstance(schema_valid, bool):
            raise MLXPipelineError(f"record prediction {record_id}: schema_valid non booleano")
        attempts = prediction_row.get("attempts")
        raw_outputs = prediction_row.get("raw_outputs")
        if (
            isinstance(attempts, bool)
            or not isinstance(attempts, int)
            or attempts < 1
            or not isinstance(raw_outputs, list)
            or len(raw_outputs) != attempts
            or any(not isinstance(raw, str) for raw in raw_outputs)
        ):
            raise MLXPipelineError(f"record prediction {record_id}: tentativi non validi")
        maximum_attempts = 2 if retry_invalid_once else 1
        if attempts > maximum_attempts:
            raise MLXPipelineError(f"record prediction {record_id}: troppi tentativi")

        if schema_valid:
            if prediction_row.get("error") is not None:
                raise MLXPipelineError(f"record prediction {record_id}: errore su output valido")
            for raw in raw_outputs[:-1]:
                try:
                    _parse_generated_output(parser_input, raw)
                except (ValueError, TypeError):
                    continue
                raise MLXPipelineError(
                    f"record prediction {record_id}: retry eseguito dopo un output gia valido"
                )
            try:
                predicted_from_raw = _parse_generated_output(parser_input, raw_outputs[-1])
                predicted = ParserAIOutput.model_validate(prediction_row.get("prediction"))
            except (ValueError, TypeError) as exc:
                raise MLXPipelineError(
                    f"record prediction {record_id}: prediction dichiarata valida non validabile"
                ) from exc
            predicted_payload = predicted.model_dump(mode="json")
            _require_equal(
                prediction_row.get("prediction"),
                predicted_payload,
                label=f"prediction canonica {record_id}",
            )
            _require_equal(
                predicted_from_raw.model_dump(mode="json"),
                predicted_payload,
                label=f"prediction {record_id} rispetto all'output grezzo",
            )
            score = score_output(predicted, gold)
            observations.extend(confidence_observations(predicted, gold))
        else:
            if prediction_row.get("prediction") is not None:
                raise MLXPipelineError(
                    f"record prediction {record_id}: output invalido con prediction"
                )
            expected_attempts = 2 if retry_invalid_once else 1
            if attempts != expected_attempts:
                raise MLXPipelineError(
                    f"record prediction {record_id}: tentativi invalidi non completi"
                )
            last_error: str | None = None
            for raw in raw_outputs:
                try:
                    _parse_generated_output(parser_input, raw)
                except (ValueError, TypeError) as exc:
                    last_error = str(exc)
                    continue
                raise MLXPipelineError(
                    f"record prediction {record_id}: output valido dichiarato invalido"
                )
            error = prediction_row.get("error")
            if not isinstance(error, str) or not error:
                raise MLXPipelineError(f"record prediction {record_id}: errore invalido assente")
            _require_equal(error, last_error, label=f"errore validation prediction {record_id}")
            score = score_invalid_output(gold, error)

        _require_equal(
            prediction_row.get("score"),
            score,
            label=f"score per-record {record_id}",
        )
        scores.append(score)
    return aggregate_scores(scores), tuple(observations)


def _verify_metrics_artifacts(
    metrics_path: Path,
    *,
    expected_split: str | None = None,
    require_real: bool = False,
) -> dict[str, Any]:
    metrics_path = metrics_path.resolve()
    if metrics_path.name != "metrics.json" or not metrics_path.is_file():
        raise MLXPipelineError("metrics.json di evaluation assente")
    metrics = _read_json_object(metrics_path, label="metrics evaluation")
    if metrics.get("schema_version") != "1.0.0":
        raise MLXPipelineError("schema metrics evaluation non supportato")
    lineage = metrics.get("lineage")
    if not isinstance(lineage, dict) or lineage.get("schema_version") != (
        EVALUATION_LINEAGE_SCHEMA_VERSION
    ):
        raise MLXPipelineError("lineage evaluation assente o non supportata")
    declared_split = metrics.get("declared_split")
    if declared_split not in _EVALUATION_SPLIT_FILES:
        raise MLXPipelineError("declared_split non valido nelle metrics")
    if expected_split is not None and declared_split != expected_split:
        raise MLXPipelineError(
            f"lineage split non coerente: atteso {expected_split}, trovato {declared_split}"
        )
    _require_equal(lineage.get("declared_split"), declared_split, label="split nelle metrics")

    run_lineage = _verify_best_run(
        _lineage_path(lineage, "profile_path"),
        _lineage_path(lineage, "repo_root"),
        _lineage_path(lineage, "run_dir"),
        adapter_path=_lineage_path(lineage, "adapter_path"),
    )
    for key, actual in run_lineage.items():
        _require_equal(lineage.get(key), actual, label=f"metrics.{key}")

    evaluation_path = (
        _lineage_path(lineage, "evaluation_dataset_path")
        / _EVALUATION_SPLIT_FILES[str(declared_split)]
    )
    _require_equal(
        Path(str(metrics.get("evaluation_file"))).resolve(),
        evaluation_path,
        label="path del file evaluation",
    )
    verified_path, snapshot = _verify_evaluation_snapshot(
        evaluation_path,
        str(declared_split),
        run_lineage,
    )
    expected_lineage = _evaluation_lineage(
        run_lineage,
        verified_path,
        snapshot,
        str(declared_split),
    )
    for key, actual in expected_lineage.items():
        _require_equal(lineage.get(key), actual, label=f"metrics.{key}")
    _require_equal(
        metrics.get("evaluation_sha256"),
        expected_lineage["evaluation_sha256"],
        label="evaluation_sha256 top-level",
    )
    _require_equal(
        Path(str(metrics.get("adapter_path"))).resolve(),
        _lineage_path(expected_lineage, "adapter_path"),
        label="adapter_path top-level",
    )
    if require_real and snapshot["runtime_smoke_only"]:
        raise MLXPipelineError("lineage validation reale richiesta; runtime smoke rifiutato")

    predictions_path = metrics_path.parent / "predictions.jsonl"
    observations_path = metrics_path.parent / "confidence-observations.jsonl"
    for path, key in (
        (predictions_path, "predictions_sha256"),
        (observations_path, "confidence_observations_sha256"),
    ):
        if path.is_symlink() or not path.is_file():
            raise MLXPipelineError(f"artefatto evaluation assente o symlink: {path.name}")
        _require_equal(
            metrics.get(key),
            sha256_file(path),
            label=f"checksum {path.name}",
        )
    prediction_count = sum(1 for _ in iter_jsonl(predictions_path))
    observation_count = sum(1 for _ in iter_jsonl(observations_path))
    if isinstance(metrics.get("records"), bool) or not isinstance(metrics.get("records"), int):
        raise MLXPipelineError("conteggio predictions non intero nelle metrics")
    if isinstance(metrics.get("confidence_observations"), bool) or not isinstance(
        metrics.get("confidence_observations"), int
    ):
        raise MLXPipelineError("conteggio confidence non intero nelle metrics")
    _require_equal(metrics.get("records"), prediction_count, label="conteggio predictions")
    _require_equal(
        metrics.get("confidence_observations"),
        observation_count,
        label="conteggio confidence",
    )
    retry_invalid_once = metrics.get("retry_invalid_once")
    if not isinstance(retry_invalid_once, bool):
        raise MLXPipelineError("retry_invalid_once non booleano nelle metrics")
    recomputed_metrics, expected_observations = _reconstruct_evaluation(
        evaluation_path,
        predictions_path,
        retry_invalid_once=retry_invalid_once,
    )
    expected_metric_keys = set(recomputed_metrics) | {
        "schema_version",
        "created_at",
        "evaluation_file",
        "evaluation_sha256",
        "adapter_path",
        "confidence_observations",
        "retry_invalid_once",
        "declared_split",
        "lineage",
        "predictions_sha256",
        "confidence_observations_sha256",
    }
    if set(metrics) != expected_metric_keys:
        raise MLXPipelineError("metrics.json contiene campi inattesi o mancanti")
    if not isinstance(metrics.get("created_at"), str) or not metrics["created_at"]:
        raise MLXPipelineError("created_at assente nelle metrics")
    for key, expected in recomputed_metrics.items():
        _require_equal(metrics.get(key), expected, label=f"metrica ricalcolata {key}")
    actual_observations = _load_confidence_observations(observations_path)
    _require_equal(
        actual_observations,
        expected_observations,
        label="confidence-observations ricalcolate",
    )
    return {
        "path": metrics_path,
        "sha256": sha256_file(metrics_path),
        "metrics": metrics,
        "lineage": expected_lineage,
        "run_lineage": run_lineage,
        "snapshot": snapshot,
        "observations_path": observations_path,
        "predictions_path": predictions_path,
    }


def _load_confidence_observations(path: Path) -> tuple[ConfidenceObservation, ...]:
    values: list[ConfidenceObservation] = []
    for row in iter_jsonl(path):
        if set(row) != {"confidence", "correct"}:
            raise MLXPipelineError("campi inattesi nelle confidence-observations")
        confidence = row.get("confidence")
        correct = row.get("correct")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise MLXPipelineError("confidence non numerica nell'artefatto di evaluation")
        if not isinstance(correct, bool):
            raise MLXPipelineError("esito confidence non booleano nell'artefatto di evaluation")
        values.append(ConfidenceObservation(confidence=float(confidence), correct=correct))
    return tuple(values)


def calibrate_predictions(
    observations_jsonl: Path,
    output_path: Path,
    *,
    fit_split: str = "validation",
    maximum_risk: float = 0.10,
    minimum_coverage_count: int = 10,
) -> dict[str, Any]:
    if fit_split != "validation":
        raise MLXPipelineError("la calibrazione accetta soltanto fit_split=validation")
    metrics_path = observations_jsonl.parent / "metrics.json"
    context = _verify_metrics_artifacts(
        metrics_path,
        expected_split="validation",
        require_real=True,
    )
    observations_jsonl = observations_jsonl.resolve()
    _require_equal(
        observations_jsonl,
        context["observations_path"],
        label="path confidence di calibrazione",
    )
    source_metrics = context["metrics"]
    observed_sha256 = sha256_file(observations_jsonl)
    observations = _load_confidence_observations(observations_jsonl)
    if int(source_metrics.get("confidence_observations", -1)) != len(observations):
        raise MLXPipelineError("calibrazione bloccata: conteggio delle confidence non coerente")
    report = calibration_report(
        observations,
        maximum_risk=maximum_risk,
        minimum_coverage_count=minimum_coverage_count,
    )
    report.update(
        {
            "schema_version": "1.0.0",
            "created_at": utc_now(),
            "observations_sha256": observed_sha256,
            "source_metrics_path": str(context["path"]),
            "source_metrics_sha256": context["sha256"],
            "source_declared_split": source_metrics["declared_split"],
            "calibration_parameters": {
                "bins": 10,
                "maximum_risk": maximum_risk,
                "minimum_coverage_count": minimum_coverage_count,
            },
            "lineage": {
                **context["lineage"],
                "source_metrics_path": str(context["path"]),
                "source_metrics_sha256": context["sha256"],
            },
        }
    )
    _write_json(output_path, report)
    return report


def _verify_calibration_artifact(calibration_path: Path) -> dict[str, Any]:
    calibration_path = calibration_path.resolve()
    calibration = _read_json_object(calibration_path, label="calibrazione")
    if calibration.get("schema_version") != "1.0.0":
        raise MLXPipelineError("schema calibrazione non supportato")
    if (
        calibration.get("fit_split") != "validation"
        or calibration.get("test_used_for_fit") is not False
    ):
        raise MLXPipelineError("calibrazione non derivata esclusivamente da validation")
    lineage = calibration.get("lineage")
    if not isinstance(lineage, dict):
        raise MLXPipelineError("lineage calibrazione assente")
    source_metrics_path = _lineage_path(lineage, "source_metrics_path")
    context = _verify_metrics_artifacts(
        source_metrics_path,
        expected_split="validation",
        require_real=True,
    )
    _require_equal(
        calibration.get("source_metrics_sha256"),
        context["sha256"],
        label="metrics sorgente della calibrazione",
    )
    _require_equal(
        calibration.get("observations_sha256"),
        sha256_file(context["observations_path"]),
        label="confidence sorgente della calibrazione",
    )
    parameters = calibration.get("calibration_parameters")
    if not isinstance(parameters, dict):
        raise MLXPipelineError("parametri calibrazione assenti")
    bins = parameters.get("bins")
    maximum_risk = parameters.get("maximum_risk")
    minimum_coverage_count = parameters.get("minimum_coverage_count")
    if isinstance(bins, bool) or not isinstance(bins, int):
        raise MLXPipelineError("bins calibrazione non valido")
    if isinstance(maximum_risk, bool) or not isinstance(maximum_risk, (int, float)):
        raise MLXPipelineError("maximum_risk calibrazione non valido")
    if isinstance(minimum_coverage_count, bool) or not isinstance(minimum_coverage_count, int):
        raise MLXPipelineError("minimum_coverage_count calibrazione non valido")
    recomputed = calibration_report(
        _load_confidence_observations(context["observations_path"]),
        bins=bins,
        maximum_risk=float(maximum_risk),
        minimum_coverage_count=minimum_coverage_count,
    )
    for key in (
        "method",
        "fit_split",
        "count",
        "temperature",
        "before",
        "after",
        "abstention",
        "test_used_for_fit",
    ):
        _require_equal(calibration.get(key), recomputed[key], label=f"ricalcolo {key}")
    expected_lineage = {
        **context["lineage"],
        "source_metrics_path": str(context["path"]),
        "source_metrics_sha256": context["sha256"],
    }
    for key, actual in expected_lineage.items():
        _require_equal(lineage.get(key), actual, label=f"calibrazione.{key}")
    return {
        "path": calibration_path,
        "sha256": sha256_file(calibration_path),
        "calibration": calibration,
        "source_metrics": context,
    }


def export_adapter_bundle(
    profile_path: Path,
    repo_root: Path,
    run_dir: Path,
    output_dir: Path,
    *,
    dataset_manifest: Path,
    metrics_path: Path,
    calibration_path: Path,
) -> dict[str, Any]:
    """Esporta un bundle adapter locale, senza pesi base o dati del corpus."""

    if output_dir.exists() and any(output_dir.iterdir()):
        raise MLXPipelineError("directory export non vuota")
    run_lineage = _verify_best_run(profile_path, repo_root, run_dir)
    if run_lineage["run_status"] not in _EXPORTABLE_RUN_STATUSES:
        raise MLXPipelineError("run arrestato per memoria: export finale bloccato")
    if run_lineage["smoke_test"]:
        raise MLXPipelineError("export finale bloccato per un run runtime smoke")

    dataset_manifest = dataset_manifest.resolve()
    if dataset_manifest.name != "snapshot-manifest.json" or dataset_manifest.is_symlink():
        raise MLXPipelineError("--dataset-manifest deve indicare snapshot-manifest.json")
    snapshot = validate_snapshot_integrity(dataset_manifest.parent)
    _require_equal(
        snapshot["manifest_path"],
        str(dataset_manifest),
        label="path manifest snapshot di export",
    )
    for actual, expected, label in (
        (
            snapshot["snapshot_id"],
            run_lineage["run_dataset_snapshot_id"],
            "snapshot id di export rispetto al run",
        ),
        (
            snapshot["snapshot_sha256"],
            run_lineage["run_dataset_snapshot_sha256"],
            "snapshot hash di export rispetto al run",
        ),
        (
            snapshot["manifest_sha256"],
            run_lineage["run_dataset_manifest_sha256"],
            "manifest hash di export rispetto al run",
        ),
    ):
        _require_equal(actual, expected, label=label)

    metrics_context = _verify_metrics_artifacts(metrics_path, require_real=True)
    calibration_context = _verify_calibration_artifact(calibration_path)
    metrics_split = metrics_context["metrics"]["declared_split"]
    if metrics_split not in {"test", "external"}:
        raise MLXPipelineError("export richiede metrics finali da test oppure external")
    for context_label, context in (
        ("metrics", metrics_context),
        ("calibrazione", calibration_context["source_metrics"]),
    ):
        for key, actual in run_lineage.items():
            _require_equal(
                context["run_lineage"].get(key),
                actual,
                label=f"{context_label}.{key} rispetto al run esportato",
            )
    _require_equal(
        calibration_context["source_metrics"]["snapshot"]["snapshot_sha256"],
        snapshot["snapshot_sha256"],
        label="snapshot calibrazione rispetto al training snapshot",
    )
    if metrics_split == "test":
        _require_equal(
            metrics_context["snapshot"]["snapshot_sha256"],
            snapshot["snapshot_sha256"],
            label="snapshot test rispetto al training snapshot",
        )

    best = run_dir.resolve() / "best"
    output_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(best / "adapters.safetensors", output_dir / "adapters.safetensors")
    if (best / "adapter_config.json").is_file():
        shutil.copyfile(best / "adapter_config.json", output_dir / "adapter_config.json")
    shutil.copyfile(profile_path, output_dir / "training-profile.json")
    shutil.copyfile(run_dir / "run-state.json", output_dir / "run-state.json")
    shutil.copyfile(dataset_manifest, output_dir / "dataset-manifest.json")
    shutil.copyfile(metrics_context["path"], output_dir / "metrics.json")
    shutil.copyfile(calibration_context["path"], output_dir / "calibration.json")

    profile = load_profile(profile_path)
    files = [
        {
            "path": path.relative_to(output_dir).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(output_dir.iterdir())
        if path.is_file() and path.name != "export-manifest.json"
    ]
    manifest = {
        "schema_version": "1.0.0",
        "created_at": utc_now(),
        "artifact_type": "mlx_lora_adapter_bundle",
        "base_repository": profile["model"]["repository"],
        "base_revision": profile["model"]["revision"],
        "base_license": profile["model"]["license"],
        "contains_base_weights": False,
        "contains_training_data": False,
        "lineage": {
            "profile_sha256": run_lineage["profile_sha256"],
            "model_provenance_sha256": run_lineage["model_provenance_sha256"],
            "run_state_sha256": run_lineage["run_state_sha256"],
            "dataset_snapshot_id": snapshot["snapshot_id"],
            "dataset_snapshot_sha256": snapshot["snapshot_sha256"],
            "dataset_manifest_sha256": snapshot["manifest_sha256"],
            "adapter_sha256": run_lineage["adapter_sha256"],
            "metrics_sha256": metrics_context["sha256"],
            "metrics_split": metrics_split,
            "evaluation_snapshot_id": metrics_context["snapshot"]["snapshot_id"],
            "evaluation_snapshot_sha256": metrics_context["snapshot"]["snapshot_sha256"],
            "evaluation_manifest_sha256": metrics_context["snapshot"]["manifest_sha256"],
            "calibration_sha256": calibration_context["sha256"],
            "calibration_source_metrics_sha256": calibration_context["source_metrics"]["sha256"],
        },
        "files": files,
    }
    _write_json(output_dir / "export-manifest.json", manifest)
    return manifest
