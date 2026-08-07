"""API locale con lo stesso caso d'uso della CLI (PRD FR-029)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

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
    enforce_privacy,
    scan_text,
)
from ntruth.ingest.safety import SafetyError
from ntruth.prospective import (
    MAX_PROSPECTIVE_D0_BODY_BYTES,
    MAX_PROSPECTIVE_D0_ROWS,
    ProspectiveD0CompileRequest,
    ProspectiveD0RulesetError,
    ProspectiveD0ValidationError,
    ProspectiveGoldRecord,
    ProspectivePlanExecutionRecord,
    ProspectiveSession,
    ProspectiveSessionNotFound,
    ProspectiveSessionRegistry,
    compile_prospective_d0,
)
from ntruth.reporting import read_json, report_to_dict
from ntruth.rules.loader import (
    DEFAULT_RULESET_ID,
    DEFAULT_RULESET_VERSION,
    RulesetNotFound,
)
from ntruth.schemas.core import Provenance, ProvenanceKind, content_checksum, stable_id
from ntruth.schemas.experiment import (
    Correction,
    CorrectionReason,
    Estimand,
    InferenceTarget,
    InferenceTargetStatus,
)
from ntruth.schemas.graph import NodeType
from ntruth.schemas.manifest import LicenseManifest, ReleaseProfile
from ntruth.storage import StorageDatabase, StorageIntegrityError
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
    release_profile: ReleaseProfile = ReleaseProfile.D0_CORE
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
    reviewer_role: str = Field(default="reviewer", min_length=2, max_length=64)


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


class PlanExecutionAppendRequest(BaseModel):
    """Append di un candidato piano/esecuzione su storage locale SQLite."""

    project_id: str = Field(min_length=1, max_length=200)
    project_dir: str = Field(min_length=1, max_length=4000)
    record: dict[str, Any]
    actor_role: str | None = Field(default=None, max_length=64)


class PlanExecutionGoldRequest(BaseModel):
    """Promozione a gold adjudicato di un candidato piano/esecuzione."""

    project_dir: str = Field(min_length=1, max_length=4000)
    gold: dict[str, Any]
    actor_role: str | None = Field(default=None, max_length=64)


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
    prospective_sessions = ProspectiveSessionRegistry()

    @api.middleware("http")
    async def reject_oversized_prospective_body(request: Any, call_next: Any) -> Any:
        path = request.url.path
        if path == "/v1/prospective/d0/compile" or path.startswith(
            "/v1/prospective/plan-execution"
        ):
            raw_length = request.headers.get("content-length")
            if raw_length is not None:
                try:
                    body_length = int(raw_length)
                except ValueError:
                    return JSONResponse(
                        status_code=400,
                        content={"detail": {"code": "invalid_content_length"}},
                    )
                if body_length > MAX_PROSPECTIVE_D0_BODY_BYTES:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "detail": {
                                "code": "prospective_payload_too_large",
                                "max_body_bytes": MAX_PROSPECTIVE_D0_BODY_BYTES,
                            }
                        },
                    )
            body = bytearray()
            async for chunk in request.stream():
                if len(body) + len(chunk) > MAX_PROSPECTIVE_D0_BODY_BYTES:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "detail": {
                                "code": "prospective_payload_too_large",
                                "max_body_bytes": MAX_PROSPECTIVE_D0_BODY_BYTES,
                            }
                        },
                    )
                body.extend(chunk)
            # Starlette riusa il body gia verificato nel receive wrapper di
            # ``call_next``; nessun secondo buffering legge lo stream originale.
            request._body = bytes(body)
        return await call_next(request)

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
            "prospective_d0_limits": {
                "max_rows": MAX_PROSPECTIVE_D0_ROWS,
                "max_body_bytes": MAX_PROSPECTIVE_D0_BODY_BYTES,
                "session_persistence": "ephemeral_process_memory",
            },
            "plan_execution_persistence": "sqlite_append_only",
            "default_release_profile": ReleaseProfile.D0_CORE.value,
            "input_profiles": {
                ReleaseProfile.D0_CORE.value: [".txt", ".md", ".csv"],
                ReleaseProfile.EXTENDED_EXPERIMENTAL.value: [
                    ".docx",
                    ".xlsx",
                    ".pdf",
                    ".xml/.nxml/.jats",
                    ".r/.py/.rmd",
                ],
            },
        }

    @api.post("/preflight")
    @api.post("/v1/preflight")
    def preflight(payload: DomainPreflightRequest) -> dict[str, Any]:
        return assess_domain(payload.domain).model_dump(mode="json")

    def prospective_response(session: ProspectiveSession) -> dict[str, Any]:
        return {
            "session_id": session.id,
            "session_persistence": "ephemeral_process_memory",
            "audit_trail": [item.model_dump(mode="json") for item in session.audit_trail],
            **session.compilation.model_dump(mode="json"),
        }

    @api.post("/v1/prospective/d0/compile")
    def compile_prospective(payload: ProspectiveD0CompileRequest) -> dict[str, Any]:
        """Compila il wizard D0; input non valido non crea alcuna sessione."""

        try:
            compilation = compile_prospective_d0(payload)
        except ProspectiveD0RulesetError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": exc.code,
                    "allowed_ruleset": (f"{DEFAULT_RULESET_ID}@{DEFAULT_RULESET_VERSION}"),
                    "message": str(exc),
                },
            ) from exc
        except ProspectiveD0ValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "prospective_d0_invalid",
                    "issues": [item.model_dump(mode="json") for item in exc.issues],
                },
            ) from exc
        session = prospective_sessions.create(
            compilation,
            actor_role=payload.draft.reviewer_role,
            input_checksum=content_checksum(payload.model_dump(mode="json")),
        )
        return prospective_response(session)

    @api.get("/v1/prospective/d0/sessions/{session_id}")
    def prospective_session(session_id: str) -> dict[str, Any]:
        try:
            return prospective_response(prospective_sessions.get(session_id))
        except ProspectiveSessionNotFound as exc:
            raise HTTPException(status_code=404, detail="Sessione prospettica non trovata") from exc

    @api.get("/v1/prospective/d0/sessions/{session_id}/export")
    def export_prospective_session(session_id: str) -> Any:
        """Esporta soltanto JSON canonico; nessun file viene pubblicato o caricato."""

        try:
            session = prospective_sessions.get(session_id)
        except ProspectiveSessionNotFound as exc:
            raise HTTPException(status_code=404, detail="Sessione prospettica non trovata") from exc
        filename = f"ntruth-d0-{session.compilation.compilation_id}.json"
        export_payload = {
            **session.compilation.model_dump(mode="json"),
            "audit_trail": [item.model_dump(mode="json") for item in session.audit_trail],
        }
        serialized_export = json.dumps(
            export_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        privacy_scan = scan_text(
            serialized_export,
            artifact_id=session.compilation.compilation_id,
            field_path="prospective_d0_export",
        )
        try:
            enforce_privacy(privacy_scan, PrivacyPolicy.BLOCKED)
        except PrivacyBlocked as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "privacy_export_blocked",
                    "message": (
                        "L'export contiene identificatori potenzialmente sensibili; "
                        "creare una copia redatta prima della distribuzione."
                    ),
                    "finding_count": len(privacy_scan.findings),
                    "finding_kinds": sorted(
                        {finding.kind.value for finding in privacy_scan.findings}
                    ),
                },
            ) from exc
        return JSONResponse(
            content=export_payload,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    def _open_project_database(project_dir: str) -> StorageDatabase:
        root = Path(project_dir).expanduser()
        if root.is_symlink():
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "invalid_project_dir",
                    "message": "project_dir symlink non ammesso",
                },
            )
        database_path = root / "ntruth.sqlite3"
        if database_path.is_symlink():
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "invalid_project_dir",
                    "message": "database SQLite symlink non ammesso",
                },
            )
        try:
            return StorageDatabase(database_path)
        except StorageIntegrityError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": "storage_integrity_error", "message": str(exc)},
            ) from exc

    def _ensure_project_registered(
        database: StorageDatabase,
        *,
        project_id: str,
        manifest_checksum: str,
    ) -> None:
        exists = database.connection.execute(
            "SELECT 1 FROM projects WHERE project_id = ?", (project_id,)
        ).fetchone()
        if exists is None:
            database.upsert_project(
                project_id=project_id,
                name=project_id,
                manifest_path="manifest.json",
                manifest_checksum=manifest_checksum,
            )

    def _plan_execution_response(record: Any) -> dict[str, Any]:
        return {
            "record_id": record.record_id,
            "project_id": record.project_id,
            "status": record.status,
            "content_checksum": record.content_checksum,
            "payload": record.payload,
            "actor_role": record.actor_role,
            "parent_candidate_id": record.parent_candidate_id,
            "created_at": record.created_at,
        }

    @api.post("/v1/prospective/plan-execution")
    def append_plan_execution(payload: PlanExecutionAppendRequest) -> dict[str, Any]:
        """Persiste un candidato piano/esecuzione su SQLite append-only locale."""

        try:
            validated = ProspectivePlanExecutionRecord.model_validate(payload.record)
        except ValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "plan_execution_invalid",
                    "message": "ProspectivePlanExecutionRecord non valido",
                    "errors": json.loads(exc.json()),
                },
            ) from exc

        record_payload = validated.model_dump(mode="json")
        canonical = json.dumps(
            record_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        bootstrap_checksum = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

        with _open_project_database(payload.project_dir) as database:
            _ensure_project_registered(
                database,
                project_id=payload.project_id,
                manifest_checksum=bootstrap_checksum,
            )
            try:
                stored = database.put_plan_execution_candidate(
                    payload.project_id,
                    record_payload,
                    actor_role=payload.actor_role,
                )
            except StorageIntegrityError as exc:
                raise HTTPException(
                    status_code=409,
                    detail={"code": "plan_execution_storage_error", "message": str(exc)},
                ) from exc
        return _plan_execution_response(stored)

    @api.get("/v1/prospective/plan-execution/{record_id}")
    def get_plan_execution(record_id: str, project_dir: str) -> dict[str, Any]:
        """Carica un record piano/esecuzione da storage locale."""

        with _open_project_database(project_dir) as database:
            stored = database.get_plan_execution(record_id)
        if stored is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "plan_execution_not_found",
                    "message": "Record piano/esecuzione non trovato",
                },
            )
        return _plan_execution_response(stored)

    @api.post("/v1/prospective/plan-execution/{record_id}/gold")
    def promote_plan_execution_gold(
        record_id: str, payload: PlanExecutionGoldRequest
    ) -> dict[str, Any]:
        """Promuove un candidato a gold adjudicato senza mutare il candidato."""

        try:
            gold = ProspectiveGoldRecord.model_validate(payload.gold)
        except ValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "plan_execution_gold_invalid",
                    "message": "ProspectiveGoldRecord non valido",
                    "errors": json.loads(exc.json()),
                },
            ) from exc

        gold_payload = gold.model_dump(mode="json")
        plan_execution_payload = gold.plan_execution.model_dump(mode="json")
        plan_execution_canonical = json.dumps(
            plan_execution_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        plan_execution_checksum = hashlib.sha256(
            plan_execution_canonical.encode("utf-8")
        ).hexdigest()

        with _open_project_database(payload.project_dir) as database:
            candidate = database.get_plan_execution(record_id)
            if candidate is None:
                raise HTTPException(
                    status_code=404,
                    detail={
                        "code": "plan_execution_not_found",
                        "message": "Candidato piano/esecuzione non trovato",
                    },
                )
            if candidate.status != "candidate":
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "plan_execution_not_candidate",
                        "message": "Solo un candidato puo essere promosso a gold",
                        "status": candidate.status,
                    },
                )
            candidate_domain_id = candidate.payload.get("record_id")
            if candidate_domain_id != gold.plan_execution.record_id:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "plan_execution_gold_mismatch",
                        "message": (
                            "gold.plan_execution.record_id non coincide con il candidato"
                        ),
                    },
                )
            if candidate.content_checksum != plan_execution_checksum:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "plan_execution_gold_mismatch",
                        "message": (
                            "gold.plan_execution non coincide con il payload del candidato"
                        ),
                    },
                )
            try:
                stored = database.promote_plan_execution_gold(
                    record_id,
                    gold_payload,
                    actor_role=payload.actor_role or gold.adjudicator_role,
                )
            except StorageIntegrityError as exc:
                raise HTTPException(
                    status_code=409,
                    detail={"code": "plan_execution_gold_conflict", "message": str(exc)},
                ) from exc
        return _plan_execution_response(stored)

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
                release_profile=payload.release_profile,
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
                session.undo(payload.block_id, actor_role=payload.reviewer_role)
                if action == "undo"
                else session.redo(payload.block_id, actor_role=payload.reviewer_role)
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
