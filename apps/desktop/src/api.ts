import type {
  PlanExecutionGetResponse,
  PlanExecutionSubmitPayload,
  PlanExecutionSubmitResponse,
} from "./d0/planExecutionTypes";
import type { DeterminabilityState } from "./d0/types";
import type {
  AnalysisResponse,
  AuditEntry,
  Correction,
  DomainTransparency,
  ExperimentBlock,
  PrivacyAudit,
  Report,
  ShareReadiness,
} from "./types";

export type {
  PlanExecutionGetResponse,
  PlanExecutionSubmitPayload,
  PlanExecutionSubmitResponse,
} from "./d0/planExecutionTypes";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail?: unknown,
  ) {
    super(message);
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  const body = (await response.json().catch(() => null)) as
    | { detail?: unknown }
    | null;
  if (!response.ok) {
    const detail = body?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : typeof detail === "object" && detail && "message" in detail
          ? String(detail.message)
          : `Richiesta fallita (${response.status})`;
    throw new ApiError(message, response.status, detail);
  }
  return body as T;
}

export async function health(): Promise<{ status: string; version: string }> {
  return request("/v1/health");
}

export async function preflight(domain: string): Promise<DomainTransparency> {
  return request("/v1/preflight", {
    method: "POST",
    body: JSON.stringify({ domain }),
  });
}

export interface AnalyzePayload {
  source: string;
  out: string;
  project_dir?: string;
  language: "it" | "en";
  domain: string;
  acknowledge_unvalidated_domain: boolean;
}

export async function analyze(payload: AnalyzePayload): Promise<AnalysisResponse> {
  return request("/v1/analyze", { method: "POST", body: JSON.stringify(payload) });
}

export interface CorrectionResponse {
  report: Report;
  block_id: string;
  audit_trail: AuditEntry[];
  active_correction_ids: string[];
  redo_correction_ids: string[];
  candidate_annotations: Record<string, unknown>;
  candidate_artifact_name: string;
  recalculation_ms: number;
  artifacts: Record<string, string>;
  run_id: string;
  revision: number;
  privacy_audit: PrivacyAudit;
  share_readiness: ShareReadiness;
}

export async function applyCorrection(
  sessionId: string,
  blockId: string,
  correction: Omit<Correction, "id" | "sequence">,
): Promise<CorrectionResponse> {
  return request("/v1/corrections/apply", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, block_id: blockId, correction }),
  });
}

export async function navigateCorrection(
  action: "undo" | "redo",
  sessionId: string,
  blockId: string,
  reviewerRole = "reviewer",
): Promise<CorrectionResponse> {
  return request(`/v1/corrections/${action}`, {
    method: "POST",
    body: JSON.stringify({
      session_id: sessionId,
      block_id: blockId,
      reviewer_role: reviewerRole,
    }),
  });
}

export interface InferenceTargetDraft {
  target_id?: string;
  question_text: string;
  claim_text: string;
  population_of_inference: string;
  factor_ids: string[];
  contrast_ids: string[];
  endpoint_ids: string[];
  target_biological_unit: string;
  evidence_ids: string[];
  rationale: string;
  reviewer_role: string;
  estimands: EstimandDraft[];
}

export interface EstimandDraft {
  estimand_id?: string;
  endpoint_id: string;
  effect_measure: string;
  target_population_or_unit: string;
  generalization_level: string;
  factor_ids: string[];
  timepoint?: string;
  condition?: string;
  evidence_ids: string[];
}

export async function confirmInferenceTarget(
  sessionId: string,
  blockId: string,
  target: InferenceTargetDraft,
): Promise<CorrectionResponse> {
  return request("/v1/design/inference-targets/confirm", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, block_id: blockId, target }),
  });
}

export type ProspectiveD0NodeType = "Well" | "Plate" | "UNKNOWN";

