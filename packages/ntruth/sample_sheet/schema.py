"""Contratto canonico del sample sheet iniziale (PRD v6, Appendice O).

Il sample sheet descrive provenance, contenimento, fattori e lifecycle dei
campioni. Gli identificatori sono chiavi locali: la loro presenza, unicita o
costanza non costituisce mai evidenza di allocazione o indipendenza.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Self

from pydantic import Field, field_validator, model_validator

from ntruth.schemas.core import NTruthModel

SAMPLE_SHEET_SCHEMA_VERSION = "6.0"
FACTOR_COLUMN_PREFIX = "factor_level_"

# Appendice O: questi header devono essere sempre presenti, anche quando i due
# identificatori di provenance contengono valori nulli.
REQUIRED_HEADERS: tuple[str, ...] = (
    "sample_id",
    "source_id",
    "preparation_id",
    "lifecycle_status",
)

# Colonne standard opzionali. Il template le include tutte per evitare che una
# successiva raccolta dati debba cambiare forma a meta esperimento.
OPTIONAL_HEADERS: tuple[str, ...] = (
    "culture_id",
    "plate_id",
    "well_id",
    "batch_id",
    "timepoint",
    "endpoint_id",
    "exclusion_reason",
    "file_ref",
)

# Alias ammessi soltanto al confine CSV. Gli oggetti e gli export canonici
# usano sempre i nomi dell'Appendice O.
HEADER_ALIASES: dict[str, str] = {
    "batch": "batch_id",
    "endpoint": "endpoint_id",
    "status": "lifecycle_status",
    "factor_level": "factor_level_treatment",
}

_FACTOR_COLUMN_RE = re.compile(r"^factor_level_[a-z0-9][a-z0-9_.-]*$")
_BARE_NUMBER_RE = re.compile(r"^[+-]?\d+(?:[.,]\d+)?$")


class SampleLifecycleStatus(StrEnum):
    """Stati ammessi per una riga del sample sheet iniziale."""

    PLANNED = "planned"
    TREATED = "treated"
    OBSERVED = "observed"
    EXCLUDED = "excluded"
    ANALYSED = "analysed"

    @classmethod
    def _missing_(cls, value: object) -> SampleLifecycleStatus | None:
        # Migrazione controllata dallo spelling US, senza perpetuarlo in output.
        if isinstance(value, str) and value.strip().casefold() == "analyzed":
            return cls.ANALYSED
        return None


def normalize_factor_column(name: str) -> str:
    """Normalizza e valida il nome CSV di un fattore."""

    normalized = name.strip().casefold().replace(" ", "_")
    normalized = HEADER_ALIASES.get(normalized, normalized)
    if not _FACTOR_COLUMN_RE.fullmatch(normalized):
        raise ValueError(
            f"la colonna del fattore deve seguire il pattern '{FACTOR_COLUMN_PREFIX}<nome>'"
        )
    return normalized


class SampleSheetRow(NTruthModel):
    """Riga canonica indipendente dalla rappresentazione CSV.

    I livelli dei fattori sono metadati categoriali osservati. Il modello non
    espone deliberatamente campi di allocazione o indipendenza.
    """

    sample_id: str
    source_id: str | None
    preparation_id: str | None
    culture_id: str | None = None
    plate_id: str | None = None
    well_id: str | None = None
    factor_levels: dict[str, str] = Field(min_length=1)
    batch_id: str | None = None
    timepoint: str | None = None
    endpoint_id: str | None = None
    lifecycle_status: SampleLifecycleStatus
    exclusion_reason: str | None = None
    file_ref: str | None = None
    extra_fields: dict[str, str | None] = Field(default_factory=dict)

    @field_validator(
        "sample_id",
        "source_id",
        "preparation_id",
        "culture_id",
        "plate_id",
        "well_id",
        "batch_id",
        "timepoint",
        "endpoint_id",
        "exclusion_reason",
        "file_ref",
        mode="before",
    )
    @classmethod
    def _strip_cells(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        return stripped or None

    @field_validator("sample_id")
    @classmethod
    def _sample_id_is_present(cls, value: str | None) -> str:
        if not value:
            raise ValueError("sample_id non puo essere nullo o vuoto")
        return value

    @field_validator("timepoint")
    @classmethod
    def _timepoint_has_explicit_unit(cls, value: str | None) -> str | None:
        if value is not None and _BARE_NUMBER_RE.fullmatch(value):
            raise ValueError("timepoint numerico senza unita temporale esplicita")
        return value

    @field_validator("factor_levels", mode="before")
    @classmethod
    def _normalize_factor_levels(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        normalized: dict[str, str] = {}
        for raw_name, raw_value in value.items():
            name = normalize_factor_column(str(raw_name))
            level = str(raw_value).strip() if raw_value is not None else ""
            if not level:
                raise ValueError(f"valore mancante per '{name}'")
            if name in normalized:
                raise ValueError(f"fattore duplicato dopo normalizzazione: '{name}'")
            normalized[name] = level
        return normalized

    @model_validator(mode="after")
    def _exclusion_has_reason(self) -> Self:
        if self.lifecycle_status is SampleLifecycleStatus.EXCLUDED and not self.exclusion_reason:
            raise ValueError("exclusion_reason e obbligatorio quando lifecycle_status=excluded")
        reserved = set(REQUIRED_HEADERS) | set(OPTIONAL_HEADERS) | set(self.factor_levels)
        collisions = sorted(
            key
            for key in self.extra_fields
            if key in reserved or key.startswith(FACTOR_COLUMN_PREFIX)
        )
        if collisions:
            raise ValueError(
                "extra_fields non puo ridefinire campi canonici: " + ", ".join(collisions)
            )
        return self


class SampleSheetSpec(NTruthModel):
    """Sample sheet validato, con forma e provenance del file esplicite."""

    schema_version: str = SAMPLE_SHEET_SCHEMA_VERSION
    headers: tuple[str, ...]
    factor_columns: tuple[str, ...] = Field(min_length=1)
    rows: tuple[SampleSheetRow, ...]
    source_name: str | None = None
    content_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @field_validator("headers", mode="before")
    @classmethod
    def _normalize_headers(cls, value: object) -> object:
        if not isinstance(value, (tuple, list)):
            return value
        normalized = (str(header).strip().casefold().replace(" ", "_") for header in value)
        return tuple(HEADER_ALIASES.get(header, header) for header in normalized)

    @field_validator("factor_columns", mode="before")
    @classmethod
    def _normalize_factor_columns(cls, value: object) -> object:
        if not isinstance(value, (tuple, list)):
            return value
        return tuple(normalize_factor_column(str(column)) for column in value)

    @model_validator(mode="after")
    def _validate_shape(self) -> Self:
        if len(set(self.headers)) != len(self.headers):
            raise ValueError("gli header del sample sheet devono essere univoci")
        if len(set(self.factor_columns)) != len(self.factor_columns):
            raise ValueError("factor_columns deve contenere nomi univoci")

        missing = [header for header in REQUIRED_HEADERS if header not in self.headers]
        if missing:
            raise ValueError(f"header obbligatori mancanti: {', '.join(missing)}")

        discovered = tuple(
            header for header in self.headers if header.startswith(FACTOR_COLUMN_PREFIX)
        )
        if not discovered:
            raise ValueError("serve almeno una colonna factor_level_*")
        if set(discovered) != set(self.factor_columns):
            raise ValueError("factor_columns non coincide con gli header factor_level_*")

        sample_ids = [row.sample_id for row in self.rows]
        if len(sample_ids) != len(set(sample_ids)):
            raise ValueError("sample_id deve essere univoco")

        expected_factors = set(self.factor_columns)
        for index, row in enumerate(self.rows, start=2):
            if set(row.factor_levels) != expected_factors:
                raise ValueError(f"riga CSV {index}: livelli dei fattori incompleti o inattesi")
        return self
