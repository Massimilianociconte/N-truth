"""Ingestione sicura: import, checksum, MIME, manifest e sandbox (PRD 11.1)."""

from ntruth.ingest.project import IngestResult, Project, sha256_of
from ntruth.ingest.safety import (
    SUPPORTED_EXTENSIONS,
    SafetyError,
    SafetyReport,
    check_file,
    detect_injection,
    neutralize_formula,
    resolve_inside,
)

__all__ = [
    "SUPPORTED_EXTENSIONS",
    "IngestResult",
    "Project",
    "SafetyError",
    "SafetyReport",
    "check_file",
    "detect_injection",
    "neutralize_formula",
    "resolve_inside",
    "sha256_of",
]