export interface ProspectiveD0CompilePayload {
  draft: {
    experimentBlockId: string;
    title: string;
    question: string;
    inferenceTarget: string;
    factorName: string;
    factorKind: "treatment" | "genotype" | "dose" | "time" | "diet" | "other" | "unknown";
    levelA: string;
    levelB: string;
    endpointName: string;
    endpointId: string;
    measuredOn: ProspectiveD0NodeType;
    allocationLevel: ProspectiveD0NodeType;
    applicationLevel: ProspectiveD0NodeType;
    independentlyAssigned: "TRUE" | "FALSE" | "UNKNOWN";
    independenceMechanism: string | null;
    sharedEnvironment: string[];
    targetBiologicalUnit: Exclude<ProspectiveD0NodeType, "UNKNOWN">;
    estimand: {
      effectMeasure: string;
      targetPopulationOrUnit: string;
      generalizationLevel: string;
      timepoint: string | null;
      condition: string | null;
    };
    reviewerRole: string;
  };
  rows: Array<{
    sampleId: string;
    sourceId: string | null;
    preparationId: string | null;
    cultureId: string | null;
    plateId: string | null;
    wellId: string | null;
    factorLevel: string;
    batchId: string | null;
    extraFields: {
      day_id: string | null;
      operator_id: string | null;
      incubator_id: string | null;
    };
    timepoint: string | null;
    endpointId: string | null;
    lifecycleStatus: "planned" | "treated" | "observed" | "excluded" | "analysed";
    exclusionReason: string | null;
    exclusionPhase:
      | "pre_allocation"
      | "post_allocation"
      | "post_treatment"
      | "post_measurement"
      | "post_outcome"
      | "unknown"
      | null;
    exclusionPrespecified: "TRUE" | "FALSE" | "UNKNOWN";
    exclusionAuthorRole: string | null;
    exclusionImpact: string | null;
    fileRef: string | null;
  }>;
  language: "it" | "en";
  rulesetId: "ntruth-core";
  rulesetVersion: "0.2.0";
}

export interface ProspectiveD0CompileResponse {
  session_id: string;
  session_persistence: "ephemeral_process_memory";
  contract_version: "1.0.0";
  compiler_version: "1.0.0";
  compilation_id: string;
  ruleset_checksum: string;
  block: ExperimentBlock;
  sample_sheet: Record<string, unknown>;
  capability: {
    profile_id: string;
    profile_version: string;
    profile_reference: string;
    status: string;
    supported: boolean | null;
    reason_codes: string[];
    details: string[];
  };
  design_compilation: Record<string, unknown>;
  verification: {
    schema_version: string;
    status: string;
    block_id: string;
    violations: Array<{
      code: string;
      message: string;
      blocking: boolean;
      node_ids: string[];
      relation_ids: string[];
    }>;
    warnings: Array<{
      code: string;
      message: string;
      blocking: boolean;
      node_ids: string[];
      relation_ids: string[];
    }>;
    checked_invariants: string[];
  };
  rule_evaluations: Array<{
    rule_id: string;
    rule_version: string;
    ruleset_id: string;
    ruleset_version: string;
    ruleset_checksum: string;
    outcome: "fired" | "not_applicable" | "abstained" | "excepted" | "unevaluable";
    matched: string[];
    failed: string[];
    triggered_exception?: string | null;
    triggered_abstention?: string | null;
    unknown_predicates: string[];
    scope_label: string;
    premise_trace: Array<{
      expression: string;
      result: boolean | null;
      fact_ids: string[];
      evidence_ids: string[];
      provenance_origins: string[];
    }>;
    evidence_gap: string[];
    output_ids: string[];
  }>;
  issues: Array<{
    code: string;
    message: string;
    severity: "error" | "warning";
    row?: number | null;
    field?: string | null;
  }>;
  determinability: DeterminabilityState;
  ready_for_handoff: boolean;
  scientific_validation_status: "not_performed";
  prohibited_outputs: string[];
  audit_trail: Array<{
    id: string;
    action: "compile";
    actor_role: string;
    recorded_at: string;
    input_checksum: string;
    output_checksum: string;
  }>;
}

export async function compileProspectiveD0(
  payload: ProspectiveD0CompilePayload,
): Promise<ProspectiveD0CompileResponse> {
  return request("/v1/prospective/d0/compile", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function submitPlanExecution(
  payload: PlanExecutionSubmitPayload,
): Promise<PlanExecutionSubmitResponse> {
  return request("/v1/prospective/plan-execution", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getPlanExecution(
  recordId: string,
  projectDir: string,
): Promise<PlanExecutionGetResponse> {
  const params = new URLSearchParams({ project_dir: projectDir });
  return request(
    `/v1/prospective/plan-execution/${encodeURIComponent(recordId)}?${params.toString()}`,
  );
}

export function downloadJson(filename: string, payload: unknown): void {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
