"""Scanner locale stand-off di identificatori e copie redatte (PRD v3 26).

I finding conservano coordinate e hash, non il valore originale. La funzione di
redazione restituisce una nuova stringa e non modifica mai la fonte.
"""

from __future__ import annotations

import hashlib
import re
from enum import StrEnum

from pydantic import Field

from ntruth.schemas.core import FrozenModel, content_checksum, stable_id


class IdentifierKind(StrEnum):
    EMAIL = "email"
    LOCAL_PATH = "local_path"
    NAME_LIKE = "name_like"
    SAMPLE_ID = "sample_id"


class PrivacyPolicy(StrEnum):
    BLOCKED = "blocked"
    ACKNOWLEDGED = "acknowledged"
    REDACTED_COPY = "redacted_copy"


class PrivacyFinding(FrozenModel):
    finding_id: str
    artifact_id: str
    field_path: str
    kind: IdentifierKind
    start: int = Field(ge=0)
    end: int = Field(ge=1)
    line: int = Field(ge=1)
    column: int = Field(ge=1)
    confidence: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    matched_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    masked_preview: str
    detector_version: str = "1.0.0"


class PrivacyScanResult(FrozenModel):
    artifact_id: str
    field_path: str
    original_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    findings: tuple[PrivacyFinding, ...] = ()
    detector_version: str = "1.0.0"


class RedactionManifest(FrozenModel):
    artifact_id: str
    field_path: str
    original_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    derivative_checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    redacted_finding_ids: tuple[str, ...]
    replacement: str


class PrivacyDecision(FrozenModel):
    policy: PrivacyPolicy
    allowed: bool
    finding_ids: tuple[str, ...] = ()
    acknowledgement_reference: str | None = None
    redaction_manifest_checksum: str | None = None


class PrivacyBlocked(PermissionError):
    pass


_PATTERNS: tuple[tuple[IdentifierKind, re.Pattern[str], float, str | None], ...] = (
    (
        IdentifierKind.EMAIL,
        re.compile(
            r"(?<![\w.+-])[A-Z0-9._%+-]+@"
            r"[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?"
            r"(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)*"
            r"\.[A-Z]{2,63}(?![\w-])",
            re.I,
        ),
        0.99,
        None,
    ),
    (
        IdentifierKind.LOCAL_PATH,
        re.compile(
            r"(?:file://)?(?:/Users/|/home/)[^\s'\"<>]+|"
            r"[A-Za-z]:\\Users\\[^\s'\"<>]+",
            re.I,
        ),
        0.98,
        None,
    ),
    (
        IdentifierKind.SAMPLE_ID,
        re.compile(
            r"\b(?:sample(?:[_ -]?id)?|subject(?:[_ -]?id)?|participant(?:[_ -]?id)?|"
            r"patient(?:[_ -]?id)?|donor(?:[_ -]?id)?)\s*[:=]\s*['\"]?"
            r"(?P<value>[A-Za-z0-9][A-Za-z0-9_.@-]{2,})",
            re.I,
        ),
        0.93,
        "value",
    ),
    (
        IdentifierKind.NAME_LIKE,
        re.compile(
            r"\b(?i:(?:name|full[ _-]?name|author|patient[ _-]?name|participant[ _-]?name))"
            r"\s*[:=]\s*(?P<value>[A-ZÀ-ÖØ-Ý][A-Za-zÀ-ÖØ-öø-ÿ'-]+"
            r"(?:\s+[A-ZÀ-ÖØ-Ý][A-Za-zÀ-ÖØ-öø-ÿ'-]+)+)"
        ),
        0.75,
        "value",
    ),
)


