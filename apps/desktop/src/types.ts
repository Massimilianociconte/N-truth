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
  at?: string;
}
