"""API locale con lo stesso caso d'uso della CLI (PRD FR-029)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from ntruth import SCHEMA_VERSION, __version__
from ntruth.api.sessions import (
    SessionArtifactNotFound,
    SessionBlockNotFound,
    SessionNotFound,
    SessionRegistry,
    SessionUpdate,
)
from ntruth.application import (
    DistributionGovernanceBundle,
    DomainAcknowledgementRequired,
    NoUsableFilesError,
    RedactedDerivativeMaterial,
    evaluate_distribution_readiness,
    execute_analysis,
)
from ntruth.corrections import CorrectionEngineError, CorrectionLedger
from ntruth.governance import (
    GovernanceDenied,
    GovernanceRecord,
    PrivacyBlocked,
    PrivacyPolicy,
    RedactionManifest,
)
from ntruth.ingest.safety import SafetyError
from ntruth.reporting import read_json, report_to_dict
from ntruth.rules.loader import (
    DEFAULT_RULESET_ID,
    DEFAULT_RULESET_VERSION,
    RulesetNotFound,
)
from ntruth.schemas.core import Provenance, ProvenanceKind, stable_id
from ntruth.schemas.experiment import (
    Correction,
    CorrectionReason,
    Estimand,
    InferenceTarget,
    InferenceTargetStatus,
)
from ntruth.schemas.graph import NodeType
from ntruth.schemas.manifest import LicenseManifest
from ntruth.transparency import SUPPORTED_DOMAINS, VALIDATED_DOMAINS, assess_domain


class DomainPreflightRequest(BaseModel):
    domain: str = "quantitative_microscopy"


class AnalyzeRequest(BaseModel):
    source: str
    out: str = "./ntruth-out"
    project_dir: str | None = None
    language: Literal["it", "en"] = "it"
    domain: str = "quantitative_microscopy"
    ruleset_id: str = DEFAULT_RULESET_ID
    ruleset_version: str = DEFAULT_RULESET_VERSION
    acknowledge_unvalidated_domain: bool = False


class CorrectionDraft(BaseModel):
    """Input umano privo di ID/sequence, assegnati dal ledger sul server."""

    reason: CorrectionReason
    rationale: str = Field(min_length=8, max_length=4000)
    patch: tuple[dict[str, Any], ...] = Field(min_length=1, max_length=32)
    evidence_ids: tuple[str, ...] = ()
    reviewer_role: str = Field(default="reviewer", min_length=2, max_length=64)
    verified: bool = False


class ApplyCorrectionRequest(BaseModel):
    session_id: str
    block_id: str
    correction: CorrectionDraft


class NavigateCorrectionRequest(BaseModel):
    session_id: str
    block_id: str


class InferenceTargetDraft(BaseModel):
    """Target dichiarato dall'utente; nessun campo viene completato dal server."""

    target_id: str | None = None
    question_text: str = Field(min_length=3, max_length=4000)
    claim_text: str = Field(default="", max_length=4000)
    population_of_inference: str = Field(min_length=2, max_length=2000)
    factor_ids: tuple[str, ...] = Field(min_length=1)
    contrast_ids: tuple[str, ...] = Field(min_length=1)
    endpoint_ids: tuple[str, ...] = Field(min_length=1)
    target_biological_unit: NodeType
    evidence_ids: tuple[str, ...] = ()
    rationale: str = Field(min_length=8, max_length=4000)
    reviewer_role: str = Field(default="researcher", min_length=2, max_length=64)
    estimands: tuple[EstimandDraft, ...] = Field(min_length=1)


class EstimandDraft(BaseModel):
    """Estimand minimo dichiarato dall'utente, mai completato dal server."""

    estimand_id: str | None = None
    endpoint_id: str
    effect_measure: str = Field(min_length=1, max_length=500)
    target_population_or_unit: str = Field(min_length=1, max_length=2000)
    generalization_level: str = Field(min_length=1, max_length=1000)
    factor_ids: tuple[str, ...] = Field(min_length=1)
    timepoint: str | None = Field(default=None, max_length=500)
    condition: str | None = Field(default=None, max_length=1000)
    evidence_ids: tuple[str, ...] = ()


