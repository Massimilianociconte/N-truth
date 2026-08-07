import {
  AlertTriangle,
  Check,
  ChevronRight,
  ClipboardList,
  FileText,
  FlaskConical,
  Link2,
  Plus,
  Table2,
  Trash2,
} from "lucide-react";
import { useMemo, useRef, useState } from "react";

import {
  ApiError,
  compileProspectiveD0,
  type ProspectiveD0CompilePayload,
  type ProspectiveD0CompileResponse,
} from "../api";
import { PlanExecutionPanel } from "./PlanExecutionPanel";
import type {
  D0DesignDraft,
  D0Evidence,
  D0Language,
  DeterminabilityState,
  LifecycleCount,
  LifecycleStatus,
  ProofPremise,
  SampleSheetRow,
} from "./types";

const STEPS = ["scope", "profile", "samples", "review"] as const;
type Step = (typeof STEPS)[number];

const INITIAL_DRAFT: D0DesignDraft = {
  question: "Il trattamento modifica la vitalità cellulare a 24 ore?",
  inferenceTarget: "Pozzetti della piastra P01 nella coltura CULT-001",
  factorName: "Trattamento",
  factorKind: "treatment",
  levelA: "Controllo veicolo",
  levelB: "Composto 10 µM",
  endpointName: "Vitalità cellulare a 24 ore",
  endpointId: "EP-VIABILITY-24H",
  measuredOn: "Well",
  allocationLevel: "Well",
  applicationLevel: "Well",
  independentlyAssigned: "UNKNOWN",
  independenceMechanism: "",
  sharedEnvironment: "Piastra P01, incubatore e giornata di acquisizione",
  targetBiologicalUnit: "Well",
  effectMeasure: "Differenza tra medie",
  estimandTargetPopulation: "Pozzetti dichiarati nel blocco D0",
  generalizationLevel: "Condizioni di coltura e trattamento dichiarate",
  estimandCondition: "",
  reviewerRole: "researcher",
};

const INITIAL_ROWS: SampleSheetRow[] = [
  ["D0-CTL-001", "SRC-001", "PREP-001", "CULT-001", "P01", "A01", "Controllo veicolo"],
  ["D0-CTL-002", "SRC-001", "PREP-001", "CULT-001", "P01", "A02", "Controllo veicolo"],
  ["D0-TRT-001", "SRC-001", "PREP-001", "CULT-001", "P01", "A03", "Composto 10 µM"],
  ["D0-TRT-002", "SRC-001", "PREP-001", "CULT-001", "P01", "A04", "Composto 10 µM"],
].map(([sampleId, sourceId, preparationId, cultureId, plateId, wellId, factorLevel]) => ({
  sampleId,
  sourceId,
  preparationId,
  cultureId,
  plateId,
  wellId,
  factorLevel,
  batchId: "BATCH-001",
  dayId: "DAY-001",
  operatorId: "",
  incubatorId: "INC-001",
  timepoint: "24 h",
  endpointId: "EP-VIABILITY-24H",
  lifecycleStatus: "planned",
  exclusionReason: "",
  fileRef: "",
}));

const SAMPLE_SCHEMA = [
  ["sample_id", "string", "required", "univoco"],
  ["source_id", "string/null", "required header", "cella vuota = null; non usare segnaposto"],
  ["preparation_id", "string/null", "required header", "cella vuota = null; non usare segnaposto"],
  ["culture_id", "string/null", "optional", "coltura"],
  ["plate_id", "string/null", "optional", "contenimento fisico; richiesto dal template D0"],
  ["well_id", "string/null", "optional", "coordinate normalizzate; richiesto dal template D0"],
  ["factor_level_*", "categorical", "required per factor", "una colonna per fattore"],
  ["batch_id", "string/null", "optional", "rende il batch osservabile, non prova confondimento"],
  ["day_id", "string/null", "optional", "giornata operativa per il controllo del confondimento"],
  ["operator_id", "string/null", "optional", "operatore pseudonimizzato; non inserire nomi"],
  ["incubator_id", "string/null", "optional", "ambiente condiviso per livello del fattore"],
  ["timepoint", "typed", "optional", "unità temporale esplicita"],
  ["endpoint_id", "string", "optional", "per rappresentazione long form"],
  ["lifecycle_status", "enum", "required", "planned, treated, observed, excluded, analysed"],
  ["exclusion_reason", "string/null", "conditional", "fase, criterio e autore quando excluded"],
  ["file_ref", "string/null", "optional", "hash o URI locale"],
] as const;

const STATE_COPY: Array<{
  state: DeterminabilityState;
  conditionIt: string;
  conditionEn: string;
  outputIt: string;
  outputEn: string;
  singleN: "yes" | "branch" | "no";
}> = [
  {
    state: "DETERMINATE",
    conditionIt: "Fatti decisivi completi e coerenti",
    conditionEn: "Decisive facts are complete and coherent",
    outputIt: "EU, n, classi e proof trace",
    outputEn: "EU, n, classes and proof trace",
    singleN: "yes",
  },
  {
    state: "CONDITIONALLY_DETERMINATE",
    conditionIt: "Scenari biologici enumerabili ma non confermati",
    conditionEn: "Enumerable biological scenarios remain unconfirmed",
    outputIt: "Rami if/then e domanda decisiva",
    outputEn: "If/then branches and a decisive question",
    singleN: "branch",
  },
  {
    state: "MULTIPLE_PLAUSIBLE_GRAPHS",
    conditionIt: "Più grafi compatibili con le evidenze",
    conditionEn: "Multiple graphs fit the evidence",
    outputIt: "Alternative, conseguenze e domanda discriminante",
    outputEn: "Alternatives, consequences and a discriminating question",
    singleN: "no",
  },
  {
    state: "INSUFFICIENT_INFORMATION",
    conditionIt: "Fatti decisivi assenti e non inferibili",
    conditionEn: "Decisive facts are missing and cannot be inferred",
    outputIt: "Null, reporting gap e domanda minima",
    outputEn: "Null, reporting gap and minimum question",
    singleN: "no",
  },
  {
    state: "CONFLICTING_INFORMATION",
    conditionIt: "Fonti primarie incompatibili",
    conditionEn: "Primary sources conflict",
    outputIt: "Conflitto trattenuto e blocco",
    outputEn: "Retained conflict and block",
    singleN: "no",
  },
  {
    state: "INVALID_GRAPH",
    conditionIt: "Invarianti strutturali violate",
    conditionEn: "Structural invariants are violated",
    outputIt: "Errori e correzioni richieste",
    outputEn: "Errors and required corrections",
    singleN: "no",
  },
  {
    state: "OUT_OF_SCOPE",
    conditionIt: "Disegno non coperto dal profilo attivo",
    conditionEn: "Design is not covered by the active profile",
    outputIt: "Solo riepilogo strutturale",
    outputEn: "Structural summary only",
    singleN: "no",
  },
];

const LIFECYCLE_STATUSES: LifecycleStatus[] = [
  "planned",
  "treated",
  "observed",
  "excluded",
  "analysed",
];

const REQUIRED_D0_ROW_FIELDS: Array<keyof SampleSheetRow> = [
  "sampleId",
  "plateId",
  "wellId",
  "factorLevel",
  "endpointId",
];

function text(language: D0Language, it: string, en: string): string {
  return language === "it" ? it : en;
}

function factorId(name: string): string {
  const normalized = name
    .normalize("NFKD")
    .replace(/[^a-zA-Z0-9]+/g, "_")
    .replace(/^_|_$/g, "")
    .toLocaleLowerCase();
  return normalized || "primary";
}

function rowLocator(rowIndex: number, column = "A:P"): string {
  return `SampleSheet_D0!${column}${rowIndex + 2}`;
}

function hasExclusionAudit(reason: string): boolean {
  return /(pre-allocation|post-allocation|post-treatment|post-measurement|post-outcome)/i.test(
    reason,
  ) && /(?:autore|author)\s*:/i.test(reason) && /(?:criterio|criterion)\s*:/i.test(reason);
}

function nullIfBlank(value: string): string | null {
  const normalized = value.trim();
  return normalized || null;
}

function exclusionPhase(reason: string): ProspectiveD0CompilePayload["rows"][number]["exclusionPhase"] {
  const normalized = reason.toLocaleLowerCase().replaceAll("-", "_");
  for (const phase of [
    "pre_allocation",
    "post_allocation",
    "post_treatment",
    "post_measurement",
    "post_outcome",
  ] as const) {
    if (normalized.includes(phase)) return phase;
  }
  return reason.trim() ? "unknown" : null;
}

function exclusionAuthorRole(reason: string): string | null {
  const match = reason.match(/(?:autore|author)\s*:\s*([^|]+)/i);
  return match ? nullIfBlank(match[1]) : null;
}

