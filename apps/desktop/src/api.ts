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
  QuickDesignV8ResultWire,
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

function isSha256(value: unknown): value is string {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}

function hasV8Schema(value: unknown): value is JsonRecord {
  return isRecord(value) && value.schema_version === "8.0.0";
}

function hasUniqueStrings(value: unknown, minimum = 0): value is string[] {
  return (
    isStringArray(value) &&
    value.length >= minimum &&
    value.every(isNonEmptyString) &&
    new Set(value).size === value.length
  );
}

function isUnambiguousScientificPayload(value: unknown): boolean {
  if (value === null || value === undefined) return false;
  if (typeof value === "string") return isNonEmptyString(value);
  if (Array.isArray(value)) return value.length > 0;
  if (isRecord(value)) return Object.keys(value).length > 0;
  return typeof value === "number" || typeof value === "boolean";
}

function isKnowledgeValue(value: unknown): value is KnowledgeValue {
  if (
    !hasV8Schema(value) ||
    typeof value.knowledge_state !== "string" ||
    !Array.isArray(value.conflicting_values) ||
    !hasUniqueStrings(value.evidence_ids) ||
    !hasUniqueStrings(value.source_scope_ids) ||
    !(value.rationale === null || value.rationale === undefined || isNonEmptyString(value.rationale)) ||
    !(value.claim_scope_id === null || value.claim_scope_id === undefined || isNonEmptyString(value.claim_scope_id)) ||
    !(value.query_scope_id === null || value.query_scope_id === undefined || isNonEmptyString(value.query_scope_id))
  ) {
    return false;
  }
  const state = value.knowledge_state;
  const noSelectedValue = value.value === null || value.value === undefined;
  if (state === "PRESENT") {
    return (
      isUnambiguousScientificPayload(value.value) &&
      value.evidence_ids.length > 0 &&
      value.conflicting_values.length === 0
    );
  }
  if (state === "CONFLICTING") {
    const alternatives = value.conflicting_values.map((item) => pythonJson(item));
    return (
      noSelectedValue &&
      alternatives.length >= 2 &&
      new Set(alternatives).size === alternatives.length &&
      value.conflicting_values.every(isUnambiguousScientificPayload) &&
      value.evidence_ids.length > 0
    );
  }
  if (
    ![
      "ABSENT_EXPLICIT",
      "NOT_REPORTED",
      "UNKNOWN",
      "NOT_APPLICABLE",
    ].includes(state) ||
    !noSelectedValue ||
    value.conflicting_values.length > 0
  ) {
    return false;
  }
  if (state === "ABSENT_EXPLICIT") return value.evidence_ids.length > 0;
  if (state === "NOT_REPORTED") return value.source_scope_ids.length > 0;
  return (
    isNonEmptyString(value.rationale) &&
    (isNonEmptyString(value.claim_scope_id) || isNonEmptyString(value.query_scope_id))
  );
}

function isArtifactShape(value: unknown): value is ProspectiveArtifactV8 {
  return (
    hasV8Schema(value) &&
    isNonEmptyString(value.artifact_id) &&
    ["SAMPLE_SHEET", "METHODS_DRAFT", "ID_CONVENTION"].includes(String(value.kind)) &&
    isNonEmptyString(value.media_type) &&
    isNonEmptyString(value.content) &&
    isSha256(value.content_checksum) &&
    value.artifact_id === `ARTIFACT-${String(value.kind)}-${value.content_checksum.slice(0, 20)}`
  );
}

function hasExactArtifactShapes(value: unknown): value is ProspectiveArtifactV8[] {
  if (!Array.isArray(value) || value.length !== 3 || !value.every(isArtifactShape)) {
    return false;
  }
  return new Set(value.map((item) => item.kind)).size === 3;
}