class UpsertInferenceTargetRequest(BaseModel):
    session_id: str
    block_id: str
    target: InferenceTargetDraft


class DistributionReadinessRequest(BaseModel):
    session_id: str
    action: Literal["share", "redistribute"]
    governance_records: tuple[GovernanceRecord, ...] = ()
    license_manifests: tuple[LicenseManifest, ...] = ()
    redaction_manifests: tuple[RedactionManifest, ...] = ()
    redacted_derivatives: tuple[RedactedDerivativeMaterial, ...] = ()
    privacy_policy: PrivacyPolicy = PrivacyPolicy.BLOCKED
    acknowledgement_reference: str | None = None


def create_app() -> Any:
    """Crea l'app senza rendere FastAPI una dipendenza del core."""

    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.middleware.trustedhost import TrustedHostMiddleware
        from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
        from fastapi.staticfiles import StaticFiles
    except ModuleNotFoundError as exc:  # pragma: no cover - dipende dall'extra installato
        raise RuntimeError("FastAPI non installato: usare `pip install 'ntruth[api]'`") from exc

    api = FastAPI(
        title="N-Truth local API",
        version=__version__,
        description="API locale/offline per la stessa pipeline usata dalla CLI.",
    )
    api.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "testserver"],
    )
    sessions = SessionRegistry()

    @api.get("/health")
    @api.get("/v1/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "ntruth",
            "version": __version__,
            "schema_version": SCHEMA_VERSION,
            "offline_core": True,
            "supported_domains": list(SUPPORTED_DOMAINS),
            "validated_domains": list(VALIDATED_DOMAINS),
            "privacy_scan": "local_stand_off",
            "distribution_gate": "explicit_fail_closed",
        }

    @api.post("/preflight")
    @api.post("/v1/preflight")
    def preflight(payload: DomainPreflightRequest) -> dict[str, Any]:
        return assess_domain(payload.domain).model_dump(mode="json")

    @api.post("/analyze")
    @api.post("/v1/analyze")
    def analyze(payload: AnalyzeRequest) -> dict[str, Any]:
        notice = assess_domain(payload.domain)
        if notice.requires_acknowledgement and not payload.acknowledge_unvalidated_domain:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "domain_acknowledgement_required",
                    "message": notice.warning,
                    "domain_transparency": notice.model_dump(mode="json"),
                },
            )
        try:
            execution = execute_analysis(
                Path(payload.source),
                out=Path(payload.out),
                project_dir=Path(payload.project_dir) if payload.project_dir else None,
                language=payload.language,
                domain=payload.domain,
                ruleset_id=payload.ruleset_id,
                ruleset_version=payload.ruleset_version,
                require_domain_acknowledgement=True,
                acknowledged_unvalidated_domain=payload.acknowledge_unvalidated_domain,
            )
        except DomainAcknowledgementRequired as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "domain_acknowledgement_required",
                    "message": str(exc),
                    "domain_transparency": exc.transparency.model_dump(mode="json"),
                },
            ) from exc
        except (FileNotFoundError, NoUsableFilesError, SafetyError, RulesetNotFound) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        session = sessions.create(execution)
        return {
            "report": report_to_dict(execution.result.report),
            "ingest_summary": execution.ingest.summary(),
            "artifacts": {name: str(path) for name, path in execution.written.items()},
            "domain_transparency": execution.transparency.model_dump(mode="json"),
            "session_id": session.id,
            "run_id": execution.run_id,
            "revision": execution.revision,
            "output_dir": str(execution.run_dir),
            "privacy_audit": execution.privacy_audit.model_dump(mode="json"),
            "share_readiness": execution.share_readiness.model_dump(mode="json"),
        }

    @api.get("/report")
    @api.get("/v1/report")
    @api.get("/v1/reports")
    def report(path: str) -> dict[str, Any]:
        report_path = Path(path).expanduser()
        if not report_path.is_file():
            raise HTTPException(status_code=404, detail=f"Report non trovato: {report_path}")
        try:
            loaded = read_json(report_path)
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=f"Report non valido: {exc}") from exc
        return report_to_dict(loaded)

    def correction_response(update: SessionUpdate) -> dict[str, Any]:
        ledger = update.ledger
        return {
            "report": report_to_dict(update.execution.result.report),
            "block_id": ledger.current_block.id,
            "audit_trail": [event.to_dict() for event in ledger.audit_trail],
            "active_correction_ids": list(ledger.active_correction_ids),
            "redo_correction_ids": list(ledger.redo_correction_ids),
            "candidate_annotations": update.candidate_payload,
            "candidate_artifact_name": update.candidate_artifact_name,
            "recalculation_ms": update.elapsed_ms,
            "artifacts": {name: str(path) for name, path in update.execution.written.items()},
            "run_id": update.execution.run_id,
            "revision": update.execution.revision,
            "privacy_audit": update.execution.privacy_audit.model_dump(mode="json"),
            "share_readiness": update.execution.share_readiness.model_dump(mode="json"),
        }

    @api.post("/v1/corrections/apply")
    def apply_correction(payload: ApplyCorrectionRequest) -> dict[str, Any]:
        try:
            session = sessions.get(payload.session_id)
            draft = payload.correction

            def build_correction(ledger: CorrectionLedger) -> Correction:
                return Correction(
                    id=stable_id(
                        "cor",
                        payload.block_id,
                        ledger.current_checksum,
                        ledger.next_sequence,
                        draft.reason,
                        draft.rationale,
                        json.dumps(draft.patch, sort_keys=True, ensure_ascii=False),
                    ),
                    sequence=ledger.next_sequence,
                    reason=draft.reason,
                    rationale=draft.rationale,
                    patch=draft.patch,
                    evidence_ids=draft.evidence_ids,
                    reviewer_role=draft.reviewer_role,
                    # La verifica/adjudication non può essere auto-assegnata dal client.
                    verified=False,
                )

            return correction_response(session.apply_generated(payload.block_id, build_correction))
        except (SessionNotFound, SessionBlockNotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except CorrectionEngineError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @api.post("/v1/design/inference-targets/confirm")
    def confirm_inference_target(payload: UpsertInferenceTargetRequest) -> dict[str, Any]:
        """Registra una conferma umana come patch auditabile e ricompila il design."""

        try:
            session = sessions.get(payload.session_id)
            draft = payload.target

            def build_target_correction(ledger: CorrectionLedger) -> Correction:
                current = ledger.current_block
                known_factors = {factor.id for factor in current.factors}
                known_endpoints = {endpoint.id for endpoint in current.endpoints}
                target_factors = set(draft.factor_ids)
                target_endpoints = set(draft.endpoint_ids)
                if not target_factors <= known_factors:
                    raise HTTPException(status_code=422, detail="Factor del target non trovato")
                if not target_endpoints <= known_endpoints:
                    raise HTTPException(status_code=422, detail="Endpoint del target non trovato")
                covered_endpoints = {item.endpoint_id for item in draft.estimands}
                if covered_endpoints != target_endpoints:
                    raise HTTPException(
                        status_code=422,
                        detail="Serve esattamente un estimand minimo per ogni endpoint del target",
                    )
                for item in draft.estimands:
                    if not target_factors <= set(item.factor_ids):
                        raise HTTPException(
                            status_code=422,
                            detail="Ogni estimand deve coprire tutti i factor_ids del target",
                        )
                target_index: int | None = None
                if draft.target_id is not None:
                    target_index = next(
                        (
                            index
                            for index, item in enumerate(current.inference_targets)
                            if item.id == draft.target_id
                        ),
                        None,
                    )
                    if target_index is None:
                        raise HTTPException(
                            status_code=404,
                            detail="Target inferenziale non trovato",
                        )

                target_id = draft.target_id or stable_id(
                    "itr",
                    payload.block_id,
                    draft.question_text,
                    draft.population_of_inference,
                    draft.factor_ids,
                    draft.contrast_ids,
                    draft.endpoint_ids,
                    draft.target_biological_unit,
                )
                target = InferenceTarget(
                    id=target_id,
                    question_text=draft.question_text,
                    claim_text=draft.claim_text,
                    population_of_inference=draft.population_of_inference,
                    factor_ids=draft.factor_ids,
                    contrast_ids=draft.contrast_ids,
                    endpoint_ids=draft.endpoint_ids,
                    target_biological_unit=draft.target_biological_unit,
                    evidence_ids=draft.evidence_ids,
                    provenance=Provenance(
                        origin=ProvenanceKind.USER,
                        evidence_ids=draft.evidence_ids,
                        actor_role=draft.reviewer_role,
                    ),
                    status=InferenceTargetStatus.USER_CONFIRMED,
                )
                target_operation: dict[str, object] = {
                    "op": "replace" if target_index is not None else "add",
                    "path": (
                        f"/inference_targets/{target_index}"
                        if target_index is not None
                        else "/inference_targets/-"
                    ),
                    "value": target.model_dump(mode="json"),
                }
                estimand_operations: list[dict[str, object]] = []
                for estimand_draft in draft.estimands:
                    estimand_id = estimand_draft.estimand_id or stable_id(
                        "est",
                        payload.block_id,
                        estimand_draft.endpoint_id,
                        estimand_draft.effect_measure,
                        estimand_draft.target_population_or_unit,
                        estimand_draft.generalization_level,
                        estimand_draft.factor_ids,
                        estimand_draft.timepoint,
                        estimand_draft.condition,
                    )
                    estimand = Estimand(
                        id=estimand_id,
                        endpoint_id=estimand_draft.endpoint_id,
                        effect_measure=estimand_draft.effect_measure,
                        target_population_or_unit=estimand_draft.target_population_or_unit,
                        generalization_level=estimand_draft.generalization_level,
                        factor_ids=estimand_draft.factor_ids,
                        timepoint=estimand_draft.timepoint,
                        condition=estimand_draft.condition,
                        evidence_ids=estimand_draft.evidence_ids,
                        provenance=Provenance(
                            origin=ProvenanceKind.USER,
                            evidence_ids=estimand_draft.evidence_ids,
                            actor_role=draft.reviewer_role,
                        ),
                    )
                    estimand_index = next(
                        (
                            index
                            for index, item in enumerate(current.estimands)
                            if item.id == estimand_id
                        ),
                        None,
                    )
                    estimand_operations.append(
                        {
                            "op": "replace" if estimand_index is not None else "add",
                            "path": (
                                f"/estimands/{estimand_index}"
                                if estimand_index is not None
                                else "/estimands/-"
                            ),
                            "value": estimand.model_dump(mode="json"),
                        }
                    )
                patch: tuple[dict[str, object], ...] = (
                    target_operation,
                    *estimand_operations,
                )
                return Correction(
                    id=stable_id(
                        "cor",
                        payload.block_id,
                        ledger.current_checksum,
                        ledger.next_sequence,
                        CorrectionReason.DOMAIN_JUDGEMENT,
                        draft.rationale,
                        json.dumps(patch, sort_keys=True, ensure_ascii=False),
                    ),
                    sequence=ledger.next_sequence,
                    reason=CorrectionReason.DOMAIN_JUDGEMENT,
                    rationale=draft.rationale,
                    patch=patch,
                    evidence_ids=draft.evidence_ids,
                    reviewer_role=draft.reviewer_role,
                    verified=False,
                )

            return correction_response(
                session.apply_generated(payload.block_id, build_target_correction)
            )
        except (SessionNotFound, SessionBlockNotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except CorrectionEngineError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @api.post("/v1/distribution/readiness")
    def distribution_readiness(payload: DistributionReadinessRequest) -> dict[str, Any]:
        """Valuta share/redistribute localmente; non trasferisce alcun file."""

        try:
            session = sessions.get(payload.session_id)
            evaluation = evaluate_distribution_readiness(
                session.execution.share_readiness,
                session.execution.privacy_audit,
                DistributionGovernanceBundle(
                    governance_records=payload.governance_records,
                    license_manifests=payload.license_manifests,
                    redaction_manifests=payload.redaction_manifests,
                    redacted_derivatives=payload.redacted_derivatives,
                ),
                action=payload.action,
                privacy_policy=payload.privacy_policy,
                acknowledgement_reference=payload.acknowledgement_reference,
            )
            return evaluation.model_dump(mode="json")
        except SessionNotFound as exc:
            raise HTTPException(status_code=404, detail="Sessione non trovata") from exc
        except GovernanceDenied as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": exc.code, "message": exc.detail},
            ) from exc
        except PrivacyBlocked as exc:
            raise HTTPException(
                status_code=409,
                detail={"code": "privacy_not_ready", "message": str(exc)},
            ) from exc

    def navigate_correction(
        payload: NavigateCorrectionRequest, action: Literal["undo", "redo"]
    ) -> dict[str, Any]:
        try:
            session = sessions.get(payload.session_id)
            update = (
                session.undo(payload.block_id)
                if action == "undo"
                else session.redo(payload.block_id)
            )
            return correction_response(update)
        except (SessionNotFound, SessionBlockNotFound) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except CorrectionEngineError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @api.post("/v1/corrections/undo")
    def undo_correction(payload: NavigateCorrectionRequest) -> dict[str, Any]:
        return navigate_correction(payload, "undo")

    @api.post("/v1/corrections/redo")
    def redo_correction(payload: NavigateCorrectionRequest) -> dict[str, Any]:
        return navigate_correction(payload, "redo")

    @api.get("/v1/sessions/{session_id}/artifacts/{name}")
    def download_artifact(session_id: str, name: str) -> Any:
        try:
            path = sessions.get(session_id).artifact(name)
        except SessionNotFound as exc:
            raise HTTPException(status_code=404, detail="Sessione non trovata") from exc
        except SessionArtifactNotFound as exc:
            raise HTTPException(status_code=404, detail="Artefatto non trovato") from exc
        return FileResponse(
            path,
            filename=path.name,
            media_type=(
                "application/ld+json"
                if name == "ro_crate"
                else "application/json"
                if path.suffix == ".json"
                else "text/html"
            ),
        )

    ui_dir = _ui_directory()
    if ui_dir is not None:
        api.mount("/app", StaticFiles(directory=ui_dir, html=True), name="desktop-ui")

        @api.get("/", include_in_schema=False)
        def root() -> Any:
            return RedirectResponse(url="/app/")

    else:

        @api.get("/", include_in_schema=False)
        def root_without_ui() -> Any:
            return JSONResponse(
                {
                    "service": "ntruth",
                    "ui": "not_built",
                    "message": "Eseguire il build in apps/desktop per la UI locale.",
                }
            )

    return api


def _ui_directory() -> Path | None:
    """Trova gli asset React nel checkout o nel wheel, senza accesso di rete."""

    candidates = (
        Path(__file__).resolve().parents[1] / "_ui",
        Path(__file__).resolve().parents[3] / "apps" / "desktop" / "dist",
    )
    return next((path for path in candidates if (path / "index.html").is_file()), None)


try:  # L'import del core resta possibile senza l'extra API.
    import fastapi as _fastapi  # noqa: F401
except ModuleNotFoundError:  # pragma: no cover - configurazione core-only
    app = None
else:  # pragma: no cover - coperto dai test con extra API
    app = create_app()
