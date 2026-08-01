"""Export RO-Crate 1.3 / JSON-LD deterministico (PRD FR-028, FR-034)."""

from __future__ import annotations

import hashlib
import json
import mimetypes
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ntruth import __version__
from ntruth.schemas.core import content_checksum
from ntruth.schemas.report import Report

RO_CRATE_VERSION = "1.3"
RO_CRATE_CONTEXT = f"https://w3id.org/ro/crate/{RO_CRATE_VERSION}/context"
RO_CRATE_SPEC = f"https://w3id.org/ro/crate/{RO_CRATE_VERSION}"
NTRUTH_TERMS = "https://w3id.org/ntruth/terms/"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _candidate_metadata(path: Path) -> dict[str, Any] | None:
    """Valida e descrive un export candidate senza promuoverlo a gold."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or payload.get("artifact_type") != "ntruth_candidate_annotations"
    ):
        return None

    declared_checksum = payload.get("content_checksum")
    checksummed_payload = dict(payload)
    checksummed_payload.pop("content_checksum", None)
    actual_checksum = content_checksum(checksummed_payload)
    if declared_checksum != actual_checksum:
        raise ValueError(f"checksum candidate annotations non valido: {path}")

    history = payload.get("history_state")
    if not isinstance(history, dict):
        raise ValueError(f"stato undo/redo/branching assente: {path}")
    audit_trail = payload.get("audit_trail")
    candidates = payload.get("candidate_annotations")
    if not isinstance(audit_trail, list) or not isinstance(candidates, list):
        raise ValueError(f"candidate annotations o audit non validi: {path}")

    audit_checksum = payload.get("audit_checksum")
    candidate_checksum = payload.get("candidate_annotations_checksum")
    if audit_checksum != content_checksum(audit_trail):
        raise ValueError(f"checksum audit candidate non valido: {path}")
    if candidate_checksum != content_checksum(candidates):
        raise ValueError(f"checksum annotazioni candidate non valido: {path}")

    return {
        "creativeWorkStatus": "candidate",
        "ntruth:goldStatus": payload.get("gold_status"),
        "ntruth:trainingEligible": payload.get("training_eligible"),
        "ntruth:contentChecksum": declared_checksum,
        "ntruth:candidateAnnotationsChecksum": candidate_checksum,
        "ntruth:auditChecksum": audit_checksum,
        "ntruth:auditEventCount": len(audit_trail),
        "ntruth:undoAvailable": bool(history.get("undo_available")),
        "ntruth:redoAvailable": bool(history.get("redo_available")),
        "ntruth:branchingOccurred": bool(history.get("branching_occurred")),
    }


def ro_crate_to_dict(
    report: Report,
    out_dir: Path,
    exported_files: Mapping[str, Path],
) -> dict[str, Any]:
    """Descrive gli export presenti nella crate senza introdurre fatti scientifici."""

    out_dir = out_dir.resolve()
    file_entities: list[dict[str, Any]] = []
    file_refs: list[dict[str, str]] = []
    result_refs: list[dict[str, str]] = []
    candidate_refs: list[dict[str, str]] = []

    for label, raw_path in sorted(exported_files.items()):
        path = raw_path.resolve()
        try:
            relative = path.relative_to(out_dir).as_posix()
        except ValueError as exc:
            raise ValueError(f"file RO-Crate fuori dalla directory di export: {path}") from exc
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        reference = {"@id": relative}
        file_refs.append(reference)
        result_refs.append(reference)
        entity: dict[str, Any] = {
            "@id": relative,
            "@type": "File",
            "name": path.name,
            "encodingFormat": media_type,
            "contentSize": str(path.stat().st_size),
            "sha256": _sha256(path),
            "ntruth:artifactRole": label,
        }
        if label in {"parser_ai_input_schema", "parser_ai_output_schema"}:
            entity["conformsTo"] = {"@id": "https://json-schema.org/draft/2020-12/schema"}
        candidate_metadata = _candidate_metadata(path) if label.startswith("candidate_") else None
        if candidate_metadata is not None:
            entity.update(candidate_metadata)
            candidate_refs.append(reference)
        file_entities.append(entity)

    versions = report.versions
    metadata = {
        "@id": "ro-crate-metadata.json",
        "@type": "CreativeWork",
        "about": {"@id": "./"},
        "conformsTo": {"@id": RO_CRATE_SPEC},
    }
    root = {
        "@id": "./",
        "@type": "Dataset",
        "name": f"N-Truth - {report.project_name}",
        "description": (
            "Export locale N-Truth del disegno sperimentale con report, grafo e provenance."
        ),
        "hasPart": file_refs,
        "conformsTo": {"@id": RO_CRATE_SPEC},
        "mentions": [
            {"@id": "#ntruth"},
            {"@id": "#analysis"},
            {"@id": "#ntruth-profile"},
        ],
        "ntruth:inputChecksum": report.input_checksum,
        "ntruth:reportChecksum": report.content_checksum(),
        "ntruth:schemaVersion": versions.schema_version,
        "ntruth:parserVersion": versions.parser_version,
        "ntruth:graphVersion": versions.graph_version,
        "ntruth:rulesetId": versions.ruleset_id,
        "ntruth:rulesetVersion": versions.ruleset_version,
        "ntruth:ontologyVersion": versions.ontology_version or "not_recorded",
        "ntruth:modelVersion": versions.model_version or "rules_only",
        "ntruth:domainValidationStatus": report.domain_transparency.validation_status.value,
        "ntruth:domainWarning": report.domain_transparency.warning,
        "ntruth:candidateAnnotationArtifacts": candidate_refs,
        # Nessuna licenza delle fonti o del dataset viene dedotta dalla licenza software.
        "ntruth:datasetLicenseStatus": "not_asserted",
        "ntruth:inputRightsStatus": "not_inferred",
    }
    software = {
        "@id": "#ntruth",
        "@type": "SoftwareApplication",
        "name": "N-Truth",
        "softwareVersion": __version__,
        "applicationCategory": "Scientific software",
        "license": {"@id": "https://spdx.org/licenses/Apache-2.0"},
    }
    action = {
        "@id": "#analysis",
        "@type": "CreateAction",
        "name": "Analisi locale N-Truth",
        "instrument": {"@id": "#ntruth"},
        "result": result_refs,
    }
    profile = {
        "@id": "#ntruth-profile",
        "@type": "CreativeWork",
        "name": "N-Truth RO-Crate profile",
        "version": versions.schema_version,
        "creativeWorkStatus": "candidate",
        "description": (
            "Profilo candidato: gli allineamenti ontologici richiedono revisione esperta."
        ),
    }
    license_entity = {
        "@id": "https://spdx.org/licenses/Apache-2.0",
        "@type": "CreativeWork",
        "name": "Apache License 2.0",
    }
    return {
        "@context": [RO_CRATE_CONTEXT, {"ntruth": NTRUTH_TERMS}],
        "@graph": [metadata, root, *file_entities, software, action, profile, license_entity],
    }


def write_ro_crate(
    report: Report,
    out_dir: Path,
    exported_files: Mapping[str, Path],
    *,
    filename: str = "ro-crate-metadata.json",
) -> Path:
    """Scrive il metadata document nella root della crate allegata."""

    out_dir = out_dir.expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / filename
    payload = ro_crate_to_dict(report, out_dir, exported_files)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return path