function createExperimentBlockId(): string {
  if (typeof globalThis.crypto.randomUUID === "function") {
    return `EB-D0-${globalThis.crypto.randomUUID()}`;
  }
  const words = new Uint32Array(4);
  globalThis.crypto.getRandomValues(words);
  return `EB-D0-${Array.from(words, (word) => word.toString(16).padStart(8, "0")).join("")}`;
}

function canonicalEvidenceLocator(evidence: { file_id: string; page?: number | null; section_title?: string | null; cell?: { sheet?: string | null; table_id: string; row: number; column: string } | null }): string {
  if (evidence.cell) {
    const sheet = evidence.cell.sheet ? `${evidence.cell.sheet}!` : "";
    return `${evidence.file_id} · ${sheet}${evidence.cell.column}${evidence.cell.row}`;
  }
  if (evidence.page != null) return `${evidence.file_id} · page ${evidence.page}`;
  if (evidence.section_title) return `${evidence.file_id} · ${evidence.section_title}`;
  return evidence.file_id;
}

function allocationKey(row: SampleSheetRow, level: D0DesignDraft["allocationLevel"]): string {
  if (level === "Plate") return row.plateId.trim();
  if (level === "Well") return `${row.plateId.trim()}::${row.wellId.trim()}`;
  return "";
}

function countUniqueAllocationUnits(
  rows: SampleSheetRow[],
  group: string,
  allocationLevel: D0DesignDraft["allocationLevel"],
  status?: LifecycleStatus,
): number {
  return new Set(
    rows
      .filter(
        (row) => row.factorLevel === group && (!status || row.lifecycleStatus === status),
      )
      .map((row) => allocationKey(row, allocationLevel))
      .filter(Boolean),
  ).size;
}

function lifecycleCounts(
  rows: SampleSheetRow[],
  draft: D0DesignDraft,
): LifecycleCount[] {
  const groups = [draft.levelA, draft.levelB];
  const phases: LifecycleCount["phase"][] = [
    "planned_n",
    "allocated_n",
    "treated_n",
    "observed_n",
    "excluded_n",
    "analysed_n",
  ];

  return groups.flatMap((group) =>
    phases.map((phase) => {
      const isPlanned = phase === "planned_n";
      // Appendix O registra uno stato corrente per riga, non una storia degli
      // eventi. Da quel solo campo non e lecito ricostruire conteggi cumulativi
      // treated/observed/excluded/analysed. Il backend canonico potra emetterli
      // soltanto quando esiste un lifecycle/event ledger auditabile.
      const reportable = isPlanned && draft.allocationLevel !== "UNKNOWN";
      return {
        phase,
        group,
        value: reportable
          ? isPlanned
            ? countUniqueAllocationUnits(rows, group, draft.allocationLevel)
            : null
          : null,
        quantifier: reportable ? "EXACT" : "NOT_REPORTED",
        unitType: draft.allocationLevel,
        factorId: factorId(draft.factorName),
        contrastId: `${factorId(draft.factorName)}:${draft.levelA}_vs_${draft.levelB}`,
        endpointId: draft.endpointId,
        timepoint: rows[0]?.timepoint || "UNKNOWN",
        evidenceId: "d0-evidence-samplesheet",
        sourceCell: "SampleSheet_D0!A2:P5",
        source: phase === "allocated_n" ? "derived" : "SampleSheet",
      };
    }),
  );
}

