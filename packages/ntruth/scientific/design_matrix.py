"""PRD v9 §11.2: design matrix, aliasing perfetto e variazione intra-blocco.

Controlli strutturali deterministici sulla topologia di assegnazione
registrata. Non raccomandano mai un test statistico e non applicano alcuna
soglia universale sui pochi cluster (SRR-V8-013): il numero di blocchi e
riportato come dato, e l'unico giudizio strutturale emesso e' l'incapacita
dell'assegnazione registrata di sostenere il contrasto dichiarato.

Semantica open-world (audit 2026-09-12, A02/A03):

- un'unita senza livello registrato per un fattore e un dato mancante, mai un
  livello: non crea variazione intra-blocco e rende esplicita l'incompletezza
  (``unassigned_units``), che limita il supporto a PARTIALLY_SUPPORTED;
- l'aliasing e una relazione fra due fattori: il gate di un fattore consuma
  solo gli alias che lo coinvolgono, non quelli fra nuisance estranei;
- un fattore costante dentro ogni livello multi-unita di un altro fattore
  (es. trattamento per gabbia, misure per topo) varia solo fra cluster: il
  contrasto dipende da un'assunzione non registrata sul ruolo del cluster
  (unita di assegnazione oppure nuisance confondente) e non puo essere
  SUPPORTED_WITHIN_RECORDED_DESIGN. E un fatto descrittivo, non un verdetto
  sul modello statistico (HANDOFF_ONLY).

Gli output alimentano i gate v9 (`scientific.v9_gates`) con i booleani che il
contratto richiede ma che nessun modulo calcolava dal grafo.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DesignMatrixCheck:
    """Fatti strutturali §11.2; mai una valutazione statistica."""

    units: int
    factors: tuple[str, ...]
    #: factor_id -> level -> unit ids (ordinati, deterministici)
    level_partition: Mapping[str, Mapping[str, tuple[str, ...]]]
    #: livelli dichiarati senza alcuna unita assegnata
    levels_without_units: tuple[tuple[str, str], ...]
    #: True quando almeno una coppia di fattori e perfettamente aliasata
    #: (fatto globale della matrice; il gate usa ``aliased_with``).
    fully_aliased: bool
    aliased_factor_pairs: tuple[tuple[str, str], ...]
    #: factor_id -> variazione di livelli *registrati* dentro lo stesso blocco;
    #: None quando i blocchi non sono stati dichiarati (non valutabile).
    within_block_variation: Mapping[str, bool | None]
    #: dati, non soglia: numero di blocchi e dimensione del piu piccolo.
    blocks_count: int | None
    smallest_block_size: int | None
    #: factor_id -> unita senza livello registrato (dato mancante, non livello).
    unassigned_units: Mapping[str, tuple[str, ...]]
    #: factor_id -> altri fattori nei cui livelli multi-unita il fattore e
    #: costante (varia solo fra cluster), esclusi gli alias perfetti.
    constant_within_levels_of: Mapping[str, tuple[str, ...]]

    def aliased_with(self, factor_id: str) -> tuple[str, ...]:
        """Fattori perfettamente aliasati con ``factor_id``."""

        return tuple(
            other
            for pair in self.aliased_factor_pairs
            if factor_id in pair
            for other in pair
            if other != factor_id
        )

    def gate_inputs_for_factor(self, factor_id: str) -> dict[str, bool]:
        """Booleani pronti per `scientific.v9_gates.gate_experimental_unit_claim`."""

        if factor_id not in self.level_partition:
            raise ValueError(f"factor {factor_id!r} is not part of the design matrix")
        variation = self.within_block_variation.get(factor_id)
        return {
            "levels_present": all(
                bool(units) for units in self.level_partition[factor_id].values()
            ),
            "within_block_variation": bool(variation),
            "fully_aliased": bool(self.aliased_with(factor_id)),
            "assignment_complete": not self.unassigned_units.get(factor_id),
            "between_cluster_only": bool(self.constant_within_levels_of.get(factor_id)),
        }


def evaluate_design_matrix(
    *,
    assignments: Mapping[str, Mapping[str, str]],
    declared_levels: Mapping[str, Sequence[str]],
    blocks: Mapping[str, str] | None = None,
) -> DesignMatrixCheck:
    """Deriva i fatti §11.2 dall'assegnazione unita-per-unita registrata.

    Fail-closed: livelli assegnati non dichiarati, fattori non dichiarati o
    assegnazioni vuote sono un errore del chiamante. Un fattore dichiarato ma
    non registrato per un'unita resta un dato mancante esplicito.
    """

    if not assignments:
        raise ValueError("assignments must not be empty")
    unknown_factors: set[str] = set()
    for unit_levels in assignments.values():
        unknown_factors.update(set(unit_levels) - set(declared_levels))
    if unknown_factors:
        raise ValueError(
            f"assignment factors not declared in the design matrix: {sorted(unknown_factors)}"
        )
    for factor_id, levels in declared_levels.items():
        if not levels:
            raise ValueError(f"factor {factor_id!r} declares no levels")
        if len(set(levels)) != len(levels):
            raise ValueError(f"factor {factor_id!r} declares duplicate levels")

    factors = tuple(sorted(declared_levels))
    level_partition: dict[str, dict[str, tuple[str, ...]]] = {}
    levels_without_units: list[tuple[str, str]] = []
    unassigned: dict[str, tuple[str, ...]] = {}
    for factor_id in factors:
        declared = list(declared_levels[factor_id])
        buckets: dict[str, list[str]] = {level: [] for level in declared}
        missing: list[str] = []
        for unit_id in sorted(assignments):
            level = assignments[unit_id].get(factor_id)
            if level is None:
                missing.append(unit_id)
                continue
            if level not in buckets:
                raise ValueError(
                    f"unit {unit_id!r} assigns undeclared level {level!r} of {factor_id!r}"
                )
            buckets[level].append(unit_id)
        level_partition[factor_id] = {
            level: tuple(units) for level, units in sorted(buckets.items())
        }
        levels_without_units.extend(
            (factor_id, level) for level, units in level_partition[factor_id].items() if not units
        )
        unassigned[factor_id] = tuple(missing)

    aliased_pairs: list[tuple[str, str]] = []
    for index, first in enumerate(factors):
        for second in factors[index + 1 :]:
            if _perfectly_aliased(assignments, first, second):
                aliased_pairs.append((first, second))
    aliased_set = {frozenset(pair) for pair in aliased_pairs}

    nesting: dict[str, tuple[str, ...]] = {}
    for factor_id in factors:
        nesting[factor_id] = tuple(
            other
            for other in factors
            if other != factor_id
            and frozenset((factor_id, other)) not in aliased_set
            and _constant_within_multi_unit_levels(assignments, factor_id, other)
        )

    variation: dict[str, bool | None] = {factor_id: None for factor_id in factors}
    blocks_count: int | None = None
    smallest_block_size: int | None = None
    if blocks is not None:
        missing_blocks = sorted(set(assignments) - set(blocks))
        if missing_blocks:
            raise ValueError(
                f"units without a block assignment: {missing_blocks[:5]}"
                + (" ..." if len(missing_blocks) > 5 else "")
            )
        grouped: dict[str, list[str]] = {}
        for unit_id, block_id in blocks.items():
            grouped.setdefault(block_id, []).append(unit_id)
        blocks_count = len(grouped)
        smallest_block_size = min(len(units) for units in grouped.values()) if grouped else 0
        for factor_id in factors:
            variation[factor_id] = any(
                len(_recorded_levels(assignments, units, factor_id)) > 1
                for units in grouped.values()
            )

    return DesignMatrixCheck(
        units=len(assignments),
        factors=factors,
        level_partition=level_partition,
        levels_without_units=tuple(sorted(levels_without_units)),
        fully_aliased=bool(aliased_pairs),
        aliased_factor_pairs=tuple(aliased_pairs),
        within_block_variation=variation,
        blocks_count=blocks_count,
        smallest_block_size=smallest_block_size,
        unassigned_units=unassigned,
        constant_within_levels_of=nesting,
    )


def _recorded_levels(
    assignments: Mapping[str, Mapping[str, str]], units: Sequence[str], factor_id: str
) -> set[str]:
    """Livelli registrati nel gruppo di unita; i mancanti non sono un livello."""

    levels: set[str] = set()
    for unit_id in units:
        level = assignments.get(unit_id, {}).get(factor_id)
        if level is not None:
            levels.add(level)
    return levels


def _constant_within_multi_unit_levels(
    assignments: Mapping[str, Mapping[str, str]], factor: str, grouping: str
) -> bool:
    """True quando ``factor`` varia solo fra i livelli di ``grouping``.

    Considera le sole unita con entrambi i livelli registrati. Richiede che
    ``factor`` abbia almeno due livelli, che ogni livello di ``grouping``
    contenga un solo livello di ``factor`` e che almeno un livello di
    ``grouping`` raggruppi due o piu unita: un identificativo per-unita non e
    un cluster.
    """

    levels_by_group: dict[str, set[str]] = {}
    units_by_group: dict[str, int] = {}
    for unit_levels in assignments.values():
        level = unit_levels.get(factor)
        group = unit_levels.get(grouping)
        if level is None or group is None:
            continue
        levels_by_group.setdefault(group, set()).add(level)
        units_by_group[group] = units_by_group.get(group, 0) + 1
    distinct_levels = set().union(*levels_by_group.values()) if levels_by_group else set()
    return (
        len(distinct_levels) >= 2
        and all(len(levels) == 1 for levels in levels_by_group.values())
        and any(count >= 2 for count in units_by_group.values())
    )


def _perfectly_aliased(
    assignments: Mapping[str, Mapping[str, str]], first: str, second: str
) -> bool:
    """True quando i due fattori partizionano le unita nello stesso modo.

    Alias perfetto = ogni livello del primo fattore co-occorre con esattamente
    un livello del secondo e viceversa (confondimento strutturale, §11.2).
    """

    observed: set[tuple[str, str]] = set()
    for unit_levels in assignments.values():
        level_first = unit_levels.get(first)
        level_second = unit_levels.get(second)
        if level_first is None or level_second is None:
            continue
        observed.add((level_first, level_second))
    distinct_first = {pair[0] for pair in observed}
    distinct_second = {pair[1] for pair in observed}
    if len(distinct_first) < 2 or len(distinct_second) < 2:
        return False
    return len(observed) == len(distinct_first) == len(distinct_second)
