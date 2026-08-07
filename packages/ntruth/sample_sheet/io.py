"""I/O CSV sicuro e riproducibile per :mod:`ntruth.sample_sheet`."""

from __future__ import annotations

import csv
import hashlib
import io
import os
import re
import tempfile
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from enum import StrEnum
from pathlib import Path
from typing import TextIO

from pydantic import ValidationError

from ntruth.ingest.safety import MAX_FILE_BYTES, neutralize_formula
from ntruth.sample_sheet.schema import (
    FACTOR_COLUMN_PREFIX,
    HEADER_ALIASES,
    OPTIONAL_HEADERS,
    REQUIRED_HEADERS,
    SampleSheetRow,
    SampleSheetSpec,
    normalize_factor_column,
)
from ntruth.schemas.core import NTruthModel

_FACTOR_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
MAX_SAMPLE_SHEET_BYTES = MAX_FILE_BYTES
MAX_SAMPLE_SHEET_ROWS = 200_000
MAX_SAMPLE_SHEET_COLUMNS = 512


class SampleSheetIssueSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class SampleSheetIssue(NTruthModel):
    code: str
    message: str
    severity: SampleSheetIssueSeverity
    row: int | None = None
    column: str | None = None


class SampleSheetValidation(NTruthModel):
    """Esito non distruttivo: conserva tutti gli errori trovati in un passaggio."""

    spec: SampleSheetSpec | None = None
    issues: tuple[SampleSheetIssue, ...] = ()

    @property
    def valid(self) -> bool:
        return self.spec is not None and not any(
            issue.severity is SampleSheetIssueSeverity.ERROR for issue in self.issues
        )

    @property
    def errors(self) -> tuple[SampleSheetIssue, ...]:
        return tuple(
            issue for issue in self.issues if issue.severity is SampleSheetIssueSeverity.ERROR
        )

    @property
    def warnings(self) -> tuple[SampleSheetIssue, ...]:
        return tuple(
            issue for issue in self.issues if issue.severity is SampleSheetIssueSeverity.WARNING
        )


class SampleSheetValidationError(ValueError):
    """Errore al caricamento strict con l'esito strutturato disponibile."""

    def __init__(self, validation: SampleSheetValidation) -> None:
        self.validation = validation
        detail = "; ".join(issue.message for issue in validation.errors)
        super().__init__(detail or "sample sheet non valido")


def _canonical_header(raw: str) -> str:
    normalized = raw.strip().casefold().replace(" ", "_")
    return HEADER_ALIASES.get(normalized, normalized)


def _issue(
    code: str,
    message: str,
    *,
    severity: SampleSheetIssueSeverity = SampleSheetIssueSeverity.ERROR,
    row: int | None = None,
    column: str | None = None,
) -> SampleSheetIssue:
    return SampleSheetIssue(
        code=code,
        message=message,
        severity=severity,
        row=row,
        column=column,
    )


def _read_source(source: str | Path) -> tuple[str, str, str]:
    path = Path(source)
    if path.is_symlink():
        raise SampleSheetValidationError(
            SampleSheetValidation(
                issues=(_issue("symlink_not_allowed", "symlink non ammesso come sample sheet"),)
            )
        )
    if not path.is_file():
        raise SampleSheetValidationError(
            SampleSheetValidation(
                issues=(_issue("not_regular_file", "il sample sheet non e un file regolare"),)
            )
        )
    size = path.stat().st_size
    if size > MAX_SAMPLE_SHEET_BYTES:
        raise SampleSheetValidationError(
            SampleSheetValidation(
                issues=(
                    _issue(
                        "file_too_large",
                        f"sample sheet oltre il limite ({size} > {MAX_SAMPLE_SHEET_BYTES} byte)",
                    ),
                )
            )
        )
    raw = path.read_bytes()
    # Ricontrollo dopo la lettura per non accettare un file cresciuto tra stat e open.
    if len(raw) > MAX_SAMPLE_SHEET_BYTES:
        raise SampleSheetValidationError(
            SampleSheetValidation(
                issues=(
                    _issue(
                        "file_too_large",
                        "sample sheet oltre il limite "
                        f"({len(raw)} > {MAX_SAMPLE_SHEET_BYTES} byte)",
                    ),
                )
            )
        )
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SampleSheetValidationError(
            SampleSheetValidation(
                issues=(
                    _issue(
                        "invalid_encoding",
                        "il sample sheet deve essere codificato UTF-8",
                    ),
                )
            )
        ) from exc
    return content, path.name, hashlib.sha256(raw).hexdigest()


