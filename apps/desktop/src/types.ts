export type Severity = "critical" | "high" | "medium" | "info" | "insufficient";

export interface Provenance {
  origin: string;
  evidence_ids?: string[];
  rule_id?: string | null;
  ruleset_version?: string | null;
  derivation?: string | null;
  document_version?: string | null;
  extraction_method?: string | null;
  timestamp?: string | null;
  actor_role?: string | null;
}

export interface EvidenceSpan {
  id: string;
  file_id: string;
  section_id?: string | null;
  section_title?: string | null;
  start?: number | null;
  end?: number | null;
  text: string;
  parser_version: string;
  evidence_type?:
    | "STRUCTURAL_FACT"
    | "AUTHOR_ASSERTION"
    | "SAMPLE_METADATA"
    | "STATISTICAL_CODE"
    | "USER_CONFIRMATION"
    | "MODEL_INFERENCE"
    | "DERIVED_FACT"
    | "CONFLICTING_EVIDENCE";
  page?: number | null;
  document_version?: string | null;
  extraction_method?: string | null;
  cell?: {
    table_id: string;
    row: number;
    column: string;
    sheet?: string | null;
  } | null;
}

export interface GraphNode {
  id: string;
  type: string;
  label: string;
  count?: number | null;
  attributes: Record<string, string | number | boolean | null>;
  evidence_ids: string[];
  confidence: number;
  provenance: Provenance;
}

export interface GraphRelation {
  id: string;
  type: string;
  source: string;
  target: string;
  attributes: Record<string, string | number | boolean | null>;
  evidence_ids: string[];
  confidence: number;
  provenance: Provenance;
}

export interface Alert {
  id: string;
  rule_id: string;
  ruleset_version: string;
  severity: Severity;
  alert_class?: "design_replication" | "analytical_dependence" | "inference_scope";
  message: string;
  confidence: number;
  premise_confidence?: number | null;
  evidence_ids: string[];
  missing_information: string[];
  requires_human_confirmation: boolean;
}

export interface Question {
  id: string;
  text: string;
  reason: string;
  missing_field?: string | null;
  priority?: number;
  decisive?: boolean;
  impact?: string;
}

export interface NStatement {
  id: string;
  value?: number | null;
  entity_type: string;
  node_type?: string | null;
  raw_text: string;
  evidence_ids: string[];
  confidence: number;
}

export interface Factor {
  id: string;
  name: string;
  levels: string[];
  kind: string;
  assignment_level?: string | null;
  assignment_confidence: number;
  allocation_level?: string | null;
  application_level?: string | null;
  allocation_confidence?: number;
  application_confidence?: number;
  randomized?: boolean | null;
  evidence_ids: string[];
}

export interface Contrast {
  id: string;
  label: string;
  factor_id: string;
  factor_ids?: string[];
  group_a?: string | null;
  group_b?: string | null;
  endpoint_ids: string[];
  evidence_ids: string[];
}

export interface Endpoint {
  id: string;
  name: string;
  measured_on?: string | null;
  timepoints: string[];
  aggregation?: string | null;
  evidence_ids: string[];
}

export interface InferenceTarget {
  id: string;
  question_text: string;
  claim_text: string;
  population_of_inference: string;
  factor_ids: string[];
  contrast_ids: string[];
  endpoint_ids: string[];
  target_biological_unit?: string | null;
  evidence_ids: string[];
  status: "extracted" | "user_confirmed" | "missing" | "conflicted";
}

export interface Estimand {
  id: string;
  endpoint_id: string;
  effect_measure: string;
  target_population_or_unit: string;
  generalization_level: string;
  factor_ids: string[];
  timepoint?: string | null;
  condition?: string | null;
  evidence_ids: string[];
  provenance?: Provenance;
}

export interface Correction {
  id: string;
  sequence: number;
  reason: string;
  rationale: string;
  patch: Array<Record<string, unknown>>;
  evidence_ids: string[];
  reviewer_role?: string | null;
  recorded_at?: string | null;
  verified: boolean;
}

export type CountQuantifier =
  | "EXACT"
  | "LOWER_BOUND"
  | "UPPER_BOUND"
  | "APPROXIMATE"
  | "RANGE"
  | "UNKNOWN"
  | "NOT_REPORTED";

export interface CountScope {
  unit_type?: string | null;
  factor_id?: string | null;
  contrast_id?: string | null;
  group_or_level?: string | null;
  endpoint_id?: string | null;
  timepoint?: string | null;
  lifecycle?: "planned" | "allocated" | "treated" | "observed" | "excluded" | "analysed" | null;
  population?: string | null;
  condition?: string | null;
  unknown_reasons: Record<string, string>;
}

