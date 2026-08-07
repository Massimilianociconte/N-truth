import { AlertTriangle, Check, GitCompareArrows, Plus, Trash2 } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";

import {
  ApiError,
  submitPlanExecution,
  type ProspectiveD0CompileResponse,
} from "../api";
import type {
  PlanExecutionDesignSnapshot,
  PlanExecutionDeviation,
  PlanExecutionDeviationCategory,
  PlanExecutionExclusion,
  PlanExecutionExclusionPhase,
  PlanExecutionLostSample,
  PlanExecutionPooling,
  PlanExecutionSubmitPayload,
  PlanExecutionSubstitution,
  PlanExecutionTreatmentChange,
  PlanExecutionTriState,
} from "./planExecutionTypes";
import type { D0DesignDraft, D0Language, SampleSheetRow } from "./types";

const DEVIATION_CATEGORIES: PlanExecutionDeviationCategory[] = [
  "design_change",
  "procedure_change",
  "timing_change",
  "equipment_change",
  "environment_change",
  "other",
];

const EXCLUSION_PHASES: PlanExecutionExclusionPhase[] = [
  "pre_allocation",
  "post_allocation",
  "post_treatment",
  "post_measurement",
  "post_outcome",
  "unknown",
];

function text(language: D0Language, it: string, en: string): string {
  return language === "it" ? it : en;
}

function nullIfBlank(value: string): string | null {
  const normalized = value.trim();
  return normalized || null;
}

function newId(prefix: string): string {
  if (typeof globalThis.crypto.randomUUID === "function") {
    return `${prefix}-${globalThis.crypto.randomUUID().slice(0, 8)}`;
  }
  return `${prefix}-${Date.now().toString(36)}`;
}

function designFromDraft(
  draft: D0DesignDraft,
  experimentBlockId: string,
  title?: string,
): PlanExecutionDesignSnapshot {
  return {
    experimentBlockId,
    title: title ?? draft.question,
    question: draft.question,
    inferenceTarget: draft.inferenceTarget,
    factorName: draft.factorName,
    levelA: draft.levelA,
    levelB: draft.levelB,
    endpointId: draft.endpointId,
    endpointName: draft.endpointName,
    allocationLevel: draft.allocationLevel,
    independentlyAssigned: draft.independentlyAssigned,
    independenceMechanism: nullIfBlank(draft.independenceMechanism),
    reviewerRole: draft.reviewerRole,
  };
}

function normalizeFactorColumn(factorName: string): string {
  const slug =
    factorName
      .normalize("NFKD")
      .replace(/[^a-zA-Z0-9]+/g, "_")
      .replace(/^_|_$/g, "")
      .toLocaleLowerCase() || "primary";
  return `factor_level_${slug}`;
}

function draftToProspectiveDesign(
  snapshot: PlanExecutionDesignSnapshot,
  draft: D0DesignDraft,
): Record<string, unknown> {
  const shared = draft.sharedEnvironment
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  return {
    experiment_block_id: snapshot.experimentBlockId,
    title: snapshot.title,
    question_text: snapshot.question,
    population_of_inference: snapshot.inferenceTarget,
    factor_name: snapshot.factorName,
    factor_kind: draft.factorKind,
    level_a: snapshot.levelA,
    level_b: snapshot.levelB,
    endpoint_name: snapshot.endpointName,
    endpoint_id: snapshot.endpointId,
    measured_on: draft.measuredOn,
    allocation_level: snapshot.allocationLevel,
    application_level: draft.applicationLevel,
    independently_assigned: snapshot.independentlyAssigned,
    independence_mechanism: snapshot.independenceMechanism,
    shared_environment: shared,
    target_biological_unit: draft.targetBiologicalUnit,
    estimand: {
      effect_measure: draft.effectMeasure,
      target_population_or_unit: draft.estimandTargetPopulation,
      generalization_level: draft.generalizationLevel,
      timepoint: null,
      condition: nullIfBlank(draft.estimandCondition),
    },
    reviewer_role: snapshot.reviewerRole,
  };
}