def validate_sample_sheet(source: str | Path) -> SampleSheetValidation:
    """Valida un CSV senza sollevare per errori di contenuto."""

    try:
        content, source_name, checksum = _read_source(source)
    except OSError as exc:
        return SampleSheetValidation(
            issues=(_issue("read_error", f"impossibile leggere il sample sheet: {exc}"),)
        )
    except SampleSheetValidationError as exc:
        return exc.validation

    reader = csv.reader(io.StringIO(content, newline=""), strict=True)
    try:
        raw_headers = next(reader)
    except StopIteration:
        return SampleSheetValidation(issues=(_issue("empty_file", "il sample sheet CSV e vuoto"),))
    except csv.Error as exc:
        return SampleSheetValidation(issues=(_issue("invalid_csv", f"CSV non valido: {exc}"),))

    issues: list[SampleSheetIssue] = []
    if not raw_headers or not any(header.strip() for header in raw_headers):
        return SampleSheetValidation(issues=(_issue("empty_header", "l'header CSV e vuoto"),))
    if len(raw_headers) > MAX_SAMPLE_SHEET_COLUMNS:
        return SampleSheetValidation(
            issues=(
                _issue(
                    "too_many_columns",
                    f"header con {len(raw_headers)} colonne; limite {MAX_SAMPLE_SHEET_COLUMNS}",
                ),
            )
        )

    headers = tuple(_canonical_header(header) for header in raw_headers)
    blank_headers = [index + 1 for index, header in enumerate(headers) if not header]
    if blank_headers:
        issues.append(
            _issue(
                "blank_header",
                f"header vuoti nelle posizioni: {blank_headers}",
            )
        )

    duplicates = sorted({header for header in headers if headers.count(header) > 1 and header})
    if duplicates:
        issues.append(
            _issue(
                "duplicate_header",
                f"header duplicati dopo normalizzazione: {', '.join(duplicates)}",
            )
        )

    for raw, canonical in zip(raw_headers, headers, strict=True):
        normalized = raw.strip().casefold().replace(" ", "_")
        if normalized in HEADER_ALIASES:
            issues.append(
                _issue(
                    "legacy_header_alias",
                    f"header '{raw}' importato come '{canonical}'",
                    severity=SampleSheetIssueSeverity.WARNING,
                    column=canonical,
                )
            )

    missing = [header for header in REQUIRED_HEADERS if header not in headers]
    if missing:
        issues.append(
            _issue(
                "missing_required_header",
                f"header obbligatori mancanti: {', '.join(missing)}",
            )
        )

    factor_columns = tuple(header for header in headers if header.startswith(FACTOR_COLUMN_PREFIX))
    if not factor_columns:
        issues.append(
            _issue(
                "missing_factor_header",
                "serve almeno una colonna factor_level_*",
            )
        )
    for column in factor_columns:
        try:
            normalize_factor_column(column)
        except ValueError as exc:
            issues.append(_issue("invalid_factor_header", str(exc), column=column))

    error_headers = any(issue.severity is SampleSheetIssueSeverity.ERROR for issue in issues)
    rows: list[SampleSheetRow] = []
    seen_sample_ids: dict[str, int] = {}
    if not error_headers:
        try:
            for csv_row, values in enumerate(reader, start=2):
                if csv_row > MAX_SAMPLE_SHEET_ROWS + 1:
                    issues.append(
                        _issue(
                            "too_many_rows",
                            f"sample sheet oltre il limite di {MAX_SAMPLE_SHEET_ROWS} righe dati",
                            row=csv_row,
                        )
                    )
                    break
                if not values or not any(value.strip() for value in values):
                    continue
                if len(values) != len(headers):
                    issues.append(
                        _issue(
                            "row_width_mismatch",
                            f"riga {csv_row}: attese {len(headers)} celle, trovate {len(values)}",
                            row=csv_row,
                        )
                    )
                    continue

                record = dict(zip(headers, (value.strip() for value in values), strict=True))
                factor_levels = {column: record.pop(column) for column in factor_columns}
                known = set(REQUIRED_HEADERS) | set(OPTIONAL_HEADERS)
                extra = {key: (value or None) for key, value in record.items() if key not in known}
                payload = {
                    "sample_id": record.get("sample_id"),
                    "source_id": record.get("source_id"),
                    "preparation_id": record.get("preparation_id"),
                    "culture_id": record.get("culture_id"),
                    "plate_id": record.get("plate_id"),
                    "well_id": record.get("well_id"),
                    "factor_levels": factor_levels,
                    "batch_id": record.get("batch_id"),
                    "timepoint": record.get("timepoint"),
                    "endpoint_id": record.get("endpoint_id"),
                    "lifecycle_status": record.get("lifecycle_status"),
                    "exclusion_reason": record.get("exclusion_reason"),
                    "file_ref": record.get("file_ref"),
                    "extra_fields": extra,
                }
                try:
                    row = SampleSheetRow.model_validate(payload)
                except ValidationError as exc:
                    for detail in exc.errors(include_url=False):
                        location = ".".join(str(item) for item in detail["loc"])
                        issues.append(
                            _issue(
                                "invalid_row",
                                f"riga {csv_row}, {location}: {detail['msg']}",
                                row=csv_row,
                                column=location or None,
                            )
                        )
                    continue

                previous = seen_sample_ids.get(row.sample_id)
                if previous is not None:
                    issues.append(
                        _issue(
                            "duplicate_sample_id",
                            f"sample_id '{row.sample_id}' duplicato alle righe "
                            f"{previous} e {csv_row}",
                            row=csv_row,
                            column="sample_id",
                        )
                    )
                    continue
                seen_sample_ids[row.sample_id] = csv_row
                rows.append(row)
        except csv.Error as exc:
            issues.append(_issue("invalid_csv", f"CSV non valido: {exc}"))

    if any(issue.severity is SampleSheetIssueSeverity.ERROR for issue in issues):
        return SampleSheetValidation(issues=tuple(issues))

    try:
        spec = SampleSheetSpec(
            headers=headers,
            factor_columns=factor_columns,
            rows=tuple(rows),
            source_name=source_name,
            content_sha256=checksum,
        )
    except ValidationError as exc:  # Difesa per costruzioni incoerenti future.
        issues.append(_issue("invalid_spec", str(exc)))
        return SampleSheetValidation(issues=tuple(issues))
    return SampleSheetValidation(spec=spec, issues=tuple(issues))


