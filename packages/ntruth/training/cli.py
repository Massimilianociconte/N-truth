"""CLI separata per la corsia MLX locale e opzionale."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import typer

from ntruth.training import PreparationConfig, SplitRatios, load_supervised_jsonl, prepare_dataset
from ntruth.training.mlx_dataset import (
    create_runtime_smoke_dataset,
    export_mlx_dataset,
)
from ntruth.training.mlx_inference import (
    calibrate_predictions,
    export_adapter_bundle,
    predict_and_score,
    tokenize_report,
)
from ntruth.training.mlx_runtime import (
    MLXPipelineError,
    doctor,
    download_model,
    run_training,
    verify_model,
)


def _default_profile() -> Path:
    from ntruth.model_backends.registry import default_profile_path

    return default_profile_path()


DEFAULT_PROFILE = _default_profile()

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="N-Truth ML — preparazione governata e QLoRA locale con MLX/Metal.",
)


def _emit(value: object) -> None:
    typer.echo(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _fail(exc: Exception) -> None:
    typer.secho(f"N-Truth ML: {exc}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1) from exc


@app.command()
def check(
    profile: Path = typer.Option(DEFAULT_PROFILE, "--profile", help="Profilo MLX fissato."),
    repo: Path = typer.Option(Path("."), "--repo", help="Root del checkout N-Truth."),
) -> None:
    """Verifica piattaforma, RAM, disco, runtime e presenza del modello."""

    try:
        status = doctor(profile.resolve(), repo.resolve())
    except (MLXPipelineError, OSError, ValueError) as exc:
        _fail(exc)
    _emit(status)
    if not status["ready_to_train"]:
        raise typer.Exit(code=2)


@app.command("download-model")
def download_model_command(
    confirm: bool = typer.Option(
        False,
        "--confirm-license-and-download",
        help="Conferma il download dello snapshot Apache-2.0 fissato dal profilo.",
    ),
    profile: Path = typer.Option(DEFAULT_PROFILE, "--profile"),
    repo: Path = typer.Option(Path("."), "--repo"),
) -> None:
    """Scarica soltanto il modello selezionato dopo i gate di spazio/hardware."""

    if not confirm:
        _fail(ValueError("serve --confirm-license-and-download"))
    try:
        result = download_model(profile.resolve(), repo.resolve())
    except (MLXPipelineError, OSError, ValueError) as exc:
        _fail(exc)
    _emit(result)


@app.command("verify-model")
def verify_model_command(
    profile: Path = typer.Option(DEFAULT_PROFILE, "--profile"),
    repo: Path = typer.Option(Path("."), "--repo"),
) -> None:
    """Ricalcola dimensioni e SHA-256 dello snapshot locale."""

    try:
        result = verify_model(profile.resolve(), repo.resolve())
    except (MLXPipelineError, OSError, ValueError) as exc:
        _fail(exc)
    _emit(result)


@app.command()
def prepare(
    source: Path = typer.Argument(..., help="JSONL SupervisedRecord approvato."),
    out: Path = typer.Option(..., "--out", help="Nuovo snapshot locale MLX."),
    seed: str = typer.Option("ntruth-dataset-v1", "--seed"),
    train_ratio: float = typer.Option(0.8, "--train-ratio"),
    validation_ratio: float = typer.Option(0.1, "--validation-ratio"),
    test_ratio: float = typer.Option(0.1, "--test-ratio"),
    near_duplicate_threshold: float = typer.Option(0.92, "--near-duplicate-threshold"),
) -> None:
    """Normalizza, deduplica, separa e converte annotazioni autorizzate."""

    try:
        records = load_supervised_jsonl(source.resolve())
        prepared = prepare_dataset(
            records,
            config=PreparationConfig(
                seed=seed,
                near_duplicate_threshold=near_duplicate_threshold,
                split_ratios=SplitRatios(
                    train=train_ratio,
                    validation=validation_ratio,
                    test=test_ratio,
                ),
                require_training_eligible=True,
                fail_on_error=True,
            ),
        )
        result = export_mlx_dataset(prepared, out.resolve())
    except (MLXPipelineError, OSError, ValueError) as exc:
        _fail(exc)
    _emit(result)


@app.command("make-smoke-data")
def make_smoke_data(
    out: Path = typer.Option(..., "--out", help="Directory locale nuova per fixture runtime."),
) -> None:
    """Crea otto esempi tecnici; non sono corpus, gold o validation scientifica."""

    try:
        result = create_runtime_smoke_dataset(out.resolve())
    except (MLXPipelineError, OSError, ValueError) as exc:
        _fail(exc)
    _emit(result)


@app.command()
def tokenize(
    data: Path = typer.Argument(..., help="Snapshot MLX con train/valid/test.jsonl."),
    out: Path = typer.Option(..., "--out", help="Report JSON delle lunghezze."),
    profile: Path = typer.Option(DEFAULT_PROFILE, "--profile"),
    repo: Path = typer.Option(Path("."), "--repo"),
) -> None:
    """Misura token e troncamenti usando il tokenizer locale fissato."""

    try:
        result = tokenize_report(profile.resolve(), repo.resolve(), data.resolve(), out.resolve())
    except (MLXPipelineError, OSError, ValueError) as exc:
        _fail(exc)
    _emit(result)
    if not result["overall"]["gate_passed"]:
        raise typer.Exit(code=2)


@app.command()
def train(
    data: Path = typer.Argument(..., help="Snapshot MLX approvato."),
    out: Path = typer.Option(..., "--out", help="Directory locale del run."),
    seed: int = typer.Option(13, "--seed"),
    resume: bool = typer.Option(False, "--resume"),
    runtime_smoke_only: bool = typer.Option(
        False,
        "--runtime-smoke-only",
        help="Massimo due iterazioni su fixture tecniche, senza valore scientifico.",
    ),
    profile: Path = typer.Option(DEFAULT_PROFILE, "--profile"),
    repo: Path = typer.Option(Path("."), "--repo"),
) -> None:
    """Esegue QLoRA locale con checkpoint, ripresa ed early stopping a fasi."""

    try:
        result = run_training(
            profile.resolve(),
            repo.resolve(),
            data.resolve(),
            out.resolve(),
            seed=seed,
            smoke_test=runtime_smoke_only,
            resume=resume,
        )
    except (MLXPipelineError, OSError, ValueError) as exc:
        _fail(exc)
    _emit(result)


@app.command("benchmark-resources")
def benchmark_resources(
    out: Path = typer.Option(
        Path("benchmarks/runtime"),
        "--out",
        help="Directory dove scrivere budget misurato e protocol report.",
    ),
    model: Path | None = typer.Option(
        None,
        "--model",
        help="Snapshot MLX locale (default: local_path del profilo).",
    ),
    profile: Path = typer.Option(DEFAULT_PROFILE, "--profile"),
    repo: Path = typer.Option(Path("."), "--repo"),
    include_cpu_stages: bool = typer.Option(
        True,
        "--include-cpu-stages/--mlx-only",
        help="Include rules/hard/semantic stages oltre a mlx_generate.",
    ),
    quick: bool = typer.Option(
        False,
        "--quick",
        help="Una sola replica e workload ridotto (smoke). Non usare per release.",
    ),
) -> None:
    """Misura peak RAM/swap/latency reali e scrive RuntimeResourceBudget.

    Esegue load+warmup+generate sul modello locale e (opzionale) stage
    deterministici. Non inventa picchi: senza misure complete fallisce.
    """

    from ntruth.training.mlx_runtime import load_profile
    from ntruth.training.runtime_benchmark import (
        DEFAULT_WORKLOADS,
        ProfileWorkload,
        run_full_runtime_benchmark,
    )
    from ntruth.runtime_resources.schema import RuntimeProfileName

    try:
        loaded = load_profile(profile.resolve())
        model_path = (
            Path(model).resolve()
            if model is not None
            else (repo.resolve() / loaded["model"]["local_path"]).resolve()
        )
        if quick:
            workloads = (
                ProfileWorkload(
                    RuntimeProfileName.LOW_MEMORY,
                    prompt_chars=800,
                    max_new_tokens=32,
                    replicates=1,
                ),
                ProfileWorkload(
                    RuntimeProfileName.BALANCED,
                    prompt_chars=1_600,
                    max_new_tokens=48,
                    replicates=1,
                ),
                ProfileWorkload(
                    RuntimeProfileName.QUALITY,
                    prompt_chars=2_400,
                    max_new_tokens=64,
                    replicates=1,
                ),
            )
        else:
            workloads = DEFAULT_WORKLOADS
        result = run_full_runtime_benchmark(
            model_path=model_path,
            output_dir=out.resolve(),
            workloads=workloads,
            include_cpu_stages=include_cpu_stages,
        )
    except (MLXPipelineError, OSError, ValueError, KeyError) as exc:
        _fail(exc)
    _emit(result)


@app.command()
def predict(
    evaluation: Path = typer.Argument(..., help="JSONL locale con messages e gold assistant."),
    adapter: Path = typer.Option(..., "--adapter", help="Directory adapter best."),
    out: Path = typer.Option(..., "--out"),
    split: Literal["validation", "test", "external"] = typer.Option(..., "--split"),
    retry_invalid_once: bool = typer.Option(True, "--retry-invalid-once/--no-retry"),
    resource_budget: Path | None = typer.Option(
        None,
        "--resource-budget",
        help="Budget RuntimeResource misurato (JSON). Opzionale; senza path resta il percorso legacy.",
    ),
    resource_profile: str = typer.Option(
        "BALANCED",
        "--resource-profile",
        help="Profilo operativo LOW_MEMORY|BALANCED|QUALITY del budget misurato.",
    ),
    profile: Path = typer.Option(DEFAULT_PROFILE, "--profile"),
    repo: Path = typer.Option(Path("."), "--repo"),
) -> None:
    """Genera, valida col contratto e calcola metriche strutturate."""

    try:
        result = predict_and_score(
            profile.resolve(),
            repo.resolve(),
            evaluation.resolve(),
            adapter.resolve(),
            out.resolve(),
            declared_split=split,
            retry_invalid_once=retry_invalid_once,
            resource_budget_path=resource_budget.resolve() if resource_budget else None,
            resource_profile=resource_profile,
        )
    except (MLXPipelineError, OSError, ValueError) as exc:
        _fail(exc)
    _emit(result)


@app.command()
def calibrate(
    observations: Path = typer.Argument(..., help="Confidence prodotte sul validation split."),
    out: Path = typer.Option(..., "--out"),
    fit_split: Literal["validation"] = typer.Option("validation", "--fit-split"),
    maximum_risk: float = typer.Option(0.10, "--maximum-risk"),
    minimum_coverage_count: int = typer.Option(10, "--minimum-coverage-count"),
) -> None:
    """Stima temperatura e soglia di astensione; il test non e accettato."""

    try:
        result = calibrate_predictions(
            observations.resolve(),
            out.resolve(),
            fit_split=fit_split,
            maximum_risk=maximum_risk,
            minimum_coverage_count=minimum_coverage_count,
        )
    except (MLXPipelineError, OSError, ValueError) as exc:
        _fail(exc)
    _emit(result)


@app.command("export-adapter")
def export_adapter(
    run: Path = typer.Argument(..., help="Run MLX completato."),
    dataset_manifest: Path = typer.Option(..., "--dataset-manifest"),
    out: Path = typer.Option(..., "--out"),
    metrics: Path = typer.Option(..., "--metrics"),
    calibration: Path = typer.Option(..., "--calibration"),
    profile: Path = typer.Option(DEFAULT_PROFILE, "--profile"),
    repo: Path = typer.Option(Path("."), "--repo"),
) -> None:
    """Esporta adapter, provenance e metriche senza dati o pesi base."""

    try:
        result = export_adapter_bundle(
            profile.resolve(),
            repo.resolve(),
            run.resolve(),
            out.resolve(),
            dataset_manifest=dataset_manifest.resolve(),
            metrics_path=metrics.resolve(),
            calibration_path=calibration.resolve(),
        )
    except (MLXPipelineError, OSError, ValueError) as exc:
        _fail(exc)
    _emit(result)
