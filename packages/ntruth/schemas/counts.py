"""Conteggi scope-aware e semantica canonica dei conteggi (PRD v7 §7.9, §15.10).

Regole vincolanti:
- ogni conteggio decisivo dichiara unit type, factor, contrast, endpoint, group,
  timepoint, lifecycle stage, quantifier, population scope, condition, evidence
  e rule trace;
- i conteggi globali senza scope sono vietati quando il bundle contiene piu
  fattori, endpoint o timepoint;
- ``effective_n`` resta diagnostico e non ripara la replicazione del disegno;
- ``biological_source_count`` e semanticamente distinto da
  ``experimental_unit_count`` anche quando i valori numerici coincidono;
- il parser non emette mai ``independent_n`` o ``experimental_unit_count`` finali.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from ntruth.schemas.core import FrozenModel, content_checksum, stable_id


class Quantifier(StrEnum):
    """Quantificatori (PRD v7 §7.10): nessun limite convertito in valore esatto."""

    EXACT = "EXACT"
    LOWER_BOUND = "LOWER_BOUND"
    UPPER_BOUND = "UPPER_BOUND"
    APPROXIMATE = "APPROXIMATE"
    RANGE = "RANGE"
    UNKNOWN = "UNKNOWN"
    NOT_REPORTED = "NOT_REPORTED"


class CountKind(StrEnum):
    """Tipi canonici di conteggio (PRD v7 §7.9, lifecycle completo)."""

    PLANNED_N = "planned_n"
    ALLOCATED_N = "allocated_n"
    TREATED_N = "treated_n"
    OBSERVED_N = "observed_n"
    EXCLUDED_N = "excluded_n"
    N_ANALYZED = "n_analyzed"
    DECLARED_N = "declared_n"
    OBSERVATIONAL_N = "observational_n"
    ANALYTICAL_N = "analytical_n"
    INDEPENDENT_N = "independent_n"
    EXPERIMENTAL_UNIT_COUNT = "experimental_unit_count"
    EXPERIMENTAL_UNIT_COUNT_CANDIDATE = "experimental_unit_count_candidate"
    BIOLOGICAL_SOURCE_COUNT = "biological_source_count"
    EFFECTIVE_N = "effective_n"  # solo diagnostico


#: Alias legacy accettati in input; l'output canonico usa sempre CountKind.
#: E-10: spelling canonica "analyzed"; "analysed" accettata come alias.
COUNT_KIND_ALIASES: dict[str, CountKind] = {
    "analysed": CountKind.N_ANALYZED,
    "n_analysed": CountKind.N_ANALYZED,
    "n_independent": CountKind.INDEPENDENT_N,
    "n_declared": CountKind.DECLARED_N,
    "n_observational": CountKind.OBSERVATIONAL_N,
    "n_analytical": CountKind.ANALYTICAL_N,
    "n_experimental_units": CountKind.EXPERIMENTAL_UNIT_COUNT,
    "n_biological_sources": CountKind.BIOLOGICAL_SOURCE_COUNT,
}

#: Bootstrap Count Profile (PRD v7 §7.9): campi prioritari dei primi pilot.
BOOTSTRAP_COUNT_PROFILE: tuple[CountKind, ...] = (
    CountKind.DECLARED_N,
    CountKind.OBSERVATIONAL_N,
    CountKind.N_ANALYZED,
    CountKind.BIOLOGICAL_SOURCE_COUNT,
    CountKind.EXPERIMENTAL_UNIT_COUNT_CANDIDATE,
    CountKind.EXCLUDED_N,
)

#: Conteggi che solo il rules engine puo emettere (mai parser/annotazione).
RULE_ENGINE_ONLY_KINDS: frozenset[CountKind] = frozenset(
    {
        CountKind.INDEPENDENT_N,
        CountKind.EXPERIMENTAL_UNIT_COUNT,
    }
)


class CountOrigin(StrEnum):
    """Chi ha prodotto il conteggio: il parser resta candidate-only."""

    DECLARED_IN_SOURCE = "declared_in_source"
    SAMPLE_SHEET = "sample_sheet"
    ANNOTATION_CANDIDATE = "annotation_candidate"
    RULE_DERIVATION = "rule_derivation"


class CountRecord(FrozenModel):
    """Un conteggio legato al proprio scope (PRD v7 §15.10)."""

    id: str
    kind: CountKind
    value: int | None = Field(default=None, ge=0)
    unit_type: str | None = None
    factor_id: str | None = None
    contrast_id: str | None = None
    endpoint_id: str | None = None
    group_id: str | None = None
    timepoint_id: str | None = None
    lifecycle_stage: str | None = None
    quantifier: Quantifier = Quantifier.UNKNOWN
    population_scope: str | None = None
    condition: str | None = None
    source_evidence: tuple[str, ...] = ()
    rule_trace: tuple[str, ...] = ()
    origin: CountOrigin = CountOrigin.DECLARED_IN_SOURCE

    @model_validator(mode="after")
    def _invariants(self) -> Self:
        if self.value is None and self.quantifier is Quantifier.EXACT:
            raise ValueError("quantifier EXACT richiede un valore")
        if self.kind in RULE_ENGINE_ONLY_KINDS and self.origin is not CountOrigin.RULE_DERIVATION:
            raise ValueError(
                f"{self.kind.value} puo essere emesso solo dal rules engine, non dal parser"
            )
        if self.kind is CountKind.EFFECTIVE_N and (
            self.condition is None or "diagnostic" not in self.condition.lower()
        ):
            raise ValueError("effective_n deve dichiarare la sezione diagnostica")
        return self

    def scope_key(self) -> str:
        return "|".join(
            part or "-"
            for part in (
                self.factor_id,
                self.contrast_id,
                self.endpoint_id,
                self.group_id,
                self.timepoint_id,
            )
        )


def canonical_count_kind(raw: str) -> CountKind:
    """Normalizza le spelling legacy al tipo canonico (fail-closed)."""
    try:
        return CountKind(raw)
    except ValueError:
        pass
    alias = COUNT_KIND_ALIASES.get(raw.strip().lower())
    if alias is not None:
        return alias
    raise ValueError(f"tipo di conteggio non riconosciuto: {raw!r}")


def require_scope_for_multi_scope_bundle(
    counts: tuple[CountRecord, ...],
    *,
    multi_factor: bool,
    multi_endpoint: bool,
    multi_timepoint: bool,
) -> None:
    """Vieta conteggi globali quando il bundle ha piu fattori/endpoint/timepoint."""
    if not (multi_factor or multi_endpoint or multi_timepoint):
        return
    for count in counts:
        if multi_factor and count.factor_id is None:
            raise ValueError(f"{count.kind.value} senza factor_id in bundle multi-fattore")
        if multi_endpoint and count.endpoint_id is None:
            raise ValueError(f"{count.kind.value} senza endpoint_id in bundle multi-endpoint")
        if multi_timepoint and count.timepoint_id is None:
            raise ValueError(f"{count.kind.value} senza timepoint_id in bundle multi-timepoint")


def make_count_id(kind: CountKind, scope_key: str) -> str:
    return stable_id("cnt", str(kind), scope_key)


def count_checksum(counts: tuple[CountRecord, ...]) -> str:
    return content_checksum([c.model_dump(mode="json") for c in counts])


#: Separazione obbligatoria: effective_n non puo comparire nella stessa sezione
#: di independent_n (statistical-washing ban, PRD v7 §11.3-11.4).
DIAGNOSTIC_KINDS: frozenset[CountKind] = frozenset({CountKind.EFFECTIVE_N})
