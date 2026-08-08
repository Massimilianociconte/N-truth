import type {
  AnalysisResponse,
  AuditEntry,
  Correction,
  DomainTransparency,
  PrivacyAudit,
  QuickDesignV8Response,
  QuickDesignV8Submission,
  Report,
  ShareReadiness,
} from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail?: unknown,
  ) {
    super(message);
  }
}

function errorDetailField(error: ApiError, field: string): string | undefined {
  if (!error.detail || typeof error.detail !== "object" || !(field in error.detail)) {
    return undefined;
  }
  const value = (error.detail as Record<string, unknown>)[field];
  return typeof value === "string" && value.trim() ? value : undefined;
}

export function apiErrorCode(error: ApiError): string | undefined {
  return errorDetailField(error, "code");
}

export function apiErrorIssueId(error: ApiError): string | undefined {
  return errorDetailField(error, "issue_id");
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

export interface LegacyAnalyzePayload {
  source: string;
  out: string;
  project_dir?: string;
  language: "it" | "en";
  domain: string;
  acknowledge_unvalidated_domain: boolean;
}

type JsonRecord = Record<string, unknown>;

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isCanonicalQuickDesignResponse(value: unknown): value is QuickDesignV8Response {
  if (!isRecord(value) || !isRecord(value.contract) || !isRecord(value.report)) return false;
  const report = value.report;
  const countRegistry = report.count_registry;
  return (
    value.contract.code === "PRD_V8" &&
    value.contract.version === "8.0.0" &&
    value.contract.strategy_module_status === "HANDOFF_ONLY" &&
    typeof report.report_id === "string" &&
    typeof report.content_checksum === "string" &&
    report.strategy_module_status === "HANDOFF_ONLY" &&
    Array.isArray(report.query_sections) &&
    Array.isArray(report.claim_sets) &&
    Array.isArray(report.source_records) &&
    isRecord(countRegistry) &&
    Array.isArray(countRegistry.records)
  );
}

function sanitizeLegacyValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sanitizeLegacyValue);
  if (!isRecord(value)) return value === "ready_for_review" ? "review_required" : value;
  return Object.fromEntries(
    Object.entries(value)
      .filter(([field]) => field !== "candidate_analysis_strategies")
      .map(([field, item]) => [field, sanitizeLegacyValue(item)]),
  );
}

function neutralLegacyReviewOutput(blockId: string, value: unknown): JsonRecord {
  const sanitized = isRecord(sanitizeLegacyValue(value))
    ? (sanitizeLegacyValue(value) as JsonRecord)
    : {};
  const methods = isRecord(sanitized.methods_statement)
    ? sanitized.methods_statement
    : {};
  return {
    ...sanitized,
    block_id: typeof sanitized.block_id === "string" ? sanitized.block_id : blockId,
    path_status: "review_required",
    non_certifying: true,
    methods_statement: {
      ...methods,
      status: "review_required",
      non_certifying: true,
    },
    determinability: isRecord(sanitized.determinability)
      ? sanitized.determinability
      : {
          state: "INSUFFICIENT_INFORMATION",
          rationale:
            "The v7 adapter does not provide claim-specific PRD v8 determinability.",
        },
    design_adequacy: isRecord(sanitized.design_adequacy)
      ? sanitized.design_adequacy
      : {
          knowledge_state: "UNKNOWN",
          finding: "NOT_ASSESSED",
          rationale:
            "The historical output does not authorize a PRD v8 design-adequacy evaluation.",
        },
    strategy_module_status: "HANDOFF_ONLY",
    statistical_handoff: isRecord(sanitized.statistical_handoff)
      ? sanitized.statistical_handoff
      : {
          structural_requirements: [],
          unresolved_questions: [
            "Migrate this historical output to a verified PRD v8 query-scoped report.",
          ],
        },
  };
}

export function adaptV7AnalysisResponse(value: unknown): AnalysisResponse {
  if (!isRecord(value) || !isRecord(value.report)) {
    throw new Error("Malformed DEPRECATED_V7_ADAPTER response.");
  }
  const sanitizedResponse = sanitizeLegacyValue(value) as JsonRecord;
  const sanitizedReport = sanitizedResponse.report as JsonRecord;
  const legacyReport = value.report;
  const rawOutputs = isRecord(legacyReport.review_outputs)
    ? legacyReport.review_outputs
    : isRecord(legacyReport.positive_outputs)
      ? legacyReport.positive_outputs
      : {};
  const reviewOutputs = Object.fromEntries(
    Object.entries(rawOutputs).map(([blockId, output]) => [
      blockId,
      neutralLegacyReviewOutput(blockId, output),
    ]),
  );
  const { positive_outputs: _positiveOutputs, ...reportWithoutPositiveOutputs } =
    sanitizedReport;
  return {
    ...sanitizedResponse,
    report: {
      ...reportWithoutPositiveOutputs,
      review_outputs: reviewOutputs,
    },
  } as unknown as AnalysisResponse;
}

export async function analyzeV7(
  payload: LegacyAnalyzePayload,
): Promise<AnalysisResponse> {
  const raw = await request<unknown>("/v7/analyze", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  if (
    !isRecord(raw) ||
    !isRecord(raw.contract) ||
    raw.contract.code !== "DEPRECATED_V7_ADAPTER"
  ) {
    throw new Error("The historical endpoint did not return DEPRECATED_V7_ADAPTER.");
  }
  return adaptV7AnalysisResponse(raw);
}

export async function quickDesignV8(
  payload: QuickDesignV8Submission,
): Promise<QuickDesignV8Response> {
  const result = await request<unknown>("/v8/quick-design", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  if (!isCanonicalQuickDesignResponse(result)) {
    throw new Error("The canonical endpoint returned a malformed PRD_V8 ReportBundle.");
  }
  return result;
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
): Promise<CorrectionResponse> {
  return request(`/v1/corrections/${action}`, {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, block_id: blockId }),
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

export function downloadJson(filename: string, payload: unknown): void {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
