"""Artefatti deterministici della Quick Design Session (PRD v7 §6.1).

Sample sheet, ID convention e Methods draft sono generati dal record: nessuna
indipendenza viene dedotta dai soli ID (PRD §20.3).
"""

from __future__ import annotations

SAMPLE_SHEET_COLUMNS: tuple[str, ...] = (
    "sample_id",
    "source_id",
    "preparation_id",
    "culture_id",
    "plate_id",
    "well_id",
    "factor_level",
    "batch_id",
    "timepoint",
    "endpoint_id",
    "lifecycle_status",
    "exclusion_reason",
    "file_ref",
)


def build_sample_sheet(
    *,
    rows: tuple[dict[str, str], ...],
) -> str:
    """CSV canonico SampleSheetSpec (App. O). Colonne mancanti -> stringa vuota."""
    lines = [",".join(SAMPLE_SHEET_COLUMNS)]
    for row in rows:
        lines.append(",".join(row.get(column, "") for column in SAMPLE_SHEET_COLUMNS))
    return "\n".join(lines) + "\n"


def build_id_convention(
    *,
    block_label: str,
    factor_id: str,
) -> str:
    """Convenzione di naming leggibile; gli ID non provano l'indipendenza."""
    return (
        f"{block_label}: source=S###, preparation=P###, culture=C###, "
        f"plate=PL##, well=PL##_W##, {factor_id} level appended as _L##"
    )


def build_methods_draft(
    *,
    source_description: str,
    factor_id: str,
    levels: tuple[str, ...],
    endpoint_id: str,
    allocation_level: str,
    assignment_timing: str,
) -> str:
    """Bozza Methods con i buchi informativi resi espliciti, mai riempiti."""
    levels_text = " and ".join(levels)
    timing = (
        f"Assignment of {factor_id} levels occurred {assignment_timing} relative to splitting."
        if assignment_timing != "unknown"
        else f"Assignment timing of {factor_id} relative to splitting: NOT REPORTED."
    )
    allocation = (
        f"{factor_id} was allocated at the {allocation_level} level."
        if allocation_level != "unknown"
        else f"Allocation level of {factor_id}: NOT REPORTED."
    )
    return "\n".join(
        [
            f"Biological source: {source_description}.",
            f"Primary factor: {factor_id} with levels {levels_text}.",
            allocation,
            timing,
            f"Primary endpoint: {endpoint_id}.",
            "Independence of biological sources and preparation: NOT REPORTED.",
            "Interference / shared exposure assessment: NOT REPORTED.",
        ]
    )
