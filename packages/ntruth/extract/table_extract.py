"""Estrazione dal sample sheet (PRD FR-005, 11.2).

Il sample sheet contiene la provenance essenziale: quale campione viene da quale
sorgente e a quale livello e stato applicato il fattore. Da una tabella queste
relazioni si derivano in modo esatto, non probabilistico, per questo l'input
tabulare migliora la ricostruzione rispetto al solo testo (PRD ipotesi H5).
"""

from __future__ import annotations

import re

from ntruth.extract.facts import (
    EntityFact,
    EntityInstanceFact,
    ExtractionResult,
    FactorFact,
    FactorKind,
    InstanceAssignmentFact,
    InstanceRelationFact,
    ProcessFact,
    RelationFact,
    make_evidence,
)
from ntruth.schemas.core import CellRef, EvidenceSpan, EvidenceType, ProvenanceKind, stable_id
from ntruth.schemas.document import DocumentIR, Table
from ntruth.schemas.graph import CLUSTER_TYPES, NodeType, RelationType, rank_of

#: Colonna -> livello gerarchico. L'ordine conta: il primo pattern che
#: corrisponde vince.
COLUMN_LEVELS: list[tuple[NodeType, re.Pattern[str]]] = [
    (NodeType.CAGE, re.compile(r"^(cage|gabbia)(_?id)?$", re.I)),
    (NodeType.LITTER, re.compile(r"^(litter|cucciolata)(_?id)?$", re.I)),
    (NodeType.DAM, re.compile(r"^(dam|mother|madre)(_?id)?$", re.I)),
    (
        NodeType.HUMAN_DONOR,
        re.compile(r"^(donor|subject|patient|individual|donatore|soggetto)(_?id)?$", re.I),
    ),
    (
        NodeType.ANIMAL,
        re.compile(r"^(animal|mouse|rat|pup|animale|topo|ratto)(_?id)?$", re.I),
    ),
    (NodeType.CELL_LINE, re.compile(r"^(cell_?line|line|linea(_cellulare)?)(_?id)?$", re.I)),
    (NodeType.TISSUE, re.compile(r"^(tissue|region|tessuto|regione)(_?id)?$", re.I)),
    (
        NodeType.CELL_CULTURE,
        re.compile(
            r"^(culture|prep|preparation|isolation|dissection|thaw|passage|"
            r"coltura|preparazione|isolamento|passaggio)(_?id|_?number)?$",
            re.I,
        ),
    ),
    (NodeType.ORGANOID, re.compile(r"^(organoid|organoide)(_?id)?$", re.I)),
    (NodeType.EXPLANT, re.compile(r"^(explant|espianto)(_?id)?$", re.I)),
    (NodeType.POOL, re.compile(r"^(pool)(_?id)?$", re.I)),
    (NodeType.ALIQUOT, re.compile(r"^(aliquot|aliquota)(_?id)?$", re.I)),
    (NodeType.PLATE, re.compile(r"^(plate|dish|coverslip|piastra)(_?id)?$", re.I)),
    (NodeType.WELL, re.compile(r"^(well|pozzetto)(_?id|_?position)?$", re.I)),
    (NodeType.SECTION_SLICE, re.compile(r"^(section|slice|slide|sezione|vetrino)(_?id)?$", re.I)),
    (NodeType.FIELD, re.compile(r"^(field|fov|image|frame|campo|immagine)(_?id)?$", re.I)),
    (NodeType.ROI, re.compile(r"^(roi|region_of_interest)(_?id)?$", re.I)),
    (NodeType.CELL, re.compile(r"^(cell|nucleus|neuron|cellula|nucleo|neurone)(_?id)?$", re.I)),
    (NodeType.LIBRARY, re.compile(r"^(library|libreria)(_?id)?$", re.I)),
    (NodeType.RUN, re.compile(r"^(run|lane|session|sessione)(_?id)?$", re.I)),
    (NodeType.BATCH, re.compile(r"^(batch|lot|lotto)(_?id)?$", re.I)),
]

