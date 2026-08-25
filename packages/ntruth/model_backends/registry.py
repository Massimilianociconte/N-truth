"""Registry centrale dei modelli Train A (single source of truth per model ID)."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from ntruth.model_backends.base import ModelProvider
from ntruth.model_backends.qualification import (
    ContaminationRisk,
    ModelQualificationRecord,
    QualificationStage,
)

REGISTRY_SCHEMA_VERSION = "1.3.0"

# Canonical IDs — non duplicare altrove senza passare da qui / env.
DEFAULT_PROVIDER = ModelProvider.GRANITE
DEFAULT_MODEL_ID = "ibm-granite/granite-4.1-3b"
DEFAULT_MLX_REPO = "mlx-community/granite-4.1-3b-4bit"
DEFAULT_GGUF_REPO = "ibm-granite/granite-4.1-3b-GGUF"
DEFAULT_BASE_ABLATION_ID = "ibm-granite/granite-4.1-3b-base"
DEFAULT_PROFILE_FILENAME = "granite-4.1-3b-mlx-qlora.json"

# Campi che, se cambiano rispetto al fingerprint qualificato, invalidano lo stato.
ARTIFACT_FINGERPRINT_KEYS: tuple[str, ...] = (
    "model_id",
    "model_revision",
    "weights_sha256",
    "adapter_sha256",
    "tokenizer_revision",
    "chat_template_hash",
    "quantization",
    "backend",
    "backend_version",
    "schema_version",
    "task_profile",
    "domain_profile",
)


class ModelRegistryError(RuntimeError):
    pass


class MigrationStatus(StrEnum):
    """Stato della migrazione codice/config — non implica qualificazione modello."""

    ARCHITECTURE_MIGRATED = "ARCHITECTURE_MIGRATED"
    SUPERSEDED = "SUPERSEDED"


class RuntimeQualificationStatus(StrEnum):
    """Qualificazione runtime multipiattaforma (pesi, E2E, budget, CI OS)."""

    UNVERIFIED = "UNVERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    STALE = "STALE"


class ScientificValidationStatus(StrEnum):
    """Validazione scientifica su gold/external challenge — indipendente dal runtime."""

    NOT_STARTED = "NOT_STARTED"
    PILOT_VALIDATED = "PILOT_VALIDATED"
    EXTERNAL_VALIDATED = "EXTERNAL_VALIDATED"
    FAILED = "FAILED"
    INVALIDATED = "INVALIDATED"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_profile_path() -> Path:
    """Profilo ML predefinito (Granite). Override: NTRUTH_ML_PROFILE / NTRUTH_MODEL_PROFILE_PATH."""

    explicit = os.environ.get("NTRUTH_ML_PROFILE") or os.environ.get("NTRUTH_MODEL_PROFILE_PATH")
    if explicit:
        return Path(explicit).expanduser()

    checkout = _repo_root() / "models" / "configs" / DEFAULT_PROFILE_FILENAME
    if checkout.is_file():
        return checkout
    bundled = Path(__file__).resolve().parents[1] / "_bundled" / "models" / DEFAULT_PROFILE_FILENAME
    return bundled


def resolve_provider() -> ModelProvider:
    raw = (os.environ.get("NTRUTH_MODEL_PROVIDER") or "granite").strip().lower()
    if raw in {"granite", "ibm-granite", "ibm"}:
        return ModelProvider.GRANITE
    if raw in {"legacy_qwen", "qwen", "qwen3"}:
        return ModelProvider.LEGACY_QWEN
    if raw == "generic":
        return ModelProvider.GENERIC
    raise ModelRegistryError(
        f"NTRUTH_MODEL_PROVIDER non supportato: {raw!r} (attesi granite|legacy_qwen|generic)"
    )


def resolve_model_id() -> str:
    return (os.environ.get("NTRUTH_MODEL_ID") or DEFAULT_MODEL_ID).strip()


def resolve_resource_profile() -> str:
    return (os.environ.get("NTRUTH_MODEL_PROFILE") or "BALANCED").strip().upper()


def resolve_quantization() -> str:
    return (os.environ.get("NTRUTH_MODEL_QUANTIZATION") or "auto").strip().lower()


def structured_output_enabled() -> bool:
    raw = (os.environ.get("NTRUTH_STRUCTURED_OUTPUT") or "true").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def registry_path() -> Path:
    return _repo_root() / "models" / "registry" / "default.json"


def load_registry(path: Path | None = None) -> dict[str, Any]:
    target = path or registry_path()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelRegistryError(f"registry non leggibile: {target}: {exc}") from exc
    if payload.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        raise ModelRegistryError(
            f"schema registry atteso {REGISTRY_SCHEMA_VERSION}, "
            f"ricevuto {payload.get('schema_version')!r}"
        )
    # Fail-closed: i tre stati devono essere presenti e coerenti (no inferenza).
    _validate_qualification_block(payload.get("qualification"))
    # Ledger SQLite: fonte autorevole; mirror JSON rigenerabile (ledger-first).
    payload = _sync_and_verify_ledger(payload, registry_file=target)
    return payload


def _sync_and_verify_ledger(
    payload: dict[str, Any],
    *,
    registry_file: Path,
    rebuild_json_mirror: bool = True,
) -> dict[str, Any]:
    """Ledger-first: verifica catena; ricostruisce mirror JSON se incoerente.

    Policy esplicita:
    - SQLite e la sola fonte autorevole delle transizioni;
    - un mirror JSON stale/mancante non e errore se il ledger e integro;
    - un ledger corrotto fallisce fail-closed.
    """

    from ntruth.model_backends.qualification_ledger import (
        QualificationLedger,
        QualificationLedgerError,
        default_ledger_path,
        rebuild_json_transition_mirror,
        seed_ledger_from_json_log,
    )

    block = payload["qualification"]
    log = list(block.get("transition_log") or [])
    # models/registry/default.json → parents[2] = repo root
    repo_root = registry_file.resolve().parents[2]
    source_json_sha256 = hashlib.sha256(
        registry_file.read_bytes() if registry_file.is_file() else b""
    ).hexdigest()

    try:
        with QualificationLedger(
            default_ledger_path(repo_root),
            registry_id="default",
        ) as ledger:
            if not ledger.is_initialized() and ledger.count() == 0:
                # Bootstrap controllato (una sola volta): GENESIS + seed dal JSON.
                seed_ledger_from_json_log(
                    ledger,
                    log,
                    source_json_sha256=source_json_sha256,
                    schema_version=str(payload.get("schema_version") or REGISTRY_SCHEMA_VERSION),
                    actor="ntruth-bootstrap",
                    allow_reseed=False,
                )
            else:
                ledger.verify_chain(verify_evidence=True)

            ledger_export = rebuild_json_transition_mirror(ledger)
            # Se il mirror JSON diverge, ricostruisci in memoria (e su disco se richiesto).
            if log != ledger_export:
                block["transition_log"] = ledger_export
                payload["qualification"] = block
                if rebuild_json_mirror:
                    temporary = registry_file.with_suffix(registry_file.suffix + ".tmp")
                    temporary.write_text(
                        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
                    temporary.replace(registry_file)
    except QualificationLedgerError as exc:
        raise ModelRegistryError(f"qualification ledger integrity failure: {exc}") from exc
    return payload


def artifact_fingerprint(values: dict[str, Any] | None) -> dict[str, Any]:
    """Normalizza il fingerprint di un artefatto di qualificazione.

    Una validazione BF16/Transformers non si trasferisce a GGUF Q4, a un adapter
    successivo o a un chat template diverso: ogni combinazione ha il suo record.
    """

    if not isinstance(values, dict):
        raise ModelRegistryError("artifact_fingerprint richiede un oggetto")
    out: dict[str, Any] = {}
    for key in ARTIFACT_FINGERPRINT_KEYS:
        value = values.get(key)
        if value is None or value == "":
            out[key] = None
        elif isinstance(value, str):
            out[key] = value.strip() or None
        else:
            out[key] = value
    return out


def canonical_fingerprint_payload(values: dict[str, Any] | None) -> str:
    """Serializzazione stabile (chiavi ordinate, separatori fissi, UTF-8)."""

    fingerprint = artifact_fingerprint(values)
    return json.dumps(
        fingerprint,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_fingerprint_hash(values: dict[str, Any] | None) -> str:
    """SHA-256 del payload canonico: evita falsi STALE per ordine/formattazione."""

    payload = canonical_fingerprint_payload(values)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def fingerprints_equal(left: dict[str, Any] | None, right: dict[str, Any] | None) -> bool:
    if left is None or right is None:
        return False
    return canonical_fingerprint_hash(left) == canonical_fingerprint_hash(right)


def _positive_scientific(status: ScientificValidationStatus) -> bool:
    return status in {
        ScientificValidationStatus.PILOT_VALIDATED,
        ScientificValidationStatus.EXTERNAL_VALIDATED,
    }


def _positive_runtime(status: RuntimeQualificationStatus) -> bool:
    return status in {
        RuntimeQualificationStatus.PARTIALLY_VERIFIED,
        RuntimeQualificationStatus.VERIFIED,
    }


def _binding_is_complete(binding: object) -> bool:
    if not isinstance(binding, dict):
        return False
    fingerprint = artifact_fingerprint(binding)
    # Campi minimi per un binding operativo (pesi + backend + quantizzazione + modello).
    required = ("model_id", "model_revision", "weights_sha256", "quantization", "backend")
    return all(fingerprint.get(key) is not None for key in required)


def _validate_transition_log(block: dict[str, Any]) -> None:
    log = block.get("transition_log")
    if log is None:
        raise ModelRegistryError("qualification.transition_log obbligatorio (append-only)")
    if not isinstance(log, list):
        raise ModelRegistryError("qualification.transition_log deve essere un array")
    for index, entry in enumerate(log):
        if not isinstance(entry, dict):
            raise ModelRegistryError(f"transition_log[{index}] deve essere un oggetto")
        for field in (
            "sequence",
            "timestamp",
            "actor",
            "dimension",
            "from_status",
            "to_status",
            "rationale",
        ):
            if not entry.get(field):
                raise ModelRegistryError(
                    f"transition_log[{index}] manca il campo obbligatorio {field}"
                )
        if index > 0:
            prev = log[index - 1]
            if int(entry["sequence"]) <= int(prev["sequence"]):
                raise ModelRegistryError(
                    "transition_log deve essere strettamente monotono in sequence (append-only)"
                )


def _validate_qualification_block(block: object) -> None:
    if not isinstance(block, dict):
        raise ModelRegistryError("registry.qualification obbligatorio (schema 1.3.0+)")
    try:
        MigrationStatus(str(block.get("migration_status")))
        runtime = RuntimeQualificationStatus(str(block.get("runtime_qualification_status")))
        scientific = ScientificValidationStatus(str(block.get("scientific_validation_status")))
    except ValueError as exc:
        raise ModelRegistryError(f"qualification status non valido: {exc}") from exc

    _validate_transition_log(block)
    binding = block.get("qualified_artifact")

    # Transizioni impossibili bloccate dallo schema di coerenza.
    if scientific is ScientificValidationStatus.EXTERNAL_VALIDATED and runtime is not (
        RuntimeQualificationStatus.VERIFIED
    ):
        raise ModelRegistryError(
            "INVALID: EXTERNAL_VALIDATED richiede runtime_qualification_status=VERIFIED"
        )

    if runtime is RuntimeQualificationStatus.VERIFIED and not _binding_is_complete(binding):
        raise ModelRegistryError(
            "INVALID: VERIFIED richiede qualified_artifact completo "
            "(model_id, model_revision, weights_sha256, quantization, backend)"
        )

    if _positive_scientific(scientific):
        if runtime in {
            RuntimeQualificationStatus.UNVERIFIED,
            RuntimeQualificationStatus.FAILED,
            RuntimeQualificationStatus.STALE,
        }:
            raise ModelRegistryError(
                "INVALID: scientific_validation_status positivo richiede runtime "
                "PARTIALLY_VERIFIED o VERIFIED (non UNVERIFIED/FAILED/STALE)"
            )
        if not _binding_is_complete(binding):
            raise ModelRegistryError(
                "INVALID: validazione scientifica positiva richiede qualified_artifact completo"
            )

    if _positive_runtime(runtime) and not _binding_is_complete(binding):
        raise ModelRegistryError(
            "INVALID: PARTIALLY_VERIFIED/VERIFIED richiedono qualified_artifact "
            "(fingerprint esatto: pesi, quantizzazione, backend, template, schema, task)"
        )

    if isinstance(binding, dict) and binding:
        # Canonical hash opzionale ma se presente deve combaciare.
        fingerprint = artifact_fingerprint(binding)
        expected = binding.get("canonical_fingerprint_sha256")
        if expected is not None:
            actual = canonical_fingerprint_hash(fingerprint)
            if str(expected) != actual:
                raise ModelRegistryError(
                    "INVALID: qualified_artifact.canonical_fingerprint_sha256 non combacia "
                    "col payload canonico (ordine/formattazione non devono contare)"
                )


def evaluate_qualification_against_artifact(
    *,
    current_artifact: dict[str, Any],
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Confronta l'artefatto runtime corrente col fingerprint qualificato.

    Se i fingerprint non coincidono, gli stati positivi diventano STALE/INVALIDATED
    *nell'esito valutato* (non riscrivono il file registry: l'audit e del chiamante).
    """

    data = registry if registry is not None else load_registry()
    block = data["qualification"]
    runtime = RuntimeQualificationStatus(str(block["runtime_qualification_status"]))
    scientific = ScientificValidationStatus(str(block["scientific_validation_status"]))
    binding = block.get("qualified_artifact")
    current = artifact_fingerprint(current_artifact)

    stale_reasons: list[str] = []
    effective_runtime = runtime
    effective_scientific = scientific

    if isinstance(binding, dict) and any(
        binding.get(k) is not None for k in ARTIFACT_FINGERPRINT_KEYS
    ):
        qualified = artifact_fingerprint(binding)
        if not fingerprints_equal(qualified, current):
            for key in ARTIFACT_FINGERPRINT_KEYS:
                if qualified.get(key) != current.get(key):
                    stale_reasons.append(
                        f"{key}: qualified={qualified.get(key)!r} current={current.get(key)!r}"
                    )
            if _positive_runtime(runtime):
                effective_runtime = RuntimeQualificationStatus.STALE
            if _positive_scientific(scientific):
                effective_scientific = ScientificValidationStatus.INVALIDATED
    elif _positive_runtime(runtime) or _positive_scientific(scientific):
        stale_reasons.append("missing_qualified_artifact_binding")

    current_hash = canonical_fingerprint_hash(current)
    qualified_fp = artifact_fingerprint(binding) if isinstance(binding, dict) else None
    return {
        "migration_status": str(block["migration_status"]),
        "runtime_qualification_status": effective_runtime.value,
        "scientific_validation_status": effective_scientific.value,
        "recorded_runtime_qualification_status": runtime.value,
        "recorded_scientific_validation_status": scientific.value,
        "current_artifact": current,
        "current_canonical_fingerprint_sha256": current_hash,
        "qualified_artifact": qualified_fp,
        "qualified_canonical_fingerprint_sha256": (
            canonical_fingerprint_hash(qualified_fp) if qualified_fp else None
        ),
        "stale": bool(stale_reasons),
        "stale_reasons": stale_reasons,
        "summary": str(block.get("summary") or ""),
    }


