"""PRD v9 §11.2: design matrix, aliasing perfetto e variazione intra-blocco.

Controlli strutturali deterministici sulla topologia di assegnazione
registrata. Non raccomandano mai un test statistico e non applicano alcuna
soglia universale sui pochi cluster (SRR-V8-013): il numero di blocchi e
riportato come dato, e l'unico giudizio strutturale emesso e' l'incapacita
dell'assegnazione registrata di sostenere il contrasto dichiarato.

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
    fully_aliased: bool
    aliased_factor_pairs: tuple[tuple[str, str], ...]
    #: factor_id -> variazione di livello presente dentro lo stesso blocco;
    #: None quando i blocchi non sono stati dichiarati (non valutabile).
    within_block_variation: Mapping[str, bool | None]
    #: dati, non soglia: numero di blocchi e dimensione del piu piccolo.
    blocks_count: int | None
    smallest_block_size: int | None

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
            "fully_aliased": self.fully_aliased,
        }


def evaluate_design_matrix(
    *,
    assignments: Mapping[str, Mapping[str, str]],
    declared_levels: Mapping[str, Sequence[str]],
    blocks: Mapping[str, str] | None = None,
) -> DesignMatrixCheck:
    """Deriva i fatti §11.2 dall'assegnazione unita-per-unita registrata.

    Fail-closed: livelli assegnati non dichiarati, fattori incompleti o
    assegnazioni vuote sono un errore del chiamante, non un dato mancante.
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
    for factor_id in factors:
        declared = list(declared_levels[factor_id])
        buckets: dict[str, list[str]] = {level: [] for level in declared}
        for unit_id in sorted(assignments):
            level = assignments[unit_id].get(factor_id)
            if level is None:
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

    aliased_pairs: list[tuple[str, str]] = []
    for index, first in enumerate(factors):
        for second in factors[index + 1 :]:
            if _perfectly_aliased(assignments, first, second):
                aliased_pairs.append((first, second))

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
                len({assignments[unit_id].get(factor_id) for unit_id in units}) > 1
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
