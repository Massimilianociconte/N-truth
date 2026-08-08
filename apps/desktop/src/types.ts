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
  verified: boolean;
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
  unit_assessments: Array<Record<string, unknown>>;
  alerts: Alert[];
  questions: Question[];
  contradictions: Array<Record<string, unknown>>;
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
  review_outputs?: Record<string, BlockReviewOutput>;
  parser_warnings: string[];
  limits: string[];
  content_checksum?: string;
  disclaimer?: string;
}

export type DeterminabilityState =
  | "DETERMINATE"
  | "CONDITIONALLY_DETERMINATE"
  | "MULTIPLE_PLAUSIBLE_GRAPHS"
  | "INSUFFICIENT_INFORMATION"
  | "CONFLICTING_INFORMATION"
  | "INVALID_GRAPH"
  | "OUT_OF_SCOPE";

export type ScientificKnowledgeState =
  | "PRESENT"
  | "ABSENT_EXPLICIT"
  | "NOT_REPORTED"
  | "UNKNOWN"
  | "NOT_APPLICABLE"
  | "CONFLICTING";

export interface KnowledgeValue<T = unknown> {
  knowledge_state: ScientificKnowledgeState;
  value?: T | null;
  rationale?: string | null;
  evidence_ids?: string[];
  query_scope_id?: string | null;
}

