"""Ingestione sicura: import, checksum, MIME, manifest e sandbox (PRD 11.1)."""

from ntruth.ingest.project import IngestResult, Project, sha256_of
from ntruth.ingest.safety import (
    D0_CORE_EXTENSIONS,
    EXTENDED_EXPERIMENTAL_EXTENSIONS,
    SUPPORTED_EXTENSIONS,
    SafetyError,
    SafetyReport,
    check_file,
    detect_injection,
    extension_allowed,
    neutralize_formula,
    resolve_inside,
    sniff_media_type,
)

__all__ = [
    "D0_CORE_EXTENSIONS",
    "EXTENDED_EXPERIMENTAL_EXTENSIONS",
    "SUPPORTED_EXTENSIONS",
    "IngestResult",
    "Project",
    "SafetyError",
    "SafetyReport",
    "check_file",
    "detect_injection",
    "extension_allowed",
    "neutralize_formula",
    "resolve_inside",
    "sha256_of",
    "sniff_media_type",
]
