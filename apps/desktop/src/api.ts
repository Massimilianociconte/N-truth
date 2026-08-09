import type {
  AnalysisResponse,
  AuditEntry,
  Correction,
  DomainTransparency,
  GuidedQuickDesignBuildRequest,
  GuidedQuickDesignBuildResponse,
  KnowledgeValue,
  PrivacyAudit,
  ProspectiveArtifactV8,
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

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function isKnowledgeValue(value: unknown): value is KnowledgeValue {
  if (!isRecord(value) || typeof value.knowledge_state !== "string") return false;
  const state = value.knowledge_state;
  return (
    [
      "PRESENT",
      "ABSENT_EXPLICIT",
      "NOT_REPORTED",
      "UNKNOWN",
      "CONFLICTING",
      "NOT_APPLICABLE",
    ].includes(state) &&
    (value.evidence_ids === undefined || isStringArray(value.evidence_ids)) &&
    (value.source_scope_ids === undefined || isStringArray(value.source_scope_ids)) &&
    (state !== "PRESENT" || ("value" in value && value.value !== null)) &&
    (!["UNKNOWN", "NOT_APPLICABLE"].includes(state) || isNonEmptyString(value.rationale))
  );
}

function isArtifact(value: unknown): value is ProspectiveArtifactV8 {
  return (
    isRecord(value) &&
    value.schema_version === "8.0.0" &&
    isNonEmptyString(value.artifact_id) &&
    ["SAMPLE_SHEET", "METHODS_DRAFT", "ID_CONVENTION"].includes(String(value.kind)) &&
    isNonEmptyString(value.media_type) &&
    typeof value.content === "string" &&
    typeof value.content_checksum === "string" &&
    /^[0-9a-f]{64}$/.test(value.content_checksum)
  );
}

function hasExactArtifacts(value: unknown): value is ProspectiveArtifactV8[] {
  if (!Array.isArray(value) || value.length !== 3 || !value.every(isArtifact)) return false;
  return new Set(value.map((item) => item.kind)).size === 3;
}

function isQuickDesignSubmission(value: unknown): value is QuickDesignV8Submission {
  return (
    isRecord(value) &&
    value.schema_version === "8.0.0" &&
    isRecord(value.pipeline_request) &&
    isRecord(value.input_ledger) &&
    isRecord(value.planned_event_registry) &&
    Array.isArray(value.planned_unit_counts) &&
    value.planned_unit_counts.length > 0 &&
    typeof value.sample_sheet_csv === "string" &&
    value.sample_sheet_csv.length > 0 &&
    typeof value.methods_draft === "string" &&
    value.methods_draft.length > 0 &&
    typeof value.id_convention === "string" &&
    value.id_convention.length > 0 &&
    isStringArray(value.user_confirmation_scopes) &&
    value.user_confirmation_scopes.length > 0 &&
    isKnowledgeValue(value.ai_candidates) &&
    isKnowledgeValue(value.conflicts) &&
    isKnowledgeValue(value.sensitivities) &&
    Array.isArray(value.questions) &&
    value.questions.length > 0 &&
    isRecord(value.statistical_handoff) &&
    value.statistical_handoff.strategy_module_status === "HANDOFF_ONLY" &&
    Array.isArray(value.statistical_handoff.items) &&
    isStringArray(value.inference_limits) &&
    value.inference_limits.length > 0
  );
}

function isClaimSet(value: unknown): boolean {
  if (
    !isRecord(value) ||
    typeof value.claim_set_id !== "string" ||
    typeof value.inferential_query_id !== "string" ||
    !Array.isArray(value.claims) ||
    value.claims.length === 0
  ) {
    return false;
  }
  return value.claims.every(
    (claim) =>
      isRecord(claim) &&
      isNonEmptyString(claim.claim_id) &&
      isNonEmptyString(claim.claim_type) &&
      [
        "DETERMINATE",
        "CONDITIONALLY_DETERMINATE",
        "MULTIPLE_PLAUSIBLE_GRAPHS",
        "INSUFFICIENT_INFORMATION",
        "CONFLICTING_INFORMATION",
        "INVALID_GRAPH",
        "OUT_OF_SCOPE",
      ].includes(String(claim.determinability_state)) &&
      isKnowledgeValue(claim.value) &&
      isRecord(claim.support_grade) &&
      isNonEmptyString(claim.support_grade.token) &&
      isNonEmptyString(claim.support_grade.vocabulary_id) &&
      isStringArray(claim.required_predicates) &&
      Array.isArray(claim.irrelevant_predicates) &&
      claim.irrelevant_predicates.every(
        (predicate) =>
          isRecord(predicate) &&
          isNonEmptyString(predicate.id) &&
          isNonEmptyString(predicate.rationale),
      ) &&
      isStringArray(claim.assumptions) &&
      Array.isArray(claim.proof_trace) &&
      claim.proof_trace.length > 0 &&
      claim.proof_trace.every(
        (step) =>
          isRecord(step) &&
          typeof step.step_id === "string" &&
          typeof step.theory_clause_id === "string" &&
          typeof step.rule_id === "string" &&
          Array.isArray(step.predicate_references) &&
          step.predicate_references.every(
            (reference) =>
              isRecord(reference) &&
              isNonEmptyString(reference.predicate_id) &&
              isKnowledgeValue(reference.predicate_value),
          ) &&
          Array.isArray(step.input_record_references),
      ),
  );
}

function isProfileCoverage(value: unknown): boolean {
  return (
    isRecord(value) &&
    isNonEmptyString(value.profile_id) &&
    isNonEmptyString(value.statement_id) &&
    isNonEmptyString(value.predicate_closure_argument_id) &&
    isStringArray(value.covered_predicate_ids) &&
    isStringArray(value.known_gap_ids) &&
    isRecord(value.contract_review) &&
    isNonEmptyString(value.contract_review.issue_id) &&
    isNonEmptyString(value.contract_review.status) &&
    isNonEmptyString(value.contract_review.rationale)
  );
}

function isScenarioCoverage(value: unknown): boolean {
  return (
    isRecord(value) &&
    isNonEmptyString(value.status) &&
    isNonEmptyString(value.profile_id) &&
    isStringArray(value.emitting_clause_ids) &&
    isKnowledgeValue(value.omitted_dimensions) &&
    isKnowledgeValue(value.caveat)
  );
}

function isAdequacyEvaluation(value: unknown): boolean {
  return (
    isRecord(value) &&
    isNonEmptyString(value.evaluation_id) &&
    isNonEmptyString(value.inferential_query_id) &&
    isNonEmptyString(value.axis) &&
    isKnowledgeValue(value.outcome) &&
    isNonEmptyString(value.rationale)
  );
}

function isReportQuestion(value: unknown): boolean {
  return (
    isRecord(value) &&
    isNonEmptyString(value.question_id) &&
    isNonEmptyString(value.inferential_query_id) &&
    isNonEmptyString(value.text) &&
    isStringArray(value.evidence_required) &&
    typeof value.primary === "boolean"
  );
}

function isStatisticalHandoff(value: unknown): boolean {
  return (
    isRecord(value) &&
    value.strategy_module_status === "HANDOFF_ONLY" &&
    Array.isArray(value.items) &&
    value.items.every(
      (item) =>
        isRecord(item) &&
        ["STRUCTURAL_CONSTRAINT", "UNRESOLVED_QUESTION"].includes(String(item.category)) &&
        isNonEmptyString(item.origin) &&
        isNonEmptyString(item.authority) &&
        isNonEmptyString(item.inferential_query_id) &&
        isStringArray(item.evidence_refs) &&
        isStringArray(item.predicate_ids) &&
        isStringArray(item.question_ids),
    )
  );
}

function isDesignRecordContext(value: unknown): boolean {
  return (
    isRecord(value) &&
    isNonEmptyString(value.mode) &&
    isKnowledgeValue(value.planned_design_record) &&
    isKnowledgeValue(value.executed_design_record) &&
    isKnowledgeValue(value.reconciliation_record)
  );
}

function isConfirmedGraph(value: unknown): boolean {
  return (
    isRecord(value) &&
    Array.isArray(value.nodes) &&
    value.nodes.every(
      (node) =>
        isRecord(node) &&
        isNonEmptyString(node.node_id) &&
        isNonEmptyString(node.node_type),
    ) &&
    Array.isArray(value.relations)
  );
}

function isExecutionManifest(value: unknown): boolean {
  return (
    isRecord(value) &&
    isNonEmptyString(value.manifest_id) &&
    isNonEmptyString(value.theory_id) &&
    isNonEmptyString(value.theory_version) &&
    isNonEmptyString(value.theory_checksum) &&
    isNonEmptyString(value.rulebook_id) &&
    isNonEmptyString(value.rulebook_version) &&
    isNonEmptyString(value.rulebook_checksum) &&
    isStringArray(value.release_blocker_issue_ids)
  );
}

function isCanonicalQuickDesignResponse(value: unknown): value is QuickDesignV8Response {
  if (
    !isRecord(value) ||
    !isRecord(value.contract) ||
    !isRecord(value.report) ||
    !isRecord(value.planned_design) ||
    typeof value.planned_design.plan_id !== "string" ||
    !hasExactArtifacts(value.artifacts)
  ) {
    return false;
  }
  const report = value.report;
  const countRegistry = report.count_registry;
  const querySections = report.query_sections;
  const claimSets = report.claim_sets;
  const sourceRecords = report.source_records;
  const evidenceRecords = report.evidence_records;
  const sourceIds = Array.isArray(sourceRecords)
    ? new Set(
        sourceRecords.flatMap((source) =>
          isRecord(source) && isNonEmptyString(source.source_id) ? [source.source_id] : [],
        ),
      )
    : new Set<string>();
  return (
    value.contract.code === "PRD_V8" &&
    value.contract.version === "8.0.0" &&
    value.contract.strategy_module_status === "HANDOFF_ONLY" &&
    typeof report.report_id === "string" &&
    typeof report.content_checksum === "string" &&
    isNonEmptyString(report.epistemic_boundary) &&
    isDesignRecordContext(report.design_record_context) &&
    isRecord(report.report_resolution) &&
    isKnowledgeValue(report.report_resolution.resolution) &&
    report.strategy_module_status === "HANDOFF_ONLY" &&
    Array.isArray(querySections) &&
    querySections.length > 0 &&
    querySections.every((section) => {
      if (
        !isRecord(section) ||
        !isRecord(section.inferential_query) ||
        !isNonEmptyString(section.inferential_query.id) ||
        !isNonEmptyString(section.inferential_query.profile_id) ||
        !isClaimSet(section.claim_set)
      ) {
        return false;
      }
      const queryId = section.inferential_query.id;
      const claimSet = section.claim_set as JsonRecord & {
        inferential_query_id: string;
        claims: unknown[];
      };
      return (
        claimSet.inferential_query_id === queryId &&
        claimSet.claims.every(
          (claim) => isRecord(claim) && claim.inferential_query_id === queryId,
        ) &&
        Array.isArray(section.adequacy_evaluations) &&
        section.adequacy_evaluations.every(
          (evaluation) =>
            isRecord(evaluation) &&
            isAdequacyEvaluation(evaluation) &&
            evaluation.inferential_query_id === queryId,
        ) &&
        isStringArray(section.count_record_ids) &&
        Array.isArray(section.scenario_coverages) &&
        section.scenario_coverages.every(isScenarioCoverage) &&
        isProfileCoverage(section.profile_coverage) &&
        isKnowledgeValue(section.ai_candidates) &&
        isKnowledgeValue(section.human_confirmations) &&
        isKnowledgeValue(section.conflicts) &&
        isKnowledgeValue(section.sensitivities) &&
        Array.isArray(section.questions) &&
        section.questions.every(
          (question) =>
            isRecord(question) &&
            isReportQuestion(question) &&
            question.inferential_query_id === queryId,
        )
      );
    }) &&
    Array.isArray(claimSets) &&
    claimSets.length === querySections.length &&
    claimSets.every(
      (claimSet, index) =>
        isClaimSet(claimSet) &&
        JSON.stringify(claimSet) === JSON.stringify(querySections[index].claim_set),
    ) &&
    Array.isArray(sourceRecords) &&
    sourceRecords.length > 0 &&
    sourceIds.size === sourceRecords.length &&
    sourceRecords.every(
      (source) =>
        isRecord(source) &&
        typeof source.source_id === "string" &&
        typeof source.source_version === "string" &&
        typeof source.source_context === "string" &&
        isRecord(source.source_class),
    ) &&
    Array.isArray(evidenceRecords) &&
    evidenceRecords.length > 0 &&
    evidenceRecords.every(
      (evidence) =>
        isRecord(evidence) &&
        typeof evidence.evidence_id === "string" &&
        sourceIds.has(String(evidence.source_id)) &&
        typeof evidence.locator === "string" &&
        typeof evidence.original_text === "string",
    ) &&
    Array.isArray(report.design_adequacy_evaluations) &&
    report.design_adequacy_evaluations.every(isAdequacyEvaluation) &&
    Array.isArray(report.scenario_coverages) &&
    report.scenario_coverages.every(isScenarioCoverage) &&
    isProfileCoverage(report.profile_coverage) &&
    Array.isArray(report.questions) &&
    report.questions.every(isReportQuestion) &&
    isKnowledgeValue(report.sensitivities) &&
    isKnowledgeValue(report.human_confirmations) &&
    isKnowledgeValue(report.conflicts) &&
    isStatisticalHandoff(report.statistical_handoff) &&
    isStringArray(report.inference_limits) &&
    report.inference_limits.length > 0 &&
    Array.isArray(report.ai_candidates) &&
    report.ai_candidates.every(isKnowledgeValue) &&
    isConfirmedGraph(report.confirmed_graph) &&
    isExecutionManifest(report.execution_manifest) &&
    isRecord(countRegistry) &&
    isNonEmptyString(countRegistry.registry_version) &&
    Array.isArray(countRegistry.records) &&
    countRegistry.records.every(
      (record) =>
        isRecord(record) &&
        isNonEmptyString(record.count_id) &&
        isNonEmptyString(record.kind) &&
        isNonEmptyString(record.quantifier) &&
        isNonEmptyString(record.origin) &&
        isKnowledgeValue(record.value) &&
        isRecord(record.scope) &&
        isNonEmptyString(record.scope.query_id) &&
        isStringArray(record.rule_trace),
    )
  );
}

function normalizedAuditDraft(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(normalizedAuditDraft);
  if (!isRecord(value)) return value;
  return Object.fromEntries(
    Object.keys(value)
      .filter((key) => key !== "schema_version" || value[key] !== "8.0.0")
      .sort()
      .map((key) => [key, normalizedAuditDraft(value[key])]),
  );
}

function isGuidedBuildResponse(
  value: unknown,
  expectedDraft: GuidedQuickDesignBuildRequest["draft"],
): value is GuidedQuickDesignBuildResponse {
  if (
    !isRecord(value) ||
    value.schema_version !== "8.0.0" ||
    value.contract_code !== "NTRUTH_QUICK_DESIGN_GUIDED_V8" ||
    value.contract_version !== "8.0.0" ||
    "next_endpoint" in value ||
    value.submission_is_execution_capability !== false ||
    typeof value.preview_checksum !== "string" ||
    !/^[0-9a-f]{64}$/.test(value.preview_checksum) ||
    !isRecord(value.summary) ||
    !isNonEmptyString(value.summary.experiment_block_id) ||
    !isNonEmptyString(value.summary.inferential_query_id) ||
    !isStringArray(value.summary.provided_field_ids) ||
    !isStringArray(value.summary.unknown_field_ids) ||
    !isStringArray(value.summary.known_profile_gaps) ||
    value.summary.known_profile_gaps.length === 0 ||
    typeof value.summary.planned_group_count !== "number" ||
    typeof value.summary.planned_unit_total !== "number" ||
    value.summary.scenario_coverage_status !== "NON_EXHAUSTIVE" ||
    value.summary.strategy_module_status !== "HANDOFF_ONLY" ||
    !Array.isArray(value.visible_questions) ||
    value.visible_questions.length > 3 ||
    !Array.isArray(value.question_queue) ||
    value.question_queue.length < value.visible_questions.length ||
    !hasExactArtifacts(value.artifact_previews) ||
    !isRecord(value.review_snapshot) ||
    value.review_snapshot.schema_version !== "8.0.0" ||
    !isRecord(value.review_snapshot.draft) ||
    !isRecord(value.review_snapshot.conformance_bundle_payload) ||
    Object.keys(value.review_snapshot.conformance_bundle_payload).length === 0 ||
    value.review_snapshot.is_execution_capability !== false ||
    JSON.stringify(normalizedAuditDraft(value.review_snapshot.draft)) !==
      JSON.stringify(normalizedAuditDraft(expectedDraft)) ||
    !isKnowledgeValue(value.submission_audit_snapshot) ||
    !isKnowledgeValue(value.canonical_result) ||
    !isKnowledgeValue(value.confirmed_snapshot_checksum)
  ) {
    return false;
  }
  const validQuestions = value.question_queue.every(
    (question) =>
      isRecord(question) &&
      typeof question.question_id === "string" &&
      typeof question.predicate_id === "string" &&
      isStringArray(question.theory_clause_ids) &&
      isStringArray(question.required_predicate_rationales) &&
      isStringArray(question.known_gap_rationales) &&
      typeof question.text === "string" &&
      question.priority_state === "UNREVIEWED" &&
      isRecord(question.priority_review) &&
      isNonEmptyString(question.priority_review.issue_id) &&
      question.priority_review.status === "SCIENTIFIC_REVIEW_REQUIRED" &&
      isNonEmptyString(question.priority_review.rationale) &&
      isKnowledgeValue(question.evidence_required),
  );
  const visibleIds = value.visible_questions.map((question) =>
    isRecord(question) ? question.question_id : undefined,
  );
  const prefixIds = value.question_queue
    .slice(0, value.visible_questions.length)
    .map((question) => (isRecord(question) ? question.question_id : undefined));
  const questionIds = value.question_queue.map((question) =>
    isRecord(question) ? question.question_id : undefined,
  );
  const predicateIds = value.question_queue.map((question) =>
    isRecord(question) ? question.predicate_id : undefined,
  );
  if (
    !validQuestions ||
    new Set(questionIds).size !== questionIds.length ||
    new Set(predicateIds).size !== predicateIds.length ||
    JSON.stringify(visibleIds) !== JSON.stringify(prefixIds)
  ) {
    return false;
  }
  if (value.action === "PREVIEW") {
    return (
      value.state === "REVIEW_REQUIRED" &&
      value.submission_audit_snapshot.knowledge_state === "UNKNOWN" &&
      value.submission_audit_snapshot.value == null &&
      value.canonical_result.knowledge_state === "UNKNOWN" &&
      value.canonical_result.value == null &&
      value.confirmed_snapshot_checksum.knowledge_state === "UNKNOWN" &&
      value.confirmed_snapshot_checksum.value == null
    );
  }
  return (
    value.action === "CONFIRM" &&
    value.state === "BUILT" &&
    value.submission_audit_snapshot.knowledge_state === "PRESENT" &&
    isQuickDesignSubmission(value.submission_audit_snapshot.value) &&
    value.canonical_result.knowledge_state === "PRESENT" &&
    isCanonicalQuickDesignResponse(value.canonical_result.value) &&
    value.confirmed_snapshot_checksum.knowledge_state === "PRESENT" &&
    typeof value.confirmed_snapshot_checksum.value === "string" &&
    /^[0-9a-f]{64}$/.test(value.confirmed_snapshot_checksum.value) &&
    JSON.stringify(value.artifact_previews) ===
      JSON.stringify(value.canonical_result.value.artifacts)
  );
}

function sanitizeLegacyValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sanitizeLegacyValue);
  if (!isRecord(value)) return value === "ready_for_review" ? "review_required" : value;
  return Object.fromEntries(
    Object.entries(value)
      .filter(
        ([field]) =>
          ![
            "candidate_analysis_strategies",
            "determinability",
            "design_adequacy",
            "statistical_handoff",
            "strategy_module_status",
          ].includes(field),
      )
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
    determinability: {
      state: "INSUFFICIENT_INFORMATION",
      rationale:
        "The v7 adapter does not provide claim-specific PRD v8 determinability.",
    },
    design_adequacy: {
      knowledge_state: "UNKNOWN",
      finding: "NOT_ASSESSED",
      rationale:
        "The historical output does not authorize a PRD v8 design-adequacy evaluation.",
    },
    strategy_module_status: "HANDOFF_ONLY",
    statistical_handoff: {
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
  endpoint: "/v8/quick-design" = "/v8/quick-design",
): Promise<QuickDesignV8Response> {
  const result = await request<unknown>(endpoint, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  if (!isCanonicalQuickDesignResponse(result)) {
    throw new Error("The canonical endpoint returned a malformed PRD_V8 ReportBundle.");
  }
  return result;
}

export async function buildQuickDesignSubmission(
  payload: GuidedQuickDesignBuildRequest,
): Promise<GuidedQuickDesignBuildResponse> {
  const result = await request<unknown>("/v8/quick-design/build-submission", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  if (!isGuidedBuildResponse(result, payload.draft)) {
    throw new Error("The guided endpoint returned a malformed PRD v8 build response.");
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
