import type {
  AnalysisResponse,
  AuditEntry,
  Correction,
  DomainTransparency,
  PrivacyAudit,
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