def qualification_status(registry: dict[str, Any] | None = None) -> dict[str, str]:
    """Stati machine-readable registrati: migrazione ≠ runtime ≠ scienza."""

    data = registry if registry is not None else load_registry()
    block = data["qualification"]
    return {
        "migration_status": str(block["migration_status"]),
        "runtime_qualification_status": str(block["runtime_qualification_status"]),
        "scientific_validation_status": str(block["scientific_validation_status"]),
        "summary": str(
            block.get("summary")
            or (
                "Il codice e migrato a Granite. Il runtime Granite non e ancora "
                "qualificato e il modello non e ancora scientificamente validato "
                "come modello definitivo di N-Truth."
            )
        ),
    }


def _gate_result(
    *,
    allowed: bool,
    reason: str,
    required_next_state: str | None = None,
    current_runtime: str | None = None,
    current_scientific: str | None = None,
) -> dict[str, Any]:
    return {
        "allowed": allowed,
        "reason": reason,
        "required_next_state": required_next_state,
        "current_runtime_qualification_status": current_runtime,
        "current_scientific_validation_status": current_scientific,
    }


def evaluate_claim_gate(
    gate: str,
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Valuta un claim gate con reason code (non solo bool).

    Gate ammessi:
    - exploratory_benchmark
    - internal_pilot
    - external_validation
    - scientifically_releasable
    """

    status = qualification_status(registry)
    runtime = RuntimeQualificationStatus(status["runtime_qualification_status"])
    scientific = ScientificValidationStatus(status["scientific_validation_status"])
    rt = runtime.value
    sc = scientific.value

    if gate == "exploratory_benchmark":
        if runtime is RuntimeQualificationStatus.FAILED:
            return _gate_result(
                allowed=False,
                reason="RUNTIME_FAILED",
                required_next_state="UNVERIFIED_or_PARTIALLY_VERIFIED_after_fix",
                current_runtime=rt,
                current_scientific=sc,
            )
        return _gate_result(
            allowed=True,
            reason="OK_EXPLORATORY",
            current_runtime=rt,
            current_scientific=sc,
        )

    if gate == "internal_pilot":
        if runtime in {
            RuntimeQualificationStatus.PARTIALLY_VERIFIED,
            RuntimeQualificationStatus.VERIFIED,
        }:
            return _gate_result(
                allowed=True,
                reason="OK_INTERNAL_PILOT",
                current_runtime=rt,
                current_scientific=sc,
            )
        if runtime is RuntimeQualificationStatus.UNVERIFIED:
            return _gate_result(
                allowed=False,
                reason="RUNTIME_UNVERIFIED",
                required_next_state=RuntimeQualificationStatus.PARTIALLY_VERIFIED.value,
                current_runtime=rt,
                current_scientific=sc,
            )
        if runtime is RuntimeQualificationStatus.STALE:
            return _gate_result(
                allowed=False,
                reason="RUNTIME_STALE",
                required_next_state=RuntimeQualificationStatus.PARTIALLY_VERIFIED.value,
                current_runtime=rt,
                current_scientific=sc,
            )
        return _gate_result(
            allowed=False,
            reason="RUNTIME_FAILED",
            required_next_state=RuntimeQualificationStatus.PARTIALLY_VERIFIED.value,
            current_runtime=rt,
            current_scientific=sc,
        )

    if gate == "external_validation":
        if runtime is RuntimeQualificationStatus.VERIFIED:
            return _gate_result(
                allowed=True,
                reason="OK_EXTERNAL_VALIDATION",
                current_runtime=rt,
                current_scientific=sc,
            )
        if runtime is RuntimeQualificationStatus.PARTIALLY_VERIFIED:
            return _gate_result(
                allowed=False,
                reason="RUNTIME_ONLY_PARTIALLY_VERIFIED",
                required_next_state=RuntimeQualificationStatus.VERIFIED.value,
                current_runtime=rt,
                current_scientific=sc,
            )
        if runtime is RuntimeQualificationStatus.UNVERIFIED:
            return _gate_result(
                allowed=False,
                reason="RUNTIME_UNVERIFIED",
                required_next_state=RuntimeQualificationStatus.VERIFIED.value,
                current_runtime=rt,
                current_scientific=sc,
            )
        return _gate_result(
            allowed=False,
            reason=f"RUNTIME_{runtime.value}",
            required_next_state=RuntimeQualificationStatus.VERIFIED.value,
            current_runtime=rt,
            current_scientific=sc,
        )

    if gate == "scientifically_releasable":
        if (
            runtime is RuntimeQualificationStatus.VERIFIED
            and scientific is ScientificValidationStatus.EXTERNAL_VALIDATED
        ):
            return _gate_result(
                allowed=True,
                reason="OK_SCIENTIFICALLY_RELEASABLE",
                current_runtime=rt,
                current_scientific=sc,
            )
        if runtime is not RuntimeQualificationStatus.VERIFIED:
            return _gate_result(
                allowed=False,
                reason="RUNTIME_NOT_VERIFIED",
                required_next_state=RuntimeQualificationStatus.VERIFIED.value,
                current_runtime=rt,
                current_scientific=sc,
            )
        return _gate_result(
            allowed=False,
            reason="SCIENTIFIC_NOT_EXTERNAL_VALIDATED",
            required_next_state=ScientificValidationStatus.EXTERNAL_VALIDATED.value,
            current_runtime=rt,
            current_scientific=sc,
        )

    raise ModelRegistryError(
        f"gate sconosciuto: {gate!r} "
        "(attesi exploratory_benchmark|internal_pilot|external_validation|"
        "scientifically_releasable)"
    )


def can_run_exploratory_benchmarks(registry: dict[str, Any] | None = None) -> bool:
    """UNVERIFIED+ (tranne FAILED): sviluppo, smoke e benchmark esplorativi."""

    return bool(evaluate_claim_gate("exploratory_benchmark", registry)["allowed"])


def can_run_internal_pilot(registry: dict[str, Any] | None = None) -> bool:
    """Pilot interni / calibration: da PARTIALLY_VERIFIED (non STALE/FAILED)."""

    return bool(evaluate_claim_gate("internal_pilot", registry)["allowed"])


def can_run_external_validation(registry: dict[str, Any] | None = None) -> bool:
    """External validation: solo runtime VERIFIED."""

    return bool(evaluate_claim_gate("external_validation", registry)["allowed"])


def is_scientifically_releasable(registry: dict[str, Any] | None = None) -> bool:
    """True solo VERIFIED + EXTERNAL_VALIDATED (claim scientifici supportati)."""

    return bool(evaluate_claim_gate("scientifically_releasable", registry)["allowed"])


def claim_gates(registry: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Gate fail-closed con reason code: blocca i claim, non la ricerca esplorativa."""

    return {
        "exploratory_benchmark": evaluate_claim_gate("exploratory_benchmark", registry),
        "internal_pilot": evaluate_claim_gate("internal_pilot", registry),
        "external_validation": evaluate_claim_gate("external_validation", registry),
        "scientifically_releasable": evaluate_claim_gate("scientifically_releasable", registry),
    }


def append_qualification_transition(
    *,
    dimension: str,
    from_status: str,
    to_status: str,
    actor: str,
    rationale: str,
    evidence_artifact: str | dict[str, Any] | Path | None = None,
    registry_path_override: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Append-only ledger-first: SQLite e autorevole; JSON e mirror best-effort.

    1. Valida coerenza status (schema fail-closed).
    2. COMMIT sul ledger SQLite (append-only, sequence max+1).
    3. Rigenera mirror JSON; se la scrittura JSON fallisce, la transizione
       resta valida nel ledger e verra ricostruita al prossimo load.
    """

    from ntruth.model_backends.qualification_ledger import (
        QualificationLedger,
        QualificationLedgerError,
        default_ledger_path,
    )

    path = registry_path_override or registry_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelRegistryError(f"registry non leggibile: {path}: {exc}") from exc
    if payload.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        raise ModelRegistryError(
            f"schema registry atteso {REGISTRY_SCHEMA_VERSION}, "
            f"ricevuto {payload.get('schema_version')!r}"
        )
    block = payload["qualification"]
    if not actor.strip() or not rationale.strip():
        raise ModelRegistryError("actor e rationale obbligatori per ogni transizione")

    if dry_run:
        return {
            "sequence": None,
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "actor": actor.strip(),
            "dimension": dimension,
            "from_status": from_status,
            "to_status": to_status,
            "rationale": rationale.strip(),
            "evidence_artifact": evidence_artifact,
            "dry_run": True,
        }

    if dimension == "runtime_qualification_status":
        block["runtime_qualification_status"] = to_status
    elif dimension == "scientific_validation_status":
        block["scientific_validation_status"] = to_status
    elif dimension == "migration_status":
        block["migration_status"] = to_status
    else:
        raise ModelRegistryError(
            "dimension deve essere migration_status|runtime_qualification_status|"
            "scientific_validation_status"
        )

    # Valida coerenza status con log esistente (mirror o ledger sara la sequence).
    tentative = list(block.get("transition_log") or [])
    tentative.append(
        {
            "sequence": (int(tentative[-1]["sequence"]) + 1) if tentative else 1,
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "actor": actor.strip(),
            "dimension": dimension,
            "from_status": from_status,
            "to_status": to_status,
            "rationale": rationale.strip(),
            "evidence_artifact": evidence_artifact,
        }
    )
    block["transition_log"] = tentative
    payload["qualification"] = block
    _validate_qualification_block(block)

    repo_root = path.resolve().parents[2]
    try:
        with QualificationLedger(
            default_ledger_path(repo_root),
            registry_id="default",
        ) as ledger:
            if not ledger.is_initialized():
                # Non dovrebbe accadere dopo load_registry; bootstrap esplicito.
                ledger.ensure_genesis(
                    actor="ntruth-bootstrap",
                    source_json_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    schema_version=REGISTRY_SCHEMA_VERSION,
                )
            record = ledger.append(
                dimension=dimension,
                from_status=from_status,
                to_status=to_status,
                actor=actor,
                rationale=rationale,
                evidence=evidence_artifact,
            )
            ledger.verify_chain(verify_evidence=True)
            block["transition_log"] = ledger.export_transition_log()
            payload["qualification"] = block
    except QualificationLedgerError as exc:
        raise ModelRegistryError(f"ledger append fallito: {exc}") from exc

    # Mirror JSON best-effort: fallimento non annulla il commit SQLite.
    try:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    except OSError:
        # Ledger resta autorevole; load_registry ricostruira il mirror.
        pass
    return record.as_dict()


def evaluate_model_qualification_record(
    record: ModelQualificationRecord | None,
    *,
    current_artifact: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Valutazione additiva di un ModelQualificationRecord opzionale (PRD v9 §25.10).

    Non cambia firme/semantica esistenti del registry: esito standalone fail-closed
    (record assente o artefatto corrente non confrontabile ⇒ mai deployable).
    """

    if record is None:
        return {
            "provided": False,
            "stage": None,
            "deployable": False,
            "stale": True,
            "stale_reasons": ["MODEL_QUALIFICATION_RECORD_ABSENT"],
            "binding": {},
            "matches_current_artifact": False,
        }
    binding = artifact_fingerprint(
        {
            "model_id": record.model_id,
            "model_revision": record.model_revision or None,
            "weights_sha256": record.artifact_sha256,
            "tokenizer_revision": record.tokenizer_sha256,
            "chat_template_hash": record.chat_template_sha256,
            "quantization": record.quantization,
            "backend": record.backend,
            "task_profile": record.task_profile,
        }
    )
    stale_reasons: list[str] = []
    matches = False
    if current_artifact is None:
        stale_reasons.append("CURRENT_ARTIFACT_UNAVAILABLE")
    else:
        current = artifact_fingerprint(current_artifact)
        matches = fingerprints_equal(binding, current)
        if not matches:
            for key in ARTIFACT_FINGERPRINT_KEYS:
                if binding.get(key) != current.get(key):
                    stale_reasons.append(
                        f"{key}: qualified={binding.get(key)!r} current={current.get(key)!r}"
                    )
    deployable = (
        record.stage is QualificationStage.PROFILE_DEPLOYMENT_QUALIFIED
        and matches
        and not stale_reasons
        and record.contamination_risk not in {ContaminationRisk.HIGH, ContaminationRisk.UNKNOWN}
    )
    return {
        "provided": True,
        "stage": record.stage.value,
        "deployable": deployable,
        "stale": bool(stale_reasons),
        "stale_reasons": stale_reasons,
        "binding": binding,
        "matches_current_artifact": matches,
        "contamination_risk": record.contamination_risk.value,
        "calibration_id": record.calibration_id,
        "task_profile": record.task_profile,
    }


def active_entry(registry: dict[str, Any] | None = None) -> dict[str, Any]:
    data = registry if registry is not None else load_registry()
    default_id = data.get("default_model_id") or DEFAULT_MODEL_ID
    env_id = resolve_model_id()
    models = data.get("models")
    if not isinstance(models, dict):
        raise ModelRegistryError("registry.models deve essere un oggetto")
    entry = models.get(env_id) or models.get(default_id)
    if not isinstance(entry, dict):
        raise ModelRegistryError(f"modello assente dal registry: {env_id}")
    return entry


def legacy_opt_in_enabled(*, allow_legacy: bool = False) -> bool:
    """Opt-in esplicito: flag API o NTRUTH_ALLOW_LEGACY_QWEN=1|true|yes."""

    if allow_legacy:
        return True
    raw = (os.environ.get("NTRUTH_ALLOW_LEGACY_QWEN") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def assert_not_legacy_default(*, allow_legacy: bool = False) -> None:
    """Fail-closed: Qwen non e mai selezionato senza opt-in esplicito.

    - Default e percorsi generici → solo Granite.
    - ``NTRUTH_MODEL_PROVIDER=legacy_qwen`` senza opt-in → errore.
    - ``allow_legacy=True`` o ``NTRUTH_ALLOW_LEGACY_QWEN`` → opt-in ammesso.
    """

    provider = resolve_provider()
    if provider is ModelProvider.LEGACY_QWEN and not legacy_opt_in_enabled(
        allow_legacy=allow_legacy
    ):
        raise ModelRegistryError(
            "legacy_qwen richiede opt-in esplicito "
            "(allow_legacy=True oppure NTRUTH_ALLOW_LEGACY_QWEN=1); "
            "default supportato: NTRUTH_MODEL_PROVIDER=granite"
        )
    model_id = resolve_model_id().casefold()
    if "qwen" in model_id and not legacy_opt_in_enabled(allow_legacy=allow_legacy):
        raise ModelRegistryError(
            "model ID Qwen non ammesso senza opt-in legacy esplicito "
            "(nessun fallback silenzioso al percorso Qwen)"
        )


__all__ = [
    "ARTIFACT_FINGERPRINT_KEYS",
    "DEFAULT_BASE_ABLATION_ID",
    "DEFAULT_GGUF_REPO",
    "DEFAULT_MLX_REPO",
    "DEFAULT_MODEL_ID",
    "DEFAULT_PROFILE_FILENAME",
    "DEFAULT_PROVIDER",
    "REGISTRY_SCHEMA_VERSION",
    "MigrationStatus",
    "ModelRegistryError",
    "RuntimeQualificationStatus",
    "ScientificValidationStatus",
    "active_entry",
    "append_qualification_transition",
    "artifact_fingerprint",
    "assert_not_legacy_default",
    "can_run_exploratory_benchmarks",
    "can_run_external_validation",
    "can_run_internal_pilot",
    "canonical_fingerprint_hash",
    "canonical_fingerprint_payload",
    "claim_gates",
    "default_profile_path",
    "evaluate_claim_gate",
    "evaluate_model_qualification_record",
    "evaluate_qualification_against_artifact",
    "fingerprints_equal",
    "is_scientifically_releasable",
    "legacy_opt_in_enabled",
    "load_registry",
    "qualification_status",
    "registry_path",
    "resolve_model_id",
    "resolve_provider",
    "resolve_quantization",
    "resolve_resource_profile",
    "structured_output_enabled",
]