FACTOR_COLUMNS: list[tuple[str, FactorKind, re.Pattern[str]]] = [
    (
        "treatment",
        "treatment",
        re.compile(r"^(treatment|drug|compound|stimulus|trattamento)$", re.I),
    ),
    ("group", "treatment", re.compile(r"^(group|condition|arm|gruppo|condizione)$", re.I)),
    ("genotype", "genotype", re.compile(r"^(genotype|genotipo|strain|line_genotype)$", re.I)),
    ("dose", "dose", re.compile(r"^(dose|concentration|dosaggio|concentrazione)$", re.I)),
    ("diet", "diet", re.compile(r"^(diet|dieta|chow)$", re.I)),
    ("time", "time", re.compile(r"^(time|timepoint|time_?point|day|week|hour|tempo)$", re.I)),
    ("sex", "other", re.compile(r"^(sex|gender|sesso)$", re.I)),
]

EXCLUSION_COLUMNS = re.compile(
    r"^(exclude[d]?|exclusion|qc|qc_?pass|include[d]?|status|escluso|esclusione)$", re.I
)

COUNT_COLUMNS = re.compile(
    r"^(n|count|n_?cells?|cell_?count|n_?fields?|field_?count|n_?wells?|"
    r"numero|conteggio)$",
    re.I,
)


def extract_from_tables(ir: DocumentIR) -> ExtractionResult:
    result = ExtractionResult()
    for table in ir.tables:
        if not table.rows or not table.columns:
            continue
        _extract_table(ir, table, result)
    result.dedupe_evidence()
    return result


def _evidence(
    result: ExtractionResult, ir: DocumentIR, table: Table, column: str, row: int, text: str
) -> EvidenceSpan | None:
    cell = CellRef(table_id=table.id, row=row, column=column, sheet=table.sheet)
    return result.register(
        make_evidence(
            file_id=table.file_id,
            section_title=f"{table.name}",
            cell=cell,
            text=text,
            parser_version=ir.parser_version,
            evidence_type=EvidenceType.SAMPLE_METADATA,
            extraction_method="deterministic_table_extraction",
        )
    )


def _extract_table(ir: DocumentIR, table: Table, result: ExtractionResult) -> None:
    level_columns = _detect_levels(table)
    factor_columns = _detect_factors(table)

    for column in level_columns:
        missing = sum(1 for row in table.rows if not (row.get(column) or "").strip())
        if missing:
            result.warnings.append(
                f"sample sheet '{table.name}': {missing} valori mancanti nella colonna "
                f"identificativa '{column}'"
            )

    for column, node_type in level_columns.items():
        values = _distinct(table, column)
        evidence = _evidence(
            result, ir, table, column, 0, f"colonna '{column}': {len(values)} valori distinti"
        )
        result.entities.append(
            EntityFact(
                node_type=node_type,
                label=str(node_type),
                count=len(values),
                evidence=evidence,
                origin=ProvenanceKind.TABULAR,
                confidence=0.98,
                attributes={"column": column, "table": table.name},
            )
        )
        _extract_instances(ir, table, column, node_type, result)

    _extract_nesting(ir, table, level_columns, result)

    for column, (name, kind) in factor_columns.items():
        levels = _distinct(table, column)
        if len(levels) < 2:
            continue
        assignment, confidence, detail = _assignment_level(table, column, level_columns)
        evidence = _evidence(
            result, ir, table, column, 0, f"colonna '{column}': livelli {sorted(levels)}"
        )
        result.factors.append(
            FactorFact(
                name=name,
                levels=tuple(sorted(levels)),
                kind=kind,
                assignment_level=assignment,
                assignment_confidence=confidence,
                assignment_evidence=evidence,
                evidence=evidence,
                origin=ProvenanceKind.TABULAR,
            )
        )
        if detail:
            result.warnings.append(detail)
        _extract_instance_assignments(
            ir,
            table,
            factor_column=column,
            factor_name=name,
            assignment_level=assignment,
            level_columns=level_columns,
            result=result,
        )
        _detect_confounding(ir, table, column, name, levels, level_columns, result)

    for column in table.columns:
        if EXCLUSION_COLUMNS.match(column):
            excluded = [
                i for i, row in enumerate(table.rows) if _is_excluded(row.get(column, ""), column)
            ]
            if excluded:
                evidence = _evidence(
                    result,
                    ir,
                    table,
                    column,
                    excluded[0],
                    f"colonna '{column}': {len(excluded)} record esclusi",
                )
                result.processes.append(
                    ProcessFact(
                        kind="exclusion",
                        detail=f"{len(excluded)} record marcati come esclusi in '{column}'",
                        value=len(excluded),
                        evidence=evidence,
                        origin=ProvenanceKind.TABULAR,
                    )
                )
        elif COUNT_COLUMNS.match(column):
            total = _sum_numeric(table, column)
            if total is not None:
                evidence = _evidence(
                    result, ir, table, column, 0, f"colonna '{column}': somma {total}"
                )
                result.processes.append(
                    ProcessFact(
                        kind="declared_count",
                        detail=f"somma della colonna '{column}'",
                        value=total,
                        evidence=evidence,
                        origin=ProvenanceKind.TABULAR,
                    )
                )