export interface CountRecord {
  count_id: string;
  kind:
    | "planned_n"
    | "allocated_n"
    | "treated_n"
    | "observed_n"
    | "excluded_n"
    | "analysed_n"
    | "declared_n"
    | "observational_n"
    | "analytical_n"
    | "independent_n"
    | "biological_source_count"
    | "effective_n";
  value?: number | null;
  quantifier: CountQuantifier;
  lower_bound?: number | null;
  upper_bound?: number | null;
  scope: CountScope;
  evidence_ids: string[];
  rule_trace_ids: string[];
  diagnostic_only: boolean;
  provenance: Provenance;
}

export interface ExclusionRecord {
  id: string;
  unit_id?: string | null;
  unit_type: string;
  phase:
    | "pre_allocation"
    | "post_allocation"
    | "post_treatment"
    | "post_measurement"
    | "post_outcome"
    | "unknown";
  prespecified: "TRUE" | "FALSE" | "UNKNOWN";
  endpoint_id?: string | null;
  factor_id?: string | null;
  contrast_id?: string | null;
  group?: string | null;
  author_role?: string | null;
  reason?: string | null;
  evidence_ids: string[];
  impact?: string | null;
  unknown_reasons: Record<string, string>;
  provenance: Provenance;
}

export interface ProcessFact {
  id: string;
  kind: string;
  detail: string;
  node_type?: string | null;
  value?: number | null;
  endpoint_hint?: string | null;
  group_hint?: string | null;
  evidence_ids: string[];
  provenance: Provenance;
}

export interface PlausibleGraphSet {
  id: string;
  discriminating_question_id: string;
  evidence_ids: string[];
  provenance: Provenance;
  alternatives: Array<{
    id: string;
    label: string;
    hierarchy: { nodes: GraphNode[]; relations: GraphRelation[] };
    evidence_ids: string[];
    provenance: Provenance;
    consequences: Array<{
      id: string;
      description: string;
      experimental_unit?: string | null;
      n_independent?: number | null;
      n_independent_by_group: Record<string, number>;
      evidence_ids: string[];
      provenance: Provenance;
      scope: Record<string, unknown>;
    }>;
  }>;
}

export interface AssessmentScope {
  factor_id?: string | null;
  contrast_id?: string | null;
  endpoint_id?: string | null;
  group?: string | null;
  timepoint?: string | null;
  inference_target_id?: string | null;
  unit_type?: string | null;
  lifecycle?: string | null;
  population?: string | null;
  condition?: string | null;
  is_global: boolean;
}

export interface ConditionalScenario {
  conditional_on: string;
  if_confirmed: Record<string, number | null>;
  if_rejected: Record<string, number | null>;
  question: string;
  rule_id: string;
  evidence_ids: string[];
}

export interface UnitAssessment {
  id: string;
  scope: AssessmentScope;
  biological_unit?: string | null;
  allocation_unit_candidate?: string | null;
  experimental_unit?: string | null;
  observational_unit?: string | null;
  analytical_unit?: string | null;
  n_planned?: number | null;
  n_declared?: number | null;
  n_allocated?: number | null;
  n_treated?: number | null;
  n_observed?: number | null;
  n_excluded?: number | null;
  n_analysed?: number | null;
  n_independent?: number | null;
  biological_source_count?: number | null;
  effective_n?: number | null;
  inferability: string;
  conditional_scenarios: ConditionalScenario[];
  risk: string;
  rationale: string;
  evidence_ids: string[];
  provenance: Provenance;
}

export interface Contradiction {
  id: string;
  description: string;
  statement_ids: string[];
  evidence_ids: string[];
  retained_interpretations: string[];
  status: "unresolved" | "resolved_by_user" | "resolved_by_adjudication";
  provenance?: Provenance | null;
}

export interface ExperimentBlock {
  id: string;
  title: string;
  document_id: string;
  source_file_ids: string[];
  inference_targets: InferenceTarget[];
  hierarchy: { nodes: GraphNode[]; relations: GraphRelation[] };
  factors: Factor[];
  contrasts: Contrast[];
  endpoints: Endpoint[];
  estimands: Estimand[];
  n_statements: NStatement[];
  count_records: CountRecord[];
  exclusion_records: ExclusionRecord[];
  processes: ProcessFact[];
  plausible_graph_set?: PlausibleGraphSet | null;
  unit_assessments: UnitAssessment[];
  alerts: Alert[];
  questions: Question[];
  contradictions: Contradiction[];
  evidence: EvidenceSpan[];
  corrections: Correction[];
  versions: Record<string, string | null>;
}

export interface BlockSummary {
  block_id: string;
  title: string;
  max_severity?: Severity | null;
  n_alerts: number;
  n_questions: number;
  n_unresolved_conflicts: number;
  assessments_with_independent_n: number;
  assessments_total: number;
  abstained: boolean;
}

export interface DomainTransparency {
  declared_domain: string;
  normalized_domain?: string;
  validation_status: "validated" | "unvalidated" | "out_of_scope" | "unknown";
  ood_assessment: string;
  requires_acknowledgement: boolean;
  warning: string;
}

export interface DesignQuestion {
  id: string;
  text: string;
  reason: string;
  missing_field?: string | null;
}