def load_sample_sheet(source: str | Path) -> SampleSheetSpec:
    """Carica un CSV valido; su errore espone tutti i problemi rilevati."""

    validation = validate_sample_sheet(source)
    if not validation.valid or validation.spec is None:
        raise SampleSheetValidationError(validation)
    return validation.spec


def _factor_columns(factor_names: Sequence[str]) -> tuple[str, ...]:
    if not factor_names:
        raise ValueError("serve almeno un fattore")
    columns: list[str] = []
    for raw_name in factor_names:
        normalized = raw_name.strip().casefold().replace(" ", "_")
        if normalized.startswith(FACTOR_COLUMN_PREFIX):
            column = normalize_factor_column(normalized)
        else:
            if not _FACTOR_NAME_RE.fullmatch(normalized):
                raise ValueError(f"nome fattore non valido: '{raw_name}'")
            column = normalize_factor_column(f"{FACTOR_COLUMN_PREFIX}{normalized}")
        if column in columns:
            raise ValueError(f"fattore duplicato: '{raw_name}'")
        columns.append(column)
    return tuple(columns)


def _safe_csv_value(value: object) -> str:
    if value is None:
        return ""
    safe, _ = neutralize_formula(str(value))
    return safe


def _prepare_destination(path: Path, *, overwrite: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise OSError(f"directory di destinazione symlink non ammessa: {path.parent}")
    if path.is_symlink():
        raise OSError(f"destinazione symlink non ammessa: {path}")
    if path.exists() and not path.is_file():
        raise OSError(f"la destinazione non e un file regolare: {path}")
    if path.exists() and not overwrite:
        raise FileExistsError(f"il file esiste gia: {path}")


@contextmanager
def _atomic_csv_writer(path: Path, *, overwrite: bool) -> Iterator[TextIO]:
    """Pubblica un CSV completo senza seguire o sovrascrivere symlink."""

    _prepare_destination(path, overwrite=overwrite)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            yield handle
            handle.flush()
            os.fsync(handle.fileno())

        # Ricontrollo immediatamente prima della pubblicazione. Con overwrite
        # os.replace sostituisce comunque il link stesso, mai il suo target.
        if path.is_symlink():
            raise OSError(f"destinazione symlink non ammessa: {path}")
        if overwrite:
            os.replace(temporary, path)
        else:
            os.link(temporary, path)
            temporary.unlink()
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def generate_sample_sheet(
    destination: str | Path,
    *,
    factor_names: Sequence[str] = ("treatment",),
    rows: Iterable[SampleSheetRow | Mapping[str, object]] = (),
    overwrite: bool = False,
) -> Path:
    """Genera il template CSV canonico, opzionalmente popolato con righe."""

    path = Path(destination)
    factor_columns = _factor_columns(factor_names)
    headers = (
        "sample_id",
        "source_id",
        "preparation_id",
        "culture_id",
        "plate_id",
        "well_id",
        *factor_columns,
        "batch_id",
        "timepoint",
        "endpoint_id",
        "lifecycle_status",
        "exclusion_reason",
        "file_ref",
    )

    materialized: list[SampleSheetRow] = []
    for raw_row in rows:
        row = (
            raw_row
            if isinstance(raw_row, SampleSheetRow)
            else SampleSheetRow.model_validate(raw_row)
        )
        if set(row.factor_levels) != set(factor_columns):
            raise ValueError(
                f"la riga '{row.sample_id}' non contiene esattamente i fattori del template"
            )
        materialized.append(row)

    with _atomic_csv_writer(path, overwrite=overwrite) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=headers, extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        for row in materialized:
            record: dict[str, object] = {
                "sample_id": row.sample_id,
                "source_id": row.source_id,
                "preparation_id": row.preparation_id,
                "culture_id": row.culture_id,
                "plate_id": row.plate_id,
                "well_id": row.well_id,
                **row.factor_levels,
                "batch_id": row.batch_id,
                "timepoint": row.timepoint,
                "endpoint_id": row.endpoint_id,
                "lifecycle_status": row.lifecycle_status.value,
                "exclusion_reason": row.exclusion_reason,
                "file_ref": row.file_ref,
            }
            writer.writerow({key: _safe_csv_value(value) for key, value in record.items()})
    return path


def write_sample_sheet(
    spec: SampleSheetSpec,
    destination: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Esporta uno spec senza perdere colonne opzionali o di estensione."""

    path = Path(destination)
    with _atomic_csv_writer(path, overwrite=overwrite) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=spec.headers,
            extrasaction="ignore",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in spec.rows:
            record: dict[str, object] = {
                # Gli extension field vengono inseriti prima: anche un oggetto
                # costruito da codice non puo sovrascrivere i valori canonici.
                **row.extra_fields,
                "sample_id": row.sample_id,
                "source_id": row.source_id,
                "preparation_id": row.preparation_id,
                "culture_id": row.culture_id,
                "plate_id": row.plate_id,
                "well_id": row.well_id,
                **row.factor_levels,
                "batch_id": row.batch_id,
                "timepoint": row.timepoint,
                "endpoint_id": row.endpoint_id,
                "lifecycle_status": row.lifecycle_status.value,
                "exclusion_reason": row.exclusion_reason,
                "file_ref": row.file_ref,
            }
            writer.writerow(
                {header: _safe_csv_value(record.get(header)) for header in spec.headers}
            )
    return path