export function ProspectiveD0Workspace({
  active,
  language,
}: {
  active: boolean;
  language: D0Language;
}) {
  const [step, setStep] = useState<Step>("scope");
  const [draft, setDraft] = useState<D0DesignDraft>(INITIAL_DRAFT);
  const [rows, setRows] = useState<SampleSheetRow[]>(INITIAL_ROWS);
  const [experimentBlockId] = useState(createExperimentBlockId);
  const [compileResult, setCompileResult] = useState<ProspectiveD0CompileResponse | null>(null);
  const [compileError, setCompileError] = useState<string | null>(null);
  const [compiling, setCompiling] = useState(false);
  const compileGeneration = useRef(0);
  const [selectedEvidenceId, setSelectedEvidenceId] = useState("d0-evidence-factor");
  const [selectedCanonicalEvidenceId, setSelectedCanonicalEvidenceId] = useState<string | null>(null);

  const currentStep = STEPS.indexOf(step);
  const dynamicFactorColumn = `factor_level_${factorId(draft.factorName)}`;

  const missingFacts = useMemo(() => {
    const missing: string[] = [];
    const requiredDraft: Array<[keyof D0DesignDraft, string]> = [
      ["question", "question"],
      ["inferenceTarget", "inference_target"],
      ["factorName", "factor"],
      ["levelA", "factor_level_A"],
      ["levelB", "factor_level_B"],
      ["endpointName", "endpoint"],
      ["endpointId", "endpoint_id"],
      ["effectMeasure", "estimand.effect_measure"],
      ["estimandTargetPopulation", "estimand.target_population_or_unit"],
      ["generalizationLevel", "estimand.generalization_level"],
      ["reviewerRole", "reviewer_role"],
    ];
    for (const [field, label] of requiredDraft) {
      if (!String(draft[field]).trim()) missing.push(label);
    }
    if (draft.independentlyAssigned === "TRUE" && !draft.independenceMechanism.trim()) {
      missing.push("independence_mechanism");
    }
    rows.forEach((row, index) => {
      REQUIRED_D0_ROW_FIELDS.forEach((field) => {
        if (!String(row[field]).trim()) missing.push(`row_${index + 1}.${field}`);
      });
    });
    return missing;
  }, [draft, rows]);

  const invariantErrors = useMemo(() => {
    const errors: string[] = [];
    if (draft.levelA.trim() && draft.levelA.trim() === draft.levelB.trim()) {
      errors.push(text(language, "I due livelli devono essere distinti.", "The two levels must differ."));
    }
    const sampleIds = rows.map((row) => row.sampleId.trim()).filter(Boolean);
    if (new Set(sampleIds).size !== sampleIds.length) {
      errors.push(text(language, "sample_id duplicati.", "Duplicate sample_id values."));
    }
    const wells = rows
      .map((row) => `${row.plateId.trim()}::${row.wellId.trim()}`)
      .filter((value) => value !== "::");
    if (new Set(wells).size !== wells.length) {
      errors.push(text(language, "Coordinate plate_id/well_id duplicate.", "Duplicate plate_id/well_id coordinates."));
    }
    if (draft.allocationLevel !== "UNKNOWN") {
      const levelsByAllocationUnit = new Map<string, Set<string>>();
      rows.forEach((row) => {
        const key = allocationKey(row, draft.allocationLevel);
        if (!key) return;
        const levels = levelsByAllocationUnit.get(key) ?? new Set<string>();
        levels.add(row.factorLevel);
        levelsByAllocationUnit.set(key, levels);
      });
      for (const [key, levels] of levelsByAllocationUnit) {
        if (levels.size > 1) {
          errors.push(
            text(
              language,
              `L'unità di allocazione ${key} è associata a più livelli del fattore.`,
              `Allocation unit ${key} is associated with multiple factor levels.`,
            ),
          );
        }
      }
      for (const level of [draft.levelA, draft.levelB]) {
        if (countUniqueAllocationUnits(rows, level, draft.allocationLevel) === 0) {
          errors.push(
            text(
              language,
              `Il livello '${level}' non contiene alcuna unità di allocazione.`,
              `Level '${level}' has no allocation unit.`,
            ),
          );
        }
      }
    }
    rows.forEach((row, index) => {
      if (![draft.levelA, draft.levelB].includes(row.factorLevel)) {
        errors.push(
          text(
            language,
            `Riga ${index + 1}: livello del fattore fuori dal contrasto primario.`,
            `Row ${index + 1}: factor level is outside the primary contrast.`,
          ),
        );
      }
      if (row.endpointId && row.endpointId !== draft.endpointId) {
        errors.push(
          text(
            language,
            `Riga ${index + 1}: endpoint_id non coincide con l'endpoint primario.`,
            `Row ${index + 1}: endpoint_id does not match the primary endpoint.`,
          ),
        );
      }
      if (row.lifecycleStatus === "excluded" && !hasExclusionAudit(row.exclusionReason)) {
        errors.push(
          text(
            language,
            `Riga ${index + 1}: l'esclusione richiede fase e autore.`,
            `Row ${index + 1}: exclusion requires a stage and author.`,
          ),
        );
      }
    });
    return errors;
  }, [draft.allocationLevel, draft.endpointId, draft.levelA, draft.levelB, language, rows]);

  const capabilityErrors = useMemo(() => {
    const errors: string[] = [];
    const timepoints = [...new Set(rows.map((row) => row.timepoint.trim()).filter(Boolean))];
    if (timepoints.length > 1) {
      errors.push(
        text(
          language,
          "Il profilo D0 accetta un solo timepoint esplicito.",
          "The D0 profile accepts one explicit timepoint only.",
        ),
      );
    }
    const typedTimepoint = /^\d+(?:[.,]\d+)?\s*(?:ms|s|sec|min|h|hr|d|day|days)$/i;
    for (const timepoint of timepoints) {
      if (!typedTimepoint.test(timepoint)) {
        errors.push(
          text(
            language,
            `Timepoint '${timepoint}' privo di unità temporale supportata.`,
            `Timepoint '${timepoint}' lacks a supported time unit.`,
          ),
        );
      }
    }
    return errors;
  }, [language, rows]);

  const previewDeterminability: DeterminabilityState = useMemo(() => {
    if (invariantErrors.length) return "INVALID_GRAPH";
    if (capabilityErrors.length) return "OUT_OF_SCOPE";
    if (missingFacts.length || draft.allocationLevel === "UNKNOWN") {
      return "INSUFFICIENT_INFORMATION";
    }
    if (draft.independentlyAssigned === "UNKNOWN") return "CONDITIONALLY_DETERMINATE";
    if (draft.independentlyAssigned === "FALSE") return "INSUFFICIENT_INFORMATION";
    return "DETERMINATE";
  }, [capabilityErrors.length, draft.allocationLevel, draft.independentlyAssigned, invariantErrors.length, missingFacts.length]);

  const determinability = compileResult?.determinability ?? previewDeterminability;
  const selectedCanonicalEvidence = compileResult
    ? compileResult.block.evidence.find((item) => item.id === selectedCanonicalEvidenceId) ??
      compileResult.block.evidence[0]
    : undefined;

  const evidence = useMemo<D0Evidence[]>(
    () => [
      {
        id: "d0-evidence-question",
        title: text(language, "Domanda e target", "Question and target"),
        locator: "D0-WIZARD · scope.question",
        text: `${draft.question} Target: ${draft.inferenceTarget}.`,
        evidenceType: "USER_CONFIRMATION",
        origin: text(language, "Input del ricercatore", "Researcher input"),
      },
      {
        id: "d0-evidence-factor",
        title: text(language, "Fattore e contrasto", "Factor and contrast"),
        locator: `D0-WIZARD · factor.${factorId(draft.factorName)}`,
        text: `${draft.factorName}: ${draft.levelA} versus ${draft.levelB}. Allocation level: ${draft.allocationLevel}.`,
        evidenceType: "USER_CONFIRMATION",
        origin: text(language, "Input del ricercatore", "Researcher input"),
      },
      {
        id: "d0-evidence-independence",
        title: text(language, "Meccanismo di indipendenza", "Independence mechanism"),
        locator: "D0-WIZARD · core_profile.independence_mechanism",
        text: draft.independenceMechanism || text(language, "Non riportato.", "Not reported."),
        evidenceType: "USER_CONFIRMATION",
        origin: text(language, "Conferma esplicita richiesta", "Explicit confirmation required"),
      },
      {
        id: "d0-evidence-samplesheet",
        title: "SampleSheet D0",
        locator: "SampleSheet_D0!A2:P5",
        text: text(
          language,
          `${rows.length} righe prospettiche; ID, provenienza, pozzetto, livello del fattore, endpoint e lifecycle sono collegati per cella.`,
          `${rows.length} prospective rows; IDs, provenance, well, factor level, endpoint and lifecycle are linked by cell.`,
        ),
        evidenceType: "SAMPLE_METADATA",
        origin: text(language, "Tabella locale generata dal wizard", "Local table generated by the wizard"),
      },
      {
        id: "d0-evidence-endpoint",
        title: text(language, "Endpoint primario", "Primary endpoint"),
        locator: "D0-WIZARD · endpoint.primary",
        text: `${draft.endpointId}: ${draft.endpointName}; measured_on=${draft.measuredOn}.`,
        evidenceType: "USER_CONFIRMATION",
        origin: text(language, "Input del ricercatore", "Researcher input"),
      },
    ],
    [draft, language, rows.length],
  );

  const proofPremises = useMemo<ProofPremise[]>(
    () => [
      {
        id: "premise-allocation",
        expression: "not assignment_unknown()",
        label: text(language, "Livello di allocazione esplicito", "Explicit allocation level"),
        status: draft.allocationLevel === "UNKNOWN" ? "unresolved" : "satisfied",
        evidenceId: "d0-evidence-factor",
      },
      {
        id: "premise-independent",
        expression: "independently_assigned()",
        label: text(language, "Assegnazione indipendente confermata", "Independent assignment confirmed"),
        status:
          draft.independentlyAssigned === "TRUE"
            ? "satisfied"
            : draft.independentlyAssigned === "FALSE"
              ? "failed"
              : "unresolved",
        evidenceId: "d0-evidence-independence",
      },
      {
        id: "premise-mechanism",
        expression: "independence_mechanism != null",
        label: text(language, "Meccanismo operativo registrato", "Operational mechanism recorded"),
        status: draft.independenceMechanism.trim() ? "satisfied" : "unresolved",
        evidenceId: "d0-evidence-independence",
      },
      {
        id: "premise-sheet",
        expression: "samplesheet_invariants_valid()",
        label: text(language, "SampleSheet completa e coerente", "Complete and coherent SampleSheet"),
        status: invariantErrors.length ? "failed" : missingFacts.length ? "unresolved" : "satisfied",
        evidenceId: "d0-evidence-samplesheet",
      },
    ],
    [draft, invariantErrors.length, language, missingFacts.length],
  );

  const selectedEvidence =
    evidence.find((item) => item.id === selectedEvidenceId) ?? evidence[0];
  const counts = useMemo(() => lifecycleCounts(rows, draft), [draft, rows]);

  const resetCompilation = () => {
    compileGeneration.current += 1;
    setCompileResult(null);
    setCompileError(null);
    setSelectedCanonicalEvidenceId(null);
    setCompiling(false);
  };

  const updateDraft = <Field extends keyof D0DesignDraft>(
    field: Field,
    value: D0DesignDraft[Field],
  ) => {
    if (field === "levelA" || field === "levelB") {
      const previous = draft[field];
      setRows((current) =>
        current.map((row) =>
          row.factorLevel === previous ? { ...row, factorLevel: String(value) } : row,
        ),
      );
    }
    if (field === "endpointId") {
      setRows((current) => current.map((row) => ({ ...row, endpointId: String(value) })));
    }
    setDraft((current) => ({ ...current, [field]: value }));
    resetCompilation();
  };

  const updateRow = <Field extends keyof SampleSheetRow>(
    index: number,
    field: Field,
    value: SampleSheetRow[Field],
  ) => {
    setRows((current) =>
      current.map((row, rowIndex) => (rowIndex === index ? { ...row, [field]: value } : row)),
    );
    resetCompilation();
  };

  const addRow = () => {
    const number = rows.length + 1;
    const level = number % 2 ? draft.levelA : draft.levelB;
    setRows((current) => [
      ...current,
      {
        sampleId: `D0-SAMPLE-${String(number).padStart(3, "0")}`,
        sourceId: "",
        preparationId: "",
        cultureId: "",
        plateId: "P01",
        wellId: `A${String(number).padStart(2, "0")}`,
        factorLevel: level,
        batchId: "",
        dayId: "",
        operatorId: "",
        incubatorId: "",
        timepoint: "24 h",
        endpointId: draft.endpointId,
        lifecycleStatus: "planned",
        exclusionReason: "",
        fileRef: "",
      },
    ]);
    resetCompilation();
  };

  const removeRow = (index: number) => {
    setRows((current) => current.filter((_, rowIndex) => rowIndex !== index));
    resetCompilation();
  };

  const compileCanonical = async () => {
    const generation = compileGeneration.current + 1;
    compileGeneration.current = generation;
    setCompiling(true);
    setCompileError(null);
    setCompileResult(null);
    const timepoints = [...new Set(rows.map((row) => row.timepoint.trim()).filter(Boolean))];
    const payload: ProspectiveD0CompilePayload = {
      draft: {
        experimentBlockId,
        title: draft.question,
        question: draft.question,
        inferenceTarget: draft.inferenceTarget,
        factorName: draft.factorName,
        factorKind: draft.factorKind,
        levelA: draft.levelA,
        levelB: draft.levelB,
        endpointName: draft.endpointName,
        endpointId: draft.endpointId,
        measuredOn: draft.measuredOn,
        allocationLevel: draft.allocationLevel,
        applicationLevel: draft.applicationLevel,
        independentlyAssigned: draft.independentlyAssigned,
        independenceMechanism: nullIfBlank(draft.independenceMechanism),
        sharedEnvironment: nullIfBlank(draft.sharedEnvironment)
          ? [draft.sharedEnvironment.trim()]
          : [],
        targetBiologicalUnit: draft.targetBiologicalUnit,
        estimand: {
          effectMeasure: draft.effectMeasure,
          targetPopulationOrUnit: draft.estimandTargetPopulation,
          generalizationLevel: draft.generalizationLevel,
          timepoint: timepoints.length === 1 ? timepoints[0] : null,
          condition: nullIfBlank(draft.estimandCondition),
        },
        reviewerRole: draft.reviewerRole,
      },
      rows: rows.map((row) => {
        const excluded = row.lifecycleStatus === "excluded";
        return {
          sampleId: row.sampleId,
          sourceId: nullIfBlank(row.sourceId),
          preparationId: nullIfBlank(row.preparationId),
          cultureId: nullIfBlank(row.cultureId),
          plateId: nullIfBlank(row.plateId),
          wellId: nullIfBlank(row.wellId),
          factorLevel: row.factorLevel,
          batchId: nullIfBlank(row.batchId),
          extraFields: {
            day_id: nullIfBlank(row.dayId),
            operator_id: nullIfBlank(row.operatorId),
            incubator_id: nullIfBlank(row.incubatorId),
          },
          timepoint: nullIfBlank(row.timepoint),
          endpointId: nullIfBlank(row.endpointId),
          lifecycleStatus: row.lifecycleStatus,
          exclusionReason: excluded ? nullIfBlank(row.exclusionReason) : null,
          exclusionPhase: excluded ? exclusionPhase(row.exclusionReason) : null,
          exclusionPrespecified: "UNKNOWN" as const,
          exclusionAuthorRole: excluded ? exclusionAuthorRole(row.exclusionReason) : null,
          exclusionImpact: null,
          fileRef: nullIfBlank(row.fileRef),
        };
      }),
      language,
      rulesetId: "ntruth-core",
      rulesetVersion: "0.2.0",
    };
    try {
      const result = await compileProspectiveD0(payload);
      if (compileGeneration.current === generation) {
        setCompileResult(result);
        setSelectedCanonicalEvidenceId(result.block.evidence[0]?.id ?? null);
      }
    } catch (error) {
      if (compileGeneration.current !== generation) return;
      if (error instanceof ApiError) {
        const detail = error.detail;
        const issueText =
          typeof detail === "object" && detail && "issues" in detail && Array.isArray(detail.issues)
            ? detail.issues
                .map((issue) => {
                  if (typeof issue !== "object" || !issue) return String(issue);
                  const item = issue as Record<string, unknown>;
                  const location = [
                    typeof item.row === "number" ? `row ${item.row}` : "",
                    typeof item.field === "string" ? item.field : "",
                  ].filter(Boolean).join(" · ");
                  return `${String(item.code ?? "issue")}: ${String(item.message ?? "")}${location ? ` · ${location}` : ""}`;
                })
                .join(" | ")
            : "";
        const detailCode =
          typeof detail === "object" && detail && "code" in detail
            ? String(detail.code)
            : "";
        setCompileError(
          [detailCode || error.message, issueText, `[HTTP ${error.status}]`]
            .filter(Boolean)
            .join(" · "),
        );
      } else {
        setCompileError(
          text(
            language,
            "API locale non raggiungibile: l'anteprima client resta non autorevole.",
            "Local API unavailable: the client preview remains non-authoritative.",
          ),
        );
      }
    } finally {
      if (compileGeneration.current === generation) setCompiling(false);
    }
  };

  const goNext = () => setStep(STEPS[Math.min(currentStep + 1, STEPS.length - 1)]);
  const goBack = () => setStep(STEPS[Math.max(currentStep - 1, 0)]);

  const nCopy = (value: "yes" | "branch" | "no") => {
    if (value === "yes") return text(language, "Sì", "Yes");
    if (value === "branch") return text(language, "Solo per ramo", "Per branch only");
    return text(language, "No", "No");
  };

  return (
    <section
      id="d0-panel"
      className={`panel d0-workspace ${active ? "focused-panel" : ""}`}
      aria-labelledby="d0-heading"
    >
      <div className="d0-heading">
        <div>
          <span className="eyebrow">Core Profile v0.1-D · prospective-first</span>
          <h1 id="d0-heading">
            {text(language, "Progettazione prospettica D0", "Prospective D0 design")}
          </h1>
          <p>
            {text(
              language,
              "Template vincolato per colture cellulari su piastra. La determinabilità è derivata: non è una scelta dell'utente.",
              "Constrained template for plate-based cell cultures. Determinability is derived, never user-selected.",
            )}
          </p>
        </div>
        <div className="d0-scope-chips" aria-label={text(language, "Perimetro D0", "D0 scope")}>
          <span><FlaskConical size={14} /> {text(language, "Colture + piastre", "Cultures + plates")}</span>
          <span>1 {text(language, "fattore", "factor")}</span>
          <span>2 {text(language, "livelli", "levels")}</span>
          <span>1 endpoint</span>
        </div>
      </div>

      <nav className="d0-stepper" aria-label={text(language, "Passi del wizard D0", "D0 wizard steps")}>
        {STEPS.map((item, index) => {
          const labels = [
            text(language, "Domanda", "Question"),
            "Core Profile",
            "SampleSheet",
            text(language, "Verifica", "Review"),
          ];
          return (
            <button
              key={item}
              className={step === item ? "active" : index < currentStep ? "complete" : ""}
              onClick={() => setStep(item)}
              aria-current={step === item ? "step" : undefined}
            >
              <span>{index < currentStep ? <Check size={14} /> : index + 1}</span>
              {labels[index]}
            </button>
          );
        })}
      </nav>

      <div className="d0-layout">
        <div className="d0-step-content">
          {step === "scope" && (
            <div className="d0-form-section">
              <div className="d0-section-title">
                <div><span className="eyebrow">01 · scope</span><h2>{text(language, "Domanda e target", "Question and target")}</h2></div>
                <span className="d0-fixed-badge">D0 fixed</span>
              </div>
              <div className="d0-domain-callout">
                <ClipboardList size={19} />
                <div><strong>{text(language, "Template di dominio", "Domain template")}</strong><span>{text(language, "Colture cellulari · well plate · contrasto monofattoriale", "Cell cultures · well plate · one-factor contrast")}</span></div>
              </div>
              <div className="d0-field-grid">
                <label className="field-label d0-wide">
                  {text(language, "Domanda primaria", "Primary question")} <span aria-hidden="true">*</span>
                  <textarea value={draft.question} rows={2} onChange={(event) => updateDraft("question", event.target.value)} />
                </label>
                <label className="field-label d0-wide">
                  {text(language, "Target inferenziale", "Inference target")} <span aria-hidden="true">*</span>
                  <input value={draft.inferenceTarget} onChange={(event) => updateDraft("inferenceTarget", event.target.value)} />
                  <small>{text(language, "Dichiarare a quale popolazione o insieme di unità si estende il contrasto.", "State the population or unit set to which the contrast extends.")}</small>
                </label>
              </div>
            </div>
          )}

          {step === "profile" && (
            <div className="d0-form-section">
              <div className="d0-section-title">
                <div><span className="eyebrow">02 · Core Profile</span><h2>{text(language, "Fattore, allocazione ed endpoint", "Factor, allocation and endpoint")}</h2></div>
                <span className="d0-fixed-badge">1 × 2 × 1</span>
              </div>
              <div className="d0-field-grid">
                <label className="field-label">
                  {text(language, "Fattore primario", "Primary factor")} *
                  <input aria-label={text(language, "Fattore primario", "Primary factor")} value={draft.factorName} onChange={(event) => updateDraft("factorName", event.target.value)} />
                </label>
                <label className="field-label">
                  factor_kind *
                  <select aria-label="factor_kind" value={draft.factorKind} onChange={(event) => updateDraft("factorKind", event.target.value as D0DesignDraft["factorKind"])}>
                    <option value="treatment">treatment</option><option value="genotype">genotype</option><option value="dose">dose</option><option value="time">time</option><option value="diet">diet</option><option value="other">other</option><option value="unknown">unknown</option>
                  </select>
                </label>
                <div className="d0-readonly-field"><span>{text(language, "Numero fattori", "Factor count")}</span><strong>1</strong><small>{text(language, "Bloccato dal profilo D0", "Locked by the D0 profile")}</small></div>
                <label className="field-label">
                  {text(language, "Livello A", "Level A")} *
                  <input value={draft.levelA} onChange={(event) => updateDraft("levelA", event.target.value)} />
                </label>
                <label className="field-label">
                  {text(language, "Livello B", "Level B")} *
                  <input value={draft.levelB} onChange={(event) => updateDraft("levelB", event.target.value)} />
                </label>
                <label className="field-label">
                  allocation_level *
                  <select aria-label="allocation_level" value={draft.allocationLevel} onChange={(event) => updateDraft("allocationLevel", event.target.value as D0DesignDraft["allocationLevel"])}>
                    <option value="Well">Well</option><option value="Plate">Plate</option><option value="UNKNOWN">UNKNOWN</option>
                  </select>
                </label>
                <label className="field-label">
                  application_level
                  <select aria-label="application_level" value={draft.applicationLevel} onChange={(event) => updateDraft("applicationLevel", event.target.value as D0DesignDraft["applicationLevel"])}>
                    <option value="Well">Well</option><option value="Plate">Plate</option><option value="UNKNOWN">UNKNOWN</option>
                  </select>
                </label>
                <label className="field-label">
                  independently_assigned *
                  <select aria-label={text(language, "Indipendenza dell'assegnazione", "Assignment independence")} value={draft.independentlyAssigned} onChange={(event) => updateDraft("independentlyAssigned", event.target.value as D0DesignDraft["independentlyAssigned"])}>
                    <option value="TRUE">TRUE</option><option value="FALSE">FALSE</option><option value="UNKNOWN">UNKNOWN</option>
                  </select>
                  <small>{text(language, "Tri-state obbligatorio; gli ID non provano indipendenza.", "Required tri-state; IDs do not prove independence.")}</small>
                </label>
                <label className="field-label">
                  independence_mechanism {draft.independentlyAssigned === "TRUE" ? "*" : ""}
                  <textarea value={draft.independenceMechanism} rows={2} onChange={(event) => updateDraft("independenceMechanism", event.target.value)} />
                </label>
                <label className="field-label d0-wide">
                  shared_environment
                  <input value={draft.sharedEnvironment} onChange={(event) => updateDraft("sharedEnvironment", event.target.value)} />
                </label>
                <label className="field-label">
                  {text(language, "Endpoint primario", "Primary endpoint")} *
                  <input value={draft.endpointName} onChange={(event) => updateDraft("endpointName", event.target.value)} />
                </label>
                <label className="field-label">
                  endpoint_id *
                  <input value={draft.endpointId} onChange={(event) => updateDraft("endpointId", event.target.value)} />
                </label>
                <div className="d0-readonly-field"><span>measured_on</span><strong>Well</strong><small>{text(language, "Un solo endpoint primario nel D0", "One primary endpoint in D0")}</small></div>
                <div className="d0-readonly-field"><span>{text(language, "Contrasto primario", "Primary contrast")}</span><strong>{draft.levelA || "A"} vs {draft.levelB || "B"}</strong><small>{text(language, "Derivato dai due livelli", "Derived from the two levels")}</small></div>
                <label className="field-label">
                  target_biological_unit *
                  <select aria-label="target_biological_unit" value={draft.targetBiologicalUnit} onChange={(event) => updateDraft("targetBiologicalUnit", event.target.value as D0DesignDraft["targetBiologicalUnit"])}>
                    <option value="Well">Well</option><option value="Plate">Plate</option>
                  </select>
                </label>
                <label className="field-label">
                  effect_measure *
                  <input aria-label="effect_measure" value={draft.effectMeasure} onChange={(event) => updateDraft("effectMeasure", event.target.value)} />
                </label>
                <label className="field-label d0-wide">
                  target_population_or_unit *
                  <input aria-label="target_population_or_unit" value={draft.estimandTargetPopulation} onChange={(event) => updateDraft("estimandTargetPopulation", event.target.value)} />
                </label>
                <label className="field-label">
                  generalization_level *
                  <input aria-label="generalization_level" value={draft.generalizationLevel} onChange={(event) => updateDraft("generalizationLevel", event.target.value)} />
                </label>
                <label className="field-label">
                  estimand_condition
                  <input aria-label="estimand_condition" value={draft.estimandCondition} onChange={(event) => updateDraft("estimandCondition", event.target.value)} />
                </label>
                <label className="field-label">
                  reviewer_role *
                  <input aria-label="reviewer_role" value={draft.reviewerRole} onChange={(event) => updateDraft("reviewerRole", event.target.value)} />
                </label>
              </div>
            </div>
          )}

          {step === "samples" && (
            <div className="d0-form-section">
              <div className="d0-section-title">
                <div><span className="eyebrow">03 · Appendix O</span><h2>SampleSheetSpec D0</h2></div>
                <button className="button secondary compact" onClick={addRow}><Plus size={15} /> {text(language, "Aggiungi riga", "Add row")}</button>
              </div>
              <p className="d0-instruction">
                {text(language, "Gli header source_id e preparation_id sono obbligatori, ma una cella può restare vuota per rappresentare null: non usare NULL, unknown o altri segnaposto. Compila day_id, operator_id e incubator_id quando possono rivelare confondimento; usa ID pseudonimi, mai nomi. Gli ID non dimostrano indipendenza.", "The source_id and preparation_id headers are required, but a cell may be left blank to represent null: do not use NULL, unknown, or other placeholders. Fill day_id, operator_id and incubator_id when they may reveal confounding; use pseudonymous IDs, never names. IDs do not establish independence.")}
              </p>
              <div className="d0-table-wrap">
                <table className="d0-sample-table" aria-label="SampleSheet D0">
                  <thead><tr>
                    <th>sample_id *</th><th>source_id *</th><th>preparation_id *</th><th>culture_id</th><th>plate_id <sup>D0</sup></th><th>well_id <sup>D0</sup></th><th>{dynamicFactorColumn} *</th><th>batch_id</th><th>day_id</th><th>operator_id</th><th>incubator_id</th><th>timepoint</th><th>endpoint_id</th><th>lifecycle_status *</th><th>exclusion_reason</th><th>file_ref</th><th><span className="sr-only">{text(language, "Azioni", "Actions")}</span></th>
                  </tr></thead>
                  <tbody>
                    {rows.map((row, index) => (
                      <tr key={`${index}-${row.sampleId}`}>
                        <td><input aria-label={`sample_id ${index + 1}`} value={row.sampleId} onChange={(event) => updateRow(index, "sampleId", event.target.value)} /></td>
                        <td><input aria-label={`source_id ${index + 1}`} value={row.sourceId} onChange={(event) => updateRow(index, "sourceId", event.target.value)} /></td>
                        <td><input aria-label={`preparation_id ${index + 1}`} value={row.preparationId} onChange={(event) => updateRow(index, "preparationId", event.target.value)} /></td>
                        <td><input aria-label={`culture_id ${index + 1}`} value={row.cultureId} onChange={(event) => updateRow(index, "cultureId", event.target.value)} /></td>
                        <td><input aria-label={`plate_id ${index + 1}`} value={row.plateId} onChange={(event) => updateRow(index, "plateId", event.target.value)} /></td>
                        <td><input aria-label={`well_id ${index + 1}`} value={row.wellId} onChange={(event) => updateRow(index, "wellId", event.target.value)} /></td>
                        <td><select aria-label={`${dynamicFactorColumn} ${index + 1}`} value={row.factorLevel} onChange={(event) => updateRow(index, "factorLevel", event.target.value)}><option value={draft.levelA}>{draft.levelA}</option><option value={draft.levelB}>{draft.levelB}</option></select></td>
                        <td><input aria-label={`batch_id ${index + 1}`} value={row.batchId} onChange={(event) => updateRow(index, "batchId", event.target.value)} /></td>
                        <td><input aria-label={`day_id ${index + 1}`} value={row.dayId} onChange={(event) => updateRow(index, "dayId", event.target.value)} /></td>
                        <td><input aria-label={`operator_id ${index + 1}`} value={row.operatorId} onChange={(event) => updateRow(index, "operatorId", event.target.value)} /></td>
                        <td><input aria-label={`incubator_id ${index + 1}`} value={row.incubatorId} onChange={(event) => updateRow(index, "incubatorId", event.target.value)} /></td>
                        <td><input aria-label={`timepoint ${index + 1}`} value={row.timepoint} onChange={(event) => updateRow(index, "timepoint", event.target.value)} /></td>
                        <td><input aria-label={`endpoint_id ${index + 1}`} value={row.endpointId} onChange={(event) => updateRow(index, "endpointId", event.target.value)} /></td>
                        <td><select aria-label={`lifecycle_status ${index + 1}`} value={row.lifecycleStatus} onChange={(event) => updateRow(index, "lifecycleStatus", event.target.value as LifecycleStatus)}>{LIFECYCLE_STATUSES.map((status) => <option key={status}>{status}</option>)}</select></td>
                        <td><input aria-label={`exclusion_reason ${index + 1}`} value={row.exclusionReason} disabled={row.lifecycleStatus !== "excluded"} placeholder="post-treatment | autore: …" onChange={(event) => updateRow(index, "exclusionReason", event.target.value)} /></td>
                        <td><input aria-label={`file_ref ${index + 1}`} value={row.fileRef} onChange={(event) => updateRow(index, "fileRef", event.target.value)} /></td>
                        <td><button className="d0-icon-button" aria-label={`${text(language, "Rimuovi riga", "Remove row")} ${index + 1}`} disabled={rows.length <= 2} onClick={() => removeRow(index)}><Trash2 size={14} /></button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <details className="d0-schema-details">
                <summary>{text(language, "Dizionario completo delle colonne Appendix O", "Complete Appendix O column dictionary")}</summary>
                <div className="d0-table-wrap"><table><thead><tr><th>{text(language, "Colonna", "Column")}</th><th>{text(language, "Tipo", "Type")}</th><th>{text(language, "Obbligo", "Requirement")}</th><th>{text(language, "Nota", "Note")}</th></tr></thead><tbody>{SAMPLE_SCHEMA.map(([name, type, requirement, note]) => <tr key={name}><td><code>{name}</code></td><td>{type}</td><td>{requirement}</td><td>{note}</td></tr>)}</tbody></table></div>
              </details>
            </div>
          )}

          {step === "review" && (
            <div className="d0-review">
              <div className="d0-section-title">
                <div><span className="eyebrow">04 · canonical API compile</span><h2>{text(language, "Verifica, evidenze e proof trace", "Validation, evidence and proof trace")}</h2></div>
                <button className="button primary" disabled={compiling} onClick={() => void compileCanonical()}><Check size={16} /> {compiling ? text(language, "Compilazione…", "Compiling…") : text(language, "Compila con verificatore D0", "Compile with D0 verifier")}</button>
              </div>
              <div className={`d0-compile-result state-${determinability.toLocaleLowerCase()}`} role="status">
                <div><span>{compileResult ? text(language, "Risultato canonico API", "Canonical API result") : text(language, "Anteprima client non autorevole", "Non-authoritative client preview")}</span><strong>{determinability}</strong></div>
                <p>{STATE_COPY.find((item) => item.state === determinability)?.[language === "it" ? "outputIt" : "outputEn"]}</p>
                {!compileResult && <small>{text(language, "Il valore live è solo un controllo client. Compila per ottenere il risultato del motore Python; nessun gold o verdetto scientifico viene creato.", "The live value is only a client check. Compile to obtain the Python engine result; no gold label or scientific verdict is created.")}</small>}
              </div>

              {compileError && <div className="d0-validation-list" role="alert"><AlertTriangle size={18} /><div><strong>{text(language, "Compilazione canonica non completata", "Canonical compilation did not complete")}</strong><p>{compileError}</p></div></div>}

              {compileResult && (
                <section className="d0-result-section" aria-labelledby="canonical-d0-heading">
                  <div className="d0-subheading"><div><span className="eyebrow">ntruth-core@0.2.0 · API</span><h3 id="canonical-d0-heading">{text(language, "Esito canonico del compilatore", "Canonical compiler result")}</h3></div><span className={`rule-outcome outcome-${compileResult.ready_for_handoff ? "fired" : "abstained"}`}>{compileResult.ready_for_handoff ? "READY" : "WITHHELD"}</span></div>
                  <div className="d0-scope-band">
                    <span><strong>capability</strong> {compileResult.capability.status}</span>
                    <span><strong>hard_verifier</strong> {compileResult.verification.status}</span>
                    <span><strong>session</strong> {compileResult.session_persistence}</span>
                    <span><strong>scientific_validation</strong> {compileResult.scientific_validation_status}</span>
                  </div>
                  <p><strong>compilation_id:</strong> <code>{compileResult.compilation_id}</code> · <strong>ruleset SHA-256:</strong> <code>{compileResult.ruleset_checksum.slice(0, 16)}…</code></p>
                  {(compileResult.capability.reason_codes.length > 0 || compileResult.capability.details.length > 0) && (
                    <div className="d0-validation-list">
                      <AlertTriangle size={18} />
                      <div><strong>{text(language, "Motivi del capability gate", "Capability-gate reasons")}</strong><ul>{compileResult.capability.reason_codes.map((code) => <li key={code}><code>{code}</code></li>)}{compileResult.capability.details.map((detail) => <li key={detail}>{detail}</li>)}</ul></div>
                    </div>
                  )}
                  {compileResult.issues.length > 0 && (
                    <div className="d0-validation-list">
                      <AlertTriangle size={18} />
                      <div><strong>{text(language, "Issue canoniche", "Canonical issues")}</strong><ul>{compileResult.issues.map((issue, index) => <li key={`${issue.code}-${index}`}><code>{issue.code}</code> · {issue.message}{issue.row != null ? ` · row ${issue.row}` : ""}{issue.field ? ` · ${issue.field}` : ""}</li>)}</ul></div>
                    </div>
                  )}
                  {(compileResult.verification.violations.length > 0 || compileResult.verification.warnings.length > 0) && (
                    <div className="d0-validation-list">
                      <AlertTriangle size={18} />
                      <div><strong>{text(language, "Traccia hard-verifier", "Hard-verifier trace")}</strong><ul>{[...compileResult.verification.violations, ...compileResult.verification.warnings].map((violation, index) => <li key={`${violation.code}-${index}`}><code>{violation.code}</code> · {violation.message}</li>)}</ul></div>
                    </div>
                  )}
                  {compileResult.block.unit_assessments.length > 0 && (
                    <div className="d0-table-wrap">
                      <table className="d0-count-table" aria-label={text(language, "Unita e n canonici API", "Canonical API units and n")}>
                        <thead><tr><th>scope</th><th>{text(language, "Unita", "Units")}</th><th>n</th><th>inferability</th><th>evidence</th></tr></thead>
                        <tbody>{compileResult.block.unit_assessments.map((assessment) => <tr key={assessment.id}><td>{assessment.scope.group ?? "—"} · {assessment.scope.endpoint_id ?? "—"} · {assessment.scope.timepoint ?? "—"}</td><td>bio={assessment.biological_unit ?? "—"}; allocation={assessment.allocation_unit_candidate ?? "—"}; EU={assessment.experimental_unit ?? "—"}; obs={assessment.observational_unit ?? "—"}; analytical={assessment.analytical_unit ?? "—"}</td><td>planned={assessment.n_planned ?? "—"}; independent={assessment.n_independent ?? "—"}; sources={assessment.biological_source_count ?? "—"}</td><td>{assessment.inferability}</td><td>{assessment.evidence_ids.map((evidenceId) => <button key={evidenceId} className="link-button" onClick={() => setSelectedCanonicalEvidenceId(evidenceId)}>{evidenceId}</button>)}</td></tr>)}</tbody>
                      </table>
                      {compileResult.block.unit_assessments.flatMap((assessment) => assessment.conditional_scenarios).map((scenario) => <div key={`${scenario.rule_id}-${scenario.conditional_on}`} className="d0-validation-list"><AlertTriangle size={18} /><div><strong>{text(language, "Ramo canonico condizionale", "Canonical conditional branch")} · {scenario.rule_id}</strong><p>{scenario.question}</p><p><code>if_confirmed</code> {JSON.stringify(scenario.if_confirmed)} · <code>if_rejected</code> {JSON.stringify(scenario.if_rejected)}</p>{scenario.evidence_ids.map((evidenceId) => <button key={evidenceId} className="link-button" onClick={() => setSelectedCanonicalEvidenceId(evidenceId)}>{evidenceId}</button>)}</div></div>)}
                    </div>
                  )}
                  {compileResult.block.count_records.length > 0 && (
                    <div className="d0-table-wrap">
                      <table className="d0-count-table" aria-label={text(language, "Conteggi canonici API", "Canonical API counts")}>
                        <thead><tr><th>{text(language, "Tipo", "Kind")}</th><th>scope</th><th>{text(language, "Valore", "Value")}</th><th>{text(language, "Quantificatore", "Quantifier")}</th><th>evidence</th></tr></thead>
                        <tbody>{compileResult.block.count_records.map((count) => <tr key={count.count_id}><td><code>{count.kind}</code></td><td>{count.scope.unit_type ?? "—"} · {count.scope.group_or_level ?? "—"} · {count.scope.lifecycle ?? "—"}</td><td>{count.value ?? "—"}</td><td>{count.quantifier}</td><td>{count.evidence_ids.map((evidenceId) => <button key={evidenceId} className="link-button" onClick={() => setSelectedCanonicalEvidenceId(evidenceId)}>{evidenceId}</button>)}</td></tr>)}</tbody>
                      </table>
                    </div>
                  )}
                  {compileResult.block.alerts.length > 0 && (
                    <div className="d0-validation-list">
                      <AlertTriangle size={18} />
                      <div><strong>{text(language, "Alert canonici", "Canonical alerts")}</strong><ul>{compileResult.block.alerts.map((alert) => <li key={alert.id}><code>{alert.rule_id}</code> · {alert.severity} · {alert.message} {alert.evidence_ids.map((evidenceId) => <button key={evidenceId} className="link-button" onClick={() => setSelectedCanonicalEvidenceId(evidenceId)}>{evidenceId}</button>)}</li>)}</ul></div>
                    </div>
                  )}
                  {compileResult.block.contradictions.length > 0 && (
                    <div className="d0-validation-list">
                      <AlertTriangle size={18} />
                      <div><strong>{text(language, "Conflitti canonici trattenuti", "Retained canonical conflicts")}</strong><ul>{compileResult.block.contradictions.map((contradiction) => <li key={contradiction.id}>{contradiction.description}<ul>{contradiction.retained_interpretations.map((interpretation) => <li key={interpretation}>{interpretation}</li>)}</ul>{contradiction.evidence_ids.map((evidenceId) => <button key={evidenceId} className="link-button" onClick={() => setSelectedCanonicalEvidenceId(evidenceId)}>{evidenceId}</button>)}</li>)}</ul></div>
                    </div>
                  )}
                  {compileResult.block.questions.length > 0 && (
                    <div className="d0-validation-list">
                      <AlertTriangle size={18} />
                      <div><strong>{text(language, "Domande canoniche da risolvere", "Canonical questions to resolve")}</strong><ul>{compileResult.block.questions.slice(0, 8).map((question) => <li key={question.id}>{question.text}{question.missing_field ? <> · <code>{question.missing_field}</code></> : null}</li>)}</ul></div>
                    </div>
                  )}
                  {compileResult.rule_evaluations.some((evaluation) => evaluation.outcome !== "not_applicable") && (
                    <details className="d0-schema-details">
                      <summary>{text(language, "Valutazioni canoniche delle regole", "Canonical rule evaluations")}</summary>
                      <div className="d0-table-wrap"><table><thead><tr><th>rule</th><th>outcome</th><th>scope</th><th>{text(language, "Astensione/eccezione", "Abstention/exception")}</th><th>evidence</th></tr></thead><tbody>{compileResult.rule_evaluations.filter((evaluation) => evaluation.outcome !== "not_applicable").map((evaluation, index) => <tr key={`${evaluation.rule_id}-${evaluation.scope_label}-${index}`}><td><code>{evaluation.rule_id}@{evaluation.rule_version}</code></td><td>{evaluation.outcome}</td><td>{evaluation.scope_label || "—"}</td><td>{evaluation.triggered_abstention ?? evaluation.triggered_exception ?? (evaluation.evidence_gap.join(", ") || "—")}</td><td>{Array.from(new Set(evaluation.premise_trace.flatMap((premise) => premise.evidence_ids))).map((evidenceId) => <button key={evidenceId} className="link-button" onClick={() => setSelectedCanonicalEvidenceId(evidenceId)}>{evidenceId}</button>)}</td></tr>)}</tbody></table></div>
                    </details>
                  )}
                  <details className="d0-schema-details">
                    <summary>{text(language, "Gerarchia canonica API", "Canonical API hierarchy")}</summary>
                    <div className="d0-table-wrap"><table aria-label={text(language, "Nodi canonici API", "Canonical API nodes")}><thead><tr><th>node_id</th><th>type</th><th>label</th><th>evidence</th></tr></thead><tbody>{compileResult.block.hierarchy.nodes.map((node) => <tr key={node.id}><td><code>{node.id}</code></td><td>{node.type}</td><td>{node.label}</td><td>{node.evidence_ids.map((evidenceId) => <button key={evidenceId} className="link-button" onClick={() => setSelectedCanonicalEvidenceId(evidenceId)}>{evidenceId}</button>)}</td></tr>)}</tbody></table></div>
                    <div className="d0-table-wrap"><table aria-label={text(language, "Relazioni canoniche API", "Canonical API relations")}><thead><tr><th>type</th><th>source</th><th>target</th><th>evidence</th></tr></thead><tbody>{compileResult.block.hierarchy.relations.map((relation) => <tr key={relation.id}><td>{relation.type}</td><td><code>{relation.source}</code></td><td><code>{relation.target}</code></td><td>{relation.evidence_ids.map((evidenceId) => <button key={evidenceId} className="link-button" onClick={() => setSelectedCanonicalEvidenceId(evidenceId)}>{evidenceId}</button>)}</td></tr>)}</tbody></table></div>
                  </details>
                  {selectedCanonicalEvidence && (
                    <section className="d0-result-section d0-evidence-view" aria-labelledby="canonical-evidence-heading">
                      <div className="d0-subheading"><div><span className="eyebrow">canonical API evidence</span><h4 id="canonical-evidence-heading">{text(language, "Evidenza canonica sincronizzata", "Synchronized canonical evidence")}</h4></div><FileText size={18} /></div>
                      <div className="source-locator"><Link2 size={14} /> {canonicalEvidenceLocator(selectedCanonicalEvidence)}</div>
                      <blockquote>{selectedCanonicalEvidence.text}</blockquote>
                      <div className="d0-evidence-meta"><span>{selectedCanonicalEvidence.evidence_type ?? "UNSPECIFIED"}</span><span>{selectedCanonicalEvidence.extraction_method ?? selectedCanonicalEvidence.parser_version}</span></div>
                      <div className="d0-evidence-index" aria-label={text(language, "Indice evidenze canoniche", "Canonical evidence index")}>{compileResult.block.evidence.map((evidenceItem) => <button key={evidenceItem.id} className={evidenceItem.id === selectedCanonicalEvidence.id ? "active" : ""} onClick={() => setSelectedCanonicalEvidenceId(evidenceItem.id)}>{evidenceItem.id}</button>)}</div>
                    </section>
                  )}
                  <small>{text(language, "Il risultato è registrato nella memoria del processo locale e non certifica validità scientifica, potenza o scelta del modello statistico.", "The result is stored in local process memory and does not certify scientific validity, power, or statistical-model choice.")}</small>
                </section>
              )}

              {compileResult && (
                <PlanExecutionPanel
                  language={language}
                  draft={draft}
                  rows={rows}
                  experimentBlockId={experimentBlockId}
                  compileResult={compileResult}
                />
              )}

              <div className="d0-client-preview" aria-label={text(language, "Anteprima client non autorevole", "Non-authoritative client preview")}>
                <div className="d0-validation-list">
                  <AlertTriangle size={18} />
                  <div><strong>{text(language, "Dettaglio client non autorevole", "Non-authoritative client detail")}</strong><p>{text(language, "Le tabelle e la proof trace seguenti aiutano a compilare il draft, ma non sostituiscono conteggi, domande o valutazioni restituite dalla API.", "The following tables and proof trace help prepare the draft but do not replace counts, questions, or evaluations returned by the API.")}</p></div>
                </div>

              {(missingFacts.length > 0 || invariantErrors.length > 0 || capabilityErrors.length > 0) && (
                <div className="d0-validation-list">
                  <AlertTriangle size={18} />
                  <div><strong>{text(language, "Fatti, invarianti o limiti di profilo da risolvere", "Facts, invariants, or profile limits to resolve")}</strong><ul>{missingFacts.slice(0, 6).map((item) => <li key={item}>{text(language, "Manca", "Missing")}: <code>{item}</code></li>)}{invariantErrors.map((item) => <li key={item}>{item}</li>)}{capabilityErrors.map((item) => <li key={item}>{item}</li>)}</ul></div>
                </div>
              )}

              {previewDeterminability === "CONDITIONALLY_DETERMINATE" && (
                <section className="d0-result-section conditional-branches" aria-labelledby="d0-conditional-heading">
                  <div className="d0-subheading"><div><span className="eyebrow">client preview · if / then</span><h3 id="d0-conditional-heading">{text(language, "Rami condizionali materializzati", "Materialized conditional branches")}</h3></div></div>
                  <p><strong>{text(language, "Domanda decisiva:", "Decisive question:")}</strong> {text(language, `Le unità ${draft.allocationLevel} sono state allocate indipendentemente ai livelli di ${draft.factorName}?`, `Were ${draft.allocationLevel} units independently allocated to ${draft.factorName} levels?`)}</p>
                  <div className="field-grid">
                    <div className="d0-readonly-field"><span>{text(language, "Se confermato", "If confirmed")}</span><strong>EU = {draft.allocationLevel}</strong><small>n({draft.levelA}) = {countUniqueAllocationUnits(rows, draft.levelA, draft.allocationLevel)}; n({draft.levelB}) = {countUniqueAllocationUnits(rows, draft.levelB, draft.allocationLevel)}</small></div>
                    <div className="d0-readonly-field"><span>{text(language, "Se rifiutato", "If rejected")}</span><strong>EU = null; independent_n = null</strong><small>{text(language, "Identificare e contare l'unità superiore realmente allocata.", "Identify and count the higher-level unit that was actually allocated.")}</small></div>
                  </div>
                </section>
              )}

              <section className="d0-result-section" aria-labelledby="determinability-heading">
                <div className="d0-subheading"><div><span className="eyebrow">normative state machine</span><h3 id="determinability-heading">DeterminabilityState</h3></div><span className="d0-derived-label">{text(language, "Derivato · sola lettura", "Derived · read only")}</span></div>
                <div className="d0-table-wrap"><table className="d0-state-table" aria-label={text(language, "Sette stati di determinabilità", "Seven determinability states")}><thead><tr><th>{text(language, "Stato", "State")}</th><th>{text(language, "Precondizione", "Precondition")}</th><th>{text(language, "Output ammesso", "Allowed output")}</th><th>{text(language, "Singolo n", "Single n")}</th></tr></thead><tbody>{STATE_COPY.map((item) => <tr key={item.state} className={item.state === determinability ? "active" : ""} aria-current={item.state === determinability ? "true" : undefined}><td><span className="state-marker" /> <code>{item.state}</code>{item.state === determinability && <small>{text(language, "Attivo", "Active")}</small>}</td><td>{language === "it" ? item.conditionIt : item.conditionEn}</td><td>{language === "it" ? item.outputIt : item.outputEn}</td><td>{nCopy(item.singleN)}</td></tr>)}</tbody></table></div>
              </section>

              <section className="d0-result-section" aria-labelledby="lifecycle-heading">
                <div className="d0-subheading"><div><span className="eyebrow">client preview · scope-aware counts</span><h3 id="lifecycle-heading">{text(language, "Conteggi del lifecycle", "Lifecycle counts")}</h3></div><span className="d0-derived-label">EXACT ≠ NOT_REPORTED</span></div>
                <div className="d0-scope-band"><span><strong>unit_type</strong> {draft.allocationLevel}</span><span><strong>factor</strong> {factorId(draft.factorName)}</span><span><strong>contrast</strong> {draft.levelA} vs {draft.levelB}</span><span><strong>endpoint</strong> {draft.endpointId}</span><span><strong>timepoint</strong> {rows[0]?.timepoint || "UNKNOWN"}</span></div>
                <div className="d0-table-wrap"><table className="d0-count-table" aria-label={text(language, "Conteggi lifecycle scope-aware", "Scope-aware lifecycle counts")}><thead><tr><th>{text(language, "Fase", "Phase")}</th><th>{text(language, "Livello", "Level")}</th><th>{text(language, "Valore", "Value")}</th><th>{text(language, "Quantificatore", "Quantifier")}</th><th>{text(language, "Fonte", "Source")}</th></tr></thead><tbody>{counts.map((count) => <tr key={`${count.phase}-${count.group}`}><td><code>{count.phase}</code></td><td>{count.group}</td><td>{count.value ?? "—"}</td><td><span className={`quantifier quantifier-${count.quantifier.toLocaleLowerCase()}`}>{count.quantifier}</span></td><td><button className="link-button" onClick={() => setSelectedEvidenceId(count.evidenceId)}>{count.sourceCell}</button></td></tr>)}</tbody></table></div>
                <p className="muted">{text(language, "Le fasi successive restano NOT_REPORTED finché non esiste un event ledger auditabile; lo stato corrente della riga non viene reinterpretato come storia cumulativa.", "Later phases remain NOT_REPORTED until an auditable event ledger exists; a row's current state is not reinterpreted as cumulative history.")}</p>
                <div className="d0-effective-n"><strong>effective_n</strong><span>NOT_CALCULATED</span><small>{text(language, "Diagnostica statistica separata: non sostituisce independent_n.", "Separate statistical diagnostic: it does not replace independent_n.")}</small></div>
              </section>

              <div className="d0-proof-grid">
                <section className="d0-result-section" aria-labelledby="proof-heading">
                  <div className="d0-subheading"><div><span className="eyebrow">client preview · ntruth-core@0.2.0</span><h3 id="proof-heading">Proof trace · GEN-001@1.0.0</h3></div><span className={`rule-outcome outcome-${previewDeterminability === "DETERMINATE" ? "fired" : "abstained"}`}>{previewDeterminability === "DETERMINATE" ? "FIRED" : "ABSTAINED"}</span></div>
                  <p className="d0-proof-warning">{text(language, "Rappresentazione client di supporto; l'esito canonico è quello restituito dalla API e non costituisce validazione scientifica o annotazione gold.", "Supporting client representation; the canonical result is returned by the API and is not scientific validation or a gold annotation.")}</p>
                  <div className="d0-premise-list">{proofPremises.map((premise) => <button key={premise.id} className={`d0-premise premise-${premise.status}`} onClick={() => setSelectedEvidenceId(premise.evidenceId)}><span>{premise.status === "satisfied" ? <Check size={14} /> : <AlertTriangle size={14} />}</span><span><code>{premise.expression}</code><small>{premise.label}</small></span><Link2 size={14} /></button>)}</div>
                  <div className="d0-conclusion"><span>{text(language, "Conclusione candidata della preview", "Candidate preview conclusion")}</span><strong>{previewDeterminability === "DETERMINATE" ? `${text(language, "EU candidata", "Candidate EU")}: ${draft.allocationLevel}; independent_n(${draft.levelA}) = ${countUniqueAllocationUnits(rows, draft.levelA, draft.allocationLevel)}; independent_n(${draft.levelB}) = ${countUniqueAllocationUnits(rows, draft.levelB, draft.allocationLevel)}` : text(language, "EU e n non emessi senza tutte le precondizioni.", "EU and n are withheld until every precondition is met.")}</strong><small>{text(language, "Valore non autorevole; l'indipendenza riguarda l'assegnazione del fattore e non prova indipendenza delle fonti biologiche.", "Non-authoritative value; independence concerns factor assignment and does not prove biological-source independence.")}</small></div>
                </section>

                <section className="d0-result-section d0-evidence-view" aria-labelledby="d0-evidence-heading">
                  <div className="d0-subheading"><div><span className="eyebrow">synchronized source</span><h3 id="d0-evidence-heading">Evidence View</h3></div><FileText size={18} /></div>
                  <div className="source-locator"><Link2 size={14} /> {selectedEvidence.locator}</div>
                  <blockquote>{selectedEvidence.text}</blockquote>
                  <div className="d0-evidence-meta"><span>{selectedEvidence.evidenceType}</span><span>{selectedEvidence.origin}</span></div>
                  <div className="d0-evidence-index" aria-label={text(language, "Indice evidenze D0", "D0 evidence index")}>{evidence.map((item) => <button key={item.id} className={item.id === selectedEvidence.id ? "active" : ""} onClick={() => setSelectedEvidenceId(item.id)}>{item.title}</button>)}</div>
                </section>
              </div>

              <section className="d0-result-section d0-methods" aria-labelledby="methods-d0-heading">
                <div className="d0-subheading"><div><span className="eyebrow">generated draft</span><h3 id="methods-d0-heading">Design &amp; Methods statement</h3></div><Table2 size={18} /></div>
                <blockquote>{text(language, `Nel blocco D0 il fattore ${draft.factorName} comprende i livelli ${draft.levelA} e ${draft.levelB}. Il fattore è allocato a livello ${draft.allocationLevel} mediante: ${draft.independenceMechanism || "meccanismo non riportato"}. L'endpoint primario ${draft.endpointId} (${draft.endpointName}) è misurato sui pozzetti. Il target inferenziale dichiarato è: ${draft.inferenceTarget}.`, `In the D0 block, factor ${draft.factorName} includes levels ${draft.levelA} and ${draft.levelB}. The factor is allocated at ${draft.allocationLevel} level through: ${draft.independenceMechanism || "mechanism not reported"}. Primary endpoint ${draft.endpointId} (${draft.endpointName}) is measured on wells. The declared inference target is: ${draft.inferenceTarget}.`)}</blockquote>
                <small>{text(language, "Bozza iniziale da verificare e riconciliare con l'esecuzione wet-lab; non è un testo certificato.", "Initial draft to verify and reconcile with wet-lab execution; this is not certified text.")}</small>
              </section>
              </div>
            </div>
          )}

          <div className="d0-nav-actions">
            <button className="button secondary" onClick={goBack} disabled={currentStep === 0}>{text(language, "Indietro", "Back")}</button>
            {currentStep < STEPS.length - 1 && <button className="button primary" onClick={goNext}>{text(language, "Continua", "Continue")} <ChevronRight size={16} /></button>}
          </div>
        </div>

        <aside className="d0-profile-summary" aria-label="Core Profile summary">
          <div><span className="eyebrow">live Core Profile</span><h2>{text(language, "Riepilogo strutturale", "Structural summary")}</h2></div>
          <dl>
            <div><dt>experiment_block_id</dt><dd>{experimentBlockId}</dd></div>
            <div><dt>factor</dt><dd>{draft.factorName || "NOT_REPORTED"}</dd></div>
            <div><dt>primary_contrast</dt><dd>{draft.levelA || "?"} vs {draft.levelB || "?"}</dd></div>
            <div><dt>allocation_level</dt><dd>{draft.allocationLevel}</dd></div>
            <div><dt>independently_assigned</dt><dd>{draft.independentlyAssigned}</dd></div>
            <div><dt>endpoint</dt><dd>{draft.endpointId || "NOT_REPORTED"}</dd></div>
            <div><dt>samples</dt><dd>{rows.length}</dd></div>
            <div><dt>determinability</dt><dd><span className="d0-state-pill">{determinability}</span></dd></div>
            <div><dt>result_authority</dt><dd>{compileResult ? "canonical_api" : "client_preview"}</dd></div>
          </dl>
          <div className="d0-summary-note"><AlertTriangle size={16} /><p>{text(language, "Gli ID aiutano la provenance ma non provano indipendenza. AUTHOR_ASSERTION da sola non promuove a DETERMINATE.", "IDs support provenance but do not prove independence. AUTHOR_ASSERTION alone cannot promote the state to DETERMINATE.")}</p></div>
        </aside>
      </div>
    </section>
  );
}
