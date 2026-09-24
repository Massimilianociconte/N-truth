import type { D0DesignDraft, LifecycleStatus, SampleSheetRow } from "./types";

/** UI-only identities: never serialized into scientific input or derived from sample_id. */
export class D0RowIdentity {
  private readonly keys = new WeakMap<SampleSheetRow, string>();
  private next = 0;

  key(row: SampleSheetRow): string {
    let key = this.keys.get(row);
    if (!key) {
      key = `d0-row-${this.next++}`;
      this.keys.set(row, key);
    }
    return key;
  }

  update(row: SampleSheetRow, changes: Partial<SampleSheetRow>): SampleSheetRow {
    const updated = { ...row, ...changes };
    this.keys.set(updated, this.key(row));
    return updated;
  }
}

export function createSampleRow(rows: SampleSheetRow[], endpointId: string): SampleSheetRow {
  const ids = new Set(rows.map((row) => row.sampleId.trim()));
  let number = 1;
  while (ids.has(`D0-SAMPLE-${String(number).padStart(3, "0")}`)) number++;
  const wells = new Set(rows.filter((row) => row.plateId.trim() === "P01").map((row) => row.wellId.trim().toUpperCase()));
  let well = 1;
  while (wells.has(`A${String(well).padStart(2, "0")}`)) well++;
  return {
    sampleId: `D0-SAMPLE-${String(number).padStart(3, "0")}`,
    plateId: "P01", wellId: `A${String(well).padStart(2, "0")}`,
    sourceId: "", preparationId: "", cultureId: "", factorLevel: "",
    batchId: "", dayId: "", operatorId: "", incubatorId: "", timepoint: "",
    endpointId, lifecycleStatus: "planned", exclusionReason: "", fileRef: "",
  };
}

export function rowLocator(rowIndex: number, column = "A:P"): string {
  const row = rowIndex + 2;
  return `SampleSheet_D0!${column.split(":").map((part) => `${part}${row}`).join(":")}`;
}

export function sampleSheetLocator(rowCount: number): string {
  return rowCount > 0 ? `SampleSheet_D0!A2:P${rowCount + 1}` : "SampleSheet_D0!A1:P1";
}

export function allocationKey(row: SampleSheetRow, level: D0DesignDraft["allocationLevel"]): string {
  if (level === "Plate") return row.plateId.trim();
  if (level === "Well" && row.plateId.trim() && row.wellId.trim()) return `${row.plateId.trim()}::${row.wellId.trim()}`;
  return "";
}

export function countUniqueAllocationUnits(
  rows: SampleSheetRow[], group: string, allocationLevel: D0DesignDraft["allocationLevel"], status?: LifecycleStatus,
): number {
  return new Set(rows.filter((row) => row.factorLevel === group && (!status || row.lifecycleStatus === status))
    .map((row) => allocationKey(row, allocationLevel)).filter(Boolean)).size;
}