function canonicalJson(
  value: unknown,
  itemSeparator: string,
  keySeparator: string,
): string {
  if (value === null) return "null";
  if (typeof value === "string" || typeof value === "boolean") {
    return JSON.stringify(value);
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new Error("non-finite JSON number");
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalJson(item, itemSeparator, keySeparator)).join(itemSeparator)}]`;
  }
  if (isRecord(value)) {
    return `{${Object.keys(value)
      .sort()
      .map(
        (key) =>
          `${JSON.stringify(key)}${keySeparator}${canonicalJson(value[key], itemSeparator, keySeparator)}`,
      )
      .join(itemSeparator)}}`;
  }
  throw new Error("value is not JSON serializable");
}

function pythonJson(value: unknown): string {
  return canonicalJson(value, ", ", ": ");
}

function compactCanonicalJson(value: unknown): string {
  return canonicalJson(value, ",", ":");
}

async function sha256(value: string): Promise<string | undefined> {
  try {
    if (!globalThis.crypto?.subtle) return undefined;
    const digest = await globalThis.crypto.subtle.digest(
      "SHA-256",
      new TextEncoder().encode(value),
    );
    return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
  } catch {
    return undefined;
  }
}

async function contentChecksum(value: unknown): Promise<string | undefined> {
  try {
    return await sha256(pythonJson(value));
  } catch {
    return undefined;
  }
}

async function stableId(prefix: string, ...parts: string[]): Promise<string | undefined> {
  const digest = await contentChecksum(parts);
  return digest === undefined ? undefined : `${prefix}-${digest.slice(0, 12)}`;
}

async function compactChecksum(value: unknown): Promise<string | undefined> {
  try {
    return await sha256(compactCanonicalJson(value));
  } catch {
    return undefined;
  }
}

async function hasExactArtifacts(value: unknown): Promise<boolean> {
  if (!hasExactArtifactShapes(value)) return false;
  const checksums = await Promise.all(value.map((artifact) => contentChecksum(artifact.content)));
  return checksums.every((checksum, index) => checksum === value[index].content_checksum);
}

function hasExactKeys(
  value: JsonRecord,
  required: readonly string[],
  optional: readonly string[] = [],
): boolean {
  const allowed = new Set([...required, ...optional]);
  return (
    required.every((key) => key in value) &&
    Object.keys(value).every((key) => allowed.has(key))
  );
}

const REVIEWED_CONFORMANCE_ASSET_PINS = {
  theory: "aa37639893e2ba7732496f2eb6a121291e0aad2d3bae51501c8f1ea9e9b6464f",
  rulebook: "a82a49f841f3c996497a9ea610fd13ee7926cec3f428c5cda9d3f627c0f5f19b",
  profile_closure: "1080f48e37b719351554c406d85e8cce7c2106f9f01ee5b8168413f57a747698",
  reference_registry: "7e573af256a1365ca0e3892786f80a6a8f62710ce0e4dc39d1dfef24d2089db3",
  fixture_set: "f7a9b4c0a009fcbf1ae4c7a2bb3b15d8392225cb6e040ec17e2187cb396918e6",
  evaluator_registry: "a7b249bd32e508a3d97287c14b0a40e9973f1163b03b473805dcce02f5326b98",
} as const;

const REVIEWED_CONFORMANCE_BUNDLE_CHECKSUM =
  "439ef54a000c78b290eea0e8e390108de3e853b1a84bb4ee9d8529f80168a7bb";

function isConformanceBundle(value: unknown): value is JsonRecord {
  if (
    !isRecord(value) ||
    !hasExactKeys(value, Object.keys(REVIEWED_CONFORMANCE_ASSET_PINS))
  ) {
    return false;
  }
  return Object.entries(REVIEWED_CONFORMANCE_ASSET_PINS).every(
    ([name, checksum]) =>
      hasV8Schema(value[name]) && value[name].declared_checksum === checksum,
  );
}

async function hasValidConformanceAssetChecksums(value: unknown): Promise<boolean> {
  if (!isConformanceBundle(value)) return false;
  const assets = [
    value.theory,
    value.rulebook,
    value.profile_closure,
    value.reference_registry,
    value.fixture_set,
    value.evaluator_registry,
  ] as JsonRecord[];
  const computed = await Promise.all(
    assets.map((asset) => {
      const { declared_checksum: _declared, ...payload } = asset;
      return compactChecksum(payload);
    }),
  );
  return computed.every((checksum, index) => checksum === assets[index].declared_checksum);
}

function isGuidedTextAnswer(value: unknown): boolean {
  if (!isRecord(value) || !hasExactKeys(value, ["status"], ["schema_version", "value", "rationale"])) {
    return false;
  }
  if (value.schema_version !== undefined && value.schema_version !== "8.0.0") return false;
  if (value.status === "PROVIDED") {
    return isNonEmptyString(value.value) && (value.rationale === undefined || value.rationale === null);
  }
  return (
    value.status === "NOT_AVAILABLE" &&
    isNonEmptyString(value.rationale) &&
    (value.value === undefined || value.value === null)
  );
}

function isGuidedIdSetAnswer(value: unknown): boolean {
  if (!isRecord(value) || !hasExactKeys(value, ["status"], ["schema_version", "values", "rationale"])) {
    return false;
  }
  if (value.schema_version !== undefined && value.schema_version !== "8.0.0") return false;
  if (value.status === "PROVIDED") {
    return hasUniqueStrings(value.values, 1) && (value.rationale === undefined || value.rationale === null);
  }
  return (
    value.status === "NOT_AVAILABLE" &&
    isNonEmptyString(value.rationale) &&
    (value.values === undefined || (Array.isArray(value.values) && value.values.length === 0))
  );
}

function isGuidedDraft(value: unknown): boolean {
  if (!isRecord(value)) return false;
  const fields = [
    "template_id",
    "block_title",
    "source_description",
    "preparation_description",
    "biological_source_unit_type",
    "candidate_unit_type",
    "factor_id",
    "factor_levels",
    "contrast_id",
    "endpoint_id",
    "timepoint_id",
    "estimand",
    "population_scope",
    "inference_level",
    "assignment_unit_type",
    "assignment_unit_ids",
    "application_unit_type",
    "application_unit_ids",
    "intervention_id",
    "effective_exposure_unit_type",
    "exposed_unit_ids",
    "exposure_pathway",
    "exposure_container",
    "interference",
    "assignment_to_application_timing",
    "planned_unit_type",
    "planned_groups",
  ] as const;
  if (!hasExactKeys(value, fields, ["schema_version"])) return false;
  if (value.schema_version !== undefined && value.schema_version !== "8.0.0") return false;
  const textAnswers = [
    value.source_description,
    value.preparation_description,
    value.biological_source_unit_type,
    value.candidate_unit_type,
    value.assignment_unit_type,
    value.application_unit_type,
    value.intervention_id,
    value.effective_exposure_unit_type,
    value.exposure_pathway,
    value.exposure_container,
    value.planned_unit_type,
  ];
  const idAnswers = [value.assignment_unit_ids, value.application_unit_ids, value.exposed_unit_ids];
  const scalarFields = [
    value.block_title,
    value.factor_id,
    value.contrast_id,
    value.endpoint_id,
    value.timepoint_id,
    value.estimand,
    value.population_scope,
    value.inference_level,
  ];
  if (
    value.template_id !== "simple_cell_culture" ||
    !scalarFields.every(isNonEmptyString) ||
    !textAnswers.every(isGuidedTextAnswer) ||
    !idAnswers.every(isGuidedIdSetAnswer) ||
    !hasUniqueStrings(value.factor_levels, 2) ||
    new Set(value.factor_levels.map((item) => item.toLocaleLowerCase())).size !== value.factor_levels.length ||
    !isRecord(value.interference) ||
    !hasExactKeys(value.interference, ["status", "rationale"], ["schema_version"]) ||
    !["UNKNOWN", "POSSIBLE"].includes(String(value.interference.status)) ||
    !isNonEmptyString(value.interference.rationale) ||
    !isRecord(value.assignment_to_application_timing) ||
    !hasExactKeys(
      value.assignment_to_application_timing,
      ["status"],
      ["schema_version", "relation", "rationale"],
    ) ||
    !Array.isArray(value.planned_groups) ||
    value.planned_groups.length < 2
  ) {
    return false;
  }
  const timing = value.assignment_to_application_timing;
  if (
    timing.schema_version !== undefined && timing.schema_version !== "8.0.0" ||
    (timing.status === "PROVIDED"
      ? !["BEFORE", "AFTER", "SAME_EVENT", "OVERLAPS"].includes(String(timing.relation)) ||
        !(timing.rationale === undefined || timing.rationale === null)
      : timing.status !== "NOT_AVAILABLE" ||
        !isNonEmptyString(timing.rationale) ||
        !(timing.relation === undefined || timing.relation === null))
  ) {
    return false;
  }
  const groups = value.planned_groups;
  if (
    !groups.every(
      (group) =>
        isRecord(group) &&
        hasExactKeys(
          group,
          ["group_id", "cohort_id", "factor_level", "planned_count"],
          ["schema_version"],
        ) &&
        (group.schema_version === undefined || group.schema_version === "8.0.0") &&
        isNonEmptyString(group.group_id) &&
        isGuidedTextAnswer(group.cohort_id) &&
        isNonEmptyString(group.factor_level) &&
        Number.isInteger(group.planned_count) &&
        Number(group.planned_count) >= 1 &&
        Number(group.planned_count) <= 100_000,
    )
  ) {
    return false;
  }
  const groupIds = groups.map((group) => (group as JsonRecord).group_id);
  const groupLevels = groups.map((group) =>
    String((group as JsonRecord).factor_level).toLocaleLowerCase(),
  );
  const factorLevels = value.factor_levels.map((item) => item.toLocaleLowerCase());
  return (
    new Set(groupIds).size === groupIds.length &&
    new Set(groupLevels).size === groupLevels.length &&
    groupLevels.length === factorLevels.length &&
    groupLevels.every((level) => factorLevels.includes(level)) &&
    groups.reduce((total, group) => total + Number((group as JsonRecord).planned_count), 0) <=
      100_000
  );
}

function isGuidedQuestion(value: unknown): boolean {
  return (
    hasV8Schema(value) &&
    isNonEmptyString(value.question_id) &&
    isNonEmptyString(value.predicate_id) &&
    hasUniqueStrings(value.theory_clause_ids, 1) &&
    Array.isArray(value.required_predicate_rationales) &&
    value.required_predicate_rationales.length > 0 &&
    value.required_predicate_rationales.every(isNonEmptyString) &&
    Array.isArray(value.known_gap_rationales) &&
    value.known_gap_rationales.every(isNonEmptyString) &&
    isNonEmptyString(value.text) &&
    value.priority_state === "UNREVIEWED" &&
    hasV8Schema(value.priority_review) &&
    isNonEmptyString(value.priority_review.issue_id) &&
    value.priority_review.status === "SCIENTIFIC_REVIEW_REQUIRED" &&
    isNonEmptyString(value.priority_review.rationale) &&
    isKnowledgeValue(value.evidence_required)
  );
}

function isSortedUniqueStringArray(value: unknown): value is string[] {
  return (
    hasUniqueStrings(value) &&
    pythonJson(value) === pythonJson([...value].sort())
  );
}

async function hasCanonicalGuidedPreviewProjection(value: JsonRecord): Promise<boolean> {
  if (
    !isRecord(value.review_snapshot) ||
    !isGuidedDraft(value.review_snapshot.draft) ||
    !isConformanceBundle(value.review_snapshot.conformance_bundle_payload) ||
    !hasV8Schema(value.summary) ||
    !Array.isArray(value.question_queue) ||
    !Array.isArray(value.artifact_previews)
  ) {
    return false;
  }
  const draft = value.review_snapshot.draft;
  const bundle = value.review_snapshot.conformance_bundle_payload;
  const summary = value.summary;
  const profileClosure = bundle.profile_closure;
  const theory = bundle.theory;
  const providedFields = summary.provided_field_ids;
  const unknownFields = summary.unknown_field_ids;
  if (
    !isRecord(profileClosure) ||
    !isRecord(theory) ||
    !hasUniqueStrings(profileClosure.known_gaps, 1) ||
    !isSortedUniqueStringArray(providedFields) ||
    !isSortedUniqueStringArray(unknownFields) ||
    providedFields.some((field) => unknownFields.includes(field))
  ) {
    return false;
  }
  const canonicalDraft = draft as JsonRecord;
  const groups = canonicalDraft.planned_groups as JsonRecord[];
  const blockId = await stableId(
    "BLOCK-QD",
    String(canonicalDraft.template_id),
    String(canonicalDraft.block_title),
  );
  const queryId =
    blockId === undefined
      ? undefined
      : await stableId(
          "IQ-QD",
          blockId,
          String(canonicalDraft.factor_id),
          String(canonicalDraft.contrast_id),
          String(canonicalDraft.endpoint_id),
          String(canonicalDraft.timepoint_id),
          String(canonicalDraft.estimand),
          String(canonicalDraft.population_scope),
          String(canonicalDraft.inference_level),
        );
  if (
    blockId === undefined ||
    queryId === undefined ||
    summary.experiment_block_id !== blockId ||
    summary.inferential_query_id !== queryId ||
    summary.planned_group_count !== groups.length ||
    summary.planned_unit_total !==
      groups.reduce((total, group) => total + Number(group.planned_count), 0) ||
    pythonJson(summary.known_profile_gaps) !== pythonJson(profileClosure.known_gaps)
  ) {
    return false;
  }
  const checksum = await contentChecksum({
    draft: canonicalDraft,
    theory_checksum: theory.declared_checksum,
    questions: value.question_queue,
    artifacts: (value.artifact_previews as JsonRecord[]).map(
      (artifact) => artifact.content_checksum,
    ),
    summary,
  });
  return checksum !== undefined && value.preview_checksum === checksum;
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
    hasV8Schema(value) &&
    isNonEmptyString(value.manifest_id) &&
    isNonEmptyString(value.theory_id) &&
    isNonEmptyString(value.theory_version) &&
    isSha256(value.theory_checksum) &&
    isNonEmptyString(value.rulebook_id) &&
    isNonEmptyString(value.rulebook_version) &&
    isSha256(value.rulebook_checksum) &&
    isNonEmptyString(value.profile_closure_asset_id) &&
    isNonEmptyString(value.profile_closure_asset_version) &&
    isSha256(value.profile_closure_checksum) &&
    isNonEmptyString(value.reference_registry_id) &&
    isNonEmptyString(value.reference_registry_version) &&
    isSha256(value.reference_registry_checksum) &&
    isNonEmptyString(value.fixture_set_id) &&
    isNonEmptyString(value.fixture_set_version) &&
    isSha256(value.fixture_set_checksum) &&
    isNonEmptyString(value.evaluator_registry_id) &&
    isNonEmptyString(value.evaluator_registry_version) &&
    isSha256(value.evaluator_registry_checksum) &&
    Array.isArray(value.implementation_rules) &&
    value.implementation_rules.length >= 7 &&
    value.implementation_rules.every(
      (pin) =>
        hasV8Schema(pin) &&
        isNonEmptyString(pin.theory_clause_id) &&
        isNonEmptyString(pin.rule_id) &&
        isSha256(pin.theory_checksum) &&
        isSha256(pin.rule_checksum) &&
        isSha256(pin.implementation_artifact_checksum),
    ) &&
    hasV8Schema(value.adequacy_evaluator) &&
    isNonEmptyString(value.adequacy_evaluator.theory_clause_id) &&
    isNonEmptyString(value.adequacy_evaluator.rule_id) &&
    isSha256(value.adequacy_evaluator.theory_checksum) &&
    isSha256(value.adequacy_evaluator.rule_checksum) &&
    isSha256(value.adequacy_evaluator.implementation_artifact_checksum) &&
    isStringArray(value.release_blocker_issue_ids)
  );
}

async function expectedExecutionManifest(
  bundle: JsonRecord,
): Promise<JsonRecord | undefined> {
  const theory = bundle.theory;
  const rulebook = bundle.rulebook;
  const profile = bundle.profile_closure;
  const referenceRegistry = bundle.reference_registry;
  const fixtureSet = bundle.fixture_set;
  const evaluatorRegistry = bundle.evaluator_registry;
  if (
    !isRecord(theory) ||
    !isRecord(rulebook) ||
    !isRecord(profile) ||
    !isRecord(referenceRegistry) ||
    !isRecord(fixtureSet) ||
    !isRecord(evaluatorRegistry) ||
    !Array.isArray(theory.clauses) ||
    !Array.isArray(rulebook.rules) ||
    rulebook.rules.length < 7 ||
    !Array.isArray(rulebook.scientific_review_requirements) ||
    !Array.isArray(referenceRegistry.slots) ||
    !Array.isArray(evaluatorRegistry.artifact_pins)
  ) {
    return undefined;
  }
  const clauses = theory.clauses.filter(isRecord);
  const evaluatorPins = evaluatorRegistry.artifact_pins.filter(isRecord);
  if (clauses.length !== theory.clauses.length || evaluatorPins.length < 8) {
    return undefined;
  }
  const implementationRules: JsonRecord[] = [];
  const ruleChecksums: string[] = [];
  const implementationChecksums: string[] = [];
  for (const item of rulebook.rules) {
    if (
      !isRecord(item) ||
      !isNonEmptyString(item.rule_id) ||
      !isNonEmptyString(item.rule_version) ||
      !isNonEmptyString(item.theory_clause_id) ||
      !isNonEmptyString(item.theory_clause_version) ||
      !Array.isArray(item.required_predicates) ||
      item.required_predicates.length < 1 ||
      !item.required_predicates.every(
        (predicate) => isRecord(predicate) && isNonEmptyString(predicate.predicate_id),
      ) ||
      !Array.isArray(item.irrelevant_predicates) ||
      item.irrelevant_predicates.length < 1
    ) {
      return undefined;
    }
    const clauseMatches = clauses.filter(
      (clause) => clause.clause_id === item.theory_clause_id,
    );
    const pinMatches = evaluatorPins.filter(
      (pin) =>
        pin.evaluator_kind === "DERIVATION" &&
        pin.theory_clause_id === item.theory_clause_id &&
        pin.rule_id === item.rule_id,
    );
    if (clauseMatches.length !== 1 || pinMatches.length !== 1) return undefined;
    const clause = clauseMatches[0];
    const pin = pinMatches[0];
    const ruleChecksum = await compactChecksum(item);
    if (
      ruleChecksum === undefined ||
      !isNonEmptyString(clause.clause_version) ||
      clause.clause_version !== item.theory_clause_version ||
      !isNonEmptyString(pin.artifact_id) ||
      !isNonEmptyString(pin.artifact_version) ||
      !isSha256(pin.implementation_source_digest)
    ) {
      return undefined;
    }
    ruleChecksums.push(ruleChecksum);
    implementationChecksums.push(pin.implementation_source_digest);
    implementationRules.push({
      schema_version: "8.0.0",
      theory_id: theory.theory_id,
      theory_version: theory.theory_version,
      theory_checksum: theory.declared_checksum,
      rule_id: item.rule_id,
      rule_version: item.rule_version,
      rule_checksum: ruleChecksum,
      theory_clause_id: item.theory_clause_id,
      theory_clause_version: item.theory_clause_version,
      implementation_artifact_id: pin.artifact_id,
      implementation_artifact_version: pin.artifact_version,
      implementation_artifact_checksum: pin.implementation_source_digest,
      required_predicate_ids: item.required_predicates.map(
        (predicate) => (predicate as JsonRecord).predicate_id,
      ),
      irrelevant_predicates: item.irrelevant_predicates,
    });
  }
  const adequacyRuleMatches = rulebook.rules.filter(
    (rule) =>
      isRecord(rule) && rule.theory_clause_id === "DT-E-INTERFERENCE-ESTIMAND",
  );
  const adequacyClauseMatches = clauses.filter(
    (clause) => clause.clause_id === "DT-E-INTERFERENCE-ESTIMAND",
  );
  const adequacyPinMatches = evaluatorPins.filter(
    (pin) =>
      pin.evaluator_kind === "ADEQUACY" &&
      pin.theory_clause_id === "DT-E-INTERFERENCE-ESTIMAND",
  );
  if (
    adequacyRuleMatches.length !== 1 ||
    adequacyClauseMatches.length !== 1 ||
    adequacyPinMatches.length !== 1
  ) {
    return undefined;
  }
  const adequacyRule = adequacyRuleMatches[0] as JsonRecord;
  const adequacyClause = adequacyClauseMatches[0];
  const adequacyPin = adequacyPinMatches[0];
  const adequacyRuleChecksum = await compactChecksum(adequacyRule);
  if (
    adequacyRuleChecksum === undefined ||
    !isNonEmptyString(adequacyClause.clause_version) ||
    !isNonEmptyString(adequacyPin.artifact_id) ||
    !isNonEmptyString(adequacyPin.artifact_version) ||
    !isSha256(adequacyPin.implementation_source_digest)
  ) {
    return undefined;
  }
  const adequacyEvaluator: JsonRecord = {
    schema_version: "8.0.0",
    theory_id: theory.theory_id,
    theory_version: theory.theory_version,
    theory_checksum: theory.declared_checksum,
    theory_clause_id: adequacyClause.clause_id,
    theory_clause_version: adequacyClause.clause_version,
    rule_id: adequacyRule.rule_id,
    rule_version: adequacyRule.rule_version,
    rule_checksum: adequacyRuleChecksum,
    implementation_artifact_id: adequacyPin.artifact_id,
    implementation_artifact_version: adequacyPin.artifact_version,
    implementation_artifact_checksum: adequacyPin.implementation_source_digest,
  };
  const blockerIds = new Set<string>();
  for (const review of rulebook.scientific_review_requirements) {
    if (!isRecord(review) || !isNonEmptyString(review.issue_id)) return undefined;
    blockerIds.add(review.issue_id);
  }
  if (
    !isRecord(profile.review_requirement) ||
    !isNonEmptyString(profile.review_requirement.issue_id)
  ) {
    return undefined;
  }
  blockerIds.add(profile.review_requirement.issue_id);
  for (const slot of referenceRegistry.slots) {
    if (!isRecord(slot)) return undefined;
    if (slot.availability === "SCIENTIFIC_REVIEW_REQUIRED") {
      if (
        !isRecord(slot.review_requirement) ||
        !isNonEmptyString(slot.review_requirement.issue_id)
      ) {
        return undefined;
      }
      blockerIds.add(slot.review_requirement.issue_id);
    }
  }
  for (const rule of rulebook.rules) {
    if (!isRecord(rule) || !isStringArray(rule.known_gap_issue_ids)) return undefined;
    for (const issueId of rule.known_gap_issue_ids) blockerIds.add(issueId);
  }
  const checksums = [
    theory.declared_checksum,
    rulebook.declared_checksum,
    profile.declared_checksum,
    referenceRegistry.declared_checksum,
    fixtureSet.declared_checksum,
    evaluatorRegistry.declared_checksum,
  ];
  if (!checksums.every(isSha256)) return undefined;
  const manifestId = await stableId(
    "v8-execution-manifest",
    ...checksums,
    ...ruleChecksums,
    ...implementationChecksums,
    adequacyPin.implementation_source_digest,
  );
  if (manifestId === undefined) return undefined;
  return {
    schema_version: "8.0.0",
    manifest_id: manifestId,
    theory_id: theory.theory_id,
    theory_version: theory.theory_version,
    theory_checksum: theory.declared_checksum,
    rulebook_id: rulebook.rulebook_id,
    rulebook_version: rulebook.rulebook_version,
    rulebook_checksum: rulebook.declared_checksum,
    profile_closure_asset_id: profile.asset_id,
    profile_closure_asset_version: profile.asset_version,
    profile_closure_checksum: profile.declared_checksum,
    reference_registry_id: referenceRegistry.registry_id,
    reference_registry_version: referenceRegistry.registry_version,
    reference_registry_checksum: referenceRegistry.declared_checksum,
    fixture_set_id: fixtureSet.fixture_set_id,
    fixture_set_version: fixtureSet.fixture_set_version,
    fixture_set_checksum: fixtureSet.declared_checksum,
    evaluator_registry_id: evaluatorRegistry.registry_id,
    evaluator_registry_version: evaluatorRegistry.registry_version,
    evaluator_registry_checksum: evaluatorRegistry.declared_checksum,
    implementation_rules: implementationRules,
    adequacy_evaluator: adequacyEvaluator,
    release_blocker_issue_ids: [...blockerIds].sort(),
  };
}

function isSourceRecord(value: unknown): boolean {
  return (
    hasV8Schema(value) &&
    isNonEmptyString(value.source_id) &&
    ["planned", "executed", "reconciled", "unverified_retrospective_statement"].includes(
      String(value.source_context),
    ) &&
    isNonEmptyString(value.source_version) &&
    hasV8Schema(value.source_class) &&
    value.source_class.registry_id === "ntruth-source-class-v8.0" &&
    isNonEmptyString(value.source_class.token) &&
    (value.source_class.token !== "UNKNOWN_WITH_REASON" ||
      isNonEmptyString(value.source_class.unknown_reason))
  );
}

function isEvidenceRecord(value: unknown, sourceIds: Set<string>): boolean {
  return (
    hasV8Schema(value) &&
    isNonEmptyString(value.evidence_id) &&
    isNonEmptyString(value.source_id) &&
    sourceIds.has(value.source_id) &&
    [
      "STRUCTURAL_FACT",
      "PROCEDURAL_EVENT",
      "AUTHOR_ASSERTION",
      "SAMPLE_METADATA_PLANNED",
      "SAMPLE_METADATA_EXECUTED",
      "INSTRUMENT_OR_EXECUTION_LOG",
      "IMAGE_METADATA",
      "STATISTICAL_CODE",
      "AUTHOR_CLARIFICATION",
      "USER_CONFIRMATION",
      "EXPERT_ADJUDICATION",
      "MODEL_INFERENCE",
      "RULE_DERIVATION",
      "CONFLICTING_EVIDENCE",
    ].includes(String(value.evidence_type)) &&
    isNonEmptyString(value.locator) &&
    isNonEmptyString(value.original_text)
  );
}

function isVerifiedPipelineContextShape(value: unknown): value is JsonRecord {
  return (
    hasV8Schema(value) &&
    isNonEmptyString(value.context_id) &&
    isSha256(value.content_checksum) &&
    value.context_id === `PIPELINE-CONTEXT-${value.content_checksum.slice(0, 20)}` &&
    isRecord(value.request_payload) &&
    isRecord(value.result_payload) &&
    isConformanceBundle(value.conformance_bundle_payload) &&
    isSha256(value.conformance_bundle_checksum)
  );
}

async function isVerifiedPipelineContext(value: unknown): Promise<boolean> {
  if (!isVerifiedPipelineContextShape(value)) return false;
  const { context_id: _contextId, content_checksum: _checksum, ...addressed } = value;
  const [contextChecksum, assetsValid] = await Promise.all([
    contentChecksum(addressed),
    hasValidConformanceAssetChecksums(value.conformance_bundle_payload),
  ]);
  return (
    assetsValid &&
    contextChecksum === value.content_checksum &&
    value.conformance_bundle_checksum === REVIEWED_CONFORMANCE_BUNDLE_CHECKSUM
  );
}

function isProspectiveInputLedgerShape(value: unknown): value is JsonRecord {
  if (
    !hasV8Schema(value) ||
    !isNonEmptyString(value.ledger_id) ||
    !isSha256(value.content_checksum) ||
    value.ledger_id !== `PROSPECTIVE-LEDGER-${value.content_checksum.slice(0, 20)}` ||
    !isRecord(value.request_payload) ||
    !isSha256(value.request_checksum) ||
    !Array.isArray(value.sources) ||
    value.sources.length < 1 ||
    !value.sources.every(isSourceRecord) ||
    !Array.isArray(value.evidence_records) ||
    value.evidence_records.length < 1 ||
    !Array.isArray(value.confirmation_events) ||
    !Array.isArray(value.support_bindings) ||
    value.support_bindings.length < 1 ||
    !value.support_bindings.every(isRecord) ||
    !hasExactArtifactShapes(value.artifacts)
  ) {
    return false;
  }
  const sourceIds = new Set(
    value.sources.map((source) => String((source as JsonRecord).source_id)),
  );
  const evidenceIds = value.evidence_records.map((record) =>
    isRecord(record) ? record.evidence_id : undefined,
  );
  return (
    sourceIds.size === value.sources.length &&
    evidenceIds.every(isNonEmptyString) &&
    new Set(evidenceIds).size === evidenceIds.length &&
    value.evidence_records.every((record) => isEvidenceRecord(record, sourceIds))
  );
}

async function isProspectiveInputLedger(value: unknown): Promise<boolean> {
  if (!isProspectiveInputLedgerShape(value)) return false;
  const { ledger_id: _ledgerId, content_checksum: _checksum, ...addressed } = value;
  const [requestChecksum, ledgerChecksum, artifactsValid] = await Promise.all([
    contentChecksum(value.request_payload),
    contentChecksum(addressed),
    hasExactArtifacts(value.artifacts),
  ]);
  return (
    artifactsValid &&
    requestChecksum === value.request_checksum &&
    ledgerChecksum === value.content_checksum
  );
}

async function hasCanonicalReportIntegrity(report: JsonRecord): Promise<boolean> {
  if (
    !Array.isArray(report.verified_pipeline_contexts) ||
    report.verified_pipeline_contexts.length < 1 ||
    !isKnowledgeValue(report.prospective_input_ledgers)
  ) {
    return false;
  }
  const contextsValid = await Promise.all(
    report.verified_pipeline_contexts.map(isVerifiedPipelineContext),
  );
  if (!contextsValid.every(Boolean)) return false;
  const contexts = report.verified_pipeline_contexts;
  const mode = isRecord(report.design_record_context)
    ? report.design_record_context.mode
    : undefined;
  if (mode === "UNVERIFIED_RETROSPECTIVE") {
    if (report.prospective_input_ledgers.knowledge_state !== "NOT_APPLICABLE") {
      return false;
    }
  } else {
    if (
      report.prospective_input_ledgers.knowledge_state !== "PRESENT" ||
      !Array.isArray(report.prospective_input_ledgers.value) ||
      report.prospective_input_ledgers.value.length !== contexts.length
    ) {
      return false;
    }
    const ledgers = report.prospective_input_ledgers.value;
    const ledgersValid = await Promise.all(ledgers.map(isProspectiveInputLedger));
    if (!ledgersValid.every(Boolean)) return false;
    if (
      !ledgers.every(
        (ledger, index) =>
          isRecord(ledger) &&
          isRecord(contexts[index]) &&
          pythonJson(ledger.request_payload) ===
            pythonJson((contexts[index] as JsonRecord).request_payload),
      )
    ) {
      return false;
    }
  }
  const { report_id: _reportId, content_checksum: _checksum, ...addressed } = report;
  const expected = await contentChecksum(addressed);
  return (
    expected === report.content_checksum &&
    report.report_id === `REPORT-${String(report.content_checksum).slice(0, 20)}`
  );
}

async function isCanonicalQuickDesignResponse(
  value: unknown,
): Promise<boolean> {
  if (
    !isRecord(value) ||
    !isRecord(value.contract) ||
    !isRecord(value.report) ||
    !isRecord(value.planned_design) ||
    typeof value.planned_design.plan_id !== "string" ||
    !hasExactArtifactShapes(value.artifacts)
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
    report.schema_version === "8.0.0" &&
    isNonEmptyString(report.report_id) &&
    isSha256(report.content_checksum) &&
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
    Array.isArray(report.verified_pipeline_contexts) &&
    report.verified_pipeline_contexts.length === querySections.length &&
    Array.isArray(sourceRecords) &&
    sourceRecords.length > 0 &&
    sourceIds.size === sourceRecords.length &&
    sourceRecords.every(isSourceRecord) &&
    Array.isArray(evidenceRecords) &&
    evidenceRecords.length > 0 &&
    evidenceRecords.every((evidence) => isEvidenceRecord(evidence, sourceIds)) &&
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
    ) &&
    (await hasExactArtifacts(value.artifacts)) &&
    (await hasCanonicalReportIntegrity(report))
  );
}

const QUICK_DESIGN_RESULT_KEYS = [
  "schema_version",
  "planned_design",
  "pipeline_result",
  "report_bundle",
  "artifacts",
] as const;

const PLANNED_DESIGN_KEYS = [
  "schema_version",
  "plan_id",
  "content_checksum",
  "experiment_block_id",
  "inferential_queries",
  "query_checksums",
  "sources",
  "evidence_records",
  "confirmation_events",
  "event_registry",
  "count_records",
  "sample_sheet_ref",
  "methods_draft_ref",
  "id_convention_ref",
  "user_confirmation_scopes",
] as const;

const PIPELINE_RESULT_KEYS = [
  "schema_version",
  "execution_manifest",
  "claim_set",
  "design_adequacy_evaluations",
  "report_resolution",
  "profile_coverage",
  "scenario_coverages",
  "stage_order",
] as const;

const PIPELINE_STAGE_ORDER = [
  "FACT_VERIFICATION",
  "THEORY_DERIVATION",
  "CLAIM_VERIFICATION",
  "RULE_ADEQUACY",
  "REPORT_RESOLUTION",
] as const;

function normalizeQuickDesignV8Result(
  value: QuickDesignV8ResultWire,
): QuickDesignV8Response {
  return {
    planned_design: value.planned_design,
    report: value.report_bundle,
    artifacts: value.artifacts,
    contract: {
      code: "PRD_V8",
      version: "8.0.0",
      strategy_module_status: "HANDOFF_ONLY",
      guided_confirmation: true,
    },
  };
}

async function isAddressedPlannedDesign(value: unknown): Promise<boolean> {
  if (
    !hasV8Schema(value) ||
    !hasExactKeys(value, PLANNED_DESIGN_KEYS) ||
    !isNonEmptyString(value.plan_id) ||
    !isSha256(value.content_checksum) ||
    value.plan_id !== `PLAN-${value.content_checksum.slice(0, 20)}` ||
    !isNonEmptyString(value.experiment_block_id) ||
    !Array.isArray(value.inferential_queries) ||
    value.inferential_queries.length !== 1 ||
    !value.inferential_queries.every(
      (query) => isRecord(query) && isNonEmptyString(query.id),
    ) ||
    !isStringArray(value.query_checksums) ||
    value.query_checksums.length !== value.inferential_queries.length ||
    !isNonEmptyString(value.sample_sheet_ref) ||
    !isNonEmptyString(value.methods_draft_ref) ||
    !isNonEmptyString(value.id_convention_ref)
  ) {
    return false;
  }
  const queryChecksums = await Promise.all(
    value.inferential_queries.map((query) => contentChecksum(query)),
  );
  const { plan_id: _planId, content_checksum: _checksum, ...addressed } = value;
  return (
    pythonJson(queryChecksums) === pythonJson(value.query_checksums) &&
    (await contentChecksum(addressed)) === value.content_checksum
  );
}

function isPipelineResultShape(value: unknown): value is JsonRecord {
  return (
    hasV8Schema(value) &&
    hasExactKeys(value, PIPELINE_RESULT_KEYS) &&
    isExecutionManifest(value.execution_manifest) &&
    isClaimSet(value.claim_set) &&
    Array.isArray(value.design_adequacy_evaluations) &&
    value.design_adequacy_evaluations.every(isAdequacyEvaluation) &&
    isRecord(value.report_resolution) &&
    isKnowledgeValue(value.report_resolution.resolution) &&
    isProfileCoverage(value.profile_coverage) &&
    Array.isArray(value.scenario_coverages) &&
    value.scenario_coverages.every(isScenarioCoverage) &&
    pythonJson(value.stage_order) === pythonJson(PIPELINE_STAGE_ORDER)
  );
}

async function isQuickDesignV8ResultWire(
  value: unknown,
  reviewedBundle: unknown,
): Promise<boolean> {
  if (
    !hasV8Schema(value) ||
    !hasExactKeys(value, QUICK_DESIGN_RESULT_KEYS) ||
    !(await isAddressedPlannedDesign(value.planned_design)) ||
    !isPipelineResultShape(value.pipeline_result) ||
    !isRecord(value.report_bundle) ||
    !hasExactArtifactShapes(value.artifacts)
  ) {
    return false;
  }
  const plan = value.planned_design;
  const pipeline = value.pipeline_result;
  const report = value.report_bundle;
  const normalized = normalizeQuickDesignV8Result(
    value as unknown as QuickDesignV8ResultWire,
  );
  if (!(await isCanonicalQuickDesignResponse(normalized))) return false;

  const designContext = report.design_record_context;
  const plannedSnapshot = isRecord(designContext)
    ? designContext.planned_design_record
    : undefined;
  const contexts = report.verified_pipeline_contexts;
  const ledgers = isKnowledgeValue(report.prospective_input_ledgers)
    ? report.prospective_input_ledgers.value
    : undefined;
  const artifactIdsByKind = new Map(
    value.artifacts.map((artifact) => [artifact.kind, artifact.artifact_id]),
  );
  if (
    !isConformanceBundle(reviewedBundle) ||
    !Array.isArray(contexts) ||
    contexts.length !== 1 ||
    !isRecord(contexts[0]) ||
    pythonJson(contexts[0].conformance_bundle_payload) !== pythonJson(reviewedBundle)
  ) {
    return false;
  }
  const expectedManifest = await expectedExecutionManifest(reviewedBundle);
  if (
    expectedManifest === undefined ||
    pythonJson(pipeline.execution_manifest) !== pythonJson(expectedManifest)
  ) {
    return false;
  }
  return (
    isKnowledgeValue(plannedSnapshot) &&
    plannedSnapshot.knowledge_state === "PRESENT" &&
    pythonJson(plannedSnapshot.value) === pythonJson(plan) &&
    isRecord(plan) &&
    plan.sample_sheet_ref === artifactIdsByKind.get("SAMPLE_SHEET") &&
    plan.methods_draft_ref === artifactIdsByKind.get("METHODS_DRAFT") &&
    plan.id_convention_ref === artifactIdsByKind.get("ID_CONVENTION") &&
    pythonJson(contexts[0].result_payload) === pythonJson(pipeline) &&
    pythonJson(pipeline.execution_manifest) === pythonJson(report.execution_manifest) &&
    Array.isArray(report.claim_sets) &&
    report.claim_sets.length === 1 &&
    pythonJson(pipeline.claim_set) === pythonJson(report.claim_sets[0]) &&
    pythonJson(pipeline.design_adequacy_evaluations) ===
      pythonJson(report.design_adequacy_evaluations) &&
    pythonJson(pipeline.report_resolution) === pythonJson(report.report_resolution) &&
    pythonJson(pipeline.profile_coverage) === pythonJson(report.profile_coverage) &&
    pythonJson(pipeline.scenario_coverages) === pythonJson(report.scenario_coverages) &&
    Array.isArray(ledgers) &&
    ledgers.length === 1 &&
    isRecord(ledgers[0]) &&
    pythonJson(ledgers[0].artifacts) === pythonJson(value.artifacts)
  );
}

function canonicalGuidedTextAnswer(value: unknown): JsonRecord {
  const answer = value as JsonRecord;
  return answer.status === "PROVIDED"
    ? { status: "PROVIDED", value: answer.value }
    : { status: "NOT_AVAILABLE", rationale: answer.rationale };
}

function canonicalGuidedIdSetAnswer(value: unknown): JsonRecord {
  const answer = value as JsonRecord;
  return answer.status === "PROVIDED"
    ? { status: "PROVIDED", values: answer.values }
    : { status: "NOT_AVAILABLE", rationale: answer.rationale };
}

function canonicalGuidedTimingAnswer(value: unknown): JsonRecord {
  const answer = value as JsonRecord;
  return answer.status === "PROVIDED"
    ? { status: "PROVIDED", relation: answer.relation }
    : { status: "NOT_AVAILABLE", rationale: answer.rationale };
}

function canonicalSemanticGuidedDraft(value: unknown): JsonRecord {
  const draft = value as JsonRecord;
  const groups = draft.planned_groups as JsonRecord[];
  return {
    template_id: draft.template_id,
    block_title: draft.block_title,
    source_description: canonicalGuidedTextAnswer(draft.source_description),
    preparation_description: canonicalGuidedTextAnswer(draft.preparation_description),
    biological_source_unit_type: canonicalGuidedTextAnswer(
      draft.biological_source_unit_type,
    ),
    candidate_unit_type: canonicalGuidedTextAnswer(draft.candidate_unit_type),
    factor_id: draft.factor_id,
    factor_levels: draft.factor_levels,
    contrast_id: draft.contrast_id,
    endpoint_id: draft.endpoint_id,
    timepoint_id: draft.timepoint_id,
    estimand: draft.estimand,
    population_scope: draft.population_scope,
    inference_level: draft.inference_level,
    assignment_unit_type: canonicalGuidedTextAnswer(draft.assignment_unit_type),
    assignment_unit_ids: canonicalGuidedIdSetAnswer(draft.assignment_unit_ids),
    application_unit_type: canonicalGuidedTextAnswer(draft.application_unit_type),
    application_unit_ids: canonicalGuidedIdSetAnswer(draft.application_unit_ids),
    intervention_id: canonicalGuidedTextAnswer(draft.intervention_id),
    effective_exposure_unit_type: canonicalGuidedTextAnswer(
      draft.effective_exposure_unit_type,
    ),
    exposed_unit_ids: canonicalGuidedIdSetAnswer(draft.exposed_unit_ids),
    exposure_pathway: canonicalGuidedTextAnswer(draft.exposure_pathway),
    exposure_container: canonicalGuidedTextAnswer(draft.exposure_container),
    interference: {
      status: (draft.interference as JsonRecord).status,
      rationale: (draft.interference as JsonRecord).rationale,
    },
    assignment_to_application_timing: canonicalGuidedTimingAnswer(
      draft.assignment_to_application_timing,
    ),
    planned_unit_type: canonicalGuidedTextAnswer(draft.planned_unit_type),
    planned_groups: groups.map((group) => ({
      group_id: group.group_id,
      cohort_id: canonicalGuidedTextAnswer(group.cohort_id),
      factor_level: group.factor_level,
      planned_count: group.planned_count,
    })),
  };
}

async function isGuidedBuildResponse(
  value: unknown,
  expectedDraft: GuidedQuickDesignBuildRequest["draft"],
): Promise<boolean> {
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
    value.question_queue.length < 1 ||
    value.visible_questions.length !== Math.min(3, value.question_queue.length) ||
    !hasExactArtifactShapes(value.artifact_previews) ||
    !isRecord(value.review_snapshot) ||
    value.review_snapshot.schema_version !== "8.0.0" ||
    !isGuidedDraft(value.review_snapshot.draft) ||
    !isGuidedDraft(expectedDraft) ||
    !isConformanceBundle(value.review_snapshot.conformance_bundle_payload) ||
    value.review_snapshot.is_execution_capability !== false ||
    pythonJson(canonicalSemanticGuidedDraft(value.review_snapshot.draft)) !==
      pythonJson(canonicalSemanticGuidedDraft(expectedDraft)) ||
    !isKnowledgeValue(value.submission_audit_snapshot) ||
    !isKnowledgeValue(value.canonical_result) ||
    !isKnowledgeValue(value.confirmed_snapshot_checksum)
  ) {
    return false;
  }
  const validQuestions =
    value.question_queue.every(isGuidedQuestion) &&
    value.visible_questions.every(isGuidedQuestion);
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
    pythonJson(value.visible_questions) !== pythonJson(value.question_queue.slice(0, 3)) ||
    !(await hasExactArtifacts(value.artifact_previews)) ||
    !(await hasValidConformanceAssetChecksums(
      value.review_snapshot.conformance_bundle_payload,
    )) ||
    !(await hasCanonicalGuidedPreviewProjection(value))
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
  if (
    value.action !== "CONFIRM" ||
    value.state !== "BUILT" ||
    value.submission_audit_snapshot.knowledge_state !== "PRESENT" ||
    !isQuickDesignSubmission(value.submission_audit_snapshot.value) ||
    value.canonical_result.knowledge_state !== "PRESENT" ||
    !(await isQuickDesignV8ResultWire(
      value.canonical_result.value,
      value.review_snapshot.conformance_bundle_payload,
    )) ||
    value.confirmed_snapshot_checksum.knowledge_state !== "PRESENT" ||
    typeof value.confirmed_snapshot_checksum.value !== "string" ||
    !/^[0-9a-f]{64}$/.test(value.confirmed_snapshot_checksum.value)
  ) {
    return false;
  }
  const rawResult = value.canonical_result.value as QuickDesignV8ResultWire;
  const expectedConfirmedChecksum = await contentChecksum({
    preview_checksum: value.preview_checksum,
    submission_audit_snapshot: value.submission_audit_snapshot.value,
    canonical_result: rawResult,
  });
  return (
    expectedConfirmedChecksum === value.confirmed_snapshot_checksum.value &&
    pythonJson(value.artifact_previews) === pythonJson(rawResult.artifacts)
  );
}

function sanitizeLegacyValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sanitizeLegacyValue);
  if (!isRecord(value)) return value === "ready_for_review" ? "review_required" : value;
  const isScientificVerdictOrStrategy = (field: string): boolean => {
    const normalized = field.toLocaleLowerCase().replace(/[^a-z0-9]/g, "");
    return (
      normalized.includes("verdict") ||
      normalized.includes("strateg") ||
      normalized.includes("determinability") ||
      normalized.includes("designadequacy") ||
      normalized.includes("statisticalhandoff")
    );
  };
  return Object.fromEntries(
    Object.entries(value)
      .filter(([field]) => !isScientificVerdictOrStrategy(field))
      .map(([field, item]) => [field, sanitizeLegacyValue(item)]),
  );
}

function neutralLegacyReviewOutput(blockId: string, value: unknown): JsonRecord {
  const neutralized = sanitizeLegacyValue(value);
  const sanitized = isRecord(neutralized) ? neutralized : {};
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
  if (!(await isCanonicalQuickDesignResponse(result))) {
    throw new Error("The canonical endpoint returned a malformed PRD_V8 ReportBundle.");
  }
  return result as QuickDesignV8Response;
}

export async function buildQuickDesignSubmission(
  payload: GuidedQuickDesignBuildRequest,
): Promise<GuidedQuickDesignBuildResponse> {
  const result = await request<unknown>("/v8/quick-design/build-submission", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  if (!(await isGuidedBuildResponse(result, payload.draft))) {
    throw new Error("The guided endpoint returned a malformed PRD v8 build response.");
  }
  if (
    isRecord(result) &&
    result.action === "CONFIRM" &&
    isKnowledgeValue(result.canonical_result) &&
    result.canonical_result.knowledge_state === "PRESENT"
  ) {
    const wire = result.canonical_result.value as QuickDesignV8ResultWire;
    return {
      ...(result as unknown as GuidedQuickDesignBuildResponse),
      canonical_result: {
        ...result.canonical_result,
        value: normalizeQuickDesignV8Result(wire),
      } as KnowledgeValue<QuickDesignV8Response>,
    };
  }
  return result as GuidedQuickDesignBuildResponse;
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