export interface DesignCompilation {
  specification_id: string;
  status: "ready" | "abstained";
  abstained: boolean;
  elicitation: {
    questions: DesignQuestion[];
    blocking_question_ids: string[];
    complete: boolean;
  };
  analysis_handoff: {
    target_population_support: "unknown" | "conditional" | "supported";
    targets: Array<{
      inference_target_id: string;
      status: InferenceTarget["status"];
      question_text: string;
      claim_text: string;
      population_of_inference: string;
      target_biological_unit?: string | null;
      target_population_support: "unknown" | "conditional" | "supported";
      estimand_ids?: string[];
    }>;
    estimands?: Array<{
      estimand_id: string;
      endpoint_id: string;
      effect_measure: string;
      target_population_or_unit: string;
      generalization_level: string;
      factor_ids: string[];
      timepoint?: string | null;
      condition?: string | null;
      evidence_ids: string[];
    }>;
    unresolved_assumptions: Array<{
      id: string;
      code: string;
      message: string;
      blocking: boolean;
    }>;
    prohibited_outputs: string[];
  };
}

export interface Report {
  report_id: string;
  project_id: string;
  project_name: string;
  language: string;
  domain_transparency: DomainTransparency;
  versions: Record<string, string | null>;
  blocks: ExperimentBlock[];
  summaries: BlockSummary[];
  design_compilations: Record<string, DesignCompilation>;
  rule_evaluations?: Record<string, unknown[]>;
  positive_outputs?: Record<string, BlockPositiveOutput>;
  parser_warnings: string[];
  limits: string[];
  content_checksum?: string;
  disclaimer?: string;
}

export interface BlockPositiveOutput {
  block_id: string;
  path_status: "ready_for_review" | "conditional" | "incomplete";
  status_reason: string;
  non_certifying: boolean;
  methods_statement: {
    text: string;
    language: string;
    evidence_ids: string[];
    status: "ready_for_review" | "conditional" | "incomplete";
    non_certifying: boolean;
    limitations: string[];
  };
  n_table: Array<{
    assessment_id: string;
    scope: string;
    biological_unit?: string | null;
    experimental_unit?: string | null;
    observational_unit?: string | null;
    analytical_unit?: string | null;
    n_declared?: number | null;
    n_observational?: number | null;
    n_independent?: number | null;
    n_allocated?: number | null;
    n_analyzed?: number | null;
    inferability: string;
    conditional_scenarios: Array<Record<string, unknown>>;
    evidence_ids: string[];
  }>;
  count_records?: CountRecord[];
  diagnostic_count_records?: CountRecord[];
  suppressed_count_record_ids?: string[];
  exclusion_records?: ExclusionRecord[];
  plausible_graph_set?: PlausibleGraphSet | null;
  discriminating_question?: Question | null;
  driver_checklist: Array<{
    item_id: string;
    title: string;
    status: "present" | "partial" | "missing" | "not_assessed";
    note: string;
    evidence_ids: string[];
    source_url: string;
  }>;
  statements: Array<{
    id: string;
    layer: "fact" | "assertion" | "inference" | "hypothesis" | "limitation";
    text: string;
    evidence_ids: string[];
    source: string;
  }>;
  candidate_analysis_strategies: string[];
  decisive_question_ids: string[];
}

export interface PrivacyAudit {
  document_id: string;
  status: "clean" | "review_required";
  scanned_fields: number;
  scanned_asset_ids: string[];
  scans_with_findings: Array<{
    artifact_id: string;
    field_path: string;
    original_checksum: string;
    findings: Array<{
      finding_id: string;
      kind: "email" | "local_path" | "name_like" | "sample_id";
      masked_preview: string;
      line: number;
      column: number;
    }>;
  }>;
  finding_count: number;
  original_sources_mutated: false;
  detector_version: string;
}

export interface ShareReadiness {
  analysis_allowed: true;
  share_ready: false;
  redistribute_ready: false;
  privacy_status: PrivacyAudit["status"];
  governance_status: "not_evaluated";
  privacy_audit_checksum: string;
  assets: Array<{
    asset_id: string;
    sha256: string;
    governance_record_id?: string | null;
    governance_record_hash?: string | null;
    license_manifest_id?: string | null;
  }>;
  reasons: string[];
  requires_explicit_distribution_check: true;
}

export interface AnalysisResponse {
  report: Report;
  ingest_summary: string;
  artifacts: Record<string, string>;
  domain_transparency: DomainTransparency;
  session_id?: string;
  run_id?: string;
  revision?: number;
  output_dir?: string;
  privacy_audit: PrivacyAudit;
  share_readiness: ShareReadiness;
}

export interface AuditEntry {
  id: string;
  sequence: number;
  action: "apply" | "undo" | "redo";
  correction_id: string;
  actor_role?: string;
  recorded_at?: string;
  /** Legacy demo field; authoritative API responses use recorded_at. */
  at?: string;
}