function rowsToSampleSheet(
  rows: SampleSheetRow[],
  factorColumn: string,
): Record<string, unknown> {
  const headers = [
    "sample_id",
    "source_id",
    "preparation_id",
    "culture_id",
    "plate_id",
    "well_id",
    factorColumn,
    "batch_id",
    "timepoint",
    "endpoint_id",
    "lifecycle_status",
    "exclusion_reason",
    "file_ref",
  ];
  return {
    headers,
    factor_columns: [factorColumn],
    rows: rows.map((row) => ({
      sample_id: row.sampleId,
      source_id: nullIfBlank(row.sourceId),
      preparation_id: nullIfBlank(row.preparationId),
      culture_id: nullIfBlank(row.cultureId),
      plate_id: nullIfBlank(row.plateId),
      well_id: nullIfBlank(row.wellId),
      factor_levels: { [factorColumn]: row.factorLevel },
      batch_id: nullIfBlank(row.batchId),
      timepoint: nullIfBlank(row.timepoint),
      endpoint_id: nullIfBlank(row.endpointId),
      lifecycle_status: row.lifecycleStatus,
      exclusion_reason: nullIfBlank(row.exclusionReason),
      file_ref: nullIfBlank(row.fileRef),
      extra_fields: {
        day_id: nullIfBlank(row.dayId),
        operator_id: nullIfBlank(row.operatorId),
        incubator_id: nullIfBlank(row.incubatorId),
      },
    })),
  };
}

function designsDiffer(
  planned: PlanExecutionDesignSnapshot,
  executed: PlanExecutionDesignSnapshot,
): boolean {
  return JSON.stringify(planned) !== JSON.stringify(executed);
}

function formatApiError(error: unknown, language: D0Language): string {
  if (error instanceof ApiError) {
    const detail = error.detail;
    if (typeof detail === "object" && detail && "validation_errors" in detail) {
      const items = (detail as { validation_errors?: unknown }).validation_errors;
      if (Array.isArray(items)) {
        return items
          .map((item) => {
            if (typeof item !== "object" || !item) return String(item);
            const row = item as Record<string, unknown>;
            const code = typeof row.code === "string" ? row.code : "";
            const message = typeof row.message === "string" ? row.message : String(item);
            const field = typeof row.field === "string" ? row.field : "";
            return [code, field, message].filter(Boolean).join(" · ");
          })
          .join(" | ");
      }
    }
    if (typeof detail === "object" && detail && "message" in detail) {
      return `${String((detail as { message: unknown }).message)} [HTTP ${error.status}]`;
    }
    if (typeof detail === "string") return `${detail} [HTTP ${error.status}]`;
    return `${error.message} [HTTP ${error.status}]`;
  }
  return text(
    language,
    "API locale non raggiungibile per piano vs esecuzione.",
    "Local API unavailable for plan vs execution.",
  );
}

