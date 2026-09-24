import { allocationKey, countUniqueAllocationUnits } from "./rowHelpers";
import type { D0DesignDraft, D0Language, SampleSheetRow } from "./types";

export type D0FieldTarget =
  | { step: "scope" | "profile"; field: keyof D0DesignDraft }
  | { step: "samples"; field: keyof SampleSheetRow; row: number };

export interface D0ValidationIssue {
  id: string;
  message: string;
  category: "required" | "invariant" | "capability" | "canonical";
  severity: "error" | "warning";
  targets: D0FieldTarget[];
}

export function draftTarget(field: keyof D0DesignDraft): D0FieldTarget {
  return { step: field === "question" || field === "inferenceTarget" ? "scope" : "profile", field };
}

export function fieldId(target: D0FieldTarget): string {
  return `d0-${target.step}-${target.step === "samples" ? `${target.row}-` : ""}${target.field}`;
}

export function validateD0(draft: D0DesignDraft, rows: SampleSheetRow[], language: D0Language): D0ValidationIssue[] {
  const issues: D0ValidationIssue[] = [];
  const text = (it: string, en: string) => language === "it" ? it : en;
  const add = (category: D0ValidationIssue["category"], message: string, targets: D0FieldTarget[]) => {
    issues.push({ id: `d0-local-${issues.length}`, category, message, targets, severity: "error" });
  };
  const cells = (indices: number[], fields: (keyof SampleSheetRow)[]): D0FieldTarget[] => indices.flatMap((row) => fields.map((field) => ({ step: "samples" as const, row, field })));
  const requiredDraft: (keyof D0DesignDraft)[] = ["question", "inferenceTarget", "factorName", "levelA", "levelB", "endpointName", "endpointId", "effectMeasure", "estimandTargetPopulation", "generalizationLevel", "reviewerRole"];
  if (draft.independentlyAssigned === "TRUE") requiredDraft.push("independenceMechanism");
  for (const field of requiredDraft) {
    if (!draft[field].trim()) add("required", text(`Manca: ${field}`, `Missing: ${field}`), [draftTarget(field)]);
  }
  rows.forEach((row, index) => {
    for (const field of ["sampleId", "plateId", "wellId", "factorLevel", "endpointId"] as const) {
      if (!row[field].trim()) add("required", text(`Manca: riga ${index + 1} · ${field}`, `Missing: row ${index + 1} · ${field}`), cells([index], [field]));
    }
  });
  if (draft.levelA.trim() && draft.levelA.trim() === draft.levelB.trim()) {
    add("invariant", text("I due livelli devono essere distinti.", "The two levels must differ."), [draftTarget("levelA"), draftTarget("levelB")]);
  }
  const duplicate = (key: (row: SampleSheetRow) => string, fields: (keyof SampleSheetRow)[], message: string) => {
    const groups = new Map<string, number[]>();
    rows.forEach((row, index) => {
      const value = key(row);
      if (value) groups.set(value, [...(groups.get(value) ?? []), index]);
    });
    const indices = [...groups.values()].filter((group) => group.length > 1).flat();
    if (indices.length) add("invariant", message, cells(indices, fields));
  };
  duplicate((row) => row.sampleId.trim(), ["sampleId"], text("sample_id duplicati.", "Duplicate sample_id values."));
  duplicate((row) => allocationKey(row, "Well"), ["plateId", "wellId"], text("Coordinate plate_id/well_id duplicate.", "Duplicate plate_id/well_id coordinates."));
  if (draft.allocationLevel !== "UNKNOWN") {
    const groups = new Map<string, number[]>();
    rows.forEach((row, index) => {
      const key = allocationKey(row, draft.allocationLevel);
      if (key) groups.set(key, [...(groups.get(key) ?? []), index]);
    });
    for (const [key, indices] of groups) {
      if (new Set(indices.map((index) => rows[index].factorLevel).filter(Boolean)).size > 1) {
        add("invariant", text(`L'unità di allocazione ${key} è associata a più livelli del fattore.`, `Allocation unit ${key} is associated with multiple factor levels.`), [draftTarget("allocationLevel"), ...cells(indices, ["factorLevel", "plateId", "wellId"])]);
      }
    }
    for (const level of [draft.levelA, draft.levelB]) {
      if (level.trim() && countUniqueAllocationUnits(rows, level, draft.allocationLevel) === 0) {
        add("invariant", text(`Il livello '${level}' non contiene alcuna unità di allocazione.`, `Level '${level}' has no allocation unit.`), cells(rows.map((_, index) => index), ["factorLevel"]));
      }
    }
  }
  rows.forEach((row, index) => {
    if (row.factorLevel && ![draft.levelA, draft.levelB].includes(row.factorLevel)) add("invariant", text(`Riga ${index + 1}: livello del fattore fuori dal contrasto primario.`, `Row ${index + 1}: factor level is outside the primary contrast.`), cells([index], ["factorLevel"]));
    if (row.endpointId && row.endpointId !== draft.endpointId) add("invariant", text(`Riga ${index + 1}: endpoint_id non coincide con l'endpoint primario.`, `Row ${index + 1}: endpoint_id does not match the primary endpoint.`), cells([index], ["endpointId"]));
    const reason = row.exclusionReason;
    if (row.lifecycleStatus === "excluded" && !(/(pre-allocation|post-allocation|post-treatment|post-measurement|post-outcome)/i.test(reason) && /(?:autore|author)\s*:/i.test(reason) && /(?:criterio|criterion)\s*:/i.test(reason))) {
      add("invariant", text(`Riga ${index + 1}: l'esclusione richiede fase e autore.`, `Row ${index + 1}: exclusion requires a stage and author.`), cells([index], ["exclusionReason"]));
    }
  });
  const timepoints = [...new Set(rows.map((row) => row.timepoint.trim()).filter(Boolean))];
  if (timepoints.length > 1) add("capability", text("Il profilo D0 accetta un solo timepoint esplicito.", "The D0 profile accepts one explicit timepoint only."), cells(rows.flatMap((row, index) => row.timepoint.trim() ? [index] : []), ["timepoint"]));
  for (const timepoint of timepoints) {
    if (!/^\d+(?:[.,]\d+)?\s*(?:ms|s|sec|min|h|hr|d|day|days)$/i.test(timepoint)) add("capability", text(`Timepoint '${timepoint}' privo di unità temporale supportata.`, `Timepoint '${timepoint}' lacks a supported time unit.`), cells(rows.flatMap((row, index) => row.timepoint.trim() === timepoint ? [index] : []), ["timepoint"]));
  }
  return issues;
}