def _detect_confounding(
    ir: DocumentIR,
    table: Table,
    factor_col: str,
    factor_name: str,
    levels: set[str],
    level_columns: dict[str, NodeType],
    result: ExtractionResult,
) -> None:
    """Confondimento perfetto tra fattore e batch/giorno/piastra/operatore (GEN-005).

    Si verifica quando ogni istanza del cluster porta un solo livello del fattore
    e il numero di cluster coincide con il numero di livelli: in quel caso effetto
    del fattore ed effetto del cluster non sono separabili senza assunzioni.
    """
    for column, node_type in level_columns.items():
        if node_type not in CLUSTER_TYPES:
            continue
        instances = _distinct(table, column)
        if len(instances) < 2 or len(instances) != len(levels):
            continue
        if not _constant_within(table, column, factor_col):
            continue
        evidence = _evidence(
            result,
            ir,
            table,
            column,
            0,
            f"'{factor_col}' e costante entro ogni '{column}' e i due hanno lo stesso numero "
            f"di livelli ({len(levels)})",
        )
        result.processes.append(
            ProcessFact(
                kind="confounding",
                detail=(
                    f"il fattore '{factor_name}' e perfettamente confuso con "
                    f"'{column}' ({node_type})"
                ),
                node_type=node_type,
                value=len(instances),
                evidence=evidence,
                origin=ProvenanceKind.TABULAR,
            )
        )


def _instance_key(table: Table, column: str, value: str) -> str:
    """Chiave pseudonima stabile per un identificatore tabulare."""

    return stable_id("ein", table.id, column, value.strip())