export function PlanExecutionPanel({
  language,
  draft,
  rows,
  experimentBlockId,
  compileResult,
}: {
  language: D0Language;
  draft: D0DesignDraft;
  rows: SampleSheetRow[];
  experimentBlockId: string;
  compileResult: ProspectiveD0CompileResponse;
}) {
  const plannedDesign = useMemo(
    () => designFromDraft(draft, experimentBlockId, draft.question),
    [draft, experimentBlockId],
  );

  const [projectDir, setProjectDir] = useState("./ntruth-project");
  const [executedDesign, setExecutedDesign] = useState<PlanExecutionDesignSnapshot>(() => ({
    ...plannedDesign,
  }));
  const [deviations, setDeviations] = useState<PlanExecutionDeviation[]>([]);
  const [substitutions, setSubstitutions] = useState<PlanExecutionSubstitution[]>([]);
  const [exclusions, setExclusions] = useState<PlanExecutionExclusion[]>([]);
  const [pooling, setPooling] = useState<PlanExecutionPooling[]>([]);
  const [lostSamples, setLostSamples] = useState<PlanExecutionLostSample[]>([]);
  const [treatmentChanges, setTreatmentChanges] = useState<PlanExecutionTreatmentChange[]>([]);
  const [finalSampleSheetNote, setFinalSampleSheetNote] = useState(
    text(
      language,
      "Gli aggiornamenti di lifecycle del final sample sheet devono essere accompagnati da eventi tipizzati (esclusioni, perdite, pooling, sostituzioni, cambi di trattamento).",
      "Final sample sheet lifecycle updates must be accompanied by typed events (exclusions, losses, pooling, substitutions, treatment changes).",
    ),
  );
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitOk, setSubmitOk] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(true);

  const factorColumn = normalizeFactorColumn(draft.factorName);

  const updateExecuted = <K extends keyof PlanExecutionDesignSnapshot>(
    field: K,
    value: PlanExecutionDesignSnapshot[K],
  ) => {
    setExecutedDesign((current) => ({ ...current, [field]: value }));
    setSubmitOk(null);
  };

  const buildPayload = (): PlanExecutionSubmitPayload => {
    const planned = {
      ...plannedDesign,
      experimentBlockId: plannedDesign.experimentBlockId || experimentBlockId,
    };
    const executed = {
      ...executedDesign,
      experimentBlockId: planned.experimentBlockId,
    };
    const sampleIds = rows.map((row) => row.sampleId);
    const effectiveDeviations = [...deviations];
    if (designsDiffer(planned, executed) && effectiveDeviations.length === 0) {
      effectiveDeviations.push({
        deviationId: newId("dev-auto"),
        category: "design_change",
        description: text(
          language,
          "Disegno eseguito diverso dal piano; deviazione registrata dal wizard.",
          "Executed design differs from plan; deviation recorded by the wizard.",
        ),
        affectedSampleIds: sampleIds,
      });
    }
    const sheet = rowsToSampleSheet(rows, factorColumn);
    // Prefer the compiler sample sheet when present and non-empty; fall back to
    // the wizard rows so plan/execution remains reconcilable offline.
    const plannedSheet =
      compileResult.sample_sheet &&
      Array.isArray((compileResult.sample_sheet as { rows?: unknown }).rows) &&
      ((compileResult.sample_sheet as { rows: unknown[] }).rows?.length ?? 0) > 0
        ? (compileResult.sample_sheet as Record<string, unknown>)
        : sheet;
    const projectRoot = projectDir.trim() || "./ntruth-project";
    return {
      project_id: planned.experimentBlockId,
      project_dir: projectRoot,
      actor_role: draft.reviewerRole || "researcher",
      record: {
        contract_version: "1.0.0",
        record_id: `plan-exec-${compileResult.compilation_id}`,
        planned_design: draftToProspectiveDesign(planned, draft),
        planned_sample_sheet: plannedSheet,
        executed_design: draftToProspectiveDesign(executed, {
          ...draft,
          question: executed.question,
          inferenceTarget: executed.inferenceTarget,
          factorName: executed.factorName,
          levelA: executed.levelA,
          levelB: executed.levelB,
          endpointId: executed.endpointId,
          endpointName: executed.endpointName,
          allocationLevel: executed.allocationLevel as D0DesignDraft["allocationLevel"],
          independentlyAssigned:
            executed.independentlyAssigned as D0DesignDraft["independentlyAssigned"],
          independenceMechanism: executed.independenceMechanism ?? "",
          reviewerRole: executed.reviewerRole,
        }),
        deviations: effectiveDeviations.map((item) => ({
          deviation_id: item.deviationId,
          category: item.category,
          description: item.description,
          affected_sample_ids: item.affectedSampleIds,
          evidence_refs: [],
        })),
        substitutions: substitutions.map((item) => ({
          substitution_id: item.substitutionId,
          planned_sample_id: item.plannedSampleId,
          substitute_sample_id: item.substituteSampleId,
          reason: item.reason,
          evidence_refs: [],
        })),
        exclusions: exclusions.map((item) => ({
          exclusion_id: item.exclusionId,
          sample_id: item.sampleId,
          reason: item.reason,
          phase: item.phase,
          prespecified: item.prespecified,
          author_role: item.authorRole,
          evidence_refs: [],
        })),
        pooling: pooling.map((item) => ({
          pooling_id: item.poolingId,
          input_sample_ids: item.inputSampleIds,
          output_sample_id: item.outputSampleId,
          reason: item.reason,
          evidence_refs: [],
        })),
        lost_samples: lostSamples.map((item) => ({
          lost_sample_id: item.lostSampleId,
          sample_id: item.sampleId,
          phase: item.phase,
          reason: item.reason,
          evidence_refs: [],
        })),
        treatment_changes: treatmentChanges.map((item) => ({
          treatment_change_id: item.treatmentChangeId,
          sample_id: item.sampleId,
          factor_column: item.factorColumn || factorColumn,
          planned_level: item.plannedLevel,
          executed_level: item.executedLevel,
          reason: item.reason,
          evidence_refs: [],
        })),
        final_sample_sheet: plannedSheet,
        recorded_by_role: draft.reviewerRole || "researcher",
      },
    };
  };

  const onSubmit = async () => {
    setSubmitting(true);
    setSubmitError(null);
    setSubmitOk(null);
    const payload = buildPayload();
    try {
      const response = await submitPlanExecution(payload);
      setSubmitOk(
        text(
          language,
          `Record ${response.record_id} registrato come ${response.status} (checksum ${response.content_checksum.slice(0, 12)}…).`,
          `Record ${response.record_id} stored as ${response.status} (checksum ${response.content_checksum.slice(0, 12)}…).`,
        ),
      );
    } catch (error) {
      setSubmitError(formatApiError(error, language));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section
      className="d0-result-section d0-plan-execution"
      aria-labelledby="plan-execution-heading"
    >
      <div className="d0-subheading">
        <div>
          <span className="eyebrow">ADR-0009 · plan vs execution</span>
          <h3 id="plan-execution-heading">
            {text(language, "Piano vs esecuzione", "Plan vs execution")}
          </h3>
        </div>
        <button
          type="button"
          className="button secondary compact"
          onClick={() => setExpanded((value) => !value)}
          aria-expanded={expanded}
        >
          <GitCompareArrows size={14} />
          {expanded
            ? text(language, "Comprimi", "Collapse")
            : text(language, "Espandi", "Expand")}
        </button>
      </div>

      <p className="d0-instruction">
        {text(
          language,
          "Il sample sheet finale non ricostruisce da solo il disegno originario. Registra deviazioni tipizzate rispetto al piano compilato.",
          "The final sample sheet alone does not reconstruct the original design. Record typed deviations against the compiled plan.",
        )}
      </p>

      {expanded && (
        <>
          <label className="d0-wide">
            <span className="eyebrow">project_dir</span>
            <input
              aria-label="project_dir"
              value={projectDir}
              onChange={(event) => setProjectDir(event.target.value)}
            />
          </label>

          <div className="d0-plan-exec-columns">
            <div className="d0-plan-exec-card" data-testid="planned-design">
              <div className="d0-subheading">
                <div>
                  <span className="eyebrow">planned</span>
                  <h4>{text(language, "Disegno pianificato", "Planned design")}</h4>
                </div>
                <span className="d0-fixed-badge">{text(language, "Sola lettura", "Read only")}</span>
              </div>
              <dl className="d0-plan-exec-dl">
                <div><dt>experiment_block_id</dt><dd>{plannedDesign.experimentBlockId}</dd></div>
                <div><dt>question</dt><dd>{plannedDesign.question}</dd></div>
                <div><dt>factor</dt><dd>{plannedDesign.factorName}: {plannedDesign.levelA} vs {plannedDesign.levelB}</dd></div>
                <div><dt>endpoint</dt><dd>{plannedDesign.endpointId}</dd></div>
                <div><dt>allocation_level</dt><dd>{plannedDesign.allocationLevel}</dd></div>
                <div><dt>independently_assigned</dt><dd>{plannedDesign.independentlyAssigned}</dd></div>
                <div><dt>samples</dt><dd>{rows.length}</dd></div>
              </dl>
            </div>

            <div className="d0-plan-exec-card" data-testid="executed-design">
              <div className="d0-subheading">
                <div>
                  <span className="eyebrow">executed</span>
                  <h4>{text(language, "Disegno eseguito", "Executed design")}</h4>
                </div>
                <span className="d0-derived-label">
                  {text(language, "Copia del piano · modificabile", "Copy of plan · editable")}
                </span>
              </div>
              <div className="d0-field-grid">
                <label>
                  <span className="eyebrow">title</span>
                  <input
                    aria-label={text(language, "Titolo eseguito", "Executed title")}
                    value={executedDesign.title}
                    onChange={(event) => updateExecuted("title", event.target.value)}
                  />
                </label>
                <label>
                  <span className="eyebrow">question</span>
                  <input
                    aria-label={text(language, "Domanda eseguita", "Executed question")}
                    value={executedDesign.question}
                    onChange={(event) => updateExecuted("question", event.target.value)}
                  />
                </label>
                <label>
                  <span className="eyebrow">factorName</span>
                  <input
                    aria-label={text(language, "Fattore eseguito", "Executed factor")}
                    value={executedDesign.factorName}
                    onChange={(event) => updateExecuted("factorName", event.target.value)}
                  />
                </label>
                <label>
                  <span className="eyebrow">endpointId</span>
                  <input
                    aria-label={text(language, "Endpoint eseguito", "Executed endpoint")}
                    value={executedDesign.endpointId}
                    onChange={(event) => updateExecuted("endpointId", event.target.value)}
                  />
                </label>
              </div>
              <p className="muted">
                {text(
                  language,
                  "Se il disegno eseguito differisce dal piano serve almeno una deviation documentata.",
                  "If the executed design differs from the plan, at least one documented deviation is required.",
                )}
              </p>
            </div>
          </div>

          <EventSection
            title={text(language, "Deviazioni", "Deviations")}
            language={language}
            onAdd={() =>
              setDeviations((current) => [
                ...current,
                {
                  deviationId: newId("dev"),
                  category: "procedure_change",
                  description: "",
                  affectedSampleIds: [],
                },
              ])
            }
          >
            {deviations.map((item, index) => (
              <div key={item.deviationId} className="d0-plan-exec-event">
                <label>
                  <span className="eyebrow">category</span>
                  <select
                    aria-label={`${text(language, "Categoria deviazione", "Deviation category")} ${index + 1}`}
                    value={item.category}
                    onChange={(event) =>
                      setDeviations((current) =>
                        current.map((row, i) =>
                          i === index
                            ? { ...row, category: event.target.value as PlanExecutionDeviationCategory }
                            : row,
                        ),
                      )
                    }
                  >
                    {DEVIATION_CATEGORIES.map((category) => (
                      <option key={category} value={category}>{category}</option>
                    ))}
                  </select>
                </label>
                <label className="d0-wide">
                  <span className="eyebrow">description</span>
                  <input
                    aria-label={`${text(language, "Descrizione deviazione", "Deviation description")} ${index + 1}`}
                    value={item.description}
                    onChange={(event) =>
                      setDeviations((current) =>
                        current.map((row, i) =>
                          i === index ? { ...row, description: event.target.value } : row,
                        ),
                      )
                    }
                  />
                </label>
                <button
                  type="button"
                  className="d0-icon-button"
                  aria-label={`${text(language, "Rimuovi deviazione", "Remove deviation")} ${index + 1}`}
                  onClick={() => setDeviations((current) => current.filter((_, i) => i !== index))}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </EventSection>

          <EventSection
            title={text(language, "Sostituzioni", "Substitutions")}
            language={language}
            onAdd={() =>
              setSubstitutions((current) => [
                ...current,
                {
                  substitutionId: newId("sub"),
                  plannedSampleId: "",
                  substituteSampleId: "",
                  reason: "",
                },
              ])
            }
          >
            {substitutions.map((item, index) => (
              <div key={item.substitutionId} className="d0-plan-exec-event">
                <label>
                  <span className="eyebrow">planned_sample_id</span>
                  <input
                    aria-label={`${text(language, "Sample pianificato", "Planned sample")} ${index + 1}`}
                    value={item.plannedSampleId}
                    onChange={(event) =>
                      setSubstitutions((current) =>
                        current.map((row, i) =>
                          i === index ? { ...row, plannedSampleId: event.target.value } : row,
                        ),
                      )
                    }
                  />
                </label>
                <label>
                  <span className="eyebrow">substitute_sample_id</span>
                  <input
                    aria-label={`${text(language, "Sample sostituto", "Substitute sample")} ${index + 1}`}
                    value={item.substituteSampleId}
                    onChange={(event) =>
                      setSubstitutions((current) =>
                        current.map((row, i) =>
                          i === index ? { ...row, substituteSampleId: event.target.value } : row,
                        ),
                      )
                    }
                  />
                </label>
                <label className="d0-wide">
                  <span className="eyebrow">reason</span>
                  <input
                    aria-label={`${text(language, "Motivo sostituzione", "Substitution reason")} ${index + 1}`}
                    value={item.reason}
                    onChange={(event) =>
                      setSubstitutions((current) =>
                        current.map((row, i) =>
                          i === index ? { ...row, reason: event.target.value } : row,
                        ),
                      )
                    }
                  />
                </label>
                <button
                  type="button"
                  className="d0-icon-button"
                  aria-label={`${text(language, "Rimuovi sostituzione", "Remove substitution")} ${index + 1}`}
                  onClick={() => setSubstitutions((current) => current.filter((_, i) => i !== index))}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </EventSection>

          <EventSection
            title={text(language, "Esclusioni", "Exclusions")}
            language={language}
            onAdd={() =>
              setExclusions((current) => [
                ...current,
                {
                  exclusionId: newId("excl"),
                  sampleId: "",
                  reason: "",
                  phase: "post_treatment",
                  prespecified: "UNKNOWN",
                  authorRole: draft.reviewerRole || "researcher",
                },
              ])
            }
          >
            {exclusions.map((item, index) => (
              <div key={item.exclusionId} className="d0-plan-exec-event">
                <label>
                  <span className="eyebrow">sample_id</span>
                  <input
                    aria-label={`${text(language, "Sample escluso", "Excluded sample")} ${index + 1}`}
                    value={item.sampleId}
                    onChange={(event) =>
                      setExclusions((current) =>
                        current.map((row, i) =>
                          i === index ? { ...row, sampleId: event.target.value } : row,
                        ),
                      )
                    }
                  />
                </label>
                <label>
                  <span className="eyebrow">phase</span>
                  <select
                    aria-label={`${text(language, "Fase esclusione", "Exclusion phase")} ${index + 1}`}
                    value={item.phase}
                    onChange={(event) =>
                      setExclusions((current) =>
                        current.map((row, i) =>
                          i === index
                            ? { ...row, phase: event.target.value as PlanExecutionExclusionPhase }
                            : row,
                        ),
                      )
                    }
                  >
                    {EXCLUSION_PHASES.map((phase) => (
                      <option key={phase} value={phase}>{phase}</option>
                    ))}
                  </select>
                </label>
                <label>
                  <span className="eyebrow">prespecified</span>
                  <select
                    aria-label={`${text(language, "Prespecificata", "Prespecified")} ${index + 1}`}
                    value={item.prespecified}
                    onChange={(event) =>
                      setExclusions((current) =>
                        current.map((row, i) =>
                          i === index
                            ? { ...row, prespecified: event.target.value as PlanExecutionTriState }
                            : row,
                        ),
                      )
                    }
                  >
                    <option value="TRUE">TRUE</option>
                    <option value="FALSE">FALSE</option>
                    <option value="UNKNOWN">UNKNOWN</option>
                  </select>
                </label>
                <label className="d0-wide">
                  <span className="eyebrow">reason</span>
                  <input
                    aria-label={`${text(language, "Motivo esclusione", "Exclusion reason")} ${index + 1}`}
                    value={item.reason}
                    onChange={(event) =>
                      setExclusions((current) =>
                        current.map((row, i) =>
                          i === index ? { ...row, reason: event.target.value } : row,
                        ),
                      )
                    }
                  />
                </label>
                <button
                  type="button"
                  className="d0-icon-button"
                  aria-label={`${text(language, "Rimuovi esclusione", "Remove exclusion")} ${index + 1}`}
                  onClick={() => setExclusions((current) => current.filter((_, i) => i !== index))}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </EventSection>

          <EventSection
            title={text(language, "Pooling", "Pooling")}
            language={language}
            onAdd={() =>
              setPooling((current) => [
                ...current,
                {
                  poolingId: newId("pool"),
                  inputSampleIds: [],
                  outputSampleId: "",
                  reason: "",
                },
              ])
            }
          >
            {pooling.map((item, index) => (
              <div key={item.poolingId} className="d0-plan-exec-event">
                <label>
                  <span className="eyebrow">input_sample_ids</span>
                  <input
                    aria-label={`${text(language, "Input pooling", "Pooling inputs")} ${index + 1}`}
                    placeholder="id1, id2"
                    value={item.inputSampleIds.join(", ")}
                    onChange={(event) =>
                      setPooling((current) =>
                        current.map((row, i) =>
                          i === index
                            ? {
                                ...row,
                                inputSampleIds: event.target.value
                                  .split(",")
                                  .map((part) => part.trim())
                                  .filter(Boolean),
                              }
                            : row,
                        ),
                      )
                    }
                  />
                </label>
                <label>
                  <span className="eyebrow">output_sample_id</span>
                  <input
                    aria-label={`${text(language, "Output pooling", "Pooling output")} ${index + 1}`}
                    value={item.outputSampleId}
                    onChange={(event) =>
                      setPooling((current) =>
                        current.map((row, i) =>
                          i === index ? { ...row, outputSampleId: event.target.value } : row,
                        ),
                      )
                    }
                  />
                </label>
                <label className="d0-wide">
                  <span className="eyebrow">reason</span>
                  <input
                    aria-label={`${text(language, "Motivo pooling", "Pooling reason")} ${index + 1}`}
                    value={item.reason}
                    onChange={(event) =>
                      setPooling((current) =>
                        current.map((row, i) =>
                          i === index ? { ...row, reason: event.target.value } : row,
                        ),
                      )
                    }
                  />
                </label>
                <button
                  type="button"
                  className="d0-icon-button"
                  aria-label={`${text(language, "Rimuovi pooling", "Remove pooling")} ${index + 1}`}
                  onClick={() => setPooling((current) => current.filter((_, i) => i !== index))}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </EventSection>

          <EventSection
            title={text(language, "Campioni persi", "Lost samples")}
            language={language}
            onAdd={() =>
              setLostSamples((current) => [
                ...current,
                {
                  lostSampleId: newId("lost"),
                  sampleId: "",
                  phase: "post_treatment",
                  reason: "",
                },
              ])
            }
          >
            {lostSamples.map((item, index) => (
              <div key={item.lostSampleId} className="d0-plan-exec-event">
                <label>
                  <span className="eyebrow">sample_id</span>
                  <input
                    aria-label={`${text(language, "Sample perso", "Lost sample")} ${index + 1}`}
                    value={item.sampleId}
                    onChange={(event) =>
                      setLostSamples((current) =>
                        current.map((row, i) =>
                          i === index ? { ...row, sampleId: event.target.value } : row,
                        ),
                      )
                    }
                  />
                </label>
                <label>
                  <span className="eyebrow">phase</span>
                  <input
                    aria-label={`${text(language, "Fase perdita", "Loss phase")} ${index + 1}`}
                    value={item.phase}
                    onChange={(event) =>
                      setLostSamples((current) =>
                        current.map((row, i) =>
                          i === index ? { ...row, phase: event.target.value } : row,
                        ),
                      )
                    }
                  />
                </label>
                <label className="d0-wide">
                  <span className="eyebrow">reason</span>
                  <input
                    aria-label={`${text(language, "Motivo perdita", "Loss reason")} ${index + 1}`}
                    value={item.reason}
                    onChange={(event) =>
                      setLostSamples((current) =>
                        current.map((row, i) =>
                          i === index ? { ...row, reason: event.target.value } : row,
                        ),
                      )
                    }
                  />
                </label>
                <button
                  type="button"
                  className="d0-icon-button"
                  aria-label={`${text(language, "Rimuovi perdita", "Remove loss")} ${index + 1}`}
                  onClick={() => setLostSamples((current) => current.filter((_, i) => i !== index))}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </EventSection>

          <EventSection
            title={text(language, "Cambi di trattamento", "Treatment changes")}
            language={language}
            onAdd={() =>
              setTreatmentChanges((current) => [
                ...current,
                {
                  treatmentChangeId: newId("tx"),
                  sampleId: "",
                  factorColumn,
                  plannedLevel: draft.levelA,
                  executedLevel: draft.levelB,
                  reason: "",
                },
              ])
            }
          >
            {treatmentChanges.map((item, index) => (
              <div key={item.treatmentChangeId} className="d0-plan-exec-event">
                <label>
                  <span className="eyebrow">sample_id</span>
                  <input
                    aria-label={`${text(language, "Sample trattamento", "Treatment sample")} ${index + 1}`}
                    value={item.sampleId}
                    onChange={(event) =>
                      setTreatmentChanges((current) =>
                        current.map((row, i) =>
                          i === index ? { ...row, sampleId: event.target.value } : row,
                        ),
                      )
                    }
                  />
                </label>
                <label>
                  <span className="eyebrow">planned_level</span>
                  <input
                    aria-label={`${text(language, "Livello pianificato", "Planned level")} ${index + 1}`}
                    value={item.plannedLevel}
                    onChange={(event) =>
                      setTreatmentChanges((current) =>
                        current.map((row, i) =>
                          i === index ? { ...row, plannedLevel: event.target.value } : row,
                        ),
                      )
                    }
                  />
                </label>
                <label>
                  <span className="eyebrow">executed_level</span>
                  <input
                    aria-label={`${text(language, "Livello eseguito", "Executed level")} ${index + 1}`}
                    value={item.executedLevel}
                    onChange={(event) =>
                      setTreatmentChanges((current) =>
                        current.map((row, i) =>
                          i === index ? { ...row, executedLevel: event.target.value } : row,
                        ),
                      )
                    }
                  />
                </label>
                <label className="d0-wide">
                  <span className="eyebrow">reason</span>
                  <input
                    aria-label={`${text(language, "Motivo cambio trattamento", "Treatment change reason")} ${index + 1}`}
                    value={item.reason}
                    onChange={(event) =>
                      setTreatmentChanges((current) =>
                        current.map((row, i) =>
                          i === index ? { ...row, reason: event.target.value } : row,
                        ),
                      )
                    }
                  />
                </label>
                <button
                  type="button"
                  className="d0-icon-button"
                  aria-label={`${text(language, "Rimuovi cambio trattamento", "Remove treatment change")} ${index + 1}`}
                  onClick={() =>
                    setTreatmentChanges((current) => current.filter((_, i) => i !== index))
                  }
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </EventSection>

          <div className="d0-summary-note">
            <AlertTriangle size={16} />
            <div>
              <strong>
                {text(language, "Final sample sheet", "Final sample sheet")}
              </strong>
              <p>
                {text(
                  language,
                  "Gli aggiornamenti di lifecycle devono essere accompagnati da eventi. Non sovrascrivere il piano con il solo foglio finale.",
                  "Lifecycle updates must be accompanied by events. Do not overwrite the plan with the final sheet alone.",
                )}
              </p>
              <label className="d0-wide">
                <span className="eyebrow">final_sample_sheet_note</span>
                <textarea
                  aria-label={text(language, "Nota final sample sheet", "Final sample sheet note")}
                  rows={2}
                  value={finalSampleSheetNote}
                  onChange={(event) => setFinalSampleSheetNote(event.target.value)}
                />
              </label>
            </div>
          </div>

          {submitError && (
            <div className="d0-validation-list" role="alert">
              <AlertTriangle size={18} />
              <div>
                <strong>
                  {text(
                    language,
                    "Validazione piano vs esecuzione fallita",
                    "Plan vs execution validation failed",
                  )}
                </strong>
                <p>{submitError}</p>
              </div>
            </div>
          )}

          {submitOk && (
            <div className="d0-compile-result" role="status">
              <div>
                <span>{text(language, "Registrazione", "Registration")}</span>
                <strong><Check size={14} /> {submitOk}</strong>
              </div>
            </div>
          )}

          <div className="d0-nav-actions" style={{ marginTop: 0, borderTop: 0, paddingTop: 0 }}>
            <span className="muted">
              {text(
                language,
                "Candidato auditabile · non gold",
                "Auditable candidate · not gold",
              )}
            </span>
            <button
              type="button"
              className="button primary"
              disabled={submitting}
              onClick={() => void onSubmit()}
            >
              <GitCompareArrows size={16} />
              {submitting
                ? text(language, "Registrazione…", "Registering…")
                : text(language, "Registra piano vs esecuzione", "Register plan vs execution")}
            </button>
          </div>
        </>
      )}
    </section>
  );
}

function EventSection({
  title,
  language,
  onAdd,
  children,
}: {
  title: string;
  language: D0Language;
  onAdd: () => void;
  children: ReactNode;
}) {
  return (
    <div className="d0-plan-exec-events">
      <div className="d0-subheading">
        <h4>{title}</h4>
        <button type="button" className="button secondary compact" onClick={onAdd}>
          <Plus size={14} />
          {text(language, "Aggiungi", "Add")}
        </button>
      </div>
      {children}
    </div>
  );
}
