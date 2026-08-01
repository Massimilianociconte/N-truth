"""CLI locale di N-Truth (PRD FR-029: CLI e API oltre alla GUI).

Il core gira senza rete. Nessun comando invia file fuori dal workspace.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import typer
from pydantic import ValidationError

from ntruth import DISCLAIMER, SCHEMA_VERSION, __version__
from ntruth.application import (
    DistributionGovernanceBundle,
    DomainAcknowledgementRequired,
    NoUsableFilesError,
    evaluate_distribution_readiness,
    execute_analysis,
)
from ntruth.governance import GovernanceDenied, PrivacyBlocked
from ntruth.ingest.project import Project
from ntruth.ingest.safety import SafetyError
from ntruth.pipeline import AnalysisResult, severity_order
from ntruth.reporting import PrivacyAudit, ShareReadiness
from ntruth.rules.loader import (
    DEFAULT_RULESET_ID,
    DEFAULT_RULESET_VERSION,
    available_rulesets,
    load_ruleset,
)
from ntruth.schemas.core import Severity
from ntruth.schemas.report import DomainTransparency

app = typer.Typer(
    add_completion=False,
    help="N-Truth — ricostruzione verificabile di unita sperimentali e n indipendente.",
    no_args_is_help=True,
)
rules_app = typer.Typer(add_completion=False, help="Ispezione dei ruleset versionati.")
app.add_typer(rules_app, name="rules")

_SEVERITY_MARK = {
    Severity.CRITICAL: "CRITICO",
    Severity.HIGH: "ALTO",
    Severity.MEDIUM: "MEDIO",
    Severity.INSUFFICIENT: "INSUFF.",
    Severity.INFO: "INFO",
}


@app.command()
def analyze(
    source: Path = typer.Argument(..., help="File o cartella con Methods, legend e sample sheet."),
    out: Path = typer.Option(Path("./ntruth-out"), "--out", "-o", help="Cartella di output."),
    project_dir: Path | None = typer.Option(
        None,
        "--project",
        "-p",
        help=(
            "Workspace da riusare esplicitamente "
            "(default: nuovo progetto in <out>/runs/<run-id>/project)."
        ),
    ),
    lang: Literal["it", "en"] = typer.Option(
        "it", "--lang", "-l", help="Lingua dei messaggi: it o en."
    ),
    domain: str = typer.Option(
        "quantitative_microscopy", "--domain", help="Dominio sperimentale dichiarato."
    ),
    acknowledge_unvalidated_domain: bool = typer.Option(
        False,
        "--acknowledge-unvalidated-domain",
        help="Dichiara di aver letto l'avviso sul dominio non validato.",
    ),
    ruleset_id: str = typer.Option(DEFAULT_RULESET_ID, "--ruleset", help="ID del ruleset."),
    ruleset_version: str = typer.Option(
        DEFAULT_RULESET_VERSION, "--ruleset-version", help="Versione del ruleset."
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Stampa solo i percorsi di output."),
) -> None:
    """Analizza documenti locali e produce report JSON, HTML e graph.json."""
    source = source.expanduser()
    if not source.exists():
        typer.secho(f"Percorso inesistente: {source}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    def show_preflight(notice: DomainTransparency) -> None:
        if notice.warning and not acknowledge_unvalidated_domain:
            typer.secho("ATTENZIONE DOMINIO: " + notice.warning, fg=typer.colors.YELLOW, err=True)

    try:
        execution = execute_analysis(
            source,
            out=out,
            project_dir=project_dir,
            language=lang,
            domain=domain,
            ruleset_id=ruleset_id,
            ruleset_version=ruleset_version,
            on_preflight=show_preflight,
            require_domain_acknowledgement=True,
            acknowledged_unvalidated_domain=acknowledge_unvalidated_domain,
        )
    except DomainAcknowledgementRequired as exc:
        typer.secho(
            "Analisi sospesa: confermare esplicitamente il dominio con "
            "--acknowledge-unvalidated-domain. " + str(exc),
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=2) from exc
    except NoUsableFilesError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    result = execution.result
    ingest = execution.ingest
    written = execution.written

    if quiet:
        for path in written.values():
            typer.echo(str(path))
        raise typer.Exit(code=0)

    _print_summary(result, ingest.summary())
    typer.echo(f"\nRun locale: {execution.run_id} · revisione {execution.revision}")
    if execution.privacy_audit.finding_count:
        typer.secho(
            f"Privacy: {execution.privacy_audit.finding_count} finding stand-off; "
            "share/redistribute richiedono policy esplicita.",
            fg=typer.colors.YELLOW,
        )
    else:
        typer.echo("Privacy: nessun identificatore rilevato dallo scanner locale.")
    typer.echo("Distribuzione: non autorizzata; eseguire distribution-check con governance.")
    typer.echo("")
    for label, path in written.items():
        typer.echo(f"  {label:8} {path}")
    typer.echo("")
    typer.secho(DISCLAIMER, fg=typer.colors.BRIGHT_BLACK)


def _print_summary(result: AnalysisResult, ingest_summary: str) -> None:
    report = result.report
    typer.secho(f"\nProgetto: {report.project_name}", bold=True)
    typer.echo(f"  {ingest_summary}")
    typer.echo(
        f"  ruleset {report.versions.ruleset_id}@{report.versions.ruleset_version} "
        f"· schema {report.versions.schema_version}"
    )
    typer.echo(f"  ExperimentBlock: {len(report.blocks)}")

    for index, analysis in enumerate(result.block_analyses, start=1):
        block = analysis.block
        typer.secho(f"\nBlocco {index}/{len(report.blocks)}: {block.title}", bold=True)
        typer.secho("Unita e n per scope", bold=True)
        for assessment in block.unit_assessments:
            factor = (
                block.factor(assessment.scope.factor_id) if assessment.scope.factor_id else None
            )
            endpoint = (
                block.endpoint(assessment.scope.endpoint_id)
                if assessment.scope.endpoint_id
                else None
            )
            scope = factor.name if factor else "nessun fattore"
            if endpoint:
                scope += f" / {endpoint.name}"
            independent = (
                str(assessment.n_independent)
                if assessment.n_independent is not None
                else "non determinabile"
            )
            typer.echo(
                f"  {scope}\n"
                f"    unita sperimentale : {assessment.experimental_unit or 'non determinata'}\n"
                f"    n dichiarato       : {assessment.n_declared if assessment.n_declared is not None else 'non riportato'}\n"
                f"    n osservazionale   : {assessment.n_observational if assessment.n_observational is not None else 'non determinato'}\n"
                f"    n indipendente     : {independent}  ({assessment.inferability.value})"
            )

        if block.alerts:
            typer.secho("\nAlert", bold=True)
            for alert in sorted(block.alerts, key=lambda item: severity_order(item.severity)):
                colour = {
                    Severity.CRITICAL: typer.colors.RED,
                    Severity.HIGH: typer.colors.YELLOW,
                    Severity.MEDIUM: typer.colors.BRIGHT_YELLOW,
                    Severity.INSUFFICIENT: typer.colors.BLUE,
                    Severity.INFO: typer.colors.CYAN,
                }[alert.severity]
                typer.secho(
                    f"  [{_SEVERITY_MARK[alert.severity]}] {alert.rule_id}",
                    fg=colour,
                    nl=False,
                )
                typer.echo(f" {alert.message}")

        if block.questions:
            typer.secho("\nDomande aperte", bold=True)
            for question in block.questions:
                typer.echo(f"  - {question.text}")

        if analysis.abstention.abstained:
            typer.secho(f"\n{analysis.abstention.describe()}", fg=typer.colors.BLUE)


@app.command("distribution-check")
def distribution_check(
    revision_dir: Path = typer.Argument(
        ...,
        help="Directory di revisione contenente privacy-scan.json e share-readiness.json.",
    ),
    governance_bundle: Path = typer.Option(
        ...,
        "--governance",
        help=(
            "JSON locale con governance_records, license_manifests, redaction_manifests "
            "e, per redacted_copy, redacted_derivatives verificabili."
        ),
    ),
    action: str = typer.Option("share", "--action", help="share oppure redistribute."),
    privacy_policy: str = typer.Option(
        "blocked",
        "--privacy-policy",
        help="blocked, acknowledged oppure redacted_copy.",
    ),
    acknowledgement_reference: str | None = typer.Option(
        None,
        "--acknowledgement-reference",
        help="Riferimento locale alla revisione privacy esplicita.",
    ),
) -> None:
    """Valuta i gate di distribuzione; non copia e non invia alcun file."""

    revision_dir = revision_dir.expanduser()
    try:
        readiness = ShareReadiness.model_validate_json(
            (revision_dir / "share-readiness.json").read_text(encoding="utf-8")
        )
        audit = PrivacyAudit.model_validate_json(
            (revision_dir / "privacy-scan.json").read_text(encoding="utf-8")
        )
        governance = DistributionGovernanceBundle.model_validate_json(
            governance_bundle.expanduser().read_text(encoding="utf-8")
        )
        evaluation = evaluate_distribution_readiness(
            readiness,
            audit,
            governance,
            action=action,
            privacy_policy=privacy_policy,
            acknowledgement_reference=acknowledgement_reference,
        )
    except (OSError, ValidationError, ValueError, GovernanceDenied, PrivacyBlocked) as exc:
        typer.secho(f"Distribuzione non autorizzata: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    typer.secho(
        f"Gate {evaluation.action.value}: autorizzato per {evaluation.artifact_scope}.",
        fg=typer.colors.GREEN,
    )
    typer.echo("Nessun trasferimento eseguito.")


@app.command()
def verify(
    project_dir: Path = typer.Argument(..., help="Cartella del progetto da verificare."),
) -> None:
    """Verifica i checksum dei file registrati nel progetto (PRD FR-007)."""
    try:
        project = Project.open(project_dir.expanduser())
    except (OSError, ValidationError, SafetyError) as exc:
        typer.secho(f"Workspace non verificabile: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc
    problems = project.verify_integrity()
    if problems:
        for problem in problems:
            typer.secho(f"  {problem}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    typer.secho(
        f"Integrita verificata: {len(project.manifest.files)} file, "
        f"checksum manifest {project.manifest.checksum()[:16]}",
        fg=typer.colors.GREEN,
    )


@rules_app.command("list")
def rules_list(
    ruleset_id: str = typer.Option(DEFAULT_RULESET_ID, "--ruleset"),
    ruleset_version: str = typer.Option(DEFAULT_RULESET_VERSION, "--ruleset-version"),
    domain: str | None = typer.Option(None, "--domain", "-d", help="Filtra per dominio."),
) -> None:
    """Elenca le regole attive con severita e dominio."""
    ruleset = load_ruleset(ruleset_id, ruleset_version)
    rules = ruleset.by_domain(domain) if domain else list(ruleset.rules)
    typer.secho(
        f"{ruleset.ruleset_id}@{ruleset.version} — {len(rules)} regole "
        f"(checksum {ruleset.checksum()[:16]})",
        bold=True,
    )
    for rule in rules:
        typer.echo(f"  {rule.rule_id:9} [{rule.severity.value:12}] {rule.domain:22} {rule.title}")


@rules_app.command("show")
def rules_show(
    rule_id: str = typer.Argument(..., help="ID della regola, es. MIC-004."),
    ruleset_id: str = typer.Option(DEFAULT_RULESET_ID, "--ruleset"),
    ruleset_version: str = typer.Option(DEFAULT_RULESET_VERSION, "--ruleset-version"),
) -> None:
    """Mostra precondizioni, eccezioni e condizioni di astensione di una regola."""
    ruleset = load_ruleset(ruleset_id, ruleset_version)
    rule = ruleset.rule(rule_id.upper())
    if rule is None:
        typer.secho(f"Regola '{rule_id}' non trovata in {ruleset.ruleset_id}", fg=typer.colors.RED)
        raise typer.Exit(code=2)
    typer.secho(f"{rule.rule_id}@{rule.version} — {rule.title}", bold=True)
    typer.echo(f"  dominio     : {rule.domain}")
    typer.echo(f"  severita    : {rule.severity.value}")
    typer.echo("  precondizioni:")
    for expression, normalized in zip(
        rule.preconditions, rule.normalized_preconditions(), strict=True
    ):
        suffix = f"   ->  {normalized}" if expression != normalized else ""
        typer.echo(f"    - {expression}{suffix}")
    if rule.exceptions:
        typer.echo("  eccezioni:")
        for expression in rule.normalized_exceptions():
            typer.echo(f"    - {expression}")
    if rule.abstain_if:
        typer.echo("  astensione se:")
        for expression in rule.normalized_abstentions():
            typer.echo(f"    - {expression}")
    if rule.questions:
        typer.echo("  domande:")
        for question in rule.questions:
            typer.echo(f"    - {question}")
    if rule.references:
        typer.echo(f"  riferimenti : {', '.join(rule.references)}")
    typer.echo(f"  messaggio   : {rule.message('it')}")


@rules_app.command("predicates")
def rules_predicates() -> None:
    """Elenca i predicati disponibili per scrivere nuove regole."""
    from ntruth.rules.predicates import REGISTRY

    typer.secho(f"{len(REGISTRY)} predicati disponibili", bold=True)
    for name in sorted(REGISTRY):
        typer.echo(f"  {name}")


@rules_app.command("paths")
def rules_paths() -> None:
    """Mostra dove vengono cercati i ruleset."""
    for path in available_rulesets():
        typer.echo(f"  {path}")


@app.command()
def version() -> None:
    """Versioni di software e contratti."""
    typer.echo(f"N-Truth {__version__} · schema {SCHEMA_VERSION}")


if __name__ == "__main__":  # pragma: no cover
    app()