export interface BlockReviewOutput {
  block_id: string;
  path_status: "review_required" | "conditional" | "incomplete";
  status_reason: string;
  non_certifying: boolean;
  methods_statement: {
    text: string;
    language: string;
    evidence_ids: string[];
    status: "review_required" | "conditional" | "incomplete";
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
    layer: "fact" | "inference" | "hypothesis" | "limitation";
    text: string;
    evidence_ids: string[];
    source: string;
  }>;
  determinability: {
    state: DeterminabilityState;
    rationale: string;
  };
  design_adequacy: {
    knowledge_state: ScientificKnowledgeState;
    finding: string;
    rationale: string;
  };
  strategy_module_status: "HANDOFF_ONLY";
  statistical_handoff: {
    structural_requirements: string[];
    unresolved_questions: string[];
  };
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

export interface QuickDesignV8Submission {
  pipeline_request: Record<string, unknown>;
  planned_sources: unknown[];
  planned_event_registry?: Record<string, unknown>;
  planned_unit_counts?: unknown[];
  sample_sheet_csv?: string;
  methods_draft?: string;
  id_convention?: string;
  user_confirmation_scopes?: string[];
  ai_candidates?: KnowledgeValue<unknown[]>;
  human_confirmations?: KnowledgeValue<unknown[]>;
  conflicts?: KnowledgeValue<Array<Record<string, unknown>>>;
  sensitivities?: KnowledgeValue<unknown[]>;
  questions?: unknown[];
  statistical_handoff?: StatisticalHandoffV8;
  inference_limits?: string[];
  [field: string]: unknown;
}

export interface DerivedClaimV8 {
  claim_id: string;
  claim_type: string;
  inferential_query_id: string;
  value: KnowledgeValue;
  determinability_state: DeterminabilityState;
  support_grade: {
    token: string;
    vocabulary_id: string;
    [field: string]: unknown;
  };
  proof_trace: Array<{
    theory_clause_id: string;
    rule_id: string;
    [field: string]: unknown;
  }>;
  required_predicates: string[];
  irrelevant_predicates: Array<{ id: string; rationale: string }>;
  assumptions: string[];
  sensitivity_records: string[];
  [field: string]: unknown;
}

export interface DerivedClaimSetV8 {
  claim_set_id: string;
  inferential_query_id: string;
  claims: DerivedClaimV8[];
}

export interface DesignAdequacyEvaluationV8 {
  evaluation_id: string;
  inferential_query_id: string;
  axis: string;
  outcome: KnowledgeValue;
  rationale: string;
}

export interface StatisticalHandoffV8 {
  strategy_module_status: "HANDOFF_ONLY";
  items: Array<{
    category: "STRUCTURAL_CONSTRAINT" | "UNRESOLVED_QUESTION";
    origin: string;
    authority: string;
    inferential_query_id: string;
    evidence_refs: string[];
    predicate_ids: string[];
    question_ids: string[];
    [field: string]: unknown;
  }>;
}

export interface ReportBundleV8 {
  report_id: string;
  content_checksum: string;
  epistemic_boundary: string;
  design_record_context: {
    mode: string;
    planned_design_record: KnowledgeValue<{ plan_id: string; content_checksum: string }>;
    executed_design_record: KnowledgeValue<Record<string, unknown>>;
    reconciliation_record: KnowledgeValue<Record<string, unknown>>;
    [field: string]: unknown;
  };
  source_records: Array<{
    source_id: string;
    source_context: string;
    source_class: { token: string; registry_id: string };
    source_version: string;
    [field: string]: unknown;
  }>;
  evidence_records: Array<{
    evidence_id: string;
    source_id: string;
    evidence_type: string;
    locator: string;
    [field: string]: unknown;
  }>;
  query_sections: Array<{
    inferential_query: { id: string; profile_id: string; [field: string]: unknown };
    claim_set: DerivedClaimSetV8;
    [field: string]: unknown;
  }>;
  claim_sets: DerivedClaimSetV8[];
  report_resolution: { resolution: KnowledgeValue; [field: string]: unknown };
  design_adequacy_evaluations: DesignAdequacyEvaluationV8[];
  count_registry: {
    registry_version: string;
    records: Array<{
      count_id: string;
      kind: string;
      quantifier: string;
      origin: string;
      value: KnowledgeValue<number>;
      scope: { query_id: string; [field: string]: unknown };
      rule_trace: string[];
      [field: string]: unknown;
    }>;
  };
  scenario_coverages: Array<{
    status: string;
    profile_id: string;
    emitting_clause_ids: string[];
    omitted_dimensions: KnowledgeValue<string[]>;
    caveat: KnowledgeValue<string>;
    [field: string]: unknown;
  }>;
  profile_coverage: {
    profile_id: string;
    statement_id: string;
    predicate_closure_argument_id: string;
    covered_predicate_ids: string[];
    known_gap_ids: string[];
    contract_review: { issue_id: string; status: string; rationale: string };
    [field: string]: unknown;
  };
  questions: Array<{
    question_id: string;
    inferential_query_id: string;
    text: string;
    evidence_required: string[];
    primary: boolean;
  }>;
  sensitivities: KnowledgeValue<Array<Record<string, unknown>>>;
  human_confirmations: KnowledgeValue<Array<Record<string, unknown>>>;
  conflicts: KnowledgeValue<Array<Record<string, unknown>>>;
  ai_candidates: Array<KnowledgeValue<Array<Record<string, unknown>>>>;
  confirmed_graph: {
    nodes: Array<{ node_id: string; node_type: string }>;
    relations: Array<Record<string, unknown>>;
  };
  execution_manifest: {
    manifest_id: string;
    theory_id: string;
    theory_version: string;
    theory_checksum: string;
    rulebook_id: string;
    rulebook_version: string;
    rulebook_checksum: string;
    release_blocker_issue_ids: string[];
    [field: string]: unknown;
  };
  statistical_handoff: StatisticalHandoffV8;
  strategy_module_status: "HANDOFF_ONLY";
  inference_limits: string[];
  [field: string]: unknown;
}

export interface QuickDesignV8Response {
  planned_design: { plan_id: string; [field: string]: unknown };
  report: ReportBundleV8;
  contract: {
    code: "PRD_V8";
    version: string;
    strategy_module_status: "HANDOFF_ONLY";
  };
}

export interface AuditEntry {
  id: string;
  sequence: number;
  action: "apply" | "undo" | "redo";
  correction_id: string;
  at?: string;
}