def _extract_instances(
    ir: DocumentIR,
    table: Table,
    column: str,
    node_type: NodeType,
    result: ExtractionResult,
) -> None:
    """Materializza una istanza per ogni identificatore distinto non vuoto."""

    seen: set[str] = set()
    for row_index, row in enumerate(table.rows):
        value = (row.get(column) or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        key = _instance_key(table, column, value)
        evidence = _evidence(
            result,
            ir,
            table,
            column,
            row_index,
            f"{column}='{value}'",
        )
        result.entity_instances.append(
            EntityInstanceFact(
                node_type=node_type,
                instance_key=key,
                # Il valore originale resta nella sola evidenza locale: ne ID ne
                # label del grafo esportato contengono identificatori sorgente.
                label=f"{node_type} {key[-6:]}",
                evidence=evidence,
                attributes={"source_column": column, "source_table": table.name},
            )
        )


def _extract_instance_assignments(
    ir: DocumentIR,
    table: Table,
    *,
    factor_column: str,
    factor_name: str,
    assignment_level: NodeType | None,
    level_columns: dict[str, NodeType],
    result: ExtractionResult,
) -> None:
    """Lega un gruppo a una istanza solo con una colonna-identita univoca."""

    if assignment_level is None:
        return
    candidates = [
        column for column, node_type in level_columns.items() if node_type is assignment_level
    ]
    if len(candidates) != 1:
        result.warnings.append(
            f"sample sheet '{table.name}': impossibile legare '{factor_name}' alle istanze "
            f"di {assignment_level}; colonne candidate={candidates}"
        )
        return

    instance_column = candidates[0]
    seen: set[tuple[str, str]] = set()
    for row_index, row in enumerate(table.rows):
        instance_value = (row.get(instance_column) or "").strip()
        factor_level = (row.get(factor_column) or "").strip()
        if not instance_value or not factor_level:
            continue
        pair = (instance_value, factor_level.casefold())
        if pair in seen:
            continue
        seen.add(pair)
        evidence = _evidence(
            result,
            ir,
            table,
            factor_column,
            row_index,
            f"{factor_column}='{factor_level}' assegnato a {instance_column}='{instance_value}'",
        )
        result.instance_assignments.append(
            InstanceAssignmentFact(
                factor_name=factor_name,
                factor_level=factor_level,
                node_type=assignment_level,
                instance_key=_instance_key(table, instance_column, instance_value),
                evidence=evidence,
            )
        )


def _detect_levels(table: Table) -> dict[str, NodeType]:
    detected: dict[str, NodeType] = {}
    for column in table.columns:
        normalized = column.strip().lower().replace(" ", "_")
        for node_type, pattern in COLUMN_LEVELS:
            if pattern.match(normalized):
                detected[column] = node_type
                break
    return detected


def _detect_factors(table: Table) -> dict[str, tuple[str, FactorKind]]:
    detected: dict[str, tuple[str, FactorKind]] = {}
    for column in table.columns:
        normalized = column.strip().lower().replace(" ", "_")
        for name, kind, pattern in FACTOR_COLUMNS:
            if pattern.match(normalized):
                detected[column] = (name, kind)
                break
    return detected


def _distinct(table: Table, column: str) -> set[str]:
    return {v.strip() for v in table.values(column) if v and v.strip()}


def _sum_numeric(table: Table, column: str) -> int | None:
    total = 0
    seen = False
    for value in table.values(column):
        text = value.strip().replace(",", "")
        if not text:
            continue
        try:
            total += int(float(text))
            seen = True
        except ValueError:
            return None
    return total if seen else None


def _is_excluded(value: str, column: str) -> bool:
    """Interpreta la cella tenendo conto della polarita della colonna."""
    text = value.strip().lower()
    if not text:
        return False
    column_name = column.strip().lower()
    if column_name.startswith(("include", "qc", "incluso")):
        # Polarita inversa: "no"/"fail" significa escluso.
        return text in {"no", "false", "0", "fail", "excluded", "escluso"}
    return text in {"yes", "true", "1", "excluded", "fail", "si", "sì", "escluso", "drop"}


def _extract_nesting(
    ir: DocumentIR, table: Table, level_columns: dict[str, NodeType], result: ExtractionResult
) -> None:
    """Deriva l'annidamento dalle dipendenze funzionali tra colonne."""
    columns = list(level_columns)
    for child_col in columns:
        for parent_col in columns:
            if child_col == parent_col:
                continue
            child_type = level_columns[child_col]
            parent_type = level_columns[parent_col]
            if child_type is parent_type:
                continue
            if not _functionally_determines(table, child_col, parent_col):
                continue
            if _functionally_determines(table, parent_col, child_col):
                # Relazione 1:1: i due livelli sono indistinguibili nei dati.
                result.warnings.append(
                    f"'{child_col}' e '{parent_col}' sono in corrispondenza 1:1 nel sample "
                    f"sheet: i due livelli non sono separabili senza informazione aggiuntiva"
                )
            child_rank, parent_rank = rank_of(child_type), rank_of(parent_type)
            if child_rank is not None and parent_rank is not None and child_rank <= parent_rank:
                continue
            evidence = _evidence(
                result,
                ir,
                table,
                child_col,
                0,
                f"ogni valore di '{child_col}' corrisponde a un solo '{parent_col}'",
            )
            result.relations.append(
                RelationFact(
                    type=RelationType.NESTED_IN,
                    source_type=child_type,
                    target_type=parent_type,
                    evidence=evidence,
                    origin=ProvenanceKind.TABULAR,
                    confidence=0.97,
                    derivation=f"dipendenza funzionale {child_col} -> {parent_col}",
                )
            )
            seen_pairs: set[tuple[str, str]] = set()
            for row_index, row in enumerate(table.rows):
                child_value = (row.get(child_col) or "").strip()
                parent_value = (row.get(parent_col) or "").strip()
                if not child_value or not parent_value:
                    continue
                pair = (child_value, parent_value)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                instance_evidence = _evidence(
                    result,
                    ir,
                    table,
                    child_col,
                    row_index,
                    f"{child_col}='{child_value}' -> {parent_col}='{parent_value}'",
                )
                result.instance_relations.append(
                    InstanceRelationFact(
                        type=RelationType.NESTED_IN,
                        source_type=child_type,
                        source_key=_instance_key(table, child_col, child_value),
                        target_type=parent_type,
                        target_key=_instance_key(table, parent_col, parent_value),
                        evidence=instance_evidence,
                        derivation=(
                            f"riga {row_index}: dipendenza funzionale {child_col} -> {parent_col}"
                        ),
                    )
                )


def _functionally_determines(table: Table, child_col: str, parent_col: str) -> bool:
    """Vero se ogni valore di child corrisponde a un solo valore di parent."""
    mapping: dict[str, str] = {}
    seen_pairs = 0
    for row in table.rows:
        child = (row.get(child_col) or "").strip()
        parent = (row.get(parent_col) or "").strip()
        if not child or not parent:
            continue
        seen_pairs += 1
        if child in mapping and mapping[child] != parent:
            return False
        mapping[child] = parent
    return seen_pairs > 0 and len(mapping) > 1


def _assignment_level(
    table: Table, factor_col: str, level_columns: dict[str, NodeType]
) -> tuple[NodeType | None, float, str | None]:
    """Livello di assegnazione = livello piu alto in cui il fattore resta costante.

    La scelta del livello piu alto e conservativa: riduce l'n indipendente
    invece di gonfiarlo quando i dati non distinguono due livelli (PRD 28.3).
    """
    candidates: list[tuple[int, str, NodeType]] = []
    for column, node_type in level_columns.items():
        rank = rank_of(node_type)
        if rank is None:
            continue
        if _constant_within(table, column, factor_col):
            candidates.append((rank, column, node_type))
    if not candidates:
        return (
            None,
            0.0,
            (
                f"nessun livello del sample sheet mantiene costante '{factor_col}': "
                "il fattore varia entro ogni unita nota"
            ),
        )
    candidates.sort()
    rank, column, node_type = candidates[0]
    finest = candidates[-1]
    detail = None
    if len(candidates) > 1 and finest[2] is not node_type:
        detail = (
            f"'{factor_col}' e costante sia a livello '{column}' sia a livello "
            f"'{finest[1]}': assunto il livello piu alto ({node_type})"
        )
    return node_type, 0.95, detail


def _constant_within(table: Table, level_col: str, factor_col: str) -> bool:
    """Il fattore e costante entro ogni istanza del livello e varia tra istanze."""
    groups: dict[str, set[str]] = {}
    for row in table.rows:
        level = (row.get(level_col) or "").strip()
        factor = (row.get(factor_col) or "").strip()
        if not level or not factor:
            continue
        groups.setdefault(level, set()).add(factor)
    if len(groups) < 2:
        return False
    if any(len(values) > 1 for values in groups.values()):
        return False
    distinct_factor_values = {next(iter(v)) for v in groups.values()}
    return len(distinct_factor_values) > 1