def scan_text(
    text: str,
    *,
    artifact_id: str,
    field_path: str = "text",
) -> PrivacyScanResult:
    """Scansiona localmente e restituisce soltanto riferimenti stand-off."""

    findings: list[PrivacyFinding] = []
    occupied: list[tuple[int, int]] = []
    for kind, pattern, confidence, value_group in _PATTERNS:
        for match in pattern.finditer(text):
            start, end = match.span(value_group) if value_group else match.span()
            if any(start < other_end and end > other_start for other_start, other_end in occupied):
                continue
            value = text[start:end]
            line = text.count("\n", 0, start) + 1
            last_newline = text.rfind("\n", 0, start)
            column = start - last_newline
            digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
            finding_id = stable_id("privacy", artifact_id, field_path, kind, start, end, digest)
            findings.append(
                PrivacyFinding(
                    finding_id=finding_id,
                    artifact_id=artifact_id,
                    field_path=field_path,
                    kind=kind,
                    start=start,
                    end=end,
                    line=line,
                    column=column,
                    confidence=confidence,
                    matched_sha256=digest,
                    masked_preview=_mask(value),
                )
            )
            occupied.append((start, end))
    findings.sort(key=lambda finding: (finding.start, finding.end, finding.kind))
    return PrivacyScanResult(
        artifact_id=artifact_id,
        field_path=field_path,
        original_checksum=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        findings=tuple(findings),
    )


def make_redacted_copy(
    text: str,
    scan: PrivacyScanResult,
    *,
    replacement: str = "[REDACTED]",
) -> tuple[str, RedactionManifest]:
    """Crea una derivata; verifica che la fonte coincida con lo scan."""

    original_checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if original_checksum != scan.original_checksum:
        raise ValueError("il testo e cambiato dopo la scansione privacy")
    redacted = text
    for finding in sorted(scan.findings, key=lambda item: item.start, reverse=True):
        current = redacted[finding.start : finding.end]
        if hashlib.sha256(current.encode("utf-8")).hexdigest() != finding.matched_sha256:
            raise ValueError(f"coordinate privacy obsolete: {finding.finding_id}")
        redacted = redacted[: finding.start] + replacement + redacted[finding.end :]
    manifest = RedactionManifest(
        artifact_id=scan.artifact_id,
        field_path=scan.field_path,
        original_checksum=scan.original_checksum,
        derivative_checksum=hashlib.sha256(redacted.encode("utf-8")).hexdigest(),
        redacted_finding_ids=tuple(finding.finding_id for finding in scan.findings),
        replacement=replacement,
    )
    return redacted, manifest


def enforce_privacy(
    scan: PrivacyScanResult,
    policy: PrivacyPolicy | str,
    *,
    acknowledgement_reference: str | None = None,
    redaction_manifest: RedactionManifest | None = None,
) -> PrivacyDecision:
    """Gate fail-closed da invocare prima di export/share."""

    selected = PrivacyPolicy(policy)
    finding_ids = tuple(finding.finding_id for finding in scan.findings)
    if not finding_ids:
        return PrivacyDecision(policy=selected, allowed=True)
    if selected is PrivacyPolicy.BLOCKED:
        raise PrivacyBlocked("identificatori rilevati: export bloccato")
    if selected is PrivacyPolicy.ACKNOWLEDGED:
        if not acknowledgement_reference:
            raise PrivacyBlocked("acknowledgement esplicito assente")
        return PrivacyDecision(
            policy=selected,
            allowed=True,
            finding_ids=finding_ids,
            acknowledgement_reference=acknowledgement_reference,
        )
    if redaction_manifest is None:
        raise PrivacyBlocked("manifest della copia redatta assente")
    if redaction_manifest.artifact_id != scan.artifact_id:
        raise PrivacyBlocked("manifest di redazione riferito a un altro artefatto")
    if redaction_manifest.field_path != scan.field_path:
        raise PrivacyBlocked("manifest di redazione riferito a un altro campo")
    if redaction_manifest.original_checksum != scan.original_checksum:
        raise PrivacyBlocked("manifest di redazione riferito a un'altra fonte")
    if set(redaction_manifest.redacted_finding_ids) != set(finding_ids):
        raise PrivacyBlocked("non tutti gli identificatori sono stati redatti")
    return PrivacyDecision(
        policy=selected,
        allowed=True,
        finding_ids=finding_ids,
        redaction_manifest_checksum=content_checksum(redaction_manifest.model_dump(mode="json")),
    )


def _mask(value: str) -> str:
    if len(value) <= 2:
        return "*" * len(value)
    return value[0] + "*" * min(len(value) - 2, 12) + value[-1]