const rowFields: (keyof SampleSheetRow)[] = ["sampleId", "sourceId", "preparationId", "cultureId", "plateId", "wellId", "factorLevel", "batchId", "dayId", "operatorId", "incubatorId", "timepoint", "endpointId", "lifecycleStatus", "exclusionReason", "fileRef"];
const draftFields: (keyof D0DesignDraft)[] = ["question", "inferenceTarget", "factorName", "factorKind", "levelA", "levelB", "endpointName", "endpointId", "allocationLevel", "applicationLevel", "independentlyAssigned", "independenceMechanism", "sharedEnvironment", "targetBiologicalUnit", "effectMeasure", "estimandTargetPopulation", "generalizationLevel", "estimandCondition", "reviewerRole"];
const normalize = (field: string) => field.replace(/[_ .]/g, "").toLowerCase();
const aliases: Record<string, keyof D0DesignDraft> = {
  "estimand.effect_measure": "effectMeasure", "estimand.effectMeasure": "effectMeasure",
  "estimand.target_population_or_unit": "estimandTargetPopulation", "estimand.targetPopulationOrUnit": "estimandTargetPopulation",
  "estimand.generalization_level": "generalizationLevel", "estimand.generalizationLevel": "generalizationLevel",
  "estimand.condition": "estimandCondition", "target_population_or_unit": "estimandTargetPopulation",
};

/** Presentation only; retain unknown locations rather than guessing a scientific correction. */
export function canonicalIssues(raw: unknown, rows: SampleSheetRow[]): D0ValidationIssue[] {
  if (!Array.isArray(raw)) return [];
  return raw.map((value, index) => {
    const issue = value && typeof value === "object" ? value as Record<string, unknown> : { message: String(value) };
    const fields = [...new Set([issue.field, ...(Array.isArray(issue.fields) ? issue.fields : [])].filter((field): field is string => typeof field === "string"))];
    const targets: D0FieldTarget[] = [];
    for (const field of fields) {
      const name = field.replace(/^draft\./, "");
      const rowField = rowFields.find((key) => normalize(key) === normalize(name)) ?? (name.startsWith("factor_level_") ? "factorLevel" : name.startsWith("exclusion_") ? "exclusionReason" : undefined);
      const draftField = aliases[name] ?? draftFields.find((key) => normalize(key) === normalize(name));
      if (rowField && (issue.row != null || !draftField)) {
        const indices = issue.row == null ? rows.map((_, row) => row) : typeof issue.row === "number" && Number.isInteger(issue.row) && issue.row >= 1 && issue.row <= rows.length ? [issue.row - 1] : [];
        targets.push(...indices.map((row) => ({ step: "samples" as const, row, field: rowField })));
      } else if (draftField) targets.push(draftTarget(draftField));
    }
    const location = [issue.row != null ? `row ${String(issue.row)}` : "", ...fields].filter(Boolean).join(" · ");
    return {
      id: `d0-canonical-${index}`, category: "canonical", severity: issue.severity === "warning" ? "warning" : "error",
      message: `${String(issue.code ?? "issue")}: ${String(issue.message ?? "")}${location ? ` · ${location}` : ""}`,
      targets: targets.filter((target, i) => targets.findIndex((item) => fieldId(item) === fieldId(target)) === i),
    };
  });
}
